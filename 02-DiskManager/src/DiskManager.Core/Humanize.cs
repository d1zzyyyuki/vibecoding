using System;
using System.Globalization;

namespace DiskManager.Core
{
    public static class Humanize
    {
        private static readonly string[] Units = { "B", "KB", "MB", "GB", "TB", "PB" };

        public static string Bytes(long bytes)
        {
            if (bytes < 0) return "0 B";
            double value = bytes;
            var unit = 0;
            while (value >= 1024 && unit < Units.Length - 1)
            {
                value /= 1024;
                unit++;
            }
            if (unit == 0) return bytes.ToString(CultureInfo.InvariantCulture) + " B";
            return value.ToString("0.0", CultureInfo.InvariantCulture) + " " + Units[unit];
        }

        public static string Speed(double megabytesPerSecond)
        {
            if (megabytesPerSecond >= 1000) return (megabytesPerSecond / 1000.0).ToString("0.00", CultureInfo.InvariantCulture) + " GB/s";
            return megabytesPerSecond.ToString("0", CultureInfo.InvariantCulture) + " MB/s";
        }

        public static string SpeedMBps(double megabytesPerSecond)
        {
            if (megabytesPerSecond <= 0) return "—";
            return megabytesPerSecond.ToString("0", CultureInfo.InvariantCulture) + " MB/s";
        }

        public static string Duration(TimeSpan span)
        {
            if (span.TotalSeconds < 1) return "不到 1 秒";
            if (span.TotalSeconds < 60) return Math.Ceiling(span.TotalSeconds).ToString(CultureInfo.InvariantCulture) + " 秒";
            if (span.TotalMinutes < 60) return ((int)span.TotalMinutes) + " 分 " + span.Seconds.ToString("00", CultureInfo.InvariantCulture) + " 秒";
            return ((int)span.TotalHours) + " 小时 " + span.Minutes.ToString("00", CultureInfo.InvariantCulture) + " 分";
        }

        public static string MoveEstimate(long bytes, double megabytesPerSecond)
        {
            if (megabytesPerSecond <= 0) return "—";
            // Partition relocation reads and writes every byte and pays for seek overhead.
            var effective = megabytesPerSecond * 0.65;
            var seconds = (bytes / 1024.0 / 1024.0) / effective;
            return Duration(TimeSpan.FromSeconds(seconds));
        }
    }
}
