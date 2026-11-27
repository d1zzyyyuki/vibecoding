using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;
using DiskManager.Core;
using DiskManager.Core.Engine;
using DiskManager.Core.Json;
using DiskManager.Core.Operations;
using DiskManager.Core.Planning;

namespace DiskManager.Tests
{
    internal static class Program
    {
        private static int Main(string[] args)
        {
            if (args.Length > 0 && (args[0] == "scan" || args[0] == "selftest"))
            {
                return Scan(args);
            }
            if (args.Length > 0 && args[0] == "plan")
            {
                return Plan(args);
            }
            if (args.Length > 0 && args[0] == "engine-run")
            {
                return EngineRun(args);
            }
            if (args.Length > 0 && args[0] == "engine-resume")
            {
                return EngineRun(args);
            }
            if (args.Length > 0 && args[0] == "engine-rollback")
            {
                return EngineRollback(args);
            }
            if (args.Length > 0 && args[0] == "extend-test")
            {
                return ExtendTest(args);
            }
            if (args.Length > 0 && args[0].StartsWith("partition-", StringComparison.OrdinalIgnoreCase))
            {
                return PartitionOperation(args);
            }

            var checks = RunUnitTests();
            var failed = 0;
            foreach (var check in checks)
            {
                Console.WriteLine((check.Passed ? "PASS " : "FAIL ") + check.Name + (string.IsNullOrEmpty(check.Detail) ? "" : "  " + check.Detail));
                if (!check.Passed) failed++;
            }
            Console.WriteLine();
            Console.WriteLine(failed == 0 ? "ALL PASS (" + checks.Count + " checks)" : failed + " FAILED");
            return failed == 0 ? 0 : 1;
        }

        private static int Scan(string[] args)
        {
            var outPath = GetArg(args, "--out");
            var logPath = GetArg(args, "--log");
            var log = new StringBuilder();
            void L(string s)
            {
                Console.WriteLine(s);
                log.AppendLine(s);
            }

            L("DiskManager scanner starting; elevated=" + Elevation.IsElevated());
            var result = DiskScanner.Scan(new ScanOptions());
            L("durationMs=" + result.DurationMs + " disks=" + result.Disks.Count + " volumes=" + result.VolumeCount);
            foreach (var disk in result.Disks)
            {
                L("DISK " + disk.Number + " " + disk.Model + " bus=" + disk.BusType + " media=" + disk.MediaKind +
                    " size=" + Humanize.Bytes(disk.SizeBytes) + " style=" + disk.PartitionStyle + " health=" + disk.Health +
                    " system=" + disk.IsSystemDisk);
                if (disk.Speed != null)
                {
                    L("  speed success=" + disk.Speed.Success + " avg=" + disk.Speed.ThroughputMBps +
                        " peak=" + disk.Speed.PeakMBps + " elapsed=" + disk.Speed.ElapsedMs + "ms err=" + disk.Speed.Error);
                }
                foreach (var partition in disk.Partitions)
                {
                    L("  PART " + partition.PartitionNumber + " " + partition.DisplayLetter + " " + partition.TypeName +
                        " " + partition.FileSystem + " offset=" + partition.OffsetBytes + " size=" + Humanize.Bytes(partition.SizeBytes) +
                        " free=" + Humanize.Bytes(partition.FreeBytes) + " system=" + partition.IsSystem + " hidden=" + partition.IsHidden);
                }
            }
            foreach (var warning in result.Warnings) L("WARN " + warning);
            foreach (var error in result.Errors) L("ERROR " + error);

            if (!string.IsNullOrEmpty(outPath))
            {
                var checks = new List<CheckResult>
                {
                    new CheckResult { Name = "elevated", Passed = result.IsElevated, Detail = "管理员权限" },
                    new CheckResult { Name = "disks", Passed = result.Disks.Count > 0, Detail = result.Disks.Count.ToString(CultureInfo.InvariantCulture) + " 块磁盘" },
                    new CheckResult { Name = "speed", Passed = result.Disks.Exists(d => d.Speed != null && d.Speed.Success), Detail = "至少一块盘测速成功" }
                };
                var passed = checks.TrueForAll(c => c.Passed);
                var json = JsonReport.Build(result, checks, passed);
                File.WriteAllText(outPath, json, new UTF8Encoding(false));
                L("JSON -> " + outPath);
            }

            if (!string.IsNullOrEmpty(logPath)) File.WriteAllText(logPath, log.ToString(), new UTF8Encoding(false));
            return result.Disks.Count > 0 ? 0 : 1;
        }

        private static int Plan(string[] args)
        {
            var diskNumber = GetIntArg(args, "--disk", -1);
            var systemNumber = GetIntArg(args, "--system", -1);
            var dataNumber = GetIntArg(args, "--data", -1);
            var growthMb = GetIntArg(args, "--growth-mb", 0);
            if (diskNumber < 0 || systemNumber < 0 || dataNumber < 0 || growthMb <= 0)
            {
                Console.WriteLine("usage: plan --disk N --system N --data N --growth-mb N");
                return 2;
            }

            var scan = DiskScanner.Scan(new ScanOptions());
            DiskInfo disk = null;
            foreach (var candidate in scan.Disks)
            {
                if (candidate.Number == diskNumber) { disk = candidate; break; }
            }
            if (disk == null)
            {
                Console.WriteLine("disk not found: " + diskNumber);
                return 2;
            }

            var speed = disk.Speed != null && disk.Speed.Success ? disk.Speed.ThroughputMBps : 0;
            var plan = PartitionPlanner.Build(disk, new PlanRequest
            {
                DiskNumber = diskNumber,
                SystemPartitionNumber = systemNumber,
                DataPartitionNumber = dataNumber,
                GrowthBytes = growthMb * 1024L * 1024L
            }, speed);

            Console.WriteLine("disk " + disk.Number + " " + disk.Model + " style=" + disk.PartitionStyle + " speedMBps=" + speed);
            Console.WriteLine("valid=" + plan.IsValid + " summary=" + plan.Summary);
            Console.WriteLine("oldSystem=" + plan.OldSystemSizeBytes + " newSystem=" + plan.NewSystemSizeBytes +
                " oldDataStart=" + plan.OldDataStartBytes + " newDataStart=" + plan.NewDataStartBytes +
                " oldDataSize=" + plan.OldDataSizeBytes + " newDataSize=" + plan.NewDataSizeBytes +
                " shrink=" + plan.DataShrinkBytes + " tailGap=" + plan.TailGapBytes + " move=" + plan.DataMoveBytes +
                " estimateMs=" + plan.EstimatedMs);
            foreach (var error in plan.Errors) Console.WriteLine("ERROR " + error.Code + ": " + error.Message);
            foreach (var warning in plan.Warnings) Console.WriteLine("WARN " + warning);
            foreach (var step in plan.Steps)
            {
                Console.WriteLine("STEP " + step.Kind + " bytes=" + step.Bytes + " ms=" + step.EstimatedMs + " " + step.Title + " | " + step.Detail);
            }
            return plan.IsValid ? 0 : 1;
        }

        private static int EngineRun(string[] args)
        {
            var journal = GetArg(args, "--journal");
            if (string.IsNullOrEmpty(journal))
            {
                Console.WriteLine("usage: engine-run --disk N --system N --data N --growth-mb N --journal PATH [--interrupt-mb N] [--chunk-delay-ms N]");
                return 2;
            }
            var options = new EngineOptions
            {
                DiskNumber = GetIntArg(args, "--disk", -1),
                SystemPartitionNumber = GetIntArg(args, "--system", -1),
                DataPartitionNumber = GetIntArg(args, "--data", -1),
                GrowthBytes = GetIntArg(args, "--growth-mb", 0) * 1024L * 1024L,
                JournalPath = journal,
                InterruptAfterBytes = GetIntArg(args, "--interrupt-mb", 0) * 1024L * 1024L,
                ChunkDelayMs = GetIntArg(args, "--chunk-delay-ms", 0),
                AllowRealDisk = false,
                FailAfterGptStartUpdate = HasArg(args, "--fail-gpt-start"),
                FailAfterGptUpdated = HasArg(args, "--fail-gpt-updated")
            };

            Console.WriteLine("engine-run journal=" + journal);
            var result = File.Exists(journal) ? OnlineResizeEngine.Resume(options) : OnlineResizeEngine.Execute(options);
            PrintEngine(result);
            return result.ExitCode;
        }

        private static int EngineRollback(string[] args)
        {
            var journal = GetArg(args, "--journal");
            if (string.IsNullOrEmpty(journal))
            {
                Console.WriteLine("usage: engine-rollback --journal PATH");
                return 2;
            }
            Console.WriteLine("engine-rollback journal=" + journal);
            var result = OnlineResizeEngine.Rollback(new EngineOptions { JournalPath = journal });
            PrintEngine(result);
            return result.ExitCode;
        }

        private static int ExtendTest(string[] args)
        {
            var letter = GetArg(args, "--letter") ?? "V";
            var sizeGb = GetIntArg(args, "--size-gb", 0);
            var sizeMb = GetIntArg(args, "--size-mb", 0);
            var sizeBytes = sizeGb > 0 ? sizeGb * 1024L * 1024L * 1024L : sizeMb * 1024L * 1024L;
            if (sizeBytes <= 0) { Console.WriteLine("need --size-gb or --size-mb"); return 2; }
            var scan = DiskScanner.Scan(new ScanOptions { ProbeSpeed = false });
            foreach (var disk in scan.Disks)
            {
                foreach (var partition in disk.Partitions)
                {
                    if (!string.Equals(partition.DriveLetter, letter, StringComparison.OrdinalIgnoreCase)) continue;
                    Console.WriteLine("volume guid=" + partition.VolumeGuid + " partitionSize=" + partition.SizeBytes + " volumeTotal=" + partition.VolumeTotalBytes + " free=" + partition.FreeBytes);
                    var ok = VolumeControl.ExtendVolume(partition.VolumeGuid, partition.DriveLetter, sizeBytes, 512, out var error);
                    Console.WriteLine("extend size=" + sizeBytes + " ok=" + ok + " error=" + error);
                    return ok ? 0 : 1;
                }
            }
            Console.WriteLine("volume not found: " + letter);
            return 2;
        }

        private static int PartitionOperation(string[] args)
        {
            var operation = args[0].Substring("partition-".Length).ToLowerInvariant();
            var diskNumber = GetIntArg(args, "--disk", -1);
            if (diskNumber < 0) { Console.WriteLine("need --disk N"); return 2; }
            var scan = DiskScanner.Scan(new ScanOptions { ProbeSpeed = false });
            DiskInfo disk = null;
            foreach (var candidate in scan.Disks) if (candidate.Number == diskNumber) { disk = candidate; break; }
            if (disk == null) { Console.WriteLine("disk not found: " + diskNumber); return 2; }

            var log = GetArg(args, "--log");
            var sizeMb = GetIntArg(args, "--size-mb", 0);
            var letter = GetArg(args, "--letter");
            var label = GetArg(args, "--label") ?? "DATA";
            var fs = GetArg(args, "--fs") ?? "NTFS";
            var partitionNumber = GetIntArg(args, "--partition", -1);
            PartitionInfo partition = null;
            foreach (var candidate in disk.Partitions) if (candidate.PartitionNumber == partitionNumber) { partition = candidate; break; }

            PartitionOperationResult result;
            if (operation == "create")
            {
                result = PartitionOperations.Create(disk, sizeMb * 1024L * 1024L, fs, label, letter, false, log);
            }
            else if (operation == "delete")
            {
                result = PartitionOperations.Delete(disk, partition, false, log);
            }
            else if (operation == "format")
            {
                result = PartitionOperations.Format(disk, partition, fs, label, false, log);
            }
            else if (operation == "split")
            {
                result = PartitionOperations.Split(disk, partition, sizeMb * 1024L * 1024L, fs, label, letter, false, log);
            }
            else
            {
                Console.WriteLine("unknown partition operation: " + operation);
                return 2;
            }

            Console.WriteLine("op=" + operation + " success=" + result.Success + " exit=" + result.ExitCode + " message=" + result.Message);
            Console.WriteLine("log=" + result.LogPath);
            if (!string.IsNullOrEmpty(result.Output)) Console.WriteLine(result.Output.Trim());
            return result.Success ? 0 : 1;
        }

        private static void PrintEngine(EngineResult result)
        {
            Console.WriteLine("success=" + result.Success + " exit=" + result.ExitCode + " message=" + result.Message);
            if (result.Plan != null)
            {
                Console.WriteLine("plan_valid=" + result.Plan.IsValid + " summary=" + result.Plan.Summary);
                Console.WriteLine("plan_newSystem=" + result.Plan.NewSystemSizeBytes + " plan_newDataStart=" + result.Plan.NewDataStartBytes);
            }
            if (result.Journal != null)
            {
                var journal = result.Journal;
                Console.WriteLine("journal_phase=" + journal.Phase + " progress=" + journal.ProgressSourceOffset +
                    " dataOffset=" + journal.DataOffset + " dataSize=" + journal.DataSize +
                    " growth=" + journal.Growth + " newDataStart=" + journal.NewDataStart);
            }
        }

        private static List<CheckResult> RunUnitTests()
        {
            var checks = new List<CheckResult>();
            void Check(string name, bool condition, string detail = null)
            {
                checks.Add(new CheckResult { Name = name, Passed = condition, Detail = detail });
            }

            Check("bytes-zero", Humanize.Bytes(0) == "0 B", Humanize.Bytes(0));
            Check("bytes-gb", Humanize.Bytes(1024L * 1024 * 1024) == "1.0 GB", Humanize.Bytes(1024L * 1024 * 1024));
            Check("bytes-tb", Humanize.Bytes(1024L * 1024 * 1024 * 1024) == "1.0 TB", Humanize.Bytes(1024L * 1024 * 1024 * 1024));
            Check("bytes-disk", Humanize.Bytes(1024209543168) == "953.9 GB", Humanize.Bytes(1024209543168));
            Check("gpt-efi", PartitionTypes.NameOf(PartitionTypes.EfiSystem) == "EFI 系统分区", PartitionTypes.NameOf(PartitionTypes.EfiSystem));
            Check("gpt-basic", PartitionTypes.NameOf(PartitionTypes.BasicData) == "基本数据", PartitionTypes.NameOf(PartitionTypes.BasicData));
            Check("gpt-unknown", PartitionTypes.NameOf("00000000-0000-0000-0000-000000000000") == null, "unknown -> null");
            Check("mbr-ntfs", PartitionTypes.MbrName(0x07) == "NTFS/exFAT", PartitionTypes.MbrName(0x07));
            Check("speed-format", Humanize.Speed(2493.1) == "2.49 GB/s", Humanize.Speed(2493.1));
            Check("duration", Humanize.Duration(TimeSpan.FromSeconds(125)) == "2 分 05 秒", Humanize.Duration(TimeSpan.FromSeconds(125)));
            Check("move-estimate", Humanize.MoveEstimate(1024L * 1024 * 1024 * 1024, 2000) == "13 分 26 秒", Humanize.MoveEstimate(1024L * 1024 * 1024 * 1024, 2000));
            Check("space-low", SpaceHealth.IsLowFreeSpace(5, 100), "5/100");
            Check("space-threshold", !SpaceHealth.IsLowFreeSpace(10, 100), "10/100 boundary");
            Check("space-warning", SpaceHealth.IsWarningFreeSpace(15, 100), "15/100");
            Check("space-empty", !SpaceHealth.IsLowFreeSpace(0, 0), "zero total");

            const long MB = 1024L * 1024L;
            var tailDisk = MakePlanDisk(9216, 16, 3072, 3088, 4096, 4096);
            const long oneGb = 1024 * MB;
            var tailPlan = PartitionPlanner.Build(tailDisk, new PlanRequest
            {
                DiskNumber = 2, SystemPartitionNumber = 2, DataPartitionNumber = 3, GrowthBytes = oneGb
            }, 2000);
            Check("plan-tail-valid", tailPlan.IsValid, tailPlan.Summary);
            Check("plan-tail-no-shrink", tailPlan.DataShrinkBytes == 0, tailPlan.DataShrinkBytes.ToString());
            Check("plan-tail-new-start", tailPlan.NewDataStartBytes == 4112 * MB, tailPlan.NewDataStartBytes.ToString());
            Check("plan-tail-new-system", tailPlan.NewSystemSizeBytes == 4096 * MB, tailPlan.NewSystemSizeBytes.ToString());
            Check("plan-tail-steps", tailPlan.Steps.Count == 5, tailPlan.Steps.Count.ToString());
            Check("plan-tail-estimate", tailPlan.EstimatedMs > 0, tailPlan.EstimatedMs.ToString());

            var noTailDisk = MakePlanDisk(8192, 16, 2048, 2064, 6000, 5980);
            var noTailPlan = PartitionPlanner.Build(noTailDisk, new PlanRequest
            {
                DiskNumber = 3, SystemPartitionNumber = 2, DataPartitionNumber = 3, GrowthBytes = 512 * MB
            }, 2000);
            Check("plan-notail-valid", noTailPlan.IsValid, noTailPlan.Summary);
            Check("plan-notail-shrink", noTailPlan.DataShrinkBytes == 385 * MB, noTailPlan.DataShrinkBytes.ToString());
            Check("plan-notail-new-start", noTailPlan.NewDataStartBytes == 2576 * MB, noTailPlan.NewDataStartBytes.ToString());
            Check("plan-notail-end", noTailPlan.NewDataStartBytes + noTailPlan.NewDataSizeBytes == 8191 * MB, "must stop before backup GPT");
            Check("plan-notail-steps", noTailPlan.Steps.Count == 6, noTailPlan.Steps.Count.ToString());

            var nonAdjacent = MakePlanDisk(9216, 16, 2048, 4096, 4096, 4096);
            var nonAdjacentPlan = PartitionPlanner.Build(nonAdjacent, new PlanRequest { DiskNumber = 4, SystemPartitionNumber = 2, DataPartitionNumber = 3, GrowthBytes = oneGb }, 2000);
            Check("plan-reject-gap", HasError(nonAdjacentPlan, "not-adjacent"), nonAdjacentPlan.Errors.Count.ToString());

            var misaligned = MakePlanDisk(9216, 16, 3072, 3088, 4096, 4096);
            var misalignedPlan = PartitionPlanner.Build(misaligned, new PlanRequest { DiskNumber = 5, SystemPartitionNumber = 2, DataPartitionNumber = 3, GrowthBytes = oneGb + 1 }, 2000);
            Check("plan-reject-align", HasError(misalignedPlan, "growth-misaligned"), misalignedPlan.Errors.Count.ToString());

            var bitlockerPlan = PartitionPlanner.Build(tailDisk, new PlanRequest
            {
                DiskNumber = 2, SystemPartitionNumber = 2, DataPartitionNumber = 3, GrowthBytes = oneGb, BitLockerDetected = true
            }, 2000);
            Check("plan-reject-bitlocker", HasError(bitlockerPlan, "bitlocker"), bitlockerPlan.Errors.Count.ToString());

            var mbrDisk = MakePlanDisk(9216, 16, 3072, 3088, 4096, 4096, "MBR");
            var mbrPlan = PartitionPlanner.Build(mbrDisk, new PlanRequest { DiskNumber = 6, SystemPartitionNumber = 2, DataPartitionNumber = 3, GrowthBytes = oneGb }, 2000);
            Check("plan-reject-mbr", HasError(mbrPlan, "not-gpt"), mbrPlan.Errors.Count.ToString());

            var fullDisk = MakePlanDisk(4096, 16, 2048, 2064, 1024, 20);
            var fullPlan = PartitionPlanner.Build(fullDisk, new PlanRequest { DiskNumber = 7, SystemPartitionNumber = 2, DataPartitionNumber = 3, GrowthBytes = 256 * MB }, 2000);
            Check("plan-reject-used", HasError(fullPlan, "data-too-small"), fullPlan.Errors.Count.ToString());

            var missingPlan = PartitionPlanner.Build(tailDisk, new PlanRequest { DiskNumber = 2, SystemPartitionNumber = 2, DataPartitionNumber = 9, GrowthBytes = oneGb }, 2000);
            Check("plan-reject-missing", HasError(missingPlan, "data-missing"), missingPlan.Errors.Count.ToString());


            var json = JsonReport.Build(new ScanResult
            {
                MachineName = "MACHINE",
                OsDescription = "Windows",
                OsArchitecture = "X64",
                IsElevated = true,
                StartedAtUtc = new DateTime(2026, 1, 2, 3, 4, 5, DateTimeKind.Utc),
                Disks = new List<DiskInfo>
                {
                    new DiskInfo
                    {
                        Number = 0, Model = "Test \"Disk\"", BusType = "NVMe", MediaKind = "NVMe SSD",
                        SizeBytes = 1024, Partitions = new List<PartitionInfo>
                        {
                            new PartitionInfo { PartitionNumber = 1, SizeBytes = 1024, DriveLetter = "C", FileSystem = "NTFS", IsSystem = true }
                        }
                    }
                }
            }, new List<CheckResult> { new CheckResult { Name = "one", Passed = true, Detail = "ok" } }, true);
            Check("json-has-disks", json.Contains("\"disks\"") && json.Contains("\"passed\": true"), "json structure");
            Check("json-escapes-quote", json.Contains("Test \\\"Disk\\\""), "quote escaped");

            var expandAlloc = ExpandCPlanner.Allocate(3L * 1024 * MB,
                new List<long> { 512 * MB, 1024 * MB, 4096 * MB });
            Check("expand-alloc-waterfill",
                expandAlloc[0] == 512 * MB && expandAlloc[1] == 1024 * MB && expandAlloc[2] == 1536 * MB,
                expandAlloc[0] / MB + "/" + expandAlloc[1] / MB + "/" + expandAlloc[2] / MB);
            List<long> expandRealloc;
            ExpandCPlanner.Reallocate(3L * 1024 * MB, new List<long> { 4096 * MB, 4096 * MB, 4096 * MB }, 1, 512 * MB, out expandRealloc);
            Check("expand-alloc-fixed", expandRealloc[0] == 1280 * MB && expandRealloc[1] == 512 * MB && expandRealloc[2] == 1280 * MB,
                expandRealloc[0] / MB + "/" + expandRealloc[1] / MB + "/" + expandRealloc[2] / MB);
            var expandDisk = MakePlanDisk(9216, 16, 2048, 2064, 2048, 1024);
            var expandPlan = ExpandCPlanner.Build(expandDisk, 2);
            Check("expand-max", expandPlan.Valid && expandPlan.MaxExpandableBytes == 1024 * MB,
                expandPlan.MaxExpandableBytes / MB + " MB");

            var gptLayout = new byte[48 + 128 * 144];
            BitConverter.GetBytes(1).CopyTo(gptLayout, 0);
            BitConverter.GetBytes(3).CopyTo(gptLayout, 4);
            Action<int, int, long, long> entry = (index, number, start, length) =>
            {
                var offset = 48 + index * 144;
                BitConverter.GetBytes(start).CopyTo(gptLayout, offset + 8);
                BitConverter.GetBytes(length).CopyTo(gptLayout, offset + 16);
                BitConverter.GetBytes(number).CopyTo(gptLayout, offset + 24);
            };
            entry(0, 2, 16 * MB, 2048 * MB);
            entry(1, 3, 2064 * MB, 2048 * MB);
            entry(2, 4, 4112 * MB, 2048 * MB);
            GptEditor.PatchMulti(gptLayout, 2, oneGb, new Dictionary<int, long> { { 3, 2064 * MB }, { 4, 4112 * MB } }, false);
            Check("gpt-patch-multi",
                BitConverter.ToInt64(gptLayout, 48 + 1 * 144 + 8) == 3088 * MB &&
                BitConverter.ToInt64(gptLayout, 48 + 2 * 144 + 8) == 5136 * MB &&
                BitConverter.ToInt64(gptLayout, 48 + 0 * 144 + 16) == 2048 * MB,
                "donor starts shifted, system length left for GrowPartition");

            return checks;
        }

        private static DiskInfo MakePlanDisk(int totalMb, int systemOffsetMb, int systemSizeMb, int dataOffsetMb, int dataSizeMb, int dataFreeMb, string style = "GPT")
        {
            const long MB = 1024L * 1024L;
            var system = new PartitionInfo
            {
                DiskNumber = 0,
                PartitionNumber = 2,
                OffsetBytes = systemOffsetMb * MB,
                SizeBytes = systemSizeMb * MB,
                PartitionStyle = style,
                TypeName = "基本数据",
                IsBasicData = true,
                IsSystem = true,
                HasVolume = true,
                DriveLetter = "V",
                FileSystem = "NTFS",
                VolumeTotalBytes = systemSizeMb * MB,
                FreeBytes = systemSizeMb * MB / 2
            };
            var data = new PartitionInfo
            {
                DiskNumber = 0,
                PartitionNumber = 3,
                OffsetBytes = dataOffsetMb * MB,
                SizeBytes = dataSizeMb * MB,
                PartitionStyle = style,
                TypeName = "基本数据",
                IsBasicData = true,
                HasVolume = true,
                DriveLetter = "W",
                FileSystem = "NTFS",
                VolumeTotalBytes = dataSizeMb * MB,
                FreeBytes = dataFreeMb * MB
            };
            var disk = new DiskInfo
            {
                Number = 0,
                Model = "Synthetic",
                PartitionStyle = style,
                SizeBytes = totalMb * MB,
                IsSystemDisk = true
            };
            disk.Partitions.Add(system);
            disk.Partitions.Add(data);
            return disk;
        }

        private static bool HasError(PlanResult plan, string code)
        {
            foreach (var error in plan.Errors)
            {
                if (error.Code == code) return true;
            }
            return false;
        }

        private static int GetIntArg(string[] args, string name, int fallback)
        {
            var value = GetArg(args, name);
            int parsed;
            return !string.IsNullOrEmpty(value) && int.TryParse(value, out parsed) ? parsed : fallback;
        }

        private static bool HasArg(string[] args, string name)
        {
            return Array.IndexOf(args, name) >= 0;
        }

        private static string GetArg(string[] args, string name)
        {
            for (var i = 0; i < args.Length - 1; i++)
            {
                if (string.Equals(args[i], name, StringComparison.OrdinalIgnoreCase)) return args[i + 1];
            }
            return null;
        }
    }
}
