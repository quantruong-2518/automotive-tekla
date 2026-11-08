using System;
using TeklaHarness.Core.Json;

namespace TeklaHarness.Core;

/// <summary>
/// A validation receipt (schema <c>urn:tekla-harness:schema:spec-receipt:0.1</c>, ADR-0010
/// Amendment 1 §3), checked field by field: exactly the schema's fields and types. Whether it
/// matches the spec bytes, schema id and minimum rules version is decided by <see cref="SpecLoader"/>.
/// </summary>
internal sealed class SpecReceipt
{
    private static readonly string[] TopLevelFields =
        { "schema_version", "spec_file", "spec_sha256", "spec_schema_id", "validator", "validated_at" };

    private static readonly string[] ValidatorFields = { "name", "version", "rules_version" };

    private SpecReceipt(string specSha256, string specSchemaId, long rulesVersion)
    {
        SpecSha256 = specSha256;
        SpecSchemaId = specSchemaId;
        RulesVersion = rulesVersion;
    }

    public string SpecSha256 { get; }

    public string SpecSchemaId { get; }

    public long RulesVersion { get; }

    /// <summary>Checks the receipt's shape. Throws <see cref="SpecRefusedException"/> (ReceiptInvalid) on any deviation.</summary>
    public static SpecReceipt Read(JsonValue root)
    {
        var receipt = AsObject(root, "receipt");
        CheckFields(receipt, TopLevelFields, string.Empty);

        if (StringField(receipt, "schema_version") != "0.1")
        {
            throw Invalid("schema_version must be \"0.1\"");
        }

        var specFile = StringField(receipt, "spec_file");
        if (specFile.Length == 0 || specFile.IndexOf('/') >= 0 || specFile.IndexOf('\\') >= 0)
        {
            throw Invalid("spec_file must be a non-empty base name");
        }

        var sha = StringField(receipt, "spec_sha256");
        if (sha.Length != 64 || !AllChars(sha, IsLowerHex))
        {
            throw Invalid("spec_sha256 must be 64 lowercase hexadecimal characters");
        }

        var schemaId = StringField(receipt, "spec_schema_id");

        receipt.TryGet("validator", out var validatorValue);
        var validator = AsObject(validatorValue!, "validator");
        CheckFields(validator, ValidatorFields, "validator.");
        if (StringField(validator, "name", "validator.") != "tekla_harness")
        {
            throw Invalid("validator.name must be \"tekla_harness\"");
        }

        if (StringField(validator, "version", "validator.").Length == 0)
        {
            throw Invalid("validator.version must be a non-empty string");
        }

        validator.TryGet("rules_version", out var rules);
        var number = rules as JsonNumber;
        if (number is null || !number.IsInteger || number.Value > 1000000)
        {
            throw Invalid("validator.rules_version must be an integer of at most 1000000");
        }

        if (!IsTimestamp(StringField(receipt, "validated_at")))
        {
            throw Invalid("validated_at must look like 2026-11-07T09:00:00Z");
        }

        return new SpecReceipt(sha, schemaId, (long)number.Value);
    }

    private static SpecRefusedException Invalid(string detail)
        => new(SpecRefusal.ReceiptInvalid, "Receipt is not valid: " + detail + ".");

    private static JsonObject AsObject(JsonValue value, string what)
        => value as JsonObject ?? throw Invalid(what + " must be an object");

    /// <summary>Unknown field or missing field: both refuse.</summary>
    private static void CheckFields(JsonObject obj, string[] expected, string prefix)
    {
        foreach (var member in obj.Members)
        {
            if (Array.IndexOf(expected, member.Key) < 0)
            {
                throw Invalid("unknown field '" + prefix + member.Key + "'");
            }
        }

        foreach (var field in expected)
        {
            if (!obj.TryGet(field, out _))
            {
                throw Invalid("missing field '" + prefix + field + "'");
            }
        }
    }

    private static string StringField(JsonObject obj, string field, string prefix = "")
    {
        obj.TryGet(field, out var value);
        return (value as JsonString)?.Value ?? throw Invalid(prefix + field + " must be a string");
    }

    private static bool AllChars(string s, Func<char, bool> predicate)
    {
        foreach (var c in s)
        {
            if (!predicate(c))
            {
                return false;
            }
        }

        return true;
    }

    private static bool IsLowerHex(char c) => c is (>= '0' and <= '9') or (>= 'a' and <= 'f');

    private static bool IsAsciiDigit(char c) => c is >= '0' and <= '9';

    /// <summary>Exactly <c>[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z</c>, ASCII digits only.</summary>
    private static bool IsTimestamp(string s)
    {
        const string Shape = "dddd-dd-ddTdd:dd:ddZ";
        if (s.Length != Shape.Length)
        {
            return false;
        }

        for (var i = 0; i < Shape.Length; i++)
        {
            if (Shape[i] == 'd' ? !IsAsciiDigit(s[i]) : s[i] != Shape[i])
            {
                return false;
            }
        }

        return true;
    }
}

/// <summary>Internal control flow of <see cref="SpecLoader"/>: a refusal with its reason.</summary>
internal sealed class SpecRefusedException : Exception
{
    public SpecRefusedException(SpecRefusal refusal, string detail)
        : base(detail) => Refusal = refusal;

    public SpecRefusal Refusal { get; }
}
