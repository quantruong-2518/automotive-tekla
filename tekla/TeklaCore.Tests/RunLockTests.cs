using System;
using System.Globalization;
using System.Threading;
using Xunit;

namespace TeklaHarness.Core.Tests;

/// <summary>ADR-0012 decision 4: one writer per model, a named mutex keyed on the normalised path.</summary>
public sealed class RunLockTests
{
    /// <summary>A unique working-copy path per test, so parallel test runs never share a mutex.</summary>
    private static string UniquePath() => @"C:\Models\lock-" + Guid.NewGuid().ToString("N", CultureInfo.InvariantCulture);

    /// <summary>Runs <paramref name="action"/> on its own thread and waits for it.</summary>
    private static void OnOtherThread(Action action)
    {
        Exception? error = null;
        var thread = new Thread(() =>
        {
            try
            {
                action();
            }
            catch (Exception e)
            {
                error = e;
            }
        });
        thread.Start();
        thread.Join();
        if (error is not null)
        {
            throw new InvalidOperationException("other thread failed", error);
        }
    }

    [Fact]
    public void Mutex_name_folds_the_spellings_safety_rule_1_treats_as_the_same_folder()
    {
        var name = NamedMutexRunLock.MutexName(@"C:\Models\Copy");
        Assert.NotNull(name);
        Assert.Equal(name, NamedMutexRunLock.MutexName(@"c:/models/copy/"));
        Assert.Equal(name, NamedMutexRunLock.MutexName(@"C:\\Models\.\COPY"));
        Assert.NotEqual(name, NamedMutexRunLock.MutexName(@"C:\Models\Copy2"));
        Assert.NotEqual(name, NamedMutexRunLock.MutexName(@"D:\Models\Copy"));
        Assert.NotEqual(name, NamedMutexRunLock.MutexName(@"C:\Models\Copy\Sub"));
        Assert.StartsWith(@"Global\tekla-harness-run-", name, StringComparison.Ordinal);
        var hash = name!.Substring(@"Global\tekla-harness-run-".Length);
        Assert.Equal(64, hash.Length);
        Assert.All(hash, c => Assert.True(c is (>= '0' and <= '9') or (>= 'a' and <= 'f')));
    }

    [Fact]
    public void Mutex_name_is_the_sha256_of_the_upper_case_canonical_path()
    {
        var name = NamedMutexRunLock.MutexName(@"C:\Models\Copy");
        using var sha = System.Security.Cryptography.SHA256.Create();
        var digest = sha.ComputeHash(System.Text.Encoding.UTF8.GetBytes(@"C:\MODELS\COPY"));
        var hex = string.Concat(Array.ConvertAll(digest, b => b.ToString("x2", CultureInfo.InvariantCulture)));
        Assert.Equal(@"Global\tekla-harness-run-" + hex, name);
        Assert.Equal(NamedMutexRunLock.MutexName(@"C:\Models\Dự Án"), NamedMutexRunLock.MutexName(@"c:\MODELS\DỰ ÁN"));
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData(@"Models\Copy")]
    [InlineData(@"\\server\share\copy")]
    [InlineData(@"C:\")]
    [InlineData(@"C:\Models\..\Copy")]
    public void Unprovable_path_has_no_lock_and_refuses_with_5(string? path)
    {
        Assert.Null(NamedMutexRunLock.MutexName(path));
        using var result = NamedMutexRunLock.Instance.TryAcquire(path);
        Assert.False(result.Acquired);
        Assert.False(result.PreviousHolderCrashed);
        Assert.Equal(ExitCode.RefusedBySafetyRule, result.ExitCode);
        Assert.False(string.IsNullOrEmpty(result.Detail));
    }

    [Fact]
    public void Free_lock_is_acquired_and_released_on_dispose()
    {
        var path = UniquePath();
        var first = NamedMutexRunLock.Instance.TryAcquire(path);
        Assert.True(first.Acquired, first.Detail);
        Assert.False(first.PreviousHolderCrashed);
        Assert.Equal(ExitCode.Ok, first.ExitCode);
        first.Dispose();
        first.Dispose(); // idempotent
        using var second = NamedMutexRunLock.Instance.TryAcquire(path.ToUpperInvariant());
        Assert.True(second.Acquired, second.Detail);
    }

    [Fact]
    public void Lock_held_by_another_thread_refuses_with_3()
    {
        var path = UniquePath();
        using var held = new ManualResetEventSlim();
        using var release = new ManualResetEventSlim();
        var holderAcquired = false;
        var holder = new Thread(() =>
        {
            try
            {
                using var mine = NamedMutexRunLock.Instance.TryAcquire(path);
                holderAcquired = mine.Acquired;
                held.Set();
                release.Wait();
            }
            catch (Exception)
            {
                held.Set(); // holderAcquired stays false and fails the test
            }
        });
        holder.Start();
        held.Wait();
        try
        {
            Assert.True(holderAcquired);
            RunLockResult? other = null;
            OnOtherThread(() => other = NamedMutexRunLock.Instance.TryAcquire(path.ToUpperInvariant().Replace('\\', '/')));
            Assert.False(other!.Acquired);
            Assert.Equal(ExitCode.EnvironmentError, other.ExitCode);
            Assert.Contains("held", other.Detail, StringComparison.Ordinal);
            other.Dispose();
        }
        finally
        {
            release.Set();
            holder.Join();
        }

        using var after = NamedMutexRunLock.Instance.TryAcquire(path);
        Assert.True(after.Acquired, after.Detail);
    }

    [Fact]
    public void Mutex_held_outside_this_lock_object_refuses_with_3()
    {
        // Another CLI process holds the same named mutex: simulated by a raw mutex on another thread.
        var path = UniquePath();
        var name = NamedMutexRunLock.MutexName(path)!;
        using var held = new ManualResetEventSlim();
        using var release = new ManualResetEventSlim();
        var holder = new Thread(() =>
        {
            using var mutex = new Mutex(false, name);
            if (mutex.WaitOne(0))
            {
                held.Set();
                release.Wait();
                mutex.ReleaseMutex();
            }
            else
            {
                held.Set();
            }
        });
        holder.Start();
        held.Wait();
        try
        {
            using var result = NamedMutexRunLock.Instance.TryAcquire(path);
            Assert.False(result.Acquired);
            Assert.False(result.PreviousHolderCrashed);
            Assert.Equal(ExitCode.EnvironmentError, result.ExitCode);
            Assert.Equal("Run lock for '" + path + "' is held by another writer: wait for it to finish.", result.Detail);
        }
        finally
        {
            release.Set();
            holder.Join();
        }

        using var after = NamedMutexRunLock.Instance.TryAcquire(path);
        Assert.True(after.Acquired, after.Detail);
        Assert.False(after.PreviousHolderCrashed);
    }

    [Fact]
    public void Same_thread_cannot_take_the_lock_twice()
    {
        var path = UniquePath();
        using var first = NamedMutexRunLock.Instance.TryAcquire(path);
        Assert.True(first.Acquired);
        using var second = NamedMutexRunLock.Instance.TryAcquire(path);
        Assert.False(second.Acquired);
        Assert.Equal(ExitCode.EnvironmentError, second.ExitCode);
    }

    [Fact]
    public void Holder_that_ended_without_releasing_counts_as_crashed()
    {
        var path = UniquePath();
        var name = NamedMutexRunLock.MutexName(path)!;

        // Keeps the named mutex alive: if the GC finalised the thread's handle first, the kernel
        // object would vanish and the next acquire would see a fresh mutex, not an abandoned one.
        using var observer = new Mutex(false, name);
        OnOtherThread(() =>
        {
            var mutex = new Mutex(false, name);
            Assert.True(mutex.WaitOne(0));
            // the thread ends holding it: the mutex is abandoned
        });
        using var result = NamedMutexRunLock.Instance.TryAcquire(path);
        Assert.True(result.Acquired, result.Detail);
        Assert.True(result.PreviousHolderCrashed);
        Assert.Equal(ExitCode.Ok, result.ExitCode);
        Assert.Equal("Run lock for '" + path + "' acquired; the previous holder ended without releasing it (abandoned): its running invocation crashed.", result.Detail);
    }

    [Fact]
    public void Dispose_releases_the_mutex_for_other_threads()
    {
        // An observer handle keeps the named mutex alive, so a missing release shows as abandonment.
        var path = UniquePath();
        using var observer = new Mutex(false, NamedMutexRunLock.MutexName(path)!);
        OnOtherThread(() =>
        {
            var result = NamedMutexRunLock.Instance.TryAcquire(path);
            Assert.True(result.Acquired, result.Detail);
            result.Dispose();
        });
        using var again = NamedMutexRunLock.Instance.TryAcquire(path);
        Assert.True(again.Acquired, again.Detail);
        Assert.False(again.PreviousHolderCrashed);
    }

    [Fact]
    public void Details_name_the_path_and_the_reason()
    {
        var path = UniquePath();
        using (var first = NamedMutexRunLock.Instance.TryAcquire(path))
        {
            Assert.Equal("Run lock for '" + path + "' acquired.", first.Detail);
            using var second = NamedMutexRunLock.Instance.TryAcquire(path);
            Assert.Equal("Run lock for '" + path + "' is already held by this process.", second.Detail);
        }

        using var bad = NamedMutexRunLock.Instance.TryAcquire("relative");
        Assert.Equal("Working-copy path cannot be checked, so it cannot be locked: 'relative'.", bad.Detail);
    }
}
