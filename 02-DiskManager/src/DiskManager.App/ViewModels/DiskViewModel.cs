using System;
using System.Collections.ObjectModel;
using System.Linq;
using System.Windows.Media;
using DiskManager.Core;

namespace DiskManager.ViewModels
{
    public sealed class DiskViewModel : ObservableObject
    {
        private readonly long _usedBytes;
        private readonly long _freeBytes;
        private readonly double _usagePercent;

        public DiskViewModel(DiskInfo disk)
        {
            Source = disk;
            Partitions = new ObservableCollection<PartitionViewModel>();
            foreach (var partition in disk.Partitions)
            {
                Partitions.Add(new PartitionViewModel(partition, disk.Speed != null && disk.Speed.Success ? disk.Speed.ThroughputMBps : 0));
            }

            _freeBytes = disk.UsageFreeBytes;
            _usedBytes = Math.Max(0, disk.UsageTotalBytes - disk.UsageFreeBytes);
            _usagePercent = disk.SizeBytes > 0 ? Math.Max(0, Math.Min(100, _usedBytes * 100.0 / disk.SizeBytes)) : 0;
        }

        public DiskInfo Source { get; private set; }

        public ObservableCollection<PartitionViewModel> Partitions { get; private set; }

        public string DiskIndexText
        {
            get { return "DISK " + Source.Number; }
        }

        public string Title
        {
            get { return Source.DisplayName; }
        }

        public string RoleText
        {
            get { return UiLanguage.T(Source.IsSystemDisk ? "系统磁盘" : "数据磁盘", Source.IsSystemDisk ? "System disk" : "Data disk"); }
        }

        public string BadgeMedia
        {
            get { return Source.MediaKind; }
        }

        public string BadgeBus
        {
            get
            {
                if (!string.IsNullOrEmpty(Source.PcieLink)) return Source.PcieLink;
                if (Source.BusType == "NVMe") return "PCIe";
                return Source.BusType;
            }
        }

        public string CapacityText
        {
            get { return Humanize.Bytes(Source.SizeBytes); }
        }

        public long SizeBytes
        {
            get { return Source.SizeBytes; }
        }

        public string FreeText
        {
            get { return Humanize.Bytes(_freeBytes); }
        }

        public string UsedText
        {
            get { return Humanize.Bytes(_usedBytes); }
        }

        public string UsagePercentText
        {
            get { return _usagePercent.ToString("0") + "%"; }
        }

        public double UsagePercent
        {
            get { return _usagePercent; }
        }

        public string PartitionCountText
        {
            get
            {
                if (UiLanguage.English) return Source.Partitions.Count + (Source.Partitions.Count == 1 ? " partition" : " partitions");
                return Source.Partitions.Count + " 个分区";
            }
        }

        public string UsedDisplayText
        {
            get { return UiLanguage.T("已用 ", "Used ") + UsedText; }
        }

        public string FreeDisplayText
        {
            get { return UiLanguage.T("空闲 ", "Free ") + FreeText; }
        }

        public string HealthText
        {
            get
            {
                var text = string.IsNullOrEmpty(Source.Health) || Source.Health == "未知" ? Source.OperationalStatus : Source.Health;
                if (!UiLanguage.English) return text;
                if (text == "在线") return "Online";
                if (text == "未知") return "Unknown";
                if (text == "预警") return "Warning";
                return text;
            }
        }

        public Brush HealthBrush
        {
            get
            {
                if (Source.Health == "预警") return UiBrush.Get("Warning");
                return UiBrush.Get("Healthy");
            }
        }

        public string SpeedText
        {
            get
            {
                if (Source.Speed == null || !Source.Speed.Success) return UiLanguage.T("测速失败", "Speed test failed");
                return UiLanguage.T("读 ", "Read ") + Humanize.SpeedMBps(Source.Speed.ThroughputMBps) +
                       (Source.WriteSpeed != null && Source.WriteSpeed.Success ? UiLanguage.T(" · 写 ", " · Write ") + Humanize.SpeedMBps(Source.WriteSpeed.ThroughputMBps) : "");
            }
        }

        public string ReadSpeedText
        {
            get
            {
                if (Source.Speed == null || !Source.Speed.Success) return "—";
                return UiLanguage.T("读 ", "Read ") + Humanize.SpeedMBps(Source.Speed.ThroughputMBps);
            }
        }

        public string WriteSpeedText
        {
            get
            {
                if (Source.WriteSpeed == null) return UiLanguage.T("写 —", "Write —");
                if (!Source.WriteSpeed.Success) return UiLanguage.T("写 —", "Write —");
                return UiLanguage.T("写 ", "Write ") + Humanize.SpeedMBps(Source.WriteSpeed.ThroughputMBps);
            }
        }

        public string SpeedDetail
        {
            get
            {
                if (Source.Speed == null) return UiLanguage.T("等待测速", "Waiting for test");
                if (!Source.Speed.Success) return Source.Speed.Error ?? UiLanguage.T("无法读取", "Unavailable");
                return UiLanguage.T("顺序读 ", "Sequential read ") + Source.Speed.SamplesCompleted + UiLanguage.T(" 次采样", " samples");
            }
        }

        public string SpeedTooltip
        {
            get
            {
                if (Source.Speed == null) return UiLanguage.T("未测速", "Not tested");
                if (UiLanguage.English)
                {
                    var english = "Read avg " + Humanize.SpeedMBps(Source.Speed.ThroughputMBps) +
                                  " / peak " + Humanize.SpeedMBps(Source.Speed.PeakMBps) +
                                  "\nRead samples " + Source.Speed.SamplesCompleted + ", " + Source.Speed.ElapsedMs + " ms";
                    if (Source.WriteSpeed != null && Source.WriteSpeed.Success)
                        english += "\nWrite avg " + Humanize.SpeedMBps(Source.WriteSpeed.ThroughputMBps) + " (temp file)";
                    else if (Source.WriteSpeed != null)
                        english += "\nWrite test failed: " + Source.WriteSpeed.Error;
                    return english;
                }
                var text = "读取平均 " + Humanize.SpeedMBps(Source.Speed.ThroughputMBps) +
                           " / 峰值 " + Humanize.SpeedMBps(Source.Speed.PeakMBps) +
                           "\n读采样 " + Source.Speed.SamplesCompleted + " 次，耗时 " + Source.Speed.ElapsedMs + " ms";
                if (Source.WriteSpeed != null && Source.WriteSpeed.Success)
                    text += "\n写入平均 " + Humanize.SpeedMBps(Source.WriteSpeed.ThroughputMBps) + "（临时文件）";
                else if (Source.WriteSpeed != null)
                    text += "\n写入测速失败：" + Source.WriteSpeed.Error;
                return text;
            }
        }

        public bool IsSystemDisk
        {
            get { return Source.IsSystemDisk; }
        }

        public bool HasLowSpace
        {
            get { return Partitions.Any(p => p.IsLowSpace); }
        }

        public string Tooltip
        {
            get
            {
                if (UiLanguage.English)
                {
                    return Source.DisplayName + "\n" +
                           "Bus " + Source.BusType + " · " + Source.MediaKind + "\n" +
                           "Capacity " + CapacityText + " · " + Source.LogicalSectorSize + " / " + Source.PhysicalSectorSize + " B sectors\n" +
                           "Partition table " + Source.PartitionStyle;
                }
                return Source.DisplayName + "\n" +
                       "总线 " + Source.BusType + " · " + Source.MediaKind + "\n" +
                       "容量 " + CapacityText + " · " + Source.LogicalSectorSize + " / " + Source.PhysicalSectorSize + " B 扇区\n" +
                       "分区表 " + Source.PartitionStyle;
            }
        }
    }
}
