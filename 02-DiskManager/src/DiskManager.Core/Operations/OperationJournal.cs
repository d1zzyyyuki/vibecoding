using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;

namespace DiskManager.Core.Operations
{
    public enum OperationPhase
    {
        Prepared,
        Shrinking,
        DataLocked,
        Moving,
        Moved,
        GptDataStartUpdated,
        GptUpdated,
        Completed,
        RollingBack,
        RolledBack,
        Failed
    }

    public sealed class OperationJournal
    {
        public int Version = 1;
        public string OperationId;
        public string Phase = OperationPhase.Prepared.ToString();
        public int DiskNumber;
        public int SystemPartitionNumber;
        public int DataPartitionNumber;
        public string SystemGptId;
        public string DataGptId;
        public string SystemVolumeGuid;
        public string DataVolumeGuid;
        public string SystemDriveLetter;
        public string DataDriveLetter;
        public string DiskModel;
        public long DiskSize;
        public int LogicalSectorSize = 512;
        public long DataShrinkBytes;
        public long NewSystemSize;
        public long SystemOffset;
        public long SystemSize;
        public long DataOffset;
        public long DataSize;
        public long Growth;
        public long NewDataStart;
        public long ProgressSourceOffset;
        public string CreatedUtc;
        public string UpdatedUtc;
        public string LastError;

        public static OperationJournal Create(int diskNumber, int systemPartition, int dataPartition, long growth, long dataOffset, long dataSize)
        {
            return new OperationJournal
            {
                OperationId = Guid.NewGuid().ToString("N"),
                Phase = OperationPhase.Prepared.ToString(),
                DiskNumber = diskNumber,
                SystemPartitionNumber = systemPartition,
                DataPartitionNumber = dataPartition,
                Growth = growth,
                DataOffset = dataOffset,
                DataSize = dataSize,
                NewDataStart = dataOffset + growth,
                ProgressSourceOffset = dataOffset + dataSize,
                CreatedUtc = DateTime.UtcNow.ToString("o", CultureInfo.InvariantCulture),
                UpdatedUtc = DateTime.UtcNow.ToString("o", CultureInfo.InvariantCulture)
            };
        }

        public void Save(string path)
        {
            UpdatedUtc = DateTime.UtcNow.ToString("o", CultureInfo.InvariantCulture);
            var content = new StringBuilder();
            content.Append("version=").Append(Version).Append('\n');
            content.Append("operationId=").Append(OperationId).Append('\n');
            content.Append("phase=").Append(Phase).Append('\n');
            content.Append("diskNumber=").Append(DiskNumber).Append('\n');
            content.Append("systemPartition=").Append(SystemPartitionNumber).Append('\n');
            content.Append("dataPartition=").Append(DataPartitionNumber).Append('\n');
            content.Append("systemGptId=").Append(SystemGptId).Append('\n');
            content.Append("dataGptId=").Append(DataGptId).Append('\n');
            content.Append("systemVolumeGuid=").Append(SystemVolumeGuid).Append('\n');
            content.Append("dataVolumeGuid=").Append(DataVolumeGuid).Append('\n');
            content.Append("systemDriveLetter=").Append(SystemDriveLetter).Append('\n');
            content.Append("dataDriveLetter=").Append(DataDriveLetter).Append('\n');
            content.Append("diskModel=").Append(DiskModel).Append('\n');
            content.Append("diskSize=").Append(DiskSize).Append('\n');
            content.Append("logicalSectorSize=").Append(LogicalSectorSize).Append('\n');
            content.Append("dataShrinkBytes=").Append(DataShrinkBytes).Append('\n');
            content.Append("newSystemSize=").Append(NewSystemSize).Append('\n');
            content.Append("systemOffset=").Append(SystemOffset).Append('\n');
            content.Append("systemSize=").Append(SystemSize).Append('\n');
            content.Append("dataOffset=").Append(DataOffset).Append('\n');
            content.Append("dataSize=").Append(DataSize).Append('\n');
            content.Append("growth=").Append(Growth).Append('\n');
            content.Append("newDataStart=").Append(NewDataStart).Append('\n');
            content.Append("progressSourceOffset=").Append(ProgressSourceOffset).Append('\n');
            content.Append("createdUtc=").Append(CreatedUtc).Append('\n');
            content.Append("updatedUtc=").Append(UpdatedUtc).Append('\n');
            content.Append("lastError=").Append((LastError ?? string.Empty).Replace("\r", " ").Replace("\n", " ")).Append('\n');

            WriteAtomic(path, Encoding.UTF8.GetBytes(content.ToString()));
        }

        public static OperationJournal Load(string path)
        {
            var map = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            foreach (var line in File.ReadAllLines(path, Encoding.UTF8))
            {
                if (string.IsNullOrEmpty(line)) continue;
                var index = line.IndexOf('=');
                if (index <= 0) continue;
                map[line.Substring(0, index)] = line.Substring(index + 1);
            }

            var journal = new OperationJournal();
            journal.Version = ParseInt(map, "version", 1);
            journal.OperationId = Get(map, "operationId");
            journal.Phase = Get(map, "phase");
            journal.DiskNumber = ParseInt(map, "diskNumber", -1);
            journal.SystemPartitionNumber = ParseInt(map, "systemPartition", -1);
            journal.DataPartitionNumber = ParseInt(map, "dataPartition", -1);
            journal.SystemGptId = Get(map, "systemGptId");
            journal.DataGptId = Get(map, "dataGptId");
            journal.SystemVolumeGuid = Get(map, "systemVolumeGuid");
            journal.DataVolumeGuid = Get(map, "dataVolumeGuid");
            journal.SystemDriveLetter = Get(map, "systemDriveLetter");
            journal.DataDriveLetter = Get(map, "dataDriveLetter");
            journal.DiskModel = Get(map, "diskModel");
            journal.DiskSize = ParseLong(map, "diskSize", 0);
            journal.LogicalSectorSize = ParseInt(map, "logicalSectorSize", 512);
            journal.DataShrinkBytes = ParseLong(map, "dataShrinkBytes", 0);
            journal.NewSystemSize = ParseLong(map, "newSystemSize", 0);
            journal.SystemOffset = ParseLong(map, "systemOffset", 0);
            journal.SystemSize = ParseLong(map, "systemSize", 0);
            journal.DataOffset = ParseLong(map, "dataOffset", 0);
            journal.DataSize = ParseLong(map, "dataSize", 0);
            journal.Growth = ParseLong(map, "growth", 0);
            journal.NewDataStart = ParseLong(map, "newDataStart", 0);
            journal.ProgressSourceOffset = ParseLong(map, "progressSourceOffset", 0);
            journal.CreatedUtc = Get(map, "createdUtc");
            journal.UpdatedUtc = Get(map, "updatedUtc");
            journal.LastError = Get(map, "lastError");
            return journal;
        }

        public static void SaveGpt(string journalPath, byte[] layout)
        {
            WriteAtomic(journalPath + ".gpt", layout);
        }

        public static byte[] LoadGpt(string journalPath)
        {
            var path = journalPath + ".gpt";
            return File.Exists(path) ? File.ReadAllBytes(path) : null;
        }

        public static void Delete(string journalPath)
        {
            try { if (File.Exists(journalPath)) File.Delete(journalPath); } catch { }
            try { if (File.Exists(journalPath + ".gpt")) File.Delete(journalPath + ".gpt"); } catch { }
        }

        private static void WriteAtomic(string path, byte[] data)
        {
            var temp = path + ".tmp";
            using (var stream = new FileStream(temp, FileMode.Create, FileAccess.Write, FileShare.None))
            {
                stream.Write(data, 0, data.Length);
                stream.Flush(true);
            }
            try
            {
                if (File.Exists(path)) File.Replace(temp, path, null);
                else File.Move(temp, path);
            }
            catch
            {
                try { if (File.Exists(path)) File.Delete(path); } catch { }
                File.Move(temp, path);
            }
        }

        private static string Get(Dictionary<string, string> map, string key)
        {
            string value;
            return map.TryGetValue(key, out value) ? value : null;
        }

        private static int ParseInt(Dictionary<string, string> map, string key, int fallback)
        {
            int value;
            return int.TryParse(Get(map, key), NumberStyles.Integer, CultureInfo.InvariantCulture, out value) ? value : fallback;
        }

        private static long ParseLong(Dictionary<string, string> map, string key, long fallback)
        {
            long value;
            return long.TryParse(Get(map, key), NumberStyles.Integer, CultureInfo.InvariantCulture, out value) ? value : fallback;
        }
    }
}
