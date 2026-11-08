using System;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading;
using Xunit;

namespace TeklaHarness.Core.Tests;

/// <summary>
/// ADR-0012 decision 2: the journal is read with the strict JSON profile and exactly the schema's
/// shape, and written as deterministic bytes (golden file shared with pytest).
/// </summary>
public sealed class RunJournalJsonTests
{
    private const string Sha = "77a1243091e09d63325185ae2a70896726c355f20f78564b57b9429023b91713";
    private const string Guid1 = "3f2504e0-4f89-11d3-9a0c-0305e82c3301";
    private const string Obj = "{\"spec_id\":\"L1-C-A1\",\"guid\":\"" + Guid1 + "\",\"action\":\"created\",\"state\":\"tagged\"}";
    private const string Fail = "{\"stage\":\"tag\",\"spec_id\":\"L1-C-A2\",\"error\":\"boom\"}";
    private const string Conf = "{\"kind\":\"mismatch\",\"spec_id\":\"x\",\"guid\":null,\"detail\":\"d\"}";

    private const string Inv =
        "{\"command\":\"build\",\"started_at\":\"2026-11-08T09:00:00Z\",\"ended_at\":null,\"tekla_version\":\"2024.0\","
        + "\"model_path\":\"C:\\\\M\\\\copy2\",\"outcome\":\"stopped\",\"exit_code\":4,\"committed\":false,"
        + "\"objects\":[" + Obj + "],\"failure\":" + Fail + ",\"conflicts\":[" + Conf + "]}";

    internal const string Base =
        "{\"schema_version\":\"0.1\",\"project_id\":\"demo-warehouse\",\"lot\":1,\"run_id\":\"R1\",\"spec_file\":\"spec.json\","
        + "\"spec_sha256\":\"" + Sha + "\",\"model_path\":\"C:\\\\M\\\\copy\",\"invocations\":[" + Inv + "]}";

    private static string GoldenPath => Path.Combine(RepoPaths.Root, "tests", "fixtures", "run-journal", "golden.json");

    internal static string Swap(string text, string oldValue, string newValue)
    {
        var at = text.IndexOf(oldValue, StringComparison.Ordinal);
        Assert.True(at >= 0, "fragment not found: " + oldValue);
        Assert.Equal(at, text.LastIndexOf(oldValue, StringComparison.Ordinal));
        return text.Substring(0, at) + newValue + text.Substring(at + oldValue.Length);
    }

    internal static JournalReadResult Parse(string text) => RunJournalFile.Parse(Encoding.UTF8.GetBytes(text), "test journal");

    private static RunJournal Accepted(string text)
    {
        var result = Parse(text);
        Assert.True(result.Status == JournalReadStatus.Found, result.Detail);
        Assert.Equal(ExitCode.Ok, result.ExitCode);
        Assert.NotNull(result.Journal);
        return result.Journal!;
    }

    private static void Rejected(string text, string? detailFragment = null)
    {
        var result = Parse(text);
        Assert.Equal(JournalReadStatus.Invalid, result.Status);
        Assert.Equal(ExitCode.RefusedBySafetyRule, result.ExitCode);
        Assert.Null(result.Journal);
        Assert.Contains("test journal", result.Detail, StringComparison.Ordinal);
        if (detailFragment is not null)
        {
            Assert.Contains(detailFragment, result.Detail, StringComparison.Ordinal);
        }
    }

    // ---- the base and the example are valid

    [Fact]
    public void Base_journal_reads_every_field()
    {
        var j = Accepted(Base);
        Assert.Equal("0.1", j.SchemaVersion);
        Assert.Equal("demo-warehouse", j.ProjectId);
        Assert.Equal(1, j.Lot);
        Assert.Equal("R1", j.RunId);
        Assert.Equal("spec.json", j.SpecFile);
        Assert.Equal(Sha, j.SpecSha256);
        Assert.Equal(@"C:\M\copy", j.ModelPath);
        var inv = Assert.Single(j.Invocations);
        Assert.Equal(JournalCommand.Build, inv.Command);
        Assert.Equal("2026-11-08T09:00:00Z", inv.StartedAt);
        Assert.Null(inv.EndedAt);
        Assert.Equal("2024.0", inv.TeklaVersion);
        Assert.Equal(@"C:\M\copy2", inv.ModelPath);
        Assert.Equal(InvocationOutcome.Stopped, inv.Outcome);
        Assert.Equal(4, inv.ExitCode);
        Assert.False(inv.Committed);
        var o = Assert.Single(inv.Objects);
        Assert.Equal("L1-C-A1", o.SpecId);
        Assert.Equal(new Guid(Guid1), o.Guid);
        Assert.Equal(ObjectAction.Created, o.Action);
        Assert.Equal(ObjectState.Tagged, o.State);
        Assert.NotNull(inv.Failure);
        Assert.Equal(FailureStage.Tag, inv.Failure!.Stage);
        Assert.Equal("L1-C-A2", inv.Failure.SpecId);
        Assert.Equal("boom", inv.Failure.Error);
        var c = Assert.Single(inv.Conflicts);
        Assert.Equal(ConflictKind.Mismatch, c.Kind);
        Assert.Equal("x", c.SpecId);
        Assert.Null(c.Guid);
        Assert.Equal("d", c.Detail);
    }

    [Fact]
    public void Schema_example_parses()
    {
        var result = RunJournalFile.Read(RepoPaths.SchemaExample("run-journal.example.json"));
        Assert.Equal(JournalReadStatus.Found, result.Status);
        var j = result.Journal!;
        Assert.Equal("R20261108-01", j.RunId);
        Assert.Equal(2, j.Invocations.Count);
        Assert.Equal(ObjectState.Inserted, j.Invocations[0].Objects[1].State);
        Assert.Equal(ObjectAction.Retagged, j.Invocations[1].Objects[0].Action);
        Assert.True(j.Invocations[1].Committed);
        Assert.Equal(0, j.Invocations[1].ExitCode);
        Assert.Equal("2026-11-08T09:10:04Z", j.Invocations[1].EndedAt);
    }

    [Theory]
    [InlineData("\"ended_at\":null", "\"ended_at\":\"2026-11-08T09:00:05Z\"")]
    [InlineData("\"exit_code\":4", "\"exit_code\":null")]
    [InlineData("\"exit_code\":4", "\"exit_code\":0")]
    [InlineData("\"exit_code\":4", "\"exit_code\":5")]
    [InlineData("\"failure\":" + Fail, "\"failure\":null")]
    [InlineData("\"spec_id\":\"L1-C-A2\"", "\"spec_id\":null")]
    [InlineData("\"spec_id\":\"x\"", "\"spec_id\":\"any text, not a spec id\"")]
    [InlineData("\"spec_id\":\"x\"", "\"spec_id\":null")]
    [InlineData("\"guid\":null", "\"guid\":\"" + Guid1 + "\"")]
    [InlineData("\"lot\":1,", "\"lot\":2147483647,")]
    [InlineData("\"run_id\":\"R1\"", "\"run_id\":\"R1234567890123456789012345678901\"")]
    [InlineData("\"run_id\":\"R1\"", "\"run_id\":\"0_A-\"")]
    [InlineData("\"project_id\":\"demo-warehouse\"", "\"project_id\":\"d1\"")]
    [InlineData("\"spec_file\":\"spec.json\"", "\"spec_file\":\"spec name\u00e9.json\"")]
    [InlineData("\"spec_id\":\"L1-C-A1\"", "\"spec_id\":\"A\"")]
    [InlineData("\"committed\":false", "\"committed\":true")]
    [InlineData("\"objects\":[" + Obj + "]", "\"objects\":[]")]
    [InlineData("\"conflicts\":[" + Conf + "]", "\"conflicts\":[]")]
    [InlineData("\"invocations\":[" + Inv + "]", "\"invocations\":[]")]
    [InlineData("\"guid\":\"" + Guid1 + "\",\"action\":\"created\",\"state\":\"tagged\"", "\"guid\":null,\"action\":\"created\",\"state\":\"inserting\"")]
    [InlineData("\"guid\":\"" + Guid1 + "\",\"action\":\"created\",\"state\":\"tagged\"", "\"guid\":\"" + Guid1 + "\",\"action\":\"retagged\",\"state\":\"inserted\"")]
    public void Valid_variants_are_accepted(string oldValue, string newValue)
    {
        Accepted(Swap(Base, oldValue, newValue));
    }

    [Fact]
    public void Longest_ids_are_accepted()
    {
        Accepted(Swap(Base, "\"project_id\":\"demo-warehouse\"", "\"project_id\":\"" + new string('a', 64) + "\""));
        Accepted(Swap(Base, "\"spec_id\":\"L1-C-A1\"", "\"spec_id\":\"" + new string('A', 64) + "\""));
    }

    [Fact]
    public void Every_enum_value_reads()
    {
        foreach (var (word, value) in new[] { ("build", JournalCommand.Build), ("update", JournalCommand.Update), ("rollback", JournalCommand.Rollback) })
        {
            Assert.Equal(value, Accepted(Swap(Base, "\"command\":\"build\"", "\"command\":\"" + word + "\"")).Invocations[0].Command);
        }

        var outcomes = new[] { "running", "ok", "stopped", "conflict", "refused", "abandoned" };
        for (var i = 0; i < outcomes.Length; i++)
        {
            Assert.Equal((InvocationOutcome)i, Accepted(Swap(Base, "\"outcome\":\"stopped\"", "\"outcome\":\"" + outcomes[i] + "\"")).Invocations[0].Outcome);
        }

        var stages = new[] { "plan", "insert", "tag", "commit", "journal", "other" };
        for (var i = 0; i < stages.Length; i++)
        {
            Assert.Equal((FailureStage)i, Accepted(Swap(Base, "\"stage\":\"tag\"", "\"stage\":\"" + stages[i] + "\"")).Invocations[0].Failure!.Stage);
        }

        var kinds = new[] { "mismatch", "duplicate_spec_id", "spec_id_in_other_run", "run_in_other_lot", "unknown_spec_id", "intent_unresolved", "tag_contradiction", "unclassified" };
        for (var i = 0; i < kinds.Length; i++)
        {
            Assert.Equal((ConflictKind)i, Accepted(Swap(Base, "\"kind\":\"mismatch\"", "\"kind\":\"" + kinds[i] + "\"")).Invocations[0].Conflicts[0].Kind);
        }

        Assert.Equal(ObjectState.Inserted, Accepted(Swap(Base, "\"state\":\"tagged\"", "\"state\":\"inserted\"")).Invocations[0].Objects[0].State);
        Assert.Equal(ObjectAction.Retagged, Accepted(Swap(Base, "\"action\":\"created\"", "\"action\":\"retagged\"")).Invocations[0].Objects[0].Action);
    }

    // ---- every schema rule refuses

    /// <summary>One schema rule broken per case: (fragment of <c>Base</c>, replacement).</summary>
    public static readonly TheoryData<string, string> RejectCases = new()
    {
        // top level: required, unknown, const, patterns, ranges
        { "\"schema_version\":\"0.1\",", "" },
        { "\"project_id\":\"demo-warehouse\",", "" },
        { "\"lot\":1,", "" },
        { "\"run_id\":\"R1\",", "" },
        { "\"spec_file\":\"spec.json\",", "" },
        { "\"spec_sha256\":\"" + Sha + "\",", "" },
        { "\"model_path\":\"C:\\\\M\\\\copy\",", "" },
        { ",\"invocations\":[" + Inv + "]", "" },
        { "\"lot\":1,", "\"lot\":1,\"extra\":1," },
        { "\"schema_version\":\"0.1\"", "\"schema_version\":\"0.2\"" },
        { "\"schema_version\":\"0.1\"", "\"schema_version\":0.1" },
        { "\"project_id\":\"demo-warehouse\"", "\"project_id\":\"Demo\"" },
        { "\"project_id\":\"demo-warehouse\"", "\"project_id\":\"d\"" },
        { "\"project_id\":\"demo-warehouse\"", "\"project_id\":\"-demo\"" },
        { "\"project_id\":\"demo-warehouse\"", "\"project_id\":\"demo_x\"" },
        { "\"project_id\":\"demo-warehouse\"", "\"project_id\":\"demo\\n\"" },
        { "\"project_id\":\"demo-warehouse\"", "\"project_id\":null" },
        { "\"lot\":1,", "\"lot\":0," },
        { "\"lot\":1,", "\"lot\":-1," },
        { "\"lot\":1,", "\"lot\":2147483648," },
        { "\"lot\":1,", "\"lot\":1.0," },
        { "\"lot\":1,", "\"lot\":1e0," },
        { "\"lot\":1,", "\"lot\":\"1\"," },
        { "\"run_id\":\"R1\"", "\"run_id\":\"r1\"" },
        { "\"run_id\":\"R1\"", "\"run_id\":\"\"" },
        { "\"run_id\":\"R1\"", "\"run_id\":\"R1234567890123456789012345678901X\"" },
        { "\"run_id\":\"R1\"", "\"run_id\":\"R1\\n\"" },
        { "\"run_id\":\"R1\"", "\"run_id\":\"-R\"" },
        { "\"run_id\":\"R1\"", "\"run_id\":\"R.1\"" },
        { "\"spec_file\":\"spec.json\"", "\"spec_file\":\"\"" },
        { "\"spec_file\":\"spec.json\"", "\"spec_file\":\"a/spec.json\"" },
        { "\"spec_file\":\"spec.json\"", "\"spec_file\":\"a\\\\spec.json\"" },
        { "\"spec_sha256\":\"" + Sha + "\"", "\"spec_sha256\":\"" + "77A1243091e09d63325185ae2a70896726c355f20f78564b57b9429023b91713" + "\"" },
        { "\"spec_sha256\":\"" + Sha + "\"", "\"spec_sha256\":\"" + "7a1243091e09d63325185ae2a70896726c355f20f78564b57b9429023b91713" + "\"" },
        { "\"spec_sha256\":\"" + Sha + "\"", "\"spec_sha256\":\"" + Sha + "0\"" },
        { "\"spec_sha256\":\"" + Sha + "\"", "\"spec_sha256\":\"" + "g7a1243091e09d63325185ae2a70896726c355f20f78564b57b9429023b91713" + "\"" },
        { "\"model_path\":\"C:\\\\M\\\\copy\"", "\"model_path\":\"\"" },
        { "\"model_path\":\"C:\\\\M\\\\copy\"", "\"model_path\":1" },
        { "\"invocations\":[" + Inv + "]", "\"invocations\":{}" },
        { "\"invocations\":[" + Inv + "]", "\"invocations\":null" },
        { "\"invocations\":[" + Inv + "]", "\"invocations\":[1]" },
        { "\"invocations\":[" + Inv + "]", "\"invocations\":[null]" },
        // invocation
        { "\"command\":\"build\",", "" },
        { "\"started_at\":\"2026-11-08T09:00:00Z\",", "" },
        { "\"ended_at\":null,", "" },
        { "\"tekla_version\":\"2024.0\",", "" },
        { "\"model_path\":\"C:\\\\M\\\\copy2\",", "" },
        { "\"outcome\":\"stopped\",", "" },
        { "\"exit_code\":4,", "" },
        { "\"committed\":false,", "" },
        { "\"objects\":[" + Obj + "],", "" },
        { "\"failure\":" + Fail + ",", "" },
        { ",\"conflicts\":[" + Conf + "]", "" },
        { "\"committed\":false,", "\"committed\":false,\"note\":\"x\"," },
        { "\"command\":\"build\"", "\"command\":\"Build\"" },
        { "\"command\":\"build\"", "\"command\":\"delete\"" },
        { "\"command\":\"build\"", "\"command\":null" },
        { "\"started_at\":\"2026-11-08T09:00:00Z\"", "\"started_at\":\"2026-11-08T09:00:00\"" },
        { "\"started_at\":\"2026-11-08T09:00:00Z\"", "\"started_at\":\"2026-11-08 09:00:00Z\"" },
        { "\"started_at\":\"2026-11-08T09:00:00Z\"", "\"started_at\":\"2026-11-08T09:00:00.000Z\"" },
        { "\"started_at\":\"2026-11-08T09:00:00Z\"", "\"started_at\":\"\u0662026-11-08T09:00:00Z\"" },
        { "\"started_at\":\"2026-11-08T09:00:00Z\"", "\"started_at\":\"2026-11-08T09:00:0aZ\"" },
        { "\"started_at\":\"2026-11-08T09:00:00Z\"", "\"started_at\":\"2026/11-08T09:00:00Z\"" },
        { "\"started_at\":\"2026-11-08T09:00:00Z\"", "\"started_at\":null" },
        { "\"ended_at\":null", "\"ended_at\":0" },
        { "\"ended_at\":null", "\"ended_at\":\"x\"" },
        { "\"tekla_version\":\"2024.0\"", "\"tekla_version\":\"\"" },
        { "\"tekla_version\":\"2024.0\"", "\"tekla_version\":null" },
        { "\"model_path\":\"C:\\\\M\\\\copy2\"", "\"model_path\":\"\"" },
        { "\"outcome\":\"stopped\"", "\"outcome\":\"OK\"" },
        { "\"outcome\":\"stopped\"", "\"outcome\":\"done\"" },
        { "\"exit_code\":4", "\"exit_code\":6" },
        { "\"exit_code\":4", "\"exit_code\":-1" },
        { "\"exit_code\":4", "\"exit_code\":4.0" },
        { "\"exit_code\":4", "\"exit_code\":\"4\"" },
        { "\"committed\":false", "\"committed\":\"false\"" },
        { "\"committed\":false", "\"committed\":null" },
        { "\"committed\":false", "\"committed\":0" },
        { "\"objects\":[" + Obj + "]", "\"objects\":null" },
        { "\"objects\":[" + Obj + "]", "\"objects\":{}" },
        { "\"objects\":[" + Obj + "]", "\"objects\":[1]" },
        { "\"failure\":" + Fail, "\"failure\":\"x\"" },
        { "\"failure\":" + Fail, "\"failure\":[]" },
        { "\"conflicts\":[" + Conf + "]", "\"conflicts\":null" },
        { "\"conflicts\":[" + Conf + "]", "\"conflicts\":[\"x\"]" },
        // object
        { "\"spec_id\":\"L1-C-A1\",", "" },
        { "\"guid\":\"" + Guid1 + "\",", "" },
        { "\"action\":\"created\",", "" },
        { ",\"state\":\"tagged\"", "" },
        { "\"state\":\"tagged\"", "\"state\":\"tagged\",\"x\":1" },
        { "\"spec_id\":\"L1-C-A1\"", "\"spec_id\":\"l1-c-a1\"" },
        { "\"spec_id\":\"L1-C-A1\"", "\"spec_id\":\"\"" },
        { "\"spec_id\":\"L1-C-A1\"", "\"spec_id\":\"_L1\"" },
        { "\"spec_id\":\"L1-C-A1\"", "\"spec_id\":\"L1 C\"" },
        { "\"spec_id\":\"L1-C-A1\"", "\"spec_id\":null" },
        { "\"spec_id\":\"L1-C-A1\"", "\"spec_id\":\"L1-C-A1\\n\"" },
        { "\"guid\":\"" + Guid1 + "\"", "\"guid\":\"3F2504E0-4f89-11d3-9a0c-0305e82c3301\"" },
        { "\"guid\":\"" + Guid1 + "\"", "\"guid\":\"3f2504e04f8911d39a0c0305e82c3301\"" },
        { "\"guid\":\"" + Guid1 + "\"", "\"guid\":\"{3f2504e0-4f89-11d3-9a0c-0305e82c3301}\"" },
        { "\"guid\":\"" + Guid1 + "\"", "\"guid\":\"3f2504e0-4f89-11d3-9a0c-0305e82c330\"" },
        { "\"guid\":\"" + Guid1 + "\"", "\"guid\":\"3f2504e0-4f89-11d3-9a0c-0305e82c33011\"" },
        { "\"guid\":\"" + Guid1 + "\"", "\"guid\":\"3f2504e0+4f89-11d3-9a0c-0305e82c3301\"" },
        { "\"guid\":\"" + Guid1 + "\"", "\"guid\":\"3f2504e0-4f89-11d3-9a0c-0305e82c330g\"" },
        { "\"guid\":\"" + Guid1 + "\"", "\"guid\":1" },
        { "\"action\":\"created\"", "\"action\":\"create\"" },
        { "\"action\":\"created\"", "\"action\":null" },
        { "\"state\":\"tagged\"", "\"state\":\"Tagged\"" },
        { "\"state\":\"tagged\"", "\"state\":\"inserting\"" },
        { "\"guid\":\"" + Guid1 + "\"", "\"guid\":null" },
        { "\"guid\":\"" + Guid1 + "\",\"action\":\"created\",\"state\":\"tagged\"", "\"guid\":null,\"action\":\"created\",\"state\":\"inserted\"" },
        // failure
        { "\"stage\":\"tag\",", "" },
        { "\"spec_id\":\"L1-C-A2\",", "" },
        { ",\"error\":\"boom\"", "" },
        { "\"error\":\"boom\"", "\"error\":\"boom\",\"x\":1" },
        { "\"stage\":\"tag\"", "\"stage\":\"parse\"" },
        { "\"spec_id\":\"L1-C-A2\"", "\"spec_id\":\"l1\"" },
        { "\"spec_id\":\"L1-C-A2\"", "\"spec_id\":\"\"" },
        { "\"error\":\"boom\"", "\"error\":\"\"" },
        { "\"error\":\"boom\"", "\"error\":null" },
        // conflict
        { "\"kind\":\"mismatch\",", "" },
        { "\"spec_id\":\"x\",", "" },
        { "\"guid\":null,", "" },
        { ",\"detail\":\"d\"", "" },
        { "\"detail\":\"d\"", "\"detail\":\"d\",\"x\":1" },
        { "\"kind\":\"mismatch\"", "\"kind\":\"other\"" },
        { "\"spec_id\":\"x\"", "\"spec_id\":\"\"" },
        { "\"spec_id\":\"x\"", "\"spec_id\":1" },
        { "\"guid\":null", "\"guid\":\"x\"" },
        { "\"detail\":\"d\"", "\"detail\":\"\"" },
        { "\"detail\":\"d\"", "\"detail\":null" },
        // non-string values of string fields (appended: snapshot indices stay stable)
        { "\"run_id\":\"R1\"", "\"run_id\":1" },
        { "\"spec_file\":\"spec.json\"", "\"spec_file\":null" },
        { "\"spec_sha256\":\"" + Sha + "\"", "\"spec_sha256\":1" },
        { "\"spec_id\":\"L1-C-A2\"", "\"spec_id\":1" },
    };

    [Theory]
    [MemberData(nameof(RejectCases))]
    public void Every_schema_rule_refuses(string oldValue, string newValue)
    {
        Rejected(Swap(Base, oldValue, newValue));
    }

    [Theory]
    [InlineData("[]")]
    [InlineData("null")]
    [InlineData("\"journal\"")]
    public void Non_object_top_level_refuses(string text)
    {
        Rejected(text, "object");
    }

    [Theory]
    [InlineData("\"invocations\":[" + Inv + "]", "\"invocations\":[" + Inv + ",[]]")]
    [InlineData("\"objects\":[" + Obj + "]", "\"objects\":[" + Obj + ",null]")]
    [InlineData("\"failure\":" + Fail, "\"failure\":1")]
    [InlineData("\"conflicts\":[" + Conf + "]", "\"conflicts\":[" + Conf + ",[]]")]
    public void Nested_non_objects_refuse(string oldValue, string newValue)
    {
        Rejected(Swap(Base, oldValue, newValue), "object");
    }

    [Fact]
    public void Too_long_ids_refuse()
    {
        Rejected(Swap(Base, "\"project_id\":\"demo-warehouse\"", "\"project_id\":\"" + new string('a', 65) + "\""));
        Rejected(Swap(Base, "\"spec_id\":\"L1-C-A1\"", "\"spec_id\":\"" + new string('A', 65) + "\""));
    }

    [Fact]
    public void Refusal_detail_names_the_field()
    {
        Rejected(Swap(Base, "\"exit_code\":4", "\"exit_code\":9"), "invocations[0].exit_code");
        Rejected(Swap(Base, "\"state\":\"tagged\"", "\"state\":\"x\""), "invocations[0].objects[0].state");
        Rejected(Swap(Base, "\"lot\":1,", "\"lot\":1,\"extra\":1,"), "extra");
        Rejected(Swap(Base, ",\"detail\":\"d\"", ""), "invocations[0].conflicts[0].detail");
    }

    // ---- the strict JSON profile applies

    [Theory]
    [InlineData("\"lot\":1,", "\"lot\":1,\"lot\":1,")]
    [InlineData("\"detail\":\"d\"", "\"detail\":\"\\ud800\"")]
    [InlineData("\"detail\":\"d\"", "\"detail\":\"a\\u0000\"")]
    [InlineData("\"detail\":\"d\"", "\"detail\":\"a\u0001\"")]
    [InlineData("\"exit_code\":4", "\"exit_code\":NaN")]
    [InlineData("\"exit_code\":4", "\"exit_code\":9007199254740993")]
    [InlineData("\"conflicts\":[" + Conf + "]", "\"conflicts\":[" + Conf + ",]")]
    [InlineData("\"lot\":1,", "\"lot\":1, // one\n")]
    [InlineData("\"detail\":\"d\"", "\"detail\":'d'")]
    public void Strict_profile_violations_refuse(string oldValue, string newValue)
    {
        Rejected(Swap(Base, oldValue, newValue), "strict JSON");
    }

    [Fact]
    public void Bom_and_trailing_content_refuse()
    {
        var bom = new byte[] { 0xEF, 0xBB, 0xBF }.Concat(Encoding.UTF8.GetBytes(Base)).ToArray();
        Assert.Equal(JournalReadStatus.Invalid, RunJournalFile.Parse(bom, "x").Status);
        Rejected(Base + "{}", "strict JSON");
        var badUtf8 = Encoding.UTF8.GetBytes(Base);
        badUtf8[Base.IndexOf("boom", StringComparison.Ordinal)] = 0xC0;
        Assert.Equal(JournalReadStatus.Invalid, RunJournalFile.Parse(badUtf8, "x").Status);
    }

    // ---- writer: golden bytes, round trip, escapes, determinism

    [Fact]
    public void Writer_output_for_the_example_is_the_golden_file()
    {
        var example = RunJournalFile.Read(RepoPaths.SchemaExample("run-journal.example.json")).Journal!;
        Assert.Equal(File.ReadAllBytes(GoldenPath), RunJournalFile.Serialize(example));
    }

    [Fact]
    public void Golden_file_reads_and_writes_back_to_the_same_bytes()
    {
        var golden = File.ReadAllBytes(GoldenPath);
        var result = RunJournalFile.Parse(golden, "golden");
        Assert.Equal(JournalReadStatus.Found, result.Status);
        Assert.Equal(golden, RunJournalFile.Serialize(result.Journal!));
    }

    [Fact]
    public void Base_round_trips_through_the_writer()
    {
        var bytes = RunJournalFile.Serialize(Accepted(Base));
        var again = RunJournalFile.Parse(bytes, "again");
        Assert.Equal(bytes, RunJournalFile.Serialize(again.Journal!));
        var text = Encoding.UTF8.GetString(bytes);
        Assert.StartsWith("{\n  \"schema_version\": \"0.1\",\n  \"project_id\": \"demo-warehouse\",\n  \"lot\": 1,\n", text, StringComparison.Ordinal);
        Assert.Contains("\n      \"ended_at\": null,\n", text, StringComparison.Ordinal);
        Assert.Contains("\n      \"committed\": false,\n", text, StringComparison.Ordinal);
        Assert.EndsWith("\n  ]\n}\n", text, StringComparison.Ordinal);
        Assert.DoesNotContain("\r", text, StringComparison.Ordinal);
        Assert.NotEqual(0xEF, bytes[0]);
    }

    [Fact]
    public void Empty_containers_are_written_compact()
    {
        var j = new RunJournal("demo-warehouse", 3, "R1", "spec.json", Sha, @"C:\M", Array.Empty<JournalInvocation>());
        var text = Encoding.UTF8.GetString(RunJournalFile.Serialize(j));
        Assert.Equal(
            "{\n  \"schema_version\": \"0.1\",\n  \"project_id\": \"demo-warehouse\",\n  \"lot\": 3,\n  \"run_id\": \"R1\",\n"
            + "  \"spec_file\": \"spec.json\",\n  \"spec_sha256\": \"" + Sha + "\",\n  \"model_path\": \"C:\\\\M\",\n  \"invocations\": []\n}\n",
            text);
    }

    private static RunJournal WithDetail(string detail)
    {
        var inv = new JournalInvocation(
            JournalCommand.Build,
            "2026-11-08T09:00:00Z",
            null,
            "2024.0",
            @"C:\M",
            InvocationOutcome.Conflict,
            1,
            false,
            Array.Empty<JournalObject>(),
            null,
            new[] { new JournalConflict(ConflictKind.Mismatch, null, null, detail) });
        return new RunJournal("demo-warehouse", 1, "R1", "spec.json", Sha, @"C:\M", new[] { inv });
    }

    [Fact]
    public void Strings_are_escaped_like_python_json_dumps_with_raw_utf8()
    {
        var detail = "q\"b\\s/\b\f\n\r\t\u0001\u001f\u007f\u00e9\u1ea1\U0001F600\u2028";
        var bytes = RunJournalFile.Serialize(WithDetail(detail));
        var expected = Encoding.UTF8.GetBytes(
            "\"detail\": \"q\\\"b\\\\s/\\b\\f\\n\\r\\t\\u0001\\u001f\u007f\u00e9\u1ea1\U0001F600\u2028\"");
        Assert.True(IndexOf(bytes, expected) >= 0, Encoding.UTF8.GetString(bytes));
        Assert.Equal(detail, RunJournalFile.Parse(bytes, "x").Journal!.Invocations[0].Conflicts[0].Detail);
    }

    private static int IndexOf(byte[] haystack, byte[] needle)
    {
        for (var i = 0; i + needle.Length <= haystack.Length; i++)
        {
            if (haystack.Skip(i).Take(needle.Length).SequenceEqual(needle))
            {
                return i;
            }
        }

        return -1;
    }

    [Theory]
    [InlineData(0)]
    [InlineData(1)]
    [InlineData(2)]
    [InlineData(3)]
    public void Strings_the_reader_would_refuse_are_never_written(int which)
    {
        // Built here, not in attributes: lone surrogates do not survive test-case serialisation.
        var detail = which switch
        {
            0 => "a" + '\ud800' + "b",
            1 => "a" + '\udc00',
            2 => new string('\ud800', 1),
            _ => "a" + '\u0000' + "b",
        };
        Assert.Throws<InvalidOperationException>(() => RunJournalFile.Serialize(WithDetail(detail)));
    }

    [Fact]
    public void Journals_breaking_a_schema_rule_are_never_written()
    {
        var ok = Accepted(Base);
        var inv = ok.Invocations[0];
        RunJournal Header(string project = "demo-warehouse", int lot = 1, string run = "R1", string file = "spec.json", string sha = Sha, string model = @"C:\M")
            => new(project, lot, run, file, sha, model, ok.Invocations);
        JournalInvocation WithObject(JournalObject o)
            => new(inv.Command, inv.StartedAt, inv.EndedAt, inv.TeklaVersion, inv.ModelPath, inv.Outcome, inv.ExitCode, inv.Committed, new[] { o }, inv.Failure, inv.Conflicts);
        var bad = new[]
        {
            Header(project: "Demo"),
            Header(lot: 0),
            Header(run: "r1"),
            Header(file: "a/b"),
            Header(sha: "ABC"),
            Header(model: string.Empty),
            ok.WithInvocations(new[] { WithObject(new JournalObject("L1", Guid.NewGuid(), ObjectAction.Created, ObjectState.Inserting)) }),
            ok.WithInvocations(new[] { WithObject(new JournalObject("L1", null, ObjectAction.Created, ObjectState.Tagged)) }),
            ok.WithInvocations(new[] { WithObject(new JournalObject("l1", null, ObjectAction.Created, ObjectState.Inserting)) }),
            ok.WithInvocations(new[] { new JournalInvocation(inv.Command, "now", null, "2024", "C:\\M", inv.Outcome, 6, false, inv.Objects, null, inv.Conflicts) }),
            ok.WithInvocations(new[] { new JournalInvocation((JournalCommand)7, inv.StartedAt, null, "2024", "C:\\M", inv.Outcome, 0, false, inv.Objects, null, inv.Conflicts) }),
            ok.WithInvocations(new[] { new JournalInvocation(inv.Command, inv.StartedAt, null, "2024", "C:\\M", (InvocationOutcome)9, 0, false, inv.Objects, new JournalFailure((FailureStage)9, null, "e"), inv.Conflicts) }),
        };
        foreach (var journal in bad)
        {
            Assert.Throws<InvalidOperationException>(() => RunJournalFile.Serialize(journal));
        }
    }

    [Fact]
    public void Every_enum_value_writes_its_schema_word()
    {
        foreach (JournalCommand c in Enum.GetValues(typeof(JournalCommand)))
        {
            foreach (InvocationOutcome o in Enum.GetValues(typeof(InvocationOutcome)))
            {
                var inv = new JournalInvocation(c, "2026-11-08T09:00:00Z", null, "2024", "C:\\M", o, null, false, Array.Empty<JournalObject>(), null, Array.Empty<JournalConflict>());
                var j = new RunJournal("demo-warehouse", 1, "R1", "spec.json", Sha, @"C:\M", new[] { inv });
                var back = RunJournalFile.Parse(RunJournalFile.Serialize(j), "x").Journal!.Invocations[0];
                Assert.Equal(c, back.Command);
                Assert.Equal(o, back.Outcome);
            }
        }

        foreach (ConflictKind k in Enum.GetValues(typeof(ConflictKind)))
        {
            foreach (FailureStage s in Enum.GetValues(typeof(FailureStage)))
            {
                var inv = new JournalInvocation(
                    JournalCommand.Build, "2026-11-08T09:00:00Z", null, "2024", "C:\\M", InvocationOutcome.Stopped, 4, false,
                    new[] { new JournalObject("A", Guid.Empty, ObjectAction.Retagged, ObjectState.Inserted) },
                    new JournalFailure(s, null, "e"),
                    new[] { new JournalConflict(k, "s", Guid.Empty, "d") });
                var j = new RunJournal("demo-warehouse", 1, "R1", "spec.json", Sha, @"C:\M", new[] { inv });
                var text = Encoding.UTF8.GetString(RunJournalFile.Serialize(j));
                var back = RunJournalFile.Parse(Encoding.UTF8.GetBytes(text), "x").Journal!.Invocations[0];
                Assert.Equal(k, back.Conflicts[0].Kind);
                Assert.Equal(s, back.Failure!.Stage);
                Assert.Equal(ObjectAction.Retagged, back.Objects[0].Action);
                Assert.Equal(ObjectState.Inserted, back.Objects[0].State);
                Assert.Equal(Guid.Empty, back.Conflicts[0].Guid);
                Assert.Contains("\"guid\": \"00000000-0000-0000-0000-000000000000\"", text, StringComparison.Ordinal);
            }
        }
    }

    [Theory]
    [InlineData("vi-VN")]
    [InlineData("ar-SA")]
    [InlineData("tr-TR")]
    public void Writer_and_reader_do_not_depend_on_the_current_culture(string culture)
    {
        var j = new RunJournal("demo-warehouse", 1234567, "R1", "spec.json", Sha, @"C:\M\İ", Accepted(Base).Invocations);
        var saved = Thread.CurrentThread.CurrentCulture;
        byte[] invariant;
        try
        {
            Thread.CurrentThread.CurrentCulture = CultureInfo.InvariantCulture;
            invariant = RunJournalFile.Serialize(j);
            Thread.CurrentThread.CurrentCulture = new CultureInfo(culture);
            Assert.Equal(invariant, RunJournalFile.Serialize(j));
            Assert.Equal(1234567, RunJournalFile.Parse(invariant, "x").Journal!.Lot);
            Assert.Equal("2026-01-02T03:04:05Z", JournalTimestamp.Format(new DateTime(2026, 1, 2, 3, 4, 5, DateTimeKind.Utc)));
        }
        finally
        {
            Thread.CurrentThread.CurrentCulture = saved;
        }

        Assert.Contains("\"lot\": 1234567,", Encoding.UTF8.GetString(invariant), StringComparison.Ordinal);
    }

    [Fact]
    public void Timestamps_must_be_utc()
    {
        var e = Assert.Throws<ArgumentException>(() => JournalTimestamp.Format(new DateTime(2026, 1, 2, 3, 4, 5, DateTimeKind.Local)));
        Assert.StartsWith("must be a UTC time", e.Message, StringComparison.Ordinal);
        Assert.Throws<ArgumentException>(() => JournalTimestamp.Format(new DateTime(2026, 1, 2, 3, 4, 5, DateTimeKind.Unspecified)));
    }

    [Fact]
    public void Model_constructors_reject_nulls()
    {
        Assert.Throws<ArgumentNullException>(() => new RunJournal(null!, 1, "R", "s", Sha, "m", Array.Empty<JournalInvocation>()));
        Assert.Throws<ArgumentNullException>(() => new RunJournal("p1", 1, "R", "s", Sha, "m", null!));
        Assert.StartsWith("contains null", Assert.Throws<ArgumentException>(() => new RunJournal("p1", 1, "R", "s", Sha, "m", new JournalInvocation[] { null! })).Message, StringComparison.Ordinal);
        Assert.Throws<ArgumentNullException>(() => new JournalObject(null!, null, ObjectAction.Created, ObjectState.Inserting));
        Assert.Throws<ArgumentNullException>(() => new JournalFailure(FailureStage.Tag, null, null!));
        Assert.Throws<ArgumentNullException>(() => new JournalConflict(ConflictKind.Mismatch, null, null, null!));
    }

    // ---- the JSON writer alone

    [Fact]
    public void Json_writer_refuses_non_integer_numbers()
    {
        Assert.True(Json.StrictJson.TryParse(Encoding.UTF8.GetBytes("[1.5]"), out var value, out _));
        Assert.StartsWith("Only integer numbers are written; got 1.5.", Assert.Throws<ArgumentException>(() => Json.JsonWriter.ToUtf8(value!)).Message, StringComparison.Ordinal);
    }

    [Fact]
    public void Json_writer_matches_python_layout_for_nested_values()
    {
        Assert.True(Json.StrictJson.TryParse(Encoding.UTF8.GetBytes("{\"a\":[1,true,null,{},[],{\"b\":-0}],\"c\":\"x\"}"), out var value, out _));
        Assert.Equal(
            "{\n  \"a\": [\n    1,\n    true,\n    null,\n    {},\n    [],\n    {\n      \"b\": 0\n    }\n  ],\n  \"c\": \"x\"\n}\n",
            Encoding.UTF8.GetString(Json.JsonWriter.ToUtf8(value!)));
        Assert.True(Json.StrictJson.TryParse(Encoding.UTF8.GetBytes("false"), out value, out _));
        Assert.Equal("false\n", Encoding.UTF8.GetString(Json.JsonWriter.ToUtf8(value!)));
    }

    // ---- edges found by mutation testing

    [Theory]
    [InlineData("z9")]
    [InlineData("0-z")]
    [InlineData("9a")]
    [InlineData("a0")]
    public void Project_id_character_boundaries_are_accepted(string projectId)
    {
        Accepted(Swap(Base, "\"project_id\":\"demo-warehouse\"", "\"project_id\":\"" + projectId + "\""));
    }

    [Theory]
    [InlineData("{a")]
    [InlineData("/a")]
    [InlineData(":a")]
    [InlineData("`a")]
    [InlineData("a{")]
    [InlineData("a/")]
    [InlineData("a:")]
    [InlineData("a`")]
    [InlineData("a_")]
    public void Project_id_characters_outside_the_pattern_refuse(string projectId)
    {
        Rejected(Swap(Base, "\"project_id\":\"demo-warehouse\"", "\"project_id\":\"" + projectId + "\""), "project_id");
    }

    [Theory]
    [InlineData("/spec.json")]
    [InlineData("\\\\spec.json")]
    public void Spec_file_starting_with_a_separator_refuses(string specFile)
    {
        Rejected(Swap(Base, "\"spec_file\":\"spec.json\"", "\"spec_file\":\"" + specFile + "\""), "spec_file");
    }

    [Fact]
    public void Enum_values_just_outside_the_schema_words_are_never_written()
    {
        var ok = Accepted(Base);
        var inv = ok.Invocations[0];
        JournalInvocation Inv(JournalCommand command = JournalCommand.Build, InvocationOutcome outcome = InvocationOutcome.Ok, FailureStage stage = FailureStage.Tag, ConflictKind kind = ConflictKind.Mismatch, ObjectAction action = ObjectAction.Created, ObjectState state = ObjectState.Tagged)
            => new(command, inv.StartedAt, null, "2024", @"C:\M", outcome, 0, false,
                new[] { new JournalObject("A", Guid.Empty, action, state) },
                new JournalFailure(stage, null, "e"),
                new[] { new JournalConflict(kind, null, null, "d") });
        Assert.NotNull(RunJournalFile.Serialize(ok.WithInvocations(new[] { Inv() })));
        var bad = new[]
        {
            (Inv(command: (JournalCommand)3), "undefined command value 3"),
            (Inv(command: (JournalCommand)(-1)), "undefined command value -1"),
            (Inv(outcome: (InvocationOutcome)6), "undefined outcome value 6"),
            (Inv(stage: (FailureStage)6), "undefined failure stage value 6"),
            (Inv(kind: (ConflictKind)8), "undefined conflict kind value 8"),
            (Inv(action: (ObjectAction)2), "undefined action value 2"),
            (Inv(state: (ObjectState)3), "undefined state value 3"),
        };
        foreach (var (invocation, message) in bad)
        {
            var e = Assert.Throws<InvalidOperationException>(() => RunJournalFile.Serialize(ok.WithInvocations(new[] { invocation })));
            Assert.Equal("Run journal cannot be written: " + message + ".", e.Message);
        }
    }

    [Fact]
    public void Json_tree_of_a_journal_is_keyed_for_lookup()
    {
        var tree = Assert.IsType<Json.JsonObject>(RunJournalJson.ToJson(Accepted(Base)));
        Assert.True(tree.TryGet("lot", out var lot));
        Assert.Equal(1.0, Assert.IsType<Json.JsonNumber>(lot).Value);
        Assert.Equal(new[] { "schema_version", "project_id", "lot", "run_id", "spec_file", "spec_sha256", "model_path", "invocations" }, tree.Members.Select(m => m.Key));
    }

    [Fact]
    public void Invalid_content_written_reports_the_reader_detail()
    {
        var j = new RunJournal("Demo", 1, "R1", "spec.json", Sha, @"C:\M", Array.Empty<JournalInvocation>());
        var e = Assert.Throws<InvalidOperationException>(() => RunJournalFile.Serialize(j));
        Assert.Equal("Run journal to write is not a valid run journal: 'project_id' must match ^[a-z0-9][a-z0-9-]{1,63}$.", e.Message);
        var surrogate = Assert.Throws<InvalidOperationException>(() => RunJournalFile.Serialize(WithDetail(new string('\ud800', 1))));
        Assert.StartsWith("Run journal cannot be written: ", surrogate.Message, StringComparison.Ordinal);
        Assert.IsAssignableFrom<ArgumentException>(surrogate.InnerException);
    }

    [Fact]
    public void Found_detail_counts_invocations()
    {
        Assert.Equal("test journal read: 1 invocation(s).", Parse(Base).Detail);
        Assert.Equal("test journal is not strict JSON: content after the JSON document at byte " + Base.Length.ToString(CultureInfo.InvariantCulture) + ".", Parse(Base + "1").Detail);
    }
}
