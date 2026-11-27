using System.Collections.Generic;

namespace DiskManager.Core;

public sealed class DiskInfo
{
	public int Number;

	public string Model;

	public string Serial;

	public string BusType;

	public string MediaKind;

	public string PcieLink;

	public long SizeBytes;

	public int LogicalSectorSize;

	public int PhysicalSectorSize;

	public string PartitionStyle;

	public bool IsSystemDisk;

	public bool IsBootDisk;

	public bool IsRemovable;

	public string Health;

	public string OperationalStatus;

	public SpeedProbeResult Speed;

	public SpeedProbeResult WriteSpeed;

	public List<PartitionInfo> Partitions = new List<PartitionInfo>();

	public string DisplayName => string.IsNullOrEmpty(Model) ? ("磁盘 " + Number) : Model;

	public long UsageTotalBytes
	{
		get
		{
			long num = 0L;
			foreach (PartitionInfo partition in Partitions)
			{
				if (partition.HasVolume && partition.VolumeTotalBytes > 0)
				{
					num += partition.VolumeTotalBytes;
				}
			}
			return num;
		}
	}

	public long UsageFreeBytes
	{
		get
		{
			long num = 0L;
			foreach (PartitionInfo partition in Partitions)
			{
				if (partition.HasVolume)
				{
					num += partition.FreeBytes;
				}
			}
			return num;
		}
	}
}
