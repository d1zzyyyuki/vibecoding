using System;
using System.IO;
using System.Threading;
using DiskManager.Core.Engine;
using DiskManager.Core.Native;
using DiskManager.Core.Planning;

namespace DiskManager.Core.Operations
{
    public sealed class EngineOptions
    {
        public int DiskNumber;
        public int SystemPartitionNumber;
        public int DataPartitionNumber;
        public long GrowthBytes;
        public string JournalPath;
        public bool AllowRealDisk;
        public long InterruptAfterBytes;
        public int ChunkBytes = BlockMover.DefaultChunkBytes;
        public int ChunkDelayMs;
        public bool FailAfterGptStartUpdate;
        public bool FailAfterGptUpdated;
        public Action<long, long> Progress;
    }

    public sealed class EngineResult
    {
        public bool Success;
        public int ExitCode;
        public string Message;
        public OperationJournal Journal;
        public PlanResult Plan;
    }

    public static class OnlineResizeEngine
    {
        public static EngineResult Execute(EngineOptions options)
        {
            var result = new EngineResult { ExitCode = 2 };
            if (options == null || string.IsNullOrEmpty(options.JournalPath))
            {
                result.Message = "journal path is required";
                return result;
            }
            try
            {
                if (File.Exists(options.JournalPath)) return Resume(options);

                var scan = DiskScanner.Scan(new ScanOptions());
                DiskInfo disk = null;
                foreach (var candidate in scan.Disks) if (candidate.Number == options.DiskNumber) { disk = candidate; break; }
                if (disk == null) { result.Message = "disk not found: " + options.DiskNumber; return result; }
                if (!options.AllowRealDisk && disk.BusType != "FileBackedVirtual")
                {
                    result.Message = "this build refuses real disks; only virtual test disks are allowed";
                    return result;
                }

                var speed = disk.Speed != null && disk.Speed.Success ? disk.Speed.ThroughputMBps : 0;
                var plan = PartitionPlanner.Build(disk, new PlanRequest
                {
                    DiskNumber = options.DiskNumber,
                    SystemPartitionNumber = options.SystemPartitionNumber,
                    DataPartitionNumber = options.DataPartitionNumber,
                    GrowthBytes = options.GrowthBytes
                }, speed);
                result.Plan = plan;
                if (!plan.IsValid)
                {
                    result.Message = "plan rejected: " + (plan.Errors.Count > 0 ? plan.Errors[0].Message : "unknown");
                    return result;
                }
                if (string.IsNullOrEmpty(plan.DataLabel) || string.IsNullOrEmpty(plan.SystemLabel))
                {
                    result.Message = "target volume is missing a drive letter";
                    return result;
                }

                var system = FindPartition(disk, options.SystemPartitionNumber);
                var data = FindPartition(disk, options.DataPartitionNumber);
                if (system == null || data == null || string.IsNullOrEmpty(data.VolumeGuid) || string.IsNullOrEmpty(system.VolumeGuid))
                {
                    result.Message = "target partition volume GUID is missing";
                    return result;
                }

                var original = GptEditor.ReadLayout(disk.Number, out var layoutError);
                if (original == null) { result.Message = layoutError; return result; }

                var journal = OperationJournal.Create(disk.Number, system.PartitionNumber, data.PartitionNumber,
                    options.GrowthBytes, data.OffsetBytes, data.SizeBytes);
                journal.SystemGptId = system.GptTypeId;
                journal.DataGptId = data.GptTypeId;
                journal.SystemVolumeGuid = system.VolumeGuid;
                journal.DataVolumeGuid = data.VolumeGuid;
                journal.SystemDriveLetter = system.DriveLetter;
                journal.DataDriveLetter = data.DriveLetter;
                journal.DiskModel = disk.Model;
                journal.DiskSize = disk.SizeBytes;
                journal.LogicalSectorSize = disk.LogicalSectorSize > 0 ? disk.LogicalSectorSize : 512;
                journal.DataShrinkBytes = plan.DataShrinkBytes;
                journal.SystemOffset = system.OffsetBytes;
                journal.SystemSize = system.SizeBytes;
                journal.NewSystemSize = system.SizeBytes + options.GrowthBytes;
                var directory = Path.GetDirectoryName(Path.GetFullPath(options.JournalPath));
                if (!string.IsNullOrEmpty(directory)) Directory.CreateDirectory(directory);
                OperationJournal.SaveGpt(options.JournalPath, original);
                journal.Save(options.JournalPath);
                result.Journal = journal;

                if (plan.DataShrinkBytes > 0)
                {
                    journal.Phase = OperationPhase.Shrinking.ToString();
                    journal.Save(options.JournalPath);
                    string shrinkError, shrinkOutput;
                    if (!VolumeControl.ShrinkWithDiskPart(data.DriveLetter, plan.DataShrinkBytes, out shrinkError, out shrinkOutput))
                    {
                        journal.LastError = shrinkError;
                        journal.Phase = OperationPhase.Failed.ToString();
                        journal.Save(options.JournalPath);
                        result.Message = shrinkError + (string.IsNullOrEmpty(shrinkOutput) ? "" : " | " + shrinkOutput.Trim());
                        return result;
                    }

                    var afterScan = DiskScanner.Scan(new ScanOptions { ProbeSpeed = false });
                    DiskInfo afterDisk = null;
                    foreach (var candidate in afterScan.Disks) if (candidate.Number == disk.Number) { afterDisk = candidate; break; }
                    var afterData = afterDisk == null ? null : FindPartition(afterDisk, options.DataPartitionNumber);
                    if (afterDisk == null || afterData == null)
                    {
                        journal.LastError = "收缩后重新扫描失败";
                        journal.Phase = OperationPhase.Failed.ToString();
                        journal.Save(options.JournalPath);
                        result.Message = journal.LastError;
                        return result;
                    }
                    if (afterData.SizeBytes >= data.SizeBytes)
                    {
                        journal.LastError = "diskpart 报告成功但数据分区没有收缩";
                        journal.Phase = OperationPhase.Failed.ToString();
                        journal.Save(options.JournalPath);
                        result.Message = journal.LastError;
                        return result;
                    }

                    var newDataSize = afterData.SizeBytes;
                    var nextStart = afterDisk.SizeBytes - 1024L * 1024L;
                    foreach (var partition in afterDisk.Partitions)
                    {
                        var end = afterData.OffsetBytes + newDataSize;
                        if (partition.OffsetBytes >= end && partition.OffsetBytes < nextStart) nextStart = partition.OffsetBytes;
                    }
                    if (afterData.OffsetBytes + options.GrowthBytes + newDataSize > nextStart)
                    {
                        journal.LastError = "收缩后仍没有足够空间完成右移";
                        journal.Phase = OperationPhase.Failed.ToString();
                        journal.Save(options.JournalPath);
                        result.Message = journal.LastError;
                        return result;
                    }

                    data = afterData;
                    journal.DataSize = newDataSize;
                    journal.ProgressSourceOffset = afterData.OffsetBytes + newDataSize;
                    journal.DataVolumeGuid = afterData.VolumeGuid;
                    journal.DataDriveLetter = afterData.DriveLetter;
                    journal.LastError = null;
                    journal.Phase = OperationPhase.Prepared.ToString();
                    journal.Save(options.JournalPath);
                }

                var locked = VolumeControl.LockAndDismount(data.VolumeGuid, data.DriveLetter, out var lockError);
                if (locked == null)
                {
                    journal.LastError = lockError;
                    journal.Phase = OperationPhase.Failed.ToString();
                    journal.Save(options.JournalPath);
                    result.Message = lockError;
                    return result;
                }

                try
                {
                    journal.Phase = OperationPhase.DataLocked.ToString();
                    journal.Save(options.JournalPath);
                    journal.Phase = OperationPhase.Moving.ToString();
                    journal.Save(options.JournalPath);

                    try
                    {
                        MoveFromJournal(options, journal, result);
                    }
                    catch (OperationInterruptedException ex)
                    {
                        journal.LastError = ex.Message;
                        journal.Save(options.JournalPath);
                        result.Success = false;
                        result.ExitCode = 3;
                        result.Message = ex.Message;
                        return result;
                    }

                    journal.Phase = OperationPhase.Moved.ToString();
                    journal.ProgressSourceOffset = journal.DataOffset;
                    journal.Save(options.JournalPath);
                }
                finally
                {
                    locked.Dispose();
                }

                return FinalizeOperation(options, journal, original, result);
            }
            catch (Exception ex)
            {
                result.Success = false;
                result.ExitCode = 2;
                result.Message = ex.GetType().Name + ": " + ex.Message;
                return result;
            }
        }

        public static EngineResult Resume(EngineOptions options)
        {
            var result = new EngineResult { ExitCode = 2 };
            if (options == null || string.IsNullOrEmpty(options.JournalPath) || !File.Exists(options.JournalPath))
            {
                result.Message = "journal not found";
                return result;
            }
            try
            {
                var journal = OperationJournal.Load(options.JournalPath);
                result.Journal = journal;
                var phase = ParsePhase(journal.Phase);
                if (phase == OperationPhase.Completed || phase == OperationPhase.RolledBack)
                {
                    result.Success = true; result.ExitCode = 0; result.Message = "operation already " + journal.Phase;
                    return result;
                }
                if (phase == OperationPhase.Failed)
                {
                    result.Message = "operation failed: " + journal.LastError;
                    return result;
                }

                var original = OperationJournal.LoadGpt(options.JournalPath);
                if (original == null) { result.Message = "GPT backup missing"; return result; }

                if (phase == OperationPhase.Shrinking)
                {
                    result.Message = "收缩过程中断：无法安全判断卷状态，请人工检查后再处理";
                    return result;
                }
                if (phase == OperationPhase.Prepared || phase == OperationPhase.DataLocked || phase == OperationPhase.Moving)
                {
                    var locked = VolumeControl.LockAndDismount(journal.DataVolumeGuid, journal.DataDriveLetter, out var lockError);
                    if (locked == null) { result.Message = lockError; return result; }
                    try
                    {
                        if (phase != OperationPhase.Moving && journal.ProgressSourceOffset <= 0)
                        {
                            journal.ProgressSourceOffset = journal.DataOffset + journal.DataSize;
                        }
                        journal.Phase = OperationPhase.Moving.ToString();
                        journal.Save(options.JournalPath);
                        try
                        {
                            MoveFromJournal(options, journal, result);
                        }
                        catch (OperationInterruptedException ex)
                        {
                            journal.LastError = ex.Message;
                            journal.Save(options.JournalPath);
                            result.Success = false;
                            result.ExitCode = 3;
                            result.Message = ex.Message;
                            return result;
                        }
                        journal.Phase = OperationPhase.Moved.ToString();
                        journal.ProgressSourceOffset = journal.DataOffset;
                        journal.Save(options.JournalPath);
                    }
                    finally { locked.Dispose(); }
                }

                return FinalizeOperation(options, journal, original, result);
            }
            catch (Exception ex)
            {
                result.Message = ex.GetType().Name + ": " + ex.Message;
                return result;
            }
        }

        public static EngineResult Rollback(EngineOptions options)
        {
            var result = new EngineResult { ExitCode = 2 };
            try
            {
                var journal = OperationJournal.Load(options.JournalPath);
                result.Journal = journal;
                var phase = ParsePhase(journal.Phase);
                if (phase == OperationPhase.RolledBack || phase == OperationPhase.Prepared)
                {
                    result.Success = phase == OperationPhase.RolledBack; result.ExitCode = result.Success ? 0 : 2;
                    result.Message = "nothing to roll back";
                    return result;
                }
                if (phase == OperationPhase.Completed)
                {
                    result.Message = "operation already completed; rollback is not enabled";
                    return result;
                }
                if (phase == OperationPhase.GptUpdated)
                {
                    // The target partition was grown but the filesystem was not extended yet.
                    // Shrink the partition back before restoring the original GPT.
                }
                if (journal.DataShrinkBytes > 0)
                {
                    result.Message = "rollback after data shrink is not enabled in M2 test engine";
                    return result;
                }
                if (phase != OperationPhase.Moving && phase != OperationPhase.Moved && phase != OperationPhase.DataLocked && phase != OperationPhase.GptDataStartUpdated && phase != OperationPhase.GptUpdated && phase != OperationPhase.RollingBack)
                {
                    result.Message = "cannot roll back phase " + journal.Phase;
                    return result;
                }

                var original = OperationJournal.LoadGpt(options.JournalPath);
                if (original == null) { result.Message = "GPT backup missing"; return result; }
                var sourceEnd = journal.DataOffset + journal.DataSize;
                if (journal.ProgressSourceOffset <= 0 || journal.ProgressSourceOffset > sourceEnd)
                {
                    journal.ProgressSourceOffset = sourceEnd;
                }

                LockedVolume targetLocked = null;
                LockedVolume locked = null;
                try
                {
                    if (phase == OperationPhase.GptUpdated || phase == OperationPhase.RollingBack)
                    {
                        var current = GptEditor.ReadLayout(journal.DiskNumber, out var layoutError);
                        if (current == null) { result.Message = layoutError; return result; }
                        var currentSystemSize = GptEditor.GetPartitionLength(current, journal.SystemPartitionNumber);
                        if (currentSystemSize > journal.SystemSize)
                        {
                            targetLocked = VolumeControl.LockAndDismount(journal.SystemVolumeGuid, journal.SystemDriveLetter, out var targetLockError);
                            if (targetLocked == null)
                            {
                                result.Message = "无法锁定目标卷，不能回滚已扩大的目标分区：" + targetLockError;
                                return result;
                            }
                            if (!GptEditor.GrowPartition(journal.DiskNumber, journal.SystemPartitionNumber, -(currentSystemSize - journal.SystemSize), out var shrinkError))
                            {
                                result.Message = shrinkError;
                                return result;
                            }
                            GptEditor.RefreshDiskProperties(journal.DiskNumber);
                        }
                    }

                    locked = VolumeControl.LockAndDismount(journal.DataVolumeGuid, journal.DataDriveLetter, out var lockError);
                    if (locked == null)
                    {
                        // A crashed process may leave the volume already dismounted; raw copy is still safe.
                        result.Message = "lock warning: " + lockError;
                    }
                    journal.Phase = OperationPhase.RollingBack.ToString();
                    journal.Save(options.JournalPath);
                    BlockMover.CopyBack(journal.DiskNumber, journal.DataOffset, journal.ProgressSourceOffset, sourceEnd, journal.Growth, null, options.ChunkBytes);
                    GptEditor.RefreshDiskProperties(journal.DiskNumber);
                    if (!GptEditor.RestoreLayout(journal.DiskNumber, original, out var restoreError))
                    {
                        result.Message = restoreError;
                        return result;
                    }
                    GptEditor.RefreshDiskProperties(journal.DiskNumber);
                    VolumeControl.Remount(journal.SystemVolumeGuid, journal.SystemDriveLetter, out _);
                    VolumeControl.Remount(journal.DataVolumeGuid, journal.DataDriveLetter, out _);
                    VolumeControl.RestoreDriveLetter(journal.DataVolumeGuid, journal.DataDriveLetter, out _);
                    VolumeControl.RestoreDriveLetter(journal.SystemVolumeGuid, journal.SystemDriveLetter, out _);
                }
                finally
                {
                    if (locked != null) locked.Dispose();
                    if (targetLocked != null) targetLocked.Dispose();
                }

                journal.Phase = OperationPhase.RolledBack.ToString();
                journal.LastError = null;
                journal.Save(options.JournalPath);
                result.Success = true;
                result.ExitCode = 0;
                result.Message = "rolled back";
                return result;
            }
            catch (Exception ex)
            {
                result.Message = ex.GetType().Name + ": " + ex.Message;
                return result;
            }
        }

        private static EngineResult FinalizeOperation(EngineOptions options, OperationJournal journal, byte[] original, EngineResult result)
        {
            var journalPath = options.JournalPath;
            var phase = ParsePhase(journal.Phase);
            if (phase == OperationPhase.Moved)
            {
                var current = GptEditor.ReadLayout(journal.DiskNumber, out var readError);
                if (current == null)
                {
                    result.Message = readError;
                    return result;
                }
                var patched = (byte[])current.Clone();
                try
                {
                    GptEditor.PatchDataStart(patched, journal.DataPartitionNumber, journal.Growth, journal.DataOffset);
                }
                catch (Exception ex)
                {
                    result.Message = "patch GPT failed: " + ex.Message;
                    return result;
                }
                if (!GptEditor.WriteLayout(journal.DiskNumber, patched, out var writeError))
                {
                    result.Message = writeError;
                    journal.LastError = writeError;
                    journal.Phase = OperationPhase.Failed.ToString();
                    journal.Save(journalPath);
                    return result;
                }
                journal.Phase = OperationPhase.GptDataStartUpdated.ToString();
                journal.Save(journalPath);
                if (options.FailAfterGptStartUpdate)
                {
                    journal.LastError = "simulated failure after GPT data-start update";
                    journal.Save(journalPath);
                    result.Success = false;
                    result.ExitCode = 3;
                    result.Message = journal.LastError;
                    return result;
                }
            }

            phase = ParsePhase(journal.Phase);
            if (phase == OperationPhase.GptDataStartUpdated)
            {
                if (!GptEditor.GrowPartition(journal.DiskNumber, journal.SystemPartitionNumber, journal.Growth, out var growError))
                {
                    result.Message = growError;
                    journal.LastError = growError;
                    journal.Save(journalPath);
                    return result;
                }
                if (!GptEditor.UpdateDriveSize(journal.DiskNumber, out var sizeError))
                {
                    result.Message = sizeError;
                    journal.LastError = sizeError;
                    journal.Save(journalPath);
                    return result;
                }
                journal.Phase = OperationPhase.GptUpdated.ToString();
                journal.Save(journalPath);
                if (options.FailAfterGptUpdated)
                {
                    journal.LastError = "simulated failure after GPT partition growth";
                    journal.Save(journalPath);
                    result.Success = false;
                    result.ExitCode = 3;
                    result.Message = journal.LastError;
                    return result;
                }
            }

            GptEditor.RefreshDiskProperties(journal.DiskNumber);
            if (!VolumeControl.Remount(journal.DataVolumeGuid, journal.DataDriveLetter, out var remountError))
            {
                // A volume that Windows already mounted under a new letter is usable; extension is done by GUID.
                journal.LastError = remountError;
                journal.Save(journalPath);
            }
            else
            {
                journal.LastError = null;
                journal.Save(journalPath);
            }

            var extended = false;
            string extendError = null;
            for (var attempt = 0; attempt < 3 && !extended; attempt++)
            {
                extended = VolumeControl.ExtendVolume(journal.SystemVolumeGuid, journal.SystemDriveLetter, journal.NewSystemSize, journal.LogicalSectorSize, out extendError);
                if (!extended)
                {
                    GptEditor.RefreshDiskProperties(journal.DiskNumber);
                    GptEditor.UpdateDriveSize(journal.DiskNumber, out _);
                    Thread.Sleep(300);
                }
            }
            if (!extended)
            {
                result.Message = extendError;
                journal.LastError = extendError;
                journal.Save(journalPath);
                return result;
            }

            journal.Phase = OperationPhase.Completed.ToString();
            journal.ProgressSourceOffset = journal.DataOffset;
            journal.LastError = null;
            journal.Save(journalPath);

            string letterError;
            if (!VolumeControl.RestoreDriveLetter(journal.DataVolumeGuid, journal.DataDriveLetter, out letterError))
            {
                result.Message = "completed, but data drive letter was not restored: " + letterError;
            }
            if (!VolumeControl.RestoreDriveLetter(journal.SystemVolumeGuid, journal.SystemDriveLetter, out letterError))
            {
                if (string.IsNullOrEmpty(result.Message)) result.Message = "completed, but system drive letter was not restored: " + letterError;
            }
            if (string.IsNullOrEmpty(result.Message)) result.Message = "completed";
            result.Success = true;
            result.ExitCode = 0;
            return result;
        }

        private static void MoveFromJournal(EngineOptions options, OperationJournal journal, EngineResult result)
        {
            var sourceEnd = journal.DataOffset + journal.DataSize;
            var progress = journal.ProgressSourceOffset <= 0 ? sourceEnd : journal.ProgressSourceOffset;
            var movedThisRun = 0L;
            BlockMover.MoveRight(journal.DiskNumber, journal.DataOffset, sourceEnd, journal.Growth, progress,
                next =>
                {
                    journal.ProgressSourceOffset = next;
                    journal.Save(options.JournalPath);
                    if (options.Progress != null) options.Progress(sourceEnd - next, journal.DataSize);
                    if (options.ChunkDelayMs > 0) Thread.Sleep(options.ChunkDelayMs);
                    movedThisRun = sourceEnd - next;
                    if (options.InterruptAfterBytes > 0 && movedThisRun >= options.InterruptAfterBytes)
                    {
                        throw new OperationInterruptedException("simulated interruption after " + movedThisRun + " bytes");
                    }
                }, options.ChunkBytes);
        }

        private static PartitionInfo FindPartition(DiskInfo disk, int number)
        {
            foreach (var partition in disk.Partitions) if (partition.PartitionNumber == number) return partition;
            return null;
        }

        private static OperationPhase ParsePhase(string value)
        {
            OperationPhase phase;
            return Enum.TryParse(value, out phase) ? phase : OperationPhase.Failed;
        }
    }
}
