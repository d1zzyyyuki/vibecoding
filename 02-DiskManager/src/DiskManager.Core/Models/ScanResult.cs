using System;

using System.Collections.Generic;



namespace DiskManager.Core;



public sealed class ScanResult

{

	public string ToolName = "DiskManager";



	public string Version = "1.0.0";



	public DateTime StartedAtUtc;



	public long DurationMs;



	public bool IsElevated;



	public string MachineName;



	public string OsDescription;



	public string OsArchitecture;



	public string SystemVolumeGuid;



	public List<DiskInfo> Disks = new List<DiskInfo>();



	public List<string> Warnings = new List<string>();



	public List<string> Errors = new List<string>();



	public int VolumeCount

	{

		get

		{

			int num = 0;

			foreach (DiskInfo disk in Disks)

			{

				foreach (PartitionInfo partition in disk.Partitions)

				{

					if (partition.HasVolume)

					{

						num++;

					}

				}

			}

			return num;

		}

	}

}

