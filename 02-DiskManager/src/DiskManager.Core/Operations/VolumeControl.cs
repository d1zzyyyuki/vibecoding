using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Runtime.InteropServices;
using DiskManager.Core.Native;
using Microsoft.Win32.SafeHandles;

namespace DiskManager.Core.Operations
{
    public sealed class LockedVolume : IDisposable
    {
        public SafeFileHandle Handle { get; private set; }
        public string VolumePath { get; private set; }

        internal LockedVolume(SafeFileHandle handle, string volumePath)
        {
            Handle = handle;
            VolumePath = volumePath;
        }

        public void Dispose()
        {
            if (Handle != null)
            {
                Handle.Dispose();
                Handle = null;
            }
        }
    }

    public static class VolumeControl
    {
        public static LockedVolume LockAndDismount(string volumeGuid, string driveLetter, out string error)
        {
            error = null;
            var path = string.IsNullOrEmpty(volumeGuid) ? null : volumeGuid.TrimEnd('\\');
            if (string.IsNullOrEmpty(path) && !string.IsNullOrEmpty(driveLetter)) path = @"\\.\" + driveLetter + ":";
            if (string.IsNullOrEmpty(path))
            {
                error = "没有卷路径";
                return null;
            }

            var handle = OpenVolumeForIo(path);
            if (handle.IsInvalid)
            {
                error = "打开卷失败：" + Marshal.GetLastWin32Error();
                return null;
            }

            if (!Io.Control(handle, NativeMethods.FSCTL_LOCK_VOLUME, null, out var lockError))
            {
                handle.Dispose();
                error = "锁定卷失败：" + lockError + "（可能有文件/页面文件/快照占用）";
                return null;
            }
            if (!Io.Control(handle, NativeMethods.FSCTL_DISMOUNT_VOLUME, null, out var dismountError))
            {
                handle.Dispose();
                error = "卸载卷失败：" + dismountError;
                return null;
            }
            return new LockedVolume(handle, path);
        }

        public static bool ExtendVolume(string volumeGuid, string driveLetter, long newSizeBytes, int logicalSectorSize, out string error)
        {
            error = null;
            if (logicalSectorSize <= 0) logicalSectorSize = 512;
            if (newSizeBytes % logicalSectorSize != 0) { error = "新卷大小未按扇区对齐"; return false; }
            var paths = new System.Collections.Generic.List<string>();
            if (!string.IsNullOrEmpty(driveLetter)) paths.Add(@"\\.\" + driveLetter.TrimEnd(':') + ":");
            if (!string.IsNullOrEmpty(volumeGuid)) paths.Add(volumeGuid.TrimEnd('\\'));
            if (paths.Count == 0) { error = "没有卷路径"; return false; }

            var errors = new System.Collections.Generic.List<string>();
            foreach (var path in paths)
            {
                using (var handle = OpenVolumeForIo(path))
                {
                    if (handle.IsInvalid)
                    {
                        errors.Add("open " + path + " failed: " + Marshal.GetLastWin32Error());
                        continue;
                    }
                    Io.Control(handle, NativeMethods.IOCTL_DISK_UPDATE_PROPERTIES, null, out _);
                    Io.Query(handle, NativeMethods.IOCTL_DISK_UPDATE_DRIVE_SIZE, null, 64, out _);
                    var data = BitConverter.GetBytes(newSizeBytes / logicalSectorSize);
                    if (!Io.Control(handle, NativeMethods.FSCTL_EXTEND_VOLUME, data, out var ioError))
                    {
                        errors.Add("extend " + path + " failed: " + ioError + " size=" + newSizeBytes);
                        continue;
                    }
                    return true;
                }
            }
            error = string.Join(" | ", errors);
            return false;
        }

        public static bool Remount(string volumeGuid, string driveLetter, out string error)
        {
            error = null;
            if (string.IsNullOrEmpty(volumeGuid)) { error = "缺少卷 GUID"; return false; }
            var current = GetCurrentMountPoint(volumeGuid);
            if (!string.IsNullOrEmpty(current)) return true;

            if (string.IsNullOrEmpty(driveLetter)) { error = "卷已自动挂载但缺少原盘符"; return false; }
            var mountPoint = driveLetter.TrimEnd(':') + @":\";
            var volumeName = volumeGuid.TrimEnd('\\') + @"\";
            try
            {
                if (!System.IO.Directory.Exists(mountPoint)) System.IO.Directory.CreateDirectory(mountPoint);
            }
            catch { }
            if (!NativeMethods.SetVolumeMountPointW(mountPoint, volumeName))
            {
                var code = Marshal.GetLastWin32Error();
                // 183 = already mounted.
                if (code != 183)
                {
                    current = GetCurrentMountPoint(volumeGuid);
                    if (!string.IsNullOrEmpty(current)) return true;
                    error = "恢复盘符失败：" + code;
                    return false;
                }
            }
            return true;
        }

        public static string GetCurrentMountPoint(string volumeGuid)
        {
            if (string.IsNullOrEmpty(volumeGuid)) return null;
            var path = volumeGuid.TrimEnd('\\') + @"\";
            var buffer = new char[32768];
            uint needed;
            if (!NativeMethods.GetVolumePathNamesForVolumeNameW(path, buffer, (uint)buffer.Length, out needed)) return null;
            for (var i = 0; i < buffer.Length; i++)
            {
                if (buffer[i] != '\0') continue;
                if (i > 0)
                {
                    var value = new string(buffer, 0, i);
                    if (value.Length >= 2 && value[1] == ':') return value;
                }
                break;
            }
            return null;
        }

        public static bool ShrinkWithDiskPart(string driveLetter, long shrinkBytes, out string error, out string output)
        {
            error = null;
            output = null;
            if (string.IsNullOrEmpty(driveLetter)) { error = "缺少盘符"; return false; }
            if (shrinkBytes <= 0) { error = "收缩量无效"; return false; }
            var shrinkMb = (long)Math.Ceiling(shrinkBytes / 1024.0 / 1024.0);
            var directory = Path.Combine(Path.GetTempPath(), "DiskManager");
            Directory.CreateDirectory(directory);
            var script = Path.Combine(directory, "shrink-" + Guid.NewGuid().ToString("N") + ".txt");
            var log = script + ".log";
            try
            {
                var lines = new[]
                {
                    "select volume " + driveLetter.TrimEnd(':'),
                    "shrink desired=" + shrinkMb,
                    "exit"
                };
                File.WriteAllText(script, string.Join("\r\n", lines) + "\r\n", Encoding.ASCII);
                var info = new ProcessStartInfo
                {
                    FileName = Path.Combine(Environment.SystemDirectory, "diskpart.exe"),
                    Arguments = "/s \"" + script + "\"",
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true
                };
                using (var process = Process.Start(info))
                {
                    if (process == null) { error = "无法启动 diskpart"; return false; }
                    var stdout = process.StandardOutput.ReadToEnd();
                    var stderr = process.StandardError.ReadToEnd();
                    if (!process.WaitForExit(10 * 60 * 1000))
                    {
                        try { process.Kill(); } catch { }
                        error = "diskpart shrink 超时";
                        return false;
                    }
                    output = stdout + stderr;
                    try { File.WriteAllText(log, output, Encoding.UTF8); } catch { }
                    if (process.ExitCode != 0)
                    {
                        error = "diskpart shrink 失败，退出码 " + process.ExitCode;
                        return false;
                    }
                    return true;
                }
            }
            catch (Exception ex)
            {
                error = "diskpart shrink 异常: " + ex.Message;
                return false;
            }
            finally
            {
                try { if (File.Exists(script)) File.Delete(script); } catch { }
            }
        }

        public static bool RestoreDriveLetter(string volumeGuid, string preferredLetter, out string error)
        {
            error = null;
            if (string.IsNullOrEmpty(volumeGuid) || string.IsNullOrEmpty(preferredLetter))
            {
                error = "缺少卷 GUID 或盘符";
                return false;
            }
            var preferred = preferredLetter.TrimEnd(':') + @":\";
            var current = GetCurrentMountPoint(volumeGuid);
            if (string.Equals(current, preferred, StringComparison.OrdinalIgnoreCase)) return true;

            var volumeName = volumeGuid.TrimEnd('\\') + @"\";
            if (!string.IsNullOrEmpty(current) && current.Length >= 2)
            {
                NativeMethods.DeleteVolumeMountPointW(current);
            }

            if (NativeMethods.SetVolumeMountPointW(preferred, volumeName)) return true;

            // Drive-letter roots do not always exist as directories; create the DOS device symlink directly.
            var trimmed = volumeGuid.TrimEnd('\\');
            var prefix = @"\\?\";
            var target = trimmed.StartsWith(prefix, StringComparison.OrdinalIgnoreCase)
                ? @"\??\" + trimmed.Substring(prefix.Length)
                : trimmed;
            if (NativeMethods.DefineDosDeviceW(NativeMethods.DDD_RAW_TARGET_PATH, preferredLetter.TrimEnd(':') + ":", target))
            {
                return true;
            }
            error = "恢复盘符失败，Win32 错误 " + Marshal.GetLastWin32Error();
            return false;
        }

        private static SafeFileHandle OpenVolumeForIo(string path)
        {
            var handle = NativeMethods.CreateFileW(
                path,
                NativeMethods.GENERIC_READ | NativeMethods.GENERIC_WRITE,
                NativeMethods.FILE_SHARE_READ | NativeMethods.FILE_SHARE_WRITE,
                IntPtr.Zero,
                NativeMethods.OPEN_EXISTING,
                0,
                IntPtr.Zero);
            if (handle.IsInvalid)
            {
                handle = NativeMethods.CreateFileW(
                    path + "\\",
                    NativeMethods.GENERIC_READ | NativeMethods.GENERIC_WRITE,
                    NativeMethods.FILE_SHARE_READ | NativeMethods.FILE_SHARE_WRITE,
                    IntPtr.Zero,
                    NativeMethods.OPEN_EXISTING,
                    0,
                    IntPtr.Zero);
            }
            return handle;
        }
    }
}
