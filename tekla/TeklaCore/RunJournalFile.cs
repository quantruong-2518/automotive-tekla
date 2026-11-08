using System;
using System.Collections.Generic;
using System.IO;
using System.Security;
using TeklaHarness.Core.Json;

namespace TeklaHarness.Core;

/// <summary>What <see cref="RunJournalFile.Read"/> found.</summary>
public enum JournalReadStatus
{
    /// <summary>A strict-JSON, schema-shaped journal.</summary>
    Found,

    /// <summary>No file at the path: the run has no journal yet.</summary>
    Missing,

    /// <summary>The file exists but is over 16 MiB, not strict JSON or not schema-shaped (exit 5).</summary>
    Invalid,

    /// <summary>I/O error on the path: access denied, sharing violation, missing folder (exit 3).</summary>
    ReadError,

    /// <summary>No journal, but a temporary or backup file of it: a write may have been interrupted (exit 5).</summary>
    InterruptedWrite,
}

/// <summary>Result of <see cref="RunJournalFile.Read"/>.</summary>
public sealed class JournalReadResult
{
    internal JournalReadResult(JournalReadStatus status, string detail, RunJournal? journal)
    {
        Status = status;
        Detail = detail;
        Journal = journal;
    }

    public JournalReadStatus Status { get; }

    /// <summary>Human-readable reason, for the JSON output and the engineer.</summary>
    public string Detail { get; }

    /// <summary>The journal when <see cref="JournalReadStatus.Found"/>; otherwise null.</summary>
    public RunJournal? Journal { get; }

    /// <summary>Decision 5: invalid or interrupted write 5, I/O error 3; found or missing are not refusals (0).</summary>
    public ExitCode ExitCode => Status switch
    {
        JournalReadStatus.Invalid or JournalReadStatus.InterruptedWrite => ExitCode.RefusedBySafetyRule,
        JournalReadStatus.ReadError => ExitCode.EnvironmentError,
        _ => ExitCode.Ok,
    };
}

/// <summary>
/// Reads and writes run journals (ADR-0012 decisions 2–3). Both directions apply the strict JSON
/// profile (ADR-0010 Amendment 1 §1) and the schema's shape rules.
/// </summary>
public static class RunJournalFile
{
    /// <summary>Reads the journal at <paramref name="path"/>. Never throws for bad content or I/O errors.</summary>
    public static JournalReadResult Read(string path)
    {
        var what = "Run journal '" + path + "'";
        byte[] bytes;
        IReadOnlyList<string> leftovers;
        try
        {
            using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read);
            using var buffer = new MemoryStream();
            var chunk = new byte[81920];
            int read;
            while ((read = stream.Read(chunk, 0, chunk.Length)) > 0)
            {
                buffer.Write(chunk, 0, read);
                if (buffer.Length > StrictJson.MaxInputBytes)
                {
                    return new JournalReadResult(JournalReadStatus.Invalid, what + " is larger than 16 MiB.", null);
                }
            }

            bytes = buffer.ToArray();
            leftovers = AtomicFile.Leftovers(path);
        }
        catch (FileNotFoundException)
        {
            return Missing(path, what);
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException or ArgumentException or NotSupportedException or SecurityException)
        {
            // A missing folder is not "no journal": the spec was read from that folder.
            return new JournalReadResult(JournalReadStatus.ReadError, what + " cannot be read: " + e.Message, null);
        }

        var result = Parse(bytes, what);
        return result.Status == JournalReadStatus.Found && leftovers.Count > 0
            ? new JournalReadResult(JournalReadStatus.Found, result.Detail + " Leftover file(s) next to it: " + string.Join(", ", leftovers) + ".", result.Journal)
            : result;
    }

    /// <summary>No journal file: "no journal yet", unless a write of it was interrupted (review M1).</summary>
    private static JournalReadResult Missing(string path, string what)
    {
        IReadOnlyList<string> leftovers;
        try
        {
            leftovers = AtomicFile.Leftovers(path);
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException or ArgumentException or NotSupportedException or SecurityException)
        {
            return new JournalReadResult(JournalReadStatus.ReadError, what + " cannot be checked for leftovers: " + e.Message, null);
        }

        return leftovers.Count == 0
            ? new JournalReadResult(JournalReadStatus.Missing, "No run journal at '" + path + "'.", null)
            : new JournalReadResult(
                JournalReadStatus.InterruptedWrite,
                "No run journal at '" + path + "', but " + string.Join(", ", leftovers)
                + " lie next to it: a journal write may have been interrupted. Check the folder before anything else.",
                null);
    }

    /// <summary>
    /// Serialises <paramref name="journal"/> (deterministic bytes), checks the bytes read back as a
    /// valid journal, then replaces the file atomically: temporary file in the same folder, flushed
    /// to disk, then replace or move, up to 3 retries 100 ms apart on <see cref="System.IO.IOException"/>.
    /// Throws <see cref="InvalidOperationException"/> when the journal breaks a schema rule (nothing
    /// written), or the I/O exception of the last attempt. Mapping a failure to an exit code is the
    /// caller's (decision 3: exit 4 during a run).
    /// </summary>
    public static void Write(string path, RunJournal journal) => AtomicFile.Write(path, Serialize(journal));

    /// <summary>The exact bytes <see cref="Write"/> puts on disk, after the same validation.</summary>
    public static byte[] Serialize(RunJournal journal)
    {
        if (journal is null)
        {
            throw new ArgumentNullException(nameof(journal));
        }

        var bytes = ToUtf8(journal);
        var check = Parse(bytes, "Run journal to write");
        if (check.Status != JournalReadStatus.Found)
        {
            throw new InvalidOperationException(check.Detail);
        }

        return bytes;
    }

    /// <summary>Writer output; a string the strict UTF-8 encoder refuses becomes <see cref="InvalidOperationException"/>.</summary>
    private static byte[] ToUtf8(RunJournal journal)
    {
        try
        {
            return JsonWriter.ToUtf8(RunJournalJson.ToJson(journal));
        }
        catch (ArgumentException e)
        {
            throw new InvalidOperationException("Run journal cannot be written: " + e.Message, e);
        }
    }

    /// <summary>Strict JSON plus schema shape of <paramref name="utf8"/>: Found or Invalid.</summary>
    internal static JournalReadResult Parse(byte[] utf8, string what)
    {
        if (!StrictJson.TryParse(utf8, out var root, out var error))
        {
            return new JournalReadResult(JournalReadStatus.Invalid, what + " is not strict JSON: " + error + ".", null);
        }

        try
        {
            var journal = RunJournalJson.Read(root!);
            return new JournalReadResult(
                JournalReadStatus.Found,
                what + " read: " + journal.Invocations.Count.ToString(System.Globalization.CultureInfo.InvariantCulture) + " invocation(s).",
                journal);
        }
        catch (JournalInvalidException e)
        {
            return new JournalReadResult(JournalReadStatus.Invalid, what + " is not a valid run journal: " + e.Message + ".", null);
        }
    }
}
