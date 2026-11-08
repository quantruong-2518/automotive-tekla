using System.Collections.Generic;

namespace TeklaHarness.Core;

/// <summary>A lot spec as the CLI reads it for building: only the fields it needs (contract safety rule 3).</summary>
public sealed class LotSpec
{
    internal LotSpec(string schemaVersion, string projectId, int lot, IReadOnlyList<MemberSpec> members, string specSha256, int rulesVersion)
    {
        SchemaVersion = schemaVersion;
        ProjectId = projectId;
        Lot = lot;
        Members = members;
        SpecSha256 = specSha256;
        RulesVersion = rulesVersion;
    }

    public string SchemaVersion { get; }

    public string ProjectId { get; }

    public int Lot { get; }

    public IReadOnlyList<MemberSpec> Members { get; }

    /// <summary>SHA-256 of the spec file's bytes (lowercase hex), equal to the receipt's.</summary>
    public string SpecSha256 { get; }

    /// <summary>The receipt's <c>validator.rules_version</c>.</summary>
    public int RulesVersion { get; }
}

/// <summary>One member to create. Coordinates in millimetres, global.</summary>
public sealed class MemberSpec
{
    internal MemberSpec(
        string specId,
        string type,
        string profile,
        string material,
        Point3 start,
        Point3 end,
        double? rotationDeg,
        string? name,
        string? mark,
        string? memberClass)
    {
        SpecId = specId;
        Type = type;
        Profile = profile;
        Material = material;
        Start = start;
        End = end;
        RotationDeg = rotationDeg;
        Name = name;
        Mark = mark;
        Class = memberClass;
    }

    public string SpecId { get; }

    public string Type { get; }

    public string Profile { get; }

    public string Material { get; }

    public Point3 Start { get; }

    public Point3 End { get; }

    public double? RotationDeg { get; }

    public string? Name { get; }

    public string? Mark { get; }

    public string? Class { get; }
}

/// <summary>A point in millimetres.</summary>
public sealed class Point3
{
    internal Point3(double x, double y, double z)
    {
        X = x;
        Y = y;
        Z = z;
    }

    public double X { get; }

    public double Y { get; }

    public double Z { get; }
}
