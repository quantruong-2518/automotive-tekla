using System;
using System.Globalization;
using System.IO;

namespace TeklaHarness.Core;

/// <summary>
/// <c>RUN_ID</c> rules (ADR-0012 decision 1): it is a Tekla UDA value and part of the run journal's
/// file name, so it must match <c>^[A-Z0-9][A-Z0-9_-]{0,31}$</c> (<c>run_id</c> in
/// <c>common.schema.json</c>, ECMA meaning: no trailing newline, ASCII only).
/// </summary>
public static class RunId
{
    public const int MaxLength = 32;

    /// <summary>True when <paramref name="runId"/> matches the <c>run_id</c> pattern exactly.</summary>
    public static bool IsValid(string? runId) => IdPatterns.IsUpperId(runId, MaxLength);

    /// <summary>The <c>LOT</c> tag text: the invariant-culture integer, no padding (decision 1).</summary>
    public static string LotTag(int lot) => lot.ToString(CultureInfo.InvariantCulture);

    /// <summary>
    /// <c>run-journal-&lt;RUN_ID&gt;.json</c> in the spec's folder (decision 2). Throws
    /// <see cref="ArgumentException"/> for an invalid run id or an empty spec path.
    /// </summary>
    public static string JournalPath(string specPath, string runId)
    {
        if (string.IsNullOrEmpty(specPath))
        {
            throw new ArgumentException("A spec path is required.", nameof(specPath));
        }

        if (!IsValid(runId))
        {
            throw new ArgumentException("RUN_ID must match ^[A-Z0-9][A-Z0-9_-]{0,31}$.", nameof(runId));
        }

        return Path.Combine(Path.GetDirectoryName(specPath) ?? string.Empty, "run-journal-" + runId + ".json");
    }
}

/// <summary>The id patterns of <c>common.schema.json</c>, checked character by character (ASCII, no trailing newline).</summary>
internal static class IdPatterns
{
    /// <summary><c>^[A-Z0-9][A-Z0-9_-]{0,max-1}$</c>: <c>run_id</c> (32) and <c>spec_id</c> (64).</summary>
    public static bool IsUpperId(string? s, int maxLength)
    {
        if (s is null || s.Length == 0 || s.Length > maxLength || !IsUpperOrDigit(s[0]))
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

    /// <summary><c>^[a-z0-9][a-z0-9-]{1,63}$</c>: <c>project_id</c>.</summary>
    public static bool IsProjectId(string s)
    {
        if (s.Length < 2 || s.Length > 64 || !IsLowerOrDigit(s[0]))
        {
            return false;
        }

        foreach (var c in s)
        {
            if (!IsLowerOrDigit(c) && c != '-')
            {
                return false;
            }
        }

        return true;
    }

    private static bool IsUpperOrDigit(char c) => c is (>= 'A' and <= 'Z') or (>= '0' and <= '9');

    private static bool IsLowerOrDigit(char c) => c is (>= 'a' and <= 'z') or (>= '0' and <= '9');
}
