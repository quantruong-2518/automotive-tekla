using System;
using System.Globalization;
using System.Numerics;
using System.Text;

namespace TeklaHarness.Core.Json;

/// <summary>
/// Correctly rounded conversion of a JSON number token to a double (IEEE 754 round half to even),
/// equal bit for bit to Python's <c>float()</c> on every runtime. Needed because .NET Framework's
/// <c>double.Parse</c> is not correctly rounded (1 ULP off on ordinary coordinates, measured on
/// 4.8.9363). Exact big-integer arithmetic; no fast path.
/// </summary>
internal static class DecimalToDouble
{
    /// <summary>
    /// Significant digits kept. A tie between two doubles has at most 767 significant digits, so
    /// truncating to more than that and keeping a "non-zero tail" digit never changes the rounding.
    /// </summary>
    private const int MaxSignificantDigits = 800;

    /// <summary>Exponents saturate here: any non-zero value is then 0 or infinite anyway.</summary>
    private const long ExponentCap = 1_000_000_000;

    /// <summary>Smallest binary exponent: the subnormal unit is 2^-1074.</summary>
    private const long MinBinaryExponent = -1074;

    /// <summary>Largest binary exponent of a 53-bit significand: (2^53 - 1) * 2^971 is MaxValue.</summary>
    private const long MaxBinaryExponent = 971;

    private static readonly BigInteger TwoPow52 = BigInteger.One << 52;
    private static readonly BigInteger TwoPow53 = BigInteger.One << 53;

    /// <summary>
    /// 10^0 .. 10^1124: every power the bounded range in <see cref="Magnitude"/> can ask for
    /// (at most 800 digits + 323 + 1 for the sticky digit).
    /// </summary>
    private static readonly BigInteger[] PowersOfTen = BuildPowersOfTen(MaxSignificantDigits + 325);

    /// <summary>
    /// Converts a token that already matches the JSON number grammar. Returns false when the value
    /// rounds to 2^1024 or more in magnitude (not a finite double).
    /// </summary>
    public static bool TryConvert(string token, out double value)
    {
        var negative = token[0] == '-';
        var i = negative ? 1 : 0;
        var digits = new StringBuilder();
        long exponent = 0; // value = digits * 10^exponent (+ a non-zero tail when sticky)
        var sticky = false;

        // A non-integer token always continues after its integer digits ('.' or an exponent).
        for (; IsDigit(token[i]); i++)
        {
            if (digits.Length == MaxSignificantDigits)
            {
                exponent++;
                sticky |= token[i] != '0';
            }
            else if (digits.Length > 0 || token[i] != '0')
            {
                digits.Append(token[i]);
            }
        }

        if (token[i] == '.')
        {
            for (i++; i < token.Length && IsDigit(token[i]); i++)
            {
                if (digits.Length == MaxSignificantDigits)
                {
                    sticky |= token[i] != '0';
                }
                else
                {
                    exponent--;
                    if (digits.Length > 0 || token[i] != '0')
                    {
                        digits.Append(token[i]);
                    }
                }
            }
        }

        if (i < token.Length)
        {
            i++; // 'e' or 'E'
            var exponentSign = 1;
            if (token[i] is '+' or '-')
            {
                exponentSign = token[i] == '-' ? -1 : 1;
                i++;
            }

            long written = 0;
            for (; i < token.Length; i++)
            {
                written = Math.Min((written * 10) + (token[i] - '0'), ExponentCap);
            }

            exponent += exponentSign * written;
        }

        var bits = digits.Length == 0 ? 0L : Magnitude(digits.ToString(), exponent, sticky);
        if (bits < 0)
        {
            value = double.NaN;
            return false;
        }

        value = BitConverter.Int64BitsToDouble(negative ? bits | long.MinValue : bits);
        return true;
    }

    private static bool IsDigit(char c) => c is >= '0' and <= '9';

    /// <summary>IEEE bits of digits * 10^exponent (positive), or -1 when it rounds to infinity.</summary>
    private static long Magnitude(string digits, long exponent, bool sticky)
    {
        // digits has no leading zero, so the value lies in [10^(n-1+e), 10^(n+e)).
        if (digits.Length - 1 + exponent > 308)
        {
            return -1; // at least 10^309
        }

        if (digits.Length + exponent < -323)
        {
            return 0; // below 10^-324, less than half the smallest subnormal (2^-1075 ≈ 2.47e-324)
        }

        var m = BigInteger.Parse(digits, NumberStyles.None, CultureInfo.InvariantCulture);
        if (sticky)
        {
            m = (m * 10) + 1;
            exponent--;
        }

        var numerator = m * PowersOfTen[Math.Max(exponent, 0)];
        var denominator = PowersOfTen[Math.Max(-exponent, 0)];

        // With a = bits(numerator), b = bits(denominator): ratio in (2^(a-b-1), 2^(a-b+1)), so for
        // q = a - b - 53 the significand lies in (2^52, 2^54): at most one step up. When q is raised
        // to -1074 the value is subnormal-range and the significand is below 2^53.
        var q = Math.Max(BitLength(numerator) - BitLength(denominator) - 53, MinBinaryExponent);
        var significand = Divide(numerator, denominator, q, out var remainder, out var divisor);
        if (significand >= TwoPow53)
        {
            q++;
            significand = Divide(numerator, denominator, q, out remainder, out divisor);
        }

        // Round half to even.
        var half = (remainder << 1).CompareTo(divisor);
        if (half > 0 || (half == 0 && !significand.IsEven))
        {
            significand += 1;
            if (significand == TwoPow53)
            {
                significand = TwoPow52;
                q++;
            }
        }

        if (q > MaxBinaryExponent)
        {
            return -1;
        }

        if (significand < TwoPow52)
        {
            return (long)significand; // subnormal (or zero): exponent field 0
        }

        return ((q + 1075) << 52) | (long)(significand - TwoPow52);
    }

    /// <summary>floor(numerator / (denominator * 2^q)), its remainder and the divisor used.</summary>
    private static BigInteger Divide(BigInteger numerator, BigInteger denominator, long q, out BigInteger remainder, out BigInteger divisor)
    {
        divisor = denominator << (int)Math.Max(q, 0);
        return BigInteger.DivRem(numerator << (int)Math.Max(-q, 0), divisor, out remainder);
    }

    /// <summary>Number of bits of a positive integer (BigInteger.GetBitLength is not in netstandard2.0).</summary>
    private static long BitLength(BigInteger x)
    {
        // Little-endian two's complement. A 0x00 sign byte on top only follows a byte with its high
        // bit set (8 bits), so counting the sign byte as 0 bits on top of 8 * (length - 1) is exact.
        var bytes = x.ToByteArray();
        var top = bytes.Length - 1;
        long bits = top * 8L;
        for (int b = bytes[top]; b != 0; b >>= 1)
        {
            bits++;
        }

        return bits;
    }

    private static BigInteger[] BuildPowersOfTen(int count)
    {
        var powers = new BigInteger[count];
        powers[0] = BigInteger.One;
        for (var k = 1; k < count; k++)
        {
            powers[k] = powers[k - 1] * 10;
        }

        return powers;
    }
}
