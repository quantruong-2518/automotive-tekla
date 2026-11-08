using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Threading;

namespace TeklaHarness.Core;

/// <summary>Atomic whole-file replacement (ADR-0012 decision 3).</summary>
internal static class AtomicFile
{
    /// <summary>Retries after the first attempt to put the file in place.</summary>
    public const int Retries = 3;

    public const int RetryDelayMilliseconds = 100;

    private const string TemporarySuffix = ".tmp";

    private const string BackupSuffix = ".bak";

    /// <summary>
    /// Writes <paramref name="bytes"/> to a temporary file in the target's folder, flushes it to disk,
    /// then replaces the target (<c>File.Replace</c> with a backup when it exists, else
    /// <c>File.Move</c>), retrying that step up to <see cref="Retries"/> times on
    /// <see cref="IOException"/>. The backup is removed after success. On failure the temporary file
    /// is removed only while the target still exists: a replace that failed halfway (Windows
    /// ERROR_UNABLE_TO_MOVE_REPLACEMENT) leaves the new bytes in the temporary file and the old ones in
    /// the backup, and <see cref="RunJournalFile.Read"/> then refuses instead of seeing "no journal".
    /// </summary>
    public static void Write(string path, byte[] bytes) => Write(path, bytes, PutInPlace, Thread.Sleep);

    /// <summary>Test seam: <paramref name="putInPlace"/>(temporary, target, backup) and <paramref name="sleep"/>(milliseconds).</summary>
    internal static void Write(string path, byte[] bytes, Action<string, string, string> putInPlace, Action<int> sleep)
    {
        var target = Path.GetFullPath(path);
        var folder = Path.GetDirectoryName(target)!;
        var name = Path.GetFileName(target);

        // Same folder, so the replace is a rename on one volume. A leading dot and a ".tmp"/".bak" end
        // keep these files out of any "run-journal-*.json" pattern.
        var temporary = Path.Combine(folder, "." + name + "." + Guid.NewGuid().ToString("N", CultureInfo.InvariantCulture) + TemporarySuffix);
        var backup = BackupPath(target);
        var done = false;
        try
        {
            using (var stream = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            {
                stream.Write(bytes, 0, bytes.Length);
                stream.Flush(flushToDisk: true);
            }

            for (var attempt = 0; ; attempt++)
            {
                try
                {
                    putInPlace(temporary, target, backup);
                    done = true;
                    break;
                }
                catch (IOException) when (attempt < Retries)
                {
                    sleep(RetryDelayMilliseconds);
                }
            }
        }
        finally
        {
            // Never remove the new bytes while the target is missing.
            if (File.Exists(target))
            {
                DeleteLeftover(temporary);
            }
        }

        if (done)
        {
            DeleteLeftover(backup);
        }
    }

    /// <summary>The production step: replace an existing target (keeping a backup until success), else move.</summary>
    internal static void PutInPlace(string temporary, string target, string backup)
    {
        if (File.Exists(target))
        {
            File.Replace(temporary, target, backup);
        }
        else
        {
            File.Move(temporary, target);
        }
    }

    /// <summary><c>.&lt;file name&gt;.bak</c> next to <paramref name="target"/>.</summary>
    internal static string BackupPath(string target)
        => Path.Combine(Path.GetDirectoryName(Path.GetFullPath(target))!, "." + Path.GetFileName(target) + BackupSuffix);

    /// <summary>
    /// Temporary and backup files of <paramref name="target"/> left by an interrupted write: the
    /// backup first, then temporary files in ordinal order (file names only).
    /// </summary>
    internal static IReadOnlyList<string> Leftovers(string target)
    {
        var full = Path.GetFullPath(target);
        var prefix = "." + Path.GetFileName(full) + ".";
        var backupName = Path.GetFileName(BackupPath(full));
        var names = Directory.GetFiles(Path.GetDirectoryName(full)!)
            .Select(Path.GetFileName)
            .Where(n => n!.StartsWith(prefix, StringComparison.Ordinal))
            .ToList();
        var temporaries = names
            .Where(n => n!.EndsWith(TemporarySuffix, StringComparison.Ordinal) && n.Length > prefix.Length + TemporarySuffix.Length)
            .OrderBy(n => n, StringComparer.Ordinal);
        return names.Where(n => n == backupName).Concat(temporaries).ToList()!;
    }

    /// <summary>
    /// Removes a temporary or backup file if it is still there. A failure here is not reported: the
    /// write's own outcome is what the caller must see, and <see cref="RunJournalFile.Read"/> reports
    /// any leftover next to the journal.
    /// </summary>
    private static void DeleteLeftover(string file)
    {
        try
        {
            if (File.Exists(file))
            {
                File.Delete(file);
            }
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException)
        {
            // See the summary: deliberately not masking the write's outcome.
        }
    }
}
