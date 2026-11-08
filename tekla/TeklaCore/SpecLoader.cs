using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Security;
using System.Security.Cryptography;
using TeklaHarness.Core.Json;

namespace TeklaHarness.Core;

/// <summary>Why the spec loader refused a spec (contract safety rule 3, ADR-0010).</summary>
public enum SpecRefusal
{
    None,

    /// <summary>No spec path, or path text the OS rejects (exit 2).</summary>
    BadArgument,

    /// <summary>I/O error reading an existing spec or receipt: access denied, sharing violation (exit 3).</summary>
    ReadError,

    SpecMissing,
    ReceiptMissing,

    /// <summary>The spec file is over 16 MiB; refused while reading, before parsing.</summary>
    SpecTooLarge,

    /// <summary>The receipt is too large, not strict JSON, or not exactly the receipt schema's fields and types.</summary>
    ReceiptInvalid,

    /// <summary>The receipt's spec_schema_id is not one this CLI was built for.</summary>
    UnknownSpecSchema,

    /// <summary>The receipt's rules_version is below <see cref="SpecLoader.MinimumRulesVersion"/>.</summary>
    RulesVersionTooOld,

    /// <summary>The spec bytes are not the bytes the receipt vouches for.</summary>
    HashMismatch,

    /// <summary>The spec is not strict JSON (ADR-0010 Amendment 1 §1), even though its receipt matches.</summary>
    SpecRejectedByReader,

    SchemaVersionMismatch,

    /// <summary>Top level, project_id or members unusable.</summary>
    SpecMalformed,

    UnitsNotMillimetres,

    /// <summary>lot is not an integer token from 1 to 2147483647.</summary>
    LotInvalid,

    LotMismatch,
    MemberInvalid,
    DuplicateSpecId,
}

/// <summary>Result of <see cref="SpecLoader.Load"/>.</summary>
public sealed class SpecLoadResult
{
    internal SpecLoadResult(SpecRefusal refusal, string detail, LotSpec? spec)
    {
        Refusal = refusal;
        Detail = detail;
        Spec = spec;
    }

    public bool Loaded => Refusal == SpecRefusal.None;

    public SpecRefusal Refusal { get; }

    /// <summary>Human-readable reason, for the JSON output and the engineer.</summary>
    public string Detail { get; }

    /// <summary>The spec when <see cref="Loaded"/>; otherwise null.</summary>
    public LotSpec? Spec { get; }

    /// <summary>ADR-0010 Amendment 1 §6: bad arguments 2, I/O error on an existing file 3, every other refusal 5.</summary>
    public ExitCode ExitCode => Refusal switch
    {
        SpecRefusal.None => ExitCode.Ok,
        SpecRefusal.BadArgument => ExitCode.UsageError,
        SpecRefusal.ReadError => ExitCode.EnvironmentError,
        _ => ExitCode.RefusedBySafetyRule,
    };
}

/// <summary>
/// Loads a lot spec for a write command (contract safety rule 3, ADR-0010 and its Amendment 1).
/// Refuses unless <c>&lt;spec&gt;.receipt.json</c> proves these exact bytes were validated by the
/// Python validator, then applies the CLI's own read-time checks. The spec is read once; that one
/// buffer is hashed and parsed.
/// </summary>
public static class SpecLoader
{
    public const string ReceiptSuffix = ".receipt.json";

    /// <summary>Oldest receipt <c>validator.rules_version</c> this CLI accepts (ADR-0010 Amendment 1 §4).</summary>
    public const int MinimumRulesVersion = 1;

    private const string SpecSchemaIdPrefix = "urn:tekla-harness:schema:spec:";

    private const string HexDigits = "0123456789abcdef";

    /// <summary>Spec schema <c>$id</c>s this CLI was built for.</summary>
    private static readonly string[] AcceptedSpecSchemaIds = { SpecSchemaIdPrefix + "0.1" };

    public static SpecLoadResult Load(string? specPath, int expectedLot)
    {
        if (string.IsNullOrEmpty(specPath))
        {
            return new SpecLoadResult(SpecRefusal.BadArgument, "No spec path given.", null);
        }

        try
        {
            var receiptPath = specPath + ReceiptSuffix;
            var specBytes = ReadCapped(specPath!, "Spec", SpecRefusal.SpecMissing, SpecRefusal.SpecTooLarge, SpecRefusal.BadArgument);
            var sha = Sha256Hex(specBytes);
            var receiptBytes = ReadCapped(receiptPath, "Receipt", SpecRefusal.ReceiptMissing, SpecRefusal.ReceiptInvalid, SpecRefusal.ReadError);
            if (!StrictJson.TryParse(receiptBytes, out var receiptJson, out var error))
            {
                throw new SpecRefusedException(SpecRefusal.ReceiptInvalid, "Receipt '" + receiptPath + "' is not strict JSON: " + error + ".");
            }

            var receipt = SpecReceipt.Read(receiptJson!);
            if (Array.IndexOf(AcceptedSpecSchemaIds, receipt.SpecSchemaId) < 0)
            {
                throw new SpecRefusedException(
                    SpecRefusal.UnknownSpecSchema,
                    "Receipt spec_schema_id '" + receipt.SpecSchemaId + "' is not one this CLI accepts (" + string.Join(", ", AcceptedSpecSchemaIds) + ").");
            }

            if (receipt.RulesVersion < MinimumRulesVersion)
            {
                throw new SpecRefusedException(
                    SpecRefusal.RulesVersionTooOld,
                    "Receipt validator.rules_version " + receipt.RulesVersion.ToString(CultureInfo.InvariantCulture)
                    + " is older than the minimum " + MinimumRulesVersion.ToString(CultureInfo.InvariantCulture) + ": validate the spec again.");
            }

            if (!string.Equals(receipt.SpecSha256, sha, StringComparison.Ordinal))
            {
                throw new SpecRefusedException(
                    SpecRefusal.HashMismatch,
                    "Spec bytes changed since validation: receipt spec_sha256 " + receipt.SpecSha256 + ", file " + sha + ".");
            }

            if (!StrictJson.TryParse(specBytes, out var specJson, out error))
            {
                throw new SpecRefusedException(SpecRefusal.SpecRejectedByReader, "Spec '" + specPath + "' is not strict JSON: " + error + ".");
            }

            var spec = ReadSpec(specJson!, receipt, expectedLot, sha);
            return new SpecLoadResult(
                SpecRefusal.None,
                "Spec '" + specPath + "' loaded: lot " + spec.Lot.ToString(CultureInfo.InvariantCulture) + ", "
                + spec.Members.Count.ToString(CultureInfo.InvariantCulture) + " member(s).",
                spec);
        }
        catch (SpecRefusedException e)
        {
            return new SpecLoadResult(e.Refusal, e.Message, null);
        }
    }

    /// <summary>
    /// Reads a whole file, refusing as soon as more than 16 MiB has arrived. Path text the OS
    /// rejects maps to <paramref name="badPath"/>: a usage error for the spec path the engineer
    /// gave, an environment error for the receipt path (the spec path itself was fine).
    /// </summary>
    private static byte[] ReadCapped(string path, string what, SpecRefusal missing, SpecRefusal tooLarge, SpecRefusal badPath)
    {
        try
        {
            using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read);
            using var buffer = new MemoryStream();
            var chunk = new byte[81920];
            int read;
            while ((read = stream.Read(chunk, 0, chunk.Length)) > 0)
            {
                buffer.Write(chunk, 0, read);
                if (buffer.Length > StrictJson.MaxInputBytes)
                {
                    throw new SpecRefusedException(tooLarge, what + " '" + path + "' is larger than 16 MiB.");
                }
            }

            return buffer.ToArray();
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException or ArgumentException or NotSupportedException or SecurityException)
        {
            var refusal = e switch
            {
                FileNotFoundException or DirectoryNotFoundException => missing,
                PathTooLongException or ArgumentException or NotSupportedException => badPath,
                _ => SpecRefusal.ReadError,
            };
            throw new SpecRefusedException(refusal, what + " '" + path + "' cannot be read: " + e.Message);
        }
    }

    private static string Sha256Hex(byte[] bytes)
    {
        using var sha = SHA256.Create();
        var digest = sha.ComputeHash(bytes);
        var hex = new char[digest.Length * 2];
        for (var i = 0; i < digest.Length; i++)
        {
            hex[2 * i] = HexDigits[digest[i] / 16];
            hex[(2 * i) + 1] = HexDigits[digest[i] % 16];
        }

        return new string(hex);
    }

    // ---- read-time checks (ADR-0010 decision 3 and Amendment 1 §7)

    private static LotSpec ReadSpec(JsonValue root, SpecReceipt receipt, int expectedLot, string sha)
    {
        var spec = root as JsonObject;
        if (spec is null)
        {
            throw Refused(SpecRefusal.SpecMalformed, "Spec must be a JSON object.");
        }

        var schemaVersion = (Get(spec, "schema_version") as JsonString)?.Value;
        if (schemaVersion is null || !string.Equals(SpecSchemaIdPrefix + schemaVersion, receipt.SpecSchemaId, StringComparison.Ordinal))
        {
            throw Refused(
                SpecRefusal.SchemaVersionMismatch,
                "Spec schema_version " + (schemaVersion is null ? "(missing or not a string)" : "\"" + schemaVersion + "\"")
                + " does not match the receipt's spec_schema_id '" + receipt.SpecSchemaId + "'.");
        }

        if ((Get(spec, "units") as JsonString)?.Value != "mm")
        {
            throw Refused(SpecRefusal.UnitsNotMillimetres, "Spec units must be \"mm\".");
        }

        var lotNumber = Get(spec, "lot") as JsonNumber;
        if (lotNumber is null || !lotNumber.IsInteger || lotNumber.Value < 1 || lotNumber.Value > int.MaxValue)
        {
            throw Refused(SpecRefusal.LotInvalid, "Spec lot must be an integer token from 1 to 2147483647.");
        }

        var lot = (int)lotNumber.Value;
        if (lot != expectedLot)
        {
            throw Refused(
                SpecRefusal.LotMismatch,
                "Spec lot " + lot.ToString(CultureInfo.InvariantCulture) + " is not the requested --lot " + expectedLot.ToString(CultureInfo.InvariantCulture) + ".");
        }

        var projectId = RequiredString(spec, "project_id", SpecRefusal.SpecMalformed);
        var members = Get(spec, "members") as JsonArray;
        if (members is null || members.Items.Count == 0)
        {
            throw Refused(SpecRefusal.SpecMalformed, "Spec members must be a non-empty array.");
        }

        var seen = new HashSet<string>(StringComparer.Ordinal);
        var list = new List<MemberSpec>(members.Items.Count);
        for (var i = 0; i < members.Items.Count; i++)
        {
            list.Add(ReadMember(members.Items[i], "members[" + i.ToString(CultureInfo.InvariantCulture) + "]", seen));
        }

        return new LotSpec(schemaVersion, projectId, lot, list, sha, (int)receipt.RulesVersion);
    }

    private static MemberSpec ReadMember(JsonValue value, string path, HashSet<string> seen)
    {
        var member = value as JsonObject;
        if (member is null)
        {
            throw Refused(SpecRefusal.MemberInvalid, "Spec field '" + path + "' must be an object.");
        }

        var specId = RequiredString(member, path + ".spec_id", SpecRefusal.MemberInvalid);
        if (!IsSpecId(specId))
        {
            throw Refused(SpecRefusal.MemberInvalid, "Spec field '" + path + ".spec_id' must match ^[A-Z0-9][A-Z0-9_-]{0,63}$.");
        }

        if (!seen.Add(specId))
        {
            throw Refused(SpecRefusal.DuplicateSpecId, "Spec field '" + path + ".spec_id' repeats spec_id \"" + specId + "\".");
        }

        var type = (Get(member, "type") as JsonString)?.Value ?? throw MemberField(path + ".type", "must be a string");
        var profile = RequiredString(Object(member, path, "profile"), path + ".profile.value", SpecRefusal.MemberInvalid);
        var material = RequiredString(Object(member, path, "material"), path + ".material.value", SpecRefusal.MemberInvalid);
        var start = Point(member, path, "start");
        var end = Point(member, path, "end");

        double? rotation = null;
        if (member.TryGet("rotation_deg", out _))
        {
            rotation = Number(Object(member, path, "rotation_deg"), path + ".rotation_deg", "value");
        }

        return new MemberSpec(
            specId,
            type,
            profile,
            material,
            start,
            end,
            rotation,
            OptionalString(member, path, "name"),
            OptionalString(member, path, "mark"),
            OptionalString(member, path, "class"));
    }

    /// <summary>Exactly <c>^[A-Z0-9][A-Z0-9_-]{0,63}$</c> (common schema), ASCII only; no trailing newline.</summary>
    private static bool IsSpecId(string s)
    {
        if (s.Length > 64 || !IsUpperOrDigit(s[0]))
        {
            return false;
        }

        foreach (var c in s)
        {
            if (!IsUpperOrDigit(c) && c != '_' && c != '-')
            {
                return false;
            }
        }

        return true;
    }

    private static bool IsUpperOrDigit(char c) => c is (>= 'A' and <= 'Z') or (>= '0' and <= '9');

    private static Point3 Point(JsonObject member, string path, string key)
    {
        var point = Object(member, path, key);
        var at = path + "." + key;
        return new Point3(Number(point, at, "x"), Number(point, at, "y"), Number(point, at, "z"));
    }

    private static JsonObject Object(JsonObject parent, string path, string key)
        => Get(parent, key) as JsonObject ?? throw MemberField(path + "." + key, "must be an object");

    private static double Number(JsonObject parent, string path, string key)
        => (Get(parent, key) as JsonNumber)?.Value ?? throw MemberField(path + "." + key, "must be a number");

    private static string? OptionalString(JsonObject member, string path, string key)
    {
        if (!member.TryGet(key, out var value))
        {
            return null;
        }

        return (value as JsonString)?.Value ?? throw MemberField(path + "." + key, "must be a string");
    }

    /// <summary>A non-empty string; <paramref name="path"/> is the full field path, its last segment the key.</summary>
    private static string RequiredString(JsonObject parent, string path, SpecRefusal refusal)
    {
        var key = path.Substring(path.LastIndexOf('.') + 1);
        var value = (Get(parent, key) as JsonString)?.Value;
        if (string.IsNullOrEmpty(value))
        {
            throw Refused(refusal, "Spec field '" + path + "' must be a non-empty string.");
        }

        return value!;
    }

    private static JsonValue? Get(JsonObject obj, string key)
    {
        obj.TryGet(key, out var value);
        return value;
    }

    private static SpecRefusedException MemberField(string path, string problem)
        => Refused(SpecRefusal.MemberInvalid, "Spec field '" + path + "' " + problem + ".");

    private static SpecRefusedException Refused(SpecRefusal refusal, string detail) => new(refusal, detail);
}
