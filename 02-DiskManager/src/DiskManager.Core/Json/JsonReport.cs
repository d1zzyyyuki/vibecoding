using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace DiskManager.Core.Json
{
    public sealed class CheckResult
    {
        public string Name;
        public bool Passed;
        public string Detail;
    }

    public static class JsonReport
    {
        public static string Build(ScanResult result, IList<CheckResult> checks, bool passed)
        {
            var json = new StringBuilder();
            json.Append("{\n");
            Str(json, 1, "tool", result.ToolName, true);
            Str(json, 1, "version", result.Version, true);
            Str(json, 1, "startedAtUtc", result.StartedAtUtc.ToString("o", CultureInfo.InvariantCulture), true);
            Num(json, 1, "durationMs", result.DurationMs, true);
            Str(json, 1, "machine", result.MachineName, true);
            Str(json, 1, "os", result.OsDescription, true);
            Str(json, 1, "osArch", result.OsArchitecture, true);
            Bool(json, 1, "elevated", result.IsElevated, true);
            Str(json, 1, "systemVolumeGuid", result.SystemVolumeGuid, true);

            json.Append("  \"disks\": [");
            if (result.Disks.Count == 0) json.Append("],\n");
            else
            {
                json.Append('\n');
                for (var i = 0; i < result.Disks.Count; i++)
                {
                    AppendDisk(json, result.Disks[i], 2);
                    json.Append(i == result.Disks.Count - 1 ? "\n" : ",\n");
                }
                json.Append("  ],\n");
            }

            json.Append("  \"checks\": [");
            if (checks == null || checks.Count == 0) json.Append("],\n");
            else
            {
                json.Append('\n');
                for (var i = 0; i < checks.Count; i++)
                {
                    json.Append("    { ");
                    json.Append("\"name\": ").Append(Quote(checks[i].Name)).Append(", ");
                    json.Append("\"passed\": ").Append(checks[i].Passed ? "true" : "false").Append(", ");
                    json.Append("\"detail\": ").Append(Quote(checks[i].Detail)).Append(" }");
                    json.Append(i == checks.Count - 1 ? "\n" : ",\n");
                }
                json.Append("  ],\n");
            }

            StringArray(json, 1, "warnings", result.Warnings, true);
            StringArray(json, 1, "errors", result.Errors, true);
            Bool(json, 1, "passed", passed, false);
            json.Append("}\n");
            return json.ToString();
        }

        private static void AppendDisk(StringBuilder json, DiskInfo disk, int indent)
        {
            var pad = new string(' ', indent * 2);
            var inner = new string(' ', (indent + 1) * 2);
            json.Append(pad).Append("{\n");
            Num(json, indent + 1, "number", disk.Number, true);
            Str(json, indent + 1, "model", disk.Model, true);
            Str(json, indent + 1, "serial", disk.Serial, true);
            Str(json, indent + 1, "busType", disk.BusType, true);
            Str(json, indent + 1, "mediaKind", disk.MediaKind, true);
            Str(json, indent + 1, "pcieLink", disk.PcieLink, true);
            Num(json, indent + 1, "sizeBytes", disk.SizeBytes, true);
            Num(json, indent + 1, "logicalSectorSize", disk.LogicalSectorSize, true);
            Num(json, indent + 1, "physicalSectorSize", disk.PhysicalSectorSize, true);
            Str(json, indent + 1, "partitionStyle", disk.PartitionStyle, true);
            Bool(json, indent + 1, "isSystemDisk", disk.IsSystemDisk, true);
            Bool(json, indent + 1, "isBootDisk", disk.IsBootDisk, true);
            Str(json, indent + 1, "health", disk.Health, true);
            Str(json, indent + 1, "operationalStatus", disk.OperationalStatus, true);

            json.Append(inner).Append("\"speed\": ");
            if (disk.Speed == null) json.Append("null,\n");
            else
            {
                json.Append("{\n");
                Bool(json, indent + 2, "success", disk.Speed.Success, true);
                Str(json, indent + 2, "method", disk.Speed.Method, true);
                Num(json, indent + 2, "sampleBytes", disk.Speed.SampleBytes, true);
                Num(json, indent + 2, "samplesCompleted", disk.Speed.SamplesCompleted, true);
                Double(json, indent + 2, "throughputMBps", disk.Speed.ThroughputMBps, true);
                Double(json, indent + 2, "peakMBps", disk.Speed.PeakMBps, true);
                Num(json, indent + 2, "elapsedMs", disk.Speed.ElapsedMs, true);
                Str(json, indent + 2, "error", disk.Speed.Error, true);
                json.Append(new string(' ', (indent + 2) * 2)).Append("\"samples\": [");
                if (disk.Speed.Samples.Count == 0) json.Append("]\n");
                else
                {
                    json.Append('\n');
                    for (var i = 0; i < disk.Speed.Samples.Count; i++)
                    {
                        var sample = disk.Speed.Samples[i];
                        json.Append(new string(' ', (indent + 3) * 2)).Append("{ ");
                        json.Append("\"offsetBytes\": ").Append(sample.OffsetBytes.ToString(CultureInfo.InvariantCulture)).Append(", ");
                        json.Append("\"bytesRead\": ").Append(sample.BytesRead.ToString(CultureInfo.InvariantCulture)).Append(", ");
                        json.Append("\"elapsedMs\": ").Append(sample.ElapsedMs.ToString(CultureInfo.InvariantCulture)).Append(", ");
                        json.Append("\"throughputMBps\": ").Append(sample.ThroughputMBps.ToString("0.##", CultureInfo.InvariantCulture)).Append(" }");
                        json.Append(i == disk.Speed.Samples.Count - 1 ? "\n" : ",\n");
                    }
                    json.Append(new string(' ', (indent + 2) * 2)).Append("]\n");
                }
                json.Append(inner).Append("},\n");
            }

            json.Append(inner).Append("\"partitions\": [");
            if (disk.Partitions.Count == 0) json.Append("]\n");
            else
            {
                json.Append('\n');
                for (var i = 0; i < disk.Partitions.Count; i++)
                {
                    AppendPartition(json, disk.Partitions[i], indent + 2);
                    json.Append(i == disk.Partitions.Count - 1 ? "\n" : ",\n");
                }
                json.Append(inner).Append("]\n");
            }
            json.Append(pad).Append("}");
        }

        private static void AppendPartition(StringBuilder json, PartitionInfo partition, int indent)
        {
            var inner = new string(' ', (indent + 1) * 2);
            json.Append(inner).Append("{\n");
            Num(json, indent + 1, "partitionNumber", partition.PartitionNumber, true);
            Num(json, indent + 1, "offsetBytes", partition.OffsetBytes, true);
            Num(json, indent + 1, "sizeBytes", partition.SizeBytes, true);
            Str(json, indent + 1, "partitionStyle", partition.PartitionStyle, true);
            Str(json, indent + 1, "typeName", partition.TypeName, true);
            Str(json, indent + 1, "gptTypeId", partition.GptTypeId, true);
            Str(json, indent + 1, "gptName", partition.GptName, true);
            Str(json, indent + 1, "driveLetter", partition.DriveLetter, true);
            Str(json, indent + 1, "label", partition.Label, true);
            Str(json, indent + 1, "fileSystem", partition.FileSystem, true);
            Str(json, indent + 1, "volumeGuid", partition.VolumeGuid, true);
            Num(json, indent + 1, "volumeTotalBytes", partition.VolumeTotalBytes, true);
            Num(json, indent + 1, "freeBytes", partition.FreeBytes, true);
            Bool(json, indent + 1, "isSystem", partition.IsSystem, true);
            Bool(json, indent + 1, "isBoot", partition.IsBoot, true);
            Bool(json, indent + 1, "isHidden", partition.IsHidden, false);
            json.Append(inner).Append("}");
        }

        private static void Str(StringBuilder json, int indent, string key, string value, bool comma)
        {
            json.Append(new string(' ', indent * 2)).Append(Quote(key)).Append(": ");
            json.Append(value == null ? "null" : Quote(value));
            if (comma) json.Append(',');
            json.Append('\n');
        }

        private static void Num(StringBuilder json, int indent, string key, long value, bool comma)
        {
            json.Append(new string(' ', indent * 2)).Append(Quote(key)).Append(": ").Append(value.ToString(CultureInfo.InvariantCulture));
            if (comma) json.Append(',');
            json.Append('\n');
        }

        private static void Double(StringBuilder json, int indent, string key, double value, bool comma)
        {
            json.Append(new string(' ', indent * 2)).Append(Quote(key)).Append(": ").Append(value.ToString("0.##", CultureInfo.InvariantCulture));
            if (comma) json.Append(',');
            json.Append('\n');
        }

        private static void Bool(StringBuilder json, int indent, string key, bool value, bool comma)
        {
            json.Append(new string(' ', indent * 2)).Append(Quote(key)).Append(": ").Append(value ? "true" : "false");
            if (comma) json.Append(',');
            json.Append('\n');
        }

        private static void StringArray(StringBuilder json, int indent, string key, IList<string> values, bool comma)
        {
            json.Append(new string(' ', indent * 2)).Append(Quote(key)).Append(": [");
            if (values == null || values.Count == 0) json.Append(']');
            else
            {
                json.Append('\n');
                for (var i = 0; i < values.Count; i++)
                {
                    json.Append(new string(' ', (indent + 1) * 2)).Append(Quote(values[i]));
                    json.Append(i == values.Count - 1 ? "\n" : ",\n");
                }
                json.Append(new string(' ', indent * 2)).Append(']');
            }
            if (comma) json.Append(',');
            json.Append('\n');
        }

        private static string Quote(string value)
        {
            if (value == null) return "null";
            var builder = new StringBuilder(value.Length + 8);
            builder.Append('"');
            foreach (var c in value)
            {
                switch (c)
                {
                    case '"': builder.Append("\\\""); break;
                    case '\\': builder.Append("\\\\"); break;
                    case '\b': builder.Append("\\b"); break;
                    case '\f': builder.Append("\\f"); break;
                    case '\n': builder.Append("\\n"); break;
                    case '\r': builder.Append("\\r"); break;
                    case '\t': builder.Append("\\t"); break;
                    default:
                        if (c < 0x20) builder.Append("\\u").Append(((int)c).ToString("x4", CultureInfo.InvariantCulture));
                        else builder.Append(c);
                        break;
                }
            }
            builder.Append('"');
            return builder.ToString();
        }
    }
}
