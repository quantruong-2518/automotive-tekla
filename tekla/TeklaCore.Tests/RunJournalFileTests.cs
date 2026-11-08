using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using Xunit;

namespace TeklaHarness.Core.Tests;

/// <summary>ADR-0012 decisions 2–3 on a real file system: journal path, read statuses, atomic write.</summary>
public sealed class RunJournalFileTests : IDisposable
{
    private readonly string _dir;

    public RunJournalFileTests()
    {
        _dir = Path.Combine(Path.GetTempPath(), "teklacore-s1c-" + Guid.NewGuid().ToString("N", CultureInfo.InvariantCulture));
        Directory.CreateDirectory(_dir);
    }

    public void Dispose() => Directory.Delete(_dir, recursive: true);

    private string JournalPath => Path.Combine(_dir, "run-journal-R1.json");

    private static RunJournal Example => RunJournalFile.Read(RepoPaths.SchemaExample("run-journal.example.json")).Journal!;

    private static RunJournal Other => Example.WithInvocations(Example.Invocations.Take(1));

    // ---- path

    [Fact]
    public void Journal_path_is_in_the_spec_folder()
    {
        var spec = Path.Combine(_dir, "lot-1", "spec.json");
        Assert.Equal(Path.Combine(_dir, "lot-1", "run-journal-R20261108-01.json"), RunId.JournalPath(spec, "R20261108-01"));
        Assert.Equal("run-journal-R1.json", RunId.JournalPath("spec.json", "R1"));
    }

    [Theory]
    [InlineData("r1")]
    [InlineData("")]
    [InlineData("..")]
    [InlineData("R1/..")]
    public void Journal_path_refuses_an_invalid_run_id(string runId)
    {
        var e = Assert.Throws<ArgumentException>(() => RunId.JournalPath(Path.Combine(_dir, "spec.json"), runId));
        Assert.StartsWith("RUN_ID must match ^[A-Z0-9][A-Z0-9_-]{0,31}$.", e.Message, StringComparison.Ordinal);
        Assert.Equal("runId", e.ParamName);
    }

    [Fact]
    public void Journal_path_refuses_an_empty_spec_path()
    {
        var e = Assert.Throws<ArgumentException>(() => RunId.JournalPath(string.Empty, "R1"));
        Assert.StartsWith("A spec path is required.", e.Message, StringComparison.Ordinal);
        Assert.Equal("specPath", e.ParamName);
        Assert.Throws<ArgumentException>(() => RunId.JournalPath(null!, "R1"));
    }

    // ---- read

    [Fact]
    public void Missing_journal_is_not_a_refusal()
    {
        var result = RunJournalFile.Read(JournalPath);
        Assert.Equal(JournalReadStatus.Missing, result.Status);
        Assert.Equal(ExitCode.Ok, result.ExitCode);
        Assert.Null(result.Journal);
        Assert.Equal("No run journal at '" + JournalPath + "'.", result.Detail);
    }

    [Fact]
    public void Missing_folder_is_an_io_error()
    {
        var result = RunJournalFile.Read(Path.Combine(_dir, "gone", "run-journal-R1.json"));
        Assert.Equal(JournalReadStatus.ReadError, result.Status);
        Assert.Equal(ExitCode.EnvironmentError, result.ExitCode);
        Assert.Null(result.Journal);
    }

    [Fact]
    public void Folder_in_place_of_the_journal_is_an_io_error()
    {
        Directory.CreateDirectory(JournalPath);
        var result = RunJournalFile.Read(JournalPath);
        Assert.Equal(JournalReadStatus.ReadError, result.Status);
        Assert.Equal(ExitCode.EnvironmentError, result.ExitCode);
        Assert.StartsWith("Run journal '" + JournalPath + "' cannot be read: ", result.Detail, StringComparison.Ordinal);
    }

    [Fact]
    public void Journal_over_16_MiB_is_invalid()
    {
        var bytes = new byte[(16 * 1024 * 1024) + 1];
        for (var i = 0; i < bytes.Length; i++)
        {
            bytes[i] = (byte)' ';
        }

        File.WriteAllBytes(JournalPath, bytes);
        var result = RunJournalFile.Read(JournalPath);
        Assert.Equal(JournalReadStatus.Invalid, result.Status);
        Assert.Equal(ExitCode.RefusedBySafetyRule, result.ExitCode);
        Assert.Equal("Run journal '" + JournalPath + "' is larger than 16 MiB.", result.Detail);
    }

    [Fact]
    public void Journal_of_exactly_16_MiB_is_parsed()
    {
        var text = Encoding.UTF8.GetBytes("{}");
        var bytes = new byte[16 * 1024 * 1024];
        for (var i = 0; i < bytes.Length; i++)
        {
            bytes[i] = (byte)' ';
        }

        Array.Copy(text, bytes, text.Length);
        File.WriteAllBytes(JournalPath, bytes);
        var result = RunJournalFile.Read(JournalPath);
        Assert.Equal(JournalReadStatus.Invalid, result.Status);
        Assert.DoesNotContain("16 MiB", result.Detail, StringComparison.Ordinal);
        Assert.Contains("missing field", result.Detail, StringComparison.Ordinal);
    }

    [Fact]
    public void Invalid_journal_names_its_path()
    {
        File.WriteAllText(JournalPath, "{\"schema_version\":\"0.1\"}");
        var result = RunJournalFile.Read(JournalPath);
        Assert.Equal(JournalReadStatus.Invalid, result.Status);
        Assert.Equal("Run journal '" + JournalPath + "' is not a valid run journal: missing field 'project_id'.", result.Detail);
    }

    [Fact]
    public void Found_journal_detail_names_its_path()
    {
        RunJournalFile.Write(JournalPath, Example);
        var result = RunJournalFile.Read(JournalPath);
        Assert.Equal(JournalReadStatus.Found, result.Status);
        Assert.Equal("Run journal '" + JournalPath + "' read: 2 invocation(s).", result.Detail);
    }

    // ---- write

    private string[] FilesInDir() => Directory.GetFileSystemEntries(_dir).Select(Path.GetFileName).OrderBy(n => n, StringComparer.Ordinal).ToArray()!;

    [Fact]
    public void Write_creates_the_journal_and_leaves_no_temporary_file()
    {
        RunJournalFile.Write(JournalPath, Example);
        Assert.Equal(RunJournalFile.Serialize(Example), File.ReadAllBytes(JournalPath));
        Assert.Equal(new[] { "run-journal-R1.json" }, FilesInDir());
    }

    [Fact]
    public void Write_replaces_an_existing_journal()
    {
        RunJournalFile.Write(JournalPath, Example);
        RunJournalFile.Write(JournalPath, Other);
        Assert.Equal(RunJournalFile.Serialize(Other), File.ReadAllBytes(JournalPath));
        Assert.Equal(new[] { "run-journal-R1.json" }, FilesInDir());
        Assert.Single(RunJournalFile.Read(JournalPath).Journal!.Invocations);
    }

    [Fact]
    public void Invalid_journal_is_never_written()
    {
        var bad = new RunJournal("Demo", 1, "R1", "spec.json", new string('a', 64), @"C:\M", Array.Empty<JournalInvocation>());
        Assert.Throws<InvalidOperationException>(() => RunJournalFile.Write(JournalPath, bad));
        Assert.Empty(FilesInDir());
        RunJournalFile.Write(JournalPath, Example);
        Assert.Throws<InvalidOperationException>(() => RunJournalFile.Write(JournalPath, bad));
        Assert.Equal(RunJournalFile.Serialize(Example), File.ReadAllBytes(JournalPath));
    }

    [Fact]
    public void Null_arguments_throw()
    {
        Assert.Throws<ArgumentNullException>(() => RunJournalFile.Write(JournalPath, null!));
        Assert.Throws<ArgumentNullException>(() => RunJournalFile.Serialize(null!));
        Assert.Throws<ArgumentException>(() => RunJournalFile.Write(string.Empty, Example));
        Assert.Equal(JournalReadStatus.ReadError, RunJournalFile.Read(string.Empty).Status);
        Assert.Equal(JournalReadStatus.ReadError, RunJournalFile.Read(null!).Status);
    }

    // ---- atomic write mechanics (decision 3)

    private sealed class Recorder
    {
        public List<string> Temporaries { get; } = new();

        public List<int> Sleeps { get; } = new();

        public void Sleep(int ms) => Sleeps.Add(ms);
    }

    [Fact]
    public void Temporary_file_is_flushed_in_the_same_folder_and_does_not_look_like_a_journal()
    {
        var rec = new Recorder();
        var bytes = Encoding.UTF8.GetBytes("payload");
        AtomicFile.Write(JournalPath, bytes, (tmp, target) =>
        {
            rec.Temporaries.Add(tmp);
            Assert.Equal(JournalPath, target);
            Assert.Equal(bytes, File.ReadAllBytes(tmp));
            AtomicFile.PutInPlace(tmp, target);
        }, rec.Sleep);
        var temporary = Assert.Single(rec.Temporaries);
        Assert.Equal(Path.GetFullPath(_dir), Path.GetDirectoryName(Path.GetFullPath(temporary)));
        var name = Path.GetFileName(temporary);
        Assert.StartsWith(".run-journal-R1.json.", name, StringComparison.Ordinal);
        Assert.EndsWith(".tmp", name, StringComparison.Ordinal);
        Assert.Empty(rec.Sleeps);
        Assert.Equal(bytes, File.ReadAllBytes(JournalPath));
        Assert.Equal(new[] { "run-journal-R1.json" }, FilesInDir());
    }

    [Fact]
    public void Locked_target_is_retried_three_times_100_ms_apart()
    {
        var rec = new Recorder();
        var failures = 3;
        AtomicFile.Write(JournalPath, new byte[] { 1 }, (tmp, target) =>
        {
            rec.Temporaries.Add(tmp);
            if (failures-- > 0)
            {
                throw new IOException("locked");
            }

            AtomicFile.PutInPlace(tmp, target);
        }, rec.Sleep);
        Assert.Equal(4, rec.Temporaries.Count);
        Assert.Single(rec.Temporaries.Distinct());
        Assert.Equal(new[] { 100, 100, 100 }, rec.Sleeps);
        Assert.Equal(new byte[] { 1 }, File.ReadAllBytes(JournalPath));
        Assert.Equal(new[] { "run-journal-R1.json" }, FilesInDir());
    }

    [Fact]
    public void Fourth_failure_throws_and_removes_the_temporary_file()
    {
        File.WriteAllBytes(JournalPath, new byte[] { 9 });
        var rec = new Recorder();
        var e = Assert.Throws<IOException>(() => AtomicFile.Write(JournalPath, new byte[] { 1 }, (tmp, _) =>
        {
            rec.Temporaries.Add(tmp);
            throw new IOException("locked " + rec.Temporaries.Count.ToString(CultureInfo.InvariantCulture));
        }, rec.Sleep));
        Assert.Equal("locked 4", e.Message);
        Assert.Equal(new[] { 100, 100, 100 }, rec.Sleeps);
        Assert.Equal(new byte[] { 9 }, File.ReadAllBytes(JournalPath));
        Assert.Equal(new[] { "run-journal-R1.json" }, FilesInDir());
    }

    [Fact]
    public void Non_io_failure_is_not_retried()
    {
        var rec = new Recorder();
        Assert.Throws<UnauthorizedAccessException>(() => AtomicFile.Write(JournalPath, new byte[] { 1 }, (tmp, _) =>
        {
            rec.Temporaries.Add(tmp);
            throw new UnauthorizedAccessException("denied");
        }, rec.Sleep));
        Assert.Single(rec.Temporaries);
        Assert.Empty(rec.Sleeps);
        Assert.Empty(FilesInDir());
    }

    [Fact]
    public void Missing_folder_fails_before_any_retry()
    {
        var rec = new Recorder();
        Assert.ThrowsAny<IOException>(() => AtomicFile.Write(Path.Combine(_dir, "gone", "j.json"), new byte[] { 1 }, (tmp, _) => rec.Temporaries.Add(tmp), rec.Sleep));
        Assert.Empty(rec.Temporaries);
        Assert.Empty(rec.Sleeps);
    }

    [Fact]
    public void Put_in_place_moves_when_the_target_is_missing_and_replaces_when_it_exists()
    {
        var tmp = Path.Combine(_dir, "a.tmp");
        File.WriteAllBytes(tmp, new byte[] { 1 });
        AtomicFile.PutInPlace(tmp, JournalPath);
        Assert.False(File.Exists(tmp));
        Assert.Equal(new byte[] { 1 }, File.ReadAllBytes(JournalPath));
        File.WriteAllBytes(tmp, new byte[] { 2 });
        AtomicFile.PutInPlace(tmp, JournalPath);
        Assert.False(File.Exists(tmp));
        Assert.Equal(new byte[] { 2 }, File.ReadAllBytes(JournalPath));
    }

    [Fact]
    public void Target_appearing_after_the_existence_check_is_handled_by_the_retry()
    {
        // File.Move refuses an existing target (IOException); the retry then takes the replace path.
        var rec = new Recorder();
        var first = true;
        AtomicFile.Write(JournalPath, new byte[] { 7 }, (tmp, target) =>
        {
            if (first)
            {
                first = false;
                File.WriteAllBytes(target, new byte[] { 3 });
                File.Move(tmp, target);
            }

            AtomicFile.PutInPlace(tmp, target);
        }, rec.Sleep);
        Assert.Equal(new[] { 100 }, rec.Sleeps);
        Assert.Equal(new byte[] { 7 }, File.ReadAllBytes(JournalPath));
    }
}
