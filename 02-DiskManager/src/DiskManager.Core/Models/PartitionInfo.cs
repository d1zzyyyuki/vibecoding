using System;

namespace DiskManager.Core;

public sealed class PartitionInfo
{
	public int DiskNumber;

	public int PartitionNumber;

	public long OffsetBytes;

	public long SizeBytes;

	public string PartitionStyle;

	public string GptTypeId;

	public string GptName;

	public string TypeName;

	public ulong GptAttributes;

	public bool IsEfi;

	public bool IsMsr;

	public bool IsRecovery;

	public bool IsBasicData;

	public bool IsHidden;

	public bool IsSystem;

	public bool IsBoot;

	public bool HasVolume;

	public string DriveLetter;

	public string Label;

	public string FileSystem;

	public string VolumeGuid;

	public long VolumeTotalBytes;

	public long FreeBytes;

	public string DisplayLetter => string.IsNullOrEmpty(DriveLetter) ? "—" : (DriveLetter + ":");

	public double FreePercent
	{
		get
		{
			long num = ((VolumeTotalBytes > 0) ? VolumeTotalBytes : SizeBytes);
			if (num <= 0)
			{
				return 0.0;
			}
			return Math.Max(0.0, Math.Min(100.0, (double)FreeBytes * 100.0 / (double)num));
		}
	}

	public double UsedPercent => 100.0 - FreePercent;
}
