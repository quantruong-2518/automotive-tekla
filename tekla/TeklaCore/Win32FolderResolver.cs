using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.IO;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

namespace TeklaHarness.Core;

/// <summary>
/// Windows implementation of <see cref="IFolderResolver"/> (slice S1a). Facts and sources:
/// docs/research/windows-file-identity.md. Every failure is reported, never guessed.
/// </summary>
/// <remarks>
/// Opens the folder for attributes only, following reparse points (junctions, symlinks, mount
/// points resolve to their target), reads the 128-bit FILE_ID_INFO and the final path. Only NTFS
/// and ReFS are accepted: FAT/exFAT IDs are not stable. Must run in the process that writes,
/// because subst and mapped drive letters are per logon session.
/// </remarks>
public sealed class Win32FolderResolver : IFolderResolver
{
    private const string LongPrefix = @"\\?\";

    public bool TryResolve(string path, out ResolvedFolder? folder, out string error)
    {
        folder = null;
        if (!RuntimeInformation.IsOSPlatform(OSPlatform.Windows))
        {
            error = "folder identity needs Windows";
            return false;
        }

        if (string.IsNullOrEmpty(path))
        {
            error = "empty path";
            return false;
        }

        // Callers pass canonical text from the path guard (absolute drive path) or OS final
        // paths (already prefixed). The prefix lifts MAX_PATH on .NET Framework.
        var full = path.StartsWith(LongPrefix, StringComparison.Ordinal) ? path : LongPrefix + path;

        using var handle = NativeMethods.CreateFileW(
            full,
            NativeMethods.FileReadAttributes,
            NativeMethods.FileShareReadWriteDelete,
            IntPtr.Zero,
            NativeMethods.OpenExisting,
            NativeMethods.FileFlagBackupSemantics,
            IntPtr.Zero);
        if (handle.IsInvalid)
        {
            error = Win32Error("CreateFileW");
            return false;
        }

        var fileSystem = new char[NativeMethods.MaxPath + 1];
        if (!NativeMethods.GetVolumeInformationByHandleW(handle, null, 0, out _, out _, out _, fileSystem, (uint)fileSystem.Length))
        {
            error = Win32Error("GetVolumeInformationByHandleW");
            return false;
        }

        var fsName = TrimNul(fileSystem);
        if (!string.Equals(fsName, "NTFS", StringComparison.OrdinalIgnoreCase)
            && !string.Equals(fsName, "ReFS", StringComparison.OrdinalIgnoreCase))
        {
            error = $"file system '{fsName}' has no stable file IDs (NTFS or ReFS needed)";
            return false;
        }

        if (!NativeMethods.GetFileInformationByHandleEx(handle, NativeMethods.FileIdInfo, out var info, (uint)Marshal.SizeOf<NativeMethods.FileIdInfoStruct>()))
        {
            error = Win32Error("GetFileInformationByHandleEx(FileIdInfo)");
            return false;
        }

        if (!TryFinalPath(handle, out var finalPath, out error))
        {
            return false;
        }

        // A drive letter can still be a network drive (research step 7); UNC final paths are
        // refused by the guard, this catches redirectors that report a local-looking path.
        if (finalPath.Length >= 7 && finalPath[5] == ':' && finalPath[6] == '\\')
        {
            var driveType = NativeMethods.GetDriveTypeW(finalPath.Substring(4, 3));
            if (driveType is not (NativeMethods.DriveRemovable or NativeMethods.DriveFixed or NativeMethods.DriveRamDisk))
            {
                error = $"drive '{finalPath.Substring(4, 2)}' has type {driveType} (fixed, removable or RAM disk needed)";
                return false;
            }
        }

        folder = new ResolvedFolder(new FileIdentity(info.VolumeSerialNumber, info.FileIdHigh, info.FileIdLow), finalPath);
        error = string.Empty;
        return true;
    }

    public bool TryFindLink(string folder, bool includeHardLinks, out string? offender, out string error)
    {
        offender = null;
        if (!RuntimeInformation.IsOSPlatform(OSPlatform.Windows))
        {
            error = "folder scan needs Windows";
            return false;
        }

        try
        {
            // Depth-first, never entering a reparse point: any junction, symlink or mount point
            // is itself the finding.
            var pending = new Stack<string>();
            pending.Push(folder);
            while (pending.Count > 0)
            {
                foreach (var entry in new DirectoryInfo(pending.Pop()).EnumerateFileSystemInfos())
                {
                    if ((entry.Attributes & FileAttributes.ReparsePoint) != 0)
                    {
                        offender = entry.FullName;
                        error = string.Empty;
                        return true;
                    }

                    if ((entry.Attributes & FileAttributes.Directory) != 0)
                    {
                        pending.Push(entry.FullName);
                        continue;
                    }

                    if (!includeHardLinks)
                    {
                        continue;
                    }

                    if (!TryLinkCount(entry.FullName, out var links, out error))
                    {
                        return false;
                    }

                    if (links > 1)
                    {
                        offender = entry.FullName;
                        return true;
                    }
                }
            }
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or System.Security.SecurityException)
        {
            error = $"scan of '{folder}' failed: {ex.GetType().Name}: {ex.Message}";
            return false;
        }

        error = string.Empty;
        return true;
    }

    private static bool TryLinkCount(string file, out uint links, out string error)
    {
        links = 0;
        using var handle = NativeMethods.CreateFileW(
            file,
            NativeMethods.FileReadAttributes,
            NativeMethods.FileShareReadWriteDelete,
            IntPtr.Zero,
            NativeMethods.OpenExisting,
            NativeMethods.FileFlagBackupSemantics | NativeMethods.FileFlagOpenReparsePoint,
            IntPtr.Zero);
        if (handle.IsInvalid)
        {
            error = Win32Error($"CreateFileW('{file}')");
            return false;
        }

        if (!NativeMethods.GetFileInformationByHandle(handle, out var info))
        {
            error = Win32Error($"GetFileInformationByHandle('{file}')");
            return false;
        }

        links = info.NumberOfLinks;
        error = string.Empty;
        return true;
    }

    private static bool TryFinalPath(SafeFileHandle handle, out string finalPath, out string error)
    {
        var buffer = new char[NativeMethods.MaxPath + 1];
        for (var attempt = 0; attempt < 2; attempt++)
        {
            var length = NativeMethods.GetFinalPathNameByHandleW(handle, buffer, (uint)buffer.Length, NativeMethods.FileNameNormalized | NativeMethods.VolumeNameDos);
            if (length == 0)
            {
                finalPath = string.Empty;
                error = Win32Error("GetFinalPathNameByHandleW");
                return false;
            }

            if (length < buffer.Length)
            {
                finalPath = new string(buffer, 0, (int)length);
                error = string.Empty;
                return true;
            }

            buffer = new char[length + 1]; // length includes the terminating NUL when too small
        }

        finalPath = string.Empty;
        error = "GetFinalPathNameByHandleW: path keeps growing";
        return false;
    }

    private static string TrimNul(char[] buffer)
    {
        var end = Array.IndexOf(buffer, '\0');
        return new string(buffer, 0, end < 0 ? buffer.Length : end);
    }

    private static string Win32Error(string call)
    {
        var code = Marshal.GetLastWin32Error();
        return $"{call} failed: Win32 error {code} ({new Win32Exception(code).Message})";
    }

    /// <summary>Internal for tests: native struct sizes must match the Win32 headers.</summary>
    internal static int FileIdInfoSize => Marshal.SizeOf<NativeMethods.FileIdInfoStruct>();

    /// <summary>Internal for tests.</summary>
    internal static int ByHandleFileInformationSize => Marshal.SizeOf<NativeMethods.ByHandleFileInformation>();

    private static class NativeMethods
    {
        public const uint FileReadAttributes = 0x80;
        public const uint FileShareReadWriteDelete = 0x1 | 0x2 | 0x4;
        public const uint OpenExisting = 3;
        public const uint FileFlagBackupSemantics = 0x02000000;
        public const uint FileFlagOpenReparsePoint = 0x00200000;
        public const uint DriveRemovable = 2;
        public const uint DriveFixed = 3;
        public const uint DriveRamDisk = 6;

        // FILETIME is two DWORDs: 4-byte packing keeps the native 52-byte layout.
        [StructLayout(LayoutKind.Sequential, Pack = 4)]
        public struct ByHandleFileInformation
        {
            public uint FileAttributes;
            public ulong CreationTime;
            public ulong LastAccessTime;
            public ulong LastWriteTime;
            public uint VolumeSerialNumber;
            public uint FileSizeHigh;
            public uint FileSizeLow;
            public uint NumberOfLinks;
            public uint FileIndexHigh;
            public uint FileIndexLow;
        }

        [DllImport("kernel32.dll", SetLastError = true, ExactSpelling = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        public static extern bool GetFileInformationByHandle(SafeFileHandle hFile, out ByHandleFileInformation lpFileInformation);

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, ExactSpelling = true)]
        public static extern uint GetDriveTypeW(string lpRootPathName);
        public const int FileIdInfo = 0x12;
        public const uint FileNameNormalized = 0x0;
        public const uint VolumeNameDos = 0x0;
        public const int MaxPath = 260;

        [StructLayout(LayoutKind.Sequential)]
        public struct FileIdInfoStruct
        {
            public ulong VolumeSerialNumber;
            public ulong FileIdLow; // FILE_ID_128.Identifier[0..7], little-endian
            public ulong FileIdHigh; // FILE_ID_128.Identifier[8..15]
        }

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true, ExactSpelling = true)]
        public static extern SafeFileHandle CreateFileW(
            string lpFileName,
            uint dwDesiredAccess,
            uint dwShareMode,
            IntPtr lpSecurityAttributes,
            uint dwCreationDisposition,
            uint dwFlagsAndAttributes,
            IntPtr hTemplateFile);

        [DllImport("kernel32.dll", SetLastError = true, ExactSpelling = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        public static extern bool GetFileInformationByHandleEx(
            SafeFileHandle hFile,
            int fileInformationClass,
            out FileIdInfoStruct lpFileInformation,
            uint dwBufferSize);

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true, ExactSpelling = true)]
        public static extern uint GetFinalPathNameByHandleW(
            SafeFileHandle hFile,
            [Out] char[] lpszFilePath,
            uint cchFilePath,
            uint dwFlags);

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true, ExactSpelling = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        public static extern bool GetVolumeInformationByHandleW(
            SafeFileHandle hFile,
            [Out] char[]? lpVolumeNameBuffer,
            uint nVolumeNameSize,
            out uint lpVolumeSerialNumber,
            out uint lpMaximumComponentLength,
            out uint lpFileSystemFlags,
            [Out] char[] lpFileSystemNameBuffer,
            uint nFileSystemNameSize);
    }
}
