using System;
using System.Collections.Generic;
using DiskManager.Core;

namespace DiskManager.Core.Planning
{
    public enum PlanStepKind
    {
        ShrinkDataPartition,
        LockDataVolume,
        MoveDataPartition,
        UpdatePartitionTable,
        ExtendSystemVolume,
        Verify
    }

    public sealed class PlanStep
    {
        public PlanStepKind Kind;
        public string Title;
        public string Detail;
        public long Bytes;
        public long EstimatedMs;
    }

    public sealed class PlanIssue
    {
        public string Code;
        public string Message;
    }

    public sealed class PlanRequest
    {
        public int DiskNumber;
        public int SystemPartitionNumber;
        public int DataPartitionNumber;
        public long GrowthBytes;
        public long AlignmentBytes = 1024 * 1024;
        public bool? BitLockerDetected;
    }

    public sealed class PlanResult
    {
        public bool IsValid
        {
            get { return Errors.Count == 0; }
        }

        public List<PlanIssue> Errors = new List<PlanIssue>();
        public List<string> Warnings = new List<string>();
        public List<PlanStep> Steps = new List<PlanStep>();

        public int DiskNumber;
        public int SystemPartitionNumber;
        public int DataPartitionNumber;
        public long OldSystemSizeBytes;
        public long NewSystemSizeBytes;
        public long GrowthBytes;
        public long OldDataStartBytes;
        public long NewDataStartBytes;
        public long OldDataSizeBytes;
        public long NewDataSizeBytes;
        public long DataShrinkBytes;
        public long DataMoveBytes;
        public long TailGapBytes;
        public double DiskSpeedMBps;
        public long EstimatedMs;
        public bool EstimateReliable = true;

        public string DataLabel;
        public string SystemLabel;

        public string EstimateText
        {
            get
            {
                if (!EstimateReliable) return "—（虚拟磁盘不估算）";
                return EstimatedMs > 0 ? Humanize.Duration(TimeSpan.FromMilliseconds(EstimatedMs)) : "—";
            }
        }

        public string Summary
        {
            get
            {
                if (!IsValid) return "计划不可执行";
                return (string.IsNullOrEmpty(SystemLabel) ? "系统分区" : SystemLabel) + " " +
                       Humanize.Bytes(OldSystemSizeBytes) + " → " + Humanize.Bytes(NewSystemSizeBytes) +
                       "；" + (string.IsNullOrEmpty(DataLabel) ? "数据分区" : DataLabel) + " 右移 " +
                       Humanize.Bytes(GrowthBytes) + "；搬移约 " + Humanize.Bytes(DataMoveBytes) +
                       "；预计 " + EstimateText;
            }
        }

        public long NewSystemEndBytes
        {
            get { return OldDataStartBytes + GrowthBytes; }
        }

        public void AddError(string code, string message)
        {
            Errors.Add(new PlanIssue { Code = code, Message = message });
        }
    }

    public static class PartitionPlanner
    {
        private const long MinimumGrowthBytes = 64L * 1024 * 1024;
        private const long ReservedTailBytes = 1L * 1024 * 1024;
        private const long MinimumDataFreeBytes = 256L * 1024 * 1024;

        public static PlanResult Build(DiskInfo disk, PlanRequest request, double diskSpeedMBps)
        {
            var result = new PlanResult
            {
                DiskSpeedMBps = diskSpeedMBps,
                GrowthBytes = request == null ? 0 : request.GrowthBytes
            };

            if (disk == null)
            {
                result.AddError("disk-missing", "没有选中磁盘。");
                return result;
            }
            if (request == null)
            {
                result.AddError("request-missing", "没有规划参数。");
                return result;
            }

            result.DiskNumber = disk.Number;
            result.SystemPartitionNumber = request.SystemPartitionNumber;
            result.DataPartitionNumber = request.DataPartitionNumber;

            if (disk.PartitionStyle != "GPT")
            {
                result.AddError("not-gpt", "v1 只规划 GPT 磁盘，当前磁盘是 " + (disk.PartitionStyle ?? "未知") + "。");
                return result;
            }

            var system = FindPartition(disk, request.SystemPartitionNumber);
            var data = FindPartition(disk, request.DataPartitionNumber);
            if (system == null)
            {
                result.AddError("system-missing", "没有找到目标系统分区。");
                return result;
            }
            if (data == null)
            {
                result.AddError("data-missing", "没有找到要右移的数据分区。");
                return result;
            }
            if (system.PartitionNumber == data.PartitionNumber)
            {
                result.AddError("same-partition", "目标系统分区和数据分区不能是同一个。");
                return result;
            }

            result.SystemLabel = LabelOf(system);
            result.DataLabel = LabelOf(data);
            result.OldSystemSizeBytes = system.SizeBytes;
            result.OldDataStartBytes = data.OffsetBytes;
            result.OldDataSizeBytes = data.SizeBytes;

            if (system.PartitionStyle != "GPT" || data.PartitionStyle != "GPT")
            {
                result.AddError("not-gpt-partition", "目标分区不是 GPT 分区。");
                return result;
            }
            if (!system.IsBasicData || !data.IsBasicData)
            {
                result.AddError("not-basic-data", "v1 只规划两块“基本数据”分区；EFI/MSR/恢复分区不能作为目标。");
                return result;
            }
            if (!system.HasVolume || !string.Equals(system.FileSystem, "NTFS", StringComparison.OrdinalIgnoreCase))
            {
                result.AddError("system-not-ntfs", "目标系统分区必须是已挂载的 NTFS 卷。");
                return result;
            }
            if (!data.HasVolume || !string.Equals(data.FileSystem, "NTFS", StringComparison.OrdinalIgnoreCase))
            {
                result.AddError("data-not-ntfs", "要右移的数据分区必须是已挂载的 NTFS 卷。");
                return result;
            }
            if (request.BitLockerDetected == true)
            {
                result.AddError("bitlocker", "检测到 BitLocker，v1 不会对该盘执行搬移。");
                return result;
            }

            var alignment = request.AlignmentBytes <= 0 ? 1024 * 1024 : request.AlignmentBytes;
            var dataEnd = data.OffsetBytes + data.SizeBytes;
            if (system.OffsetBytes + system.SizeBytes != data.OffsetBytes)
            {
                result.AddError("not-adjacent", "系统分区后面必须紧邻数据分区；当前两者之间有其它空间或分区。");
                return result;
            }
            if (request.GrowthBytes <= 0)
            {
                result.AddError("growth-invalid", "扩容量必须大于 0。");
                return result;
            }
            if (request.GrowthBytes < MinimumGrowthBytes)
            {
                result.AddError("growth-too-small", "扩容量至少 64 MB。");
                return result;
            }
            if (request.GrowthBytes % alignment != 0)
            {
                result.AddError("growth-misaligned", "扩容量必须按 " + Humanize.Bytes(alignment) + " 对齐。");
                return result;
            }

            var diskLimit = AlignDown(disk.SizeBytes - ReservedTailBytes, alignment);
            if (dataEnd > diskLimit)
            {
                result.AddError("data-beyond-limit", "数据分区末尾超过 GPT 可用范围，无法继续规划。");
                return result;
            }

            var nextStart = diskLimit;
            foreach (var partition in disk.Partitions)
            {
                if (partition.OffsetBytes >= dataEnd && partition.OffsetBytes < nextStart) nextStart = partition.OffsetBytes;
            }

            var tailGap = nextStart - dataEnd;
            result.TailGapBytes = tailGap;
            var shrink = Math.Max(0, request.GrowthBytes - tailGap);
            shrink = AlignUp(shrink, alignment);

            var newDataSize = data.SizeBytes - shrink;
            var newDataEnd = data.OffsetBytes + request.GrowthBytes + newDataSize;
            if (newDataEnd > nextStart)
            {
                var extra = AlignUp(newDataEnd - nextStart, alignment);
                shrink += extra;
                newDataSize = data.SizeBytes - shrink;
                newDataEnd = data.OffsetBytes + request.GrowthBytes + newDataSize;
            }

            if (newDataSize <= 0 || newDataEnd > nextStart)
            {
                result.AddError("no-room", "没有足够连续空间完成右移；请减少扩容量。");
                return result;
            }

            var usedBytes = Math.Max(0, data.VolumeTotalBytes - data.FreeBytes);
            if (newDataSize < usedBytes + MinimumDataFreeBytes)
            {
                result.AddError("data-too-small",
                    "数据分区收缩后会小于已用空间加安全余量（已用 " + Humanize.Bytes(usedBytes) +
                    "，收缩后 " + Humanize.Bytes(newDataSize) + "）。请先清理或减少扩容量。");
                return result;
            }

            result.GrowthBytes = request.GrowthBytes;
            result.NewSystemSizeBytes = system.SizeBytes + request.GrowthBytes;
            result.NewDataStartBytes = data.OffsetBytes + request.GrowthBytes;
            result.NewDataSizeBytes = newDataSize;
            result.DataShrinkBytes = shrink;
            result.DataMoveBytes = newDataSize;

            if (disk.IsSystemDisk)
            {
                result.Warnings.Add("目标包含本机正在运行的系统卷；真实执行前必须完成分区表写入原型验证和备份。");
            }
            if (request.BitLockerDetected == null)
            {
                result.Warnings.Add("BitLocker 状态尚未检测；真实执行前必须检查并拒绝加密卷。");
            }
            result.Warnings.Add("D 盘不能有页面文件、VSS 快照或阻止锁定的打开句柄；真实执行前需逐项预检。");
            result.Warnings.Add("整卷搬移是块级操作，建议先备份或创建系统还原点。");
            if (disk.BusType == "FileBackedVirtual" || disk.MediaKind == "虚拟磁盘")
            {
                result.EstimateReliable = false;
                result.Warnings.Add("当前是虚拟磁盘，文件缓存让测速值不代表物理盘；耗时估算仅作流程演示。");
            }

            BuildSteps(result, disk, system, data, request.GrowthBytes, shrink, newDataSize, diskSpeedMBps);
            return result;
        }

        private static void BuildSteps(PlanResult result, DiskInfo disk, PartitionInfo system, PartitionInfo data, long growth, long shrink, long newDataSize, double diskSpeedMBps)
        {
            if (shrink > 0)
            {
                result.Steps.Add(new PlanStep
                {
                    Kind = PlanStepKind.ShrinkDataPartition,
                    Title = "收缩数据分区末尾",
                    Detail = "先把 " + LabelOf(data) + " 从末尾收缩 " + Humanize.Bytes(shrink) +
                             "，为右移腾出尾部空间；收缩后大小 " + Humanize.Bytes(data.SizeBytes - shrink) + "。",
                    Bytes = shrink,
                    EstimatedMs = 0
                });
            }

            result.Steps.Add(new PlanStep
            {
                Kind = PlanStepKind.LockDataVolume,
                Title = "锁定并卸载数据分区",
                Detail = "关闭 " + LabelOf(data) + " 上的占用，锁定卷后断开文件系统访问；失败则中止，不进入搬移。",
                Bytes = 0,
                EstimatedMs = 200
            });

            var moveMs = diskSpeedMBps > 0
                ? (long)Math.Round(newDataSize / 1024.0 / 1024.0 / (diskSpeedMBps * 0.65) * 1000.0)
                : 0;
            if (moveMs < 1) moveMs = 0;

            result.Steps.Add(new PlanStep
            {
                Kind = PlanStepKind.MoveDataPartition,
                Title = "整卷右移数据分区",
                Detail = LabelOf(data) + " 从 " + Humanize.Bytes(data.OffsetBytes) + " 移到 " +
                         Humanize.Bytes(data.OffsetBytes + growth) + "，移动 " + Humanize.Bytes(newDataSize) +
                         "；按顺序读有效吞吐 65% 估算。",
                Bytes = newDataSize,
                EstimatedMs = moveMs
            });

            result.Steps.Add(new PlanStep
            {
                Kind = PlanStepKind.UpdatePartitionTable,
                Title = "更新 GPT",
                Detail = "同时写入新的系统分区长度和数据分区起点；写入前备份 GPT，写入失败必须中止并恢复。",
                Bytes = 0,
                EstimatedMs = 500
            });

            result.Steps.Add(new PlanStep
            {
                Kind = PlanStepKind.ExtendSystemVolume,
                Title = "在线扩展系统卷",
                Detail = "调用 FSCTL_EXTEND_VOLUME 把 " + LabelOf(system) + " 扩到 " +
                         Humanize.Bytes(system.SizeBytes + growth) + "；系统卷保持在线。",
                Bytes = growth,
                EstimatedMs = 1000
            });

            result.Steps.Add(new PlanStep
            {
                Kind = PlanStepKind.Verify,
                Title = "重新扫描并校验",
                Detail = "重新读取 GPT 和卷信息，检查系统盘可用空间、数据分区文件系统与日志状态。",
                Bytes = 0,
                EstimatedMs = 500
            });

            foreach (var step in result.Steps) result.EstimatedMs += step.EstimatedMs;
        }

        private static PartitionInfo FindPartition(DiskInfo disk, int number)
        {
            foreach (var partition in disk.Partitions)
            {
                if (partition.PartitionNumber == number) return partition;
            }
            return null;
        }

        private static string LabelOf(PartitionInfo partition)
        {
            if (!string.IsNullOrEmpty(partition.DriveLetter)) return partition.DriveLetter + ":";
            if (!string.IsNullOrEmpty(partition.Label)) return partition.Label;
            return "分区 " + partition.PartitionNumber;
        }

        private static long AlignUp(long value, long alignment)
        {
            if (value <= 0) return 0;
            var remainder = value % alignment;
            return remainder == 0 ? value : value + alignment - remainder;
        }

        private static long AlignDown(long value, long alignment)
        {
            if (value <= 0) return 0;
            return value - value % alignment;
        }
    }
}
