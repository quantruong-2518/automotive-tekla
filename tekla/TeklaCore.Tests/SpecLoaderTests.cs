using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using TeklaHarness.Core.Json;
using Xunit;

namespace TeklaHarness.Core.Tests;

/// <summary>
/// Contract safety rule 3 and ADR-0010 (Amendment 1). The dangerous direction is a false
/// "loaded": building from bytes Python did not validate, or from values the CLI reads
/// differently.
/// </summary>
public sealed class SpecLoaderTests : IDisposable
{
    private const string SchemaId = "urn:tekla-harness:schema:spec:0.1";

    private const string Member1 =
        "{\"spec_id\":\"M1\",\"type\":\"beam\",\"profile\":{\"value\":\"IPE300\"},\"material\":{\"value\":\"S355JR\"},"
        + "\"start\":{\"x\":0,\"y\":-1.5,\"z\":3000},\"end\":{\"x\":6000,\"y\":0.25,\"z\":3000}}";

    private const string Member2 =
        "{\"spec_id\":\"M2\",\"type\":\"column\",\"profile\":{\"value\":\"HEA300\"},\"material\":{\"value\":\"S275\"},"
        + "\"start\":{\"x\":10,\"y\":20,\"z\":30},\"end\":{\"x\":10,\"y\":20,\"z\":3030}}";

    private const string Members = "\"members\":[" + Member1 + "," + Member2 + "]";

    private const string BaseSpec =
        "{\"schema_version\":\"0.1\",\"project_id\":\"p1\",\"lot\":1,\"units\":\"mm\",\"open_questions\":[]," + Members + "}";

    private const string Validator = "\"validator\":{\"name\":\"tekla_harness\",\"version\":\"0.1.0\",\"rules_version\":1}";

    private const string ReceiptTemplate =
        "{\"schema_version\":\"0.1\",\"spec_file\":\"spec.json\",\"spec_sha256\":\"{SHA}\",\"spec_schema_id\":\"" + SchemaId + "\","
        + Validator + ",\"validated_at\":\"2026-11-07T09:00:00Z\"}";

    private readonly string _dir;

    public SpecLoaderTests()
    {
        _dir = Path.Combine(Path.GetTempPath(), "teklacore-s1b-" + Guid.NewGuid().ToString("N", CultureInfo.InvariantCulture));
        Directory.CreateDirectory(_dir);
    }

    private string SpecPath => Path.Combine(_dir, "spec.json");

    private string ReceiptPath => SpecPath + ".receipt.json";

    public void Dispose() => Directory.Delete(_dir, recursive: true);

    // ---- helpers

    private static string Sha256Hex(byte[] bytes)
    {
        using var sha = SHA256.Create();
        return string.Concat(sha.ComputeHash(bytes).Select(b => b.ToString("x2", CultureInfo.InvariantCulture)));
    }

    /// <summary>Replaces the single occurrence of <paramref name="oldValue"/> (ordinal).</summary>
    private static string Swap(string text, string oldValue, string newValue)
    {
        var at = text.IndexOf(oldValue, StringComparison.Ordinal);
        Assert.True(at >= 0, "fragment not found: " + oldValue);
        Assert.Equal(at, text.LastIndexOf(oldValue, StringComparison.Ordinal));
        return text.Substring(0, at) + newValue + text.Substring(at + oldValue.Length);
    }

    private static string ReceiptFor(byte[] spec, string template = ReceiptTemplate)
        => template.IndexOf("{SHA}", StringComparison.Ordinal) < 0 ? template : Swap(template, "{SHA}", Sha256Hex(spec));

    private void Write(byte[] spec, string? receipt)
    {
        File.WriteAllBytes(SpecPath, spec);
        if (receipt is not null)
        {
            File.WriteAllBytes(ReceiptPath, Encoding.UTF8.GetBytes(receipt));
        }
    }

    /// <summary>Writes the spec and a receipt that matches its bytes, then loads it.</summary>
    private SpecLoadResult LoadValidated(string spec, int lot = 1, string receiptTemplate = ReceiptTemplate)
    {
        var bytes = Encoding.UTF8.GetBytes(spec);
        Write(bytes, ReceiptFor(bytes, receiptTemplate));
        return SpecLoader.Load(SpecPath, lot);
    }

    private static void AssertLoaded(SpecLoadResult result)
    {
        Assert.True(result.Loaded, result.Detail);
        Assert.Equal(SpecRefusal.None, result.Refusal);
        Assert.Equal(ExitCode.Ok, result.ExitCode);
        Assert.NotNull(result.Spec);
        Assert.False(string.IsNullOrEmpty(result.Detail));
    }

    private static void AssertRefused(SpecLoadResult result, SpecRefusal refusal, string? detailFragment = null, ExitCode exit = ExitCode.RefusedBySafetyRule)
    {
        Assert.False(result.Loaded);
        Assert.Equal(refusal, result.Refusal);
        Assert.Equal(exit, result.ExitCode);
        Assert.Null(result.Spec);
        Assert.False(string.IsNullOrEmpty(result.Detail));
        if (detailFragment is not null)
        {
            Assert.Contains(detailFragment, result.Detail, StringComparison.Ordinal);
        }
    }

    // ---- cross-language anchor: the committed receipt was written by the Python validator

    [Fact]
    public void Python_receipt_example_hashes_the_spec_example_bytes()
    {
        var spec = File.ReadAllBytes(RepoPaths.SchemaExample("spec.example.json"));
        Assert.True(StrictJson.TryParse(File.ReadAllBytes(RepoPaths.SchemaExample("spec-receipt.example.json")), out var receipt, out var error), error);
        Assert.True(((JsonObject)receipt!).TryGet("spec_sha256", out var sha));
        Assert.Equal(Sha256Hex(spec), ((JsonString)sha!).Value);
    }

    [Fact]
    public void Loads_the_schema_example_with_its_python_receipt()
    {
        File.Copy(RepoPaths.SchemaExample("spec.example.json"), SpecPath);
        File.Copy(RepoPaths.SchemaExample("spec-receipt.example.json"), ReceiptPath);

        var result = SpecLoader.Load(SpecPath, 1);

        AssertLoaded(result);
        var spec = result.Spec!;
        Assert.Equal("0.1", spec.SchemaVersion);
        Assert.Equal("demo-warehouse", spec.ProjectId);
        Assert.Equal(1, spec.Lot);
        Assert.Equal(1, spec.RulesVersion);
        Assert.Equal("77a1243091e09d63325185ae2a70896726c355f20f78564b57b9429023b91713", spec.SpecSha256);
        Assert.Equal(new[] { "L1-C-A1", "L1-C-A2", "L1-B-A12" }, spec.Members.Select(m => m.SpecId));

        var c = spec.Members[0];
        Assert.Equal("column", c.Type);
        Assert.Equal("HEA300", c.Profile);
        Assert.Equal("S355JR", c.Material);
        Assert.Equal("C1", c.Mark);
        Assert.Equal("3", c.Class);
        Assert.Null(c.Name);
        Assert.Null(c.RotationDeg);
        Assert.Equal((0.0, 0.0, 0.0), (c.Start.X, c.Start.Y, c.Start.Z));
        Assert.Equal((0.0, 0.0, 6000.0), (c.End.X, c.End.Y, c.End.Z));

        var b = spec.Members[2];
        Assert.Equal("beam", b.Type);
        Assert.Equal("IPE300", b.Profile);
        Assert.Equal("B1", b.Mark);
        Assert.Equal("4", b.Class);
        Assert.Equal((0.0, 0.0, 6000.0), (b.Start.X, b.Start.Y, b.Start.Z));
        Assert.Equal((6000.0, 0.0, 6000.0), (b.End.X, b.End.Y, b.End.Z));
    }

    [Fact]
    public void Loads_a_minimal_spec_with_every_value_read_as_written()
    {
        var result = LoadValidated(BaseSpec);

        AssertLoaded(result);
        var spec = result.Spec!;
        Assert.Equal("p1", spec.ProjectId);
        Assert.Equal(2, spec.Members.Count);
        var m1 = spec.Members[0];
        Assert.Equal(("M1", "beam", "IPE300", "S355JR"), (m1.SpecId, m1.Type, m1.Profile, m1.Material));
        Assert.Equal((0.0, -1.5, 3000.0), (m1.Start.X, m1.Start.Y, m1.Start.Z));
        Assert.Equal((6000.0, 0.25, 3000.0), (m1.End.X, m1.End.Y, m1.End.Z));
        Assert.Null(m1.Mark);
        Assert.Null(m1.Class);
        var m2 = spec.Members[1];
        Assert.Equal(("M2", "column", "HEA300", "S275"), (m2.SpecId, m2.Type, m2.Profile, m2.Material));
        Assert.Equal((10.0, 20.0, 30.0), (m2.Start.X, m2.Start.Y, m2.Start.Z));
        Assert.Equal((10.0, 20.0, 3030.0), (m2.End.X, m2.End.Y, m2.End.Z));
    }

    [Fact]
    public void Reads_optional_member_fields_and_ignores_unknown_spec_fields()
    {
        var spec = Swap(BaseSpec, "\"spec_id\":\"M1\",", "\"spec_id\":\"M1\",\"rotation_deg\":{\"value\":-90.5,\"confidence\":\"high\"},\"name\":\"BEAM\",\"mark\":\"B1\",\"class\":\"4\",\"future\":{\"x\":[1]},");
        spec = Swap(spec, "\"project_id\"", "\"unknown_top\":[1,2],\"project_id\"");

        var result = LoadValidated(spec);

        AssertLoaded(result);
        var m1 = result.Spec!.Members[0];
        Assert.Equal(-90.5, m1.RotationDeg);
        Assert.Equal("BEAM", m1.Name);
        Assert.Equal("B1", m1.Mark);
        Assert.Equal("4", m1.Class);
        Assert.Null(result.Spec.Members[1].RotationDeg);
    }

    // ---- spec_id: exactly ^[A-Z0-9][A-Z0-9_-]{0,63}$ (common schema), ASCII only, no trailing newline

    [Theory]
    [InlineData("0")]
    [InlineData("Z")]
    [InlineData("L1-C-A2")]
    [InlineData("A_B-9")]
    public void Accepts_spec_ids_matching_the_schema_pattern(string specId)
    {
        var result = LoadValidated(Swap(BaseSpec, "\"spec_id\":\"M2\"", "\"spec_id\":\"" + specId + "\""));
        AssertLoaded(result);
        Assert.Equal(specId, result.Spec!.Members[1].SpecId);
    }

    [Theory]
    [InlineData("L1-C-A2\\n")] // Python's '$' let this through
    [InlineData("L1-C-A2\\r")]
    [InlineData("m1")]
    [InlineData("M1a")]
    [InlineData("-M1")]
    [InlineData("_M1")]
    [InlineData("M 1")]
    [InlineData("M.1")]
    [InlineData("M/1")]
    [InlineData("M:1")]
    [InlineData("M@1")]
    [InlineData("M[1")]
    [InlineData("M`1")]
    [InlineData("M\\u0661")] // Arabic-Indic digit one
    [InlineData("\\uff2d1")] // fullwidth M
    public void Refuses_spec_ids_outside_the_schema_pattern(string specId)
        => Assert.Equal(
            "Spec field 'members[1].spec_id' must match ^[A-Z0-9][A-Z0-9_-]{0,63}$.",
            AssertRefusedDetail(LoadValidated(Swap(BaseSpec, "\"spec_id\":\"M2\"", "\"spec_id\":\"" + specId + "\"")), SpecRefusal.MemberInvalid));

    [Fact]
    public void Spec_id_length_is_1_to_64()
    {
        var longest = "A" + new string('9', 62) + "_";
        Assert.Equal(64, longest.Length);
        AssertLoaded(LoadValidated(Swap(BaseSpec, "\"spec_id\":\"M2\"", "\"spec_id\":\"" + longest + "\"")));
        AssertRefused(LoadValidated(Swap(BaseSpec, "\"spec_id\":\"M2\"", "\"spec_id\":\"" + longest + "9\"")), SpecRefusal.MemberInvalid, "members[1].spec_id");
    }

    private static string AssertRefusedDetail(SpecLoadResult result, SpecRefusal refusal)
    {
        AssertRefused(result, refusal);
        return result.Detail;
    }

    [Fact]
    public void Lot_at_int32_max_matches()
    {
        var result = LoadValidated(Swap(BaseSpec, "\"lot\":1,", "\"lot\":2147483647,"), int.MaxValue);
        AssertLoaded(result);
        Assert.Equal(int.MaxValue, result.Spec!.Lot);
    }

    [Theory]
    [InlineData("1", 1)]
    [InlineData("2", 2)]
    [InlineData("1000000", 1000000)]
    public void Accepts_rules_versions_from_the_minimum_to_the_schema_maximum(string token, int expected)
    {
        Assert.Equal(1, SpecLoader.MinimumRulesVersion);
        var result = LoadValidated(BaseSpec, receiptTemplate: Swap(ReceiptTemplate, "\"rules_version\":1", "\"rules_version\":" + token));
        AssertLoaded(result);
        Assert.Equal(expected, result.Spec!.RulesVersion);
    }

    // ---- receipt refusals

    [Fact]
    public void Refuses_without_a_receipt()
    {
        Write(Encoding.UTF8.GetBytes(BaseSpec), receipt: null);
        AssertRefused(SpecLoader.Load(SpecPath, 1), SpecRefusal.ReceiptMissing, "spec.json.receipt.json");
    }

    [Fact]
    public void Refuses_a_missing_spec()
        => AssertRefused(SpecLoader.Load(SpecPath, 1), SpecRefusal.SpecMissing, "spec.json");

    [Fact]
    public void Refuses_a_spec_in_a_missing_folder()
        => AssertRefused(SpecLoader.Load(Path.Combine(_dir, "nope", "spec.json"), 1), SpecRefusal.SpecMissing);

    [Fact]
    public void Receipt_name_is_the_spec_name_plus_suffix()
    {
        Assert.Equal(".receipt.json", SpecLoader.ReceiptSuffix);
        var bytes = Encoding.UTF8.GetBytes(BaseSpec);
        var path = Path.Combine(_dir, "lot-01.spec.json");
        File.WriteAllBytes(path, bytes);
        File.WriteAllBytes(path + ".receipt.json", Encoding.UTF8.GetBytes(ReceiptFor(bytes)));
        AssertLoaded(SpecLoader.Load(path, 1));

        // A receipt beside a different spec name does not count.
        AssertRefused(SpecLoader.Load(SpecPath, 1), SpecRefusal.SpecMissing);
        File.WriteAllBytes(SpecPath, bytes);
        AssertRefused(SpecLoader.Load(SpecPath, 1), SpecRefusal.ReceiptMissing);
    }

    [Fact]
    public void Refuses_when_one_byte_of_the_spec_changed_after_validation()
    {
        var bytes = Encoding.UTF8.GetBytes(BaseSpec);
        Write(Encoding.UTF8.GetBytes(BaseSpec + " "), ReceiptFor(bytes));
        AssertRefused(SpecLoader.Load(SpecPath, 1), SpecRefusal.HashMismatch, Sha256Hex(bytes));
    }

    [Fact]
    public void Refuses_a_spec_that_differs_only_by_line_endings()
    {
        var lf = Encoding.UTF8.GetBytes("{\n" + BaseSpec.Substring(1));
        Write(Encoding.UTF8.GetBytes("{\r\n" + BaseSpec.Substring(1)), ReceiptFor(lf));
        AssertRefused(SpecLoader.Load(SpecPath, 1), SpecRefusal.HashMismatch);
    }

    [Fact]
    public void Refuses_an_uppercase_hash()
    {
        var bytes = Encoding.UTF8.GetBytes(BaseSpec);
        Write(bytes, Swap(ReceiptTemplate, "{SHA}", Sha256Hex(bytes).ToUpperInvariant()));
        AssertRefused(SpecLoader.Load(SpecPath, 1), SpecRefusal.ReceiptInvalid, "spec_sha256");
    }

    [Theory]
    [InlineData(0, 63)] // too short
    [InlineData(0, 65)] // too long (padded with '0')
    [InlineData(1, 64)] // one non-hex character
    [InlineData(2, 64)] // one hex letter beyond 'f'
    public void Refuses_a_hash_that_is_not_64_lowercase_hex(int variant, int length)
    {
        var bytes = Encoding.UTF8.GetBytes(BaseSpec);
        var sha = Sha256Hex(bytes);
        sha = variant switch
        {
            1 => sha.Substring(0, 63) + "-",
            2 => sha.Substring(0, 63) + "g",
            _ => length < 64 ? sha.Substring(0, length) : sha + "0",
        };
        Write(bytes, Swap(ReceiptTemplate, "{SHA}", sha));
        AssertRefused(SpecLoader.Load(SpecPath, 1), SpecRefusal.ReceiptInvalid, "spec_sha256");
    }

    [Theory]
    // missing fields
    [InlineData("\"schema_version\":\"0.1\",", "", SpecRefusal.ReceiptInvalid, "schema_version")]
    [InlineData("\"spec_file\":\"spec.json\",", "", SpecRefusal.ReceiptInvalid, "spec_file")]
    [InlineData("\"spec_sha256\":\"{SHA}\",", "", SpecRefusal.ReceiptInvalid, "spec_sha256")]
    [InlineData("\"spec_schema_id\":\"" + SchemaId + "\",", "", SpecRefusal.ReceiptInvalid, "spec_schema_id")]
    [InlineData(Validator + ",", "", SpecRefusal.ReceiptInvalid, "validator")]
    [InlineData(",\"validated_at\":\"2026-11-07T09:00:00Z\"", "", SpecRefusal.ReceiptInvalid, "validated_at")]
    [InlineData("\"name\":\"tekla_harness\",", "", SpecRefusal.ReceiptInvalid, "validator.name")]
    [InlineData("\"version\":\"0.1.0\",", "", SpecRefusal.ReceiptInvalid, "validator.version")]
    [InlineData(",\"rules_version\":1", "", SpecRefusal.ReceiptInvalid, "validator.rules_version")]
    // unknown fields
    [InlineData("\"validated_at\"", "\"note\":\"x\",\"validated_at\"", SpecRefusal.ReceiptInvalid, "note")]
    [InlineData("\"rules_version\":1", "\"rules_version\":1,\"extra\":true", SpecRefusal.ReceiptInvalid, "validator.extra")]
    [InlineData("\"spec_file\":", "\"Spec_file\":\"x\",\"spec_file\":", SpecRefusal.ReceiptInvalid, "Spec_file")]
    // values and types
    [InlineData("\"schema_version\":\"0.1\"", "\"schema_version\":\"0.2\"", SpecRefusal.ReceiptInvalid, "schema_version")]
    [InlineData("\"schema_version\":\"0.1\"", "\"schema_version\":0.1", SpecRefusal.ReceiptInvalid, "schema_version")]
    [InlineData("\"spec_file\":\"spec.json\"", "\"spec_file\":\"\"", SpecRefusal.ReceiptInvalid, "spec_file")]
    [InlineData("\"spec_file\":\"spec.json\"", "\"spec_file\":\"a/spec.json\"", SpecRefusal.ReceiptInvalid, "spec_file")]
    [InlineData("\"spec_file\":\"spec.json\"", "\"spec_file\":\"a\\\\spec.json\"", SpecRefusal.ReceiptInvalid, "spec_file")]
    [InlineData("\"spec_file\":\"spec.json\"", "\"spec_file\":\"/spec.json\"", SpecRefusal.ReceiptInvalid, "spec_file")]
    [InlineData("\"spec_file\":\"spec.json\"", "\"spec_file\":\"\\\\spec.json\"", SpecRefusal.ReceiptInvalid, "spec_file")]
    [InlineData("\"spec_file\":\"spec.json\"", "\"spec_file\":1", SpecRefusal.ReceiptInvalid, "spec_file")]
    [InlineData("\"spec_sha256\":\"{SHA}\"", "\"spec_sha256\":1", SpecRefusal.ReceiptInvalid, "spec_sha256")]
    [InlineData("\"spec_schema_id\":\"" + SchemaId + "\"", "\"spec_schema_id\":1", SpecRefusal.ReceiptInvalid, "spec_schema_id")]
    [InlineData(Validator, "\"validator\":\"tekla_harness\"", SpecRefusal.ReceiptInvalid, "validator")]
    [InlineData(Validator, "\"validator\":null", SpecRefusal.ReceiptInvalid, "validator")]
    [InlineData("\"name\":\"tekla_harness\"", "\"name\":\"other\"", SpecRefusal.ReceiptInvalid, "validator.name")]
    [InlineData("\"name\":\"tekla_harness\"", "\"name\":\"Tekla_harness\"", SpecRefusal.ReceiptInvalid, "validator.name")]
    [InlineData("\"name\":\"tekla_harness\"", "\"name\":1", SpecRefusal.ReceiptInvalid, "validator.name")]
    [InlineData("\"version\":\"0.1.0\"", "\"version\":\"\"", SpecRefusal.ReceiptInvalid, "validator.version")]
    [InlineData("\"version\":\"0.1.0\"", "\"version\":1", SpecRefusal.ReceiptInvalid, "validator.version")]
    [InlineData("\"rules_version\":1", "\"rules_version\":1.5", SpecRefusal.ReceiptInvalid, "rules_version")]
    [InlineData("\"rules_version\":1", "\"rules_version\":1.0", SpecRefusal.ReceiptInvalid, "rules_version")]
    [InlineData("\"rules_version\":1", "\"rules_version\":1e0", SpecRefusal.ReceiptInvalid, "rules_version")]
    [InlineData("\"rules_version\":1", "\"rules_version\":\"1\"", SpecRefusal.ReceiptInvalid, "rules_version")]
    [InlineData("\"rules_version\":1", "\"rules_version\":null", SpecRefusal.ReceiptInvalid, "rules_version")]
    [InlineData("\"rules_version\":1", "\"rules_version\":1000001", SpecRefusal.ReceiptInvalid, "rules_version")]
    [InlineData("\"rules_version\":1", "\"rules_version\":9007199254740992", SpecRefusal.ReceiptInvalid, "rules_version")]
    [InlineData("\"rules_version\":1", "\"rules_version\":0", SpecRefusal.RulesVersionTooOld, "rules_version")]
    [InlineData("\"rules_version\":1", "\"rules_version\":-1", SpecRefusal.RulesVersionTooOld, "rules_version")]
    [InlineData("\"rules_version\":1", "\"rules_version\":-9007199254740992", SpecRefusal.RulesVersionTooOld, "rules_version")]
    [InlineData("2026-11-07T09:00:00Z", "2026-11-07T09:00:00", SpecRefusal.ReceiptInvalid, "validated_at")]
    [InlineData("2026-11-07T09:00:00Z", "2026-11-07 09:00:00Z", SpecRefusal.ReceiptInvalid, "validated_at")]
    [InlineData("2026-11-07T09:00:00Z", "2026-11-07T09:00:00.5Z", SpecRefusal.ReceiptInvalid, "validated_at")]
    [InlineData("2026-11-07T09:00:00Z", "2026-11-07T09:00:00z", SpecRefusal.ReceiptInvalid, "validated_at")]
    [InlineData("2026-11-07T09:00:00Z", "2026-11-07T09:00:00Z\\n", SpecRefusal.ReceiptInvalid, "validated_at")]
    [InlineData("2026-11-07T09:00:00Z", "2026-11-07T09:00:0Z", SpecRefusal.ReceiptInvalid, "validated_at")]
    [InlineData("2026-11-07T09:00:00Z", "2026-11-07T09:00:0aZ", SpecRefusal.ReceiptInvalid, "validated_at")]
    [InlineData("2026-11-07T09:00:00Z", "2026-11-07T09:00:0/Z", SpecRefusal.ReceiptInvalid, "validated_at")]
    [InlineData("2026-11-07T09:00:00Z", "2026-11-07T09:00:0:Z", SpecRefusal.ReceiptInvalid, "validated_at")]
    [InlineData("2026-11-07T09:00:00Z", "\\u0662026-11-07T09:00:00Z", SpecRefusal.ReceiptInvalid, "validated_at")] // Arabic-Indic digit
    [InlineData("2026-11-07T09:00:00Z", "2026/11-07T09:00:00Z", SpecRefusal.ReceiptInvalid, "validated_at")]
    [InlineData("2026-11-07T09:00:00Z", "2026-11/07T09:00:00Z", SpecRefusal.ReceiptInvalid, "validated_at")]
    [InlineData("2026-11-07T09:00:00Z", "2026-11-07T09-00:00Z", SpecRefusal.ReceiptInvalid, "validated_at")]
    [InlineData("2026-11-07T09:00:00Z", "2026-11-07T09:00-00Z", SpecRefusal.ReceiptInvalid, "validated_at")]
    [InlineData("\"validated_at\":\"2026-11-07T09:00:00Z\"", "\"validated_at\":1", SpecRefusal.ReceiptInvalid, "validated_at")]
    // schema id
    [InlineData(SchemaId, "urn:tekla-harness:schema:spec:0.2", SpecRefusal.UnknownSpecSchema, "urn:tekla-harness:schema:spec:0.2")]
    [InlineData(SchemaId, "urn:tekla-harness:schema:spec-receipt:0.1", SpecRefusal.UnknownSpecSchema, "spec_schema_id")]
    [InlineData(SchemaId, "URN:tekla-harness:schema:spec:0.1", SpecRefusal.UnknownSpecSchema, "spec_schema_id")]
    // strict reader on the receipt itself
    [InlineData("\"validated_at\"", "\"spec_file\":\"spec.json\",\"validated_at\"", SpecRefusal.ReceiptInvalid, "duplicate")]
    [InlineData("\"2026-11-07T09:00:00Z\"}", "\"2026-11-07T09:00:00Z\",}", SpecRefusal.ReceiptInvalid, null)]
    public void Refuses_a_malformed_or_unacceptable_receipt(string oldValue, string newValue, SpecRefusal refusal, string? detail)
        => AssertRefused(LoadValidated(BaseSpec, receiptTemplate: Swap(ReceiptTemplate, oldValue, newValue)), refusal, detail);

    [Theory]
    [InlineData("[]")]
    [InlineData("\"receipt\"")]
    [InlineData("")]
    public void Refuses_a_receipt_that_is_not_an_object(string receipt)
    {
        Write(Encoding.UTF8.GetBytes(BaseSpec), receipt);
        AssertRefused(SpecLoader.Load(SpecPath, 1), SpecRefusal.ReceiptInvalid);
    }

    [Fact]
    public void Refuses_a_receipt_with_a_bom()
    {
        var bytes = Encoding.UTF8.GetBytes(BaseSpec);
        Write(bytes, "﻿" + ReceiptFor(bytes));
        AssertRefused(SpecLoader.Load(SpecPath, 1), SpecRefusal.ReceiptInvalid, "byte order mark");
    }

    // ---- the spec itself: strict reader, then read-time checks (receipt always matches here)

    [Fact]
    public void Refuses_a_spec_the_strict_reader_rejects_even_with_a_matching_receipt()
        => AssertRefused(LoadValidated(Swap(BaseSpec, "\"lot\":1,", "\"lot\":1,\"lot\":1,")), SpecRefusal.SpecRejectedByReader, "duplicate");

    [Theory]
    [InlineData("\"lot\":1,", "\"lot\":NaN,")]
    [InlineData("\"x\":0,\"y\":-1.5", "\"x\":1e400,\"y\":-1.5")]
    [InlineData("\"p1\"", "\"p\\u0000\"")]
    public void Refuses_spec_values_python_could_read_differently(string oldValue, string newValue)
        => AssertRefused(LoadValidated(Swap(BaseSpec, oldValue, newValue)), SpecRefusal.SpecRejectedByReader);

    [Theory]
    [InlineData("[]")]
    [InlineData("1")]
    [InlineData("\"spec\"")]
    [InlineData("null")]
    public void Refuses_a_spec_that_is_not_an_object(string spec)
        => AssertRefused(LoadValidated(spec), SpecRefusal.SpecMalformed);

    [Theory]
    // schema_version vs the receipt's spec_schema_id
    [InlineData("\"schema_version\":\"0.1\"", "\"schema_version\":\"0.2\"", SpecRefusal.SchemaVersionMismatch, "0.2")]
    [InlineData("\"schema_version\":\"0.1\"", "\"schema_version\":\"0.10\"", SpecRefusal.SchemaVersionMismatch, "schema_version")]
    [InlineData("\"schema_version\":\"0.1\"", "\"schema_version\":0.1", SpecRefusal.SchemaVersionMismatch, "schema_version")]
    [InlineData("\"schema_version\":\"0.1\",", "", SpecRefusal.SchemaVersionMismatch, "schema_version")]
    // units
    [InlineData("\"units\":\"mm\"", "\"units\":\"m\"", SpecRefusal.UnitsNotMillimetres, "units")]
    [InlineData("\"units\":\"mm\"", "\"units\":\"MM\"", SpecRefusal.UnitsNotMillimetres, "units")]
    [InlineData("\"units\":\"mm\"", "\"units\":1", SpecRefusal.UnitsNotMillimetres, "units")]
    [InlineData("\"units\":\"mm\",", "", SpecRefusal.UnitsNotMillimetres, "units")]
    // lot
    [InlineData("\"lot\":1,", "\"lot\":1.0,", SpecRefusal.LotInvalid, "lot")]
    [InlineData("\"lot\":1,", "\"lot\":1e0,", SpecRefusal.LotInvalid, "lot")]
    [InlineData("\"lot\":1,", "\"lot\":2147483648,", SpecRefusal.LotInvalid, "lot")]
    [InlineData("\"lot\":1,", "\"lot\":9007199254740992,", SpecRefusal.LotInvalid, "lot")]
    [InlineData("\"lot\":1,", "\"lot\":0,", SpecRefusal.LotInvalid, "lot")]
    [InlineData("\"lot\":1,", "\"lot\":-0,", SpecRefusal.LotInvalid, "lot")]
    [InlineData("\"lot\":1,", "\"lot\":-1,", SpecRefusal.LotInvalid, "lot")]
    [InlineData("\"lot\":1,", "\"lot\":\"1\",", SpecRefusal.LotInvalid, "lot")]
    [InlineData("\"lot\":1,", "\"lot\":null,", SpecRefusal.LotInvalid, "lot")]
    [InlineData("\"lot\":1,", "", SpecRefusal.LotInvalid, "lot")]
    [InlineData("\"lot\":1,", "\"lot\":2,", SpecRefusal.LotMismatch, "--lot 1")]
    // project_id
    [InlineData("\"project_id\":\"p1\"", "\"project_id\":\"\"", SpecRefusal.SpecMalformed, "project_id")]
    [InlineData("\"project_id\":\"p1\"", "\"project_id\":1", SpecRefusal.SpecMalformed, "project_id")]
    [InlineData("\"project_id\":\"p1\",", "", SpecRefusal.SpecMalformed, "project_id")]
    // members
    [InlineData(Members, "\"members\":[]", SpecRefusal.SpecMalformed, "members")]
    [InlineData(Members, "\"members\":{}", SpecRefusal.SpecMalformed, "members")]
    [InlineData(Members, "\"members\":null", SpecRefusal.SpecMalformed, "members")]
    [InlineData("," + Members, "", SpecRefusal.SpecMalformed, "members")]
    [InlineData("\"members\":[", "\"members\":[1,", SpecRefusal.MemberInvalid, "members[0]")]
    [InlineData("\"members\":[", "\"members\":[[],", SpecRefusal.MemberInvalid, "members[0]")]
    [InlineData("\"spec_id\":\"M2\"", "\"spec_id\":\"M1\"", SpecRefusal.DuplicateSpecId, "members[1].spec_id")]
    [InlineData("\"spec_id\":\"M1\"", "\"spec_id\":\"\"", SpecRefusal.MemberInvalid, "members[0].spec_id")]
    [InlineData("\"spec_id\":\"M1\"", "\"spec_id\":1", SpecRefusal.MemberInvalid, "members[0].spec_id")]
    [InlineData("\"spec_id\":\"M2\",", "", SpecRefusal.MemberInvalid, "members[1].spec_id")]
    [InlineData("\"type\":\"beam\"", "\"type\":1", SpecRefusal.MemberInvalid, "members[0].type")]
    [InlineData("\"type\":\"beam\",", "", SpecRefusal.MemberInvalid, "members[0].type")]
    [InlineData("{\"value\":\"IPE300\"}", "{\"val\":\"IPE300\"}", SpecRefusal.MemberInvalid, "members[0].profile.value")]
    [InlineData("{\"value\":\"IPE300\"}", "{\"value\":\"\"}", SpecRefusal.MemberInvalid, "members[0].profile.value")]
    [InlineData("{\"value\":\"IPE300\"}", "{\"value\":300}", SpecRefusal.MemberInvalid, "members[0].profile.value")]
    [InlineData("{\"value\":\"IPE300\"}", "\"IPE300\"", SpecRefusal.MemberInvalid, "members[0].profile")]
    [InlineData("\"profile\":{\"value\":\"HEA300\"},", "", SpecRefusal.MemberInvalid, "members[1].profile")]
    [InlineData("{\"value\":\"S275\"}", "{\"value\":\"\"}", SpecRefusal.MemberInvalid, "members[1].material.value")]
    [InlineData("{\"value\":\"S275\"}", "{}", SpecRefusal.MemberInvalid, "members[1].material.value")]
    [InlineData("\"material\":{\"value\":\"S355JR\"},", "", SpecRefusal.MemberInvalid, "members[0].material")]
    [InlineData("\"x\":0,\"y\":-1.5", "\"x\":\"0\",\"y\":-1.5", SpecRefusal.MemberInvalid, "members[0].start.x")]
    [InlineData("\"y\":-1.5", "\"y\":null", SpecRefusal.MemberInvalid, "members[0].start.y")]
    [InlineData("\"y\":-1.5,", "", SpecRefusal.MemberInvalid, "members[0].start.y")]
    [InlineData("\"z\":3030}", "\"z\":true}", SpecRefusal.MemberInvalid, "members[1].end.z")]
    [InlineData("\"start\":{\"x\":10,\"y\":20,\"z\":30}", "\"start\":[10,20,30]", SpecRefusal.MemberInvalid, "members[1].start")]
    [InlineData(",\"end\":{\"x\":6000,\"y\":0.25,\"z\":3000}", "", SpecRefusal.MemberInvalid, "members[0].end")]
    // optional fields with the wrong type
    [InlineData("\"spec_id\":\"M1\"", "\"spec_id\":\"M1\",\"rotation_deg\":{\"value\":\"90\"}", SpecRefusal.MemberInvalid, "members[0].rotation_deg.value")]
    [InlineData("\"spec_id\":\"M1\"", "\"spec_id\":\"M1\",\"rotation_deg\":{\"confidence\":\"high\"}", SpecRefusal.MemberInvalid, "members[0].rotation_deg.value")]
    [InlineData("\"spec_id\":\"M1\"", "\"spec_id\":\"M1\",\"rotation_deg\":90", SpecRefusal.MemberInvalid, "members[0].rotation_deg")]
    [InlineData("\"spec_id\":\"M1\"", "\"spec_id\":\"M1\",\"name\":5", SpecRefusal.MemberInvalid, "members[0].name")]
    [InlineData("\"spec_id\":\"M2\"", "\"spec_id\":\"M2\",\"mark\":null", SpecRefusal.MemberInvalid, "members[1].mark")]
    [InlineData("\"spec_id\":\"M1\"", "\"spec_id\":\"M1\",\"class\":3", SpecRefusal.MemberInvalid, "members[0].class")]
    public void Refuses_a_spec_failing_a_read_time_check(string oldValue, string newValue, SpecRefusal refusal, string detail)
        => AssertRefused(LoadValidated(Swap(BaseSpec, oldValue, newValue)), refusal, detail);

    [Theory]
    [InlineData(2)]
    [InlineData(0)]
    [InlineData(-1)]
    public void Refuses_when_the_spec_lot_is_not_the_requested_lot(int expectedLot)
        => AssertRefused(LoadValidated(BaseSpec, expectedLot), SpecRefusal.LotMismatch, "lot");

    // ---- arguments and I/O

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("a\0b")]
    public void Bad_spec_path_is_a_usage_error(string? path)
        => AssertRefused(SpecLoader.Load(path, 1), SpecRefusal.BadArgument, exit: ExitCode.UsageError);

    [Fact]
    public void A_spec_path_that_is_a_folder_is_an_environment_error()
    {
        Directory.CreateDirectory(SpecPath);
        AssertRefused(SpecLoader.Load(SpecPath, 1), SpecRefusal.ReadError, "spec.json", ExitCode.EnvironmentError);
    }

    [Fact]
    public void A_path_error_only_the_receipt_name_raises_is_an_environment_error()
    {
        // 250-character spec name is fine; its receipt name (263) exceeds the 255 limit of the file system.
        var spec = Path.Combine(_dir, new string('s', 250));
        File.WriteAllBytes(spec, Encoding.UTF8.GetBytes(BaseSpec));
        var result = SpecLoader.Load(spec, 1);
        AssertRefused(result, SpecRefusal.ReadError, null, ExitCode.EnvironmentError);
        Assert.StartsWith("Receipt '" + spec + ".receipt.json' cannot be read: ", result.Detail, StringComparison.Ordinal);
    }

    [Fact]
    public void A_receipt_path_that_is_a_folder_is_an_environment_error()
    {
        File.WriteAllBytes(SpecPath, Encoding.UTF8.GetBytes(BaseSpec));
        Directory.CreateDirectory(ReceiptPath);
        AssertRefused(SpecLoader.Load(SpecPath, 1), SpecRefusal.ReadError, "receipt", ExitCode.EnvironmentError);
    }

    // ---- size cap: 16 MiB, checked while reading, before any parsing

    [Fact]
    public void Refuses_a_spec_over_16_MiB_before_parsing_it()
    {
        // All spaces: the strict reader would say "whitespace only"; the size refusal must come first.
        File.WriteAllBytes(SpecPath, Enumerable.Repeat((byte)' ', StrictJson.MaxInputBytes + 1).ToArray());
        AssertRefused(SpecLoader.Load(SpecPath, 1), SpecRefusal.SpecTooLarge, "16 MiB");
    }

    [Fact]
    public void Loads_a_spec_of_exactly_16_MiB()
    {
        var bytes = Pad(BaseSpec, StrictJson.MaxInputBytes);
        Write(bytes, ReceiptFor(bytes));
        AssertLoaded(SpecLoader.Load(SpecPath, 1));
    }

    [Fact]
    public void Receipt_size_is_capped_too()
    {
        var bytes = Encoding.UTF8.GetBytes(BaseSpec);
        File.WriteAllBytes(SpecPath, bytes);
        File.WriteAllBytes(ReceiptPath, Pad(ReceiptFor(bytes), StrictJson.MaxInputBytes));
        AssertLoaded(SpecLoader.Load(SpecPath, 1));

        File.WriteAllBytes(ReceiptPath, Pad(ReceiptFor(bytes), StrictJson.MaxInputBytes + 1));
        AssertRefused(SpecLoader.Load(SpecPath, 1), SpecRefusal.ReceiptInvalid, "16 MiB");
    }

    private static byte[] Pad(string json, int length)
    {
        var head = Encoding.UTF8.GetBytes(json);
        var bytes = Enumerable.Repeat((byte)' ', length).ToArray();
        Array.Copy(head, bytes, head.Length);
        return bytes;
    }

    // ---- exact messages: the engineer reads them; they also pin each rule to its branch

    [Theory]
    [InlineData("\"validated_at\"", "\"note\":\"x\",\"validated_at\"", "unknown field 'note'")]
    [InlineData("\"rules_version\":1", "\"rules_version\":1,\"extra\":true", "unknown field 'validator.extra'")]
    [InlineData("\"spec_file\":\"spec.json\",", "", "missing field 'spec_file'")]
    [InlineData("\"name\":\"tekla_harness\",", "", "missing field 'validator.name'")]
    [InlineData("\"schema_version\":\"0.1\"", "\"schema_version\":\"0.2\"", "schema_version must be \"0.1\"")]
    [InlineData("\"schema_version\":\"0.1\"", "\"schema_version\":1", "schema_version must be a string")]
    [InlineData("\"spec_file\":\"spec.json\"", "\"spec_file\":1", "spec_file must be a string")]
    [InlineData("\"spec_file\":\"spec.json\"", "\"spec_file\":\"a/b\"", "spec_file must be a non-empty base name")]
    [InlineData("\"spec_sha256\":\"{SHA}\"", "\"spec_sha256\":\"abc\"", "spec_sha256 must be 64 lowercase hexadecimal characters")]
    [InlineData("\"name\":\"tekla_harness\"", "\"name\":1", "validator.name must be a string")]
    [InlineData("\"name\":\"tekla_harness\"", "\"name\":\"x\"", "validator.name must be \"tekla_harness\"")]
    [InlineData("\"version\":\"0.1.0\"", "\"version\":\"\"", "validator.version must be a non-empty string")]
    [InlineData("\"rules_version\":1", "\"rules_version\":1.5", "validator.rules_version must be an integer of at most 1000000")]
    [InlineData(Validator, "\"validator\":[]", "validator must be an object")]
    [InlineData("2026-11-07T09:00:00Z", "2026-11-07", "validated_at must look like 2026-11-07T09:00:00Z")]
    public void Receipt_shape_messages(string oldValue, string newValue, string expected)
        => Assert.Equal(
            "Receipt is not valid: " + expected + ".",
            LoadValidated(BaseSpec, receiptTemplate: Swap(ReceiptTemplate, oldValue, newValue)).Detail);

    [Fact]
    public void Receipt_messages()
    {
        Write(Encoding.UTF8.GetBytes(BaseSpec), "[]");
        Assert.Equal("Receipt is not valid: receipt must be an object.", SpecLoader.Load(SpecPath, 1).Detail);

        Write(Encoding.UTF8.GetBytes(BaseSpec), string.Empty);
        Assert.Equal("Receipt '" + ReceiptPath + "' is not strict JSON: unexpected end of input at byte 0.", SpecLoader.Load(SpecPath, 1).Detail);

        Assert.Equal(
            "Receipt spec_schema_id 'urn:tekla-harness:schema:spec:0.2' is not one this CLI accepts (urn:tekla-harness:schema:spec:0.1).",
            LoadValidated(BaseSpec, receiptTemplate: Swap(ReceiptTemplate, SchemaId, "urn:tekla-harness:schema:spec:0.2")).Detail);

        Assert.Equal(
            "Receipt validator.rules_version 0 is older than the minimum 1: validate the spec again.",
            LoadValidated(BaseSpec, receiptTemplate: Swap(ReceiptTemplate, "\"rules_version\":1", "\"rules_version\":0")).Detail);

        var bytes = Encoding.UTF8.GetBytes(BaseSpec);
        var changed = Encoding.UTF8.GetBytes(BaseSpec + " ");
        Write(changed, ReceiptFor(bytes));
        Assert.Equal(
            "Spec bytes changed since validation: receipt spec_sha256 " + Sha256Hex(bytes) + ", file " + Sha256Hex(changed) + ".",
            SpecLoader.Load(SpecPath, 1).Detail);
    }

    [Fact]
    public void File_messages()
    {
        Assert.Equal("No spec path given.", SpecLoader.Load(null, 1).Detail);
        Assert.StartsWith("Spec '" + SpecPath + "' cannot be read: ", SpecLoader.Load(SpecPath, 1).Detail, StringComparison.Ordinal);

        File.WriteAllBytes(SpecPath, Encoding.UTF8.GetBytes(BaseSpec));
        Assert.StartsWith("Receipt '" + ReceiptPath + "' cannot be read: ", SpecLoader.Load(SpecPath, 1).Detail, StringComparison.Ordinal);

        File.WriteAllBytes(ReceiptPath, Enumerable.Repeat((byte)' ', StrictJson.MaxInputBytes + 1).ToArray());
        Assert.Equal("Receipt '" + ReceiptPath + "' is larger than 16 MiB.", SpecLoader.Load(SpecPath, 1).Detail);

        File.WriteAllBytes(SpecPath, Enumerable.Repeat((byte)' ', StrictJson.MaxInputBytes + 1).ToArray());
        Assert.Equal("Spec '" + SpecPath + "' is larger than 16 MiB.", SpecLoader.Load(SpecPath, 1).Detail);
    }

    [Fact]
    public void Spec_messages()
    {
        Assert.Equal("Spec '" + SpecPath + "' loaded: lot 1, 2 member(s).", LoadValidated(BaseSpec).Detail);

        var duplicated = Swap(BaseSpec, "\"lot\":1,", "\"lot\":1,\"lot\":1,");
        var at = duplicated.LastIndexOf("\"lot\"", StringComparison.Ordinal).ToString(CultureInfo.InvariantCulture);
        Assert.Equal("Spec '" + SpecPath + "' is not strict JSON: duplicate key \"lot\" at byte " + at + ".", LoadValidated(duplicated).Detail);

        Assert.Equal("Spec must be a JSON object.", LoadValidated("[]").Detail);
    }

    [Theory]
    [InlineData("\"schema_version\":\"0.1\"", "\"schema_version\":\"0.2\"", "Spec schema_version \"0.2\" does not match the receipt's spec_schema_id 'urn:tekla-harness:schema:spec:0.1'.")]
    [InlineData("\"schema_version\":\"0.1\"", "\"schema_version\":1", "Spec schema_version (missing or not a string) does not match the receipt's spec_schema_id 'urn:tekla-harness:schema:spec:0.1'.")]
    [InlineData("\"units\":\"mm\"", "\"units\":\"m\"", "Spec units must be \"mm\".")]
    [InlineData("\"lot\":1,", "\"lot\":0,", "Spec lot must be an integer token from 1 to 2147483647.")]
    [InlineData("\"lot\":1,", "\"lot\":2,", "Spec lot 2 is not the requested --lot 1.")]
    [InlineData("\"project_id\":\"p1\"", "\"project_id\":\"\"", "Spec field 'project_id' must be a non-empty string.")]
    [InlineData(Members, "\"members\":[]", "Spec members must be a non-empty array.")]
    [InlineData("\"members\":[", "\"members\":[1,", "Spec field 'members[0]' must be an object.")]
    [InlineData("\"spec_id\":\"M2\"", "\"spec_id\":\"M1\"", "Spec field 'members[1].spec_id' repeats spec_id \"M1\".")]
    [InlineData("\"type\":\"beam\"", "\"type\":1", "Spec field 'members[0].type' must be a string.")]
    [InlineData("{\"value\":\"IPE300\"}", "{\"value\":\"\"}", "Spec field 'members[0].profile.value' must be a non-empty string.")]
    [InlineData("\"start\":{\"x\":10,\"y\":20,\"z\":30}", "\"start\":1", "Spec field 'members[1].start' must be an object.")]
    [InlineData("\"x\":0,\"y\":-1.5", "\"x\":\"0\",\"y\":-1.5", "Spec field 'members[0].start.x' must be a number.")]
    [InlineData("\"spec_id\":\"M1\"", "\"spec_id\":\"M1\",\"name\":5", "Spec field 'members[0].name' must be a string.")]
    public void Read_time_check_messages(string oldValue, string newValue, string expected)
        => Assert.Equal(expected, LoadValidated(Swap(BaseSpec, oldValue, newValue)).Detail);

    // ---- exit codes (ADR-0010 Amendment 1 §6)

    [Fact]
    public void Exit_code_mapping()
    {
        foreach (SpecRefusal refusal in Enum.GetValues(typeof(SpecRefusal)))
        {
            var expected = refusal switch
            {
                SpecRefusal.None => ExitCode.Ok,
                SpecRefusal.BadArgument => ExitCode.UsageError,
                SpecRefusal.ReadError => ExitCode.EnvironmentError,
                _ => ExitCode.RefusedBySafetyRule,
            };
            Assert.Equal(expected, new SpecLoadResult(refusal, "d", null).ExitCode);
        }
    }

    // ---- culture must not change any decision or value (ADR-0009 §3)

    private (string, double, double, double)[] Snapshot()
    {
        File.Copy(RepoPaths.SchemaExample("spec.example.json"), SpecPath, overwrite: true);
        File.Copy(RepoPaths.SchemaExample("spec-receipt.example.json"), ReceiptPath, overwrite: true);
        var example = SpecLoader.Load(SpecPath, 1);
        AssertLoaded(example);
        var minimal = LoadValidated(Swap(BaseSpec, "\"spec_id\":\"M1\"", "\"spec_id\":\"M1\",\"rotation_deg\":{\"value\":12.75}"));
        AssertLoaded(minimal);
        Assert.Equal(12.75, minimal.Spec!.Members[0].RotationDeg);
        AssertRefused(LoadValidated(Swap(BaseSpec, "\"lot\":1,", "\"lot\":1.0,")), SpecRefusal.LotInvalid);
        return example.Spec!.Members.Concat(minimal.Spec.Members)
            .SelectMany(m => new[] { (m.SpecId, m.Start.X, m.Start.Y, m.Start.Z), (m.SpecId, m.End.X, m.End.Y, m.End.Z) })
            .ToArray();
    }

    [Theory]
    [InlineData("vi-VN")]
    [InlineData("tr-TR")]
    [InlineData("de-DE")]
    public void Loading_does_not_depend_on_the_current_culture(string culture)
    {
        var saved = Thread.CurrentThread.CurrentCulture;
        IReadOnlyList<(string, double, double, double)> invariant;
        try
        {
            Thread.CurrentThread.CurrentCulture = CultureInfo.InvariantCulture;
            invariant = Snapshot();
            Thread.CurrentThread.CurrentCulture = new CultureInfo(culture);
            Assert.Equal(invariant, Snapshot());
        }
        finally
        {
            Thread.CurrentThread.CurrentCulture = saved;
        }

        Assert.Contains(("M1", 0.0, -1.5, 3000.0), invariant);
        Assert.Contains(("M1", 6000.0, 0.25, 3000.0), invariant);
    }
}
