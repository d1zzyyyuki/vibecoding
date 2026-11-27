namespace DiskManager.Core;

public sealed class SpeedSample
{
	public long OffsetBytes;

	public int BytesRead;

	public long ElapsedMs;

	public double ThroughputMBps;
}
