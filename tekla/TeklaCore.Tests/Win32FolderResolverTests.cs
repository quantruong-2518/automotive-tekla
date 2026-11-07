using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using Xunit;

namespace TeklaHarness.Core.Tests;

/// <summary>
/// Slice S1a on a real Windows file system. Category "Windows": CI runs these on windows-latest
/// only (ubuntu filters them out); they fail rather than pass vacuously anywhere else.
/// Fixtures need no admin rights: directory junctions, hard links and subst drives.
/// Fixtures live under the test output folder, not %TEMP%: a runner's TEMP may contain an
/// 8.3 name (RUNNER~1) that the path guard refuses before identity runs.
/// </summary>
[Trait("Category", "Windows")]
public sealed class Win32FolderResolverTests : IDisposable
{
    private readonly string _root;
    private readonly Win32FolderResolver _os = new();
    private string? _substDrive;

    public Win32FolderResolverTests()
    {
        Assert.True(RuntimeInformation.IsOSPlatform(OSPlatform.Windows), "Windows-only test ran elsewhere; filter Category!=Windows.");
        _root = Path.Combine(AppContext.BaseDirectory, "s1a-fixtures", Guid.NewGuid().ToString("N"));
        Assert.DoesNotContain("~", _root, StringComparison.Ordinal); // precondition for the path guard
        Directory.CreateDirectory(Original);
        Directory.CreateDirectory(Copy);
    }

    private string Models => Path.Combine(_root, "Models");

    private string Original => Path.Combine(Models, "Project");

    private string Copy => Path.Combine(Models, "Project-copy");

    public void Dispose()
    {
        if (_substDrive is not null)
        {
            Run("subst.exe", _substDrive + " /D");
        }

        // Remove links first, never following them, so no target is deleted. The \\?\ prefix lets
        // .NET Framework delete trees deeper than MAX_PATH without the long-path opt-in.
        var root = @"\\?\" + _root;
        foreach (var link in FindReparsePoints(root))
        {
            Directory.Delete(link);
        }

        Directory.Delete(root, recursive: true);
    }

    // ---- resolver

    [Fact]
    public void Same_folder_gives_the_same_identity_and_a_final_path()
    {
        Assert.True(_os.TryResolve(Copy, out var a, out var error), error);
        Assert.True(_os.TryResolve(Copy, out var b, out error), error);
        Assert.Equal(a!.Identity, b!.Identity);
        Assert.Equal(@"\\?\" + Copy, a.FinalPath, ignoreCase: true);
        Assert.NotEqual(0UL, a.Identity.FileIdLow | a.Identity.FileIdHigh);
    }

    [Fact]
    public void Sibling_folders_have_different_identities()
    {
        Assert.True(_os.TryResolve(Copy, out var copy, out var error), error);
        Assert.True(_os.TryResolve(Original, out var original, out error), error);
        Assert.NotEqual(copy!.Identity, original!.Identity);
    }

    [Fact]
    public void Missing_folder_is_reported_not_guessed()
    {
        Assert.False(_os.TryResolve(Path.Combine(_root, "nope"), out var folder, out var error));
        Assert.Null(folder);
        Assert.Contains("CreateFileW failed: Win32 error 2", error, StringComparison.Ordinal);
    }

    [Fact]
    public void Junction_resolves_to_its_target()
    {
        var link = Junction(Path.Combine(_root, "J"), Original);
        Assert.True(_os.TryResolve(link, out var viaLink, out var error), error);
        Assert.True(_os.TryResolve(Original, out var direct, out error), error);
        Assert.Equal(direct!.Identity, viaLink!.Identity);
        Assert.Equal(direct.FinalPath, viaLink.FinalPath);
    }

    [Fact]
    public void Final_paths_longer_than_max_path_are_read_in_full()
    {
        var deep = Path.Combine(Models, string.Join(@"\", Enumerable.Repeat(new string('d', 60), 5)), "Copy");
        Assert.True(deep.Length > 300);
        Directory.CreateDirectory(@"\\?\" + deep);
        Assert.True(_os.TryResolve(deep, out var folder, out var error), error);
        Assert.Equal(@"\\?\" + deep, folder!.FinalPath, ignoreCase: true);
        Assert.True(ModelLocationGuard.Check(deep, deep, Original, _os).Allowed);
    }

    // ---- guard on the real file system

    [Fact]
    public void Guard_allows_a_plain_sibling_copy()
    {
        var result = ModelLocationGuard.Check(Copy, Copy, Original, _os);
        Assert.True(result.Allowed, result.Detail);
    }

    [Fact]
    public void Guard_refuses_a_junction_alias_of_the_original()
    {
        var link = Junction(Path.Combine(_root, "J"), Original);
        Assert.Equal(PathRefusal.WorkingCopyIsOriginal, ModelLocationGuard.Check(link, link, Original, _os).Refusal);
    }

    [Fact]
    public void Guard_refuses_a_junction_that_points_inside_the_original()
    {
        var inside = Path.Combine(Original, "copy");
        Directory.CreateDirectory(inside);
        var link = Junction(Path.Combine(_root, "J"), inside);
        Assert.Equal(PathRefusal.WorkingCopyAndOriginalNested, ModelLocationGuard.Check(link, link, Original, _os).Refusal);
    }

    [Fact]
    public void Guard_refuses_an_original_inside_the_copy()
    {
        var original = Path.Combine(Copy, "old");
        Directory.CreateDirectory(original);
        Assert.Equal(PathRefusal.WorkingCopyAndOriginalNested, ModelLocationGuard.Check(Copy, Copy, original, _os).Refusal);
    }

    [Fact]
    public void Guard_refuses_a_subst_drive_alias_of_the_original()
    {
        var alias = Subst(Models) + @"\Project";
        Assert.Equal(PathRefusal.WorkingCopyIsOriginal, ModelLocationGuard.Check(alias, alias, Original, _os).Refusal);
    }

    [Fact]
    public void Guard_refuses_a_copy_declared_through_a_subst_drive()
    {
        var alias = Subst(Models) + @"\Project-copy";
        Assert.Equal(PathRefusal.WorkingCopyPathIsAlias, ModelLocationGuard.Check(alias, alias, Original, _os).Refusal);
    }

    [Fact]
    public void Guard_refuses_an_original_declared_through_a_subst_drive()
    {
        var alias = Subst(Models) + @"\Project";
        Assert.Equal(PathRefusal.OriginalPathIsAlias, ModelLocationGuard.Check(Copy, Copy, alias, _os).Refusal);
    }

    [Fact]
    public void Guard_refuses_a_junction_inside_the_copy_that_points_into_the_original()
    {
        // What robocopy /E /SJ produces when the original holds a junction to its own subfolder.
        Directory.CreateDirectory(Path.Combine(Original, "attributes"));
        Junction(Path.Combine(Copy, "attributes"), Path.Combine(Original, "attributes"));
        var result = ModelLocationGuard.Check(Copy, Copy, Original, _os);
        Assert.Equal(PathRefusal.LinkInsideFolder, result.Refusal);
        Assert.Contains("attributes", result.Detail, StringComparison.Ordinal);
    }

    [Fact]
    public void Guard_refuses_a_junction_deep_inside_the_original()
    {
        Directory.CreateDirectory(Path.Combine(Original, "a", "b"));
        Junction(Path.Combine(Original, "a", "b", "to-copy"), Copy);
        Assert.Equal(PathRefusal.LinkInsideFolder, ModelLocationGuard.Check(Copy, Copy, Original, _os).Refusal);
    }

    [Fact]
    public void Guard_refuses_a_hard_linked_file_in_the_copy()
    {
        var source = Path.Combine(Original, "Project.db1");
        File.WriteAllText(source, "model");
        Run("cmd.exe", $"/c mklink /H \"{Path.Combine(Copy, "Project.db1")}\" \"{source}\"");
        var result = ModelLocationGuard.Check(Copy, Copy, Original, _os);
        Assert.Equal(PathRefusal.LinkInsideFolder, result.Refusal);
        Assert.Contains("Project.db1", result.Detail, StringComparison.Ordinal);
    }

    [Fact]
    public void Guard_allows_ordinary_files_and_folders_in_both_trees()
    {
        Directory.CreateDirectory(Path.Combine(Copy, "attributes", "deep"));
        File.WriteAllText(Path.Combine(Copy, "attributes", "deep", "x.txt"), "x");
        File.WriteAllText(Path.Combine(Original, "Project.db1"), "model");
        var result = ModelLocationGuard.Check(Copy, Copy, Original, _os);
        Assert.True(result.Allowed, result.Detail);
    }

    // ---- helpers

    private static string Junction(string link, string target)
    {
        Run("cmd.exe", $"/c mklink /J \"{link}\" \"{target}\"");
        return link;
    }

    private string Subst(string target)
    {
        // Another test process (net10.0 and net48 run in parallel locally) may take a letter
        // between the check and the subst call: try the next free one.
        var used = new HashSet<char>(DriveInfo.GetDrives().Select(d => char.ToUpperInvariant(d.Name[0])));
        foreach (var letter in Enumerable.Range('G', 'Z' - 'G' + 1).Select(c => (char)c).Reverse().Where(c => !used.Contains(c)))
        {
            if (TryRun("subst.exe", $"{letter}: \"{target}\"", out _))
            {
                _substDrive = letter + ":";
                return _substDrive;
            }
        }

        Assert.Fail("no free drive letter for subst");
        return string.Empty;
    }

    private static IEnumerable<string> FindReparsePoints(string root)
    {
        var found = new List<string>();
        var pending = new Stack<string>();
        pending.Push(root);
        while (pending.Count > 0)
        {
            foreach (var dir in new DirectoryInfo(pending.Pop()).EnumerateDirectories())
            {
                if ((dir.Attributes & FileAttributes.ReparsePoint) != 0)
                {
                    found.Add(dir.FullName);
                }
                else
                {
                    pending.Push(dir.FullName);
                }
            }
        }

        return found;
    }

    private static void Run(string file, string arguments)
    {
        Assert.True(TryRun(file, arguments, out var failure), failure);
    }

    private static bool TryRun(string file, string arguments, out string failure)
    {
        using var process = Process.Start(new ProcessStartInfo(file, arguments)
        {
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            WorkingDirectory = Path.GetPathRoot(Environment.SystemDirectory)!,
        })!;
        var output = process.StandardOutput.ReadToEnd() + process.StandardError.ReadToEnd();
        process.WaitForExit();
        failure = $"{file} {arguments} -> {process.ExitCode}: {output}";
        return process.ExitCode == 0;
    }
}

public class Win32FolderResolverPortableTests
{
    [Fact]
    public void Native_struct_sizes_match_the_win32_headers()
    {
        Assert.Equal(24, Win32FolderResolver.FileIdInfoSize); // ULONGLONG + FILE_ID_128
        Assert.Equal(52, Win32FolderResolver.ByHandleFileInformationSize); // 13 DWORDs
    }

    [Fact]
    public void Refuses_off_windows_instead_of_guessing()
    {
        if (RuntimeInformation.IsOSPlatform(OSPlatform.Windows))
        {
            return; // the Windows behaviour is covered by Win32FolderResolverTests
        }

        var os = new Win32FolderResolver();
        Assert.False(os.TryResolve(@"C:\x", out var folder, out var error));
        Assert.Null(folder);
        Assert.Equal("folder identity needs Windows", error);
        Assert.False(os.TryFindLink(@"\\?\C:\x", true, out var offender, out error));
        Assert.Null(offender);
        Assert.Equal("folder scan needs Windows", error);
    }
}
