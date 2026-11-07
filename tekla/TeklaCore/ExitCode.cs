namespace TeklaHarness.Core;

/// <summary>Process exit codes fixed by docs/tekla-cli-contract.md (Conventions).</summary>
public enum ExitCode
{
    /// <summary>Success.</summary>
    Ok = 0,

    /// <summary>Validation failure: nothing written, or an existing object differs from its spec item on resume.</summary>
    ValidationFailure = 1,

    /// <summary>Usage error: bad arguments.</summary>
    UsageError = 2,

    /// <summary>Environment error: Tekla not running, wrong model, wrong version, tag UDAs not defined.</summary>
    EnvironmentError = 3,

    /// <summary>Tekla API error: stopped; objects done so far are kept and listed in the run journal.</summary>
    TeklaApiError = 4,

    /// <summary>Refused by a safety rule.</summary>
    RefusedBySafetyRule = 5,
}
