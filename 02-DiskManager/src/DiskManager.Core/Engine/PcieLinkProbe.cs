using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
using DiskManager.Core.Native;
using Microsoft.Win32.SafeHandles;

namespace DiskManager.Core.Engine
{
    internal static class PcieLinkProbe
    {
        private const uint DIGCF_PRESENT = 0x00000002;
        private const uint SPDRP_PHYSICAL_DEVICE_OBJECT_NAME = 0x0000000E;
        private const uint DEVPROP_TYPE_UINT32 = 0x00000007;
        private const uint CM_LOCATE_DEVNODE_NORMAL = 0;
        private const uint CR_SUCCESS = 0;
        private const uint CR_BUFFER_SMALL = 0x0000001A;

        private static readonly Guid DiskDriveClass = new Guid("4D36E967-E325-11CE-BFC1-08002BE10318");
        private static readonly Guid PciPropertyGuid = new Guid(0x3ab22e31, 0x8264, 0x4b4e, 0x9a, 0xf5, 0xa8, 0xd2, 0xd8, 0xe3, 0x3e, 0x62);
        private static readonly DEVPROPKEY LinkSpeedKey = new DEVPROPKEY { fmtid = PciPropertyGuid, pid = 9 };
        private static readonly DEVPROPKEY LinkWidthKey = new DEVPROPKEY { fmtid = PciPropertyGuid, pid = 10 };

        [StructLayout(LayoutKind.Sequential)]
        private struct SP_DEVINFO_DATA
        {
            public uint cbSize;
            public Guid ClassGuid;
            public uint DevInst;
            public UIntPtr Reserved;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct DEVPROPKEY
        {
            public Guid fmtid;
            public uint pid;
        }

        [DllImport("setupapi.dll", SetLastError = true, CharSet = CharSet.Unicode)]
        private static extern IntPtr SetupDiGetClassDevsW(ref Guid classGuid, string enumerator, IntPtr hwndParent, uint flags);

        [DllImport("setupapi.dll", SetLastError = true)]
        private static extern bool SetupDiEnumDeviceInfo(IntPtr deviceInfoSet, uint memberIndex, ref SP_DEVINFO_DATA deviceInfoData);

        [DllImport("setupapi.dll", SetLastError = true, CharSet = CharSet.Unicode)]
        private static extern bool SetupDiGetDeviceRegistryPropertyW(
            IntPtr deviceInfoSet,
            ref SP_DEVINFO_DATA deviceInfoData,
            uint property,
            out uint propertyRegDataType,
            IntPtr propertyBuffer,
            uint propertyBufferSize,
            out uint requiredSize);

        [DllImport("setupapi.dll", SetLastError = true, CharSet = CharSet.Unicode)]
        private static extern bool SetupDiGetDeviceInstanceIdW(
            IntPtr deviceInfoSet,
            ref SP_DEVINFO_DATA deviceInfoData,
            StringBuilder deviceInstanceId,
            uint deviceInstanceIdSize,
            out uint requiredSize);

        [DllImport("setupapi.dll", SetLastError = true)]
        private static extern bool SetupDiDestroyDeviceInfoList(IntPtr deviceInfoSet);

        [DllImport("cfgmgr32.dll", CharSet = CharSet.Unicode)]
        private static extern uint CM_Locate_DevNodeW(out uint devInst, string deviceId, uint flags);

        [DllImport("cfgmgr32.dll")]
        private static extern uint CM_Get_Parent(out uint parentDevInst, uint devInst, uint flags);

        [DllImport("cfgmgr32.dll", CharSet = CharSet.Unicode)]
        private static extern uint CM_Get_DevNode_PropertyW(
            uint devInst,
            ref DEVPROPKEY propertyKey,
            out uint propertyType,
            IntPtr propertyBuffer,
            ref uint propertyBufferSize,
            uint flags);

        public static Dictionary<int, string> MapAll()
        {
            var result = new Dictionary<int, string>();
            IntPtr deviceSet = IntPtr.Zero;
            try
            {
                var classGuid = DiskDriveClass;
                deviceSet = SetupDiGetClassDevsW(ref classGuid, null, IntPtr.Zero, DIGCF_PRESENT);
                if (deviceSet == IntPtr.Zero || deviceSet == new IntPtr(-1)) return result;

                var info = new SP_DEVINFO_DATA { cbSize = (uint)Marshal.SizeOf(typeof(SP_DEVINFO_DATA)) };
                for (uint index = 0; SetupDiEnumDeviceInfo(deviceSet, index, ref info); index++)
                {
                    var diskNumber = ReadDiskNumber(deviceSet, ref info);
                    if (diskNumber < 0) continue;
                    var link = ReadLink(deviceSet, ref info);
                    if (!string.IsNullOrEmpty(link)) result[diskNumber] = link;
                }
            }
            catch
            {
                // PCIe link information is best-effort; the disk scan stays valid without it.
            }
            finally
            {
                if (deviceSet != IntPtr.Zero && deviceSet != new IntPtr(-1)) SetupDiDestroyDeviceInfoList(deviceSet);
            }
            return result;
        }

        private static int ReadDiskNumber(IntPtr deviceSet, ref SP_DEVINFO_DATA info)
        {
            var buffer = Marshal.AllocHGlobal(1024);
            try
            {
                uint type, required;
                if (!SetupDiGetDeviceRegistryPropertyW(deviceSet, ref info, SPDRP_PHYSICAL_DEVICE_OBJECT_NAME, out type, buffer, 1024, out required)) return -1;
                var name = Marshal.PtrToStringUni(buffer);
                if (string.IsNullOrEmpty(name)) return -1;
                var marker = name.IndexOf("Harddisk", StringComparison.OrdinalIgnoreCase);
                if (marker >= 0)
                {
                    var start = marker + "Harddisk".Length;
                    var end = start;
                    while (end < name.Length && char.IsDigit(name[end])) end++;
                    if (end == start) return -1;
                    int number;
                    return int.TryParse(name.Substring(start, end - start), out number) ? number : -1;
                }

                return ReadDiskNumberFromPdo(name);
            }
            finally
            {
                Marshal.FreeHGlobal(buffer);
            }
        }

        private static int ReadDiskNumberFromPdo(string pdoName)
        {
            SafeFileHandle handle = null;
            try
            {
                handle = NativeMethods.CreateFileW(
                    @"\\.\GLOBALROOT" + pdoName,
                    0,
                    NativeMethods.FILE_SHARE_READ | NativeMethods.FILE_SHARE_WRITE,
                    IntPtr.Zero,
                    NativeMethods.OPEN_EXISTING,
                    0,
                    IntPtr.Zero);
                if (handle.IsInvalid) return -1;
                var buffer = Io.Query(handle, NativeMethods.IOCTL_STORAGE_GET_DEVICE_NUMBER, null, 32, out _);
                if (buffer == null || buffer.Length < 8) return -1;
                return Io.ReadInt32(buffer, 4);
            }
            catch
            {
                return -1;
            }
            finally
            {
                if (handle != null) handle.Dispose();
            }
        }

        private static string ReadLink(IntPtr deviceSet, ref SP_DEVINFO_DATA info)
        {
            var instanceId = new StringBuilder(1024);
            uint required;
            if (!SetupDiGetDeviceInstanceIdW(deviceSet, ref info, instanceId, (uint)instanceId.Capacity, out required)) return null;

            uint devInst;
            if (CM_Locate_DevNodeW(out devInst, instanceId.ToString(), CM_LOCATE_DEVNODE_NORMAL) != CR_SUCCESS) return null;

            uint width = 0;
            for (var depth = 0; depth < 8 && devInst != 0; depth++)
            {
                var speedValue = ReadUIntProperty(devInst, LinkSpeedKey);
                if (speedValue.HasValue)
                {
                    var widthValue = ReadUIntProperty(devInst, LinkWidthKey);
                    if (widthValue.HasValue) width = widthValue.Value;
                    return Format(speedValue.Value, width);
                }

                uint parent;
                if (CM_Get_Parent(out parent, devInst, 0) != CR_SUCCESS) break;
                devInst = parent;
            }
            return null;
        }

        private static uint? ReadUIntProperty(uint devInst, DEVPROPKEY key)
        {
            var size = 8u;
            var buffer = Marshal.AllocHGlobal((int)size);
            try
            {
                uint type;
                var status = CM_Get_DevNode_PropertyW(devInst, ref key, out type, buffer, ref size, 0);
                if (status == CR_BUFFER_SMALL && size <= 64)
                {
                    Marshal.FreeHGlobal(buffer);
                    buffer = Marshal.AllocHGlobal((int)size);
                    status = CM_Get_DevNode_PropertyW(devInst, ref key, out type, buffer, ref size, 0);
                }
                if (status != CR_SUCCESS || type != DEVPROP_TYPE_UINT32 || size < 4) return null;
                return (uint)Marshal.ReadInt32(buffer);
            }
            finally
            {
                if (buffer != IntPtr.Zero) Marshal.FreeHGlobal(buffer);
            }
        }

        private static string Format(uint speed, uint width)
        {
            string generation;
            switch (speed)
            {
                case 1: generation = "1.0"; break;
                case 2: generation = "2.0"; break;
                case 3: generation = "3.0"; break;
                case 4: generation = "4.0"; break;
                case 5: generation = "5.0"; break;
                case 6: generation = "6.0"; break;
                default: return null;
            }

            if (width == 0) return "PCIe " + generation;
            string lanes;
            switch (width)
            {
                case 1: lanes = "x1"; break;
                case 2: lanes = "x2"; break;
                case 4: lanes = "x4"; break;
                case 8: lanes = "x8"; break;
                case 12: lanes = "x12"; break;
                case 16: lanes = "x16"; break;
                case 32: lanes = "x32"; break;
                default: lanes = "x" + width; break;
            }
            return "PCIe " + generation + " " + lanes;
        }
    }
}

