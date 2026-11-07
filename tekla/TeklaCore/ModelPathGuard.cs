using System;
using System.Collections.Generic;
using System.Text;

namespace TeklaHarness.Core;

/// <summary>Why the model-path guard refused a write (contract safety rule 1).</summary>
public enum PathRefusal
{
    None,
    OpenPathUnprovable,
    WorkingCopyPathUnprovable,
    OriginalPathUnprovable,
    WorkingCopyIsOriginal,
    WorkingCopyAndOriginalNested,
    OpenIsOriginal,
    OpenIsNotWorkingCopy,

    /// <summary>S1a: the OS could not tell which folder a path names, or its final path cannot be walked.</summary>
    IdentityUnavailable,

    /// <summary>S1a: the same path text named two different folders (replaced between lookups).</summary>
    IdentityConflict,

    /// <summary>S1a: the working copy path goes through subst, a junction or a mapped letter.</summary>
    WorkingCopyPathIsAlias,

    /// <summary>S1a: the original is declared through a drive letter other than its real one (subst/mapped).</summary>
    OriginalPathIsAlias,

    /// <summary>S1a: a junction, symlink, mount point (or, in the copy, a hard-linked file) inside a folder.</summary>
    LinkInsideFolder,
}

/// <summary>Result of <see cref="ModelPathGuard.Check"/>.</summary>
public sealed class ModelPathCheck
{
    internal ModelPathCheck(PathRefusal refusal, string detail)
    {
        Refusal = refusal;
        Detail = detail;
    }

    public bool Allowed => Refusal == PathRefusal.None;

    public PathRefusal Refusal { get; }

    /// <summary>Human-readable reason, for the JSON output and the engineer.</summary>
    public string Detail { get; }

    /// <summary>Contract mapping: another model open is "wrong model" (3); every other refusal is a safety refusal (5).</summary>
    public ExitCode ExitCode => Refusal switch
    {
        PathRefusal.None => ExitCode.Ok,
        PathRefusal.OpenIsNotWorkingCopy => ExitCode.EnvironmentError,
        _ => ExitCode.RefusedBySafetyRule,
    };
}

/// <summary>
/// Contract safety rule 1, path-text part: refuse unless the path text shows the open model is the
/// declared working copy and the working copy cannot be the original (ADR-0009 §4 and Amendment).
/// Necessary, not sufficient: text cannot see aliases (subst, junctions, mapped drives); the
/// file-identity check of slice S1a must also pass before any write.
/// </summary>
/// <remarks>
/// Two comparisons, chosen so every doubt refuses:
/// <list type="bullet">
/// <item>"Same" (open vs working copy) is strict: ASCII letters ignore case, every other character
/// must match exactly. Spellings Windows might still treat as the same folder then refuse.</item>
/// <item>"Different" (anything vs the original) is loose: case-folded and Unicode-compatibility
/// normalised, so names that might be the same folder are treated as the same and refuse.</item>
/// </list>
/// Paths are parsed without <c>System.IO.Path</c>, whose rules differ on Linux where tests run.
/// </remarks>
public static class ModelPathGuard
{
    public static ModelPathCheck Check(string? openModelPath, string? workingCopyPath, string? originalPath)
    {
        if (!WindowsPath.TryParse(workingCopyPath, out var copy, out var why))
        {
            return Refuse(PathRefusal.WorkingCopyPathUnprovable, $"Declared working copy path cannot be checked ({why}): '{workingCopyPath}'.");
        }

        if (!WindowsPath.TryParse(originalPath, out var original, out why))
        {
            return Refuse(PathRefusal.OriginalPathUnprovable, $"Declared original path cannot be checked ({why}): '{originalPath}'.");
        }

        if (!WindowsPath.TryParse(openModelPath, out var open, out why))
        {
            return Refuse(PathRefusal.OpenPathUnprovable, $"Open model path cannot be checked ({why}): '{openModelPath}'.");
        }

        if (WindowsPath.LooseEquals(copy!, original!))
        {
            return Refuse(PathRefusal.WorkingCopyIsOriginal, $"Declared working copy '{workingCopyPath}' may be the original '{originalPath}'.");
        }

        if (WindowsPath.LooseIsAncestor(copy!, original!) || WindowsPath.LooseIsAncestor(original!, copy!))
        {
            return Refuse(PathRefusal.WorkingCopyAndOriginalNested, $"Declared working copy '{workingCopyPath}' and original '{originalPath}' are nested.");
        }

        if (WindowsPath.LooseEquals(open!, original!)
            || WindowsPath.LooseIsAncestor(open!, original!)
            || WindowsPath.LooseIsAncestor(original!, open!))
        {
            return Refuse(PathRefusal.OpenIsOriginal, $"Open model '{openModelPath}' may be, or overlap, the original '{originalPath}'.");
        }

        if (!WindowsPath.StrictEquals(open!, copy!))
        {
            return Refuse(PathRefusal.OpenIsNotWorkingCopy, $"Open model '{openModelPath}' is not the declared working copy '{workingCopyPath}'.");
        }

        return new ModelPathCheck(PathRefusal.None, $"Open model is the working copy '{workingCopyPath}'.");
    }

    private static ModelPathCheck Refuse(PathRefusal refusal, string detail) => new(refusal, detail);
}

/// <summary>An absolute drive-letter Windows path that the guard can reason about.</summary>
internal sealed class WindowsPath
{
    private const int MaxLength = 32767; // longest Windows path with the extended-length prefix

    private WindowsPath(char drive, List<string> segments)
    {
        Drive = drive;
        Segments = segments;
    }

    /// <summary>Upper-case ASCII drive letter.</summary>
    public char Drive { get; }

    /// <summary>Folder names as written, without empty and "." segments.</summary>
    public IReadOnlyList<string> Segments { get; }

    /// <summary>Canonical text: upper-case drive, backslashes, no trailing separator.</summary>
    public override string ToString() => Drive + @":\" + string.Join(@"\", Segments);

    /// <summary>Typed parent folders as <c>\\?\</c> paths, from the drive root down, excluding this folder.</summary>
    public IEnumerable<string> LongAncestors()
    {
        var current = @"\\?\" + Drive + @":\";
        yield return current;
        for (var i = 0; i < Segments.Count - 1; i++)
        {
            current = i == 0 ? current + Segments[i] : current + @"\" + Segments[i];
            yield return current;
        }
    }

    public static bool TryParse(string? raw, out WindowsPath? path, out string reason)
    {
        path = null;
        if (raw is null || raw.Trim().Length == 0)
        {
            reason = "empty";
            return false;
        }

        if (raw.Length > MaxLength)
        {
            reason = "too long";
            return false;
        }

        if (raw.Length < 3 || !IsAsciiLetter(raw[0]) || raw[1] != ':' || !IsSeparator(raw[2]))
        {
            reason = "not an absolute drive-letter path (relative, UNC, device or drive-relative)";
            return false;
        }

        var segments = new List<string>();
        foreach (var segment in raw.Substring(3).Split('\\', '/'))
        {
            if (segment.Length == 0 || segment == ".")
            {
                continue;
            }

            if (!IsProvableSegment(segment, out reason))
            {
                return false;
            }

            segments.Add(segment);
        }

        if (segments.Count == 0)
        {
            reason = "drive root";
            return false;
        }

        path = new WindowsPath(ToUpperAscii(raw[0]), segments);
        reason = string.Empty;
        return true;
    }

    /// <summary>Same folder for certain: drive and ASCII letters ignore case, everything else exact.</summary>
    public static bool StrictEquals(WindowsPath a, WindowsPath b)
    {
        if (a.Drive != b.Drive || a.Segments.Count != b.Segments.Count)
        {
            return false;
        }

        for (var i = 0; i < a.Segments.Count; i++)
        {
            if (!StrictSegmentEquals(a.Segments[i], b.Segments[i]))
            {
                return false;
            }
        }

        return true;
    }

    /// <summary>Possibly the same folder: false only when the paths are certainly different.</summary>
    public static bool LooseEquals(WindowsPath a, WindowsPath b)
        => a.Drive == b.Drive && a.Segments.Count == b.Segments.Count && LooseSharedPrefix(a, b, a.Segments.Count);

    /// <summary>Possibly a strict ancestor folder of <paramref name="descendant"/>.</summary>
    public static bool LooseIsAncestor(WindowsPath ancestor, WindowsPath descendant)
        => ancestor.Drive == descendant.Drive
           && ancestor.Segments.Count < descendant.Segments.Count
           && LooseSharedPrefix(ancestor, descendant, ancestor.Segments.Count);

    private static bool LooseSharedPrefix(WindowsPath a, WindowsPath b, int count)
    {
        for (var i = 0; i < count; i++)
        {
            if (!LooseSegmentEquals(a.Segments[i], b.Segments[i]))
            {
                return false;
            }
        }

        return true;
    }

    private static bool StrictSegmentEquals(string a, string b)
    {
        if (a.Length != b.Length)
        {
            return false;
        }

        for (var i = 0; i < a.Length; i++)
        {
            // ToUpperAscii changes only a-z, so this is exact match plus ASCII case folding.
            if (ToUpperAscii(a[i]) != ToUpperAscii(b[i]))
            {
                return false;
            }
        }

        return true;
    }

    /// <summary>Internal for tests: true unless the two names are certainly different.</summary>
    internal static bool LooseSegmentEquals(string a, string b)
    {
        // Possibly equal when ANY folding matches; more foldings only add refusals.
        // 1. As NTFS does: upper-case each UTF-16 unit, no normalisation (independent review,
        //    checked against all 973 Windows upcase mappings on .NET Framework 4.8).
        // 2. Caution: the same after NFKC and after NFKD, for spellings that differ only by
        //    composition or compatibility (Vietnamese text arrives composed and decomposed).
        if (UpperKeysMatch(a, b))
        {
            return true;
        }

        try
        {
            return UpperKeysMatch(a.Normalize(NormalizationForm.FormKC), b.Normalize(NormalizationForm.FormKC))
                   || UpperKeysMatch(a.Normalize(NormalizationForm.FormKD), b.Normalize(NormalizationForm.FormKD));
        }
        catch (ArgumentException)
        {
            return true; // cannot prove they differ
        }
    }

    private static bool UpperKeysMatch(string a, string b)
        => string.Equals(UpperPerUnit(a), UpperPerUnit(b), StringComparison.Ordinal);

    private static string UpperPerUnit(string s)
    {
        var chars = s.ToCharArray();
        for (var i = 0; i < chars.Length; i++)
        {
            chars[i] = char.ToUpperInvariant(chars[i]);
        }

        return new string(chars);
    }

    private static bool IsProvableSegment(string segment, out string reason)
    {
        if (segment == "..")
        {
            reason = "'..' segment (may cross a junction or link)";
            return false;
        }

        var last = segment[segment.Length - 1];
        if (last == '.' || last == ' ')
        {
            reason = "segment ends with a dot or space (Windows drops them)";
            return false;
        }

        for (var i = 0; i < segment.Length; i++)
        {
            var c = segment[i];
            if (c < 0x20)
            {
                reason = "control character";
                return false;
            }

            if (c is '<' or '>' or ':' or '"' or '|' or '?' or '*')
            {
                reason = $"invalid character '{c}'";
                return false;
            }

            if (char.IsHighSurrogate(c))
            {
                if (i + 1 >= segment.Length || !char.IsLowSurrogate(segment[i + 1]))
                {
                    reason = "invalid UTF-16 (unpaired surrogate)";
                    return false;
                }

                i++; // skip the low half of a valid pair
            }

            if (char.IsLowSurrogate(c))
            {
                reason = "invalid UTF-16 (unpaired surrogate)";
                return false;
            }

            if (c == '~' && i + 1 < segment.Length && segment[i + 1] >= '0' && segment[i + 1] <= '9')
            {
                reason = "may be an 8.3 short name";
                return false;
            }
        }

        reason = string.Empty;
        return true;
    }

    private static bool IsSeparator(char c) => c is '\\' or '/';

    private static bool IsAsciiLetter(char c) => c is >= 'A' and <= 'Z' or >= 'a' and <= 'z';

    private static char ToUpperAscii(char c) => c is >= 'a' and <= 'z' ? (char)(c - 32) : c;
}
