using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Globalization;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Windows;
using System.Windows.Input;
using System.Windows.Media;
using DiskManager.Core;
using DiskManager.Core.Planning;
using DiskManager.ViewModels;

namespace DiskManager
{
    public sealed class DonorRowVm : INotifyPropertyChanged
    {
        private readonly ExpandCWindow _owner;
        private string _text;

        public DonorRowVm(ExpandCWindow owner, ExpandDonor donor)
        {
            _owner = owner;
            Donor = donor;
        }

        public ExpandDonor Donor { get; private set; }
        public string LetterText { get { return string.IsNullOrEmpty(Donor.Letter) ? UiLanguage.T("分区", "Partition") : Donor.Letter + ":"; } }
        public string DetailText
        {
            get
            {
                return Humanize.Bytes(Donor.Partition.SizeBytes) + " · " + UiLanguage.T("空闲 ", "Free ") + Humanize.Bytes(Donor.Partition.FreeBytes);
            }
        }
        public string UnitText
        {
            get { return Donor.ShrinkBytes >= 1024L * 1024L * 1024L ? "GB" : "MB"; }
        }

        public string Text
        {
            get { return _text; }
            set
            {
                if (_text == value) return;
                _text = value;
                Raise("Text");
                if (!_owner.IsUpdating) _owner.OnDonorText(this);
            }
        }

        public void SetText(string value)
        {
            _text = value;
            Raise("Text");
        }

        public void RaiseUnit()
        {
            Raise("UnitText");
        }

        public event PropertyChangedEventHandler PropertyChanged;
        private void Raise(string name)
        {
            var handler = PropertyChanged;
            if (handler != null) handler(this, new PropertyChangedEventArgs(name));
        }
    }

    public partial class ExpandCWindow : Window
    {
        private const long Gb = 1024L * 1024L * 1024L;
        private const long Mb = 1024L * 1024L;
        private readonly DiskInfo _disk;
        private readonly ExpandCResult _plan;
        private readonly ObservableCollection<DonorRowVm> _rows = new ObservableCollection<DonorRowVm>();
        private bool _unitGb = true;
        private bool _updating;
        private long _growthBytes;

        public ExpandCWindow(DiskInfo disk)
        {
            InitializeComponent();
            _disk = disk;
            DonorList.ItemsSource = _rows;
            if (UiLanguage.English) ApplyEnglishLabels();

            PartitionInfo system = null;
            if (disk != null)
            {
                foreach (var partition in disk.Partitions) if (partition.IsSystem && partition.HasVolume) { system = partition; break; }
                if (system == null) foreach (var partition in disk.Partitions) if (partition.IsBasicData && partition.HasVolume) { system = partition; break; }
            }
            _plan = system == null
                ? new ExpandCResult { Disk = disk, Message = UiLanguage.T("没有找到可扩容的系统分区", "No expandable system partition found") }
                : ExpandCPlanner.Build(disk, system.PartitionNumber);
            Build();
        }

        private void ApplyEnglishLabels()
        {
            Title = "Expand C";
            var map = new System.Collections.Generic.Dictionary<string, string>(StringComparer.Ordinal)
            {
                { "C 盘扩容", "Expand C" },
                { "可扩容约", "Max expandable" },
                { "扩容大小", "Growth size" },
                { "后续分区分摊", "Donor allocation" },
                { "AUTO ALLOCATION · 可手动修改", "AUTO ALLOCATION · editable" },
                { "分区", "Partition" },
                { "当前大小 / 空闲", "Current size / free" },
                { "收缩空间", "Shrink" },
                { "自动分配", "Auto allocate" },
                { "生成计划", "Generate plan" },
                { "填写扩容大小后自动分摊；也可以直接修改每个分区的收缩值。", "Enter growth, or edit each donor shrink value directly." }
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
                TranslateTree(element, map);
            }
        }

        public string ScreenshotPath { get; set; }

        private async void Window_Loaded(object sender, RoutedEventArgs e)
        {
            if (string.IsNullOrEmpty(ScreenshotPath)) return;
            await System.Threading.Tasks.Task.Delay(450);
            try
            {
                UpdateLayout();
                var width = (int)Math.Ceiling(Root.ActualWidth);
                var height = (int)Math.Ceiling(Root.ActualHeight);
                var bitmap = new System.Windows.Media.Imaging.RenderTargetBitmap(width, height, 96, 96, System.Windows.Media.PixelFormats.Pbgra32);
                bitmap.Render(Root);
                var encoder = new System.Windows.Media.Imaging.PngBitmapEncoder();
                encoder.Frames.Add(System.Windows.Media.Imaging.BitmapFrame.Create(bitmap));
                var directory = System.IO.Path.GetDirectoryName(System.IO.Path.GetFullPath(ScreenshotPath));
                if (!string.IsNullOrEmpty(directory)) System.IO.Directory.CreateDirectory(directory);
                using (var stream = System.IO.File.Create(ScreenshotPath)) encoder.Save(stream);
            }
            catch { }
            Close();
        }

        public string UnitText { get { return _unitGb ? "GB" : "MB"; } }
        public bool IsUpdating { get { return _updating; } }

        private void Build()
        {
            if (_disk != null)
            {
                DiskTitle.Text = _disk.DisplayName;
                DiskDetail.Text = UiLanguage.T("磁盘 ", "Disk ") + _disk.Number + " · " + _disk.PartitionStyle + UiLanguage.T(" · 总容量 ", " · Capacity ") + Humanize.Bytes(_disk.SizeBytes);
            }
            _rows.Clear();
            foreach (var donor in _plan.Donors) _rows.Add(new DonorRowVm(this, donor));
            if (UiMax() < Gb) _unitGb = false;
            MaxText.Text = FormatAuto(UiMax());
            GrowthHint.Text = "(0-" + FormatAuto(UiMax()) + ")";
            if (_plan.System != null)
            {
                DiskDetail.Text += UiLanguage.T(" · 目标 ", " · Target ") + (_plan.System.DriveLetter == null ? "C" : _plan.System.DriveLetter) + ":";
            }

            if (!_plan.Valid)
            {
                StatusText.Text = UiLanguage.English
                    ? "No later data partition has reclaimable free space. Max expansion is 0 MB."
                    : (_plan.Message ?? "没有可扩容空间。");
                GrowthBox.IsEnabled = false;
                NextButton.IsEnabled = false;
                _growthBytes = 0;
                UpdateTexts();
                return;
            }
            NextButton.IsEnabled = true;
            var initial = Math.Min(UiMax(), 10 * Gb);
            if (initial < 64 * Mb) initial = UiMax();
            _growthBytes = Quantize(initial);
            UpdateTexts();
            Reallocate();
            StatusText.Text = UiLanguage.T("已按空闲空间自动分摊；可修改任一收缩值，其他分区会自动调整。",
                "Allocated by free space. Edit any shrink value and the others adjust automatically.");
        }

        private void UpdateTexts()
        {
            _updating = true;
            GrowthBox.Text = FormatSelected(_growthBytes);
            UnitGbButton.Style = (Style)FindResource(_unitGb ? "PrimaryButton" : "GhostButton");
            UnitMbButton.Style = (Style)FindResource(_unitGb ? "GhostButton" : "PrimaryButton");
            foreach (var row in _rows) row.RaiseUnit();
            var total = 0L;
            foreach (var row in _rows) total += row.Donor.ShrinkBytes;
            TotalText.Text = UiLanguage.T("已分配 ", "Allocated ") + FormatAuto(total);
            BalanceText.Text = UiLanguage.T("目标 ", "Target ") + FormatAuto(_growthBytes);
            _updating = false;
        }

        private void Reallocate()
        {
            var capacities = new List<long>();
            foreach (var row in _rows) capacities.Add(row.Donor.CapacityBytes);
            var allocations = AllocateQuantized(_growthBytes, capacities, -1, 0);
            _updating = true;
            for (var i = 0; i < _rows.Count; i++)
            {
                _rows[i].Donor.ShrinkBytes = allocations[i];
                _rows[i].SetText(FormatDonor(allocations[i]));
            }
            _updating = false;
            UpdateTexts();
        }

        private long Quantum { get { return (_unitGb ? Gb : Mb) / 10; } }

        private long UiMax()
        {
            var quantum = Quantum;
            long total = 0;
            foreach (var row in _rows) total += (row.Donor.CapacityBytes / quantum) * quantum;
            return total;
        }

        private long Quantize(long bytes)
        {
            var quantum = Quantum;
            return (bytes / quantum) * quantum;
        }

        private List<long> AllocateQuantized(long growthBytes, IList<long> capacities, int fixedIndex, long fixedBytes)
        {
            var quantum = Quantum;
            var growthQuanta = Math.Max(0, growthBytes / quantum);
            var capacityQuanta = new List<long>();
            foreach (var capacity in capacities) capacityQuanta.Add(Math.Max(0, capacity / quantum));
            List<long> allocationQuanta;
            if (fixedIndex >= 0)
            {
                ExpandCPlanner.Reallocate(growthQuanta, capacityQuanta, fixedIndex, Math.Max(0, fixedBytes / quantum), out allocationQuanta);
            }
            else
            {
                allocationQuanta = ExpandCPlanner.Allocate(growthQuanta, capacityQuanta);
            }
            var result = new List<long>();
            foreach (var quanta in allocationQuanta) result.Add(quanta * quantum);
            return result;
        }

        public void OnDonorText(DonorRowVm row)
        {
            if (_updating || !_plan.Valid) return;
            var index = _rows.IndexOf(row);
            if (index < 0) return;
            long bytes;
            var rowUnitGb = string.Equals(row.UnitText, "GB", StringComparison.OrdinalIgnoreCase);
            if (!TryParseWithUnit(row.Text, rowUnitGb, out bytes)) { Reallocate(); return; }
            bytes = Math.Max(0, Math.Min(row.Donor.CapacityBytes, bytes));
            var capacities = new List<long>();
            foreach (var item in _rows) capacities.Add(item.Donor.CapacityBytes);
            var allocations = AllocateQuantized(_growthBytes, capacities, index, bytes);
            _updating = true;
            for (var i = 0; i < _rows.Count; i++)
            {
                _rows[i].Donor.ShrinkBytes = allocations[i];
                _rows[i].SetText(FormatDonor(allocations[i]));
            }
            _updating = false;
            UpdateTexts();
        }

        private void Growth_TextChanged(object sender, System.Windows.Controls.TextChangedEventArgs e)
        {
            if (_updating || !_plan.Valid) return;
            long bytes;
            if (!TryParse(GrowthBox.Text, out bytes)) return;
            if (bytes < 0) bytes = 0;
            if (bytes > UiMax()) bytes = UiMax();
            bytes = Quantize(bytes);
            _growthBytes = bytes;
            var capacities = new List<long>();
            foreach (var row in _rows) capacities.Add(row.Donor.CapacityBytes);
            var allocations = AllocateQuantized(_growthBytes, capacities, -1, 0);
            _updating = true;
            for (var i = 0; i < _rows.Count; i++)
            {
                _rows[i].Donor.ShrinkBytes = allocations[i];
                _rows[i].SetText(FormatDonor(allocations[i]));
            }
            _updating = false;
            UpdateTexts();
        }

        private void AutoAllocate_Click(object sender, RoutedEventArgs e)
        {
            Reallocate();
            StatusText.Text = UiLanguage.T("已按空闲空间重新自动分配。", "Reallocated by free space.");
        }

        private void Donor_LostFocus(object sender, RoutedEventArgs e)
        {
            var box = sender as System.Windows.Controls.TextBox;
            var row = box == null ? null : box.DataContext as DonorRowVm;
            if (row == null) return;
            row.SetText(box.Text);
            OnDonorText(row);
        }

        private void Next_Click(object sender, RoutedEventArgs e)
        {
            long bytes;
            if (!_plan.Valid || !TryParse(GrowthBox.Text, out bytes) || bytes <= 0)
            {
                StatusText.Text = UiLanguage.T("请先填写大于 0 的扩容大小。", "Enter a growth size greater than 0.");
                return;
            }
            if (bytes > UiMax()) { StatusText.Text = UiLanguage.T("扩容大小超过上限。", "Growth exceeds the maximum."); return; }
            _growthBytes = Quantize(bytes);
            Reallocate();
            var parts = new List<string>();
            foreach (var row in _rows) parts.Add(row.LetterText + UiLanguage.T(" 收缩 ", " shrink ") + FormatAuto(row.Donor.ShrinkBytes));
            var plan = string.Join(UiLanguage.T("，", ", "), parts);
            var jobPath = WriteJob();
            StatusText.Text = UiLanguage.English
                ? "Plan generated: C: grow " + FormatAuto(_growthBytes) + "; " + plan +
                  (string.IsNullOrEmpty(jobPath) ? "." : ". Job file: " + jobPath)
                : "计划已生成：C: 扩容 " + FormatAuto(_growthBytes) + "；" + plan +
                  (string.IsNullOrEmpty(jobPath) ? "。" : "。任务文件：" + jobPath);
        }

        private string WriteJob()
        {
            try
            {
                var builder = new StringBuilder();
                builder.AppendLine("{");
                builder.AppendLine("  \"version\": 1,");
                builder.AppendLine("  \"tool\": \"DiskManager\",");
                builder.AppendLine("  \"diskNumber\": " + _disk.Number + ",");
                builder.AppendLine("  \"diskSerial\": \"" + Escape(_disk.Serial) + "\",");
                builder.AppendLine("  \"diskSize\": " + _disk.SizeBytes + ",");
                builder.AppendLine("  \"systemPartition\": " + _plan.System.PartitionNumber + ",");
                builder.AppendLine("  \"systemOffset\": " + _plan.System.OffsetBytes + ",");
                builder.AppendLine("  \"systemSize\": " + _plan.System.SizeBytes + ",");
                builder.AppendLine("  \"growthBytes\": " + _growthBytes + ",");
                builder.AppendLine("  \"donors\": [");
                for (var i = 0; i < _rows.Count; i++)
                {
                    var row = _rows[i];
                    builder.Append("    { \"partition\": " + row.Donor.Partition.PartitionNumber +
                                   ", \"offset\": " + row.Donor.Partition.OffsetBytes +
                                   ", \"size\": " + row.Donor.Partition.SizeBytes +
                                   ", \"shrinkBytes\": " + row.Donor.ShrinkBytes + " }");
                    builder.AppendLine(i + 1 == _rows.Count ? "" : ",");
                }
                builder.AppendLine("  ]");
                var json = builder.ToString();
                var checksum = ComputeSha256(json);
                json = json.TrimEnd() + "," + Environment.NewLine + "  \"sha256\": \"" + checksum + "\"" + Environment.NewLine + "}" + Environment.NewLine;
                var directory = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "DiskManager", "jobs");
                Directory.CreateDirectory(directory);
                var path = Path.Combine(directory, "job-" + DateTime.Now.ToString("yyyyMMdd-HHmmss", CultureInfo.InvariantCulture) + ".json");
                File.WriteAllText(path, json, new UTF8Encoding(false));
                var peDirectory = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "DiskManager", "pe");
                Directory.CreateDirectory(peDirectory);
                File.Copy(path, Path.Combine(peDirectory, "job.json"), true);
                return path;
            }
            catch (Exception ex)
            {
                return "保存失败：" + ex.Message;
            }
        }

        private static string Escape(string value)
        {
            return (value ?? "").Replace("\\", "\\\\").Replace("\"", "\\\"");
        }

        private static string ComputeSha256(string text)
        {
            using (var sha = SHA256.Create())
            {
                var bytes = sha.ComputeHash(Encoding.UTF8.GetBytes(text));
                var builder = new StringBuilder();
                foreach (var b in bytes) builder.Append(b.ToString("x2", CultureInfo.InvariantCulture));
                return builder.ToString();
            }
        }

        private void UnitGb_Click(object sender, RoutedEventArgs e) { SetUnit(true); }
        private void UnitMb_Click(object sender, RoutedEventArgs e) { SetUnit(false); }

        private void SetUnit(bool gb)
        {
            if (_unitGb == gb) return;
            _unitGb = gb;
            if (_growthBytes > UiMax()) _growthBytes = UiMax();
            MaxText.Text = FormatAuto(UiMax());
            GrowthHint.Text = "(0-" + FormatAuto(UiMax()) + ")";
            UpdateTexts();
            Reallocate();
        }

        private bool TryParse(string text, out long bytes)
        {
            return TryParseWithUnit(text, _unitGb, out bytes);
        }

        private static bool TryParseWithUnit(string text, bool gb, out long bytes)
        {
            bytes = 0;
            double value;
            if (!double.TryParse((text ?? "").Trim(), NumberStyles.Float, CultureInfo.InvariantCulture, out value) &&
                !double.TryParse((text ?? "").Trim(), NumberStyles.Float, CultureInfo.CurrentCulture, out value)) return false;
            if (double.IsNaN(value) || double.IsInfinity(value) || value < 0) return false;
            bytes = (long)Math.Round(value * (gb ? Gb : Mb));
            return true;
        }

        private string FormatSelected(long bytes)
        {
            var divisor = _unitGb ? Gb : Mb;
            return (bytes / (double)divisor).ToString("0.0", CultureInfo.InvariantCulture);
        }

        private static string FormatDonor(long bytes)
        {
            if (bytes >= Gb) return (bytes / (double)Gb).ToString("0.0", CultureInfo.InvariantCulture);
            return (bytes / (double)Mb).ToString("0.0", CultureInfo.InvariantCulture);
        }

        private static string FormatAuto(long bytes)
        {
            if (bytes <= 0) return "0 MB";
            if (bytes >= Gb) return (bytes / (double)Gb).ToString("0.0", CultureInfo.InvariantCulture) + " GB";
            return (bytes / (double)Mb).ToString("0.0", CultureInfo.InvariantCulture) + " MB";
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

        private void Close_Click(object sender, RoutedEventArgs e) { Close(); }

        private void Window_PreviewKeyDown(object sender, System.Windows.Input.KeyEventArgs e)
        {
            if (e.Key == System.Windows.Input.Key.Escape) Close();
        }
    }
}
