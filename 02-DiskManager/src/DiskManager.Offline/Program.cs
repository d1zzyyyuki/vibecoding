using System.Text.Json;
using DiskManager.Core;
using DiskManager.Core.Engine;
using DiskManager.Core.Operations;

namespace DiskManager.Offline
{
    internal static class Program
    {
        private static int Main(string[] args)
        {
            if (args.Length == 0 || (args[0] != "validate" && args[0] != "plan" && args[0] != "run"))
            {
                Console.WriteLine("DiskManagerOffline validate --job job.json");
                Console.WriteLine("DiskManagerOffline plan --job job.json");
                Console.WriteLine("DiskManagerOffline run --job job.json [--journal path] [--allow-real]");
                Console.WriteLine("run 默认只允许虚拟磁盘；真实磁盘必须显式 --allow-real，且需要用户授权。");
                return 2;
            }
            var jobPath = GetArg(args, "--job");
            if (string.IsNullOrEmpty(jobPath) || !File.Exists(jobPath))
            {
                Console.WriteLine("job file not found");
                return 2;
            }
            try
            {
                if (args[0] == "run")
                {
                    var allowReal = false;
                    foreach (var arg in args) if (arg == "--allow-real") allowReal = true;
                    return OfflineExecutor.Run(jobPath, GetArg(args, "--journal"), allowReal);
                }
                return args[0] == "plan" ? PrintPlan(jobPath) : Validate(jobPath);
            }
            catch (Exception ex)
            {
                Console.WriteLine("ERROR: " + ex.Message);
                return 1;
            }
        }

        private static int Validate(string jobPath)
        {
            var job = OfflineJob.Load(jobPath);
            var disk = FindDisk(job);
            if (disk == null) { Console.WriteLine("FAIL disk not found"); return 1; }
            var error = ValidateLayout(job, disk, out var plan);
            if (error != null) { Console.WriteLine("FAIL " + error); return 1; }
            Console.WriteLine("OK " + plan);
            return 0;
        }

        private static int PrintPlan(string jobPath)
        {
            var job = OfflineJob.Load(jobPath);
            var disk = FindDisk(job);
            if (disk == null) { Console.WriteLine("FAIL disk not found"); return 1; }
            var error = ValidateLayout(job, disk, out var plan);
            if (error != null) { Console.WriteLine("FAIL " + error); return 1; }
            var system = FindPartition(disk, job.SystemPartition);
            Console.WriteLine("disk=" + disk.Number + " " + disk.Model + " " + disk.BusType);
            Console.WriteLine("system=" + system.PartitionNumber + " offset=" + system.OffsetBytes + " size=" + system.SizeBytes +
                              " -> size=" + (system.SizeBytes + job.GrowthBytes));
            long shrank = 0;
            foreach (var donor in job.Donors)
            {
                var part = FindPartition(disk, donor.Partition);
                if (part == null) { Console.WriteLine("FAIL donor missing " + donor.Partition); return 1; }
                shrank += donor.ShrinkBytes;
                Console.WriteLine("donor=" + part.PartitionNumber + " offset=" + part.OffsetBytes + " size=" + part.SizeBytes +
                                  " shrink=" + donor.ShrinkBytes + " newOffset=" + (part.OffsetBytes + job.GrowthBytes) +
                                  " newSize=" + (part.SizeBytes - donor.ShrinkBytes));
            }
            Console.WriteLine("shrinkTotal=" + shrank + " growth=" + job.GrowthBytes + " tailCheck=" + plan);
            return 0;
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

        private static string ValidateLayout(OfflineJob job, DiskInfo disk, out string plan)
        {
            plan = "ok";
            if (job.GrowthBytes <= 0) return "growth must be positive";
            if (job.SystemPartition <= 0) return "system partition missing";
            var system = FindPartition(disk, job.SystemPartition);
            if (system == null) return "system partition not found";
            if (!system.IsBasicData || !system.HasVolume) return "system partition is not a mounted basic volume";
            if (system.OffsetBytes != job.SystemOffset || system.SizeBytes != job.SystemSize) return "system partition layout changed";
            long shrink = 0;
            foreach (var donor in job.Donors)
            {
                if (donor.ShrinkBytes <= 0) return "donor shrink must be positive";
                var part = FindPartition(disk, donor.Partition);
                if (part == null) return "donor partition not found";
                if (!part.IsBasicData || !part.HasVolume) return "donor is not a mounted basic volume";
                if (part.OffsetBytes != donor.Offset || part.SizeBytes != donor.Size) return "donor layout changed";
                if (donor.ShrinkBytes >= part.SizeBytes) return "donor shrink too large";
                shrink += donor.ShrinkBytes;
            }
            var tail = disk.SizeBytes - 1024 * 1024;
            var finalEnd = system.OffsetBytes + system.SizeBytes + job.GrowthBytes;
            foreach (var donor in job.Donors)
            {
                var part = FindPartition(disk, donor.Partition);
                var end = part.OffsetBytes + job.GrowthBytes + (part.SizeBytes - donor.ShrinkBytes);
                if (end > tail) return "donor final end exceeds disk";
                if (end > finalEnd) finalEnd = end;
            }
            if (shrink + Math.Max(0, disk.SizeBytes - 1024 * 1024 - (system.OffsetBytes + system.SizeBytes + job.Donors.Sum(d => d.Size))) < job.GrowthBytes)
                return "not enough free tail/shrink for growth";
            plan = "finalEnd=" + finalEnd + " shrink=" + shrink;
            return null;
        }

        private static string GetArg(string[] args, string name)
        {
            for (var i = 0; i + 1 < args.Length; i++) if (args[i] == name) return args[i + 1];
            return null;
        }
    }

    internal sealed class OfflineJob
    {
        public int Version { get; set; }
        public int DiskNumber { get; set; }
        public string DiskSerial { get; set; }
        public long DiskSize { get; set; }
        public int SystemPartition { get; set; }
        public long SystemOffset { get; set; }
        public long SystemSize { get; set; }
        public long GrowthBytes { get; set; }
        public List<OfflineDonor> Donors { get; set; } = new List<OfflineDonor>();

        public static OfflineJob Load(string path)
        {
            using var doc = JsonDocument.Parse(File.ReadAllText(path));
            var root = doc.RootElement;
            var job = new OfflineJob
            {
                Version = root.TryGetProperty("version", out var v) ? v.GetInt32() : 0,
                DiskNumber = root.GetProperty("diskNumber").GetInt32(),
                DiskSerial = root.TryGetProperty("diskSerial", out var serial) ? serial.GetString() : null,
                DiskSize = root.GetProperty("diskSize").GetInt64(),
                SystemPartition = root.GetProperty("systemPartition").GetInt32(),
                SystemOffset = root.GetProperty("systemOffset").GetInt64(),
                SystemSize = root.GetProperty("systemSize").GetInt64(),
                GrowthBytes = root.GetProperty("growthBytes").GetInt64()
            };
            foreach (var donor in root.GetProperty("donors").EnumerateArray())
            {
                job.Donors.Add(new OfflineDonor
                {
                    Partition = donor.GetProperty("partition").GetInt32(),
                    Offset = donor.GetProperty("offset").GetInt64(),
                    Size = donor.GetProperty("size").GetInt64(),
                    ShrinkBytes = donor.GetProperty("shrinkBytes").GetInt64()
                });
            }
            if (job.Version != 1) throw new InvalidOperationException("unsupported job version");
            if (job.Donors.Count == 0) throw new InvalidOperationException("job has no donors");
            return job;
        }
    }

    internal sealed class OfflineDonor
    {
        public int Partition { get; set; }
        public long Offset { get; set; }
        public long Size { get; set; }
        public long ShrinkBytes { get; set; }
    }
}
