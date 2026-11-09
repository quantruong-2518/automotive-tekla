using System;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading;
using TeklaHarness.Core.Json;
using Xunit;

namespace TeklaHarness.Core.Tests;

/// <summary>
/// Strict JSON profile, ADR-0010 Amendment 1 §1. The dangerous direction is a false "accept":
/// a value the Python validator saw differently (or not at all) reaching the builder.
/// </summary>
public class StrictJsonTests
{
    private static JsonValue Accept(byte[] bytes)
    {
        var ok = StrictJson.TryParse(bytes, out var value, out var error);
        Assert.True(ok, error);
        Assert.NotNull(value);
        Assert.Equal(string.Empty, error);
        return value!;
    }

    private static JsonValue Accept(string text) => Accept(Encoding.UTF8.GetBytes(text));

    private static string Reject(byte[] bytes)
    {
        var ok = StrictJson.TryParse(bytes, out var value, out var error);
        Assert.False(ok);
        Assert.Null(value);
        Assert.False(string.IsNullOrEmpty(error));
        return error;
    }

    private static string Reject(string text) => Reject(Encoding.UTF8.GetBytes(text));

    private static byte[] Bytes(params int[] values) => values.Select(v => (byte)v).ToArray();

    // ---- shared corpus (tests/fixtures/strict-json): both readers must agree

    public static TheoryData<string> AcceptFiles() => CorpusFiles("accept");

    public static TheoryData<string> RejectFiles() => CorpusFiles("reject");

    private static TheoryData<string> CorpusFiles(string verdict)
    {
        var data = new TheoryData<string>();
        foreach (var file in Directory.GetFiles(Path.Combine(RepoPaths.StrictJsonCorpus, verdict)).OrderBy(f => f, StringComparer.Ordinal))
        {
            data.Add(verdict + "/" + Path.GetFileName(file));
        }

        return data;
    }

    [Theory]
    [MemberData(nameof(AcceptFiles))]
    public void Corpus_accept_files_parse(string file)
        => Accept(File.ReadAllBytes(Path.Combine(RepoPaths.StrictJsonCorpus, file)));

    [Theory]
    [MemberData(nameof(RejectFiles))]
    public void Corpus_reject_files_are_rejected(string file)
        => Reject(File.ReadAllBytes(Path.Combine(RepoPaths.StrictJsonCorpus, file)));

    [Fact]
    public void Corpus_is_discovered()
    {
        Assert.True(AcceptFiles().Count >= 9);
        Assert.True(RejectFiles().Count >= 45);
    }

    // ---- value parity with Python (tests/strict_json_values.py, ADR-0010 Amendment 1 §8)

    /// <summary>Canonical dump, the same format as <c>tests/strict_json_values.py</c>.</summary>
    internal static string Dump(JsonValue value)
    {
        var sb = new StringBuilder();
        DumpInto(sb, value);
        return sb.ToString();
    }

    private static void DumpInto(StringBuilder sb, JsonValue value)
    {
        switch (value)
        {
            case JsonObject o:
                sb.Append("object ").Append(o.Members.Count.ToString(CultureInfo.InvariantCulture)).Append('\n');
                foreach (var member in o.Members)
                {
                    sb.Append("key ").Append(Utf16(member.Key)).Append('\n');
                    DumpInto(sb, member.Value);
                }

                break;
            case JsonArray a:
                sb.Append("array ").Append(a.Items.Count.ToString(CultureInfo.InvariantCulture)).Append('\n');
                foreach (var item in a.Items)
                {
                    DumpInto(sb, item);
                }

                break;
            case JsonString s:
                sb.Append("string ").Append(Utf16(s.Value)).Append('\n');
                break;
            case JsonNumber n:
                sb.Append(n.IsInteger ? "int " : "float ").Append(Bits(n.Value)).Append('\n');
                break;
            case JsonBool b:
                sb.Append(b.Value ? "true" : "false").Append('\n');
                break;
            default:
                sb.Append("null").Append('\n');
                break;
        }
    }

    private static string Utf16(string text)
        => text.Length == 0 ? "-" : string.Concat(text.Select(c => ((int)c).ToString("x4", CultureInfo.InvariantCulture)));

    internal static string Bits(double value)
        => ((ulong)BitConverter.DoubleToInt64Bits(value)).ToString("x16", CultureInfo.InvariantCulture);

    [Theory]
    [MemberData(nameof(AcceptFiles))]
    public void Corpus_accept_files_read_the_same_values_as_python(string file)
    {
        var expectedPath = Path.Combine(RepoPaths.StrictJsonCorpus, "values", Path.GetFileNameWithoutExtension(file) + ".txt");
        Assert.True(File.Exists(expectedPath), "no Python value dump for " + file);
        var actual = Dump(Accept(File.ReadAllBytes(Path.Combine(RepoPaths.StrictJsonCorpus, file))));
        var expected = File.ReadAllText(expectedPath, new UTF8Encoding(false, true));
        if (!string.Equals(expected, actual, StringComparison.Ordinal))
        {
            // Name the first differing line instead of dumping thousands.
            var e = expected.Split('\n');
            var a = actual.Split('\n');
            var i = 0;
            while (i < e.Length && i < a.Length && string.Equals(e[i], a[i], StringComparison.Ordinal))
            {
                i++;
            }

            Assert.Fail("line " + (i + 1).ToString(CultureInfo.InvariantCulture) + ": expected '" + (i < e.Length ? e[i] : "<end>") + "', got '" + (i < a.Length ? a[i] : "<end>") + "'");
        }
    }

    [Fact]
    public void Every_python_value_dump_has_its_accept_file()
    {
        foreach (var dump in Directory.GetFiles(Path.Combine(RepoPaths.StrictJsonCorpus, "values")))
        {
            Assert.True(File.Exists(Path.Combine(RepoPaths.StrictJsonCorpus, "accept", Path.GetFileNameWithoutExtension(dump) + ".json")), dump);
        }
    }

    [Fact]
    public void Number_parity_corpus_is_present()
        => Assert.True(File.Exists(Path.Combine(RepoPaths.StrictJsonCorpus, "accept", "number_parity.json")));

    // ---- correctly rounded decimal to double, bit for bit equal to Python float() (reference values from CPython)

    [Theory]
    [InlineData("0", "0000000000000000")]
    [InlineData("-0", "0000000000000000")] // Python int 0
    [InlineData("0.0", "0000000000000000")]
    [InlineData("-0.0", "8000000000000000")]
    [InlineData("-0e5", "8000000000000000")]
    [InlineData("-0E-5", "8000000000000000")]
    [InlineData("0e999999999999999999", "0000000000000000")]
    [InlineData("1e-999999999999999999", "0000000000000000")]
    [InlineData("-1e-400", "8000000000000000")]
    [InlineData("1e-400", "0000000000000000")]
    [InlineData("4.9406564584124654e-324", "0000000000000001")]
    [InlineData("5e-324", "0000000000000001")]
    [InlineData("3e-324", "0000000000000001")]
    [InlineData("9.99e-324", "0000000000000002")]
    [InlineData("1.0e-324", "0000000000000000")]
    [InlineData("2.4703282292062327e-324", "0000000000000000")]
    [InlineData("2.4703282292062328e-324", "0000000000000001")]
    [InlineData("2.4703282292062327208828439643411068618252990130716238221279284125033775364e-324", "0000000000000001")]
    [InlineData("2.2250738585072011e-308", "000fffffffffffff")]
    [InlineData("2.2250738585072014e-308", "0010000000000000")]
    [InlineData("2.225073858507201136057409796709131975934819546351645648e-308", "000fffffffffffff")]
    [InlineData("1.7976931348623157e308", "7fefffffffffffff")]
    [InlineData("1.7976931348623158e308", "7fefffffffffffff")]
    [InlineData("1.7976931348623158079e308", "7fefffffffffffff")]
    [InlineData("1.00000000000000011102230246251565404236316680908203125", "3ff0000000000000")] // tie, to even
    [InlineData("1.00000000000000033306690738754696212708950042724609375", "3ff0000000000002")] // tie, to even (up)
    [InlineData("123456789012345678901234567890.0", "45f8ee90ff6c373e")]
    [InlineData("9007199254740993.0", "4340000000000000")]
    [InlineData("9007199254740995.0", "4340000000000002")]
    [InlineData("9.178631892786", "40225b75a3b313af")] // net48 double.Parse is 1 ULP off on these
    [InlineData("95249.8484716936", "40f7411d93570df9")]
    [InlineData("123080.6001311378718", "40fe0c899a231ba8")]
    [InlineData("1.5", "3ff8000000000000")]
    [InlineData("-2.5e3", "c0a3880000000000")]
    [InlineData("0.1", "3fb999999999999a")]
    [InlineData("1e23", "44b52d02c7e14af6")]
    [InlineData("8.41e21", "447c7e83209e90b2")]
    [InlineData("1E+2", "4059000000000000")]
    [InlineData("9007199254740992", "4340000000000000")]
    [InlineData("-9007199254740992", "c340000000000000")]
    public void Converts_number_tokens_to_the_same_bits_as_python(string token, string bits)
        => Assert.Equal(bits, Bits(Assert.IsType<JsonNumber>(Assert.IsType<JsonArray>(Accept("[" + token + "]")).Items[0]).Value));

    [Fact]
    public void Exact_halfway_cases_beyond_768_digits()
    {
        // 1 + 2^-53 (a tie, to even: 1.0) followed by a non-zero digit far beyond 800 digits rounds up.
        const string Tie = "1.00000000000000011102230246251565404236316680908203125";
        Assert.Equal("3ff0000000000000", Bits(((JsonNumber)Accept(Tie + new string('0', 900))).Value));
        Assert.Equal("3ff0000000000001", Bits(((JsonNumber)Accept(Tie + new string('0', 900) + "1")).Value));

        Assert.Equal("3ff0000000000001", Bits(((JsonNumber)Accept(Tie + new string('0', 900) + "11")).Value));

        // The same tie written as a long integer part: dropped integer digits scale and stick.
        const string TieDigits = "100000000000000011102230246251565404236316680908203125"; // (1 + 2^-53) * 10^53
        Assert.Equal("3ff0000000000000", Bits(((JsonNumber)Accept(TieDigits + new string('0', 900) + ".0e-953")).Value));
        Assert.Equal("3ff0000000000001", Bits(((JsonNumber)Accept(TieDigits + new string('0', 900) + "1.0e-954")).Value));
        Assert.Equal("3ff0000000000001", Bits(((JsonNumber)Accept(TieDigits + new string('0', 900) + "11.0e-955")).Value));
        Assert.Equal("4a511b0ec57e649a", Bits(((JsonNumber)Accept("1" + new string('0', 900) + ".0e-850")).Value)); // 1e50

        // Largest power of ten the converter needs: 800 kept digits, a sticky tail, value near 1e-324.
        Assert.Equal("0000000000000000", Bits(((JsonNumber)Accept("1." + new string('0', 799) + "1e-324")).Value));

        // 2^-1075 exactly: half the smallest subnormal, a tie to even (0); a hair more rounds up.
        var five = System.Numerics.BigInteger.Pow(5, 1075).ToString(CultureInfo.InvariantCulture);
        var halfMin = "0." + new string('0', 1075 - five.Length) + five;
        Assert.Equal("0000000000000000", Bits(((JsonNumber)Accept(halfMin)).Value));
        Assert.Equal("0000000000000001", Bits(((JsonNumber)Accept(halfMin + "1")).Value));
        Assert.Equal("8000000000000000", Bits(((JsonNumber)Accept("-" + halfMin)).Value));

        // 2^1024 - 2^970 exactly: the tie between MaxValue and 2^1024 rounds to 2^1024, so it is refused.
        var tieMax = (System.Numerics.BigInteger.Pow(2, 1024) - System.Numerics.BigInteger.Pow(2, 970)).ToString(CultureInfo.InvariantCulture);
        Assert.Contains("finite", Reject(tieMax + ".0"), StringComparison.Ordinal);
        Assert.Contains("finite", Reject("-" + tieMax + ".0"), StringComparison.Ordinal);
        var belowTie = (System.Numerics.BigInteger.Pow(2, 1024) - System.Numerics.BigInteger.Pow(2, 970) - 1).ToString(CultureInfo.InvariantCulture);
        Assert.Equal("7fefffffffffffff", Bits(((JsonNumber)Accept(belowTie + ".0")).Value));
        Assert.Equal("ffefffffffffffff", Bits(((JsonNumber)Accept("-" + belowTie + ".0")).Value));
    }

    [Theory]
    [InlineData("1e309")]
    [InlineData("2e308")]
    [InlineData("1e999999999999999999")]
    [InlineData("-1e999999999999999999")]
    [InlineData("1.7976931348623159e308")]
    public void Refuses_tokens_that_round_to_infinity(string token)
        => Assert.Contains("finite", Reject("[" + token + "]"), StringComparison.Ordinal);

#if NET
    /// <summary>
    /// .NET Core 3.0+ <c>double.Parse</c> is correctly rounded (IEEE), so on net10 it is a second
    /// reference for random tokens. Not on net48, whose parser is the reason the converter exists.
    /// </summary>
    [Fact]
    public void Random_tokens_match_the_correctly_rounded_runtime_parser()
    {
        var random = new Random(20261108);
        for (var n = 0; n < 50_000; n++)
        {
            var digits = new StringBuilder();
            digits.Append((char)('1' + random.Next(9)));
            var length = random.Next(1, n % 10 == 0 ? 40 : 20);
            for (var k = 1; k < length; k++)
            {
                digits.Append((char)('0' + random.Next(10)));
            }

            var point = random.Next(1, digits.Length + 1);
            var token = (random.Next(2) == 0 ? "-" : string.Empty)
                + digits.ToString(0, point) + (point < digits.Length ? "." + digits.ToString(point, digits.Length - point) : ".0")
                + "e" + random.Next(-345, 310).ToString(CultureInfo.InvariantCulture);
            var expected = double.Parse(token, NumberStyles.Float, CultureInfo.InvariantCulture);
            if (double.IsInfinity(expected))
            {
                Reject("[" + token + "]");
            }
            else
            {
                Assert.True(
                    Bits(expected) == Bits(((JsonNumber)Accept(token)).Value),
                    token + ": expected " + Bits(expected));
            }
        }
    }
#endif

    [Fact]
    public void Long_tokens_are_handled()
    {
        Assert.Equal("0000000000000000", Bits(((JsonNumber)Accept("0." + new string('0', 100_000) + "1")).Value));
        Assert.Contains("finite", Reject("1" + new string('0', 100_000) + ".0"), StringComparison.Ordinal);
        Assert.Equal("3ff0000000000000", Bits(((JsonNumber)Accept("1." + new string('0', 100_000))).Value));
        Assert.Equal(
            Bits(1.0 / 3.0),
            Bits(((JsonNumber)Accept("0." + new string('3', 100_000))).Value));
    }

    // ---- value tree

    [Fact]
    public void Object_keeps_members_in_document_order_with_their_kinds()
    {
        var root = Assert.IsType<JsonObject>(Accept("{\"b\":1,\"a\":[true,false,null],\"c\":\"x\",\"d\":{}}"));
        Assert.Equal(JsonKind.Object, root.Kind);
        Assert.Equal(new[] { "b", "a", "c", "d" }, root.Members.Select(m => m.Key));

        Assert.True(root.TryGet("a", out var a));
        var array = Assert.IsType<JsonArray>(a);
        Assert.Equal(JsonKind.Array, array.Kind);
        Assert.Equal(new[] { JsonKind.Bool, JsonKind.Bool, JsonKind.Null }, array.Items.Select(i => i.Kind));
        Assert.True(Assert.IsType<JsonBool>(array.Items[0]).Value);
        Assert.False(Assert.IsType<JsonBool>(array.Items[1]).Value);
        Assert.Same(JsonNull.Instance, array.Items[2]);

        Assert.True(root.TryGet("c", out var c));
        Assert.Equal(JsonKind.String, c!.Kind);
        Assert.Equal("x", Assert.IsType<JsonString>(c).Value);

        Assert.True(root.TryGet("d", out var d));
        Assert.Empty(Assert.IsType<JsonObject>(d).Members);

        Assert.False(root.TryGet("B", out var missing)); // keys are ordinal
        Assert.Null(missing);
    }

    [Fact]
    public void Literals_at_top_level()
    {
        Assert.True(Assert.IsType<JsonBool>(Accept("true")).Value);
        Assert.False(Assert.IsType<JsonBool>(Accept("false")).Value);
        Assert.Equal(JsonKind.Null, Accept("null").Kind);
        Assert.Empty(Assert.IsType<JsonArray>(Accept("[]")).Items);
        Assert.Equal(string.Empty, Assert.IsType<JsonString>(Accept("\"\"")).Value);
    }

    [Theory]
    [InlineData("tru")]
    [InlineData("fals")]
    [InlineData("nul")]
    [InlineData("trUe")]
    [InlineData("falsy")]
    [InlineData("nulL")]
    [InlineData("truex")]
    [InlineData("[nulls]")]
    public void Rejects_broken_literals(string text) => Reject(text);

    // ---- numbers

    [Theory]
    [InlineData("0", 0.0, true)]
    [InlineData("-0", 0.0, true)]
    [InlineData("7", 7.0, true)]
    [InlineData("-12", -12.0, true)]
    [InlineData("1.5", 1.5, false)]
    [InlineData("-1.5e10", -1.5e10, false)]
    [InlineData("1E-5", 1e-5, false)]
    [InlineData("2.5e+3", 2500.0, false)]
    [InlineData("1e2", 100.0, false)]
    [InlineData("1.0", 1.0, false)]
    [InlineData("0.25", 0.25, false)]
    [InlineData("9007199254740992", 9007199254740992.0, true)]
    [InlineData("-9007199254740992", -9007199254740992.0, true)]
    [InlineData("9007199254740993.0", 9007199254740992.0, false)] // only integer tokens are bounded
    [InlineData("1e16", 1e16, false)]
    [InlineData("1.7976931348623157e308", double.MaxValue, false)]
    [InlineData("1e-400", 0.0, false)] // underflow is finite
    public void Parses_numbers_with_raw_token_value_and_integer_flag(string token, double expected, bool isInteger)
    {
        var number = Assert.IsType<JsonNumber>(Accept("[" + token + "]") is JsonArray a ? a.Items[0] : null);
        Assert.Equal(JsonKind.Number, number.Kind);
        Assert.Equal(token, number.Raw);
        Assert.Equal(expected, number.Value);
        Assert.Equal(isInteger, number.IsInteger);
    }

    [Theory]
    [InlineData("9007199254740993")]
    [InlineData("-9007199254740993")]
    [InlineData("9007199254740999")]
    [InlineData("10000000000000000")]
    [InlineData("12345678901234567890")] // beyond Int64
    [InlineData("-99999999999999999999")]
    public void Rejects_integer_tokens_beyond_2_pow_53(string token)
        => Assert.Contains("2^53", Reject("[" + token + "]"), StringComparison.Ordinal);

    [Theory]
    [InlineData("1e400")]
    [InlineData("-1e400")]
    [InlineData("1.7976931348623159e308")] // rounds to infinity
    [InlineData("2e308")]
    public void Rejects_numbers_that_are_not_finite_doubles(string token)
        => Assert.Contains("finite", Reject("[" + token + "]"), StringComparison.Ordinal);

    [Theory]
    [InlineData("-")]
    [InlineData("-a")]
    [InlineData("--1")]
    [InlineData("+1")]
    [InlineData("01")]
    [InlineData("-01")]
    [InlineData("00")]
    [InlineData(".5")]
    [InlineData("1.")]
    [InlineData("1.e5")]
    [InlineData("1e")]
    [InlineData("1e+")]
    [InlineData("1E-")]
    [InlineData("1ee5")]
    [InlineData("0x10")]
    [InlineData("1_000")]
    [InlineData("NaN")]
    [InlineData("Infinity")]
    [InlineData("-Infinity")]
    [InlineData("1.5.2")]
    public void Rejects_number_grammar_errors(string token) => Reject("[" + token + "]");

    // ---- strings and escapes

    [Theory]
    [InlineData("\"\\u0041\"", "A")]
    [InlineData("\"\\u00e9\\u00E9\"", "éé")]
    [InlineData("\"\\uD83D\\uDE00\"", "\U0001F600")]
    [InlineData("\"\\ud83d\\ude00\"", "\U0001F600")]
    [InlineData("\"\\u0001\\u001f\"", "\u0001\u001f")] // escaped controls other than U+0000 are allowed
    [InlineData("\"\\\"\\\\\\/\\b\\f\\n\\r\\t\"", "\"\\/\b\f\n\r\t")]
    [InlineData("\"a\u007fb\"", "a\u007fb")] // DEL is not a control character in JSON
    [InlineData("\" ~\"", " ~")]
    [InlineData("\"\\uFFFF\\uE000\\uD7FF\"", "\uFFFF\uE000\uD7FF")]
    public void Decodes_escapes(string json, string expected)
        => Assert.Equal(expected, Assert.IsType<JsonString>(Accept(json)).Value);

    [Theory]
    [InlineData("\"\\ud800\\u0041\"")] // high surrogate then a letter
    [InlineData("\"\\udc00\\ud800\"")] // low then high
    [InlineData("\"\\ud800\\ud800\"")] // high then high
    [InlineData("\"\\ud800\"")]
    [InlineData("\"\\ud800x\"")]
    [InlineData("\"\\ud800\\n\"")]
    [InlineData("\"\\udbff\"")]
    [InlineData("\"\\udc00\"")]
    [InlineData("\"\\udfff\"")]
    [InlineData("\"\\ud800\\udbff\"")]
    [InlineData("\"\\ud800\\ue000\"")]
    public void Rejects_lone_surrogate_escapes(string json)
        => Assert.Contains("surrogate", Reject(json), StringComparison.Ordinal);

    [Theory]
    [InlineData("\"\\u0000\"")]
    [InlineData("{\"\\u0000\":1}")]
    [InlineData("\"a\\u0000b\"")]
    public void Rejects_escaped_nul(string json)
        => Assert.Contains("U+0000", Reject(json), StringComparison.Ordinal);

    [Theory]
    [InlineData("\"\\x41\"")]
    [InlineData("\"\\a\"")]
    [InlineData("\"\\U0041\"")]
    [InlineData("\"\\u12\"")]
    [InlineData("\"\\u12G4\"")]
    [InlineData("\"\\u00g0\"")]
    [InlineData("\"\\u/000\"")]
    [InlineData("\"\\u:000\"")]
    [InlineData("\"\\u@000\"")]
    [InlineData("\"\\uG000\"")]
    [InlineData("\"\\u`000\"")]
    [InlineData("\"\\ug000\"")]
    [InlineData("\"\\u")]
    [InlineData("\"\\")]
    [InlineData("\"\\ud800\\u")]
    [InlineData("\"\\ud800\\")]
    public void Rejects_invalid_escapes(string json) => Reject(json);

    [Fact]
    public void Accepts_every_hex_digit_case()
        => Assert.Equal("\u0123\u4567\u89ab\ucdef\uABCD\uEF01", Assert.IsType<JsonString>(Accept("\"\\u0123\\u4567\\u89ab\\ucdef\\uABCD\\uEF01\"")).Value);

    [Theory]
    [InlineData(0x00)]
    [InlineData(0x01)]
    [InlineData(0x09)]
    [InlineData(0x0A)]
    [InlineData(0x0D)]
    [InlineData(0x1F)]
    public void Rejects_raw_control_characters_in_strings(int b)
        => Assert.Contains("control", Reject(Bytes('"', 'a', b, '"')), StringComparison.Ordinal);

    [Fact]
    public void Accepts_space_raw_in_strings()
        => Assert.Equal("a b", Assert.IsType<JsonString>(Accept(Bytes('"', 'a', 0x20, 'b', '"'))).Value);

    [Theory]
    [InlineData("\"abc")]
    [InlineData("\"")]
    [InlineData("[\"a]")]
    [InlineData("{\"a")]
    public void Rejects_unterminated_strings(string json) => Reject(json);

    // ---- UTF-8: own decoder, the same on net48 and net10 (Unicode Table 3-7)

    public static TheoryData<int[], int> ValidUtf8() => new()
    {
        { new[] { 0xC2, 0x80 }, 0x80 },
        { new[] { 0xDF, 0xBF }, 0x7FF },
        { new[] { 0xE0, 0xA0, 0x80 }, 0x800 },
        { new[] { 0xE0, 0xBF, 0xBF }, 0xFFF },
        { new[] { 0xE1, 0x80, 0x80 }, 0x1000 },
        { new[] { 0xEC, 0xBF, 0xBF }, 0xCFFF },
        { new[] { 0xED, 0x80, 0x80 }, 0xD000 },
        { new[] { 0xED, 0x9F, 0xBF }, 0xD7FF },
        { new[] { 0xEE, 0x80, 0x80 }, 0xE000 },
        { new[] { 0xEF, 0xBF, 0xBF }, 0xFFFF },
        { new[] { 0xF0, 0x90, 0x80, 0x80 }, 0x10000 },
        { new[] { 0xF0, 0xBF, 0xBF, 0xBF }, 0x3FFFF },
        { new[] { 0xF1, 0x80, 0x80, 0x80 }, 0x40000 },
        { new[] { 0xF3, 0xBF, 0xBF, 0xBF }, 0xFFFFF },
        { new[] { 0xF4, 0x80, 0x80, 0x80 }, 0x100000 },
        { new[] { 0xF4, 0x8F, 0xBF, 0xBF }, 0x10FFFF },
        { new[] { 0xE1, 0xBB, 0x99 }, 0x1ED9 }, // "ộ"
    };

    [Theory]
    [MemberData(nameof(ValidUtf8))]
    public void Decodes_valid_utf8_sequences(int[] sequence, int codePoint)
    {
        var bytes = new[] { (int)'"' }.Concat(sequence).Concat(new[] { (int)'"' }).ToArray();
        Assert.Equal(char.ConvertFromUtf32(codePoint), Assert.IsType<JsonString>(Accept(Bytes(bytes))).Value);
    }

    public static TheoryData<int[]> InvalidUtf8() => new()
    {
        new[] { 0x80 }, // lone continuation
        new[] { 0xBF },
        new[] { 0xC0, 0x80 }, // overlong 2-byte
        new[] { 0xC0, 0xAF },
        new[] { 0xC1, 0xBF },
        new[] { 0xC2, 0x7F }, // bad continuation
        new[] { 0xC2, 0xC0 },
        new[] { 0xDF, 0x41 },
        new[] { 0xE0, 0x80, 0x80 }, // overlong 3-byte
        new[] { 0xE0, 0x9F, 0xBF },
        new[] { 0xE0, 0xC0, 0x80 },
        new[] { 0xE0, 0xA0, 0x7F },
        new[] { 0xE0, 0xA0, 0xC0 },
        new[] { 0xE1, 0x7F, 0x80 },
        new[] { 0xE1, 0xC0, 0x80 },
        new[] { 0xE1, 0x80, 0x7F },
        new[] { 0xEC, 0x80, 0xC0 },
        new[] { 0xED, 0xA0, 0x80 }, // encoded surrogates
        new[] { 0xED, 0xBF, 0xBF },
        new[] { 0xED, 0x7F, 0x80 },
        new[] { 0xEE, 0x7F, 0x80 },
        new[] { 0xEF, 0xC0, 0x80 },
        new[] { 0xF0, 0x80, 0x80, 0x80 }, // overlong 4-byte
        new[] { 0xF0, 0x8F, 0xBF, 0xBF },
        new[] { 0xF0, 0xC0, 0x80, 0x80 },
        new[] { 0xF0, 0x90, 0x7F, 0x80 },
        new[] { 0xF0, 0x90, 0x80, 0x7F },
        new[] { 0xF0, 0x90, 0x80, 0xC0 },
        new[] { 0xF1, 0x7F, 0x80, 0x80 },
        new[] { 0xF3, 0xC0, 0x80, 0x80 },
        new[] { 0xF4, 0x90, 0x80, 0x80 }, // above U+10FFFF
        new[] { 0xF4, 0x7F, 0x80, 0x80 },
        new[] { 0xF5, 0x80, 0x80, 0x80 },
        new[] { 0xF7, 0xBF, 0xBF, 0xBF },
        new[] { 0xF8, 0x88, 0x80, 0x80, 0x80 },
        new[] { 0xFE },
        new[] { 0xFF },
    };

    [Theory]
    [MemberData(nameof(InvalidUtf8))]
    public void Rejects_invalid_utf8_inside_strings(int[] sequence)
    {
        var bytes = new[] { (int)'"' }.Concat(sequence).Concat(new[] { (int)'"' }).ToArray();
        Assert.Contains("UTF-8", Reject(Bytes(bytes)), StringComparison.Ordinal);
    }

    [Theory]
    [InlineData(new[] { 0xC2 })]
    [InlineData(new[] { 0xE1, 0x80 })]
    [InlineData(new[] { 0xF0, 0x90, 0x80 })]
    [InlineData(new[] { 0xE1 })]
    public void Rejects_utf8_truncated_at_end_of_input(int[] sequence)
        => Reject(Bytes(new[] { (int)'"' }.Concat(sequence).ToArray()));

    [Theory]
    [InlineData(new[] { 0xC3, 0xA9 })]
    [InlineData(new[] { 0xFF })]
    [InlineData(new[] { 0x80 })]
    public void Rejects_non_ascii_bytes_outside_strings(int[] sequence)
        => Reject(Bytes(new[] { (int)'[' }.Concat(sequence).Concat(new[] { (int)']' }).ToArray()));

    // ---- BOM, whitespace, structure

    [Fact]
    public void Rejects_a_bom_and_says_so()
        => Assert.Contains("byte order mark", Reject(Bytes(0xEF, 0xBB, 0xBF, '1')), StringComparison.Ordinal);

    [Theory]
    [InlineData(new[] { 0xEF, 0xBB, '1' })]
    [InlineData(new[] { 0xEF, '1' })]
    [InlineData(new[] { 0xEF, 0xBB, 0xBE, '1' })]
    [InlineData(new[] { 0xEF, 0xBA, 0xBF, '1' })]
    [InlineData(new[] { 0xEE, 0xBB, 0xBF, '1' })]
    public void Partial_bom_is_rejected_as_a_syntax_error(int[] bytes)
        => Assert.DoesNotContain("byte order mark", Reject(Bytes(bytes)), StringComparison.Ordinal);

    [Fact]
    public void Accepts_the_four_json_whitespace_characters_everywhere()
    {
        var root = Assert.IsType<JsonObject>(Accept(" \t\r\n{ \t\r\n\"a\" \t\r\n: \t\r\n[ \t\r\n1 \t\r\n, \t\r\n2 \t\r\n] \t\r\n, \"b\":{ } } \t\r\n"));
        Assert.Equal(2, root.Members.Count);
    }

    [Theory]
    [InlineData(0x0B)] // vertical tab
    [InlineData(0x0C)] // form feed
    [InlineData(0xA0)] // NBSP byte
    [InlineData(0x00)]
    public void Rejects_other_whitespace(int b)
    {
        Reject(Bytes(b, '1'));
        Reject(Bytes('1', b));
        Reject(Bytes('[', b, '1', ']'));
    }

    [Theory]
    [InlineData("")]
    [InlineData(" ")]
    [InlineData("[")]
    [InlineData("]")]
    [InlineData("{")]
    [InlineData("}")]
    [InlineData("[1")]
    [InlineData("[1,")]
    [InlineData("[1 2]")]
    [InlineData("[1,]")]
    [InlineData("[,1]")]
    [InlineData("[1}")]
    [InlineData("{\"a\":1]")]
    [InlineData("{\"a\" 1}")]
    [InlineData("{\"a\"")]
    [InlineData("{\"a\":")]
    [InlineData("{\"a\":}")]
    [InlineData("{\"a\":1 \"b\":2}")]
    [InlineData("{\"a\":1,}")]
    [InlineData("{,}")]
    [InlineData("{1:1}")]
    [InlineData("{a:1}")]
    [InlineData("{'a':1}")]
    [InlineData("{\"a\":1}}")]
    [InlineData("[]]")]
    [InlineData("{} {}")]
    [InlineData("1 2")]
    [InlineData("\"a\" \"b\"")]
    [InlineData("// c\n1")]
    [InlineData("/* c */1")]
    public void Rejects_structure_errors(string json) => Reject(json);

    [Theory]
    [InlineData("{\"a\":1,\"a\":1}")]
    [InlineData("{\"a\":1,\"b\":2,\"a\":3}")]
    [InlineData("{\"\\u00e9\":1,\"é\":2}")]
    [InlineData("{\"\":1,\"\":2}")]
    [InlineData("[{\"x\":{\"k\":1,\"k\":2}}]")]
    public void Rejects_duplicate_keys_after_unescaping(string json)
        => Assert.Contains("duplicate", Reject(json), StringComparison.Ordinal);

    [Fact]
    public void Same_key_in_different_objects_is_fine()
        => Accept("[{\"a\":1},{\"a\":2},{\"o\":{\"a\":3},\"a\":4}]");

    // ---- depth: 64 nested containers accepted, 65 rejected

    private static string Nested(int depth, char open, char close, string inner = "")
        => new string(open, depth) + inner + new string(close, depth);

    private static string NestedObjects(int depth)
    {
        var sb = new StringBuilder();
        for (var i = 0; i < depth - 1; i++)
        {
            sb.Append("{\"a\":");
        }

        sb.Append("{}");
        sb.Append('}', depth - 1);
        return sb.ToString();
    }

    [Fact]
    public void Depth_64_is_accepted_and_65_rejected()
    {
        Accept(Nested(64, '[', ']'));
        Accept(Nested(63, '[', ']', "{}"));
        Accept(NestedObjects(64));
        Accept("[" + Nested(63, '[', ']') + "," + Nested(63, '[', ']') + "]"); // siblings do not add up
        Accept("[" + NestedObjects(63) + "," + NestedObjects(63) + "]");
        Assert.Contains("64", Reject(Nested(65, '[', ']')), StringComparison.Ordinal);
        Assert.Contains("64", Reject(Nested(64, '[', ']', "{}")), StringComparison.Ordinal);
        Assert.Contains("64", Reject(NestedObjects(65)), StringComparison.Ordinal);
    }

    [Fact]
    public void Very_deep_input_is_rejected_without_overflowing_the_stack()
        => Reject(Nested(1_000_000, '[', ']'));

    // ---- size: over 16 MiB rejected before parsing

    [Fact]
    public void Input_of_exactly_16_MiB_is_accepted_and_one_byte_more_rejected()
    {
        Assert.Equal(16 * 1024 * 1024, StrictJson.MaxInputBytes);
        Accept(ZeroPaddedTo(StrictJson.MaxInputBytes));
        Assert.Contains("16 MiB", Reject(ZeroPaddedTo(StrictJson.MaxInputBytes + 1)), StringComparison.Ordinal);
    }

    /// <summary>The document <c>0</c> followed by spaces, <paramref name="length"/> bytes in all.</summary>
    internal static byte[] ZeroPaddedTo(int length)
    {
        var bytes = Enumerable.Repeat((byte)' ', length).ToArray();
        bytes[0] = (byte)'0';
        return bytes;
    }

    // ---- exact messages: the engineer reads them, and they pin each rule to its branch

    [Theory]
    [InlineData("{} x", "content after the JSON document at byte 3")]
    [InlineData("[", "unexpected end of input at byte 1")]
    [InlineData("", "unexpected end of input at byte 0")]
    [InlineData("[x]", "unexpected character at byte 1")]
    [InlineData("[1 2]", "expected ']' at byte 3")]
    [InlineData("tru", "expected 'e' at byte 3")]
    [InlineData("{\"a\" 1}", "expected ':' at byte 5")]
    [InlineData("{\"a\":1 \"b\":2}", "expected '}' at byte 7")]
    [InlineData("{x\":1}", "expected a string key at byte 1")]
    [InlineData("{\"a\":1,\"a\":2}", "duplicate key \"a\" at byte 7")]
    [InlineData("\"abc", "unterminated string at byte 4")]
    [InlineData("\"\\x\"", "invalid escape at byte 2")]
    [InlineData("\"\\", "invalid escape at byte 2")]
    [InlineData("\"\\u12G4\"", "invalid \\u escape at byte 5")]
    [InlineData("\"\\udc00\"", "lone low surrogate escape at byte 7")]
    [InlineData("\"\\ud800x\"", "lone high surrogate escape at byte 7")]
    [InlineData("\"\\ud800\\u0041\"", "lone high surrogate escape at byte 13")]
    [InlineData("\"\\u0000\"", "escaped U+0000 at byte 7")]
    [InlineData("\"a\u0001\"", "raw control character in a string at byte 2")]
    [InlineData("-a", "invalid number at byte 1")]
    [InlineData("[1.]", "invalid number: no digit after '.' at byte 3")]
    [InlineData("1e", "invalid number: no digit in the exponent at byte 2")]
    [InlineData("[9007199254740993]", "integer outside ±2^53 at byte 1")]
    [InlineData("[1e400]", "number is not a finite double at byte 1")]
    public void Rejection_messages_name_the_rule_and_the_byte(string json, string expected)
        => Assert.Equal(expected, Reject(json));

    [Theory]
    [InlineData(new[] { '"', 0xFF, '"' }, "invalid UTF-8 lead byte at byte 1")]
    [InlineData(new[] { '"', 0xC2, 0x41, '"' }, "invalid UTF-8 sequence at byte 1")]
    [InlineData(new[] { 0xEF, 0xBB, 0xBF }, "input starts with a UTF-8 byte order mark")]
    [InlineData(new[] { 0xEF, 0xBB, 0xBF, '{', '}' }, "input starts with a UTF-8 byte order mark")]
    public void Byte_level_rejection_messages(int[] bytes, string expected)
        => Assert.Equal(expected, Reject(Bytes(bytes)));

    [Fact]
    public void Depth_and_size_messages()
    {
        Assert.Equal("nesting deeper than 64 at byte 64", Reject(Nested(65, '[', ']')));
        Assert.Equal("input is larger than 16 MiB", Reject(ZeroPaddedTo(StrictJson.MaxInputBytes + 1)));
    }

    [Theory]
    [InlineData("\"\\ud800\\udc00\"", 0x10000)]
    [InlineData("\"\\udbff\\udfff\"", 0x10FFFF)]
    [InlineData("\"\\ud800\\udfff\"", 0x103FF)]
    [InlineData("\"\\udbff\\udc00\"", 0x10FC00)]
    public void Accepts_surrogate_pairs_at_the_range_edges(string json, int codePoint)
        => Assert.Equal(char.ConvertFromUtf32(codePoint), Assert.IsType<JsonString>(Accept(json)).Value);

    [Fact]
    public void Null_input_throws()
        => Assert.Throws<ArgumentNullException>(() => StrictJson.TryParse(null!, out _, out _));

    [Fact]
    public void Error_names_the_byte_offset()
        => Assert.Contains("byte 5", Reject("[1,2,]"), StringComparison.Ordinal);

    // ---- culture must not change any value (ADR-0009 §3)

    [Theory]
    [InlineData("vi-VN")]
    [InlineData("de-DE")]
    [InlineData("tr-TR")]
    [InlineData("")]
    public void Number_values_do_not_depend_on_the_current_culture(string culture)
    {
        var saved = Thread.CurrentThread.CurrentCulture;
        try
        {
            Thread.CurrentThread.CurrentCulture = new CultureInfo(culture);
            var items = Assert.IsType<JsonArray>(Accept("[1.5,-2.5e3,1E-5,6000,0.125]")).Items;
            Assert.Equal(
                new[] { 1.5, -2500.0, 1e-5, 6000.0, 0.125 },
                items.Select(i => Assert.IsType<JsonNumber>(i).Value));
            Reject("[1,5]x");
            Reject("[1,5e400]");
        }
        finally
        {
            Thread.CurrentThread.CurrentCulture = saved;
        }
    }
}
