using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;

namespace TeklaHarness.Core.Tests;

/// <summary>Builders for resume-planner tests: by default every object matches its member exactly.</summary>
internal static class PlanFixtures
{
    public const string Project = "demo-warehouse";
    public const int Lot = 1;
    public const string LotText = "1";
    public const string Run = "R20261108-01";
    public const string ModelPath = @"C:\Models\demo-copy";
    public static readonly string Sha = new('a', 64);

    public static readonly MemberSpec A = Member("L1-C-A1", "column", new Point3(0, 0, 0), new Point3(0, 0, 6000));
    public static readonly MemberSpec B = Member("L1-C-A2", "column", new Point3(6000, 0, 0), new Point3(6000, 0, 6000));
    public static readonly MemberSpec C = Member("L1-B-A12", "beam", new Point3(0, 0, 6000), new Point3(6000, 0, 6000), profile: "IPE300");

    public static MemberSpec Member(
        string specId,
        string type,
        Point3 start,
        Point3 end,
        string profile = "HEA300",
        string material = "S355JR",
        double? rotation = null,
        string? name = null,
        string? memberClass = null)
        => new(specId, type, profile, material, start, end, rotation, name, mark: null, memberClass);

    public static LotSpec Spec(params MemberSpec[] members) => new("0.1", Project, Lot, members, Sha, 1);

    public static LotSpec Abc => Spec(A, B, C);

    public static Guid G(int n) => new("00000000-0000-0000-0000-" + n.ToString("x12", CultureInfo.InvariantCulture));

    public static ObjectBuilder Obj(MemberSpec m, Guid guid) => new(m, guid);

    /// <summary>An object of <paramref name="m"/> tagged with this lot, run and its spec id.</summary>
    public static ObjectBuilder Tagged(MemberSpec m, Guid guid) => new ObjectBuilder(m, guid).Tags(LotText, Run, m.SpecId);

    public static JournalObject JO(MemberSpec m, Guid? guid, ObjectState state, ObjectAction action = ObjectAction.Created)
        => new(m.SpecId, guid, action, state);

    public static JournalInvocation Inv(params JournalObject[] objects)
        => Inv(InvocationOutcome.Stopped, JournalCommand.Build, objects);

    public static JournalInvocation Inv(InvocationOutcome outcome, JournalCommand command, params JournalObject[] objects)
        => new(
            command,
            "2026-11-08T09:00:00Z",
            outcome == InvocationOutcome.Running ? null : "2026-11-08T09:00:05Z",
            "2024.0",
            ModelPath,
            outcome,
            outcome == InvocationOutcome.Running ? null : (outcome == InvocationOutcome.Ok ? 0 : 4),
            committed: false,
            objects,
            failure: null,
            conflicts: Array.Empty<JournalConflict>());

    public static RunJournal Journal(params JournalInvocation[] invocations)
        => new(Project, Lot, Run, "spec.json", Sha, ModelPath, invocations);

    /// <summary>
    /// Snapshot of <paramref name="objects"/>; every journal GUID is Present when an object has it,
    /// else Absent, unless <paramref name="presence"/> overrides it. Lookup flags follow the tags as
    /// S2 would set them: SPEC_ID only for ids of <paramref name="spec"/> (default <see cref="Abc"/>).
    /// </summary>
    public static ModelSnapshot Snap(RunJournal? journal, IEnumerable<ObjectBuilder> objects, IDictionary<Guid, GuidPresence>? presence = null, LotSpec? spec = null)
    {
        var specIds = new HashSet<string>((spec ?? Abc).Members.Select(m => m.SpecId), StringComparer.Ordinal);
        var journalGuids = journal is null
            ? new HashSet<Guid>()
            : new HashSet<Guid>(journal.Invocations.SelectMany(i => i.Objects).Where(o => o.Guid.HasValue).Select(o => o.Guid!.Value));
        var list = objects.ToList();
        var map = new Dictionary<Guid, GuidPresence>();
        foreach (var g in journalGuids)
        {
            map[g] = list.Any(o => o.Guid == g) ? GuidPresence.Present : GuidPresence.Absent;
        }

        if (presence is not null)
        {
            foreach (var kv in presence)
            {
                map[kv.Key] = kv.Value;
            }
        }

        return new ModelSnapshot(list.Select(o => o.Build(journalGuids.Contains(o.Guid), specIds)), map);
    }

    public static ModelSnapshot Snap(RunJournal? journal, params ObjectBuilder[] objects) => Snap(journal, objects, null);

    /// <summary>Snapshot for a spec other than <see cref="Abc"/>.</summary>
    public static ModelSnapshot SnapFor(LotSpec spec, RunJournal? journal, params ObjectBuilder[] objects) => Snap(journal, objects, null, spec);

    public static ResumePlan Plan(LotSpec spec, RunJournal? journal, ModelSnapshot snapshot) => ResumePlanner.Plan(spec, Run, ModelPath, journal, snapshot);

    public static ResumePlan Plan(RunJournal? journal, params ObjectBuilder[] objects) => Plan(Abc, journal, Snap(journal, objects));

    /// <summary>Mutable description of one snapshot object.</summary>
    internal sealed class ObjectBuilder
    {
        public ObjectBuilder(MemberSpec m, Guid guid)
        {
            Guid = guid;
            Kind = m.Type;
            Start = new Point3(m.Start.X, m.Start.Y, m.Start.Z);
            End = new Point3(m.End.X, m.End.Y, m.End.Z);
            Profile = m.Profile;
            Material = m.Material;
            Rotation = m.RotationDeg ?? 0;
            Class = m.Class;
            Name = m.Name;
        }

        public Guid Guid { get; set; }

        public string Kind { get; set; }

        public TagReading Lot { get; set; } = TagReading.Absent;

        public TagReading RunTag { get; set; } = TagReading.Absent;

        public TagReading SpecTag { get; set; } = TagReading.Absent;

        public Point3? Start { get; set; }

        public Point3? End { get; set; }

        public string? Profile { get; set; }

        public string? Material { get; set; }

        public double? Rotation { get; set; }

        public string? Class { get; set; }

        public string? Name { get; set; }

        /// <summary>Overrides the lookup flags derived from the tags.</summary>
        public SnapshotLookup? FoundBy { get; set; }

        /// <summary>Sets the tags; null leaves a tag absent.</summary>
        public ObjectBuilder Tags(string? lot, string? run, string? specId)
        {
            Lot = lot is null ? TagReading.Absent : TagReading.Of(lot);
            RunTag = run is null ? TagReading.Absent : TagReading.Of(run);
            SpecTag = specId is null ? TagReading.Absent : TagReading.Of(specId);
            return this;
        }

        public ObjectBuilder With(Action<ObjectBuilder> change)
        {
            change(this);
            return this;
        }

        public SnapshotObject Build(bool isJournalGuid) => Build(isJournalGuid, new HashSet<string>(Abc.Members.Select(m => m.SpecId), StringComparer.Ordinal));

        public SnapshotObject Build(bool isJournalGuid, ISet<string> specIds)
        {
            var found = SnapshotLookup.None;
            if (Lot.State == TagState.Value && Lot.Value == LotText)
            {
                found |= SnapshotLookup.Lot;
            }

            if (RunTag.State == TagState.Value && RunTag.Value == Run)
            {
                found |= SnapshotLookup.RunId;
            }

            if (SpecTag.State == TagState.Value && specIds.Contains(SpecTag.Value!))
            {
                found |= SnapshotLookup.SpecId;
            }

            if (isJournalGuid)
            {
                found |= SnapshotLookup.JournalGuid;
            }

            return new SnapshotObject(Guid, FoundBy ?? found, Kind, Lot, RunTag, SpecTag, Start, End, Profile, Material, Rotation, Class, Name);
        }
    }
}
