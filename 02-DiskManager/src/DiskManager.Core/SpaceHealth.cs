using System;

namespace DiskManager.Core
{
    public static class SpaceHealth
    {
        public const double LowFreePercent = 10.0;
        public const double WarningFreePercent = 20.0;

        public static bool IsLowFreeSpace(long freeBytes, long totalBytes)
        {
            return totalBytes > 0 && freeBytes >= 0 && freeBytes * 100.0 / totalBytes < LowFreePercent;
        }

        public static bool IsWarningFreeSpace(long freeBytes, long totalBytes)
        {
            return totalBytes > 0 && freeBytes >= 0 && freeBytes * 100.0 / totalBytes < WarningFreePercent;
        }

        public static string StatusText(long freeBytes, long totalBytes)
        {
            if (totalBytes <= 0) return "—";
            if (IsLowFreeSpace(freeBytes, totalBytes)) return "空间不足";
            if (IsWarningFreeSpace(freeBytes, totalBytes)) return "空间偏紧";
            return "正常";
        }
    }
}
