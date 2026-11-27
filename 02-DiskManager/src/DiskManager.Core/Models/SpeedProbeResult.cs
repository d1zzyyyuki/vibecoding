using System.Collections.Generic;

namespace DiskManager.Core;

public sealed class SpeedProbeResult
{
	public bool Success;

	public string Error;

	public string Method = "raw-read";

	public int SampleBytes;

	public int SamplesCompleted;

	public long TotalBytesRead;

	public long ElapsedMs;

	public double ThroughputMBps;

	public double PeakMBps;

	public List<SpeedSample> Samples = new List<SpeedSample>();
}
