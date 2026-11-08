using System.Collections.Generic;

namespace TeklaHarness.Core.Json;

/// <summary>Kind of a <see cref="JsonValue"/>.</summary>
internal enum JsonKind
{
    Object,
    Array,
    String,
    Number,
    Bool,
    Null,
}

/// <summary>Immutable JSON value produced by <see cref="StrictJson"/>.</summary>
internal abstract class JsonValue
{
    public abstract JsonKind Kind { get; }
}

/// <summary>Object: members in document order, keys unique (ordinal, after unescaping).</summary>
internal sealed class JsonObject : JsonValue
{
    private readonly Dictionary<string, JsonValue> _byKey;

    public JsonObject(IReadOnlyList<KeyValuePair<string, JsonValue>> members, Dictionary<string, JsonValue> byKey)
    {
        Members = members;
        _byKey = byKey;
    }

    public override JsonKind Kind => JsonKind.Object;

    public IReadOnlyList<KeyValuePair<string, JsonValue>> Members { get; }

    public bool TryGet(string key, out JsonValue? value)
    {
        var found = _byKey.TryGetValue(key, out var v);
        value = v;
        return found;
    }
}

internal sealed class JsonArray : JsonValue
{
    public JsonArray(IReadOnlyList<JsonValue> items) => Items = items;

    public override JsonKind Kind => JsonKind.Array;

    public IReadOnlyList<JsonValue> Items { get; }
}

internal sealed class JsonString : JsonValue
{
    public JsonString(string value) => Value = value;

    public override JsonKind Kind => JsonKind.String;

    public string Value { get; }
}

/// <summary>Number: the raw token, its finite double value, and whether the token is an integer (no fraction, no exponent).</summary>
internal sealed class JsonNumber : JsonValue
{
    public JsonNumber(string raw, double value, bool isInteger)
    {
        Raw = raw;
        Value = value;
        IsInteger = isInteger;
    }

    public override JsonKind Kind => JsonKind.Number;

    public string Raw { get; }

    public double Value { get; }

    /// <summary>True for an integer token; the reader guarantees |value| ≤ 2^53, so <see cref="Value"/> is exact.</summary>
    public bool IsInteger { get; }
}

internal sealed class JsonBool : JsonValue
{
    public static readonly JsonBool True = new(true);
    public static readonly JsonBool False = new(false);

    private JsonBool(bool value) => Value = value;

    public override JsonKind Kind => JsonKind.Bool;

    public bool Value { get; }
}

internal sealed class JsonNull : JsonValue
{
    public static readonly JsonNull Instance = new();

    private JsonNull()
    {
    }

    public override JsonKind Kind => JsonKind.Null;
}
