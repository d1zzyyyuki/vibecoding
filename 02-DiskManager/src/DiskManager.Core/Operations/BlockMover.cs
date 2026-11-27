using System;
using System.Runtime.InteropServices;
using DiskManager.Core.Native;
using Microsoft.Win32.SafeHandles;

namespace DiskManager.Core.Operations
{
    public sealed class OperationInterruptedException : Exception
    {
        public OperationInterruptedException(string message) : base(message) { }
    }

    public static class BlockMover
    {
        public const int DefaultChunkBytes = 32 * 1024 * 1024;
        private const long Alignment = 64 * 1024;

        public static void MoveRight(int diskNumber, long sourceStart, long sourceEnd, long delta, long resumeSourceOffset, Action<long> progress, int chunkBytes)
        {
            if (sourceEnd <= sourceStart) throw new ArgumentException("source range is empty");
            if (delta <= 0) throw new ArgumentOutOfRangeException(nameof(delta));
            if (chunkBytes <= 0) chunkBytes = DefaultChunkBytes;
            chunkBytes = (int)AlignDown(chunkBytes, Alignment);
            if (chunkBytes < (int)Alignment) chunkBytes = (int)Alignment;

            using (var handle = OpenDiskForWrite(diskNumber))
            {
                var buffer = VirtualAlloc(chunkBytes);
                try
                {
                    var next = resumeSourceOffset;
                    if (next > sourceEnd) next = sourceEnd;
                    if (next < sourceStart) next = sourceStart;

                    while (next > sourceStart)
                    {
                        var length = (int)Math.Min((long)chunkBytes, next - sourceStart);
                        length = (int)AlignDown(length, Alignment);
                        if (length <= 0) break;
                        var blockStart = next - length;

                        ReadExact(handle, buffer, blockStart, length);
                        WriteExact(handle, buffer, blockStart + delta, length);
                        if (!NativeMethods.FlushFileBuffers(handle))
                        {
                            throw new InvalidOperationException("FlushFileBuffers failed: " + Marshal.GetLastWin32Error());
                        }

                        next = blockStart;
                        if (progress != null) progress(next);
                    }
                }
                finally
                {
                    NativeMethods.VirtualFree(buffer, UIntPtr.Zero, NativeMethods.MEM_RELEASE);
                }
            }
        }

        public static void CopyBack(int diskNumber, long originalStart, long progressSourceOffset, long originalEnd, long delta, Action<long> progress, int chunkBytes)
        {
            if (originalEnd <= originalStart) return;
            if (delta <= 0) throw new ArgumentOutOfRangeException(nameof(delta));
            if (progressSourceOffset < originalStart) progressSourceOffset = originalStart;
            if (progressSourceOffset > originalEnd) progressSourceOffset = originalEnd;
            if (chunkBytes <= 0) chunkBytes = DefaultChunkBytes;
            chunkBytes = (int)AlignDown(chunkBytes, Alignment);
            if (chunkBytes < (int)Alignment) chunkBytes = (int)Alignment;

            using (var handle = OpenDiskForWrite(diskNumber))
            {
                var buffer = VirtualAlloc(chunkBytes);
                try
                {
                    var position = progressSourceOffset;
                    while (position < originalEnd)
                    {
                        var length = (int)Math.Min((long)chunkBytes, originalEnd - position);
                        length = (int)AlignDown(length, Alignment);
                        if (length <= 0) break;

                        ReadExact(handle, buffer, position + delta, length);
                        WriteExact(handle, buffer, position, length);
                        if (!NativeMethods.FlushFileBuffers(handle))
                        {
                            throw new InvalidOperationException("FlushFileBuffers failed: " + Marshal.GetLastWin32Error());
                        }

                        position += length;
                        if (progress != null) progress(position);
                    }
                }
                finally
                {
                    NativeMethods.VirtualFree(buffer, UIntPtr.Zero, NativeMethods.MEM_RELEASE);
                }
            }
        }

        private static SafeFileHandle OpenDiskForWrite(int diskNumber)
        {
            var handle = NativeMethods.CreateFileW(
                @"\\.\PhysicalDrive" + diskNumber,
                NativeMethods.GENERIC_READ | NativeMethods.GENERIC_WRITE,
                NativeMethods.FILE_SHARE_READ | NativeMethods.FILE_SHARE_WRITE,
                IntPtr.Zero,
                NativeMethods.OPEN_EXISTING,
                NativeMethods.FILE_FLAG_NO_BUFFERING | NativeMethods.FILE_FLAG_SEQUENTIAL_SCAN,
                IntPtr.Zero);
            if (handle.IsInvalid) throw new InvalidOperationException("Cannot open physical disk for write: " + Marshal.GetLastWin32Error());
            return handle;
        }

        private static IntPtr VirtualAlloc(int size)
        {
            var buffer = NativeMethods.VirtualAlloc(IntPtr.Zero, (UIntPtr)size, NativeMethods.MEM_COMMIT | NativeMethods.MEM_RESERVE, NativeMethods.PAGE_READWRITE);
            if (buffer == IntPtr.Zero) throw new OutOfMemoryException("VirtualAlloc failed");
            return buffer;
        }

        private static void ReadExact(SafeFileHandle handle, IntPtr buffer, long offset, int length)
        {
            if (!NativeMethods.SetFilePointerEx(handle, offset, IntPtr.Zero, 0)) throw new InvalidOperationException("Seek read failed: " + Marshal.GetLastWin32Error());
            uint read;
            if (!NativeMethods.ReadFile(handle, buffer, (uint)length, out read, IntPtr.Zero) || read != length)
            {
                throw new InvalidOperationException("Raw read failed: " + Marshal.GetLastWin32Error());
            }
        }

        private static void WriteExact(SafeFileHandle handle, IntPtr buffer, long offset, int length)
        {
            if (!NativeMethods.SetFilePointerEx(handle, offset, IntPtr.Zero, 0)) throw new InvalidOperationException("Seek write failed: " + Marshal.GetLastWin32Error());
            uint written;
            if (!NativeMethods.WriteFile(handle, buffer, (uint)length, out written, IntPtr.Zero) || written != length)
            {
                throw new InvalidOperationException("Raw write failed: " + Marshal.GetLastWin32Error());
            }
        }

        private static long AlignDown(long value, long alignment)
        {
            return value - value % alignment;
        }
    }
}
