using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading.Tasks;
using DiskManager.Core.Native;
using Microsoft.Win32.SafeHandles;

namespace DiskManager.Core.Engine
{
    public static class DiskScanner
    {
        public static ScanResult Scan(ScanOptions options)
        {
            if (options == null) options = new ScanOptions();
            var result = new ScanResult
            {
                StartedAtUtc = DateTime.UtcNow,
                IsElevated = Elevation.IsElevated(),
                MachineName = Environment.MachineName,
                OsDescription = DescribeOs(),
                OsArchitecture = RuntimeInformation.OSArchitecture.ToString()
            };

            var stopwatch = Stopwatch.StartNew();
            string systemVolumeGuid;
            var volumes = VolumeScanner.Scan(out systemVolumeGuid, result.Warnings);
            result.SystemVolumeGuid = systemVolumeGuid;
            var windowsVolumeGuid = VolumeScanner.GetWindowsVolumeGuid();
            var systemDrive = GetSystemDriveLetter();

            var volumeMap = new Dictionary<string, VolumeRecord>(StringComparer.OrdinalIgnoreCase);
            foreach (var volume in volumes)
            {
                if (volume.DiskNumber < 0) continue;
                var key = VolumeKey(volume.DiskNumber, volume.StartingOffset);
                if (!volumeMap.ContainsKey(key)) volumeMap.Add(key, volume);
            }

            var pcieLinks = PcieLinkProbe.MapAll();

            var foundAny = false;
            for (var number = 0; number < options.MaxDisks; number++)
            {
                using (var handle = NativeMethods.OpenPhysicalDrive(number))
                {
                    if (handle.IsInvalid) continue;
                    foundAny = true;

                    var disk = ReadDisk(handle, number, options, result);
                    if (disk == null) continue;

                    string link;
                    if (disk.BusType == "NVMe" && pcieLinks.TryGetValue(number, out link)) disk.PcieLink = link;

                    foreach (var partition in disk.Partitions)
                    {
                        VolumeRecord volume;
                        if (!volumeMap.TryGetValue(VolumeKey(disk.Number, partition.OffsetBytes), out volume)) continue;

                        partition.HasVolume = true;
                        partition.DriveLetter = volume.DriveLetter;
                        partition.Label = volume.Label;
                        partition.FileSystem = volume.FileSystem;
                        partition.VolumeGuid = volume.GuidPath;
                        partition.VolumeTotalBytes = volume.TotalBytes > 0 ? volume.TotalBytes : partition.SizeBytes;
                        partition.FreeBytes = volume.FreeBytes;

                        var normalized = VolumeScanner.Normalize(volume.GuidPath);
                        if (!string.IsNullOrEmpty(systemVolumeGuid) && normalized == VolumeScanner.Normalize(systemVolumeGuid))
                        {
                            partition.IsSystem = true;
                            disk.IsSystemDisk = true;
                        }
                        if (!string.IsNullOrEmpty(systemDrive) && volume.DriveLetter == systemDrive)
                        {
                            partition.IsSystem = true;
                            disk.IsSystemDisk = true;
                        }
                        if (!string.IsNullOrEmpty(windowsVolumeGuid) && normalized == VolumeScanner.Normalize(windowsVolumeGuid))
                        {
                            partition.IsBoot = true;
                            disk.IsBootDisk = true;
                        }
                    }

                    result.Disks.Add(disk);
                }
            }

            if (!foundAny)
            {
                result.Errors.Add("没有找到可访问的物理磁盘。请以管理员身份运行，或检查磁盘是否在线。");
            }

            if (options.ProbeSpeed && result.Disks.Count > 0)
            {
                ProbeAll(result.Disks, options, result);
            }

            result.DurationMs = stopwatch.ElapsedMilliseconds;
            return result;
        }

        private static DiskInfo ReadDisk(SafeFileHandle handle, int number, ScanOptions options, ScanResult result)
        {
            long size;
            if (!TryReadDiskSize(handle, out size) || size <= 0) return null;

            var logicalSectorSize = 512;
            var physicalSectorSize = 0;
            var geometry = Io.Query(handle, NativeMethods.IOCTL_DISK_GET_DRIVE_GEOMETRY_EX, null, 64, out _);
            if (geometry != null && geometry.Length >= 32)
            {
                logicalSectorSize = Io.ReadInt32(geometry, 20);
                if (size <= 0) size = Io.ReadInt64(geometry, 24);
            }

            var alignment = Io.Query(handle, NativeMethods.IOCTL_STORAGE_QUERY_PROPERTY, Io.StorageQuery(NativeMethods.StorageAccessAlignmentProperty), 64, out _);
            if (alignment != null && alignment.Length >= 24) physicalSectorSize = Io.ReadInt32(alignment, 20);

            var descriptor = Io.Query(handle, NativeMethods.IOCTL_STORAGE_QUERY_PROPERTY, Io.StorageQuery(NativeMethods.StorageDeviceProperty), 4096, out _);
            var vendor = string.Empty;
            var product = string.Empty;
            var serial = string.Empty;
            var busNumber = 0;
            var removable = false;
            if (descriptor != null && descriptor.Length >= 36)
            {
                vendor = Io.ReadAscii(descriptor, Io.ReadInt32(descriptor, 12));
                product = Io.ReadAscii(descriptor, Io.ReadInt32(descriptor, 16));
                serial = Io.ReadAscii(descriptor, Io.ReadInt32(descriptor, 24));
                busNumber = Io.ReadInt32(descriptor, 28);
                removable = descriptor[10] != 0;
            }

            bool? seekPenalty = null;
            var seek = Io.Query(handle, NativeMethods.IOCTL_STORAGE_QUERY_PROPERTY, Io.StorageQuery(NativeMethods.StorageDeviceSeekPenaltyProperty), 16, out _);
            if (seek != null && seek.Length >= 9) seekPenalty = seek[8] != 0;

            string health = null;
            if (options.ProbeHealth)
            {
                var predict = Io.Query(handle, NativeMethods.IOCTL_STORAGE_PREDICT_FAILURE, null, 520, out _);
                if (predict != null && predict.Length >= 4)
                {
                    health = Io.ReadUInt32(predict, 0) == 0 ? "正常" : "预警";
                }
            }

            var disk = new DiskInfo
            {
                Number = number,
                Model = BuildModel(vendor, product),
                Serial = serial,
                BusType = BusName(busNumber),
                MediaKind = MediaName(busNumber, seekPenalty),
                SizeBytes = size,
                LogicalSectorSize = logicalSectorSize,
                PhysicalSectorSize = physicalSectorSize > 0 ? physicalSectorSize : logicalSectorSize,
                IsRemovable = removable,
                Health = string.IsNullOrEmpty(health) ? "未知" : health,
                OperationalStatus = "在线"
            };

            var layout = Io.Query(handle, NativeMethods.IOCTL_DISK_GET_DRIVE_LAYOUT_EX, null, 48 + 128 * 144 + 16, out var layoutError);
            if (layout != null && layout.Length >= 48)
            {
                ParseLayout(layout, disk, result);
            }
            else
            {
                disk.PartitionStyle = layoutError == 0 ? "RAW" : "未知";
            }

            disk.Partitions.Sort((a, b) => a.OffsetBytes.CompareTo(b.OffsetBytes));
            return disk;
        }

        private static void ParseLayout(byte[] layout, DiskInfo disk, ScanResult result)
        {
            var style = Io.ReadInt32(layout, 0);
            var count = Io.ReadInt32(layout, 4);
            if (count < 0 || count > 128) count = 0;

            disk.PartitionStyle = style == 1 ? "GPT" : style == 0 ? "MBR" : "RAW";

            for (var index = 0; index < count; index++)
            {
                var offset = 48 + index * 144;
                if (offset + 144 > layout.Length) break;

                var partitionStyle = Io.ReadInt32(layout, offset);
                var partition = new PartitionInfo
                {
                    DiskNumber = disk.Number,
                    PartitionNumber = Io.ReadInt32(layout, offset + 24),
                    OffsetBytes = Io.ReadInt64(layout, offset + 8),
                    SizeBytes = Io.ReadInt64(layout, offset + 16),
                    PartitionStyle = partitionStyle == 1 ? "GPT" : "MBR"
                };

                if (partition.SizeBytes <= 0) continue;

                if (partitionStyle == 1)
                {
                    partition.GptTypeId = Io.ReadGuid(layout, offset + 32);
                    partition.GptAttributes = Io.ReadUInt64(layout, offset + 64);
                    partition.GptName = Io.ReadUnicode(layout, offset + 72, 36);
                    partition.TypeName = PartitionTypes.NameOf(partition.GptTypeId) ?? "其他分区";
                    partition.IsEfi = string.Equals(partition.GptTypeId, PartitionTypes.EfiSystem, StringComparison.OrdinalIgnoreCase);
                    partition.IsMsr = string.Equals(partition.GptTypeId, PartitionTypes.MicrosoftReserved, StringComparison.OrdinalIgnoreCase);
                    partition.IsRecovery = string.Equals(partition.GptTypeId, PartitionTypes.WindowsRecovery, StringComparison.OrdinalIgnoreCase);
                    partition.IsBasicData = string.Equals(partition.GptTypeId, PartitionTypes.BasicData, StringComparison.OrdinalIgnoreCase);
                    partition.IsHidden = partition.IsEfi || partition.IsMsr || partition.IsRecovery ||
                        (partition.GptAttributes & (PartitionTypes.AttributeHidden | PartitionTypes.AttributeNoDriveLetter)) != 0;
                }
                else if (partitionStyle == 0)
                {
                    var mbrType = layout[offset + 32];
                    partition.TypeName = PartitionTypes.MbrName(mbrType);
                    partition.GptName = string.Empty;
                    partition.IsEfi = mbrType == 0xEF;
                    partition.IsRecovery = mbrType == 0x27;
                    partition.IsBasicData = mbrType == 0x07 || mbrType == 0x0B || mbrType == 0x0C || mbrType == 0x0E;
                    partition.IsHidden = partition.IsEfi || partition.IsRecovery;
                }
                else
                {
                    partition.TypeName = "未知分区";
                }

                disk.Partitions.Add(partition);
            }
        }

        private static void ProbeAll(List<DiskInfo> disks, ScanOptions options, ScanResult result)
        {
            var tasks = new Task[disks.Count];
            for (var i = 0; i < disks.Count; i++)
            {
                var disk = disks[i];
                tasks[i] = Task.Run(() =>
                {
                    var probe = SpeedProbe.Run(disk.Number, disk.SizeBytes, options.SpeedSampleBytes, options.SpeedSampleCount);
                    disk.Speed = probe;
                    if (options.ProbeWrite) disk.WriteSpeed = WriteSpeedProbe.Run(disk, options.WriteSampleBytes);
                    if (!probe.Success)
                    {
                        lock (result.Errors)
                        {
                            result.Errors.Add("磁盘 " + disk.Number + " 测速失败: " + probe.Error);
                        }
                    }
                });
            }
            try
            {
                Task.WaitAll(tasks);
            }
            catch (AggregateException ex)
            {
                lock (result.Errors) result.Errors.Add("测速任务异常: " + ex.GetBaseException().Message);
            }
        }

        private static bool TryReadDiskSize(SafeFileHandle handle, out long size)
        {
            size = 0;
            var length = Io.Query(handle, NativeMethods.IOCTL_DISK_GET_LENGTH_INFO, null, 8, out _);
            if (length != null && length.Length >= 8)
            {
                size = Io.ReadInt64(length, 0);
                return size > 0;
            }
            var geometry = Io.Query(handle, NativeMethods.IOCTL_DISK_GET_DRIVE_GEOMETRY_EX, null, 64, out _);
            if (geometry != null && geometry.Length >= 32)
            {
                size = Io.ReadInt64(geometry, 24);
                return size > 0;
            }
            return false;
        }

        private static string VolumeKey(int diskNumber, long offset)
        {
            return diskNumber.ToString() + ":" + offset.ToString();
        }

        private static string GetSystemDriveLetter()
        {
            var systemDir = new StringBuilder(261);
            NativeMethods.GetSystemDirectoryW(systemDir, 261);
            var root = Path.GetPathRoot(systemDir.ToString());
            return string.IsNullOrEmpty(root) || root.Length < 2 ? null : char.ToUpperInvariant(root[0]).ToString();
        }

        private static string DescribeOs()
        {
            var version = Environment.OSVersion.Version;
            var name = version.Build >= 22000 ? "Windows 11" : "Windows 10";
            return name + " · build " + version.Build;
        }

        private static string BuildModel(string vendor, string product)
        {
            vendor = (vendor ?? string.Empty).Trim();
            product = (product ?? string.Empty).Trim();
            if (string.IsNullOrEmpty(product)) return vendor;
            if (string.IsNullOrEmpty(vendor)) return product;
            if (product.StartsWith(vendor, StringComparison.OrdinalIgnoreCase)) return product;
            if (vendor.Equals("NVMe", StringComparison.OrdinalIgnoreCase)) return product;
            return vendor + " " + product;
        }

        public static string BusName(int busType)
        {
            switch (busType)
            {
                case 1: return "SCSI";
                case 2: return "ATAPI";
                case 3: return "ATA";
                case 4: return "1394";
                case 5: return "SSA";
                case 6: return "Fibre";
                case 7: return "USB";
                case 8: return "RAID";
                case 9: return "iSCSI";
                case 10: return "SAS";
                case 11: return "SATA";
                case 12: return "SD";
                case 13: return "MMC";
                case 14: return "Virtual";
                case 15: return "FileBackedVirtual";
                case 16: return "Spaces";
                case 17: return "NVMe";
                case 18: return "SCM";
                case 19: return "UFS";
                default: return "Unknown";
            }
        }

        private static string MediaName(int busType, bool? seekPenalty)
        {
            if (busType == 17) return "NVMe SSD";
            if (busType == 11)
            {
                if (seekPenalty.HasValue) return seekPenalty.Value ? "SATA HDD" : "SATA SSD";
                return "SATA";
            }
            if (busType == 14 || busType == 15) return "虚拟磁盘";
            if (busType == 7) return "USB";
            if (busType == 8) return "RAID";
            if (seekPenalty.HasValue) return seekPenalty.Value ? "HDD" : "SSD";
            return "未知";
        }
    }
}
