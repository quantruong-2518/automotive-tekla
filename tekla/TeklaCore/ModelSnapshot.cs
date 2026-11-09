using System;
using System.Collections.Generic;
using System.Linq;

namespace TeklaHarness.Core;

/// <summary>How a tag UDA read back.</summary>
public enum TagState
{
    Absent,
    Value,

    /// <summary>The read failed: the planner refuses (exit 3, decision 6).</summary>
    Unreadable,
}

/// <summary>One harness tag (<c>LOT</c>, <c>RUN_ID</c>, <c>SPEC_ID</c>) as read from an object.</summary>
public sealed class TagReading
{
    public static readonly TagReading Absent = new(TagState.Absent, null);

    public static readonly TagReading Unreadable = new(TagState.Unreadable, null);

    private TagReading(TagState state, string? value)
    {
        State = state;
        Value = value;
    }

    public TagState State { get; }

    /// <summary>Non-empty when <see cref="State"/> is <see cref="TagState.Value"/>; otherwise null.</summary>
    public string? Value { get; }

    /// <summary>A present value. An empty string is not a value: the reader must say <see cref="Absent"/>.</summary>
    public static TagReading Of(string value)
    {
        if (string.IsNullOrEmpty(value))
        {
            throw new ArgumentException("A tag value is non-empty; use TagReading.Absent.", nameof(value));
        }

        return new TagReading(TagState.Value, value);
    }

    /// <summary>True when the tag holds exactly <paramref name="expected"/> (ordinal).</summary>
    internal bool Is(string expected) => State == TagState.Value && string.Equals(Value, expected, StringComparison.Ordinal);
}

/// <summary>Which snapshot lookups returned an object (decision 6).</summary>
[Flags]
public enum SnapshotLookup
{
    None = 0,
    Lot = 1,
    RunId = 2,
    SpecId = 4,
    JournalGuid = 8,
}

/// <summary>
/// One model object of the snapshot, global coordinates in millimetres. Null fields could not be
/// read; a null point, profile, material or rotation never matches a spec item.
/// </summary>
public sealed class SnapshotObject
{
    public SnapshotObject(
        Guid guid,
        SnapshotLookup foundBy,
        string kind,
        TagReading lot,
        TagReading runId,
        TagReading specId,
        Point3? start,
        Point3? end,
        string? profile,
        string? material,
        double? rotationDeg,
        string? memberClass,
        string? name)
    {
        Guid = guid;
        FoundBy = foundBy;
        Kind = kind ?? throw new ArgumentNullException(nameof(kind));
        Lot = lot ?? throw new ArgumentNullException(nameof(lot));
        RunId = runId ?? throw new ArgumentNullException(nameof(runId));
        SpecId = specId ?? throw new ArgumentNullException(nameof(specId));
        Start = start;
        End = end;
        Profile = profile;
        Material = material;
        RotationDeg = rotationDeg;
        Class = memberClass;
        Name = name;
    }

    public Guid Guid { get; }

    public SnapshotLookup FoundBy { get; }

    /// <summary>The spec's <c>type</c> vocabulary (<c>beam</c>, <c>column</c>, ...) or <c>other</c>.</summary>
    public string Kind { get; }

    public TagReading Lot { get; }

    public TagReading RunId { get; }

    public TagReading SpecId { get; }

    public Point3? Start { get; }

    public Point3? End { get; }

    public string? Profile { get; }

    public string? Material { get; }

    public double? RotationDeg { get; }

    public string? Class { get; }

    public string? Name { get; }
}

/// <summary>Result of looking up one journal GUID.</summary>
public enum GuidPresence
{
    Present,

    /// <summary>Only when the lookup of that very GUID said "not found".</summary>
    Absent,

    /// <summary>The lookup failed: the planner refuses (exit 4, decision 6).</summary>
    Error,
}

/// <summary>
/// The model as the resume planner sees it (decision 6): the union of objects with <c>LOT</c> = lot,
/// <c>RUN_ID</c> = run, <c>SPEC_ID</c> in the spec's ids, and every journal GUID; plus the lookup
/// result of every journal GUID.
/// </summary>
public sealed class ModelSnapshot
{
    public ModelSnapshot(IEnumerable<SnapshotObject> objects, IReadOnlyDictionary<Guid, GuidPresence> journalGuids)
    {
        Objects = RunJournal.NoNulls(objects, nameof(objects));
        JournalGuids = journalGuids ?? throw new ArgumentNullException(nameof(journalGuids));
        var duplicate = Objects.GroupBy(o => o.Guid).FirstOrDefault(g => g.Count() > 1);
        if (duplicate is not null)
        {
            throw new ArgumentException("Object " + duplicate.Key.ToString("D", System.Globalization.CultureInfo.InvariantCulture) + " appears twice.", nameof(objects));
        }
    }

    public IReadOnlyList<SnapshotObject> Objects { get; }

    public IReadOnlyDictionary<Guid, GuidPresence> JournalGuids { get; }
}
