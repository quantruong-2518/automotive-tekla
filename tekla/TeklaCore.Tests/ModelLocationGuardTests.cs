using System;
using System.Collections.Generic;
using Xunit;

namespace TeklaHarness.Core.Tests;

/// <summary>
/// Contract safety rule 1, both layers (ADR-0009 Amendment): the path-text guard, then file identity
/// (volume serial + file ID) of each folder and of every real ancestor (from the OS final path).
/// The fake resolver plays the operating system, including aliases the text guard cannot see.
/// </summary>
public class ModelLocationGuardTests
{
    private const string Original = @"C:\Models\Project";
    private const string Copy = @"C:\Models\Project-copy";

    private static readonly FileIdentity Root = new(1, 0, 5);
    private static readonly FileIdentity Models = new(1, 0, 10);
    private static readonly FileIdentity OriginalId = new(1, 0, 20);
    private static readonly FileIdentity CopyId = new(1, 0, 30);

    /// <summary>A plain machine: C:\Models holds the original and the copy.</summary>
    private static FakeResolver PlainMachine() => new FakeResolver()
        .Add(@"\\?\C:\", Root, @"\\?\C:\")
        .Add(@"\\?\C:\Models", Models, @"\\?\C:\Models")
        .Add(Original, OriginalId, @"\\?\C:\Models\Project")
        .Add(Copy, CopyId, @"\\?\C:\Models\Project-copy");

    private static ModelPathCheck Check(FakeResolver os, string open = Copy, string copy = Copy, string original = Original)
        => ModelLocationGuard.Check(open, copy, original, os);

    [Fact]
    public void Allows_the_working_copy_on_a_plain_machine()
    {
        var result = Check(PlainMachine());
        Assert.True(result.Allowed, result.Detail);
        Assert.Equal(ExitCode.Ok, result.ExitCode);
    }

    [Fact]
    public void Text_refusals_come_first_and_the_os_is_not_asked()
    {
        var os = PlainMachine();
        var result = Check(os, open: Original);
        Assert.Equal(PathRefusal.OpenIsOriginal, result.Refusal);
        Assert.Empty(os.Asked);
    }

    [Fact]
    public void Asks_the_os_with_canonical_text()
    {
        var os = PlainMachine();
        Check(os, open: @"c:/models/project-copy/", copy: @"C:\Models\.\Project-copy");
        Assert.Contains(@"C:\models\project-copy", os.Asked, StringComparer.Ordinal); // drive upper-cased, rest as typed
    }

    // ---- aliases: what the text guard cannot see

    [Fact]
    public void Refuses_a_subst_drive_that_is_the_original()
    {
        // subst X: C:\Models — X:\Project is the original folder itself.
        var os = PlainMachine().Add(@"X:\Project", OriginalId, @"\\?\C:\Models\Project");
        var result = Check(os, open: @"X:\Project", copy: @"X:\Project");
        Assert.Equal(PathRefusal.WorkingCopyIsOriginal, result.Refusal);
        Assert.Equal(ExitCode.RefusedBySafetyRule, result.ExitCode);
    }

    [Fact]
    public void Refuses_a_junction_that_points_into_the_original()
    {
        // C:\J is a junction to C:\Models\Project\copy: text parents (C:\) hide the nesting,
        // the final path shows it.
        var inside = new FileIdentity(1, 0, 40);
        var os = PlainMachine()
            .Add(@"C:\J", inside, @"\\?\C:\Models\Project\copy")
            .Add(@"\\?\C:\Models\Project", OriginalId, @"\\?\C:\Models\Project");
        var result = Check(os, open: @"C:\J", copy: @"C:\J");
        Assert.Equal(PathRefusal.WorkingCopyAndOriginalNested, result.Refusal);
    }

    [Fact]
    public void Refuses_an_original_that_lives_inside_the_copy_through_an_alias()
    {
        // The declared original is reached through a junction whose real folder is inside the copy.
        var os = PlainMachine()
            .Add(@"C:\Orig", new FileIdentity(1, 0, 50), @"\\?\C:\Models\Project-copy\old")
            .Add(@"\\?\C:\Models\Project-copy", CopyId, @"\\?\C:\Models\Project-copy");
        var result = Check(os, original: @"C:\Orig");
        Assert.Equal(PathRefusal.WorkingCopyAndOriginalNested, result.Refusal);
    }

    [Fact]
    public void Refuses_two_mapped_drives_on_the_same_share()
    {
        // Y: and Z: both map \\server\models; final paths may even name the server differently.
        var shared = new FileIdentity(7, 0, 99);
        var os = new FakeResolver()
            .Add(@"Y:\Project", shared, @"\\?\UNC\server\models\Project")
            .Add(@"Z:\Project", shared, @"\\?\UNC\10.0.0.5\models\Project")
            .Add(@"\\?\UNC\server\models", new FileIdentity(7, 0, 1), @"\\?\UNC\server\models")
            .Add(@"\\?\UNC\10.0.0.5\models", new FileIdentity(7, 0, 1), @"\\?\UNC\10.0.0.5\models");
        var result = ModelLocationGuard.Check(@"Y:\Project", @"Y:\Project", @"Z:\Project", os);
        Assert.Equal(PathRefusal.WorkingCopyIsOriginal, result.Refusal);
    }

    [Theory]
    [InlineData(@"\\?\UNC\server\models\Copy", @"\\?\C:\Models\Project")] // copy on a share
    [InlineData(@"\\?\C:\Models\Project-copy", @"\\?\UNC\server\models\Project")] // original on a share
    public void Refuses_remote_folders_because_different_cannot_be_proven(string copyFinal, string originalFinal)
    {
        // SMB: the client cannot see above the share root nor server-side junctions, and file
        // IDs through the redirector are undocumented (docs/research/windows-file-identity.md).
        var os = new FakeResolver()
            .Add(@"Y:\Copy", new FileIdentity(7, 0, 2), copyFinal)
            .Add(Original, OriginalId, originalFinal);
        var result = ModelLocationGuard.Check(@"Y:\Copy", @"Y:\Copy", Original, os);
        Assert.Equal(PathRefusal.IdentityUnavailable, result.Refusal);
        Assert.Contains("remote", result.Detail, StringComparison.Ordinal);
    }

    [Theory]
    [InlineData(0UL, 0UL)] // file system reports no file ID
    [InlineData(ulong.MaxValue, ulong.MaxValue)] // file ID cannot be established
    public void Refuses_placeholder_file_ids(ulong high, ulong low)
    {
        var os = PlainMachine().Add(Original, new FileIdentity(1, high, low), @"\\?\C:\Models\Project");
        var result = Check(os);
        Assert.Equal(PathRefusal.IdentityUnavailable, result.Refusal);
        Assert.Contains("no usable file ID", result.Detail, StringComparison.Ordinal);
    }

    [Theory]
    [InlineData(0UL, 1UL)]
    [InlineData(1UL, 0UL)]
    [InlineData(ulong.MaxValue, 0UL)]
    [InlineData(0UL, ulong.MaxValue)]
    public void Accepts_file_ids_that_are_only_partly_zero_or_ones(ulong high, ulong low)
    {
        var os = PlainMachine().Add(Original, new FileIdentity(1, high, low), @"\\?\C:\Models\Project");
        Assert.True(Check(os).Allowed);
    }

    [Fact]
    public void Refuses_when_an_ancestor_of_the_copy_is_the_original_by_identity()
    {
        // The copy's real parent folder is an alias of the original (e.g. a junction above it).
        var os = PlainMachine()
            .Add(@"C:\Work\Copy", CopyId, @"\\?\C:\Work\Copy")
            .Add(@"\\?\C:\Work", OriginalId, @"\\?\C:\Work");
        var result = Check(os, open: @"C:\Work\Copy", copy: @"C:\Work\Copy");
        Assert.Equal(PathRefusal.WorkingCopyAndOriginalNested, result.Refusal);
    }

    [Fact]
    public void Refuses_when_an_ancestor_of_the_original_is_the_copy_by_identity()
    {
        var os = PlainMachine()
            .Add(@"D:\Archive\Project", OriginalId, @"\\?\D:\Archive\Project")
            .Add(@"\\?\D:\", new FileIdentity(2, 0, 5), @"\\?\D:\")
            .Add(@"\\?\D:\Archive", CopyId, @"\\?\D:\Archive");
        var result = Check(os, original: @"D:\Archive\Project");
        Assert.Equal(PathRefusal.WorkingCopyAndOriginalNested, result.Refusal);
    }

    [Fact]
    public void Also_walks_the_typed_parents_not_only_the_final_path()
    {
        // Defence in depth (research step 5): if the final path ever misses an alias, the typed
        // parent C:\J (an alias of the original) still reveals the nesting.
        var os = PlainMachine()
            .Add(@"C:\J\copy", CopyId, @"\\?\C:\Elsewhere\copy")
            .Add(@"\\?\C:\Elsewhere", new FileIdentity(1, 0, 60), @"\\?\C:\Elsewhere")
            .Add(@"\\?\C:\J", OriginalId, @"\\?\C:\Models\Project");
        var result = Check(os, open: @"C:\J\copy", copy: @"C:\J\copy");
        Assert.Equal(PathRefusal.WorkingCopyAndOriginalNested, result.Refusal);
    }

    [Fact]
    public void Asks_each_ancestor_once()
    {
        var os = PlainMachine();
        Check(os);
        Assert.Single(os.Asked, p => p == @"\\?\C:\Models");
    }

    // ---- links inside either folder (independent review: robocopy /SJ keeps a junction that
    //      still points into the original; a write through it lands in the original)

    [Fact]
    public void Scans_the_copy_for_links_and_hard_links_and_the_original_for_links()
    {
        var os = PlainMachine();
        Assert.True(Check(os).Allowed);
        Assert.Contains((@"\\?\C:\Models\Project-copy", true), os.Scanned);
        Assert.Contains((@"\\?\C:\Models\Project", false), os.Scanned);
    }

    [Fact]
    public void Refuses_a_link_inside_the_copy()
    {
        var os = PlainMachine().LinkInside(@"\\?\C:\Models\Project-copy", @"\\?\C:\Models\Project-copy\attributes");
        var result = Check(os);
        Assert.Equal(PathRefusal.LinkInsideFolder, result.Refusal);
        Assert.Equal(ExitCode.RefusedBySafetyRule, result.ExitCode);
        Assert.Contains(@"The working copy contains a link or hard-linked file '\\?\C:\Models\Project-copy\attributes'", result.Detail, StringComparison.Ordinal);
    }

    [Fact]
    public void Refuses_a_link_inside_the_original()
    {
        var os = PlainMachine().LinkInside(@"\\?\C:\Models\Project", @"\\?\C:\Models\Project\to-copy");
        var result = Check(os);
        Assert.Equal(PathRefusal.LinkInsideFolder, result.Refusal);
        Assert.Contains("The original contains a link", result.Detail, StringComparison.Ordinal);
    }

    [Fact]
    public void Refuses_when_a_subtree_cannot_be_scanned()
    {
        var os = PlainMachine().ScanFails(@"\\?\C:\Models\Project", "access denied");
        var result = Check(os);
        Assert.Equal(PathRefusal.IdentityUnavailable, result.Refusal);
        Assert.Contains("access denied", result.Detail, StringComparison.Ordinal);
    }

    [Fact]
    public void Refuses_a_working_copy_reached_through_an_alias()
    {
        // subst/mapped letters are per logon session: Tekla may see another folder behind the
        // same text. The copy's typed path must be its real path (independent review).
        var os = PlainMachine()
            .Add(@"W:\Copy", CopyId, @"\\?\C:\Models\Project-copy")
            .Add(@"\\?\W:\", new FileIdentity(1, 0, 70), @"\\?\C:\Models");
        var result = Check(os, open: @"W:\Copy", copy: @"W:\Copy");
        Assert.Equal(PathRefusal.WorkingCopyPathIsAlias, result.Refusal);
        Assert.Equal(ExitCode.RefusedBySafetyRule, result.ExitCode);
        Assert.Contains(@"is reached through an alias (real path '\\?\C:\Models\Project-copy')", result.Detail, StringComparison.Ordinal);
    }

    [Fact]
    public void Refuses_an_original_declared_through_another_drive_letter()
    {
        // subst/mapped letters are per logon session: X: may name another folder for the CLI
        // than for the engineer who declared it (second independent review).
        var os = PlainMachine()
            .Add(@"X:\Project", OriginalId, @"\\?\C:\Models\Project")
            .Add(@"\\?\X:\", new FileIdentity(1, 0, 80), @"\\?\C:\Models");
        var result = Check(os, original: @"X:\Project");
        Assert.Equal(PathRefusal.OriginalPathIsAlias, result.Refusal);
        Assert.Equal(ExitCode.RefusedBySafetyRule, result.ExitCode);
        Assert.Contains(@"Original 'X:\Project' is reached through drive 'C:'", result.Detail, StringComparison.Ordinal);
    }

    [Fact]
    public void Accepts_an_original_reached_through_a_junction_on_its_own_drive()
    {
        // Junctions are global, not per session: same letter, other folders is fine.
        var os = PlainMachine()
            .Add(@"C:\Link\Project", OriginalId, @"\\?\C:\Models\Project")
            .Add(@"\\?\C:\Link", new FileIdentity(1, 0, 81), @"\\?\C:\Models");
        var result = Check(os, original: @"c:\Link\Project");
        Assert.True(result.Allowed, result.Detail);
    }

    [Fact]
    public void Refuses_when_the_copy_cannot_be_scanned()
    {
        var os = PlainMachine().ScanFails(@"\\?\C:\Models\Project-copy", "sharing violation");
        var result = Check(os);
        Assert.Equal(PathRefusal.IdentityUnavailable, result.Refusal);
        Assert.Contains("The working copy", result.Detail, StringComparison.Ordinal);
    }

    [Fact]
    public void Accepts_a_working_copy_whose_real_path_differs_only_in_case()
    {
        var os = PlainMachine()
            .Add(@"C:\models\project-copy", CopyId, @"\\?\C:\Models\Project-copy")
            .Add(@"\\?\C:\models", Models, @"\\?\C:\Models"); // the real OS ignores case here
        var result = Check(os, open: @"c:\models\project-copy", copy: @"C:\models\project-copy");
        Assert.True(result.Allowed, result.Detail);
    }

    // ---- disagreement between text and identity

    [Fact]
    public void Refuses_when_the_open_and_copy_identities_differ()
    {
        // Same text, different folder: the folder was replaced between the two lookups.
        var os = PlainMachine().AddSequence(Copy, CopyId, new FileIdentity(1, 0, 31));
        var result = Check(os);
        Assert.Equal(PathRefusal.IdentityConflict, result.Refusal);
        Assert.Equal(ExitCode.RefusedBySafetyRule, result.ExitCode);
    }

    [Fact]
    public void Identity_differs_when_only_the_volume_differs()
    {
        var os = PlainMachine().AddSequence(Copy, CopyId, new FileIdentity(2, 0, 30));
        Assert.Equal(PathRefusal.IdentityConflict, Check(os).Refusal);
    }

    [Fact]
    public void Identity_differs_when_only_the_high_half_of_the_file_id_differs()
    {
        // ReFS needs the full 128-bit ID.
        var os = PlainMachine().AddSequence(Copy, CopyId, new FileIdentity(1, 1, 30));
        Assert.Equal(PathRefusal.IdentityConflict, Check(os).Refusal);
    }

    // ---- anything the OS cannot answer refuses

    [Theory]
    [InlineData(Copy)]
    [InlineData(Original)]
    [InlineData(@"\\?\C:\Models")]
    [InlineData(@"\\?\C:\")]
    public void Refuses_when_any_needed_identity_cannot_be_read(string missing)
    {
        var os = PlainMachine().Fail(missing, "access denied");
        var result = Check(os);
        Assert.Equal(PathRefusal.IdentityUnavailable, result.Refusal);
        Assert.Equal(ExitCode.RefusedBySafetyRule, result.ExitCode);
        Assert.Contains("access denied", result.Detail, StringComparison.Ordinal);
    }

    [Fact]
    public void Refuses_when_only_an_ancestor_of_the_original_cannot_be_read()
    {
        // The copy's walk is clean; the original's walk fails half-way. Must not be masked.
        var os = PlainMachine()
            .Add(@"D:\Archive\Project", OriginalId, @"\\?\D:\Archive\Project")
            .Add(@"\\?\D:\", new FileIdentity(2, 0, 5), @"\\?\D:\")
            .Fail(@"\\?\D:\Archive", "access denied");
        var result = Check(os, original: @"D:\Archive\Project");
        Assert.Equal(PathRefusal.IdentityUnavailable, result.Refusal);
    }

    [Fact]
    public void Refuses_when_only_the_original_final_path_cannot_be_walked()
    {
        var os = PlainMachine().Add(Original, OriginalId, @"\\?\Volume{6f0c3a2e-0000-0000-0000-100000000000}\Project");
        var result = Check(os);
        Assert.Equal(PathRefusal.IdentityUnavailable, result.Refusal);
        Assert.Contains("cannot be walked", result.Detail, StringComparison.Ordinal);
    }

    [Fact]
    public void Refuses_a_resolver_that_claims_success_without_an_answer()
    {
        var os = PlainMachine().SucceedWithNull(Original);
        Assert.Equal(PathRefusal.IdentityUnavailable, Check(os).Refusal);
    }

    [Fact]
    public void Trusts_a_resolver_failure_even_when_it_left_an_answer_behind()
    {
        var os = PlainMachine().FailWithAnswer(Original, "stale handle");
        var result = Check(os);
        Assert.Equal(PathRefusal.IdentityUnavailable, result.Refusal);
        Assert.Contains("stale handle", result.Detail, StringComparison.Ordinal);
    }

    [Theory]
    [InlineData(Copy, "open model")]
    [InlineData(Original, "original")]
    [InlineData(@"\\?\C:\Models", "ancestor folder")]
    public void Unavailable_detail_names_the_role_and_path(string missing, string role)
    {
        var detail = Check(PlainMachine().Fail(missing, "denied")).Detail;
        Assert.Contains($"Identity of the {role} '{missing}' cannot be read: denied", detail, StringComparison.Ordinal);
    }

    [Fact]
    public void Unavailable_detail_names_the_working_copy_role()
    {
        // Open and copy share one path; the second lookup (the copy) fails.
        var failing = new FakeResolver()
            .Add(Copy, CopyId, @"\\?\C:\Models\Project-copy")
            .FailAfterFirst(Copy, "denied");
        Assert.Contains("Identity of the working copy", Check(failing).Detail, StringComparison.Ordinal);
    }

    [Fact]
    public void Refusal_details_explain_each_outcome()
    {
        var subst = PlainMachine().Add(@"X:\Project", OriginalId, @"\\?\C:\Models\Project");
        Assert.Contains("is the original", Check(subst, open: @"X:\Project", copy: @"X:\Project").Detail, StringComparison.Ordinal);

        var swapped = PlainMachine().AddSequence(Copy, CopyId, new FileIdentity(1, 0, 31));
        Assert.Contains("named two different folders", Check(swapped).Detail, StringComparison.Ordinal);

        var junction = PlainMachine()
            .Add(@"C:\Work\Copy", CopyId, @"\\?\C:\Work\Copy")
            .Add(@"\\?\C:\Work", OriginalId, @"\\?\C:\Work");
        Assert.Contains(@"are nested (real folder '\\?\C:\Work')", Check(junction, open: @"C:\Work\Copy", copy: @"C:\Work\Copy").Detail, StringComparison.Ordinal);

        Assert.Contains("is the working copy", Check(PlainMachine()).Detail, StringComparison.Ordinal);
        Assert.Contains("identity check failed: InvalidOperationException: boom", Check(PlainMachine().Throw(Original)).Detail, StringComparison.OrdinalIgnoreCase);
    }

    [Theory]
    [InlineData(@"C:\Models\Project-copy")] // no \\?\ prefix
    [InlineData(@"\\?\Volume{6f0c3a2e-0000-0000-0000-100000000000}\Copy")] // no drive letter
    [InlineData(@"\\?\UNC\server")] // no share
    [InlineData(@"\\?\C:")] // no root separator
    [InlineData(@"\\?\C:\Models\..\Project-copy")] // the OS never returns this; refuse if it does
    [InlineData("")]
    public void Refuses_a_final_path_it_cannot_walk(string finalPath)
    {
        var os = PlainMachine().Add(Copy, CopyId, finalPath);
        Assert.Equal(PathRefusal.IdentityUnavailable, Check(os).Refusal);
    }

    [Fact]
    public void Does_not_ask_for_the_folder_itself_as_its_own_ancestor()
    {
        var os = PlainMachine();
        Check(os);
        Assert.DoesNotContain(@"\\?\C:\Models\Project-copy", os.Asked, StringComparer.Ordinal);
    }

    [Fact]
    public void A_resolver_exception_refuses_instead_of_escaping()
    {
        var os = PlainMachine().Throw(Original);
        var ex = Record.Exception(() => Check(os));
        Assert.Null(ex);
        Assert.Equal(PathRefusal.IdentityUnavailable, Check(os).Refusal);
    }

    [Fact]
    public void Null_resolver_is_a_programming_error()
    {
        Assert.Throws<ArgumentNullException>(() => ModelLocationGuard.Check(Copy, Copy, Original, null!));
    }

    // ---- FileIdentity value semantics

    [Fact]
    public void FileIdentity_equality_uses_all_three_parts()
    {
        var a = new FileIdentity(1, 2, 3);
        Assert.Equal(a, new FileIdentity(1, 2, 3));
        Assert.True(a == new FileIdentity(1, 2, 3));
        Assert.False(a != new FileIdentity(1, 2, 3));
        Assert.NotEqual(a, new FileIdentity(9, 2, 3));
        Assert.NotEqual(a, new FileIdentity(1, 9, 3));
        Assert.NotEqual(a, new FileIdentity(1, 2, 9));
        Assert.True(a != new FileIdentity(1, 2, 9));
        Assert.False(a.Equals((object)"x"));
        Assert.True(a.Equals((object)new FileIdentity(1, 2, 3)));
        Assert.Equal(a.GetHashCode(), new FileIdentity(1, 2, 3).GetHashCode());
        Assert.Equal("0000000000000001:0000000000000002:0000000000000003", a.ToString());
    }

    /// <summary>Plays the OS: answers by exact path text, records every question.</summary>
    private sealed class FakeResolver : IFolderResolver
    {
        private readonly Dictionary<string, Queue<ResolvedFolder>> _answers = new(StringComparer.Ordinal);
        private readonly Dictionary<string, string> _failures = new(StringComparer.Ordinal);
        private readonly HashSet<string> _throws = new(StringComparer.Ordinal);

        public List<string> Asked { get; } = new();

        public List<(string Folder, bool HardLinks)> Scanned { get; } = new();

        private readonly Dictionary<string, string> _linksInside = new(StringComparer.Ordinal);
        private readonly Dictionary<string, string> _scanFailures = new(StringComparer.Ordinal);

        public FakeResolver LinkInside(string folder, string offender)
        {
            _linksInside[folder] = offender;
            return this;
        }

        public FakeResolver ScanFails(string folder, string error)
        {
            _scanFailures[folder] = error;
            return this;
        }

        public bool TryFindLink(string folder, bool includeHardLinks, out string? offender, out string error)
        {
            Scanned.Add((folder, includeHardLinks));
            if (_scanFailures.TryGetValue(folder, out var failure))
            {
                offender = null;
                error = failure;
                return false;
            }

            _linksInside.TryGetValue(folder, out offender);
            error = string.Empty;
            return true;
        }

        public FakeResolver Add(string path, FileIdentity id, string finalPath)
        {
            _answers[path] = new Queue<ResolvedFolder>(new[] { new ResolvedFolder(id, finalPath) });
            return this;
        }

        public FakeResolver AddSequence(string path, FileIdentity first, FileIdentity second)
        {
            var final = _answers[path].Peek().FinalPath;
            _answers[path] = new Queue<ResolvedFolder>(new[] { new ResolvedFolder(first, final), new ResolvedFolder(second, final) });
            return this;
        }

        public FakeResolver Fail(string path, string error)
        {
            _failures[path] = error;
            return this;
        }

        public FakeResolver Throw(string path)
        {
            _throws.Add(path);
            return this;
        }

        public FakeResolver SucceedWithNull(string path)
        {
            _nullAnswers.Add(path);
            return this;
        }

        public FakeResolver FailAfterFirst(string path, string error)
        {
            _failAfterFirst[path] = error;
            return this;
        }

        public FakeResolver FailWithAnswer(string path, string error)
        {
            _failWithAnswer[path] = error;
            return this;
        }

        private readonly HashSet<string> _nullAnswers = new(StringComparer.Ordinal);
        private readonly Dictionary<string, string> _failAfterFirst = new(StringComparer.Ordinal);
        private readonly Dictionary<string, string> _failWithAnswer = new(StringComparer.Ordinal);

        public bool TryResolve(string path, out ResolvedFolder? folder, out string error)
        {
            var seenBefore = Asked.Contains(path);
            Asked.Add(path);
            if (_throws.Contains(path))
            {
                throw new InvalidOperationException("boom");
            }

            if (_nullAnswers.Contains(path))
            {
                folder = null;
                error = string.Empty;
                return true;
            }

            if (_failWithAnswer.TryGetValue(path, out var stale))
            {
                folder = _answers[path].Peek();
                error = stale;
                return false;
            }

            if (seenBefore && _failAfterFirst.TryGetValue(path, out var later))
            {
                folder = null;
                error = later;
                return false;
            }

            if (_failures.TryGetValue(path, out var failure))
            {
                folder = null;
                error = failure;
                return false;
            }

            if (_answers.TryGetValue(path, out var queue))
            {
                folder = queue.Count > 1 ? queue.Dequeue() : queue.Peek();
                error = string.Empty;
                return true;
            }

            folder = null;
            error = "not found";
            return false;
        }
    }
}
