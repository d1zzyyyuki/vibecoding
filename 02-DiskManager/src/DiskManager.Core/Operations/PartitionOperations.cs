using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Text;
using System.Threading;
using DiskManager.Core.Engine;
using DiskManager.Core.Native;

namespace DiskManager.Core.Operations
{
    public sealed class PartitionOperationResult
    {
        public bool Success;
        public int ExitCode;
        public string Message;
        public string LogPath;
        public string Output;
    }

    public static class PartitionOperations
    {
        private const long Megabyte = 1024L * 1024L;

        public static PartitionOperationResult Create(DiskInfo disk, long sizeBytes, string fileSystem, string label, string driveLetter, bool allowRealDisk, string logPath)
        {
            var result = StartResult();
            if (!Guard(disk, allowRealDisk, result)) return result;
            if (disk.PartitionStyle != "GPT") return Fail(result, "只支持 GPT 磁盘");
            var sizeMb = BytesToMegabytes(sizeBytes);
            if (sizeMb <= 0) return Fail(result, "分区大小必须大于 0");

            var letter = string.IsNullOrEmpty(driveLetter) ? PickFreeLetter(disk, result) : driveLetter.TrimEnd(':').ToUpperInvariant();
            if (letter == null) return result;
            if (!IsLetterFree(letter, result)) return result;

            var commands = new List<string>
            {
                "select disk " + disk.Number,
                "create partition primary size=" + sizeMb,
                FormatCommand(fileSystem, label),
                "assign letter=" + letter
            };
            if (!Run(commands, logPath, result, out _)) return result;

            var refreshed = Rescan(disk.Number);
            var partition = FindByLetter(refreshed, letter);
            if (partition == null) return Fail(result, "diskpart 返回成功，但新分区没有出现：" + letter + ":");
            result.Success = true;
            result.ExitCode = 0;
            result.Message = "已创建 " + letter + ":";
            AppendLog(result, "verified: created " + letter + ": partition=" + partition.PartitionNumber);
            return result;
        }

        public static PartitionOperationResult Delete(DiskInfo disk, PartitionInfo partition, bool allowRealDisk, string logPath)
        {
            var result = StartResult();
            if (!Guard(disk, allowRealDisk, result)) return result;
            if (!GuardPartition(disk, partition, result)) return result;
            var commands = new List<string>
            {
                "select disk " + disk.Number,
                "select partition " + partition.PartitionNumber,
                "delete partition override"
            };
            if (!Run(commands, logPath, result, out _)) return result;
            var refreshed = Rescan(disk.Number);
            if (refreshed == null || FindByNumber(refreshed, partition.PartitionNumber) != null)
                return Fail(result, "diskpart 返回成功，但分区仍然存在");
            result.Success = true;
            result.ExitCode = 0;
            result.Message = "已删除分区 " + partition.PartitionNumber;
            AppendLog(result, "verified: partition " + partition.PartitionNumber + " removed");
            return result;
        }

        public static PartitionOperationResult Format(DiskInfo disk, PartitionInfo partition, string fileSystem, string label, bool allowRealDisk, string logPath)
        {
            var result = StartResult();
            if (!Guard(disk, allowRealDisk, result)) return result;
            if (!GuardPartition(disk, partition, result)) return result;
            if (string.IsNullOrEmpty(partition.DriveLetter)) return Fail(result, "分区没有盘符，不能格式化");
            var fs = NormalizeFileSystem(fileSystem);
            if (fs == null) return Fail(result, "只支持 NTFS 或 exFAT");
            var commands = new List<string>
            {
                "select volume " + partition.DriveLetter.TrimEnd(':'),
                FormatCommand(fs, label)
            };
            if (!Run(commands, logPath, result, out _)) return result;
            var refreshed = Rescan(disk.Number);
            var refreshedPartition = refreshed == null ? null : FindByNumber(refreshed, partition.PartitionNumber);
            if (refreshedPartition == null || !string.Equals(refreshedPartition.FileSystem, fs, StringComparison.OrdinalIgnoreCase))
                return Fail(result, "diskpart 返回成功，但文件系统没有变成 " + fs);
            result.Success = true;
            result.ExitCode = 0;
            result.Message = "已格式化 " + partition.DriveLetter + ": 为 " + fs;
            AppendLog(result, "verified: filesystem=" + refreshedPartition.FileSystem);
            return result;
        }

        public static PartitionOperationResult Split(DiskInfo disk, PartitionInfo partition, long newSizeBytes, string fileSystem, string label, string driveLetter, bool allowRealDisk, string logPath)
        {
            var result = StartResult();
            if (!Guard(disk, allowRealDisk, result)) return result;
            if (!GuardPartition(disk, partition, result)) return result;
            if (string.IsNullOrEmpty(partition.DriveLetter)) return Fail(result, "分区没有盘符，不能拆分");
            if (!string.Equals(partition.FileSystem, "NTFS", StringComparison.OrdinalIgnoreCase)) return Fail(result, "拆分只支持 NTFS");
            var sizeMb = BytesToMegabytes(newSizeBytes);
            if (sizeMb < 64) return Fail(result, "新分区至少 64 MB");
            var margin = 256L * Megabyte;
            if (partition.FreeBytes < newSizeBytes + margin) return Fail(result, "分区空闲空间不足，至少需要新分区大小加 256 MB");

            var letter = string.IsNullOrEmpty(driveLetter) ? PickFreeLetter(disk, result) : driveLetter.TrimEnd(':').ToUpperInvariant();
            if (letter == null) return result;
            if (!IsLetterFree(letter, result)) return result;

            var fs = NormalizeFileSystem(fileSystem);
            if (fs == null) return Fail(result, "只支持 NTFS 或 exFAT");

            var commands = new List<string>
            {
                "select volume " + partition.DriveLetter.TrimEnd(':'),
                "shrink desired=" + sizeMb,
                "create partition primary size=" + sizeMb,
                FormatCommand(fs, label),
                "assign letter=" + letter
            };
            if (!Run(commands, logPath, result, out _)) return result;

            var refreshed = Rescan(disk.Number);
            var refreshedSource = refreshed == null ? null : FindByNumber(refreshed, partition.PartitionNumber);
            var newPartition = FindByLetter(refreshed, letter);
            if (refreshedSource == null || refreshedSource.SizeBytes >= partition.SizeBytes || newPartition == null)
                return Fail(result, "diskpart 返回成功，但拆分后的分区状态不符合预期");
            result.Success = true;
            result.ExitCode = 0;
            result.Message = "已拆分出 " + letter + ":";
            AppendLog(result, "verified: sourceSize=" + refreshedSource.SizeBytes + " new=" + letter + ":");
            return result;
        }

        private static bool Guard(DiskInfo disk, bool allowRealDisk, PartitionOperationResult result)
        {
            if (disk == null) { Fail(result, "磁盘不存在"); return false; }
            if (!allowRealDisk && !string.Equals(disk.BusType, "FileBackedVirtual", StringComparison.OrdinalIgnoreCase))
            {
                Fail(result, "当前安全模式不允许写入真实磁盘；仅虚拟测试盘可执行");
                return false;
            }
            if (disk.IsSystemDisk || disk.IsBootDisk)
            {
                Fail(result, "拒绝对系统盘执行分区操作");
                return false;
            }
            return true;
        }

        private static bool GuardPartition(DiskInfo disk, PartitionInfo partition, PartitionOperationResult result)
        {
            if (partition == null) { Fail(result, "分区不存在"); return false; }
            if (!partition.IsBasicData || partition.IsSystem || partition.IsBoot || partition.IsEfi || partition.IsMsr || partition.IsRecovery)
            {
                Fail(result, "只允许操作普通数据分区");
                return false;
            }
            return true;
        }

        private static PartitionOperationResult StartResult()
        {
            return new PartitionOperationResult { ExitCode = 2 };
        }

        private static PartitionOperationResult Fail(PartitionOperationResult result, string message)
        {
            result.Success = false;
            result.ExitCode = 2;
            result.Message = message;
            return result;
        }

        private static string FormatCommand(string fileSystem, string label)
        {
            var fs = NormalizeFileSystem(fileSystem);
            var clean = CleanLabel(label);
            return "format fs=" + fs + " quick" + (clean.Length == 0 ? "" : " label=" + clean);
        }

        private static string NormalizeFileSystem(string fileSystem)
        {
            var fs = (fileSystem ?? "NTFS").Trim().ToLowerInvariant();
            return fs == "ntfs" || fs == "exfat" ? fs : null;
        }

        private static string CleanLabel(string label)
        {
            if (string.IsNullOrEmpty(label)) return "";
            var builder = new StringBuilder();
            foreach (var ch in label.Trim())
            {
                if (char.IsLetterOrDigit(ch) || ch == '-' || ch == '_') builder.Append(ch);
                if (builder.Length >= 24) break;
            }
            return builder.Length == 0 ? "DATA" : builder.ToString();
        }

        private static long BytesToMegabytes(long bytes)
        {
            if (bytes <= 0) return 0;
            return (bytes + Megabyte - 1) / Megabyte;
        }

        private static string PickFreeLetter(DiskInfo disk, PartitionOperationResult result)
        {
            var used = new HashSet<char>();
            var mask = NativeMethods.GetLogicalDrives();
            for (var i = 0; i < 26; i++) if ((mask & (1u << i)) != 0) used.Add((char)('A' + i));
            for (var ch = 'Z'; ch >= 'D'; ch--)
            {
                if (ch == 'C' || used.Contains(ch)) continue;
                return ch.ToString(CultureInfo.InvariantCulture);
            }
            Fail(result, "没有空闲盘符");
            return null;
        }

        private static bool IsLetterFree(string letter, PartitionOperationResult result)
        {
            if (string.IsNullOrEmpty(letter) || letter.Length != 1) { Fail(result, "盘符无效"); return false; }
            var ch = char.ToUpperInvariant(letter[0]);
            if (ch < 'D' || ch > 'Z' || ch == 'C') { Fail(result, "不能使用该盘符"); return false; }
            var mask = NativeMethods.GetLogicalDrives();
            if ((mask & (1u << (ch - 'A'))) != 0) { Fail(result, "盘符已被占用：" + ch + ":"); return false; }
            return true;
        }

        private static bool Run(List<string> commands, string logPath, PartitionOperationResult result, out string output)
        {
            output = null;
            var path = string.IsNullOrEmpty(logPath) ? DefaultLogPath("partition") : logPath;
            result.LogPath = path;
            var directory = Path.GetDirectoryName(Path.GetFullPath(path));
            if (!string.IsNullOrEmpty(directory)) Directory.CreateDirectory(directory);
            var scriptPath = path + ".diskpart.txt";
            try
            {
                File.WriteAllText(scriptPath, string.Join("\r\n", commands) + "\r\n", Encoding.ASCII);
                var info = new ProcessStartInfo
                {
                    FileName = Path.Combine(Environment.SystemDirectory, "diskpart.exe"),
                    Arguments = "/s \"" + scriptPath + "\"",
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true
                };
                using (var process = Process.Start(info))
                {
                    if (process == null) { Fail(result, "无法启动 diskpart"); return false; }
                    var stdout = process.StandardOutput.ReadToEnd();
                    var stderr = process.StandardError.ReadToEnd();
                    if (!process.WaitForExit(10 * 60 * 1000))
                    {
                        try { process.Kill(); } catch { }
                        Fail(result, "diskpart 超时");
                        return false;
                    }
                    output = stdout + stderr;
                    File.WriteAllText(path, "commands:\r\n" + string.Join("\r\n", commands) + "\r\n\r\n" + output, Encoding.UTF8);
                    if (process.ExitCode != 0)
                    {
                        Fail(result, "diskpart 失败，退出码 " + process.ExitCode);
                        return false;
                    }
                    return true;
                }
            }
            catch (Exception ex)
            {
                Fail(result, "diskpart 异常：" + ex.Message);
                return false;
            }
            finally
            {
                try { if (File.Exists(scriptPath)) File.Delete(scriptPath); } catch { }
            }
        }

        private static string DefaultLogPath(string operation)
        {
            var root = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "DiskManager", "operations");
            return Path.Combine(root, operation + "-" + DateTime.Now.ToString("yyyyMMdd-HHmmss", CultureInfo.InvariantCulture) + ".log");
        }

        private static DiskInfo Rescan(int diskNumber)
        {
            var scan = DiskScanner.Scan(new ScanOptions { ProbeSpeed = false });
            foreach (var disk in scan.Disks) if (disk.Number == diskNumber) return disk;
            return null;
        }

        private static PartitionInfo FindByNumber(DiskInfo disk, int partitionNumber)
        {
            if (disk == null) return null;
            foreach (var partition in disk.Partitions) if (partition.PartitionNumber == partitionNumber) return partition;
            return null;
        }

        private static PartitionInfo FindByLetter(DiskInfo disk, string letter)
        {
            if (disk == null || string.IsNullOrEmpty(letter)) return null;
            foreach (var partition in disk.Partitions)
            {
                if (string.Equals(partition.DriveLetter, letter.TrimEnd(':'), StringComparison.OrdinalIgnoreCase)) return partition;
            }
            return null;
        }

        private static void AppendLog(PartitionOperationResult result, string text)
        {
            if (string.IsNullOrEmpty(result.LogPath)) return;
            try { File.AppendAllText(result.LogPath, "\r\n" + text + "\r\n", Encoding.UTF8); } catch { }
        }
    }
}
