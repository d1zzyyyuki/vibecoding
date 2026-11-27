using System;
using System.Windows.Media;
using DiskManager.Core;

namespace DiskManager.ViewModels
{
    public sealed class PartitionViewModel
    {
        private readonly double _diskSpeedMBps;

        public PartitionViewModel(PartitionInfo partition, double diskSpeedMBps)
        {
            Source = partition;
            _diskSpeedMBps = diskSpeedMBps;
        }

        public PartitionInfo Source { get; private set; }

        public string LetterText
        {
            get { return string.IsNullOrEmpty(Source.DriveLetter) ? "—" : Source.DriveLetter + ":"; }
        }

        public string TitleText
        {
            get
            {
                if (!string.IsNullOrEmpty(Source.DriveLetter)) return Source.DriveLetter + ":";
                if (Source.IsEfi) return "EFI";
                if (Source.IsMsr) return "MSR";
                if (Source.IsRecovery) return "REC";
                return UiLanguage.T("分区 ", "Partition ") + Source.PartitionNumber;
            }
        }

        public string LabelText
        {
            get { return string.IsNullOrEmpty(Source.Label) ? "—" : Source.Label; }
        }

        public string TypeText
        {
            get
            {
                if (UiLanguage.English)
                {
                    if (Source.IsSystem) return "System partition";
                    if (Source.IsEfi) return "EFI system";
                    if (Source.IsMsr) return "MSR reserved";
                    if (Source.IsRecovery) return "Recovery partition";
                    if (Source.IsBasicData) return "Basic data";
                    return Source.TypeName;
                }
                if (Source.IsSystem) return "系统分区";
                if (Source.IsEfi) return "EFI 系统";
                if (Source.IsMsr) return "MSR 保留";
                if (Source.IsRecovery) return "恢复分区";
                if (Source.IsBasicData) return "基本数据";
                return Source.TypeName;
            }
        }

        public string FileSystemText
        {
            get { return string.IsNullOrEmpty(Source.FileSystem) ? "—" : Source.FileSystem; }
        }

        public string SizeText
        {
            get { return Humanize.Bytes(Source.SizeBytes); }
        }

        public string FreeText
        {
            get { return Source.HasVolume ? Humanize.Bytes(Source.FreeBytes) : "—"; }
        }

        public string FreePercentText
        {
            get { return Source.HasVolume ? Source.FreePercent.ToString("0") + "%" : "—"; }
        }

        public string UsedPercentText
        {
            get { return Source.HasVolume ? Source.UsedPercent.ToString("0") + "%" : "—"; }
        }

        public string FreeDisplayText
        {
            get { return UiLanguage.T("空闲 ", "Free ") + FreeText; }
        }

        public string UsedPercentDisplayText
        {
            get { return UiLanguage.T("已用 ", "Used ") + UsedPercentText; }
        }

        public double UsagePercent
        {
            get { return Source.HasVolume ? Source.UsedPercent : 0; }
        }

        public string StatusText
        {
            get
            {
                if (Source.IsSystem) return UiLanguage.T("系统", "System");
                if (Source.IsHidden) return UiLanguage.T("隐藏", "Hidden");
                if (Source.HasVolume) return IsLowSpace ? UiLanguage.T("空间不足", "Low space") : UiLanguage.T("正常", "Normal");
                return UiLanguage.T("未挂载", "Not mounted");
            }
        }

        public Brush StatusBrush
        {
            get
            {
                if (Source.IsSystem) return UiBrush.Get("SystemBlue");
                if (IsLowSpace) return UiBrush.Get("Danger");
                if (Source.IsHidden) return UiBrush.Get("TextMuted");
                return UiBrush.Get("NormalGreen");
            }
        }

        public bool IsLowSpace
        {
            get
            {
                if (!Source.HasVolume || string.IsNullOrEmpty(Source.DriveLetter)) return false;
                var total = Source.VolumeTotalBytes > 0 ? Source.VolumeTotalBytes : Source.SizeBytes;
                return SpaceHealth.IsLowFreeSpace(Source.FreeBytes, total);
            }
        }

        public bool IsSystem
        {
            get { return Source.IsSystem; }
        }

        public string OffsetText
        {
            get { return Humanize.Bytes(Source.OffsetBytes); }
        }

        public string VolumeGuidText
        {
            get
            {
                if (!string.IsNullOrEmpty(Source.VolumeGuid)) return Source.VolumeGuid.TrimEnd('\\');
                if (!string.IsNullOrEmpty(Source.GptTypeId)) return Source.GptTypeId;
                return "—";
            }
        }

        public string GptTypeText
        {
            get { return string.IsNullOrEmpty(Source.GptTypeId) ? "—" : Source.GptTypeId; }
        }

        public string PartitionStyleText
        {
            get { return Source.PartitionStyle + UiLanguage.T(" / 分区 ", " / Partition ") + Source.PartitionNumber; }
        }

        public string MoveEstimateText
        {
            get
            {
                if (IsSystem || !Source.HasVolume || _diskSpeedMBps <= 0) return "—";
                return Humanize.MoveEstimate(Source.SizeBytes, _diskSpeedMBps);
            }
        }

        public string MoveEstimateNote
        {
            get
            {
                if (IsSystem) return UiLanguage.T("系统卷不参与直接搬移", "System volume is not moved directly");
                if (!Source.HasVolume) return UiLanguage.T("无卷可搬移", "No volume to move");
                if (_diskSpeedMBps <= 0) return UiLanguage.T("缺少测速数据", "Speed data missing");
                return UiLanguage.T("按整卷搬移、有效吞吐 65% 估算", "Estimated at 65% effective whole-volume throughput");
            }
        }

        public Brush MapBrush
        {
            get
            {
                if (Source.IsSystem) return UiBrush.Get("MapSystem");
                if (Source.IsBasicData) return UiBrush.Get("MapData");
                return UiBrush.Get("MapHidden");
            }
        }

        public Brush MapTextBrush
        {
            get { return Source.IsBasicData || Source.IsSystem ? UiBrush.Get("MapText") : UiBrush.Get("MapTextMuted"); }
        }

        public string MapLabel
        {
            get
            {
                if (!string.IsNullOrEmpty(Source.DriveLetter)) return Source.DriveLetter + ":";
                if (Source.IsEfi) return "EFI";
                if (Source.IsMsr) return "MSR";
                if (Source.IsRecovery) return "REC";
                return "P" + Source.PartitionNumber;
            }
        }

        public string MapDetail
        {
            get
            {
                if (UiLanguage.English)
                    return TitleText + " · " + TypeText + " · " + SizeText + (Source.HasVolume ? " · Free " + FreeText : string.Empty);
                return TitleText + " · " + TypeText + " · " + SizeText + (Source.HasVolume ? " · 空闲 " + FreeText : string.Empty);
            }
        }

        public string Tooltip
        {
            get
            {
                if (UiLanguage.English)
                {
                    return TitleText + "  " + TypeText + "\n" +
                           "File system " + FileSystemText + " · Size " + SizeText + "\n" +
                           "Offset " + OffsetText + " · " + PartitionStyleText + "\n" +
                           (Source.HasVolume ? "Free " + FreeText + " (" + FreePercentText + ")" : "No mounted volume");
                }
                return TitleText + "  " + TypeText + "\n" +
                       "文件系统 " + FileSystemText + " · 容量 " + SizeText + "\n" +
                       "偏移 " + OffsetText + " · " + PartitionStyleText + "\n" +
                       (Source.HasVolume ? "空闲 " + FreeText + "（" + FreePercentText + "）" : "未挂载卷");
            }
        }
    }
}
