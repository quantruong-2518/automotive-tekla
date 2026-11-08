using System.Globalization;
using System.Threading;
using Xunit;

namespace TeklaHarness.Core.Tests;

/// <summary>ADR-0012 decision 1: RUN_ID pattern and the LOT tag text.</summary>
public sealed class RunIdTests
{
    [Theory]
    [InlineData("R1")]
    [InlineData("A")]
    [InlineData("0")]
    [InlineData("9_-Z")]
    [InlineData("R20261108-01")]
    [InlineData("R1234567890123456789012345678901")]
    public void Valid_run_ids(string runId)
    {
        Assert.True(RunId.IsValid(runId));
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("R12345678901234567890123456789012")]
    [InlineData("r1")]
    [InlineData("-R")]
    [InlineData("_R")]
    [InlineData("R 1")]
    [InlineData("R1\n")]
    [InlineData("R.1")]
    [InlineData("R/1")]
    [InlineData("Ｒ1")]
    [InlineData("Rİ")]
    [InlineData("@")]
    [InlineData("[")]
    [InlineData("/")]
    [InlineData(":")]
    [InlineData("R`")]
    [InlineData("R^")]
    public void Invalid_run_ids(string? runId)
    {
        Assert.False(RunId.IsValid(runId));
    }

    [Fact]
    public void Max_length_is_32()
    {
        Assert.Equal(32, RunId.MaxLength);
        Assert.True(RunId.IsValid(new string('A', 32)));
        Assert.False(RunId.IsValid(new string('A', 33)));
    }

    [Theory]
    [InlineData("vi-VN")]
    [InlineData("ar-SA")]
    [InlineData("de-DE")]
    public void Lot_tag_is_the_invariant_integer(string culture)
    {
        var saved = Thread.CurrentThread.CurrentCulture;
        try
        {
            Thread.CurrentThread.CurrentCulture = new CultureInfo(culture);
            Assert.Equal("1", RunId.LotTag(1));
            Assert.Equal("1000", RunId.LotTag(1000));
            Assert.Equal("2147483647", RunId.LotTag(int.MaxValue));
            Assert.True(RunId.IsValid("R1"));
        }
        finally
        {
            Thread.CurrentThread.CurrentCulture = saved;
        }
    }
}
