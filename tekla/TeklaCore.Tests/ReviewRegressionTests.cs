using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Threading;
using Xunit;
using static TeklaHarness.Core.Tests.PlanFixtures;

namespace TeklaHarness.Core.Tests;

/// <summary>
/// Counterexamples from the independent review of slice S1c (R1–R16, Io1, Lock1), inverted to the
/// required behaviour, and the fixes they led to (C1, M1, M2, m1–m6).
/// </summary>
public sealed class ReviewRegressionTests : IDisposable
{
    private readonly string _dir;

    public ReviewRegressionTests()
    {
        _dir = Path.Combine(Path.GetTempPath(), "teklacore-review-" + Guid.NewGuid().ToString("N", CultureInfo.InvariantCulture));
        Directory.CreateDirectory(_dir);
    }

    public void Dispose() => Directory.Delete(_dir, recursive: true);

    private static void AssertUntrusted(ResumePlan plan)
    {
        Assert.Equal(PlanRefusal.LookupUntrusted, plan.Refusal);
        Assert.Equal(ExitCode.EnvironmentError, plan.ExitCode);
        Assert.Empty(plan.Members);
        Assert.False(plan.Executable);
    }

    // ---- C1: a lookup hit and its tag must agree, in both directions

    [Fact]
    public void R1_found_by_the_spec_id_lookup_but_the_tag_reads_absent_refuses()
    {
        var o = Obj(A, G(1)).With(b => b.FoundBy = SnapshotLookup.SpecId | SnapshotLookup.Lot | SnapshotLookup.RunId);
        AssertUntrusted(Plan(Abc, null, Snap(null, o)));
    }

    [Fact]
    public void R2_found_by_the_lot_and_run_lookups_but_tags_read_absent_refuses()
    {
        var j = Journal(Inv(JO(B, G(2), ObjectState.Tagged)));
        var o = Obj(A, G(1)).With(b => b.FoundBy = SnapshotLookup.Lot | SnapshotLookup.RunId);
        AssertUntrusted(Plan(Abc, j, Snap(j, o, Tagged(B, G(2)))));
    }

    [Fact]
    public void R3_journal_object_not_flagged_as_found_by_the_journal_lookup_refuses()
    {
        var j = Journal(Inv(JO(A, G(1), ObjectState.Tagged)));
        var o = Tagged(A, G(1)).With(b => b.FoundBy = SnapshotLookup.Lot | SnapshotLookup.RunId | SnapshotLookup.SpecId);
        AssertUntrusted(Plan(Abc, j, Snap(j, o)));
    }

    [Theory]
    [InlineData(SnapshotLookup.Lot, "2", Run, "L1-C-A1")]
    [InlineData(SnapshotLookup.RunId, LotText, "R-OTHER", "L1-C-A1")]
    [InlineData(SnapshotLookup.SpecId, LotText, Run, "L1-GONE")]
    [InlineData(SnapshotLookup.SpecId, LotText, Run, null)]
    public void Lookup_flag_without_the_matching_tag_value_refuses(SnapshotLookup extra, string? lot, string? run, string? specId)
    {
        var j = Journal();
        var o = Obj(A, G(1)).Tags(lot, run, specId);
        var built = o.Build(false);
        o.FoundBy = built.FoundBy | extra;
        AssertUntrusted(Plan(Abc, j, Snap(j, o)));
    }

    [Fact]
    public void Object_no_lookup_returned_refuses()
    {
        AssertUntrusted(Plan(Abc, Journal(), Snap(Journal(), Obj(A, G(1)))));
        AssertUntrusted(Plan(Abc, Journal(), Snap(Journal(), Obj(A, G(1)).Tags("2", "R-OLD", null))));
    }

    [Fact]
    public void Journal_lookup_flag_on_an_object_outside_the_journal_refuses()
    {
        var j = Journal();
        var o = Tagged(A, G(1)).With(b => b.FoundBy = SnapshotLookup.Lot | SnapshotLookup.RunId | SnapshotLookup.SpecId | SnapshotLookup.JournalGuid);
        AssertUntrusted(Plan(Abc, j, Snap(j, o)));
    }

    [Fact]
    public void Journal_flag_details_name_both_sides()
    {
        var j = Journal();
        var o = Tagged(A, G(1)).With(b => b.FoundBy = SnapshotLookup.Lot | SnapshotLookup.RunId | SnapshotLookup.SpecId | SnapshotLookup.JournalGuid);
        Assert.Equal(
            "Object 00000000-0000-0000-0000-000000000001: the journal GUID lookup flag says yes but the journal says no: the snapshot cannot be trusted.",
            Plan(Abc, j, Snap(j, o)).Detail);
    }

    [Fact]
    public void Untagged_journal_object_found_only_by_the_journal_lookup_is_trusted()
    {
        var j = Journal(Inv(JO(A, G(1), ObjectState.Inserted)));
        var plan = Plan(Abc, j, Snap(j, Obj(A, G(1))));
        Assert.True(plan.Executable, plan.Detail);
        Assert.Equal(MemberAction.Retag, plan.Members[0].Action);
    }

    [Fact]
    public void Untrusted_detail_names_the_object_and_the_disagreement()
    {
        var o = Obj(A, G(1)).With(b => b.FoundBy = SnapshotLookup.Lot);
        var plan = Plan(Abc, Journal(), Snap(Journal(), o));
        Assert.Equal(
            "Object 00000000-0000-0000-0000-000000000001: the LOT lookup returned it, but its LOT tag is (absent): the filter cannot be trusted.",
            plan.Detail);
    }

    // ---- R4–R14: behaviour the review confirmed (kept as regression tests)

    [Fact]
    public void R4_appended_inserting_entry_stays_unresolved_in_the_planner()
    {
        var j = Journal(Inv(JO(A, null, ObjectState.Inserting), JO(A, G(1), ObjectState.Inserted), JO(A, G(1), ObjectState.Tagged)));
        var plan = Plan(Abc, j, Snap(j, Tagged(A, G(1))));
        Assert.Equal(MemberAction.Conflict, plan.Members[0].Action);
        Assert.False(plan.Executable);
    }

    [Fact]
    public void R5_journal_object_of_the_wrong_kind_is_a_conflict()
    {
        var j = Journal(Inv(JO(A, G(1), ObjectState.Inserted)));
        Assert.Equal(MemberAction.Conflict, Plan(Abc, j, Snap(j, Obj(A, G(1)).With(b => b.Kind = "beam"))).Members[0].Action);
    }

    [Fact]
    public void R6_lower_case_run_tag_is_another_run()
    {
        var plan = Plan(Abc, null, Snap(null, Obj(A, G(1)).Tags(LotText, "r20261108-01", A.SpecId)));
        Assert.False(plan.Refused, plan.Detail);
        Assert.Equal(MemberAction.Conflict, plan.Members[0].Action);
    }

    [Fact]
    public void R7_spec_tag_with_a_trailing_space_blocks_the_whole_plan()
    {
        var o = Obj(A, G(1)).Tags(LotText, Run, A.SpecId + " ");
        Assert.True(Plan(Abc, null, Snap(null, o)).Refused);
        var j = Journal(Inv(JO(B, G(2), ObjectState.Tagged)));
        var plan = Plan(Abc, j, Snap(j, o, Tagged(B, G(2))));
        Assert.False(plan.Refused, plan.Detail);
        Assert.False(plan.Executable);
        Assert.Equal(ExitCode.ValidationFailure, plan.ExitCode);
        Assert.Equal(MemberAction.Blocked, plan.Members[0].Action);
        Assert.Equal(MemberAction.Create, plan.Members[0].IntendedAction);
        Assert.DoesNotContain(plan.Members, p => p.Action is MemberAction.Create or MemberAction.Skip or MemberAction.Retag);
    }

    [Theory]
    [InlineData(-90.0, 270.0, true)]
    [InlineData(0.0, 359.995, true)]
    [InlineData(0.0, 720.005, true)]
    [InlineData(0.0, 180.0, false)]
    [InlineData(0.0, double.NaN, false)]
    [InlineData(0.0, double.PositiveInfinity, false)]
    public void R8_rotation(double spec, double model, bool skip)
    {
        var m = Member("L1-C-X", "column", new Point3(0, 0, 0), new Point3(0, 0, 1), rotation: spec);
        var j = Journal(Inv(JO(m, G(1), ObjectState.Tagged)));
        var plan = Plan(Spec(m), j, SnapFor(Spec(m), j, Tagged(m, G(1)).With(b => b.Rotation = model)));
        Assert.Equal(skip ? MemberAction.Skip : MemberAction.Conflict, plan.Members[0].Action);
    }

    [Fact]
    public void R9_journal_object_of_A_tagged_B_next_to_B_blocks_both()
    {
        var j = Journal(Inv(JO(A, G(1), ObjectState.Tagged)));
        var plan = Plan(Abc, j, Snap(j, Tagged(B, G(1)), Tagged(B, G(2))));
        Assert.Equal(MemberAction.Conflict, plan.Members[0].Action);
        Assert.Equal(MemberAction.Conflict, plan.Members[1].Action);
    }

    [Fact]
    public void R10_partial_tags_outside_the_journal_are_a_conflict()
    {
        var j = Journal(Inv(JO(B, G(2), ObjectState.Tagged)));
        var plan = Plan(Abc, j, Snap(j, Obj(A, G(1)).Tags(LotText, null, A.SpecId), Tagged(B, G(2))));
        Assert.Equal(MemberAction.Conflict, plan.Members[0].Action);
    }

    [Fact]
    public void R11_lookup_error_for_a_guid_outside_the_journal_is_ignored()
    {
        var j = Journal(Inv(JO(B, G(2), ObjectState.Tagged)));
        var snap = Snap(j, new[] { Tagged(B, G(2)) }, new Dictionary<Guid, GuidPresence> { [G(9)] = GuidPresence.Error });
        Assert.False(Plan(Abc, j, snap).Refused);
    }

    [Fact]
    public void R12_journal_object_tagged_with_another_run_is_a_conflict()
    {
        var j = Journal(Inv(JO(A, G(1), ObjectState.Tagged)));
        Assert.Equal(MemberAction.Conflict, Plan(Abc, j, Snap(j, Obj(A, G(1)).Tags(LotText, "OTHER", null))).Members[0].Action);
    }

    [Fact]
    public void R13_unreadable_lot_without_a_journal_refuses_as_unreadable()
    {
        var o = Obj(A, G(1)).With(b => (b.Lot, b.RunTag, b.SpecTag) = (TagReading.Unreadable, TagReading.Of(Run), TagReading.Of(A.SpecId)));
        Assert.Equal(PlanRefusal.UnreadableTag, Plan(Abc, null, Snap(null, o)).Refusal);
    }

    [Fact]
    public void R14_unparsable_model_path_refuses()
    {
        var j = new RunJournal(Project, Lot, Run, "spec.json", Sha, @"\\server\share\m", Array.Empty<JournalInvocation>());
        Assert.Equal(PlanRefusal.ModelPathMismatch, ResumePlanner.Plan(Abc, Run, @"\\server\share\m", j, Snap(j)).Refusal);
    }

    // ---- m5: every invocation's model path

    private static JournalInvocation InvAt(string modelPath, params JournalObject[] objects)
        => new(JournalCommand.Build, "2026-11-08T09:00:00Z", "2026-11-08T09:00:05Z", "2024.0", modelPath, InvocationOutcome.Stopped, 4, false, objects, null, Array.Empty<JournalConflict>());

    [Theory]
    [InlineData(@"D:\Other\model")]
    [InlineData(@"C:\Models\demo-copy\sub")]
    [InlineData("relative")]
    public void R15_invocation_on_another_model_refuses(string invocationModel)
    {
        var j = Journal(Inv(), InvAt(invocationModel, JO(A, G(1), ObjectState.Tagged)));
        var plan = Plan(Abc, j, Snap(j, Tagged(A, G(1))));
        Assert.Equal(PlanRefusal.ModelPathMismatch, plan.Refusal);
        Assert.Equal(ExitCode.RefusedBySafetyRule, plan.ExitCode);
        Assert.Contains(invocationModel, plan.Detail, StringComparison.Ordinal);
    }

    [Fact]
    public void Invocation_model_path_compares_like_safety_rule_1()
    {
        var j = Journal(InvAt("c:/models/DEMO-COPY/", JO(A, G(1), ObjectState.Tagged)));
        Assert.False(Plan(Abc, j, Snap(j, Tagged(A, G(1)))).Refused);
    }

    // ---- m2: a running invocation must be marked abandoned first

    [Fact]
    public void R16_running_invocation_refuses_until_marked_abandoned()
    {
        var j = Journal(Inv(InvocationOutcome.Running, JournalCommand.Build, JO(A, G(1), ObjectState.Tagged)));
        var plan = Plan(Abc, j, Snap(j, Tagged(A, G(1))));
        Assert.Equal(PlanRefusal.InvocationStillRunning, plan.Refusal);
        Assert.Equal(ExitCode.RefusedBySafetyRule, plan.ExitCode);
        Assert.Contains("MarkRunningAbandoned", plan.Detail, StringComparison.Ordinal);
        var marked = j.MarkRunningAbandoned();
        var resumed = Plan(Abc, marked, Snap(marked, Tagged(A, G(1))));
        Assert.True(resumed.Executable, resumed.Detail);
    }

    // ---- M2: a plan with conflicts cannot be executed

    [Fact]
    public void Plan_with_a_conflict_has_no_executable_action()
    {
        var journal = Journal(Inv(JO(A, G(1), ObjectState.Tagged), JO(B, null, ObjectState.Inserting)));
        var plan = Plan(Abc, journal, Snap(journal, Tagged(A, G(1))));
        Assert.False(plan.Executable);
        Assert.Equal(new[] { MemberAction.Blocked, MemberAction.Conflict, MemberAction.Blocked }, plan.Members.Select(p => p.Action));
        Assert.Equal(new[] { MemberAction.Skip, MemberAction.Conflict, MemberAction.Create }, plan.Members.Select(p => p.IntendedAction));
        Assert.Equal(G(1), plan.Members[0].Guid);
    }

    [Fact]
    public void Plan_without_conflicts_is_executable_and_blocks_nothing()
    {
        var journal = Journal(Inv(JO(A, G(1), ObjectState.Tagged)));
        var plan = Plan(Abc, journal, Snap(journal, Tagged(A, G(1))));
        Assert.True(plan.Executable);
        Assert.Equal(new[] { MemberAction.Skip, MemberAction.Create, MemberAction.Create }, plan.Members.Select(p => p.Action));
        Assert.Equal(plan.Members.Select(p => p.Action), plan.Members.Select(p => p.IntendedAction));
    }

    [Fact]
    public void Refused_plan_is_not_executable()
    {
        Assert.False(ResumePlanner.Plan(Abc, "bad", ModelPath, null, Snap(null)).Executable);
    }

    [Fact]
    public void Run_level_conflict_alone_blocks_every_member()
    {
        var plan = Plan(Abc, Journal(), Snap(Journal(), Obj(A, G(8)).Tags(LotText, Run, "L1-GONE")));
        Assert.False(plan.Executable);
        Assert.All(plan.Members, p => Assert.Equal(MemberAction.Blocked, p.Action));
        Assert.All(plan.Members, p => Assert.Equal(MemberAction.Create, p.IntendedAction));
        Assert.All(plan.Members, p => Assert.False(p.Recreated));
    }

    [Fact]
    public void Blocked_recreate_is_still_reported()
    {
        var journal = Journal(Inv(JO(A, G(1), ObjectState.Tagged), JO(B, null, ObjectState.Inserting)));
        var plan = Plan(Abc, journal, Snap(journal));
        Assert.Equal(MemberAction.Blocked, plan.Members[0].Action);
        Assert.True(plan.Members[0].Recreated);
    }

    // ---- m1: numbers in details are the same on every runtime

    [Fact]
    public void Detail_numbers_use_a_fixed_invariant_format()
    {
        var m = Member("M", "beam", new Point3(0, 0, 0), new Point3(1000, 0, 0));
        var j = Journal(Inv(JO(m, G(1), ObjectState.Tagged)));
        var plan = Plan(Spec(m), j, SnapFor(Spec(m), j, Tagged(m, G(1)).With(o =>
        {
            o.Start = new Point3(0.03, 0.04, -0.12);
            o.End = new Point3(1000.0000004, -0.0000001, 1.0 / 3.0);
            o.Rotation = -1e-7;
        })));
        var detail = Assert.Single(plan.Conflicts).Detail;
        Assert.Contains("start (0.03, 0.04, -0.12) is 0.13 mm from the spec (0, 0, 0)", detail, StringComparison.Ordinal);
        Assert.Contains("end (1000, 0, 0.333333) is 0.333333 mm from the spec (1000, 0, 0)", detail, StringComparison.Ordinal);
        Assert.DoesNotContain("rotation", detail, StringComparison.Ordinal);
    }

    [Fact]
    public void Detail_numbers_handle_extremes()
    {
        var m = Member("M", "beam", new Point3(0, 0, 0), new Point3(1000, 0, 0));
        var j = Journal(Inv(JO(m, G(1), ObjectState.Tagged)));
        var plan = Plan(Spec(m), j, SnapFor(Spec(m), j, Tagged(m, G(1)).With(o =>
        {
            o.Start = new Point3(double.NaN, double.PositiveInfinity, double.NegativeInfinity);
            o.End = new Point3(1.5e20, -2.5e-9, 0);
            o.Rotation = double.NaN;
        })));
        var detail = Assert.Single(plan.Conflicts).Detail;
        Assert.Contains("start (NaN, Infinity, -Infinity) is NaN mm", detail, StringComparison.Ordinal);
        Assert.Contains("end (1.5E+20, 0, 0) is 1.5E+20 mm", detail, StringComparison.Ordinal);
        Assert.Contains("rotation NaN deg (spec 0 deg)", detail, StringComparison.Ordinal);
    }

    [Fact]
    public void Detail_numbers_switch_to_an_exponent_at_1e15()
    {
        var m = Member("M", "beam", new Point3(0, 0, 0), new Point3(1000, 0, 0));
        var j = Journal(Inv(JO(m, G(1), ObjectState.Tagged)));
        var plan = Plan(Spec(m), j, SnapFor(Spec(m), j, Tagged(m, G(1)).With(o => o.Start = new Point3(1e15, 99999999999999.5, -1.234567891e20))));
        Assert.Contains("start (1E+15, 99999999999999.5, -1.234568E+20)", Assert.Single(plan.Conflicts).Detail, StringComparison.Ordinal);
    }

    // ---- m6: one entry per SPEC_ID within an invocation

    [Fact]
    public void Reader_refuses_two_entries_for_one_spec_id_in_one_invocation()
    {
        var obj2 = "{\"spec_id\":\"L1-C-A1\",\"guid\":null,\"action\":\"created\",\"state\":\"inserting\"}";
        var text = RunJournalJsonTests.Swap(RunJournalJsonTests.Base, "\"state\":\"tagged\"}]", "\"state\":\"tagged\"}," + obj2 + "]");
        var result = RunJournalJsonTests.Parse(text);
        Assert.Equal(JournalReadStatus.Invalid, result.Status);
        Assert.Equal(ExitCode.RefusedBySafetyRule, result.ExitCode);
        Assert.Equal("test journal is not a valid run journal: 'invocations[0].objects[1].spec_id' repeats L1-C-A1 within one invocation.", result.Detail);
    }

    [Fact]
    public void Same_spec_id_in_two_invocations_is_fine()
    {
        var example = RunJournalFile.Read(RepoPaths.SchemaExample("run-journal.example.json"));
        Assert.Equal(JournalReadStatus.Found, example.Status);
        Assert.Equal("L1-C-A2", example.Journal!.Invocations[0].Objects[1].SpecId);
        Assert.Equal("L1-C-A2", example.Journal.Invocations[1].Objects[0].SpecId);
    }

    // ---- M1: a failed replace never loses both journals

    private string JournalPath => Path.Combine(_dir, "run-journal-R1.json");

    private string[] Names() => Directory.GetFiles(_dir).Select(Path.GetFileName).OrderBy(n => n, StringComparer.Ordinal).ToArray()!;

    [Fact]
    public void Io1_replace_failing_after_removing_the_target_keeps_the_new_bytes_and_reading_refuses()
    {
        File.WriteAllBytes(JournalPath, new byte[] { 9 });
        var calls = 0;
        string? temporary = null;
        Assert.ThrowsAny<IOException>(() => AtomicFile.Write(JournalPath, new byte[] { 1 }, (tmp, target, backup) =>
        {
            calls++;
            temporary = tmp;
            if (File.Exists(target))
            {
                File.Move(target, backup); // ERROR_UNABLE_TO_MOVE_REPLACEMENT_2: the old file is now the backup
            }

            throw new IOException("unable to move replacement " + calls.ToString(CultureInfo.InvariantCulture));
        }, _ => { }));
        Assert.Equal(4, calls);
        Assert.Equal(new byte[] { 1 }, File.ReadAllBytes(temporary!));
        Assert.Equal(new byte[] { 9 }, File.ReadAllBytes(Path.Combine(_dir, ".run-journal-R1.json.bak")));
        var read = RunJournalFile.Read(JournalPath);
        Assert.Equal(JournalReadStatus.InterruptedWrite, read.Status);
        Assert.Equal(ExitCode.RefusedBySafetyRule, read.ExitCode);
        Assert.Null(read.Journal);
        Assert.Equal(
            "No run journal at '" + JournalPath + "', but .run-journal-R1.json.bak, " + Path.GetFileName(temporary!)
            + " lie next to it: a journal write may have been interrupted. Check the folder before anything else.",
            read.Detail);
    }

    [Fact]
    public void Io1b_replace_failing_without_removing_anything_cleans_up()
    {
        File.WriteAllBytes(JournalPath, new byte[] { 9 });
        Assert.ThrowsAny<IOException>(() => AtomicFile.Write(JournalPath, new byte[] { 1 }, (_, _, _) => throw new IOException("locked"), _ => { }));
        Assert.Equal(new[] { "run-journal-R1.json" }, Names());
    }

    [Fact]
    public void Successful_replace_keeps_no_backup()
    {
        string? seen = null;
        File.WriteAllBytes(JournalPath, new byte[] { 9 });
        AtomicFile.Write(JournalPath, new byte[] { 1 }, (tmp, target, backup) =>
        {
            seen = backup;
            AtomicFile.PutInPlace(tmp, target, backup);
            Assert.Equal(new byte[] { 9 }, File.ReadAllBytes(backup));
        }, _ => { });
        Assert.Equal(Path.Combine(Path.GetFullPath(_dir), ".run-journal-R1.json.bak"), seen);
        Assert.Equal(new[] { "run-journal-R1.json" }, Names());
        Assert.Equal(new byte[] { 1 }, File.ReadAllBytes(JournalPath));
    }

    [Fact]
    public void First_write_failing_keeps_its_temporary_file()
    {
        // "Never delete the temporary file while the target is missing": the next read refuses.
        Assert.ThrowsAny<IOException>(() => AtomicFile.Write(JournalPath, new byte[] { 1 }, (_, _, _) => throw new IOException("x"), _ => { }));
        var name = Assert.Single(Names());
        Assert.StartsWith(".run-journal-R1.json.", name, StringComparison.Ordinal);
        Assert.Equal(JournalReadStatus.InterruptedWrite, RunJournalFile.Read(JournalPath).Status);
    }

    [Theory]
    [InlineData(".run-journal-R1.json.bak")]
    [InlineData(".run-journal-R1.json.0123456789abcdef0123456789abcdef.tmp")]
    public void Leftover_next_to_a_missing_journal_refuses(string leftover)
    {
        File.WriteAllBytes(Path.Combine(_dir, leftover), new byte[] { 1 });
        File.WriteAllBytes(Path.Combine(_dir, "unrelated.tmp"), new byte[] { 1 });
        var read = RunJournalFile.Read(JournalPath);
        Assert.Equal(JournalReadStatus.InterruptedWrite, read.Status);
        Assert.Equal(ExitCode.RefusedBySafetyRule, read.ExitCode);
        Assert.Equal(
            "No run journal at '" + JournalPath + "', but " + leftover + " lie next to it: a journal write may have been interrupted. Check the folder before anything else.",
            read.Detail);
    }

    [Theory]
    [InlineData(".run-journal-R2.json.bak")]
    [InlineData("run-journal-R1.json.bak")]
    [InlineData(".run-journal-R1.json.tmp.old")]
    [InlineData(".run-journal-R1.jsonx.bak")]
    [InlineData(".run-journal-R1.json..tmp")]
    [InlineData(".run-journal-R1.json.tmp")]
    [InlineData("x.tmp")]
    public void Unrelated_files_are_not_leftovers(string other)
    {
        File.WriteAllBytes(Path.Combine(_dir, other), new byte[] { 1 });
        Assert.Equal(JournalReadStatus.Missing, RunJournalFile.Read(JournalPath).Status);
    }

    [Fact]
    public void Leftover_next_to_a_present_journal_is_reported()
    {
        File.Copy(RepoPaths.SchemaExample("run-journal.example.json"), JournalPath);
        File.WriteAllBytes(Path.Combine(_dir, ".run-journal-R1.json.bak"), new byte[] { 1 });
        File.WriteAllBytes(Path.Combine(_dir, ".run-journal-R1.json.b.tmp"), new byte[] { 1 });
        File.WriteAllBytes(Path.Combine(_dir, ".run-journal-R1.json.a.tmp"), new byte[] { 1 });
        var read = RunJournalFile.Read(JournalPath);
        Assert.Equal(JournalReadStatus.Found, read.Status);
        Assert.Equal(
            "Run journal '" + JournalPath + "' read: 2 invocation(s). Leftover file(s) next to it: .run-journal-R1.json.bak, .run-journal-R1.json.a.tmp, .run-journal-R1.json.b.tmp.",
            read.Detail);
    }

    // ---- m3: releasing on another thread

    [Fact]
    public void Lock1_release_on_another_thread_throws_and_does_not_poison_the_process()
    {
        var path = @"C:\Models\review-" + Guid.NewGuid().ToString("N", CultureInfo.InvariantCulture);
        RunLockResult? held = null;
        using var acquired = new ManualResetEventSlim();
        using var done = new ManualResetEventSlim();
        var t = new Thread(() =>
        {
            held = NamedMutexRunLock.Instance.TryAcquire(path);
            acquired.Set();
            done.Wait();
        });
        t.Start();
        acquired.Wait();
        try
        {
            Assert.True(held!.Acquired);
            var e = Assert.Throws<InvalidOperationException>(() => held.Dispose());
            Assert.Equal("The run lock must be released on the thread that acquired it.", e.Message);
            held.Dispose(); // already released: no-op
            using var again = NamedMutexRunLock.Instance.TryAcquire(path);
            Assert.False(again.Acquired);
            Assert.DoesNotContain("this process", again.Detail, StringComparison.Ordinal);
            Assert.Contains("another writer", again.Detail, StringComparison.Ordinal);
        }
        finally
        {
            done.Set();
            t.Join();
        }

        using var third = NamedMutexRunLock.Instance.TryAcquire(path);
        Assert.True(third.Acquired, third.Detail);
    }

    // ---- m4: one namespace for every session

    [Fact]
    public void Mutex_lives_in_the_global_namespace()
    {
        Assert.StartsWith(@"Global\tekla-harness-run-", NamedMutexRunLock.MutexName(@"C:\Models\Copy"), StringComparison.Ordinal);
    }
}
