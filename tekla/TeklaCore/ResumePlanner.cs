using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text;

namespace TeklaHarness.Core;

/// <summary>Why the planner refused before planning (ADR-0012 decisions 5–6). Nothing is written.</summary>
public enum PlanRefusal
{
    None,

    /// <summary>The run id breaks the <c>run_id</c> pattern (exit 2).</summary>
    RunIdInvalid,

    /// <summary>The journal's <c>run_id</c>, <c>lot</c> or <c>project_id</c> is not this run's (exit 5).</summary>
    JournalHeaderMismatch,

    /// <summary>The journal's <c>spec_sha256</c> is not the receipt's (exit 5).</summary>
    SpecHashMismatch,

    /// <summary>The journal's <c>model_path</c> is not the open working copy (exit 5).</summary>
    ModelPathMismatch,

    /// <summary>The run has a <c>rollback</c> invocation, whatever its outcome (exit 5).</summary>
    RunRolledBack,

    /// <summary>No journal, but objects tagged with this lot and run exist (exit 5).</summary>
    TaggedObjectsWithoutJournal,

    /// <summary>A tag of a snapshot object could not be read (exit 3).</summary>
    UnreadableTag,

    /// <summary>The lookup of a journal GUID failed (exit 4).</summary>
    GuidLookupError,

    /// <summary>The snapshot lacks a journal GUID's lookup or object, or contradicts it (exit 3).</summary>
    SnapshotIncomplete,

    /// <summary>An object carries this lot, run or a spec id, but that lookup did not return it: the filter cannot be trusted (exit 3).</summary>
    LookupUntrusted,
}

/// <summary>What to do for one spec member (decision 8).</summary>
public enum MemberAction
{
    /// <summary>One tagged object matches: nothing to do.</summary>
    Skip,

    /// <summary>The journal's object exists with missing tags and matches: tag it.</summary>
    Retag,

    /// <summary>Nothing exists for this member: create it.</summary>
    Create,

    /// <summary>Stop (exit 1): see the member's conflicts.</summary>
    Conflict,
}

/// <summary>A journal GUID of a member that the model no longer has.</summary>
public sealed class AbsentJournalObject
{
    internal AbsentJournalObject(Guid guid, ObjectState lastState)
    {
        Guid = guid;
        LastState = lastState;
    }

    public Guid Guid { get; }

    /// <summary>The state of the last journal entry with this GUID.</summary>
    public ObjectState LastState { get; }
}

/// <summary>The plan for one spec member.</summary>
public sealed class MemberPlan
{
    internal MemberPlan(
        string specId,
        MemberAction action,
        Guid? guid,
        IReadOnlyList<AbsentJournalObject> absentJournalObjects,
        string? nameNote,
        IReadOnlyList<JournalConflict> conflicts)
    {
        SpecId = specId;
        Action = action;
        Guid = guid;
        AbsentJournalObjects = absentJournalObjects;
        NameNote = nameNote;
        Conflicts = conflicts;
    }

    public string SpecId { get; }

    public MemberAction Action { get; }

    /// <summary>The object to skip or retag; null for create and conflict.</summary>
    public Guid? Guid { get; }

    /// <summary>Journal GUIDs of this member that the model no longer has, in journal order.</summary>
    public IReadOnlyList<AbsentJournalObject> AbsentJournalObjects { get; }

    /// <summary>Decision 8: a create that replaces an object the journal recorded is reported, never silent.</summary>
    public bool Recreated => Action == MemberAction.Create && AbsentJournalObjects.Count > 0;

    /// <summary>The object's name differs from the spec's (reported, not a conflict); otherwise null.</summary>
    public string? NameNote { get; }

    /// <summary>This member's conflicts; non-empty exactly when <see cref="Action"/> is <see cref="MemberAction.Conflict"/>.</summary>
    public IReadOnlyList<JournalConflict> Conflicts { get; }
}

/// <summary>Result of <see cref="ResumePlanner.Plan"/>: a refusal, or one action per spec member.</summary>
public sealed class ResumePlan
{
    internal ResumePlan(PlanRefusal refusal, string detail, IReadOnlyList<MemberPlan> members, IReadOnlyList<JournalConflict> conflicts)
    {
        Refusal = refusal;
        Detail = detail;
        Members = members;
        Conflicts = conflicts;
    }

    public bool Refused => Refusal != PlanRefusal.None;

    public PlanRefusal Refusal { get; }

    /// <summary>Human-readable summary or refusal reason.</summary>
    public string Detail { get; }

    /// <summary>One entry per spec member, in spec order; empty when refused.</summary>
    public IReadOnlyList<MemberPlan> Members { get; }

    /// <summary>Every conflict, member conflicts in spec order then run-level ones; empty when refused.</summary>
    public IReadOnlyList<JournalConflict> Conflicts { get; }

    /// <summary>Refusals per decisions 5–6; any conflict 1; otherwise 0.</summary>
    public ExitCode ExitCode => Refusal switch
    {
        PlanRefusal.None => Conflicts.Count > 0 ? ExitCode.ValidationFailure : ExitCode.Ok,
        PlanRefusal.RunIdInvalid => ExitCode.UsageError,
        PlanRefusal.UnreadableTag or PlanRefusal.SnapshotIncomplete or PlanRefusal.LookupUntrusted => ExitCode.EnvironmentError,
        PlanRefusal.GuidLookupError => ExitCode.TeklaApiError,
        _ => ExitCode.RefusedBySafetyRule,
    };
}

/// <summary>
/// The resume planner (ADR-0012 decisions 5–8): pure, Tekla-free. Given the loaded spec, the run,
/// the open working copy, the journal (null when none) and a snapshot, it refuses or plans exactly
/// one action per spec member. It never plans a create for a member while any object in the
/// snapshot carries that member's <c>SPEC_ID</c> or is the journal's object for it, and every
/// object with a harness tag is either a skip/retag target or named by a conflict.
/// </summary>
public static class ResumePlanner
{
    /// <summary>Largest start or end distance that still matches, in millimetres (decision 7).</summary>
    public const double PointToleranceMm = 0.1;

    /// <summary>
    /// Added to <see cref="PointToleranceMm"/> so that "0.1 mm or less" holds for decimal coordinates:
    /// 6000 and 6000.1 are stored as binary doubles whose difference is 0.10000000000036. The
    /// allowance absorbs that rounding for coordinates up to about 1e6 mm (error near 1e-10 mm) and
    /// is physically meaningless (one nanometre).
    /// </summary>
    public const double PointRoundingAllowanceMm = 1e-6;

    /// <summary>Largest rotation difference that still matches, in degrees, modulo 360 (decision 7).</summary>
    public const double RotationToleranceDeg = 0.01;

    /// <summary>
    /// The same kind of allowance for rotations: 90.01 - 90 is 0.010000000000005 in binary. Rounding
    /// of angles below 1e4 degrees stays under 1e-11; 1e-9 degrees is physically meaningless.
    /// </summary>
    public const double RotationRoundingAllowanceDeg = 1e-9;

    public static ResumePlan Plan(LotSpec spec, string runId, string openModelPath, RunJournal? journal, ModelSnapshot snapshot)
    {
        if (spec is null)
        {
            throw new ArgumentNullException(nameof(spec));
        }

        if (snapshot is null)
        {
            throw new ArgumentNullException(nameof(snapshot));
        }

        var refusal = CheckBeforePlanning(spec, runId, openModelPath, journal, snapshot, out var detail);
        if (refusal != PlanRefusal.None)
        {
            return new ResumePlan(refusal, detail, Array.Empty<MemberPlan>(), Array.Empty<JournalConflict>());
        }

        return new Planner(spec, runId, journal, snapshot).Run();
    }

    // ---- decisions 5 and 6: refusals, in a fixed order

    private static PlanRefusal CheckBeforePlanning(LotSpec spec, string runId, string openModelPath, RunJournal? journal, ModelSnapshot snapshot, out string detail)
    {
        detail = string.Empty;
        if (!RunId.IsValid(runId))
        {
            detail = "RUN_ID '" + Text.Printable(runId ?? string.Empty) + "' must match ^[A-Z0-9][A-Z0-9_-]{0,31}$.";
            return PlanRefusal.RunIdInvalid;
        }

        var lotTag = RunId.LotTag(spec.Lot);
        if (journal is not null)
        {
            if (journal.RunId != runId || journal.Lot != spec.Lot || journal.ProjectId != spec.ProjectId)
            {
                detail = "The run journal belongs to project '" + journal.ProjectId + "', lot " + RunId.LotTag(journal.Lot) + ", RUN_ID " + journal.RunId
                    + ", not to project '" + spec.ProjectId + "', lot " + lotTag + ", RUN_ID " + runId + ".";
                return PlanRefusal.JournalHeaderMismatch;
            }

            if (journal.SpecSha256 != spec.SpecSha256)
            {
                detail = "The run journal was written for spec " + journal.SpecSha256 + ", not this spec " + spec.SpecSha256
                    + ": a changed spec is an update, or a rollback of this run and a build with a new RUN_ID (the engineer decides).";
                return PlanRefusal.SpecHashMismatch;
            }

            if (!WindowsPath.TryParse(journal.ModelPath, out var written, out _)
                || !WindowsPath.TryParse(openModelPath, out var open, out _)
                || !WindowsPath.StrictEquals(written!, open!))
            {
                detail = "The run journal was written for model '" + journal.ModelPath + "', but the open working copy is '" + openModelPath + "'.";
                return PlanRefusal.ModelPathMismatch;
            }

            // Any rollback, finished or not (ADR-0012 amended): a resume must never rebuild what the
            // engineer asked to delete.
            var rollback = journal.Invocations.FirstOrDefault(i => i.Command == JournalCommand.Rollback);
            if (rollback is not null)
            {
                detail = "RUN_ID " + runId + " has a rollback invocation (outcome " + RunJournalJson.Outcomes[(int)rollback.Outcome]
                    + "): a run that was rolled back, even partly, is never resumed, so nothing the engineer asked to delete is rebuilt."
                    + " Finish the rollback, then build with a new RUN_ID.";
                return PlanRefusal.RunRolledBack;
            }
        }
        else
        {
            var tagged = snapshot.Objects.FirstOrDefault(o => o.Lot.Is(lotTag) && o.RunId.Is(runId));
            if (tagged is not null)
            {
                detail = "No run journal, but object " + Text.Id(tagged.Guid) + " is tagged with lot " + lotTag + " and RUN_ID " + runId
                    + ": untagged leftovers of this run cannot be ruled out without the journal.";
                return PlanRefusal.TaggedObjectsWithoutJournal;
            }
        }

        var unreadable = snapshot.Objects.FirstOrDefault(
            o => o.Lot.State == TagState.Unreadable || o.RunId.State == TagState.Unreadable || o.SpecId.State == TagState.Unreadable);
        if (unreadable is not null)
        {
            detail = "A tag of object " + Text.Id(unreadable.Guid) + " could not be read.";
            return PlanRefusal.UnreadableTag;
        }

        var journalGuids = journal is null
            ? new List<Guid>()
            : journal.Invocations.SelectMany(i => i.Objects).Where(o => o.Guid.HasValue).Select(o => o.Guid!.Value).Distinct().ToList();
        foreach (var g in journalGuids)
        {
            if (snapshot.JournalGuids.TryGetValue(g, out var presence) && presence == GuidPresence.Error)
            {
                detail = "Looking up journal GUID " + Text.Id(g) + " failed.";
                return PlanRefusal.GuidLookupError;
            }
        }

        var listed = new HashSet<Guid>(snapshot.Objects.Select(o => o.Guid));
        foreach (var g in journalGuids)
        {
            if (!snapshot.JournalGuids.TryGetValue(g, out var presence))
            {
                detail = "The snapshot has no lookup result for journal GUID " + Text.Id(g) + ".";
                return PlanRefusal.SnapshotIncomplete;
            }

            if ((presence == GuidPresence.Present) != listed.Contains(g))
            {
                detail = "The snapshot says journal GUID " + Text.Id(g) + " is " + (presence == GuidPresence.Present ? "present" : "absent")
                    + " but " + (listed.Contains(g) ? "lists" : "does not list") + " its object.";
                return PlanRefusal.SnapshotIncomplete;
            }
        }

        var specIds = new HashSet<string>(spec.Members.Select(m => m.SpecId), StringComparer.Ordinal);
        foreach (var o in snapshot.Objects)
        {
            string? missedBy = null;
            if (o.Lot.Is(lotTag) && (o.FoundBy & SnapshotLookup.Lot) == 0)
            {
                missedBy = "LOT";
            }
            else if (o.RunId.Is(runId) && (o.FoundBy & SnapshotLookup.RunId) == 0)
            {
                missedBy = "RUN_ID";
            }
            else if (o.SpecId.State == TagState.Value && specIds.Contains(o.SpecId.Value!) && (o.FoundBy & SnapshotLookup.SpecId) == 0)
            {
                missedBy = "SPEC_ID";
            }

            if (missedBy is not null)
            {
                detail = "Object " + Text.Id(o.Guid) + " carries this " + missedBy + " but the " + missedBy
                    + " lookup did not return it: the filter cannot be trusted.";
                return PlanRefusal.LookupUntrusted;
            }
        }

        return PlanRefusal.None;
    }

    // ---- decision 7

    /// <summary>Every way <paramref name="o"/> differs from <paramref name="m"/>; empty when it matches.</summary>
    private static List<string> Differences(MemberSpec m, SnapshotObject o)
    {
        var differences = new List<string>();
        ComparePoint(differences, "start", m.Start, o.Start);
        ComparePoint(differences, "end", m.End, o.End);
        if (!string.Equals(o.Profile, m.Profile, StringComparison.Ordinal))
        {
            differences.Add("profile " + Text.Quoted(o.Profile) + " (spec " + Text.Quoted(m.Profile) + ")");
        }

        if (!string.Equals(o.Material, m.Material, StringComparison.Ordinal))
        {
            differences.Add("material " + Text.Quoted(o.Material) + " (spec " + Text.Quoted(m.Material) + ")");
        }

        if (!string.Equals(o.Kind, m.Type, StringComparison.Ordinal))
        {
            differences.Add("kind " + Text.Quoted(o.Kind) + " (spec type " + Text.Quoted(m.Type) + ")");
        }

        var specRotation = m.RotationDeg ?? 0;
        if (!RotationMatches(specRotation, o.RotationDeg))
        {
            differences.Add("rotation " + (o.RotationDeg.HasValue ? Text.Number(o.RotationDeg.Value) + " deg" : "unreadable") + " (spec " + Text.Number(specRotation) + " deg)");
        }

        if (m.Class is not null && !string.Equals(o.Class, m.Class, StringComparison.Ordinal))
        {
            differences.Add("class " + Text.Quoted(o.Class) + " (spec " + Text.Quoted(m.Class) + ")");
        }

        return differences;
    }

    /// <summary>
    /// Euclidean <c>d &lt;= 0.1</c> mm plus the rounding allowance. A non-finite coordinate on either side makes <c>d</c> NaN or
    /// infinite, and neither passes <c>&lt;=</c>, so it never matches.
    /// </summary>
    private static void ComparePoint(List<string> differences, string which, Point3 spec, Point3? model)
    {
        if (model is null)
        {
            differences.Add(which + " unreadable (spec " + Text.Point(spec) + ")");
            return;
        }

        var dx = model.X - spec.X;
        var dy = model.Y - spec.Y;
        var dz = model.Z - spec.Z;
        var distance = Math.Sqrt((dx * dx) + (dy * dy) + (dz * dz));
        if (!(distance <= PointToleranceMm + PointRoundingAllowanceMm))
        {
            differences.Add(which + " " + Text.Point(model) + " is " + Text.Number(distance) + " mm from the spec " + Text.Point(spec));
        }
    }

    /// <summary>
    /// Within 0.01 degrees modulo 360. An unreadable rotation never matches; a non-finite one makes
    /// the difference NaN, which never passes <c>&lt;=</c>.
    /// </summary>
    private static bool RotationMatches(double spec, double? model)
    {
        if (!model.HasValue)
        {
            return false;
        }

        var d = Math.Abs(model.Value - spec) % 360;
        return Math.Min(d, 360 - d) <= RotationToleranceDeg + RotationRoundingAllowanceDeg;
    }

    // ---- decision 8

    private sealed class Planner
    {
        private readonly LotSpec _spec;
        private readonly string _runId;
        private readonly string _lotTag;
        private readonly ModelSnapshot _snapshot;
        private readonly HashSet<string> _specIds;
        private readonly List<JournalObject> _entries;

        /// <summary>Spec ids each journal GUID is recorded for, first appearance first.</summary>
        private readonly Dictionary<Guid, List<string>> _specsByGuid = new();

        private readonly Dictionary<Guid, ObjectState> _lastState = new();
        private readonly Dictionary<string, List<JournalConflict>> _memberConflicts = new(StringComparer.Ordinal);
        private readonly List<JournalConflict> _runConflicts = new();

        /// <summary>Candidates per member: fully tagged objects outside the journal, and uncontradicted journal objects.</summary>
        private readonly Dictionary<string, List<SnapshotObject>> _owners = new(StringComparer.Ordinal);

        public Planner(LotSpec spec, string runId, RunJournal? journal, ModelSnapshot snapshot)
        {
            _spec = spec;
            _runId = runId;
            _lotTag = RunId.LotTag(spec.Lot);
            _snapshot = snapshot;
            _specIds = new HashSet<string>(spec.Members.Select(m => m.SpecId), StringComparer.Ordinal);
            _entries = journal is null ? new List<JournalObject>() : journal.Invocations.SelectMany(i => i.Objects).ToList();
            foreach (var m in spec.Members)
            {
                _memberConflicts[m.SpecId] = new List<JournalConflict>();
                _owners[m.SpecId] = new List<SnapshotObject>();
            }

            foreach (var e in _entries.Where(e => e.Guid.HasValue))
            {
                var g = e.Guid!.Value;
                if (!_specsByGuid.TryGetValue(g, out var specs))
                {
                    _specsByGuid[g] = specs = new List<string>();
                }

                if (!specs.Contains(e.SpecId))
                {
                    specs.Add(e.SpecId);
                }

                _lastState[g] = e.State;
            }
        }

        public ResumePlan Run()
        {
            CheckJournalEntries();
            foreach (var o in _snapshot.Objects)
            {
                Classify(o);
            }

            var members = _spec.Members.Select(PlanMember).ToList();
            var conflicts = members.SelectMany(p => p.Conflicts).Concat(_runConflicts).ToList();
            var detail = "Plan: " + Count(members, MemberAction.Skip) + " skip, " + Count(members, MemberAction.Retag) + " retag, "
                + Count(members, MemberAction.Create) + " create, " + Count(members, MemberAction.Conflict) + " conflict; "
                + conflicts.Count.ToString(CultureInfo.InvariantCulture) + " conflict(s) in all.";
            return new ResumePlan(PlanRefusal.None, detail, members, conflicts);
        }

        private static string Count(List<MemberPlan> members, MemberAction action)
            => members.Count(p => p.Action == action).ToString(CultureInfo.InvariantCulture);

        /// <summary>Journal entries for spec ids outside the spec, and GUIDs recorded for several spec ids.</summary>
        private void CheckJournalEntries()
        {
            foreach (var e in _entries.Where(e => !_specIds.Contains(e.SpecId)))
            {
                AddRun(ConflictKind.UnknownSpecId, e.SpecId, e.Guid, "The journal records " + (e.Guid.HasValue ? "object " + Text.Id(e.Guid.Value) : "an insert intent")
                    + " for SPEC_ID " + e.SpecId + ", which is not in the spec.");
            }

            foreach (var pair in _specsByGuid.Where(p => p.Value.Count > 1))
            {
                foreach (var specId in pair.Value.Where(_specIds.Contains))
                {
                    AddMember(specId, ConflictKind.TagContradiction, pair.Key, "The journal records object " + Text.Id(pair.Key)
                        + " for several SPEC_IDs: " + string.Join(", ", pair.Value) + ".");
                }
            }
        }

        /// <summary>Puts one snapshot object under a member, into a conflict, or nowhere (no harness tag at all).</summary>
        private void Classify(SnapshotObject o)
        {
            var lot = o.Lot;
            var run = o.RunId;
            var specTag = o.SpecId.Value;
            var ours = specTag is not null && _specIds.Contains(specTag);
            var id = Text.Id(o.Guid);
            var tags = "LOT " + Text.Tag(lot) + ", RUN_ID " + Text.Tag(run) + ", SPEC_ID " + Text.Tag(o.SpecId);
            if (_specsByGuid.TryGetValue(o.Guid, out var recorded))
            {
                // A GUID recorded for several spec ids already put each of them in conflict
                // (CheckJournalEntries); its first spec id is enough here.
                var js = recorded[0];
                var contradicts = !_specIds.Contains(js)
                    || (lot.State == TagState.Value && !lot.Is(_lotTag))
                    || (run.State == TagState.Value && !run.Is(_runId))
                    || (specTag is not null && specTag != js);
                if (!contradicts)
                {
                    _owners[js].Add(o);
                    return;
                }

                var detail = "Object " + id + " is recorded in the journal for SPEC_ID " + string.Join(", ", recorded) + " but carries " + tags + ".";
                foreach (var specId in recorded.Where(_specIds.Contains))
                {
                    AddMember(specId, ConflictKind.TagContradiction, o.Guid, detail);
                }

                if (ours)
                {
                    AddMember(specTag!, ConflictKind.TagContradiction, o.Guid, detail);
                }

                return;
            }

            if (lot.Is(_lotTag) && run.Is(_runId) && specTag is not null)
            {
                if (ours)
                {
                    _owners[specTag].Add(o);
                }
                else
                {
                    AddRun(ConflictKind.UnknownSpecId, Text.Printable(specTag), o.Guid, "Object " + id + " is tagged with this lot and run, but SPEC_ID "
                        + Text.Printable(specTag) + " is not in the spec.");
                }
            }
            else if (ours && run.State == TagState.Value && !run.Is(_runId))
            {
                AddMember(specTag!, ConflictKind.SpecIdInOtherRun, o.Guid, "Object " + id + " carries SPEC_ID " + specTag + " under another run: " + tags + ".");
            }
            else if (run.Is(_runId) && lot.State == TagState.Value && !lot.Is(_lotTag))
            {
                Add(ours, specTag, ConflictKind.RunInOtherLot, o.Guid, "Object " + id + " carries RUN_ID " + _runId + " in another lot: " + tags + ".");
            }
            else if (lot.State == TagState.Value || run.State == TagState.Value || specTag is not null)
            {
                Add(ours, specTag, ConflictKind.Unclassified, o.Guid, "Object " + id + " has harness tags no rule classifies: " + tags + ".");
            }
        }

        private MemberPlan PlanMember(MemberSpec m)
        {
            var conflicts = _memberConflicts[m.SpecId];
            var entries = _entries.Where(e => e.SpecId == m.SpecId).ToList();
            if (entries.Any(e => e.State == ObjectState.Inserting))
            {
                AddMember(m.SpecId, ConflictKind.IntentUnresolved, null, "The journal still has an insert intent for SPEC_ID " + m.SpecId
                    + ": an untagged object may exist. Check the model, then roll the run back or remove the stray object and start a new RUN_ID.");
            }

            var latest = entries.LastOrDefault(e => e.Guid.HasValue)?.Guid;
            var absent = entries
                .Where(e => e.Guid.HasValue)
                .Select(e => e.Guid!.Value)
                .Distinct()
                .Where(g => _snapshot.JournalGuids[g] == GuidPresence.Absent)
                .Select(g => new AbsentJournalObject(g, _lastState[g]))
                .ToList();

            var owners = _owners[m.SpecId];
            SnapshotObject? target = null;
            string? nameNote = null;
            if (owners.Count > 1)
            {
                AddMember(m.SpecId, ConflictKind.DuplicateSpecId, null, "Several objects stand for SPEC_ID " + m.SpecId + ": "
                    + string.Join(", ", owners.Select(o => Text.Id(o.Guid))) + ".");
            }
            else if (owners.Count == 1)
            {
                target = owners[0];
                if (latest.HasValue && target.Guid != latest.Value)
                {
                    AddMember(m.SpecId, ConflictKind.TagContradiction, target.Guid, "Object " + Text.Id(target.Guid) + " stands for SPEC_ID " + m.SpecId
                        + ", but the journal's latest object for it is " + Text.Id(latest.Value) + ".");
                }

                var differences = Differences(m, target);
                if (differences.Count > 0)
                {
                    AddMember(m.SpecId, ConflictKind.Mismatch, target.Guid, "Object " + Text.Id(target.Guid) + " differs from spec item " + m.SpecId + ": "
                        + string.Join("; ", differences) + ".");
                }

                if (m.Name is not null && !string.Equals(target.Name, m.Name, StringComparison.Ordinal))
                {
                    nameNote = "Name " + Text.Quoted(target.Name) + " differs from the spec name " + Text.Quoted(m.Name) + ".";
                }
            }

            if (conflicts.Count > 0)
            {
                return new MemberPlan(m.SpecId, MemberAction.Conflict, null, absent, nameNote, conflicts);
            }

            if (target is null)
            {
                return new MemberPlan(m.SpecId, MemberAction.Create, null, absent, null, conflicts);
            }

            var fullyTagged = target.Lot.Is(_lotTag) && target.RunId.Is(_runId) && target.SpecId.Is(m.SpecId);
            return new MemberPlan(m.SpecId, fullyTagged ? MemberAction.Skip : MemberAction.Retag, target.Guid, absent, nameNote, conflicts);
        }

        private void Add(bool member, string? specTag, ConflictKind kind, Guid guid, string detail)
        {
            if (member)
            {
                AddMember(specTag!, kind, guid, detail);
            }
            else
            {
                AddRun(kind, specTag is null ? null : Text.Printable(specTag), guid, detail);
            }
        }

        /// <summary>One conflict per member, kind and GUID.</summary>
        private void AddMember(string specId, ConflictKind kind, Guid? guid, string detail)
        {
            var list = _memberConflicts[specId];
            if (!list.Any(c => c.Kind == kind && c.Guid == guid))
            {
                list.Add(new JournalConflict(kind, specId, guid, Text.Printable(detail)));
            }
        }

        /// <summary>One run-level conflict per kind, spec id and GUID.</summary>
        private void AddRun(ConflictKind kind, string? specId, Guid? guid, string detail)
        {
            if (!_runConflicts.Any(c => c.Kind == kind && c.SpecId == specId && c.Guid == guid))
            {
                _runConflicts.Add(new JournalConflict(kind, specId, guid, Text.Printable(detail)));
            }
        }
    }

    /// <summary>Text for details: invariant numbers, and nothing the journal writer would refuse.</summary>
    private static class Text
    {
        public static string Id(Guid g) => g.ToString("D", CultureInfo.InvariantCulture);

        public static string Number(double x) => x.ToString("R", CultureInfo.InvariantCulture);

        public static string Point(Point3 p) => "(" + Number(p.X) + ", " + Number(p.Y) + ", " + Number(p.Z) + ")";

        public static string Quoted(string? s) => s is null ? "(unreadable)" : "'" + Printable(s) + "'";

        public static string Tag(TagReading t) => t.State == TagState.Value ? "'" + Printable(t.Value!) + "'" : "(absent)";

        /// <summary>Control characters and lone surrogates as <c>\uXXXX</c>; everything else unchanged.</summary>
        public static string Printable(string s)
        {
            var sb = new StringBuilder(s.Length);
            for (var i = 0; i < s.Length; i++)
            {
                var c = s[i];
                if (char.IsHighSurrogate(c) && i + 1 < s.Length && char.IsLowSurrogate(s[i + 1]))
                {
                    sb.Append(c).Append(s[++i]);
                }
                else if (c < ' ' || char.IsSurrogate(c))
                {
                    sb.Append("\\u").Append(((int)c).ToString("x4", CultureInfo.InvariantCulture));
                }
                else
                {
                    sb.Append(c);
                }
            }

            return sb.ToString();
        }
    }
}
