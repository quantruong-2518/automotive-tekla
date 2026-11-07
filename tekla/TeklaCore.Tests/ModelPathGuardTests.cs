using System;
using System.Globalization;
using System.Text;
using System.Threading;
using Xunit;

namespace TeklaHarness.Core.Tests;

/// <summary>
/// Contract safety rule 1 and ADR-0009 §4. The dangerous direction is a false "allowed":
/// writing while the open model is, or may be, the original.
/// </summary>
public class ModelPathGuardTests
{
    private const string Original = @"C:\Models\Project";
    private const string WorkingCopy = @"C:\Models\Project-copy";

    private static ModelPathCheck Check(string? open, string? workingCopy = WorkingCopy, string? original = Original)
        => ModelPathGuard.Check(open, workingCopy, original);

    // ---- allowed: the open model is provably the working copy, which is provably not the original

    [Theory]
    [InlineData(@"C:\Models\Project-copy")]
    [InlineData(@"c:\models\project-copy")] // drive and ASCII letters are case-insensitive
    [InlineData(@"C:\Models\Project-copy\")] // ModelInfo.ModelPath format is unverified (To verify #11)
    [InlineData(@"C:/Models/Project-copy")]
    [InlineData(@"C:\Models\\Project-copy")] // repeated separators collapse
    [InlineData(@"C:\Models\.\Project-copy")] // "." is the same folder
    public void Allows_the_working_copy_in_equivalent_spellings(string open)
    {
        var result = Check(open);
        Assert.True(result.Allowed, result.Detail);
        Assert.Equal(PathRefusal.None, result.Refusal);
        Assert.Equal(ExitCode.Ok, result.ExitCode);
    }

    [Fact]
    public void Allows_identical_vietnamese_folder_names()
    {
        var result = Check(@"D:\Dự án\Bản sao", @"D:\Dự án\Bản sao", @"D:\Dự án\Gốc");
        Assert.True(result.Allowed, result.Detail);
    }

    // ---- the open model is (or may be) the original

    [Theory]
    [InlineData(@"C:\Models\Project")]
    [InlineData(@"c:\models\project\")]
    [InlineData(@"C:/MODELS/PROJECT")]
    [InlineData(@"C:\Models\.\Project")]
    public void Refuses_when_the_open_model_is_the_original(string open)
    {
        var result = Check(open);
        Assert.False(result.Allowed);
        Assert.Equal(PathRefusal.OpenIsOriginal, result.Refusal);
        Assert.Equal(ExitCode.RefusedBySafetyRule, result.ExitCode);
    }

    [Theory]
    [InlineData(@"C:\Models\Project\sub")] // inside the original
    [InlineData(@"C:\Models")] // the original's parent
    [InlineData(@"c:\MODELS\project\Sub")]
    public void Refuses_when_the_open_model_overlaps_the_original(string open)
    {
        // Declared paths are valid and separate, so only the open-vs-original check can refuse.
        var result = Check(open);
        Assert.Equal(PathRefusal.OpenIsOriginal, result.Refusal);
        Assert.Equal(ExitCode.RefusedBySafetyRule, result.ExitCode);
    }

    // ---- names NTFS treats as one folder (independent review, reproduced on NTFS)

    [Theory]
    [InlineData('h', 0x0331)]
    [InlineData('i', 0x0307)]
    [InlineData('j', 0x030C)]
    [InlineData('t', 0x0308)]
    [InlineData('t', 0x0344)]
    [InlineData('w', 0x030A)]
    [InlineData('y', 0x030A)]
    public void Refuses_letter_plus_mark_that_differs_only_in_case(char letter, int mark)
    {
        // NTFS upper-cases each UTF-16 unit without normalising: "i"+U+0307 and "I"+U+0307 are
        // one folder, although NFKC composes only the upper-case spelling.
        var lower = @"C:\M\P" + letter + (char)mark;
        var upper = @"C:\M\P" + char.ToUpperInvariant(letter) + (char)mark;

        Assert.Equal(PathRefusal.WorkingCopyIsOriginal, Check(lower, lower, upper).Refusal);
        Assert.Equal(PathRefusal.WorkingCopyIsOriginal, Check(upper, upper, lower).Refusal);
        Assert.Equal(PathRefusal.WorkingCopyAndOriginalNested, Check(lower + @"\copy", lower + @"\copy", upper).Refusal);
        Assert.Equal(PathRefusal.OpenIsOriginal, Check(upper, lower + "-copy", lower).Refusal);
    }

    [Fact]
    public void Refuses_lunate_sigma_case_pair()
    {
        // U+03F2 and U+03F9 are one NTFS name. On .NET Framework, NFKC maps U+03F2 to final
        // sigma, which upper-cases differently; the windows-latest net48 leg pins this.
        var lower = "C:\\M\\x\u03F2";
        var upper = "C:\\M\\x\u03F9";
        Assert.Equal(PathRefusal.WorkingCopyIsOriginal, Check(lower, lower, upper).Refusal);
        Assert.Equal(PathRefusal.WorkingCopyIsOriginal, Check(upper, upper, lower).Refusal);
    }

    [Fact]
    public void Refuses_composed_lower_case_against_decomposed_upper_case()
    {
        // U+01F0 (j with caron) has no composed upper case; only NFKD lines it up with "J"+U+030C.
        var composed = "C:\\M\\x\u01F0";
        var decomposed = "C:\\M\\xJ\u030C";
        Assert.Equal(PathRefusal.WorkingCopyIsOriginal, Check(composed, composed, decomposed).Refusal);
    }

    [Fact]
    public void Refuses_compatibility_spellings_of_the_original()
    {
        // Full-width letters fold to ASCII only under compatibility normalisation (NFKC).
        var result = Check(@"C:\Models\Ｐｒｏｊｅｃｔ", @"C:\Models\Ｐｒｏｊｅｃｔ", Original);
        Assert.Equal(PathRefusal.WorkingCopyIsOriginal, result.Refusal);
    }

    // ---- declared paths that do not separate the copy from the original

    [Theory]
    [InlineData(@"C:\Models\Project", @"c:\models\project\")]
    [InlineData(@"C:\Models\Project\", @"C:/Models/Project")]
    public void Refuses_when_the_working_copy_is_the_original(string workingCopy, string original)
    {
        var result = Check(workingCopy, workingCopy, original);
        Assert.False(result.Allowed);
        Assert.Equal(PathRefusal.WorkingCopyIsOriginal, result.Refusal);
        Assert.Equal(ExitCode.RefusedBySafetyRule, result.ExitCode);
    }

    [Theory]
    [InlineData(@"C:\Models\Project\copy", @"C:\Models\Project")] // copy inside the original
    [InlineData(@"C:\Models", @"C:\Models\Project")] // original inside the copy
    public void Refuses_nested_working_copy_and_original(string workingCopy, string original)
    {
        var result = Check(workingCopy, workingCopy, original);
        Assert.False(result.Allowed);
        Assert.Equal(PathRefusal.WorkingCopyAndOriginalNested, result.Refusal);
        Assert.Equal(ExitCode.RefusedBySafetyRule, result.ExitCode);
    }

    [Fact]
    public void Does_not_treat_a_shared_name_prefix_as_nesting()
    {
        // "Project-copy" starts with "Project" as text but is a sibling folder.
        var result = Check(WorkingCopy);
        Assert.True(result.Allowed, result.Detail);
    }

    // ---- another model is open

    [Theory]
    [InlineData(@"C:\Models\Other")]
    [InlineData(@"D:\Models\Project-copy")]
    [InlineData(@"C:\Models\Project-copy\sub")]
    [InlineData(@"C:\Models\Project-cop")]
    public void Refuses_another_model_as_wrong_model(string open)
    {
        var result = Check(open);
        Assert.False(result.Allowed);
        Assert.Equal(PathRefusal.OpenIsNotWorkingCopy, result.Refusal);
        Assert.Equal(ExitCode.EnvironmentError, result.ExitCode); // contract: "wrong model" is exit 3
    }

    // ---- paths the guard cannot reason about: refuse, never guess

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("   ")]
    [InlineData(@"Models\Project-copy")] // relative
    [InlineData(@"C:Models\Project-copy")] // drive-relative
    [InlineData(@"\Models\Project-copy")] // rooted without drive
    [InlineData(@"\\server\share\Project-copy")] // UNC: may be the same folder as a mapped drive
    [InlineData(@"\\?\C:\Models\Project-copy")] // extended-length prefix
    [InlineData(@"\\.\C:\Models\Project-copy")] // device path
    [InlineData(@"C:\Models\..\Models\Project-copy")] // ".." may cross a junction
    [InlineData(@"C:\MODELS~1\Project-copy")] // 8.3 short name
    [InlineData(@"C:\Models\Project-copy.")] // Windows drops trailing dots
    [InlineData(@"C:\Models\Project-copy ")] // Windows drops trailing spaces
    [InlineData(@"C:\Models\Project-copy:stream")] // alternate data stream
    [InlineData("C:\\Models\\Pro\u0000ject-copy")] // control character
    [InlineData(@"C:\Models\Pro|ject-copy")] // invalid file name character
    [InlineData(@"C:\")] // drive root is never a model folder
    public void Refuses_an_open_path_it_cannot_prove(string? open)
    {
        var result = Check(open);
        Assert.False(result.Allowed);
        Assert.Equal(PathRefusal.OpenPathUnprovable, result.Refusal);
        Assert.Equal(ExitCode.RefusedBySafetyRule, result.ExitCode);
    }

    [Fact]
    public void Refuses_unpaired_surrogates()
    {
        // Built at run time: xUnit replaces lone surrogates in InlineData with U+FFFD.
        var high = "C:\\Models\\Pro" + (char)0xD800 + "ject";
        var low = "C:\\Models\\Pro" + (char)0xDC00 + "ject";
        var highAtEnd = "C:\\Models\\Project" + (char)0xD800;
        foreach (var open in new[] { high, low, highAtEnd })
        {
            Assert.Equal(PathRefusal.OpenPathUnprovable, Check(open).Refusal);
        }

        var pair = "C:\\Models\\Pro" + char.ConvertFromUtf32(0x1F3D7) + "ject"; // valid pair
        Assert.Equal(PathRefusal.OpenIsNotWorkingCopy, Check(pair).Refusal);
    }

    [Theory]
    [InlineData(null)]
    [InlineData(@"\\server\share\Project-copy")]
    [InlineData(@"C:\Models\..\Project-copy")]
    public void Refuses_a_working_copy_path_it_cannot_prove(string? workingCopy)
    {
        var result = Check(WorkingCopy, workingCopy);
        Assert.False(result.Allowed);
        Assert.Equal(PathRefusal.WorkingCopyPathUnprovable, result.Refusal);
    }

    [Theory]
    [InlineData(null)]
    [InlineData(@"\\server\share\Project")]
    [InlineData(@"C:\PROJEC~1")]
    public void Refuses_an_original_path_it_cannot_prove(string? original)
    {
        var result = Check(WorkingCopy, WorkingCopy, original);
        Assert.False(result.Allowed);
        Assert.Equal(PathRefusal.OriginalPathUnprovable, result.Refusal);
    }

    // ---- Unicode: Vietnamese names may arrive composed (NFC) or decomposed (NFD)

    [Fact]
    public void Refuses_when_copy_and_original_differ_only_by_unicode_normalization()
    {
        var nfc = @"D:\Dự án\Mô hình".Normalize(NormalizationForm.FormC);
        var nfd = nfc.Normalize(NormalizationForm.FormD);
        Assert.NotEqual(nfc, nfd); // precondition: the two spellings really differ as strings

        var result = Check(nfc, nfc, nfd);
        Assert.False(result.Allowed);
        Assert.Equal(PathRefusal.WorkingCopyIsOriginal, result.Refusal);
    }

    [Fact]
    public void Refuses_when_copy_and_original_differ_only_by_non_ascii_case()
    {
        var result = Check(@"D:\dự án\p", @"D:\dự án\p", @"D:\DỰ ÁN\P");
        Assert.False(result.Allowed);
        Assert.Equal(PathRefusal.WorkingCopyIsOriginal, result.Refusal);
    }

    [Fact]
    public void Does_not_accept_an_open_path_that_matches_the_copy_only_after_normalization()
    {
        var nfc = @"D:\Dự án\Bản sao".Normalize(NormalizationForm.FormC);
        var nfd = nfc.Normalize(NormalizationForm.FormD);

        var result = Check(nfd, nfc, @"D:\Dự án\Gốc");
        Assert.False(result.Allowed); // cannot prove NTFS sees the same folder
    }

    [Fact]
    public void Does_not_accept_an_open_path_that_matches_the_copy_only_by_non_ascii_case()
    {
        var result = Check(@"D:\DỰ ÁN\BẢN SAO", @"D:\dự án\bản sao", @"D:\dự án\gốc");
        Assert.False(result.Allowed);
    }

    // ---- culture must not change any decision (ADR-0009 §3)

    [Theory]
    [InlineData("tr-TR")] // "i".ToUpper() is "İ" here
    [InlineData("vi-VN")]
    [InlineData("en-US")]
    public void Decisions_do_not_depend_on_the_current_culture(string culture)
    {
        var saved = Thread.CurrentThread.CurrentCulture;
        try
        {
            Thread.CurrentThread.CurrentCulture = new CultureInfo(culture);
            Assert.True(Check(@"c:\models\file-copy", @"C:\MODELS\FILE-COPY", @"C:\Models\File").Allowed);
            Assert.Equal(
                PathRefusal.WorkingCopyIsOriginal,
                Check(@"C:\Models\file", @"C:\Models\file", @"c:\MODELS\FILE").Refusal);
        }
        finally
        {
            Thread.CurrentThread.CurrentCulture = saved;
        }
    }

    // ---- character rules: exact boundaries (found by mutation testing)

    [Theory]
    [InlineData('<')]
    [InlineData('>')]
    [InlineData('"')]
    [InlineData('|')]
    [InlineData('?')]
    [InlineData('*')]
    [InlineData(':')]
    public void Refuses_each_invalid_file_name_character(char c)
    {
        Assert.Equal(PathRefusal.OpenPathUnprovable, Check(@"C:\Models\Pro" + c + "ject-copy").Refusal);
    }

    [Theory]
    [InlineData("Project~0")]
    [InlineData("Project~9")]
    [InlineData("A~1B")]
    public void Refuses_tilde_followed_by_a_digit(string name)
    {
        Assert.Equal(PathRefusal.OpenPathUnprovable, Check(@"C:\Models\" + name).Refusal);
    }

    [Theory]
    [InlineData(@"C:\Models\Project2-copy")] // digits alone are fine
    [InlineData(@"C:\Models\a~b")] // tilde without a digit
    [InlineData(@"C:\Models\ab~")] // tilde at the end
    [InlineData(@"C:\Models\a~/b")] // tilde before a separator
    [InlineData(@"C:\Models\a~-b")] // tilde before a character below '0'
    public void Allows_digits_and_tildes_that_are_not_short_names(string path)
    {
        var result = Check(path, path);
        Assert.True(result.Allowed, result.Detail);
    }

    [Theory]
    [InlineData('A')]
    [InlineData('Z')]
    [InlineData('a')]
    [InlineData('z')]
    public void Accepts_every_drive_letter_boundary(char drive)
    {
        var path = drive + @":\Models\Project-copy";
        var result = Check(path, path, @"Q:\Models\Project");
        Assert.True(result.Allowed, result.Detail);
    }

    [Theory]
    [InlineData('@')] // just below 'A'
    [InlineData('[')] // just above 'Z'
    [InlineData('`')] // just below 'a'
    [InlineData('{')] // just above 'z'
    [InlineData('1')]
    public void Refuses_a_non_letter_drive(char drive)
    {
        Assert.Equal(PathRefusal.OpenPathUnprovable, Check(drive + @":\Models\Project-copy").Refusal);
    }

    [Fact]
    public void Folds_case_across_the_whole_ascii_alphabet()
    {
        var lower = @"C:\abcdefghijklmnopqrstuvwxyz";
        var upper = @"C:\ABCDEFGHIJKLMNOPQRSTUVWXYZ";
        var result = Check(upper, lower, @"C:\Original");
        Assert.True(result.Allowed, result.Detail);

        // Characters next to the letter ranges are not letters and must match exactly.
        Assert.False(Check(@"C:\a@", @"C:\a`", @"C:\Original").Allowed); // '@' vs '`'
        Assert.False(Check(@"C:\a[", @"C:\a{", @"C:\Original").Allowed); // '[' vs '{'
    }

    [Fact]
    public void Path_length_limit_is_exactly_32767()
    {
        var prefix = @"C:\";
        var atLimit = prefix + new string('a', 32767 - prefix.Length);
        var overLimit = atLimit + "a";
        Assert.True(Check(atLimit, atLimit).Allowed);
        Assert.Equal(PathRefusal.OpenPathUnprovable, Check(overLimit).Refusal);
    }

    [Fact]
    public void Loose_comparison_treats_text_it_cannot_normalise_as_possibly_equal()
    {
        var broken = "a" + (char)0xD800;
        var ex = Record.Exception(() => broken.Normalize(NormalizationForm.FormKC));
        Assert.IsAssignableFrom<ArgumentException>(ex); // precondition on this runtime

        Assert.True(WindowsPath.LooseSegmentEquals(broken, "completely different"));
    }

    // ---- the detail is for humans; it must name the reason

    [Theory]
    [InlineData("", "empty")]
    [InlineData(@"\\server\share\x", "not an absolute drive-letter path")]
    [InlineData(@"C:\", "drive root")]
    [InlineData(@"C:\a\..\b", "'..' segment")]
    [InlineData(@"C:\a.", "ends with a dot or space")]
    [InlineData("C:\\a\u0001b", "control character")]
    [InlineData(@"C:\a|b", "invalid character '|'")]
    [InlineData(@"C:\A~1", "8.3 short name")]
    public void Refusal_detail_names_the_parse_reason(string open, string expected)
    {
        Assert.Contains(expected, Check(open).Detail, StringComparison.Ordinal);
    }

    [Fact]
    public void Refusal_detail_names_the_reason_for_each_comparison()
    {
        Assert.Contains("too long", Check(@"C:\" + new string('a', 40000)).Detail, StringComparison.Ordinal);
        Assert.Contains("unpaired surrogate", Check("C:\\a" + (char)0xDC00).Detail, StringComparison.Ordinal);
        Assert.Contains("unpaired surrogate", Check("C:\\a" + (char)0xD800).Detail, StringComparison.Ordinal);
        Assert.Contains("working copy", Check(WorkingCopy, null).Detail, StringComparison.Ordinal);
        Assert.Contains("original", Check(WorkingCopy, WorkingCopy, null).Detail, StringComparison.Ordinal);
        Assert.Contains("may be the original", Check(Original, Original, Original).Detail, StringComparison.Ordinal);
        Assert.Contains("nested", Check(@"C:\Models", @"C:\Models", Original).Detail, StringComparison.Ordinal);
        Assert.Contains("overlap", Check(Original).Detail, StringComparison.Ordinal);
        Assert.Contains("is not the declared working copy", Check(@"C:\Other").Detail, StringComparison.Ordinal);
        Assert.Contains("is the working copy", Check(WorkingCopy).Detail, StringComparison.Ordinal);
    }

    [Fact]
    public void Refusal_detail_is_not_empty()
    {
        Assert.False(string.IsNullOrWhiteSpace(Check(Original).Detail));
    }

    [Fact]
    public void Allowed_result_carries_no_refusal()
    {
        var result = Check(WorkingCopy);
        Assert.True(result.Allowed);
        Assert.Equal(PathRefusal.None, result.Refusal);
    }

    [Fact]
    public void Rejects_paths_with_only_a_drive_and_dots()
    {
        Assert.Equal(PathRefusal.OpenPathUnprovable, Check(@"C:\.").Refusal);
        Assert.Equal(PathRefusal.OpenPathUnprovable, Check(@"C:\.\").Refusal);
    }

    [Fact]
    public void Static_api_never_throws_on_odd_input()
    {
        var odd = new[] { "C", "C:", "::", @"\\", @"\\?", "C:\\\u2028", new string('a', 40000) };
        foreach (var path in odd)
        {
            var ex = Record.Exception(() => Check(path));
            Assert.Null(ex);
            Assert.False(Check(path).Allowed);
        }
    }
}
