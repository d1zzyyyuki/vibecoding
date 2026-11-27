using System;
using System.Runtime.InteropServices;
using System.Text;
using Microsoft.Win32.SafeHandles;

namespace DiskManager.Core.Native
{
    internal static class Io
    {
        public static byte[] Query(SafeFileHandle handle, uint code, byte[] input, int initialOutputSize, out int error)
        {
            error = 0;
            var outputSize = initialOutputSize;
            for (var attempt = 0; attempt < 3; attempt++)
            {
                var inPtr = IntPtr.Zero;
                var outPtr = IntPtr.Zero;
                try
                {
                    if (input != null && input.Length > 0)
                    {
                        inPtr = Marshal.AllocHGlobal(input.Length);
                        Marshal.Copy(input, 0, inPtr, input.Length);
                    }

                    if (outputSize > 0) outPtr = Marshal.AllocHGlobal(outputSize);
                    uint returned;
                    var ok = NativeMethods.DeviceIoControl(
                        handle,
                        code,
                        inPtr,
                        (uint)(input == null ? 0 : input.Length),
                        outPtr,
                        (uint)Math.Max(0, outputSize),
                        out returned,
                        IntPtr.Zero);

                    if (ok)
                    {
                        var length = (int)Math.Min((uint)Math.Max(0, outputSize), returned);
                        var buffer = new byte[length];
                        if (length > 0) Marshal.Copy(outPtr, buffer, 0, length);
                        return buffer;
                    }

                    error = Marshal.GetLastWin32Error();
                    if (error == NativeMethods.ERROR_INSUFFICIENT_BUFFER && returned > (uint)outputSize)
                    {
                        outputSize = (int)returned;
                        continue;
                    }
                    return null;
                }
                finally
                {
                    if (inPtr != IntPtr.Zero) Marshal.FreeHGlobal(inPtr);
                    if (outPtr != IntPtr.Zero) Marshal.FreeHGlobal(outPtr);
                }
            }
            return null;
        }

        public static bool Control(SafeFileHandle handle, uint code, byte[] input, int inputOffset, int inputLength, out int error)
        {
            error = 0;
            var inPtr = IntPtr.Zero;
            try
            {
                if (input != null && inputLength > 0)
                {
                    inPtr = Marshal.AllocHGlobal(inputLength);
                    Marshal.Copy(input, inputOffset, inPtr, inputLength);
                }
                uint returned;
                var ok = NativeMethods.DeviceIoControl(handle, code, inPtr, (uint)inputLength, IntPtr.Zero, 0, out returned, IntPtr.Zero);
                if (!ok) error = Marshal.GetLastWin32Error();
                return ok;
            }
            finally
            {
                if (inPtr != IntPtr.Zero) Marshal.FreeHGlobal(inPtr);
            }
        }

        public static bool Control(SafeFileHandle handle, uint code, byte[] input, out int error)
        {
            return Control(handle, code, input, 0, input == null ? 0 : input.Length, out error);
        }

        public static byte[] StorageQuery(ushort propertyId)
        {
            var input = new byte[12];
            BitConverter.GetBytes((int)propertyId).CopyTo(input, 0);
            BitConverter.GetBytes(0).CopyTo(input, 4);
            return input;
        }

        public static int ReadInt32(byte[] buffer, int offset)
        {
            return BitConverter.ToInt32(buffer, offset);
        }

        public static uint ReadUInt32(byte[] buffer, int offset)
        {
            return BitConverter.ToUInt32(buffer, offset);
        }

        public static long ReadInt64(byte[] buffer, int offset)
        {
            return BitConverter.ToInt64(buffer, offset);
        }

        public static ulong ReadUInt64(byte[] buffer, int offset)
        {
            return BitConverter.ToUInt64(buffer, offset);
        }

        public static string ReadGuid(byte[] buffer, int offset)
        {
            var bytes = new byte[16];
            Buffer.BlockCopy(buffer, offset, bytes, 0, 16);
            return new Guid(bytes).ToString("D").ToUpperInvariant();
        }

        public static string ReadAscii(byte[] buffer, int offset)
        {
            if (offset <= 0 || offset >= buffer.Length) return string.Empty;
            var end = offset;
            while (end < buffer.Length && buffer[end] != 0) end++;
            return Encoding.ASCII.GetString(buffer, offset, end - offset).Trim();
        }

        public static string ReadUnicode(byte[] buffer, int offset, int chars)
        {
            if (offset < 0 || offset + chars * 2 > buffer.Length) return string.Empty;
            return Encoding.Unicode.GetString(buffer, offset, chars * 2).TrimEnd('\0', ' ').Trim();
        }
    }
}
