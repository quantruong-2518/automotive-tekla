using System;
using System.Globalization;
using System.Text;

namespace TeklaHarness.Core.Json;

/// <summary>
/// Deterministic JSON text, the same bytes as Python's
/// <c>json.dumps(value, indent=2, ensure_ascii=False) + "\n"</c>: two-space indent, <c>": "</c>
/// after keys, empty containers as <c>{}</c>/<c>[]</c>, LF line ends, no BOM, non-ASCII as raw UTF-8,
/// escapes <c>\" \\ \b \f \n \r \t</c> and <c>\u00xx</c> (lowercase hex) for other control
/// characters. Integer numbers only, written as their exact value; the output is not culture-dependent.
/// </summary>
internal static class JsonWriter
{
    private const string HexDigits = "0123456789abcdef";

    /// <summary>Strict UTF-8: a lone surrogate throws instead of becoming U+FFFD.</summary>
    private static readonly UTF8Encoding StrictUtf8 = new(encoderShouldEmitUTF8Identifier: false, throwOnInvalidBytes: true);

    /// <summary>
    /// UTF-8 bytes of <paramref name="value"/>. Throws <see cref="ArgumentException"/> for a
    /// non-integer number or a string with a lone surrogate.
    /// </summary>
    public static byte[] ToUtf8(JsonValue value)
    {
        var sb = new StringBuilder();
        Write(sb, value, 0);
        sb.Append('\n');
        return StrictUtf8.GetBytes(sb.ToString());
    }

    private static void Write(StringBuilder sb, JsonValue value, int depth)
    {
        switch (value)
        {
            case JsonObject o:
                if (o.Members.Count == 0)
                {
                    sb.Append("{}");
                    return;
                }

                sb.Append('{');
                for (var i = 0; i < o.Members.Count; i++)
                {
                    sb.Append(i == 0 ? "\n" : ",\n");
                    Indent(sb, depth + 1);
                    WriteString(sb, o.Members[i].Key);
                    sb.Append(": ");
                    Write(sb, o.Members[i].Value, depth + 1);
                }

                sb.Append('\n');
                Indent(sb, depth);
                sb.Append('}');
                return;
            case JsonArray a:
                if (a.Items.Count == 0)
                {
                    sb.Append("[]");
                    return;
                }

                sb.Append('[');
                for (var i = 0; i < a.Items.Count; i++)
                {
                    sb.Append(i == 0 ? "\n" : ",\n");
                    Indent(sb, depth + 1);
                    Write(sb, a.Items[i], depth + 1);
                }

                sb.Append('\n');
                Indent(sb, depth);
                sb.Append(']');
                return;
            case JsonString s:
                WriteString(sb, s.Value);
                return;
            case JsonNumber n:
                if (!n.IsInteger)
                {
                    throw new ArgumentException("Only integer numbers are written; got " + n.Raw + ".", nameof(value));
                }

                // Exact: the reader and the journal keep integers within ±2^53.
                sb.Append(((long)n.Value).ToString(CultureInfo.InvariantCulture));
                return;
            case JsonBool b:
                sb.Append(b.Value ? "true" : "false");
                return;
            default:
                sb.Append("null");
                return;
        }
    }

    private static void Indent(StringBuilder sb, int depth) => sb.Append(' ', 2 * depth);

    private static void WriteString(StringBuilder sb, string s)
    {
        sb.Append('"');
        foreach (var c in s)
        {
            switch (c)
            {
                case '"':
                    sb.Append("\\\"");
                    break;
                case '\\':
                    sb.Append("\\\\");
                    break;
                case '\b':
                    sb.Append("\\b");
                    break;
                case '\f':
                    sb.Append("\\f");
                    break;
                case '\n':
                    sb.Append("\\n");
                    break;
                case '\r':
                    sb.Append("\\r");
                    break;
                case '\t':
                    sb.Append("\\t");
                    break;
                case < ' ':
                    sb.Append("\\u00").Append(HexDigits[c >> 4]).Append(HexDigits[c & 0xF]);
                    break;
                default:
                    sb.Append(c);
                    break;
            }
        }

        sb.Append('"');
    }
}
