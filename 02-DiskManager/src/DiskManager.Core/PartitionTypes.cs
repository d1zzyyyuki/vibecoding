using System;

namespace DiskManager.Core
{
    public static class PartitionTypes
    {
        public const string EfiSystem = "C12A7328-F81F-11D2-BA4B-00A0C93EC93B";
        public const string MicrosoftReserved = "E3C9E316-0B5C-4DB8-817D-F92DF00215AE";
        public const string WindowsRecovery = "DE94BBA4-06D1-4D40-A16A-BFD50179D6AC";
        public const string BasicData = "EBD0A0A2-B9E5-4433-87C0-68B6B72699C7";
        public const string LdmMetadata = "5808C8AA-7E8F-42E0-85D2-E1E90434CFB3";
        public const string LdmData = "AF9B60A0-1431-4F62-BC68-3311714A69AD";

        public const ulong AttributeNoDriveLetter = 0x8000000000000000UL;
        public const ulong AttributeHidden = 0x4000000000000000UL;
        public const ulong AttributeShadowCopy = 0x2000000000000000UL;
        public const ulong AttributeReadOnly = 0x1000000000000000UL;

        public static bool IsKnown(string guid)
        {
            return !string.IsNullOrEmpty(guid) && NameOf(guid) != null;
        }

        public static string NameOf(string guid)
        {
            if (string.IsNullOrEmpty(guid)) return null;
            switch (guid.ToUpperInvariant())
            {
                case EfiSystem: return "EFI 系统分区";
                case MicrosoftReserved: return "MSR 保留分区";
                case WindowsRecovery: return "恢复分区";
                case BasicData: return "基本数据";
                case LdmMetadata: return "LDM 元数据";
                case LdmData: return "LDM 数据";
                default: return null;
            }
        }

        public static string MbrName(byte type)
        {
            switch (type)
            {
                case 0x07: return "NTFS/exFAT";
                case 0x0B: return "FAT32";
                case 0x0C: return "FAT32 LBA";
                case 0x0E: return "FAT16 LBA";
                case 0x27: return "恢复分区";
                case 0x82: return "Linux Swap";
                case 0x83: return "Linux";
                case 0xEE: return "GPT 保护分区";
                case 0xEF: return "EFI 系统分区";
                default: return "MBR 0x" + type.ToString("X2");
            }
        }
    }
}
