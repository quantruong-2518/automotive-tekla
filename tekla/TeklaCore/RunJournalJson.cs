using System;
using System.Collections.Generic;
using System.Globalization;
using TeklaHarness.Core.Json;

namespace TeklaHarness.Core;

/// <summary>
/// Schema shape of a run journal (<c>schemas/run-journal.schema.json</c>) on top of
/// <see cref="StrictJson"/>: model ⇄ JSON. Exactly the schema's fields, types, enums and patterns;
/// stricter in one place: <c>lot</c> and <c>exit_code</c> must be integer tokens (<c>1.0</c> refused).
/// </summary>
internal static class RunJournalJson
{
    private static readonly string[] TopFields =
        { "schema_version", "project_id", "lot", "run_id", "spec_file", "spec_sha256", "model_path", "invocations" };

    private static readonly string[] InvocationFields =
        { "command", "started_at", "ended_at", "tekla_version", "model_path", "outcome", "exit_code", "committed", "objects", "failure", "conflicts" };

    private static readonly string[] ObjectFields = { "spec_id", "guid", "action", "state" };

    private static readonly string[] FailureFields = { "stage", "spec_id", "error" };

    private static readonly string[] ConflictFields = { "kind", "spec_id", "guid", "detail" };

    // Schema words in enum order: the enum value is the index.
    private static readonly string[] Commands = { "build", "update", "rollback" };
    internal static readonly string[] Outcomes = { "running", "ok", "stopped", "conflict", "refused", "abandoned" };
    private static readonly string[] Actions = { "created", "retagged" };
    private static readonly string[] States = { "inserting", "inserted", "tagged" };
    private static readonly string[] Stages = { "plan", "insert", "tag", "commit", "journal", "other" };

    private static readonly string[] Kinds =
    {
        "mismatch", "duplicate_spec_id", "spec_id_in_other_run", "run_in_other_lot",
        "unknown_spec_id", "intent_unresolved", "tag_contradiction", "unclassified",
    };

    /// <summary>Checks <paramref name="root"/> against every schema rule. Throws <see cref="JournalInvalidException"/>.</summary>
    public static RunJournal Read(JsonValue root)
    {
        var top = root as JsonObject ?? throw Invalid("the top level must be an object");
        CheckFields(top, TopFields, string.Empty);
        if (String(top, "schema_version", string.Empty) != RunJournal.CurrentSchemaVersion)
        {
            throw Invalid("'schema_version' must be \"0.1\"");
        }

        var projectId = String(top, "project_id", string.Empty);
        if (!IdPatterns.IsProjectId(projectId))
        {
            throw Invalid("'project_id' must match ^[a-z0-9][a-z0-9-]{1,63}$");
        }

        var lot = (int)Integer(top, "lot", string.Empty, 1, int.MaxValue);
        var runId = String(top, "run_id", string.Empty);
        if (!RunId.IsValid(runId))
        {
            throw Invalid("'run_id' must match ^[A-Z0-9][A-Z0-9_-]{0,31}$");
        }

        var specFile = String(top, "spec_file", string.Empty);
        if (specFile.Length == 0 || specFile.IndexOf('/') >= 0 || specFile.IndexOf('\\') >= 0)
        {
            throw Invalid("'spec_file' must be a non-empty base name");
        }

        var sha = String(top, "spec_sha256", string.Empty);
        if (sha.Length != 64 || !AllChars(sha, IsLowerHex))
        {
            throw Invalid("'spec_sha256' must be 64 lowercase hexadecimal characters");
        }

        var modelPath = NonEmpty(top, "model_path", string.Empty);
        var items = Array(top, "invocations", string.Empty);
        var invocations = new List<JournalInvocation>(items.Count);
        for (var i = 0; i < items.Count; i++)
        {
            invocations.Add(ReadInvocation(items[i], "invocations[" + Index(i) + "]."));
        }

        return new RunJournal(projectId, lot, runId, specFile, sha, modelPath, invocations);
    }

    /// <summary>The journal as a JSON tree, keys in schema order. Throws <see cref="InvalidOperationException"/> for an undefined enum value.</summary>
    public static JsonValue ToJson(RunJournal journal)
    {
        var invocations = new List<JsonValue>();
        foreach (var inv in journal.Invocations)
        {
            var objects = new List<JsonValue>();
            foreach (var o in inv.Objects)
            {
                objects.Add(Obj(
                    ("spec_id", Str(o.SpecId)),
                    ("guid", GuidValue(o.Guid)),
                    ("action", Str(Word(Actions, (int)o.Action, "action"))),
                    ("state", Str(Word(States, (int)o.State, "state")))));
            }

            var conflicts = new List<JsonValue>();
            foreach (var c in inv.Conflicts)
            {
                conflicts.Add(Obj(
                    ("kind", Str(Word(Kinds, (int)c.Kind, "conflict kind"))),
                    ("spec_id", NullableStr(c.SpecId)),
                    ("guid", GuidValue(c.Guid)),
                    ("detail", Str(c.Detail))));
            }

            var failure = inv.Failure is null
                ? (JsonValue)JsonNull.Instance
                : Obj(
                    ("stage", Str(Word(Stages, (int)inv.Failure.Stage, "failure stage"))),
                    ("spec_id", NullableStr(inv.Failure.SpecId)),
                    ("error", Str(inv.Failure.Error)));

            invocations.Add(Obj(
                ("command", Str(Word(Commands, (int)inv.Command, "command"))),
                ("started_at", Str(inv.StartedAt)),
                ("ended_at", NullableStr(inv.EndedAt)),
                ("tekla_version", Str(inv.TeklaVersion)),
                ("model_path", Str(inv.ModelPath)),
                ("outcome", Str(Word(Outcomes, (int)inv.Outcome, "outcome"))),
                ("exit_code", inv.ExitCode.HasValue ? Int(inv.ExitCode.Value) : JsonNull.Instance),
                ("committed", inv.Committed ? JsonBool.True : JsonBool.False),
                ("objects", new JsonArray(objects)),
                ("failure", failure),
                ("conflicts", new JsonArray(conflicts))));
        }

        return Obj(
            ("schema_version", Str(journal.SchemaVersion)),
            ("project_id", Str(journal.ProjectId)),
            ("lot", Int(journal.Lot)),
            ("run_id", Str(journal.RunId)),
            ("spec_file", Str(journal.SpecFile)),
            ("spec_sha256", Str(journal.SpecSha256)),
            ("model_path", Str(journal.ModelPath)),
            ("invocations", new JsonArray(invocations)));
    }

    // ---- reading

    private static JournalInvocation ReadInvocation(JsonValue value, string at)
    {
        var inv = AsObject(value, at);
        CheckFields(inv, InvocationFields, at);
        var command = (JournalCommand)Enum(inv, "command", at, Commands);
        var startedAt = Timestamp(inv, "started_at", at);
        var endedAt = IsNull(inv, "ended_at") ? null : Timestamp(inv, "ended_at", at);
        var teklaVersion = NonEmpty(inv, "tekla_version", at);
        var modelPath = NonEmpty(inv, "model_path", at);
        var outcome = (InvocationOutcome)Enum(inv, "outcome", at, Outcomes);
        int? exitCode = IsNull(inv, "exit_code") ? null : (int)Integer(inv, "exit_code", at, 0, 5);
        Get(inv, "committed", out var committedValue);
        var committed = committedValue as JsonBool ?? throw Invalid("'" + at + "committed' must be a boolean");

        // S4 updates one entry per SPEC_ID in place (inserting → inserted → tagged): a second entry
        // for the same SPEC_ID in one invocation is a malformed journal (review m6).
        var objects = new List<JournalObject>();
        var seen = new HashSet<string>(StringComparer.Ordinal);
        var items = Array(inv, "objects", at);
        for (var i = 0; i < items.Count; i++)
        {
            var entryAt = at + "objects[" + Index(i) + "].";
            var entry = ReadObject(items[i], entryAt);
            if (!seen.Add(entry.SpecId))
            {
                throw Invalid("'" + entryAt + "spec_id' repeats " + entry.SpecId + " within one invocation");
            }

            objects.Add(entry);
        }

        JournalFailure? failure = null;
        if (!IsNull(inv, "failure"))
        {
            Get(inv, "failure", out var f);
            failure = ReadFailure(f, at + "failure.");
        }

        var conflicts = new List<JournalConflict>();
        items = Array(inv, "conflicts", at);
        for (var i = 0; i < items.Count; i++)
        {
            conflicts.Add(ReadConflict(items[i], at + "conflicts[" + Index(i) + "]."));
        }

        return new JournalInvocation(command, startedAt, endedAt, teklaVersion, modelPath, outcome, exitCode, committed.Value, objects, failure, conflicts);
    }

    private static JournalObject ReadObject(JsonValue value, string at)
    {
        var o = AsObject(value, at);
        CheckFields(o, ObjectFields, at);
        var specId = SpecId(o, "spec_id", at);
        var action = (ObjectAction)Enum(o, "action", at, Actions);
        var state = (ObjectState)Enum(o, "state", at, States);
        Guid? guid = null;
        if (state == ObjectState.Inserting)
        {
            if (!IsNull(o, "guid"))
            {
                throw Invalid("'" + at + "guid' must be null while state is \"inserting\"");
            }
        }
        else
        {
            guid = GuidField(o, "guid", at);
        }

        return new JournalObject(specId, guid, action, state);
    }

    private static JournalFailure ReadFailure(JsonValue value, string at)
    {
        var f = value as JsonObject ?? throw Invalid("'" + at.TrimEnd('.') + "' must be an object or null");
        CheckFields(f, FailureFields, at);
        var stage = (FailureStage)Enum(f, "stage", at, Stages);
        var specId = IsNull(f, "spec_id") ? null : SpecId(f, "spec_id", at);
        return new JournalFailure(stage, specId, NonEmpty(f, "error", at));
    }

    private static JournalConflict ReadConflict(JsonValue value, string at)
    {
        var c = AsObject(value, at);
        CheckFields(c, ConflictFields, at);
        var kind = (ConflictKind)Enum(c, "kind", at, Kinds);
        var specId = IsNull(c, "spec_id") ? null : NonEmpty(c, "spec_id", at);
        Guid? guid = IsNull(c, "guid") ? null : GuidField(c, "guid", at);
        return new JournalConflict(kind, specId, guid, NonEmpty(c, "detail", at));
    }

    private static JournalInvalidException Invalid(string detail) => new(detail);

    private static string Index(int i) => i.ToString(CultureInfo.InvariantCulture);

    private static JsonObject AsObject(JsonValue value, string at)
        => value as JsonObject ?? throw Invalid("'" + at.TrimEnd('.') + "' must be an object");

    /// <summary>Unknown field or missing field: both refuse.</summary>
    private static void CheckFields(JsonObject obj, string[] expected, string at)
    {
        foreach (var member in obj.Members)
        {
            if (System.Array.IndexOf(expected, member.Key) < 0)
            {
                throw Invalid("unknown field '" + at + member.Key + "'");
            }
        }

        foreach (var field in expected)
        {
            if (!obj.TryGet(field, out _))
            {
                throw Invalid("missing field '" + at + field + "'");
            }
        }
    }

    /// <summary>Fields are known to exist after <see cref="CheckFields"/>.</summary>
    private static void Get(JsonObject obj, string field, out JsonValue value)
    {
        obj.TryGet(field, out var v);
        value = v!;
    }

    private static bool IsNull(JsonObject obj, string field)
    {
        Get(obj, field, out var v);
        return v.Kind == JsonKind.Null;
    }

    private static string String(JsonObject obj, string field, string at)
    {
        Get(obj, field, out var v);
        return (v as JsonString)?.Value ?? throw Invalid("'" + at + field + "' must be a string");
    }

    private static string NonEmpty(JsonObject obj, string field, string at)
    {
        var s = String(obj, field, at);
        return s.Length > 0 ? s : throw Invalid("'" + at + field + "' must be a non-empty string");
    }

    private static string SpecId(JsonObject obj, string field, string at)
    {
        var s = String(obj, field, at);
        return IdPatterns.IsUpperId(s, 64) ? s : throw Invalid("'" + at + field + "' must match ^[A-Z0-9][A-Z0-9_-]{0,63}$");
    }

    private static long Integer(JsonObject obj, string field, string at, long min, long max)
    {
        Get(obj, field, out var v);
        var n = v as JsonNumber;
        if (n is null || !n.IsInteger || n.Value < min || n.Value > max)
        {
            throw Invalid(
                "'" + at + field + "' must be an integer token from " + min.ToString(CultureInfo.InvariantCulture)
                + " to " + max.ToString(CultureInfo.InvariantCulture));
        }

        return (long)n.Value;
    }

    private static int Enum(JsonObject obj, string field, string at, string[] words)
    {
        Get(obj, field, out var v);
        var index = v is JsonString s ? System.Array.IndexOf(words, s.Value) : -1;
        return index >= 0 ? index : throw Invalid("'" + at + field + "' must be one of " + string.Join(", ", words));
    }

    private static IReadOnlyList<JsonValue> Array(JsonObject obj, string field, string at)
    {
        Get(obj, field, out var v);
        return (v as JsonArray)?.Items ?? throw Invalid("'" + at + field + "' must be an array");
    }

    /// <summary>Exactly <c>[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z</c>, ASCII digits only.</summary>
    private static string Timestamp(JsonObject obj, string field, string at)
    {
        const string Shape = "dddd-dd-ddTdd:dd:ddZ";
        Get(obj, field, out var v);
        var s = (v as JsonString)?.Value;
        if (s is null || s.Length != Shape.Length)
        {
            throw Invalid("'" + at + field + "' must look like 2026-11-08T09:00:00Z");
        }

        for (var i = 0; i < Shape.Length; i++)
        {
            if (Shape[i] == 'd' ? s[i] is < '0' or > '9' : s[i] != Shape[i])
            {
                throw Invalid("'" + at + field + "' must look like 2026-11-08T09:00:00Z");
            }
        }

        return s;
    }

    /// <summary>Lowercase 8-4-4-4-12 hexadecimal, exactly the schema's <c>guid</c> pattern.</summary>
    private static Guid GuidField(JsonObject obj, string field, string at)
    {
        Get(obj, field, out var v);
        var s = (v as JsonString)?.Value;
        if (s is null || s.Length != 36)
        {
            throw Invalid("'" + at + field + "' must be a lowercase GUID like 3f2504e0-4f89-11d3-9a0c-0305e82c3301");
        }

        for (var i = 0; i < 36; i++)
        {
            if (i is 8 or 13 or 18 or 23 ? s[i] != '-' : !IsLowerHex(s[i]))
            {
                throw Invalid("'" + at + field + "' must be a lowercase GUID like 3f2504e0-4f89-11d3-9a0c-0305e82c3301");
            }
        }

        return Guid.ParseExact(s, "D");
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

    // ---- writing

    private static JsonObject Obj(params (string Key, JsonValue Value)[] members)
    {
        var list = new List<KeyValuePair<string, JsonValue>>(members.Length);
        var byKey = new Dictionary<string, JsonValue>(StringComparer.Ordinal);
        foreach (var (key, value) in members)
        {
            list.Add(new KeyValuePair<string, JsonValue>(key, value));
            byKey.Add(key, value);
        }

        return new JsonObject(list, byKey);
    }

    private static JsonString Str(string value) => new(value);

    private static JsonValue NullableStr(string? value) => value is null ? JsonNull.Instance : new JsonString(value);

    private static JsonNumber Int(int value) => new(value.ToString(CultureInfo.InvariantCulture), value, isInteger: true);

    private static JsonValue GuidValue(Guid? guid)
        => guid.HasValue ? new JsonString(guid.Value.ToString("D", CultureInfo.InvariantCulture)) : JsonNull.Instance;

    private static string Word(string[] words, int value, string what)
        => value >= 0 && value < words.Length
            ? words[value]
            : throw new InvalidOperationException("Run journal cannot be written: undefined " + what + " value " + value.ToString(CultureInfo.InvariantCulture) + ".");
}

/// <summary>A journal that breaks a schema rule.</summary>
internal sealed class JournalInvalidException : Exception
{
    public JournalInvalidException(string message)
        : base(message)
    {
    }
}
