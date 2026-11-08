using System;
using System.Globalization;
using System.IO;
using System.Threading;

namespace TeklaHarness.Core;

/// <summary>Atomic whole-file replacement (ADR-0012 decision 3).</summary>
internal static class AtomicFile
{
    /// <summary>Retries after the first attempt to put the file in place.</summary>
    public const int Retries = 3;

    public const int RetryDelayMilliseconds = 100;

    /// <summary>
    /// Writes <paramref name="bytes"/> to a temporary file in the target's folder, flushes it to disk,
    /// then replaces the target (<c>File.Replace</c> when it exists, else <c>File.Move</c>), retrying
    /// that step up to <see cref="Retries"/> times on <see cref="IOException"/>. The temporary
    /// file is removed when the write fails.
    /// </summary>
    public static void Write(string path, byte[] bytes) => Write(path, bytes, PutInPlace, Thread.Sleep);

    /// <summary>Test seam: <paramref name="putInPlace"/>(temporary, target) and <paramref name="sleep"/>(milliseconds).</summary>
    internal static void Write(string path, byte[] bytes, Action<string, string> putInPlace, Action<int> sleep)
    {
        var target = Path.GetFullPath(path);

        // Same folder, so the replace is a rename on one volume. A leading dot and a ".tmp" end keep
        // a half-written file out of any "run-journal-*.json" pattern.
        var temporary = Path.Combine(
            Path.GetDirectoryName(target)!,
            "." + Path.GetFileName(target) + "." + Guid.NewGuid().ToString("N", CultureInfo.InvariantCulture) + ".tmp");
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
                    putInPlace(temporary, target);
                    return;
                }
                catch (IOException) when (attempt < Retries)
                {
                    sleep(RetryDelayMilliseconds);
                }
            }
        }
        finally
        {
            DeleteLeftover(temporary);
        }
    }

    /// <summary>The production step: replace an existing target, else move.</summary>
    internal static void PutInPlace(string temporary, string target)
    {
        if (File.Exists(target))
        {
            File.Replace(temporary, target, destinationBackupFileName: null);
        }
        else
        {
            File.Move(temporary, target);
        }
    }

    /// <summary>
    /// Removes the temporary file if it is still there. A failure here is not reported: the write's
    /// own outcome (success, or the exception already propagating) is what the caller must see, and a
    /// leftover <c>.tmp</c> file is never read as a journal.
    /// </summary>
    private static void DeleteLeftover(string temporary)
    {
        try
        {
            if (File.Exists(temporary))
            {
                File.Delete(temporary);
            }
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException)
        {
            // See the summary: deliberately not masking the write's outcome.
        }
    }
}
