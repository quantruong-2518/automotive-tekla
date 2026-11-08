using System;
using System.Collections.Generic;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Threading;

namespace TeklaHarness.Core;

/// <summary>One writer per model (ADR-0012 decision 4).</summary>
public interface IRunLock
{
    /// <summary>
    /// Tries to take the exclusive lock for <paramref name="workingCopyPath"/> without waiting. The
    /// caller keeps the result for its whole run and disposes it on the same thread to release.
    /// </summary>
    RunLockResult TryAcquire(string? workingCopyPath);
}

/// <summary>Result of <see cref="IRunLock.TryAcquire"/>. Disposing it releases a held lock.</summary>
public sealed class RunLockResult : IDisposable
{
    private Action? _release;

    internal RunLockResult(bool acquired, bool previousHolderCrashed, string detail, ExitCode exitCode, Action? release)
    {
        Acquired = acquired;
        PreviousHolderCrashed = previousHolderCrashed;
        Detail = detail;
        ExitCode = exitCode;
        _release = release;
    }

    public bool Acquired { get; }

    /// <summary>The previous holder ended without releasing: its <c>running</c> invocation is abandoned.</summary>
    public bool PreviousHolderCrashed { get; }

    public string Detail { get; }

    /// <summary>Acquired 0; held by another writer or not obtainable 3; working-copy path unprovable 5.</summary>
    public ExitCode ExitCode { get; }

    public void Dispose()
    {
        var release = _release;
        _release = null;
        release?.Invoke();
    }
}

/// <summary>
/// The lock as a named mutex <c>Local\tekla-harness-run-&lt;sha256&gt;</c>, keyed on the working-copy
/// path normalised as safety rule 1 reads it (drive and ASCII letters folded to upper case,
/// separators unified, no trailing separator), so every spelling the path guard accepts as the
/// same folder takes the same lock. A mutex belongs to a thread: acquire and dispose on one thread.
/// </summary>
public sealed class NamedMutexRunLock : IRunLock
{
    public static readonly NamedMutexRunLock Instance = new();

    private NamedMutexRunLock()
    {
    }

    private const string NamePrefix = @"Local\tekla-harness-run-";

    private const string HexDigits = "0123456789abcdef";

    /// <summary>Locks this process holds: a mutex is re-entrant for its thread, the run lock is not.</summary>
    private static readonly HashSet<string> HeldHere = new(StringComparer.Ordinal);

    public RunLockResult TryAcquire(string? workingCopyPath)
    {
        var name = MutexName(workingCopyPath);
        if (name is null)
        {
            return Refused(ExitCode.RefusedBySafetyRule, "Working-copy path cannot be checked, so it cannot be locked: '" + workingCopyPath + "'.");
        }

        lock (HeldHere)
        {
            if (!HeldHere.Add(name))
            {
                return Refused(ExitCode.EnvironmentError, "Run lock for '" + workingCopyPath + "' is already held by this process.");
            }
        }

        Mutex? mutex = null;
        try
        {
            mutex = new Mutex(initiallyOwned: false, name);
            var crashed = false;
            bool acquired;
            try
            {
                acquired = mutex.WaitOne(0);
            }
            catch (AbandonedMutexException)
            {
                acquired = true; // ownership passes to us; the previous holder ended without releasing
                crashed = true;
            }

            if (!acquired)
            {
                Forget(name, mutex);
                return Refused(ExitCode.EnvironmentError, "Run lock for '" + workingCopyPath + "' is held by another writer: wait for it to finish.");
            }

            var held = mutex;
            return new RunLockResult(
                acquired: true,
                previousHolderCrashed: crashed,
                crashed
                    ? "Run lock for '" + workingCopyPath + "' acquired; the previous holder ended without releasing it (abandoned): its running invocation crashed."
                    : "Run lock for '" + workingCopyPath + "' acquired.",
                ExitCode.Ok,
                () =>
                {
                    held.ReleaseMutex();
                    Forget(name, held);
                });
        }
        catch (Exception e) when (e is UnauthorizedAccessException or IOException or WaitHandleCannotBeOpenedException)
        {
            Forget(name, mutex);
            return Refused(ExitCode.EnvironmentError, "Run lock for '" + workingCopyPath + "' cannot be obtained: " + e.Message);
        }
    }

    /// <summary>The mutex name for a path; null when the path cannot be parsed.</summary>
    internal static string? MutexName(string? workingCopyPath)
    {
        if (!WindowsPath.TryParse(workingCopyPath, out var path, out _))
        {
            return null;
        }

        // Canonical text, every UTF-16 unit upper-cased as NTFS compares names: at least as broad
        // as the path guard's "same folder" (ASCII case), so one folder never gets two locks.
        var key = path!.ToString().ToCharArray();
        for (var i = 0; i < key.Length; i++)
        {
            key[i] = char.ToUpperInvariant(key[i]);
        }

        using var sha = SHA256.Create();
        var digest = sha.ComputeHash(new UTF8Encoding(false, true).GetBytes(key));
        var name = new StringBuilder(NamePrefix, NamePrefix.Length + 64);
        foreach (var b in digest)
        {
            name.Append(HexDigits[b >> 4]).Append(HexDigits[b & 0xF]);
        }

        return name.ToString();
    }

    private static RunLockResult Refused(ExitCode exitCode, string detail) => new(false, false, detail, exitCode, null);

    private static void Forget(string name, Mutex? mutex)
    {
        mutex?.Dispose();
        lock (HeldHere)
        {
            HeldHere.Remove(name);
        }
    }
}
