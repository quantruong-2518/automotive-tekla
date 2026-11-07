using System;
using System.Globalization;

namespace TeklaHarness.Core;

/// <summary>
/// Identity of a file or folder on Windows: volume serial number plus the 128-bit file ID
/// (FILE_ID_INFO). Two handles name the same folder when all three parts are equal.
/// </summary>
public readonly struct FileIdentity : IEquatable<FileIdentity>
{
    public FileIdentity(ulong volumeSerial, ulong fileIdHigh, ulong fileIdLow)
    {
        VolumeSerial = volumeSerial;
        FileIdHigh = fileIdHigh;
        FileIdLow = fileIdLow;
    }

    public ulong VolumeSerial { get; }

    public ulong FileIdHigh { get; }

    public ulong FileIdLow { get; }

    public bool Equals(FileIdentity other)
        => VolumeSerial == other.VolumeSerial && FileIdHigh == other.FileIdHigh && FileIdLow == other.FileIdLow;

    public override bool Equals(object? obj) => obj is FileIdentity other && Equals(other);

    public override int GetHashCode()
    {
        unchecked
        {
            var hash = VolumeSerial.GetHashCode();
            hash = (hash * 397) ^ FileIdHigh.GetHashCode();
            return (hash * 397) ^ FileIdLow.GetHashCode();
        }
    }

    public override string ToString()
        => string.Format(CultureInfo.InvariantCulture, "{0:X16}:{1:X16}:{2:X16}", VolumeSerial, FileIdHigh, FileIdLow);

    public static bool operator ==(FileIdentity left, FileIdentity right) => left.Equals(right);

    public static bool operator !=(FileIdentity left, FileIdentity right) => !left.Equals(right);
}

/// <summary>A folder as the operating system resolved it: its identity and its final path.</summary>
public sealed class ResolvedFolder
{
    public ResolvedFolder(FileIdentity identity, string finalPath)
    {
        Identity = identity;
        FinalPath = finalPath;
    }

    public FileIdentity Identity { get; }

    /// <summary>Path with every alias resolved, as the OS returns it, e.g. <c>\\?\C:\Models\P</c> or <c>\\?\UNC\server\share\P</c>.</summary>
    public string FinalPath { get; }
}

/// <summary>Asks the operating system which folder a path names (slice S1a). Implemented on Windows.</summary>
public interface IFolderResolver
{
    /// <summary>Returns false with a reason when the identity cannot be read; never guesses.</summary>
    bool TryResolve(string path, out ResolvedFolder? folder, out string error);

    /// <summary>
    /// Walks <paramref name="folder"/> (an OS final path) without following links. Sets
    /// <paramref name="offender"/> to the first junction, symlink or mount point found, or, when
    /// <paramref name="includeHardLinks"/>, the first file with more than one hard link; null when
    /// clean. Returns false with a reason when the walk cannot finish.
    /// </summary>
    bool TryFindLink(string folder, bool includeHardLinks, out string? offender, out string error);
}
