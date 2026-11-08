using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;

namespace TeklaHarness.Core;

/// <summary><c>command</c> of an invocation.</summary>
public enum JournalCommand
{
    Build,
    Update,
    Rollback,
}

/// <summary><c>outcome</c> of an invocation.</summary>
public enum InvocationOutcome
{
    Running,
    Ok,
    Stopped,
    Conflict,
    Refused,

    /// <summary>Was still <see cref="Running"/> when a later invocation found the lock free: it crashed (decision 4).</summary>
    Abandoned,
}

/// <summary><c>action</c> of a journal object entry.</summary>
public enum ObjectAction
{
    Created,
    Retagged,
}

/// <summary><c>state</c> of a journal object entry (decision 3).</summary>
public enum ObjectState
{
    /// <summary>Intent written before <c>Insert</c>: no GUID yet.</summary>
    Inserting,

    /// <summary>Inserted, GUID known, not tagged yet.</summary>
    Inserted,

    Tagged,
}

/// <summary><c>failure.stage</c>.</summary>
public enum FailureStage
{
    Plan,
    Insert,
    Tag,
    Commit,
    Journal,
    Other,
}

/// <summary>Conflict kinds of the journal schema (decision 8).</summary>
public enum ConflictKind
{
    /// <summary>The object differs from its spec item (decision 7).</summary>
    Mismatch,

    /// <summary>Two or more objects for one <c>SPEC_ID</c>.</summary>
    DuplicateSpecId,

    /// <summary>An object carries this <c>SPEC_ID</c> under another <c>RUN_ID</c>.</summary>
    SpecIdInOtherRun,

    /// <summary>An object carries this <c>RUN_ID</c> in another lot.</summary>
    RunInOtherLot,

    /// <summary>An object tagged with this lot and run whose <c>SPEC_ID</c> is not in the spec.</summary>
    UnknownSpecId,

    /// <summary>A journal entry still <c>inserting</c>: an untagged object may exist.</summary>
    IntentUnresolved,

    /// <summary>Model tags contradict the journal.</summary>
    TagContradiction,

    /// <summary>An object with a harness tag no rule classifies.</summary>
    Unclassified,
}

/// <summary>
/// A run journal (<c>urn:tekla-harness:schema:run-journal:0.1</c>, ADR-0012 decision 2). Immutable.
/// Constructors only reject nulls; the schema rules are applied by <see cref="RunJournalFile"/> on
/// read and before every write, so an invalid journal is never written.
/// </summary>
public sealed class RunJournal
{
    public const string CurrentSchemaVersion = "0.1";

    public RunJournal(
        string projectId,
        int lot,
        string runId,
        string specFile,
        string specSha256,
        string modelPath,
        IEnumerable<JournalInvocation> invocations)
    {
        ProjectId = projectId ?? throw new ArgumentNullException(nameof(projectId));
        Lot = lot;
        RunId = runId ?? throw new ArgumentNullException(nameof(runId));
        SpecFile = specFile ?? throw new ArgumentNullException(nameof(specFile));
        SpecSha256 = specSha256 ?? throw new ArgumentNullException(nameof(specSha256));
        ModelPath = modelPath ?? throw new ArgumentNullException(nameof(modelPath));
        Invocations = NoNulls(invocations, nameof(invocations));
    }

    public string SchemaVersion => CurrentSchemaVersion;

    public string ProjectId { get; }

    public int Lot { get; }

    public string RunId { get; }

    /// <summary>Base name of the spec file (information only).</summary>
    public string SpecFile { get; }

    /// <summary>The receipt's <c>spec_sha256</c>: binds the run to one spec (decision 5).</summary>
    public string SpecSha256 { get; }

    /// <summary>The working-copy model folder the run writes to.</summary>
    public string ModelPath { get; }

    /// <summary>One entry per CLI invocation, in execution order.</summary>
    public IReadOnlyList<JournalInvocation> Invocations { get; }

    /// <summary>The same journal with <paramref name="invocations"/> in place of the current list.</summary>
    public RunJournal WithInvocations(IEnumerable<JournalInvocation> invocations)
        => new(ProjectId, Lot, RunId, SpecFile, SpecSha256, ModelPath, invocations);

    /// <summary>
    /// Decision 4: call after acquiring the run lock. Every invocation still <c>running</c> crashed,
    /// so it becomes <c>abandoned</c>; everything else is unchanged.
    /// </summary>
    public RunJournal MarkRunningAbandoned()
        => WithInvocations(Invocations.Select(i => i.Outcome == InvocationOutcome.Running ? i.WithOutcome(InvocationOutcome.Abandoned) : i));

    internal static IReadOnlyList<T> NoNulls<T>(IEnumerable<T> items, string name)
        where T : class
    {
        if (items is null)
        {
            throw new ArgumentNullException(name);
        }

        var list = items.ToList();
        if (list.Any(i => i is null))
        {
            throw new ArgumentException("contains null", name);
        }

        return list.AsReadOnly();
    }
}

/// <summary>One CLI invocation of a run.</summary>
public sealed class JournalInvocation
{
    public JournalInvocation(
        JournalCommand command,
        string startedAt,
        string? endedAt,
        string teklaVersion,
        string modelPath,
        InvocationOutcome outcome,
        int? exitCode,
        bool committed,
        IEnumerable<JournalObject> objects,
        JournalFailure? failure,
        IEnumerable<JournalConflict> conflicts)
    {
        Command = command;
        StartedAt = startedAt ?? throw new ArgumentNullException(nameof(startedAt));
        EndedAt = endedAt;
        TeklaVersion = teklaVersion ?? throw new ArgumentNullException(nameof(teklaVersion));
        ModelPath = modelPath ?? throw new ArgumentNullException(nameof(modelPath));
        Outcome = outcome;
        ExitCode = exitCode;
        Committed = committed;
        Objects = RunJournal.NoNulls(objects, nameof(objects));
        Failure = failure;
        Conflicts = RunJournal.NoNulls(conflicts, nameof(conflicts));
    }

    public JournalCommand Command { get; }

    /// <summary>UTC, <c>yyyy-MM-ddTHH:mm:ssZ</c>, information only (see <see cref="JournalTimestamp"/>).</summary>
    public string StartedAt { get; }

    public string? EndedAt { get; }

    public string TeklaVersion { get; }

    public string ModelPath { get; }

    public InvocationOutcome Outcome { get; }

    /// <summary>0..5, or null while running.</summary>
    public int? ExitCode { get; }

    public bool Committed { get; }

    public IReadOnlyList<JournalObject> Objects { get; }

    public JournalFailure? Failure { get; }

    public IReadOnlyList<JournalConflict> Conflicts { get; }

    /// <summary>The same invocation with another outcome.</summary>
    public JournalInvocation WithOutcome(InvocationOutcome outcome)
        => new(Command, StartedAt, EndedAt, TeklaVersion, ModelPath, outcome, ExitCode, Committed, Objects, Failure, Conflicts);
}

/// <summary>One object a run created or retagged. <see cref="Guid"/> is null exactly while <see cref="ObjectState.Inserting"/>.</summary>
public sealed class JournalObject
{
    public JournalObject(string specId, Guid? guid, ObjectAction action, ObjectState state)
    {
        SpecId = specId ?? throw new ArgumentNullException(nameof(specId));
        Guid = guid;
        Action = action;
        State = state;
    }

    public string SpecId { get; }

    public Guid? Guid { get; }

    public ObjectAction Action { get; }

    public ObjectState State { get; }
}

/// <summary>Why an invocation stopped.</summary>
public sealed class JournalFailure
{
    public JournalFailure(FailureStage stage, string? specId, string error)
    {
        Stage = stage;
        SpecId = specId;
        Error = error ?? throw new ArgumentNullException(nameof(error));
    }

    public FailureStage Stage { get; }

    public string? SpecId { get; }

    public string Error { get; }
}

/// <summary>A conflict found by the resume planner (decision 8), as recorded in the journal.</summary>
public sealed class JournalConflict
{
    public JournalConflict(ConflictKind kind, string? specId, Guid? guid, string detail)
    {
        Kind = kind;
        SpecId = specId;
        Guid = guid;
        Detail = detail ?? throw new ArgumentNullException(nameof(detail));
    }

    public ConflictKind Kind { get; }

    /// <summary>The spec item, or the <c>SPEC_ID</c> tag value found on the object; null for none.</summary>
    public string? SpecId { get; }

    public Guid? Guid { get; }

    public string Detail { get; }
}

/// <summary>Journal timestamps: UTC to the second, <c>2026-11-08T09:00:00Z</c>.</summary>
public static class JournalTimestamp
{
    /// <summary>Formats a UTC time (invariant culture, Gregorian). Throws unless <paramref name="utc"/> is UTC.</summary>
    public static string Format(DateTime utc)
    {
        if (utc.Kind != DateTimeKind.Utc)
        {
            throw new ArgumentException("must be a UTC time", nameof(utc));
        }

        return utc.ToString("yyyy'-'MM'-'dd'T'HH':'mm':'ss'Z'", CultureInfo.InvariantCulture);
    }
}
