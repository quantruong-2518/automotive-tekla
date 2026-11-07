using Xunit;

namespace TeklaHarness.Core.Tests;

public class ExitCodeTests
{
    // Values fixed by docs/tekla-cli-contract.md (Conventions); callers and agents rely on them.
    [Theory]
    [InlineData(ExitCode.Ok, 0)]
    [InlineData(ExitCode.ValidationFailure, 1)]
    [InlineData(ExitCode.UsageError, 2)]
    [InlineData(ExitCode.EnvironmentError, 3)]
    [InlineData(ExitCode.TeklaApiError, 4)]
    [InlineData(ExitCode.RefusedBySafetyRule, 5)]
    public void Values_match_the_contract(ExitCode code, int expected)
    {
        Assert.Equal(expected, (int)code);
    }

    [Fact]
    public void No_other_exit_codes_exist()
    {
        Assert.Equal(6, System.Enum.GetValues(typeof(ExitCode)).Length);
    }
}
