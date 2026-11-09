using System;
using System.IO;

namespace TeklaHarness.Core.Tests;

/// <summary>Locates files shared with the Python side (corpus, schema examples) from the test binaries.</summary>
internal static class RepoPaths
{
    private static readonly Lazy<string> RootLazy = new(FindRoot);

    public static string Root => RootLazy.Value;

    public static string StrictJsonCorpus => Path.Combine(Root, "tests", "fixtures", "strict-json");

    public static string SchemaExample(string fileName) => Path.Combine(Root, "schemas", "examples", fileName);

    private static string FindRoot()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null)
        {
            if (Directory.Exists(Path.Combine(dir.FullName, "tests", "fixtures", "strict-json")))
            {
                return dir.FullName;
            }

            dir = dir.Parent;
        }

        throw new InvalidOperationException("Repository root (with tests/fixtures/strict-json) not found above " + AppContext.BaseDirectory);
    }
}
