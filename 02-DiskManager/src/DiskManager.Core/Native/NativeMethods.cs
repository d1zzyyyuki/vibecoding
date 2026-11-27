using System;
using System.Runtime.InteropServices;
using System.Text;
using Microsoft.Win32.SafeHandles;

namespace DiskManager.Core.Native
{
    internal static class NativeMethods
    {
        public const uint GENERIC_READ = 0x80000000;
        public const uint GENERIC_WRITE = 0x40000000;
        public const uint FILE_SHARE_READ = 0x00000001;
        public const uint FILE_SHARE_WRITE = 0x00000002;
        public const uint OPEN_EXISTING = 3;
        public const uint FILE_FLAG_NO_BUFFERING = 0x20000000;
        public const uint FILE_FLAG_SEQUENTIAL_SCAN = 0x08000000;

        public const uint MEM_COMMIT = 0x1000;
        public const uint MEM_RESERVE = 0x2000;
        public const uint MEM_RELEASE = 0x8000;
        public const uint PAGE_READWRITE = 0x04;

        public const uint IOCTL_DISK_GET_DRIVE_LAYOUT_EX = 0x00070050;
        public const uint IOCTL_DISK_GET_LENGTH_INFO = 0x0007405C;
        public const uint IOCTL_DISK_GET_DRIVE_GEOMETRY_EX = 0x000700A0;
        public const uint IOCTL_DISK_UPDATE_PROPERTIES = 0x00070140;
        public const uint IOCTL_DISK_UPDATE_DRIVE_SIZE = 0x0007C0C8;
        public const uint IOCTL_DISK_GROW_PARTITION = 0x0007C0D0;
        public const uint IOCTL_DISK_SET_DRIVE_LAYOUT_EX = 0x0007C054;
        public const uint IOCTL_STORAGE_QUERY_PROPERTY = 0x002D1400;
        public const uint IOCTL_STORAGE_PREDICT_FAILURE = 0x002D1100;
        public const uint IOCTL_STORAGE_GET_DEVICE_NUMBER = 0x002D1080;
        public const uint IOCTL_VOLUME_GET_VOLUME_DISK_EXTENTS = 0x00560000;

        public const uint FSCTL_LOCK_VOLUME = 0x00090018;
        public const uint FSCTL_DISMOUNT_VOLUME = 0x00090020;
        public const uint FSCTL_EXTEND_VOLUME = 0x000900F0;

        public const int ERROR_INSUFFICIENT_BUFFER = 122;
        public const int ERROR_MORE_DATA = 234;
        public const int ERROR_ACCESS_DENIED = 5;
        public const int ERROR_INVALID_FUNCTION = 1;
        public const int ERROR_NOT_SUPPORTED = 50;
        public const int ERROR_FILE_NOT_FOUND = 2;
        public const int ERROR_PATH_NOT_FOUND = 3;

        public const int StorageDeviceProperty = 0;
        public const int StorageAdapterProperty = 1;
        public const int StorageAccessAlignmentProperty = 6;
        public const int StorageDeviceSeekPenaltyProperty = 7;
        public const int StorageDeviceTrimProperty = 8;

        public const int TokenElevation = 20;
        public const uint TOKEN_QUERY = 0x0008;

        [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
        public static extern SafeFileHandle CreateFileW(
            string lpFileName,
            uint dwDesiredAccess,
            uint dwShareMode,
            IntPtr lpSecurityAttributes,
            uint dwCreationDisposition,
            uint dwFlagsAndAttributes,
            IntPtr hTemplateFile);

        [DllImport("kernel32.dll", SetLastError = true)]
        public static extern bool DeviceIoControl(
            SafeFileHandle hDevice,
            uint dwIoControlCode,
            IntPtr lpInBuffer,
            uint nInBufferSize,
            IntPtr lpOutBuffer,
            uint nOutBufferSize,
            out uint lpBytesReturned,
            IntPtr lpOverlapped);

        [DllImport("kernel32.dll", SetLastError = true)]
        public static extern bool SetFilePointerEx(SafeFileHandle hFile, long liDistanceToMove, IntPtr lpNewFilePointer, uint dwMoveMethod);

        [DllImport("kernel32.dll", SetLastError = true)]
        public static extern bool ReadFile(SafeFileHandle hFile, IntPtr lpBuffer, uint nNumberOfBytesToRead, out uint lpNumberOfBytesRead, IntPtr lpOverlapped);

        [DllImport("kernel32.dll", SetLastError = true)]
        public static extern bool WriteFile(SafeFileHandle hFile, IntPtr lpBuffer, uint nNumberOfBytesToWrite, out uint lpNumberOfBytesWritten, IntPtr lpOverlapped);

        [DllImport("kernel32.dll", SetLastError = true)]
        public static extern bool FlushFileBuffers(SafeFileHandle hFile);

        [DllImport("kernel32.dll", SetLastError = true)]
        public static extern IntPtr VirtualAlloc(IntPtr lpAddress, UIntPtr dwSize, uint flAllocationType, uint flProtect);

        [DllImport("kernel32.dll", SetLastError = true)]
        public static extern bool VirtualFree(IntPtr lpAddress, UIntPtr dwSize, uint dwFreeType);

        [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
        public static extern bool GetVolumeInformationW(
            string lpRootPathName,
            StringBuilder lpVolumeNameBuffer,
            int nVolumeNameSize,
            out uint lpVolumeSerialNumber,
            out uint lpMaximumComponentLength,
            out uint lpFileSystemFlags,
            StringBuilder lpFileSystemNameBuffer,
            int nFileSystemNameSize);

        [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
        public static extern bool GetDiskFreeSpaceExW(
            string lpDirectoryName,
            out ulong lpFreeBytesAvailable,
            out ulong lpTotalNumberOfBytes,
            out ulong lpTotalNumberOfFreeBytes);

        [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
        public static extern bool GetVolumePathNamesForVolumeNameW(
            string lpszVolumeName,
            [Out] char[] lpszVolumePathNames,
            uint cchBufferLength,
            out uint lpcchReturnLength);

        [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
        public static extern bool GetVolumeNameForVolumeMountPointW(
            string lpszVolumeMountPoint,
            StringBuilder lpszVolumeName,
            uint cchBufferLength);

        [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
        public static extern bool SetVolumeMountPointW(string lpszVolumeMountPoint, string lpszVolumeName);

        [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
        public static extern bool DeleteVolumeMountPointW(string lpszVolumeMountPoint);

        [DllImport("kernel32.dll", SetLastError = true)]
        public static extern bool DefineDosDeviceW(uint dwFlags, string lpDeviceName, string lpTargetPath);

        [DllImport("kernel32.dll")]
        public static extern uint GetLogicalDrives();

        public const uint DDD_RAW_TARGET_PATH = 0x00000001;

        [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
        public static extern IntPtr FindFirstVolumeW(StringBuilder lpszVolumeName, uint cchBufferLength);

        [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
        public static extern bool FindNextVolumeW(IntPtr hFindVolume, StringBuilder lpszVolumeName, uint cchBufferLength);

        [DllImport("kernel32.dll", SetLastError = true)]
        public static extern bool FindVolumeClose(IntPtr hFindVolume);

        [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
        public static extern uint GetSystemDirectoryW(StringBuilder lpBuffer, uint uSize);

        [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
        public static extern uint GetWindowsDirectoryW(StringBuilder lpBuffer, uint uSize);

        [DllImport("kernel32.dll", SetLastError = true)]
        public static extern IntPtr GetCurrentProcess();

        [DllImport("advapi32.dll", SetLastError = true)]
        public static extern bool OpenProcessToken(IntPtr processHandle, uint desiredAccess, out IntPtr tokenHandle);

        [DllImport("advapi32.dll", SetLastError = true)]
        public static extern bool GetTokenInformation(IntPtr tokenHandle, int tokenInformationClass, IntPtr tokenInformation, uint tokenInformationLength, out uint returnLength);

        [DllImport("kernel32.dll", SetLastError = true)]
        public static extern bool CloseHandle(IntPtr hObject);

        public static SafeFileHandle OpenPhysicalDrive(int number)
        {
            return CreateFileW(
                @"\\.\PhysicalDrive" + number,
                GENERIC_READ,
                FILE_SHARE_READ | FILE_SHARE_WRITE,
                IntPtr.Zero,
                OPEN_EXISTING,
                0,
                IntPtr.Zero);
        }

        public static SafeFileHandle TryOpenVolume(string volumePath)
        {
            var trimmed = volumePath.TrimEnd('\\');
            var handle = CreateFileW(trimmed, 0, FILE_SHARE_READ | FILE_SHARE_WRITE, IntPtr.Zero, OPEN_EXISTING, 0, IntPtr.Zero);
            if (handle.IsInvalid)
            {
                handle = CreateFileW(volumePath, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, IntPtr.Zero, OPEN_EXISTING, 0, IntPtr.Zero);
            }
            return handle;
        }
    }
}
