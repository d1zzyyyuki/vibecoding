using System;
using System.Diagnostics;
using System.IO;
using DiskManager.Core;

namespace DiskManager.Core.Engine
{
    public static class WriteSpeedProbe
    {
        public static SpeedProbeResult Run(DiskInfo disk, int sampleBytes)
        {
            var result = new SpeedProbeResult { Method = "file-write" };
            if (disk == null) { result.Error = "磁盘不存在"; return result; }

            string root = null;
            PartitionInfo target = null;
            foreach (var partition in disk.Partitions)
            {
                if (string.IsNullOrEmpty(partition.DriveLetter)) continue;
                if (!string.Equals(partition.FileSystem, "NTFS", StringComparison.OrdinalIgnoreCase)) continue;
                if (partition.FreeBytes < 128L * 1024L * 1024L) continue;
                if (target == null || partition.FreeBytes > target.FreeBytes) target = partition;
            }
            if (target == null) { result.Error = "没有可写的 NTFS 卷"; return result; }
            root = target.DriveLetter.TrimEnd(':') + ":\\";

            if (sampleBytes <= 0) sampleBytes = 8 * 1024 * 1024;
            if (sampleBytes > 16 * 1024 * 1024) sampleBytes = 16 * 1024 * 1024;
            sampleBytes = (int)(sampleBytes / (1024 * 1024)) * 1024 * 1024;
            if (sampleBytes < 1024 * 1024) sampleBytes = 1024 * 1024;

            var path = Path.Combine(root, "DiskManager_write_probe.tmp");
            var buffer = new byte[1024 * 1024];
            new Random(20261125).NextBytes(buffer);
            FileStream stream = null;
            try
            {
                stream = new FileStream(path, FileMode.Create, FileAccess.Write, FileShare.None, 1024 * 1024,
                    FileOptions.WriteThrough | FileOptions.SequentialScan);
                var started = Stopwatch.GetTimestamp();
                var written = 0;
                while (written < sampleBytes)
                {
                    var length = Math.Min(buffer.Length, sampleBytes - written);
                    stream.Write(buffer, 0, length);
                    written += length;
                }
                stream.Flush(true);
                var elapsed = Stopwatch.GetTimestamp() - started;
                var seconds = (double)elapsed / Stopwatch.Frequency;
                result.SampleBytes = sampleBytes;
                result.SamplesCompleted = 1;
                result.TotalBytesRead = sampleBytes;
                result.ElapsedMs = (long)Math.Round(seconds * 1000);
                result.ThroughputMBps = Math.Round(sampleBytes / 1024.0 / 1024.0 / Math.Max(0.000001, seconds), 2);
                result.PeakMBps = result.ThroughputMBps;
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
                if (stream != null) stream.Dispose();
                try { if (File.Exists(path)) File.Delete(path); } catch { }
            }
        }
    }
}
