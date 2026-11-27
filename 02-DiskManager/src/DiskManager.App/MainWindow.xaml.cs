using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Data;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using DiskManager.ViewModels;

namespace DiskManager
{
    public partial class MainWindow : Window
    {
        private readonly MainViewModel _viewModel;

        public MainWindow()
        {
            InitializeComponent();
            _viewModel = new MainViewModel();
            DataContext = _viewModel;
        }

        public string ScreenshotPath { get; set; }
        public int ScreenshotWidth { get; set; }
        public int ScreenshotHeight { get; set; }
        public string InitialSelection { get; set; }
        public bool StartEnglish { get; set; }

        private async void Window_Loaded(object sender, RoutedEventArgs e)
        {
            if (ScreenshotWidth > 0) Width = ScreenshotWidth;
            if (ScreenshotHeight > 0) Height = ScreenshotHeight;
            UpdateLayout();

            var windowShownAt = DateTime.Now;
            var processStart = Process.GetCurrentProcess().StartTime;
            var loadStart = Stopwatch.StartNew();
            if (StartEnglish)
            {
                UiLanguage.English = true;
                _english = true;
            }
            await _viewModel.LoadAsync();
            loadStart.Stop();
            ApplyInitialSelection();
            if (StartEnglish) ApplyShellLanguage();

            if (!string.IsNullOrEmpty(ScreenshotPath))
            {
                await Task.Delay(550);
                try
                {
                    CaptureScreenshot(ScreenshotPath);
                    var timing = "process_to_window_loaded_ms=" + Math.Max(0, (windowShownAt - processStart).TotalMilliseconds).ToString("0") + Environment.NewLine +
                                 "scan_ms=" + loadStart.ElapsedMilliseconds + Environment.NewLine +
                                 "scan_duration_ms=" + _viewModel.LastScanDurationMs + Environment.NewLine;
                    File.WriteAllText(ScreenshotPath + ".timing.txt", timing);
                }
                catch (Exception ex)
                {
                    MessageBox.Show("截图失败: " + ex.Message, "DiskManager", MessageBoxButton.OK, MessageBoxImage.Warning);
                }
                Close();
            }
        }

        private bool _english;
        private bool _languageBusy;

        private static readonly System.Collections.Generic.Dictionary<string, string> EnText =
            new System.Collections.Generic.Dictionary<string, string>(StringComparer.Ordinal)
            {
                { "物理磁盘", "PHYSICAL DISKS" },
                { "系统盘", "System disk" },
                { "数据盘", "Data disk" },
                { "全机容量", "Total capacity" },
                { "空闲", "Free" },
                { "总容量", "Capacity" },
                { "已用", "Used" },
                { "扫描", "Scan" },
                { "使用提示", "Tips" },
                { "点击左侧磁盘，中间切换该盘的分区布局。", "Select a disk on the left to inspect its layout." },
                { "悬停分区色条可查看卷标、容量与空闲。", "Hover a partition block for label, size and free space." },
                { "写操作会先弹出确认窗口；未授权时不写真实分区表。", "Every write opens a confirmation dialog; real disks stay untouched until authorized." },
                { "分区布局", "Partition layout" },
                { "LAYOUT · 悬停查看详情", "LAYOUT · hover for details" },
                { "隐藏/保留", "Hidden" },
                { "未分配", "Unallocated" },
                { "分区详情", "Partition details" },
                { "类型", "Type" },
                { "文件系统", "File system" },
                { "容量", "Size" },
                { "偏移", "Offset" },
                { "卷 GUID", "Volume GUID" },
                { "磁盘测速", "Disk speed" },
                { "操作安全", "Write safety" },
                { "所有分区写操作都会先进入确认窗口。当前构建未授权写入真实磁盘；真实盘上的执行会被拒绝，不会修改分区表。", "Every write requires confirmation. Real-disk writes are not authorized in this build and will be refused." },
                { "本地磁盘 · 分区管理", "Local disks · partition manager" },
                { "快捷功能", "Quick action" },
                { "C 盘扩容", "Expand C" },
                { "从同一块物理磁盘后续的数据分区回收空间，把 C 盘边界右移；只有存在可移动分区时才可扩容。", "Reclaim free space from later partitions on the same physical disk and move the C boundary right." },
                { "先计算可扩容上限，再分配各分区收缩量。", "Calculate the maximum, then distribute the shrink amount." },
                { "打开扩容向导", "Open expansion wizard" },
                { "新建分区", "New" },
                { "拆分分区", "Split" },
                { "格式化", "Format" },
                { "删除", "Delete" },
                { "刷新磁盘", "Refresh" },
                { "管理员", "Administrator" },
                { "选择分区", "Select a partition" },
                { "在上方分区布局或列表中选择", "Pick a partition above" },
                { "卷", "Vol" },
                { "状态", "Status" },
                { "空闲空间", "Free space" },
                { "磁盘", "Disk" },
                { "分区", "Partition" },
                { "保留分区", "Reserved" },
                { "在线", "Online" },
                { "正常", "Normal" },
                { "隐藏", "Hidden" }
            };

        private async void Language_Click(object sender, RoutedEventArgs e)
        {
            if (_languageBusy) return;
            _languageBusy = true;
            LanguageButton.IsEnabled = false;
            try
            {
                _english = !_english;
                UiLanguage.English = _english;
                ApplyShellLanguage();
                await _viewModel.LoadAsync();
                ApplyLanguage(this, _english ? EnText : Reverse(EnText));
            }
            finally
            {
                LanguageButton.IsEnabled = true;
                _languageBusy = false;
            }
        }

        private void ApplyShellLanguage()
        {
            Title = _english ? "DiskManager" : "磁盘管理器 · DiskManager";
            LanguageButton.Content = _english ? "EN / 中" : "中 / EN";
            BrandChinese.Visibility = _english ? Visibility.Collapsed : Visibility.Visible;
            FooterVersion.Text = _english
                ? "DiskManager v1.0.0 · portable single file · by cbd"
                : "DiskManager v1.0.0 · 单文件便携版 · by cbd";
            ApplyLanguage(this, _english ? EnText : Reverse(EnText));
        }

        private static System.Collections.Generic.Dictionary<string, string> Reverse(System.Collections.Generic.Dictionary<string, string> source)
        {
            var result = new System.Collections.Generic.Dictionary<string, string>(StringComparer.Ordinal);
            foreach (var pair in source) if (!result.ContainsKey(pair.Value)) result[pair.Value] = pair.Key;
            return result;
        }

        private static void ApplyLanguage(DependencyObject root, System.Collections.Generic.Dictionary<string, string> map)
        {
            if (root == null) return;
            foreach (var child in LogicalTreeHelper.GetChildren(root))
            {
                var element = child as DependencyObject;
                if (element == null) continue;
                var text = element as System.Windows.Controls.TextBlock;
                if (text != null && !BindingOperations.IsDataBound(text, System.Windows.Controls.TextBlock.TextProperty))
                {
                    string translated;
                    if (map.TryGetValue(text.Text ?? "", out translated)) text.Text = translated;
                }
                var button = element as System.Windows.Controls.Button;
                if (button != null && !BindingOperations.IsDataBound(button, System.Windows.Controls.ContentControl.ContentProperty))
                {
                    var content = button.Content as string;
                    string translated;
                    if (content != null && map.TryGetValue(content, out translated)) button.Content = translated;
                }
                ApplyLanguage(element, map);
            }
        }

        private void Window_SourceInitialized(object sender, EventArgs e)
        {
            WindowFx.Apply(this, false);
        }

        private void ApplyInitialSelection()
        {
            var letter = InitialSelection;
            if (string.IsNullOrEmpty(letter)) return;
            letter = letter.Trim().TrimEnd(':');
            foreach (var disk in _viewModel.Disks)
            {
                var partition = disk.Partitions.FirstOrDefault(p => string.Equals(p.Source.DriveLetter, letter, StringComparison.OrdinalIgnoreCase));
                if (partition == null) continue;
                _viewModel.SelectedDisk = disk;
                _viewModel.SelectedPartition = partition;
                return;
            }
        }

        private void Window_StateChanged(object sender, EventArgs e)
        {
            WindowFx.Apply(this, WindowState == WindowState.Maximized);
        }

        private void TitleBar_MouseLeftButtonDown(object sender, MouseButtonEventArgs e)
        {
            if (e.ClickCount == 2)
            {
                WindowState = WindowState == WindowState.Maximized ? WindowState.Normal : WindowState.Maximized;
                return;
            }
            if (e.ButtonState == MouseButtonState.Pressed)
            {
                try
                {
                    DragMove();
                }
                catch (InvalidOperationException)
                {
                    // DragMove can race with a released button; nothing to recover.
                }
            }
        }

        private void Minimize_Click(object sender, RoutedEventArgs e)
        {
            WindowState = WindowState.Minimized;
        }

        private void Maximize_Click(object sender, RoutedEventArgs e)
        {
            WindowState = WindowState == WindowState.Maximized ? WindowState.Normal : WindowState.Maximized;
        }

        private void Close_Click(object sender, RoutedEventArgs e)
        {
            Close();
        }

        private async void Plan_Click(object sender, RoutedEventArgs e)
        {
            var disk = _viewModel.SelectedDisk;
            if (disk == null || !_viewModel.CanExpandC) return;
            var window = new ExpandCWindow(disk.Source) { Owner = this };
            window.ShowDialog();
            await Task.CompletedTask;
        }

        private async void CreatePartition_Click(object sender, RoutedEventArgs e)
        {
            await OpenPartitionTools("create");
        }

        private async void SplitPartition_Click(object sender, RoutedEventArgs e)
        {
            await OpenPartitionTools("split");
        }

        private async void FormatPartition_Click(object sender, RoutedEventArgs e)
        {
            await OpenPartitionTools("format");
        }

        private async void DeletePartition_Click(object sender, RoutedEventArgs e)
        {
            await OpenPartitionTools("delete");
        }

        private async Task OpenPartitionTools(string mode)
        {
            var disk = _viewModel.SelectedDisk;
            if (disk == null) return;
            var partition = _viewModel.SelectedPartition == null ? null : _viewModel.SelectedPartition.Source;
            if (mode != "create" && partition == null) return;
            var window = new PartitionToolsWindow(disk.Source, partition, mode) { Owner = this };
            window.ShowDialog();
            if (window.Executed) await _viewModel.LoadAsync();
        }

        private void CaptureScreenshot(string path)
        {
            Root.UpdateLayout();
            var width = (int)Math.Ceiling(Root.ActualWidth);
            var height = (int)Math.Ceiling(Root.ActualHeight);
            if (width <= 0 || height <= 0) throw new InvalidOperationException("窗口尺寸无效");

            var bitmap = new RenderTargetBitmap(width, height, 96, 96, PixelFormats.Pbgra32);
            bitmap.Render(Root);

            var directory = Path.GetDirectoryName(Path.GetFullPath(path));
            if (!string.IsNullOrEmpty(directory)) Directory.CreateDirectory(directory);

            var encoder = new PngBitmapEncoder();
            encoder.Frames.Add(BitmapFrame.Create(bitmap));
            using (var stream = File.Create(path))
            {
                encoder.Save(stream);
            }
        }
    }
}
