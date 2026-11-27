using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using DiskManager.Core;
using DiskManager.Core.Engine;
using DiskManager.Core.Operations;

namespace DiskManager.Offline
{
    internal static class OfflineExecutor
    {
        public static int Run(string jobPath, string journalPath, bool allowReal)
        {
            var job = OfflineJob.Load(jobPath);
            var disk = FindDisk(job);
            if (disk == null) { Console.WriteLine("FAIL disk not found"); return 1; }
            if (!string.Equals(disk.BusType, "FileBackedVirtual", StringComparison.OrdinalIgnoreCase) && !allowReal)
            {
                Console.WriteLine("FAIL real disks need explicit --allow-real and user authorization; current run refused");
                return 1;
            }

            var system = FindPartition(disk, job.SystemPartition);
            if (system == null) { Console.WriteLine("FAIL system partition not found"); return 1; }
            if (system.OffsetBytes != job.SystemOffset || system.SizeBytes != job.SystemSize)
            {
                Console.WriteLine("FAIL system layout changed");
                return 1;
            }
            foreach (var donor in job.Donors)
            {
                var part = FindPartition(disk, donor.Partition);
                if (part == null || part.OffsetBytes != donor.Offset || part.SizeBytes != donor.Size)
                {
                    Console.WriteLine("FAIL donor layout changed: " + donor.Partition);
                    return 1;
                }
            }

            if (string.IsNullOrEmpty(journalPath)) journalPath = Path.Combine(Path.GetDirectoryName(Path.GetFullPath(jobPath)), "offline.journal");
            var journalDirectory = Path.GetDirectoryName(Path.GetFullPath(journalPath));
            if (!string.IsNullOrEmpty(journalDirectory)) Directory.CreateDirectory(journalDirectory);
            var gpt = GptEditor.ReadLayout(disk.Number, out var layoutError);
            if (gpt == null) { Console.WriteLine("FAIL " + layoutError); return 1; }
            File.WriteAllBytes(journalPath + ".gpt", gpt);
            WriteJournal(journalPath, "Prepared", job, 0);

            var failures = new List<string>();
            var shrunk = new Dictionary<int, long>();
            try
            {
                WriteJournal(journalPath, "Shrinking", job, 0);
                foreach (var donor in job.Donors)
                {
                    var part = FindPartition(disk, donor.Partition);
                    if (part == null || string.IsNullOrEmpty(part.DriveLetter))
                    {
                        failures.Add("donor has no drive letter: " + donor.Partition);
                        return Fail(journalPath, job, failures);
                    }
                    if (!VolumeControl.ShrinkWithDiskPart(part.DriveLetter, donor.ShrinkBytes, out var shrinkError, out var shrinkOutput))
                    {
                        failures.Add("shrink failed: " + shrinkError + " " + (shrinkOutput ?? "").Trim());
                        return Fail(journalPath, job, failures);
                    }
                    shrunk[donor.Partition] = donor.Size - donor.ShrinkBytes;
                }

                disk = FindDisk(job);
                if (disk == null) { failures.Add("disk disappeared after shrink"); return Fail(journalPath, job, failures); }
                foreach (var donor in job.Donors)
                {
                    var part = FindPartition(disk, donor.Partition);
                    if (part == null) { failures.Add("donor missing after shrink: " + donor.Partition); return Fail(journalPath, job, failures); }
                    if (part.SizeBytes > donor.Size - donor.ShrinkBytes)
                    {
                        failures.Add("donor shrink incomplete: " + donor.Partition);
                        return Fail(journalPath, job, failures);
                    }
                }

                var locks = new List<LockedVolume>();
                LockedVolume systemLocked = null;
                try
                {
                    foreach (var donor in job.Donors.OrderByDescending(d => d.Offset))
                    {
                        var part = FindPartition(disk, donor.Partition);
                        if (part == null) { failures.Add("donor missing before lock: " + donor.Partition); return Fail(journalPath, job, failures); }
                        var locked = VolumeControl.LockAndDismount(part.VolumeGuid, part.DriveLetter, out var lockError);
                        if (locked == null)
                        {
                            failures.Add("lock failed: " + donor.Partition + " " + lockError);
                            return Fail(journalPath, job, failures);
                        }
                        locks.Add(locked);
                    }

                    WriteJournal(journalPath, "Moving", job, 0);
                    foreach (var donor in job.Donors.OrderByDescending(d => d.Offset))
                    {
                        var part = FindPartition(disk, donor.Partition);
                        var newSize = part.SizeBytes;
                        var end = part.OffsetBytes + newSize;
                        long last = part.OffsetBytes;
                        BlockMover.MoveRight(disk.Number, part.OffsetBytes, end, job.GrowthBytes, end,
                            next => { last = next; WriteJournal(journalPath, "Moving", job, last); }, 32 * 1024 * 1024);
                    }

                    systemLocked = VolumeControl.LockAndDismount(system.VolumeGuid, system.DriveLetter, out var systemLockError);
                    if (systemLocked == null)
                    {
                        failures.Add("system lock failed: " + systemLockError);
                        return Fail(journalPath, job, failures);
                    }

                    var current = GptEditor.ReadLayout(disk.Number, out var readError);
                    if (current == null) { failures.Add(readError); return Fail(journalPath, job, failures); }
                    var starts = new Dictionary<int, long>();
                    foreach (var donor in job.Donors)
                    {
                        var part = FindPartition(disk, donor.Partition);
                        starts[donor.Partition] = part.OffsetBytes;
                    }
                    GptEditor.PatchMulti(current, job.SystemPartition, job.GrowthBytes, starts, false);
                    if (!GptEditor.WriteLayout(disk.Number, current, out var writeError))
                    {
                        failures.Add("GPT write failed: " + writeError);
                        return Fail(journalPath, job, failures);
                    }
                    WriteJournal(journalPath, "GptUpdated", job, 0);

                    if (!GptEditor.GrowPartition(disk.Number, job.SystemPartition, job.GrowthBytes, out var growError))
                    {
                        failures.Add("grow partition failed: " + growError);
                        return Fail(journalPath, job, failures);
                    }
                    GptEditor.UpdateDriveSize(disk.Number, out _);
                    GptEditor.RefreshDiskProperties(disk.Number);
                    systemLocked.Dispose();
                    systemLocked = null;
                    var newSystemSize = system.SizeBytes + job.GrowthBytes;
                    if (!VolumeControl.ExtendVolume(system.VolumeGuid, system.DriveLetter, newSystemSize,
                            disk.LogicalSectorSize > 0 ? disk.LogicalSectorSize : 512, out var extendError))
                    {
                        failures.Add("extend filesystem failed: " + extendError);
                        return Fail(journalPath, job, failures);
                    }
                    WriteJournal(journalPath, "Completed", job, 0);
                    Console.WriteLine("OK offline move completed");
                    return 0;
                }
                finally
                {
                    if (systemLocked != null) systemLocked.Dispose();
                    foreach (var locked in locks) locked.Dispose();
                }
            }
            catch (Exception ex)
            {
                failures.Add(ex.GetType().Name + ": " + ex.Message);
                return Fail(journalPath, job, failures);
            }
        }

        private static int Fail(string journalPath, OfflineJob job, List<string> failures)
        {
            var text = string.Join(" | ", failures);
            WriteJournal(journalPath, "Failed", job, 0, text);
            Console.WriteLine("FAIL " + text);
            return 1;
        }

        private static void WriteJournal(string path, string phase, OfflineJob job, long progress, string error = null)
        {
            var builder = new StringBuilder();
            builder.AppendLine("version=1");
            builder.AppendLine("phase=" + phase);
            builder.AppendLine("diskNumber=" + job.DiskNumber);
            builder.AppendLine("diskSerial=" + job.DiskSerial);
            builder.AppendLine("systemPartition=" + job.SystemPartition);
            builder.AppendLine("growthBytes=" + job.GrowthBytes);
            builder.AppendLine("progressSourceOffset=" + progress);
            builder.AppendLine("updatedUtc=" + DateTime.UtcNow.ToString("o"));
            builder.AppendLine("lastError=" + (error ?? ""));
            File.WriteAllText(path, builder.ToString(), new UTF8Encoding(false));
        }

        private static DiskInfo FindDisk(OfflineJob job)
        {
            var scan = DiskScanner.Scan(new ScanOptions { ProbeSpeed = false, ProbeWrite = false });
            foreach (var disk in scan.Disks)
            {
                if (disk.Number != job.DiskNumber) continue;
                if (!string.IsNullOrEmpty(job.DiskSerial) && !string.Equals(job.DiskSerial, disk.Serial, StringComparison.OrdinalIgnoreCase)) continue;
                if (job.DiskSize > 0 && disk.SizeBytes != job.DiskSize) continue;
                return disk;
            }
            return null;
        }

        private static PartitionInfo FindPartition(DiskInfo disk, int number)
        {
            foreach (var partition in disk.Partitions) if (partition.PartitionNumber == number) return partition;
            return null;
        }
    }
}
