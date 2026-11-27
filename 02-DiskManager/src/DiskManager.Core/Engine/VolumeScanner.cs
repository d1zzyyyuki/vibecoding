using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using DiskManager.Core.Native;
using Microsoft.Win32.SafeHandles;

namespace DiskManager.Core.Engine
{
    internal sealed class VolumeRecord
    {
        public string GuidPath;
        public string DriveLetter;
        public string Label;
        public string FileSystem;
        public long TotalBytes;
        public long FreeBytes;
        public int DiskNumber = -1;
        public long StartingOffset;
    }

    internal static class VolumeScanner
    {
        public static List<VolumeRecord> Scan(out string systemVolumeGuid, List<string> warnings)
        {
            var volumes = new List<VolumeRecord>();
            systemVolumeGuid = null;

            var findHandle = IntPtr.Zero;
            try
            {
                var name = new StringBuilder(261);
                findHandle = NativeMethods.FindFirstVolumeW(name, 261);
                if (findHandle == IntPtr.Zero || findHandle == new IntPtr(-1))
                {
                    if (warnings != null) warnings.Add("无法枚举卷: " + System.Runtime.InteropServices.Marshal.GetLastWin32Error());
                    return volumes;
                }

                do
                {
                    var volumePath = name.ToString();
                    var record = new VolumeRecord { GuidPath = volumePath };

                    using (var handle = NativeMethods.TryOpenVolume(volumePath))
                    {
                        if (!handle.IsInvalid)
                        {
                            var extents = Io.Query(handle, NativeMethods.IOCTL_VOLUME_GET_VOLUME_DISK_EXTENTS, null, 1024, out _);
                            if (extents != null && extents.Length >= 32)
                            {
                                var count = Io.ReadInt32(extents, 0);
                                if (count > 0)
                                {
                                    // VOLUME_DISK_EXTENTS aligns the first DISK_EXTENT to offset 8.
                                    record.DiskNumber = Io.ReadInt32(extents, 8);
                                    record.StartingOffset = Io.ReadInt64(extents, 16);
                                }
                            }
                        }
                    }

                    var paths = ReadPathNames(volumePath);
                    foreach (var path in paths)
                    {
                        if (path.Length >= 2 && path[1] == ':')
                        {
                            record.DriveLetter = char.ToUpperInvariant(path[0]).ToString();
                            break;
                        }
                    }

                    var label = new StringBuilder(261);
                    var fileSystem = new StringBuilder(261);
                    uint serial, maxComponent, flags;
                    if (NativeMethods.GetVolumeInformationW(volumePath, label, 261, out serial, out maxComponent, out flags, fileSystem, 261))
                    {
                        record.Label = label.ToString();
                        record.FileSystem = fileSystem.ToString();
                    }

                    ulong freeAvailable, totalBytes, totalFree;
                    if (NativeMethods.GetDiskFreeSpaceExW(volumePath, out freeAvailable, out totalBytes, out totalFree))
                    {
                        record.TotalBytes = ClampToLong(totalBytes);
                        record.FreeBytes = ClampToLong(freeAvailable);
                    }

                    volumes.Add(record);
                } while (NativeMethods.FindNextVolumeW(findHandle, name, 261));

                systemVolumeGuid = GetSystemVolumeGuid();
            }
            finally
            {
                if (findHandle != IntPtr.Zero && findHandle != new IntPtr(-1)) NativeMethods.FindVolumeClose(findHandle);
            }

            return volumes;
        }

        public static string GetSystemVolumeGuid()
        {
            try
            {
                var systemDir = new StringBuilder(261);
                NativeMethods.GetSystemDirectoryW(systemDir, 261);
                var root = Path.GetPathRoot(systemDir.ToString());
                if (string.IsNullOrEmpty(root)) return null;
                return GetVolumeGuid(root);
            }
            catch
            {
                return null;
            }
        }

        public static string GetWindowsVolumeGuid()
        {
            try
            {
                var windowsDir = new StringBuilder(261);
                NativeMethods.GetWindowsDirectoryW(windowsDir, 261);
                var root = Path.GetPathRoot(windowsDir.ToString());
                if (string.IsNullOrEmpty(root)) return null;
                return GetVolumeGuid(root);
            }
            catch
            {
                return null;
            }
        }

        private static string GetVolumeGuid(string mountPoint)
        {
            var name = new StringBuilder(1024);
            if (!NativeMethods.GetVolumeNameForVolumeMountPointW(mountPoint, name, 1024)) return null;
            return Normalize(name.ToString());
        }

        public static string Normalize(string volumeGuid)
        {
            return string.IsNullOrEmpty(volumeGuid) ? string.Empty : volumeGuid.TrimEnd('\\').ToUpperInvariant();
        }

        private static List<string> ReadPathNames(string volumePath)
        {
            var result = new List<string>();
            var buffer = new char[32768];
            uint needed;
            if (!NativeMethods.GetVolumePathNamesForVolumeNameW(volumePath, buffer, (uint)buffer.Length, out needed))
            {
                if (needed <= buffer.Length) return result;
                buffer = new char[needed + 2];
                if (!NativeMethods.GetVolumePathNamesForVolumeNameW(volumePath, buffer, (uint)buffer.Length, out needed)) return result;
            }

            var start = 0;
            for (var i = 0; i < buffer.Length; i++)
            {
                if (buffer[i] != '\0') continue;
                if (i == start) break;
                var path = new string(buffer, start, i - start);
                if (path.Length > 0) result.Add(path);
                start = i + 1;
            }
            return result;
        }

        private static long ClampToLong(ulong value)
        {
            return value > long.MaxValue ? long.MaxValue : (long)value;
        }
    }
}
