using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using Xunit;
using static TeklaHarness.Core.Tests.PlanFixtures;

namespace TeklaHarness.Core.Tests;

/// <summary>
/// The engineer reads every refusal and conflict detail (stdout JSON, run journal), so their exact
/// text is pinned in <c>Snapshots/details.txt</c>. On a difference the actual text is written next
/// to the temporary folder for review; update the snapshot only after reading the change.
/// </summary>
public sealed class DetailSnapshotTests
{
    private static string SnapshotPath => Path.Combine(RepoPaths.Root, "tekla", "TeklaCore.Tests", "Snapshots", "details.txt");

    private static string Id(Guid? g) => g.HasValue ? g.Value.ToString("D", CultureInfo.InvariantCulture) : "-";

    private static void Describe(List<string> lines, string name, ResumePlan plan)
    {
        lines.Add("plan " + name + ": " + plan.Refusal + (plan.Executable ? " executable" : string.Empty) + " exit " + ((int)plan.ExitCode).ToString(CultureInfo.InvariantCulture) + " | " + plan.Detail);
        foreach (var m in plan.Members)
        {
            var absent = string.Join(",", m.AbsentJournalObjects.Select(a => Id(a.Guid) + "/" + a.LastState));
            var action = m.Action == m.IntendedAction ? m.Action.ToString() : m.Action + "(" + m.IntendedAction + ")";
            lines.Add("  " + m.SpecId + " " + action + " " + Id(m.Guid) + (m.Recreated ? " recreated" : string.Empty)
                + (absent.Length > 0 ? " absent " + absent : string.Empty) + (m.NameNote is null ? string.Empty : " | note: " + m.NameNote));
        }

        foreach (var c in plan.Conflicts)
        {
            lines.Add("  ! " + c.Kind + " " + (c.SpecId ?? "-") + " " + Id(c.Guid) + " | " + c.Detail);
        }
    }

    private static IEnumerable<(string Name, ResumePlan Plan)> Plans()
    {
        var tagged = Journal(Inv(JO(A, G(1), ObjectState.Tagged)));
        ModelSnapshot S(RunJournal? j, params PlanFixtures.ObjectBuilder[] o) => Snap(j, o);

        // decision 5 and 6 refusals
        yield return ("run id null", ResumePlanner.Plan(Abc, null!, ModelPath, null, Snap(null)));
        yield return ("run id lower case", ResumePlanner.Plan(Abc, "r\u00001", ModelPath, null, Snap(null)));
        var header = new RunJournal(Project, 2, Run, "spec.json", Sha, ModelPath, Array.Empty<JournalInvocation>());
        yield return ("header", Plan(Abc, header, Snap(header)));
        var hash = new RunJournal(Project, Lot, Run, "spec.json", new string('b', 64), ModelPath, Array.Empty<JournalInvocation>());
        yield return ("spec hash", Plan(Abc, hash, Snap(hash)));
        var model = new RunJournal(Project, Lot, Run, "spec.json", Sha, @"C:\Models\other", Array.Empty<JournalInvocation>());
        yield return ("model path", Plan(Abc, model, Snap(model)));
        var rolledBack = Journal(Inv(InvocationOutcome.Ok, JournalCommand.Rollback));
        yield return ("rolled back", Plan(Abc, rolledBack, Snap(rolledBack)));
        var partial = Journal(Inv(InvocationOutcome.Ok, JournalCommand.Build), Inv(InvocationOutcome.Stopped, JournalCommand.Rollback));
        yield return ("partial rollback", Plan(Abc, partial, Snap(partial)));
        yield return ("tagged without journal", Plan(Abc, null, S(null, Tagged(A, G(1)))));
        yield return ("unreadable tag", Plan(Abc, tagged, S(tagged, Tagged(A, G(1)).With(o => o.RunTag = TagReading.Unreadable))));
        yield return ("guid error", Plan(Abc, tagged, Snap(tagged, Array.Empty<PlanFixtures.ObjectBuilder>(), new Dictionary<Guid, GuidPresence> { [G(1)] = GuidPresence.Error })));
        yield return ("no lookup result", Plan(Abc, tagged, new ModelSnapshot(Array.Empty<SnapshotObject>(), new Dictionary<Guid, GuidPresence>())));
        yield return ("present not listed", Plan(Abc, tagged, Snap(tagged, Array.Empty<PlanFixtures.ObjectBuilder>(), new Dictionary<Guid, GuidPresence> { [G(1)] = GuidPresence.Present })));
        yield return ("absent but listed", Plan(Abc, tagged, Snap(tagged, new[] { Tagged(A, G(1)) }, new Dictionary<Guid, GuidPresence> { [G(1)] = GuidPresence.Absent })));
        yield return ("missed by LOT", Plan(Abc, tagged, S(tagged, Tagged(A, G(1)).With(o => o.FoundBy = SnapshotLookup.RunId | SnapshotLookup.SpecId))));
        yield return ("missed by RUN_ID", Plan(Abc, tagged, S(tagged, Tagged(A, G(1)).With(o => o.FoundBy = SnapshotLookup.Lot | SnapshotLookup.SpecId))));
        yield return ("missed by SPEC_ID", Plan(Abc, tagged, S(tagged, Tagged(A, G(1)).With(o => o.FoundBy = SnapshotLookup.Lot | SnapshotLookup.RunId))));
        yield return ("LOT hit, tag absent", Plan(Abc, tagged, S(tagged, Tagged(A, G(1)).With(o => o.Lot = TagReading.Absent).With(o => o.FoundBy = SnapshotLookup.Lot | SnapshotLookup.RunId | SnapshotLookup.SpecId | SnapshotLookup.JournalGuid))));
        yield return ("SPEC_ID hit, foreign tag", Plan(Abc, Journal(), S(Journal(), Obj(A, G(2)).Tags(LotText, Run, "L1-GONE").With(o => o.FoundBy = SnapshotLookup.Lot | SnapshotLookup.RunId | SnapshotLookup.SpecId))));
        yield return ("no lookup", Plan(Abc, Journal(), S(Journal(), Obj(A, G(2)))));
        yield return ("journal flag missing", Plan(Abc, tagged, S(tagged, Tagged(A, G(1)).With(o => o.FoundBy = SnapshotLookup.Lot | SnapshotLookup.RunId | SnapshotLookup.SpecId))));
        var running = Journal(Inv(InvocationOutcome.Running, JournalCommand.Build));
        yield return ("still running", Plan(Abc, running, Snap(running)));
        var elsewhere = Journal(new JournalInvocation(JournalCommand.Build, "2026-11-08T09:00:00Z", null, "2024.0", @"D:\Other", InvocationOutcome.Stopped, 4, false, Array.Empty<JournalObject>(), null, Array.Empty<JournalConflict>()));
        yield return ("invocation elsewhere", Plan(Abc, elsewhere, Snap(elsewhere)));

        // decision 8 plans
        yield return ("fresh", Plan(Abc, null, Snap(null)));
        var resume = Journal(Inv(JO(A, G(1), ObjectState.Tagged), JO(B, G(2), ObjectState.Inserted), JO(C, G(3), ObjectState.Tagged)));
        yield return ("resume", Plan(Abc, resume, S(resume, Tagged(A, G(1)), Obj(B, G(2)).Tags(LotText, null, null))));
        var named = Member("N", "beam", new Point3(0, 0, 0), new Point3(1000, 0, 0), name: "BEAM-A", memberClass: "3");
        var namedJournal = Journal(Inv(JO(named, G(1), ObjectState.Tagged)));
        yield return ("name note", Plan(Spec(named), namedJournal, SnapFor(Spec(named), namedJournal, Tagged(named, G(1)).With(o => o.Name = null))));
        yield return ("mismatch every field", Plan(Spec(named), namedJournal, SnapFor(Spec(named), namedJournal, Tagged(named, G(1)).With(o =>
        {
            o.Start = null;
            o.End = new Point3(1000.5, 0, 0);
            o.Profile = "X\u0001";
            o.Material = null;
            o.Kind = "other";
            o.Rotation = null;
            o.Class = null;
            o.Name = "BEAM-B";
        }))));
        yield return ("mismatch numbers", Plan(Spec(named), namedJournal, SnapFor(Spec(named), namedJournal, Tagged(named, G(1)).With(o =>
        {
            o.Start = new Point3(0.03, 0.04, -0.12);
            o.Rotation = 1.5;
            o.Class = "4";
            o.Name = "BEAM-A";
        }))));
        var intent = Journal(Inv(JO(A, null, ObjectState.Inserting)));
        yield return ("intent", Plan(Abc, intent, Snap(intent)));
        yield return ("duplicate", Plan(Abc, tagged, S(tagged, Tagged(A, G(1)), Tagged(A, G(2)))));
        var twice = Journal(Inv(JO(A, G(1), ObjectState.Tagged)), Inv(JO(A, G(2), ObjectState.Tagged)));
        yield return ("not the latest", Plan(Abc, twice, S(twice, Tagged(A, G(1)))));
        var shared = Journal(Inv(JO(A, G(1), ObjectState.Inserted), JO(B, G(1), ObjectState.Inserted)));
        yield return ("one guid two members", Plan(Abc, shared, Snap(shared)));
        var inserted = Journal(Inv(JO(A, G(1), ObjectState.Inserted)));
        yield return ("tags contradict", Plan(Abc, inserted, S(inserted, Obj(A, G(1)).Tags("2", null, B.SpecId))));
        yield return ("other run", Plan(Abc, null, S(null, Obj(A, G(5)).Tags(LotText, "R-OLD", A.SpecId))));
        yield return ("other lot", Plan(Abc, null, S(null, Obj(A, G(7)).Tags("2", Run, A.SpecId), Obj(B, G(8)).Tags("2", Run, null))));
        var empty = Journal();
        yield return ("unknown spec id", Plan(Abc, empty, S(empty, Obj(A, G(8)).Tags(LotText, Run, "L1-GONE"))));
        var gone = Member("L1-GONE", "beam", new Point3(0, 0, 0), new Point3(1, 0, 0));
        var goneJournal = Journal(Inv(JO(gone, G(9), ObjectState.Tagged), JO(gone, null, ObjectState.Inserting)));
        yield return ("unknown in journal", Plan(Abc, goneJournal, Snap(goneJournal)));
        yield return ("unclassified", Plan(Abc, empty, S(empty, Obj(A, G(6)).Tags(LotText, null, null), Obj(B, G(7)).Tags(null, null, B.SpecId))));
    }

    private static List<string> Actual()
    {
        var lines = new List<string>();
        foreach (var (name, plan) in Plans())
        {
            Describe(lines, name, plan);
        }

        var i = 0;
        foreach (var row in RunJournalJsonTests.RejectCases)
        {
            var detail = RunJournalJsonTests.Parse(RunJournalJsonTests.Swap(RunJournalJsonTests.Base, (string)row[0], (string)row[1])).Detail;
            lines.Add("reader " + (i++).ToString("000", CultureInfo.InvariantCulture) + " | " + detail);
        }

        foreach (var text in new[] { "[]", "{\"schema_version\":\"0.1\"}" })
        {
            lines.Add("reader " + text + " | " + RunJournalJsonTests.Parse(text).Detail);
        }

        return lines;
    }

    [Fact]
    public void Details_match_the_snapshot()
    {
        var actual = Actual();
        var expected = File.Exists(SnapshotPath)
            ? File.ReadAllText(SnapshotPath, Encoding.UTF8).TrimEnd('\n', '\r').Split('\n').Select(l => l.TrimEnd('\r')).ToList()
            : new List<string>();
        if (actual.SequenceEqual(expected))
        {
            return;
        }

        var review = Path.Combine(Path.GetTempPath(), "teklacore-details.actual.txt");
        File.WriteAllText(review, string.Join("\n", actual) + "\n", new UTF8Encoding(false));
        var at = Enumerable.Range(0, Math.Max(actual.Count, expected.Count))
            .First(k => k >= actual.Count || k >= expected.Count || actual[k] != expected[k]);
        Assert.Fail(
            "line " + (at + 1).ToString(CultureInfo.InvariantCulture) + " differs (actual written to " + review + ")\nexpected: "
            + (at < expected.Count ? expected[at] : "<end>") + "\nactual:   " + (at < actual.Count ? actual[at] : "<end>"));
    }
}
