using System;
using Xunit;

namespace TeklaHarness.Core.Tests;

/// <summary>Real ancestors from an OS final path (slice S1a). Anything unexpected refuses.</summary>
public class FinalPathTests
{
    private static string[] Ancestors(string finalPath)
    {
        Assert.True(FinalPath.TryGetAncestors(finalPath, out var ancestors, out var reason), reason);
        Assert.Equal(string.Empty, reason);
        return ancestors.ToArray();
    }

    private static string Refused(string? finalPath)
    {
        Assert.False(FinalPath.TryGetAncestors(finalPath, out var ancestors, out var reason));
        Assert.Empty(ancestors);
        return reason;
    }

    [Theory]
    [InlineData(@"c:\a\b\c", new[] { @"\\?\C:\", @"\\?\C:\a", @"\\?\C:\a\b" })]
    [InlineData(@"C:\a", new[] { @"\\?\C:\" })]
    [InlineData(@"D:/x//y/./z", new[] { @"\\?\D:\", @"\\?\D:\x", @"\\?\D:\x\y" })]
    public void Typed_paths_list_their_parents_as_long_paths(string typed, string[] expected)
    {
        Assert.True(WindowsPath.TryParse(typed, out var path, out var reason), reason);
        Assert.Equal(expected, path!.LongAncestors());
    }

    [Fact]
    public void Drive_paths_list_every_ancestor_from_the_root_down()
    {
        Assert.Equal(new[] { @"\\?\C:\", @"\\?\C:\a", @"\\?\C:\a\b" }, Ancestors(@"\\?\C:\a\b\c"));
        Assert.Equal(new[] { @"\\?\C:\" }, Ancestors(@"\\?\C:\a"));
    }

    [Fact]
    public void Unc_paths_stop_at_the_share_root()
    {
        Assert.Equal(new[] { @"\\?\UNC\srv\sh", @"\\?\UNC\srv\sh\a" }, Ancestors(@"\\?\UNC\srv\sh\a\b"));
        Assert.Equal(new[] { @"\\?\UNC\srv\sh" }, Ancestors(@"\\?\UNC\srv\sh\a"));
        Assert.Equal(new[] { @"\\?\UNC\srv\sh" }, Ancestors(@"\\?\unc\srv\sh\a")); // prefix case is not significant
    }

    [Theory]
    [InlineData(@"\\?\C:\")]
    [InlineData(@"\\?\UNC\srv\sh")]
    public void A_root_has_no_ancestors(string root)
    {
        Assert.Empty(Ancestors(root));
    }

    [Theory]
    [InlineData('A')]
    [InlineData('Z')]
    [InlineData('a')]
    [InlineData('z')]
    public void Accepts_every_drive_letter_boundary(char drive)
    {
        Assert.Equal(new[] { @"\\?\" + drive + @":\" }, Ancestors(@"\\?\" + drive + @":\x"));
    }

    [Theory]
    [InlineData(null, @"no \\?\ prefix")]
    [InlineData("", @"no \\?\ prefix")]
    [InlineData(@"C:\a", @"no \\?\ prefix")]
    [InlineData(@"\\.\C:\a", @"no \\?\ prefix")]
    [InlineData(@"\\?\UNC\srv", "UNC path without server and share")]
    [InlineData(@"\\?\UNC\\sh\a", "UNC path without server and share")]
    [InlineData(@"\\?\UNC\srv\\a", "UNC path without server and share")]
    [InlineData(@"\\?\C:", "neither a drive-letter nor a UNC final path")]
    [InlineData(@"\\?\C", "neither a drive-letter nor a UNC final path")]
    [InlineData(@"\\?\C;\a", "neither a drive-letter nor a UNC final path")]
    [InlineData(@"\\?\C:/a", "neither a drive-letter nor a UNC final path")]
    [InlineData(@"\\?\1:\a", "neither a drive-letter nor a UNC final path")]
    [InlineData(@"\\?\@:\a", "neither a drive-letter nor a UNC final path")]
    [InlineData(@"\\?\[:\a", "neither a drive-letter nor a UNC final path")]
    [InlineData(@"\\?\`:\a", "neither a drive-letter nor a UNC final path")]
    [InlineData(@"\\?\{:\a", "neither a drive-letter nor a UNC final path")]
    [InlineData(@"\\?\Volume{6f0c3a2e-0000-0000-0000-100000000000}\a", "neither a drive-letter nor a UNC final path")]
    [InlineData(@"\\?\C:\a\\b", "unexpected segment ''")]
    [InlineData(@"\\?\C:\a\", "unexpected segment ''")]
    [InlineData(@"\\?\C:\a\.\b", "unexpected segment '.'")]
    [InlineData(@"\\?\C:\a\..\b", "unexpected segment '..'")]
    [InlineData(@"\\?\C:\/a", "unexpected segment '/a'")]
    [InlineData(@"\\?\C:\a/b", "unexpected segment 'a/b'")]
    [InlineData(@"\\?\UNC\srv\sh\..", "unexpected segment '..'")]
    public void Refuses_what_it_cannot_walk(string? finalPath, string reason)
    {
        Assert.Equal(reason, Refused(finalPath));
    }
}
