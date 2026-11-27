namespace DiskManager.Core;

public sealed class ScanOptions
{
	public bool ProbeSpeed = true;

	public bool ProbeWrite = true;

	public int SpeedSampleBytes = 16777216;

	public int WriteSampleBytes = 8388608;

	public int SpeedSampleCount = 3;

	public int MaxDisks = 32;

	public bool ProbeHealth = true;
}
