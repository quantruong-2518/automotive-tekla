using System;
using System.Collections.Generic;

namespace TeklaHarness.Core;

/// <summary>
/// Contract safety rule 1, complete: the path-text guard (<see cref="ModelPathGuard"/>), then
/// file identity from the operating system (ADR-0009 Amendment, slice S1a).
/// </summary>
/// <remarks>
/// Identity catches aliases text cannot see (subst drives, junctions, symlinks, mount points,
/// mapped drives). Nesting is judged on the real ancestors: the parents of each folder's
/// final path, each resolved to an identity. Anything the OS cannot answer refuses.
/// </remarks>
public static class ModelLocationGuard
{
    public static ModelPathCheck Check(string? openModelPath, string? workingCopyPath, string? originalPath, IFolderResolver resolver)
    {
        if (resolver is null)
        {
            throw new ArgumentNullException(nameof(resolver));
        }

        var text = ModelPathGuard.Check(openModelPath, workingCopyPath, originalPath);
        if (!text.Allowed)
        {
            return text;
        }

        // The text guard accepted all three, so they parse; ask the OS with canonical text.
        WindowsPath.TryParse(openModelPath, out var open, out _);
        WindowsPath.TryParse(workingCopyPath, out var copy, out _);
        WindowsPath.TryParse(originalPath, out var original, out _);

        try
        {
            return CheckIdentities(open!, copy!, original!, resolver);
        }
#pragma warning disable CA1031 // A safety control refuses on any failure of the resolver.
        catch (Exception ex)
#pragma warning restore CA1031
        {
            return Refuse(PathRefusal.IdentityUnavailable, $"Folder identity check failed: {ex.GetType().Name}: {ex.Message}");
        }
    }

    private static ModelPathCheck CheckIdentities(WindowsPath openPath, WindowsPath copyPath, WindowsPath originalPath, IFolderResolver resolver)
    {
        var open = openPath.ToString();
        var copy = copyPath.ToString();
        var original = originalPath.ToString();
        if (!Resolve(resolver, open, "open model", out var openFolder, out var refusal)
            || !Resolve(resolver, copy, "working copy", out var copyFolder, out refusal)
            || !Resolve(resolver, original, "original", out var originalFolder, out refusal))
        {
            return refusal!;
        }

        if (openFolder!.Identity != copyFolder!.Identity)
        {
            return Refuse(PathRefusal.IdentityConflict, $"'{open}' named two different folders ({openFolder.Identity} then {copyFolder.Identity}).");
        }

        if (copyFolder.Identity == originalFolder!.Identity)
        {
            return Refuse(PathRefusal.WorkingCopyIsOriginal, $"Working copy '{copy}' is the original '{original}' (same folder identity {copyFolder.Identity}).");
        }

        // Over SMB the client cannot see above the share root or server-side junctions, and file
        // IDs through the redirector are undocumented: "different" is unprovable, so refuse.
        foreach (var folder in new[] { copyFolder, originalFolder })
        {
            if (FinalPath.IsRemote(folder.FinalPath))
            {
                return Refuse(PathRefusal.IdentityUnavailable, $"'{folder.FinalPath}' is a remote folder; it cannot be proven different from the other. Keep the working copy and the original on local drives.");
            }
        }

        // Copy inside the original, then original inside the copy. Each walk must finish cleanly;
        // a walk that cannot finish refuses even if the other one would pass.
        var seen = new Dictionary<string, ResolvedFolder>(StringComparer.Ordinal);
        var nesting = CheckNesting(resolver, seen, copyFolder.FinalPath, copyPath, originalFolder.Identity, copy, original)
            ?? CheckNesting(resolver, seen, originalFolder.FinalPath, originalPath, copyFolder.Identity, copy, original);
        if (nesting is not null)
        {
            return nesting;
        }

        // Tekla reports the path in its own logon session; subst and mapped letters are per
        // session. Only a path that is already the real path means the same folder to both.
        if (!string.Equals(copyFolder.FinalPath, @"\\?\" + copy, StringComparison.OrdinalIgnoreCase))
        {
            return Refuse(PathRefusal.WorkingCopyPathIsAlias, $"Working copy '{copy}' is reached through an alias (real path '{copyFolder.FinalPath}'). Declare and open the real path.");
        }

        // Same reason for the original's drive letter. Junctions on its own drive are global and
        // stay allowed; remote originals were refused above, so the final path has a drive letter.
        var realDrive = char.ToUpperInvariant(originalFolder.FinalPath[4]);
        if (realDrive != originalPath.Drive)
        {
            return Refuse(PathRefusal.OriginalPathIsAlias, $"Original '{original}' is reached through drive '{realDrive}:' (real path '{originalFolder.FinalPath}'). Declare the original by its real drive.");
        }

        // Links inside either folder lead out of it (a junction copied by robocopy /SJ still
        // points into the original). Hard-linked files in the copy share data with other files.
        var link = FindLink(resolver, copyFolder.FinalPath, includeHardLinks: true, "working copy")
            ?? FindLink(resolver, originalFolder.FinalPath, includeHardLinks: false, "original");
        if (link is not null)
        {
            return link;
        }

        return new ModelPathCheck(PathRefusal.None, $"Open model is the working copy '{copy}' (identity {copyFolder.Identity}).");
    }

    private static ModelPathCheck? FindLink(IFolderResolver resolver, string finalPath, bool includeHardLinks, string role)
    {
        if (!resolver.TryFindLink(finalPath, includeHardLinks, out var offender, out var error))
        {
            return Refuse(PathRefusal.IdentityUnavailable, $"The {role} '{finalPath}' cannot be scanned for links: {error}");
        }

        return offender is null
            ? null
            : Refuse(PathRefusal.LinkInsideFolder, $"The {role} contains a link or hard-linked file '{offender}' (any reparse point counts: junction, symlink, mount point, cloud-sync placeholder such as OneDrive). Remove it, or keep the model outside synced folders, before writing.");
    }

    /// <summary>
    /// A refusal when an ancestor of the folder (from its final path and from its typed path) is
    /// <paramref name="target"/> or cannot be read; null when clean.
    /// </summary>
    private static ModelPathCheck? CheckNesting(
        IFolderResolver resolver,
        Dictionary<string, ResolvedFolder> seen,
        string finalPath,
        WindowsPath typed,
        FileIdentity target,
        string copy,
        string original)
    {
        if (!FinalPath.TryGetAncestors(finalPath, out var ancestors, out var why))
        {
            return Refuse(PathRefusal.IdentityUnavailable, $"Final path '{finalPath}' cannot be walked ({why}).");
        }

        foreach (var parent in typed.LongAncestors())
        {
            if (!ancestors.Contains(parent))
            {
                ancestors.Add(parent);
            }
        }

        foreach (var ancestor in ancestors)
        {
            if (!seen.TryGetValue(ancestor, out var folder))
            {
                if (!Resolve(resolver, ancestor, "ancestor folder", out folder, out var refusal))
                {
                    return refusal;
                }

                seen[ancestor] = folder!;
            }

            if (folder!.Identity == target)
            {
                return Refuse(PathRefusal.WorkingCopyAndOriginalNested, $"Working copy '{copy}' and original '{original}' are nested (real folder '{ancestor}').");
            }
        }

        return null;
    }

    private static bool Resolve(IFolderResolver resolver, string path, string role, out ResolvedFolder? folder, out ModelPathCheck? refusal)
    {
        if (!resolver.TryResolve(path, out folder, out var error) || folder is null)
        {
            refusal = Refuse(PathRefusal.IdentityUnavailable, $"Identity of the {role} '{path}' cannot be read: {error}");
            return false;
        }

        // FILE_ID_INFO: all zeros = file system has no IDs, all ones = ID cannot be established.
        var id = folder.Identity;
        if ((id.FileIdHigh == 0 && id.FileIdLow == 0) || (id.FileIdHigh == ulong.MaxValue && id.FileIdLow == ulong.MaxValue))
        {
            refusal = Refuse(PathRefusal.IdentityUnavailable, $"The {role} '{path}' has no usable file ID ({id}).");
            folder = null;
            return false;
        }

        refusal = null;
        return true;
    }

    private static ModelPathCheck Refuse(PathRefusal refusal, string detail) => new(refusal, detail);
}

/// <summary>Parses OS final paths (<c>\\?\C:\…</c>, <c>\\?\UNC\server\share\…</c>) into their real ancestors.</summary>
internal static class FinalPath
{
    private const string Prefix = @"\\?\";
    private const string UncPrefix = @"\\?\UNC\";

    /// <summary>True for <c>\\?\UNC\…</c> paths (SMB shares, mapped drives).</summary>
    public static bool IsRemote(string finalPath) => finalPath.StartsWith(UncPrefix, StringComparison.OrdinalIgnoreCase);

    /// <summary>Ancestors from the root down, excluding the folder itself.</summary>
    public static bool TryGetAncestors(string? finalPath, out List<string> ancestors, out string reason)
    {
        ancestors = new List<string>();
        if (finalPath is null || !finalPath.StartsWith(Prefix, StringComparison.Ordinal))
        {
            reason = @"no \\?\ prefix";
            return false;
        }

        string root;
        string rest;
        if (finalPath.StartsWith(UncPrefix, StringComparison.OrdinalIgnoreCase))
        {
            var parts = finalPath.Substring(UncPrefix.Length).Split('\\');
            if (parts.Length < 2 || parts[0].Length == 0 || parts[1].Length == 0)
            {
                reason = "UNC path without server and share";
                return false;
            }

            root = UncPrefix + parts[0] + @"\" + parts[1];
            rest = string.Join(@"\", parts, 2, parts.Length - 2);
        }
        else
        {
            var body = finalPath.Substring(Prefix.Length);
            if (body.Length < 3 || !IsAsciiLetter(body[0]) || body[1] != ':' || body[2] != '\\')
            {
                reason = "neither a drive-letter nor a UNC final path";
                return false;
            }

            root = Prefix + body.Substring(0, 3);
            rest = body.Substring(3);
        }

        reason = string.Empty;
        if (rest.Length == 0)
        {
            return true; // the folder is the root itself: no ancestors
        }

        var segments = rest.Split('\\');
        foreach (var segment in segments)
        {
            if (segment.Length == 0 || segment == "." || segment == ".." || segment.IndexOf('/') >= 0)
            {
                reason = $"unexpected segment '{segment}'";
                return false;
            }
        }

        ancestors.Add(root);
        var current = root;
        for (var i = 0; i < segments.Length - 1; i++)
        {
            current = current.EndsWith(@"\", StringComparison.Ordinal) ? current + segments[i] : current + @"\" + segments[i];
            ancestors.Add(current);
        }

        return true;
    }

    private static bool IsAsciiLetter(char c) => c is >= 'A' and <= 'Z' or >= 'a' and <= 'z';
}
