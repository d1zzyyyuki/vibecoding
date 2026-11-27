using System;
using System.Collections.Generic;

namespace DiskManager.Core.Planning
{
    public sealed class ExpandDonor
    {
        public PartitionInfo Partition;
        public long CapacityBytes;
        public long ShrinkBytes;
        public string Letter
        {
            get { return Partition == null ? "" : Partition.DriveLetter; }
        }
    }

    public sealed class ExpandCResult
    {
        public DiskInfo Disk;
        public PartitionInfo System;
        public List<ExpandDonor> Donors = new List<ExpandDonor>();
        public long MaxExpandableBytes;
        public long GrowthBytes;
        public bool Valid;
        public string Message;

        public long TotalShrinkBytes
        {
            get
            {
                long total = 0;
                foreach (var donor in Donors) total += donor.ShrinkBytes;
                return total;
            }
        }
    }

    public static class ExpandCPlanner
    {
        public static ExpandCResult Build(DiskInfo disk, int systemPartitionNumber)
        {
            var result = new ExpandCResult { Disk = disk };
            if (disk == null)
            {
                result.Message = "磁盘不存在";
                return result;
            }
            foreach (var partition in disk.Partitions)
            {
                if (partition.PartitionNumber == systemPartitionNumber) { result.System = partition; break; }
            }
            if (result.System == null)
            {
                result.Message = "目标系统分区不存在";
                return result;
            }
            if (!result.System.IsBasicData || !result.System.HasVolume)
            {
                result.Message = "目标不是已挂载的基本数据分区";
                return result;
            }

            var systemEnd = result.System.OffsetBytes + result.System.SizeBytes;
            foreach (var partition in disk.Partitions)
            {
                if (partition.OffsetBytes < systemEnd) continue;
                if (!partition.IsBasicData || !partition.HasVolume) continue;
                if (!string.Equals(partition.FileSystem, "NTFS", StringComparison.OrdinalIgnoreCase)) continue;
                if (string.IsNullOrEmpty(partition.DriveLetter)) continue;
                if (partition.FreeBytes <= 0) continue;
                var donor = new ExpandDonor { Partition = partition, CapacityBytes = partition.FreeBytes };
                result.Donors.Add(donor);
                result.MaxExpandableBytes += donor.CapacityBytes;
            }

            result.Valid = result.Donors.Count > 0 && result.MaxExpandableBytes > 0;
            if (!result.Valid) result.Message = "没有可回收空间的后续数据分区，可扩容 0 MB";
            return result;
        }

        public static List<long> Allocate(long growthBytes, IList<long> capacities)
        {
            var allocations = new List<long>();
            for (var i = 0; i < capacities.Count; i++) allocations.Add(0);
            if (growthBytes <= 0 || capacities == null || capacities.Count == 0) return allocations;

            long totalCapacity = 0;
            foreach (var capacity in capacities) totalCapacity += Math.Max(0, capacity);
            if (growthBytes > totalCapacity) growthBytes = totalCapacity;

            var active = new List<int>();
            for (var i = 0; i < capacities.Count; i++) if (capacities[i] > 0) active.Add(i);
            var remaining = growthBytes;
            while (remaining > 0 && active.Count > 0)
            {
                var share = remaining / active.Count;
                if (share <= 0) break;
                var capped = new List<int>();
                foreach (var index in active)
                {
                    var available = capacities[index] - allocations[index];
                    if (available <= share) capped.Add(index);
                }
                if (capped.Count == 0)
                {
                    foreach (var index in active)
                    {
                        allocations[index] += share;
                        remaining -= share;
                    }
                    if (remaining > 0)
                    {
                        foreach (var index in active)
                        {
                            if (remaining <= 0) break;
                            var available = capacities[index] - allocations[index];
                            if (available > 0) { allocations[index]++; remaining--; }
                        }
                    }
                    break;
                }
                foreach (var index in capped)
                {
                    var available = capacities[index] - allocations[index];
                    allocations[index] += available;
                    remaining -= available;
                    active.Remove(index);
                }
            }
            return allocations;
        }

        public static bool Reallocate(long growthBytes, IList<long> capacities, int fixedIndex, long fixedValue, out List<long> allocations)
        {
            allocations = Allocate(growthBytes, capacities);
            if (capacities == null || capacities.Count == 0 || fixedIndex < 0 || fixedIndex >= capacities.Count) return false;
            fixedValue = Math.Max(0, Math.Min(capacities[fixedIndex], fixedValue));
            var otherCapacity = 0L;
            for (var i = 0; i < capacities.Count; i++) if (i != fixedIndex) otherCapacity += Math.Max(0, capacities[i]);
            var minFixed = Math.Max(0, growthBytes - otherCapacity);
            if (fixedValue < minFixed) fixedValue = minFixed;
            if (fixedValue > capacities[fixedIndex]) fixedValue = capacities[fixedIndex];

            var otherIndices = new List<int>();
            var otherCapacities = new List<long>();
            for (var i = 0; i < capacities.Count; i++)
            {
                if (i == fixedIndex) continue;
                otherIndices.Add(i);
                otherCapacities.Add(capacities[i]);
            }
            var remainder = Math.Max(0, growthBytes - fixedValue);
            var otherAllocations = Allocate(remainder, otherCapacities);
            allocations = new List<long>(capacities.Count);
            for (var i = 0; i < capacities.Count; i++) allocations.Add(0);
            allocations[fixedIndex] = fixedValue;
            for (var i = 0; i < otherIndices.Count; i++) allocations[otherIndices[i]] = otherAllocations[i];
            return true;
        }
    }
}
