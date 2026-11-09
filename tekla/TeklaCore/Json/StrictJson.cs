using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace TeklaHarness.Core.Json;

/// <summary>
/// Strict JSON reader (ADR-0010 Amendment 1 §1–§2): RFC 8259 grammar plus the shared profile, the
/// same as the Python strict loader (corpus <c>tests/fixtures/strict-json</c>). Rejects a BOM,
/// invalid UTF-8 (own decoder, identical on .NET Framework and .NET), duplicate keys after
/// unescaping, numbers that are not finite doubles, integer tokens beyond ±2^53, lone surrogates
/// and U+0000 in strings, nesting deeper than 64 and input over 16 MiB.
/// </summary>
internal static class StrictJson
{
    public const int MaxInputBytes = 16 * 1024 * 1024;

    /// <summary>64 nested containers are accepted, 65 rejected.</summary>
    public const int MaxDepth = 64;

    /// <summary>2^53: integer tokens with a larger magnitude are rejected.</summary>
    public const long MaxSafeInteger = 9007199254740992;

    /// <summary>Parses <paramref name="utf8"/>. Never throws for bad input: returns false with a reason.</summary>
    public static bool TryParse(byte[] utf8, out JsonValue? value, out string error)
    {
        if (utf8 is null)
        {
            throw new ArgumentNullException(nameof(utf8));
        }

        value = null;
        if (utf8.Length > MaxInputBytes)
        {
            error = "input is larger than 16 MiB";
            return false;
        }

        if (utf8.Length >= 3 && utf8[0] == 0xEF && utf8[1] == 0xBB && utf8[2] == 0xBF)
        {
            error = "input starts with a UTF-8 byte order mark";
            return false;
        }

        try
        {
            value = new Parser(utf8).ParseDocument();
            error = string.Empty;
            return true;
        }
        catch (RejectedException e)
        {
            error = e.Message;
            return false;
        }
    }

    private sealed class RejectedException : Exception
    {
        public RejectedException(string message)
            : base(message)
        {
        }
    }

    private sealed class Parser
    {
        private readonly byte[] _b;
        private int _pos;
        private int _depth;

        public Parser(byte[] bytes) => _b = bytes;

        public JsonValue ParseDocument()
        {
            SkipWhitespace();
            var value = ParseValue();
            SkipWhitespace();
            if (_pos != _b.Length)
            {
                throw Fail("content after the JSON document");
            }

            return value;
        }

        private RejectedException Fail(string what)
            => new(what + " at byte " + _pos.ToString(CultureInfo.InvariantCulture));

        /// <summary>The byte at the current position, or -1 at the end of input.</summary>
        private int Peek() => _pos < _b.Length ? _b[_pos] : -1;

        private void SkipWhitespace()
        {
            while (Peek() is ' ' or '\t' or '\n' or '\r')
            {
                _pos++;
            }
        }

        private void Expect(char c)
        {
            if (Peek() != c)
            {
                throw Fail("expected '" + c + "'");
            }

            _pos++;
        }

        private JsonValue ParseValue()
        {
            switch (Peek())
            {
                case '{':
                    return ParseObject();
                case '[':
                    return ParseArray();
                case '"':
                    return new JsonString(ParseString());
                case 't':
                    ExpectLiteral("true");
                    return JsonBool.True;
                case 'f':
                    ExpectLiteral("false");
                    return JsonBool.False;
                case 'n':
                    ExpectLiteral("null");
                    return JsonNull.Instance;
                case '-':
                case >= '0' and <= '9':
                    return ParseNumber();
                case -1:
                    throw Fail("unexpected end of input");
                default:
                    throw Fail("unexpected character");
            }
        }

        private void ExpectLiteral(string literal)
        {
            foreach (var c in literal)
            {
                Expect(c);
            }
        }

        private void Enter()
        {
            _depth++;
            if (_depth > MaxDepth)
            {
                throw Fail("nesting deeper than 64");
            }

            _pos++;
            SkipWhitespace();
        }

        private JsonObject ParseObject()
        {
            Enter();
            var members = new List<KeyValuePair<string, JsonValue>>();
            var byKey = new Dictionary<string, JsonValue>(StringComparer.Ordinal);
            if (Peek() != '}')
            {
                while (true)
                {
                    if (Peek() != '"')
                    {
                        throw Fail("expected a string key");
                    }

                    var keyAt = _pos;
                    var key = ParseString();
                    if (byKey.ContainsKey(key))
                    {
                        _pos = keyAt;
                        throw Fail("duplicate key \"" + key + "\"");
                    }

                    SkipWhitespace();
                    Expect(':');
                    SkipWhitespace();
                    var value = ParseValue();
                    byKey.Add(key, value);
                    members.Add(new KeyValuePair<string, JsonValue>(key, value));
                    SkipWhitespace();
                    if (Peek() != ',')
                    {
                        break;
                    }

                    _pos++;
                    SkipWhitespace();
                }
            }

            Expect('}');
            _depth--;
            return new JsonObject(members, byKey);
        }

        private JsonArray ParseArray()
        {
            Enter();
            var items = new List<JsonValue>();
            if (Peek() != ']')
            {
                while (true)
                {
                    items.Add(ParseValue());
                    SkipWhitespace();
                    if (Peek() != ',')
                    {
                        break;
                    }

                    _pos++;
                    SkipWhitespace();
                }
            }

            Expect(']');
            _depth--;
            return new JsonArray(items);
        }

        private string ParseString()
        {
            _pos++; // opening quote
            var sb = new StringBuilder();
            while (true)
            {
                var c = Peek();
                if (c == '"')
                {
                    _pos++;
                    return sb.ToString();
                }

                if (c == -1)
                {
                    throw Fail("unterminated string");
                }

                if (c == '\\')
                {
                    ParseEscape(sb);
                }
                else if (c < 0x20)
                {
                    throw Fail("raw control character in a string");
                }
                else if (c < 0x80)
                {
                    sb.Append((char)c);
                    _pos++;
                }
                else
                {
                    AppendUtf8(sb, c);
                }
            }
        }

        private void ParseEscape(StringBuilder sb)
        {
            _pos++; // backslash
            var e = Peek();
            _pos++;
            switch (e)
            {
                case '"':
                case '\\':
                case '/':
                    sb.Append((char)e);
                    return;
                case 'b':
                    sb.Append('\b');
                    return;
                case 'f':
                    sb.Append('\f');
                    return;
                case 'n':
                    sb.Append('\n');
                    return;
                case 'r':
                    sb.Append('\r');
                    return;
                case 't':
                    sb.Append('\t');
                    return;
                case 'u':
                    break;
                default:
                    _pos--;
                    throw Fail("invalid escape");
            }

            var unit = ReadHex4();
            if (unit is >= 0xDC00 and <= 0xDFFF)
            {
                throw Fail("lone low surrogate escape");
            }

            if (unit is >= 0xD800 and <= 0xDBFF)
            {
                if (Peek() != '\\' || _pos + 1 >= _b.Length || _b[_pos + 1] != 'u')
                {
                    throw Fail("lone high surrogate escape");
                }

                _pos += 2;
                var low = ReadHex4();
                if (low is < 0xDC00 or > 0xDFFF)
                {
                    throw Fail("lone high surrogate escape");
                }

                sb.Append((char)unit).Append((char)low);
                return;
            }

            if (unit == 0)
            {
                throw Fail("escaped U+0000");
            }

            sb.Append((char)unit);
        }

        private int ReadHex4()
        {
            var unit = 0;
            for (var i = 0; i < 4; i++)
            {
                var digit = HexValue(Peek());
                if (digit < 0)
                {
                    throw Fail("invalid \\u escape");
                }

                unit = (unit << 4) | digit;
                _pos++;
            }

            return unit;
        }

        /// <summary>Value of an ASCII hex digit, or -1.</summary>
        private static int HexValue(int h)
        {
            if (h is >= '0' and <= '9')
            {
                return h - '0';
            }

            if (h is >= 'a' and <= 'f')
            {
                return h - 'a' + 10;
            }

            if (h is >= 'A' and <= 'F')
            {
                return h - 'A' + 10;
            }

            return -1;
        }

        /// <summary>Decodes one multi-byte UTF-8 sequence per Unicode Table 3-7 (well-formed sequences only).</summary>
        private void AppendUtf8(StringBuilder sb, int lead)
        {
            if (lead is < 0xC2 or > 0xF4)
            {
                throw Fail("invalid UTF-8 lead byte");
            }

            var count = lead >= 0xF0 ? 3 : lead >= 0xE0 ? 2 : 1;
            var secondLow = lead == 0xE0 ? 0xA0 : lead == 0xF0 ? 0x90 : 0x80; // no overlong forms
            var secondHigh = lead == 0xED ? 0x9F : lead == 0xF4 ? 0x8F : 0xBF; // no surrogates, nothing above U+10FFFF
            var codePoint = lead & ((1 << (6 - count)) - 1); // payload bits of the lead byte
            for (var i = 1; i <= count; i++)
            {
                var low = i == 1 ? secondLow : 0x80;
                var high = i == 1 ? secondHigh : 0xBF;
                var at = _pos + i;
                if (at >= _b.Length || _b[at] < low || _b[at] > high)
                {
                    throw Fail("invalid UTF-8 sequence");
                }

                codePoint = (codePoint << 6) | (_b[at] & 0x3F);
            }

            _pos += count + 1;
            sb.Append(char.ConvertFromUtf32(codePoint));
        }

        private JsonNumber ParseNumber()
        {
            var start = _pos;
            if (Peek() == '-')
            {
                _pos++;
            }

            if (Peek() == '0')
            {
                _pos++;
            }
            else if (!SkipDigits())
            {
                throw Fail("invalid number");
            }

            var isInteger = true;
            if (Peek() == '.')
            {
                isInteger = false;
                _pos++;
                if (!SkipDigits())
                {
                    throw Fail("invalid number: no digit after '.'");
                }
            }

            if (Peek() is 'e' or 'E')
            {
                isInteger = false;
                _pos++;
                if (Peek() is '+' or '-')
                {
                    _pos++;
                }

                if (!SkipDigits())
                {
                    throw Fail("invalid number: no digit in the exponent");
                }
            }

            var raw = Encoding.ASCII.GetString(_b, start, _pos - start);
            if (isInteger)
            {
                var parsed = long.TryParse(raw, NumberStyles.AllowLeadingSign, CultureInfo.InvariantCulture, out var integer);
                if (!parsed || integer > MaxSafeInteger || integer < -MaxSafeInteger)
                {
                    _pos = start;
                    throw Fail("integer outside ±2^53");
                }

                // Exact (|integer| ≤ 2^53); "-0" is the integer 0, so +0.0 as in Python.
                return new JsonNumber(raw, integer, isInteger: true);
            }

            // Not double.Parse: .NET Framework's is not correctly rounded (1 ULP off Python's float()).
            if (!DecimalToDouble.TryConvert(raw, out var value))
            {
                _pos = start;
                throw Fail("number is not a finite double");
            }

            return new JsonNumber(raw, value, isInteger: false);
        }

        /// <summary>Skips one or more ASCII digits; false when there is none.</summary>
        private bool SkipDigits()
        {
            var start = _pos;
            while (Peek() is >= '0' and <= '9')
            {
                _pos++;
            }

            return _pos > start;
        }
    }
}
