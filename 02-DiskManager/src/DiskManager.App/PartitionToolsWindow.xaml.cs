using System;
using System.ComponentModel;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Input;
using DiskManager.Core;
using DiskManager.Core.Operations;
using DiskManager.ViewModels;

namespace DiskManager
{
    public partial class PartitionToolsWindow : Window
    {
        private readonly DiskInfo _disk;
        private readonly PartitionInfo _partition;
        private readonly string _mode;
        private bool _executing;
        private bool _executed;
        private bool _executedSuccess;
        private bool _writable;
        private long _sizeMaxBytes;
        private bool _sizeUseGb;
        private const long Gb = 1024L * 1024L * 1024L;
        private const long Mb = 1024L * 1024L;

        public PartitionToolsWindow(DiskInfo disk, PartitionInfo partition, string mode)
        {
            InitializeComponent();
            _disk = disk;
            _partition = partition;
            _mode = (mode ?? "create").ToLowerInvariant();
            Owner = Application.Current == null ? null : Application.Current.MainWindow;
            Configure();
            if (UiLanguage.English) ApplyEnglishShell();
        }

        private void ApplyEnglishShell()
        {
            Title = "Partition tools";
            var map = new System.Collections.Generic.Dictionary<string, string>(StringComparer.Ordinal)
            {
                { "分区工具", "Partition tools" },
                { "新分区大小 (MB)", "New partition size (MB)" },
                { "新分区大小", "New partition size" },
                { "卷标", "Volume label" },
                { "盘符（留空自动）", "Drive letter (auto if blank)" },
                { "文件系统：NTFS（当前只开放 NTFS）", "File system: NTFS (only NTFS enabled)" },
                { "取消", "Cancel" },
                { "开始", "Start" },
                { "确认分区操作", "Confirm partition operation" },
                { "我已备份数据，并了解操作风险", "I have backed up data and understand the risk" },
                { "确认执行", "Run" }
            };
            TranslateTree(this, map);
        }

        private static void TranslateTree(DependencyObject root, System.Collections.Generic.Dictionary<string, string> map)
        {
            if (root == null) return;
            foreach (var child in LogicalTreeHelper.GetChildren(root))
            {
                var element = child as DependencyObject;
                if (element == null) continue;
                var text = element as System.Windows.Controls.TextBlock;
                if (text != null)
                {
                    string translated;
                    if (map.TryGetValue(text.Text ?? "", out translated)) text.Text = translated;
                }
                var button = element as System.Windows.Controls.Button;
                if (button != null)
                {
                    var content = button.Content as string;
                    string translated;
                    if (content != null && map.TryGetValue(content, out translated)) button.Content = translated;
                }
                var check = element as System.Windows.Controls.CheckBox;
                if (check != null)
                {
                    var content = check.Content as string;
                    string translated;
                    if (content != null && map.TryGetValue(content, out translated)) check.Content = translated;
                }
                TranslateTree(element, map);
            }
        }

        public bool Executed
        {
            get { return _executed; }
        }

        public bool ExecutedSuccess
        {
            get { return _executedSuccess; }
        }

        protected override void OnClosing(CancelEventArgs e)
        {
            if (_executing)
            {
                e.Cancel = true;
                return;
            }
            base.OnClosing(e);
        }

        private void Configure()
        {
            ModeBadge.Text = _mode.ToUpperInvariant();
            _writable = _disk != null && string.Equals(_disk.BusType, "FileBackedVirtual", StringComparison.OrdinalIgnoreCase);
            var canOperate = _mode == "create" || _partition != null;
            StartButton.IsEnabled = canOperate;
            if (!canOperate) StatusText.Text = UiLanguage.T("没有选中分区。", "No partition selected.");
            else if (!_writable) StatusText.Text = UiLanguage.T("安全预览：真实磁盘写入尚未授权，不会修改分区表。", "Safe preview: real-disk writes are not authorized; the partition table will not be changed.");

            var targetPartition = _mode == "create" ? null : _partition;
            var target = targetPartition == null
                ? UiLanguage.T("磁盘 ", "Disk ") + (_disk == null ? "—" : _disk.Number.ToString(CultureInfo.InvariantCulture)) + " · " + (_disk == null ? "—" : _disk.DisplayName)
                : (targetPartition.DriveLetter == null ? UiLanguage.T("分区 ", "Partition ") + targetPartition.PartitionNumber : targetPartition.DriveLetter + ":") + " · " + targetPartition.TypeName;
            var detail = targetPartition == null
                ? UiLanguage.T("总容量 ", "Capacity ") + (_disk == null ? "—" : Humanize.Bytes(_disk.SizeBytes)) + UiLanguage.T(" · 新分区由 diskpart 选择未分配空间", " · diskpart will use unallocated space")
                : UiLanguage.T("分区大小 ", "Partition size ") + Humanize.Bytes(targetPartition.SizeBytes) + UiLanguage.T(" · 空闲 ", " · Free ") + Humanize.Bytes(targetPartition.FreeBytes) + UiLanguage.T(" · 磁盘 ", " · Disk ") + _disk.Number;
            TargetText.Text = target;
            TargetDetail.Text = detail;

            SizePanel.Visibility = _mode == "create" || _mode == "split" ? Visibility.Visible : Visibility.Collapsed;
            LetterPanel.Visibility = _mode == "create" || _mode == "split" ? Visibility.Visible : Visibility.Collapsed;
            LabelBox.IsEnabled = _mode != "delete";
            if (SizePanel.Visibility == Visibility.Visible)
            {
                ConfigureSize(targetPartition);
                SizeBox.Focus();
                SizeBox.SelectAll();
            }

            switch (_mode)
            {
                case "split":
                    HeaderTitle.Text = UiLanguage.T("拆分分区", "Split partition");
                    HeaderSubtitle.Text = UiLanguage.T("先收缩所选分区，再用释放出的空间创建新分区；数据保留，但执行前必须备份。", "Shrink the selected partition, then create a new one from the released space. Back up first.");
                    WarningText.Text = UiLanguage.T("拆分依赖所选分区的空闲空间；收缩失败或空间不足时不会继续创建。", "Split depends on free space; creation stops if shrinking fails or space is insufficient.");
                    break;
                case "format":
                    HeaderTitle.Text = UiLanguage.T("格式化分区", "Format partition");
                    HeaderSubtitle.Text = UiLanguage.T("清空所选分区的文件系统；执行前必须确认并备份。", "Wipe the file system of the selected partition. Confirm and back up first.");
                    WarningText.Text = UiLanguage.T("格式化会删除该分区上的全部文件，无法通过本工具恢复。", "Formatting deletes all files on the partition and cannot be undone by this tool.");
                    break;
                case "delete":
                    HeaderTitle.Text = UiLanguage.T("删除分区", "Delete partition");
                    HeaderSubtitle.Text = UiLanguage.T("删除所选分区及其文件系统；执行前必须确认并备份。", "Delete the selected partition and its file system. Confirm and back up first.");
                    WarningText.Text = UiLanguage.T("删除分区会丢失该分区上的全部数据，且没有自动回滚。", "Deleting loses all data on the partition; there is no automatic rollback.");
                    break;
                default:
                    HeaderTitle.Text = UiLanguage.T("新建分区", "New partition");
                    HeaderSubtitle.Text = UiLanguage.T("在所选磁盘的未分配空间创建分区；执行前必须确认并备份。", "Create a partition in unallocated space. Confirm and back up first.");
                    WarningText.Text = UiLanguage.T("新建分区会写入 GPT 并格式化新卷；请确认磁盘上有足够未分配空间。", "Creating writes GPT and formats a new volume; verify enough unallocated space exists.");
                    break;
            }
        }

        private void ConfigureSize(PartitionInfo targetPartition)
        {
            _sizeMaxBytes = _mode == "split" && targetPartition != null
                ? Math.Max(0, targetPartition.FreeBytes)
                : GetUnallocatedBytes();
            _sizeUseGb = _sizeMaxBytes >= Gb;
            SizeUnitText.Text = _sizeUseGb ? "GB" : "MB";
            SizeRangeText.Text = "(0-" + FormatSize(_sizeMaxBytes) + (_sizeUseGb ? " GB" : " MB") + ")";
            SizeBox.Text = FormatSize(_sizeMaxBytes / 2);
        }

        private long GetUnallocatedBytes()
        {
            if (_disk == null) return 0;
            long cursor = 0;
            foreach (var partition in _disk.Partitions.OrderBy(p => p.OffsetBytes))
            {
                if (partition.OffsetBytes > cursor) cursor = partition.OffsetBytes;
                cursor = Math.Max(cursor, partition.OffsetBytes + partition.SizeBytes);
            }
            return Math.Max(0, _disk.SizeBytes - cursor - Mb);
        }

        private string FormatSize(long bytes)
        {
            var divisor = (double)(_sizeUseGb ? Gb : Mb);
            return (bytes / divisor).ToString("0.0", CultureInfo.InvariantCulture);
        }

        private void Window_SourceInitialized(object sender, EventArgs e)
        {
            WindowFx.Apply(this, false);
        }

        private void TitleBar_MouseLeftButtonDown(object sender, MouseButtonEventArgs e)
        {
            if (e.ButtonState != MouseButtonState.Pressed) return;
            try { DragMove(); } catch (InvalidOperationException) { }
        }

        private void Close_Click(object sender, RoutedEventArgs e)
        {
            Close();
        }

        private void Start_Click(object sender, RoutedEventArgs e)
        {
            if (!StartButton.IsEnabled) return;
            if (_mode == "create" || _mode == "split")
            {
                var sizeBytes = ParseSizeBytes();
                if (sizeBytes < 64 * Mb)
                {
                    StatusText.Text = UiLanguage.T("新分区大小必须是至少 64 MB。", "Partition size must be at least 64 MB.");
                    return;
                }
                if (sizeBytes > _sizeMaxBytes)
                {
                    StatusText.Text = UiLanguage.T("新分区大小不能超过可用上限。", "Partition size cannot exceed the available maximum.");
                    return;
                }
            }

            ConfirmSummaryText.Text = BuildSummary();
            ConfirmWarningText.Text = _mode == "delete" || _mode == "format"
                ? UiLanguage.T("这会清空所选分区的数据，并且没有自动回滚。确认继续？", "This wipes the selected partition and has no automatic rollback. Continue?")
                : UiLanguage.T("执行会写入分区表；请确认没有其他程序正在使用这块盘。", "This writes the partition table. Make sure no other program is using the disk.");
            RiskCheck.IsChecked = false;
            ConfirmButton.IsEnabled = false;
            ConfirmPanel.Visibility = Visibility.Visible;
        }

        private string BuildSummary()
        {
            var target = _partition == null
                ? UiLanguage.T("磁盘 ", "Disk ") + _disk.Number
                : (_partition.DriveLetter == null ? UiLanguage.T("分区 ", "Partition ") + _partition.PartitionNumber : _partition.DriveLetter + ":");
            if (_mode == "delete") return UiLanguage.T("删除 " + target + "。", "Delete " + target + ".");
            if (_mode == "format") return UiLanguage.T("格式化 " + target + " 为 NTFS，卷标 " + (LabelBox.Text ?? "DATA") + "。", "Format " + target + " as NTFS with label " + (LabelBox.Text ?? "DATA") + ".");
            var sizeMb = (SizeBox.Text ?? "0").Trim() + " " + SizeUnitText.Text;
            if (_mode == "split") return UiLanguage.T("把 " + target + " 拆分出 " + sizeMb + " 新分区，卷标 " + (LabelBox.Text ?? "DATA") + "。", "Split " + target + " into a " + sizeMb + " new partition labeled " + (LabelBox.Text ?? "DATA") + ".");
            return UiLanguage.T("在磁盘 " + _disk.Number + " 上创建 " + sizeMb + " 新分区，卷标 " + (LabelBox.Text ?? "DATA") + "。", "Create a " + sizeMb + " partition on disk " + _disk.Number + " labeled " + (LabelBox.Text ?? "DATA") + ".");
        }

        private void ConfirmCancel_Click(object sender, RoutedEventArgs e)
        {
            ConfirmPanel.Visibility = Visibility.Collapsed;
        }

        private void RiskCheck_Changed(object sender, RoutedEventArgs e)
        {
            if (ConfirmButton != null) ConfirmButton.IsEnabled = RiskCheck.IsChecked == true;
        }

        private async void Confirm_Click(object sender, RoutedEventArgs e)
        {
            ConfirmPanel.Visibility = Visibility.Collapsed;
            if (_executing) return;
            if (!_writable)
            {
                StatusText.Text = UiLanguage.T("安全预览：真实磁盘写入尚未授权；请等待测试授权后再执行。", "Safe preview: real-disk writes are not authorized yet.");
                return;
            }
            _executing = true;
            StartButton.IsEnabled = false;
            Progress.Visibility = Visibility.Visible;
            StatusText.Text = UiLanguage.T("执行中…请勿关闭窗口或断电。", "Running… do not close the window or cut power.");

            try
            {
                var logPath = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData),
                    "DiskManager", "operations", "tool-" + _mode + "-" + DateTime.Now.ToString("yyyyMMdd-HHmmss", CultureInfo.InvariantCulture) + ".log");
                var sizeBytes = ParseSizeBytes();
                var label = LabelBox.Text;
                var letter = string.IsNullOrWhiteSpace(LetterBox.Text) ? null : LetterBox.Text.Trim();
                var result = await Task.Run(() => RunOperation(sizeBytes, label, letter, logPath));
                _executed = true;
                _executedSuccess = result != null && result.Success;
                Progress.Visibility = Visibility.Collapsed;
                if (_executedSuccess)
                {
                    StatusText.Text = UiLanguage.T("完成：", "Done: ") + result.Message + UiLanguage.T("  日志：", "  Log: ") + result.LogPath;
                }
                else
                {
                    StatusText.Text = UiLanguage.T("未完成：", "Not completed: ") + (result == null ? UiLanguage.T("未知错误", "Unknown error") : result.Message);
                    if (result != null && !string.IsNullOrEmpty(result.LogPath)) StatusText.Text += UiLanguage.T("  日志：", "  Log: ") + result.LogPath;
                }
            }
            catch (Exception ex)
            {
                _executed = true;
                _executedSuccess = false;
                Progress.Visibility = Visibility.Collapsed;
                StatusText.Text = "异常：" + ex.GetType().Name + ": " + ex.Message;
            }
            finally
            {
                _executing = false;
            }
        }

        private PartitionOperationResult RunOperation(long sizeBytes, string label, string letter, string logPath)
        {
            switch (_mode)
            {
                case "split":
                    return PartitionOperations.Split(_disk, _partition, sizeBytes, "NTFS", label, letter, false, logPath);
                case "format":
                    return PartitionOperations.Format(_disk, _partition, "NTFS", label, false, logPath);
                case "delete":
                    return PartitionOperations.Delete(_disk, _partition, false, logPath);
                default:
                    return PartitionOperations.Create(_disk, sizeBytes, "NTFS", label, letter, false, logPath);
            }
        }

        private long ParseSizeBytes()
        {
            double value;
            var text = (SizeBox.Text ?? "0").Trim();
            if (!double.TryParse(text, NumberStyles.Float, CultureInfo.InvariantCulture, out value) &&
                !double.TryParse(text, NumberStyles.Float, CultureInfo.CurrentCulture, out value))
            {
                value = 0;
            }
            if (value < 0) value = 0;
            return (long)Math.Round(value * (double)(_sizeUseGb ? Gb : Mb));
        }
    }
}
