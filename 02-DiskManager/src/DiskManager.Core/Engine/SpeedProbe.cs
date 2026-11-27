using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.InteropServices;
using DiskManager.Core.Native;
using Microsoft.Win32.SafeHandles;

namespace DiskManager.Core.Engine
{
    public static class SpeedProbe
    {
        public static SpeedProbeResult Run(int diskNumber, long diskSizeBytes, int sampleBytes, int maxSamples)
        {
            var result = new SpeedProbeResult { SampleBytes = sampleBytes };
            if (diskSizeBytes <= 0)
            {
                result.Error = "磁盘容量无效";
                return result;
            }

            if (sampleBytes <= 0) sampleBytes = 16 * 1024 * 1024;
            if (sampleBytes > 32 * 1024 * 1024) sampleBytes = 32 * 1024 * 1024;
            sampleBytes = (int)AlignDown(sampleBytes, 1024 * 1024);
            if (sampleBytes <= 0) sampleBytes = 1024 * 1024;
            if (maxSamples <= 0) maxSamples = 3;

            if (diskSizeBytes < sampleBytes * 5L)
            {
                sampleBytes = (int)Math.Max(256 * 1024, AlignDown(diskSizeBytes / 5, 64 * 1024));
                result.SampleBytes = sampleBytes;
            }

            SafeFileHandle handle = null;
            var buffer = IntPtr.Zero;
            var totalRead = 0L;
            var totalTicks = 0L;

            try
            {
                handle = NativeMethods.CreateFileW(
                    @"\\.\PhysicalDrive" + diskNumber,
                    NativeMethods.GENERIC_READ,
                    NativeMethods.FILE_SHARE_READ | NativeMethods.FILE_SHARE_WRITE,
                    IntPtr.Zero,
                    NativeMethods.OPEN_EXISTING,
                    NativeMethods.FILE_FLAG_NO_BUFFERING | NativeMethods.FILE_FLAG_SEQUENTIAL_SCAN,
                    IntPtr.Zero);

                if (handle.IsInvalid)
                {
                    result.Error = "打开物理磁盘失败，Win32 错误 " + Marshal.GetLastWin32Error();
                    return result;
                }

                buffer = NativeMethods.VirtualAlloc(IntPtr.Zero, (UIntPtr)sampleBytes, NativeMethods.MEM_COMMIT | NativeMethods.MEM_RESERVE, NativeMethods.PAGE_READWRITE);
                if (buffer == IntPtr.Zero)
                {
                    result.Error = "分配测速缓冲区失败";
                    return result;
                }

                var fractions = new[] { 0.20, 0.50, 0.80 };
                for (var i = 0; i < maxSamples && i < fractions.Length; i++)
                {
                    var offset = AlignDown((long)(diskSizeBytes * fractions[i]), 1024 * 1024);
                    if (offset + sampleBytes > diskSizeBytes) offset = AlignDown(diskSizeBytes - sampleBytes - 1024 * 1024, 1024 * 1024);
                    if (offset < 0) offset = 0;

                    if (result.Samples.Count > 0 && Math.Abs(result.Samples[result.Samples.Count - 1].OffsetBytes - offset) < 1024 * 1024) continue;

                    if (!NativeMethods.SetFilePointerEx(handle, offset, IntPtr.Zero, 0))
                    {
                        if (result.Samples.Count == 0) result.Error = "定位读取位置失败，Win32 错误 " + Marshal.GetLastWin32Error();
                        break;
                    }

                    var readTicks = Stopwatch.GetTimestamp();
                    uint read;
                    var ok = NativeMethods.ReadFile(handle, buffer, (uint)sampleBytes, out read, IntPtr.Zero);
                    var elapsedTicks = Stopwatch.GetTimestamp() - readTicks;
                    if (!ok || read == 0)
                    {
                        if (result.Samples.Count == 0) result.Error = "原始读取失败，Win32 错误 " + Marshal.GetLastWin32Error();
                        break;
                    }

                    var timeSec = (double)elapsedTicks / Stopwatch.Frequency;
                    var mbps = read / 1024.0 / 1024.0 / Math.Max(0.000001, timeSec);
                    var elapsedMs = (long)Math.Round(timeSec * 1000);
                    result.Samples.Add(new SpeedSample
                    {
                        OffsetBytes = offset,
                        BytesRead = (int)read,
                        ElapsedMs = elapsedMs,
                        ThroughputMBps = Round2(mbps)
                    });
                    totalRead += read;
                    totalTicks += elapsedTicks;

                    if (result.Samples.Count >= 2 && totalTicks * 1000L / Stopwatch.Frequency > 140) break;
                }

                if (result.Samples.Count == 0)
                {
                    if (string.IsNullOrEmpty(result.Error)) result.Error = "没有完成任何读取";
                    return result;
                }

                var speeds = new List<double>();
                foreach (var sample in result.Samples) speeds.Add(sample.ThroughputMBps);
                speeds.Sort();
                var median = speeds.Count % 2 == 1 ? speeds[speeds.Count / 2] : speeds[(speeds.Count - 1) / 2];

                result.SamplesCompleted = result.Samples.Count;
                result.TotalBytesRead = totalRead;
                result.ElapsedMs = (long)Math.Round((double)totalTicks / Stopwatch.Frequency * 1000);
                result.ThroughputMBps = Round2(median);
                var peak = 0.0;
                foreach (var sample in result.Samples) if (sample.ThroughputMBps > peak) peak = sample.ThroughputMBps;
                result.PeakMBps = Round2(peak);
                result.Success = true;
                return result;
            }
            catch (Exception ex)
            {
                result.Error = ex.Message;
                return result;
            }
            finally
            {
                if (buffer != IntPtr.Zero) NativeMethods.VirtualFree(buffer, UIntPtr.Zero, NativeMethods.MEM_RELEASE);
                if (handle != null) handle.Dispose();
            }
        }

        private static long AlignDown(long value, long alignment)
        {
            return value - (value % alignment);
        }

        private static double Round2(double value)
        {
            return Math.Round(value, 2);
        }
    }
}
