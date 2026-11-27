using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using DiskManager.Core.Native;
using Microsoft.Win32.SafeHandles;

namespace DiskManager.Core.Operations
{
    public static class GptEditor
    {
        private const int LayoutHeaderSize = 48;
        private const int EntrySize = 144;

        public static byte[] ReadLayout(int diskNumber, out string error)
        {
            error = null;
            using (var handle = NativeMethods.OpenPhysicalDrive(diskNumber))
            {
                if (handle.IsInvalid)
                {
                    error = "打开物理磁盘失败：" + Marshal.GetLastWin32Error();
                    return null;
                }
                var layout = Io.Query(handle, NativeMethods.IOCTL_DISK_GET_DRIVE_LAYOUT_EX, null, LayoutHeaderSize + 128 * EntrySize + 16, out var ioError);
                if (layout == null)
                {
                    error = "读取 GPT 布局失败：" + ioError;
                    return null;
                }
                return layout;
            }
        }

        public static void PatchMulti(byte[] layout, int systemPartitionNumber, long growth, IDictionary<int, long> donorOldStarts, bool growSystem = true)
        {
            if (layout == null || layout.Length < LayoutHeaderSize) throw new ArgumentException("layout is too small");
            if (BitConverter.ToInt32(layout, 0) != 1) throw new InvalidOperationException("layout is not GPT");
            var count = BitConverter.ToInt32(layout, 4);
            var foundSystem = false;
            var foundDonors = new HashSet<int>();
            for (var i = 0; i < count; i++)
            {
                var offset = LayoutHeaderSize + i * EntrySize;
                if (offset + EntrySize > layout.Length) break;
                var number = BitConverter.ToInt32(layout, offset + 24);
                if (number == systemPartitionNumber)
                {
                    if (growSystem)
                    {
                        var length = BitConverter.ToInt64(layout, offset + 16);
                        BitConverter.GetBytes(length + growth).CopyTo(layout, offset + 16);
                        layout[offset + 28] = 1;
                    }
                    foundSystem = true;
                    continue;
                }
                if (donorOldStarts == null || !donorOldStarts.ContainsKey(number)) continue;
                var oldStart = BitConverter.ToInt64(layout, offset + 8);
                if (oldStart != donorOldStarts[number]) throw new InvalidOperationException("donor partition offset changed: " + number);
                BitConverter.GetBytes(oldStart + growth).CopyTo(layout, offset + 8);
                layout[offset + 28] = 1;
                foundDonors.Add(number);
            }
            if (!foundSystem) throw new InvalidOperationException("system partition not found in GPT layout");
            foreach (var number in donorOldStarts.Keys)
                if (!foundDonors.Contains(number)) throw new InvalidOperationException("donor partition not found in GPT layout: " + number);
        }

        public static void PatchDataStart(byte[] layout, int dataPartitionNumber, long growth, long oldDataOffset)
        {
            if (layout == null || layout.Length < LayoutHeaderSize) throw new ArgumentException("layout is too small");
            if (BitConverter.ToInt32(layout, 0) != 1) throw new InvalidOperationException("layout is not GPT");
            var count = BitConverter.ToInt32(layout, 4);
            for (var i = 0; i < count; i++)
            {
                var offset = LayoutHeaderSize + i * EntrySize;
                if (offset + EntrySize > layout.Length) break;
                if (BitConverter.ToInt32(layout, offset + 24) != dataPartitionNumber) continue;
                var oldStart = BitConverter.ToInt64(layout, offset + 8);
                if (oldStart != oldDataOffset) throw new InvalidOperationException("data partition offset changed since the plan");
                BitConverter.GetBytes(oldStart + growth).CopyTo(layout, offset + 8);
                layout[offset + 28] = 1;
                return;
            }
            throw new InvalidOperationException("data partition not found in GPT layout");
        }

        public static long GetPartitionLength(byte[] layout, int partitionNumber)
        {
            if (layout == null || layout.Length < LayoutHeaderSize) throw new ArgumentException("layout is too small");
            var count = BitConverter.ToInt32(layout, 4);
            for (var i = 0; i < count; i++)
            {
                var offset = LayoutHeaderSize + i * EntrySize;
                if (offset + EntrySize > layout.Length) break;
                if (BitConverter.ToInt32(layout, offset + 24) == partitionNumber) return BitConverter.ToInt64(layout, offset + 16);
            }
            throw new InvalidOperationException("partition not found in GPT layout");
        }

        public static bool GrowPartition(int diskNumber, int partitionNumber, long bytesToGrow, out string error)
        {
            error = null;
            using (var handle = NativeMethods.CreateFileW(
                @"\\.\PhysicalDrive" + diskNumber,
                NativeMethods.GENERIC_READ | NativeMethods.GENERIC_WRITE,
                NativeMethods.FILE_SHARE_READ | NativeMethods.FILE_SHARE_WRITE,
                IntPtr.Zero,
                NativeMethods.OPEN_EXISTING,
                0,
                IntPtr.Zero))
            {
                if (handle.IsInvalid) { error = "打开磁盘失败：" + Marshal.GetLastWin32Error(); return false; }
                var input = new byte[16];
                BitConverter.GetBytes(partitionNumber).CopyTo(input, 0);
                BitConverter.GetBytes(bytesToGrow).CopyTo(input, 8);
                if (!Io.Control(handle, NativeMethods.IOCTL_DISK_GROW_PARTITION, input, out var ioError))
                {
                    error = "扩大分区失败：" + ioError;
                    return false;
                }
                var geometry = Io.Query(handle, NativeMethods.IOCTL_DISK_UPDATE_DRIVE_SIZE, null, 64, out var updateError);
                if (geometry == null)
                {
                    error = "刷新磁盘尺寸失败：" + updateError;
                    return false;
                }
                return true;
            }
        }

        public static bool UpdateDriveSize(int diskNumber, out string error)
        {
            error = null;
            using (var handle = NativeMethods.CreateFileW(
                @"\\.\PhysicalDrive" + diskNumber,
                NativeMethods.GENERIC_READ | NativeMethods.GENERIC_WRITE,
                NativeMethods.FILE_SHARE_READ | NativeMethods.FILE_SHARE_WRITE,
                IntPtr.Zero,
                NativeMethods.OPEN_EXISTING,
                0,
                IntPtr.Zero))
            {
                if (handle.IsInvalid) { error = "打开磁盘失败：" + Marshal.GetLastWin32Error(); return false; }
                var geometry = Io.Query(handle, NativeMethods.IOCTL_DISK_UPDATE_DRIVE_SIZE, null, 64, out var ioError);
                if (geometry == null) { error = "刷新磁盘尺寸失败：" + ioError; return false; }
                return true;
            }
        }

        public static void Patch(byte[] layout, int systemPartitionNumber, int dataPartitionNumber, long growth, long oldSystemSize, long oldDataOffset)
        {
            if (layout == null || layout.Length < LayoutHeaderSize) throw new ArgumentException("layout is too small");
            if (BitConverter.ToInt32(layout, 0) != 1) throw new InvalidOperationException("layout is not GPT");
            var count = BitConverter.ToInt32(layout, 4);
            var systemFound = false;
            var dataFound = false;
            for (var i = 0; i < count; i++)
            {
                var offset = LayoutHeaderSize + i * EntrySize;
                if (offset + EntrySize > layout.Length) break;
                var number = BitConverter.ToInt32(layout, offset + 24);
                if (number == systemPartitionNumber)
                {
                    var oldLength = BitConverter.ToInt64(layout, offset + 16);
                    if (oldLength != oldSystemSize) throw new InvalidOperationException("system partition size changed since the plan");
                    BitConverter.GetBytes(oldLength + growth).CopyTo(layout, offset + 16);
                    layout[offset + 28] = 1;
                    systemFound = true;
                }
                else if (number == dataPartitionNumber)
                {
                    var oldStart = BitConverter.ToInt64(layout, offset + 8);
                    if (oldStart != oldDataOffset) throw new InvalidOperationException("data partition offset changed since the plan");
                    BitConverter.GetBytes(oldStart + growth).CopyTo(layout, offset + 8);
                    layout[offset + 28] = 1;
                    dataFound = true;
                }
            }
            if (!systemFound) throw new InvalidOperationException("system partition not found in GPT layout");
            if (!dataFound) throw new InvalidOperationException("data partition not found in GPT layout");
        }

        public static bool WriteLayout(int diskNumber, byte[] layout, out string error)
        {
            error = null;
            using (var handle = NativeMethods.CreateFileW(
                @"\\.\PhysicalDrive" + diskNumber,
                NativeMethods.GENERIC_READ | NativeMethods.GENERIC_WRITE,
                NativeMethods.FILE_SHARE_READ | NativeMethods.FILE_SHARE_WRITE,
                IntPtr.Zero,
                NativeMethods.OPEN_EXISTING,
                0,
                IntPtr.Zero))
            {
                if (handle.IsInvalid)
                {
                    error = "打开磁盘写入 GPT 失败：" + Marshal.GetLastWin32Error();
                    return false;
                }
                if (!Io.Control(handle, NativeMethods.IOCTL_DISK_SET_DRIVE_LAYOUT_EX, layout, out var ioError))
                {
                    error = "写入 GPT 失败：" + ioError;
                    return false;
                }
                Io.Control(handle, NativeMethods.IOCTL_DISK_UPDATE_PROPERTIES, null, out var updateError);
                if (updateError != 0)
                {
                    error = "刷新磁盘属性失败：" + updateError;
                    return false;
                }
                return true;
            }
        }

        public static bool RestoreLayout(int diskNumber, byte[] originalLayout, out string error)
        {
            if (originalLayout == null) { error = "没有原始 GPT 备份"; return false; }
            return WriteLayout(diskNumber, originalLayout, out error);
        }

        public static void RefreshDiskProperties(int diskNumber)
        {
            using (var handle = NativeMethods.OpenPhysicalDrive(diskNumber))
            {
                if (!handle.IsInvalid) Io.Control(handle, NativeMethods.IOCTL_DISK_UPDATE_PROPERTIES, null, out _);
            }
        }
    }
}
