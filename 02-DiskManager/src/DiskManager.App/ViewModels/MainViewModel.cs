using System;

using System.Collections.Generic;

using System.Collections.ObjectModel;

using System.Linq;

using System.Threading.Tasks;

using System.Windows.Input;

using DiskManager.Controls;

using DiskManager.Core;

using DiskManager.Core.Engine;



namespace DiskManager.ViewModels;



public sealed class MainViewModel : ObservableObject

{

	private readonly RelayCommand _refreshCommand;



	private bool _isScanning;



	private string _statusText = "正在等待扫描";



	private string _lastScanText = "—";



	private string _scanSummaryText = "—";



	private string _machineText = "—";



	private bool _isElevated;



	private string _errorText;



	private DiskViewModel _selectedDisk;



	private PartitionViewModel _selectedPartition;



	private bool _hasLowSpace;



	private string _lowSpaceText;



	private ObservableCollection<PartitionMapItem> _mapItems = new ObservableCollection<PartitionMapItem>();



	private string _totalCapacityText = "—";



	private string _totalFreeText = "—";



	private string _totalUsedText = "—";



	private double _totalUsagePercent;



	private string _scanDurationText = "—";



	private string _reservedSummaryText = null;



	public ObservableCollection<DiskViewModel> Disks { get; private set; }



	public ObservableCollection<PartitionMapItem> MapItems

	{

		get

		{

			return _mapItems;

		}

		private set

		{

			Set(ref _mapItems, value, "MapItems");

		}

	}



	public ICommand RefreshCommand { get; private set; }



	public bool IsScanning

	{

		get

		{

			return _isScanning;

		}

		private set

		{

			if (Set(ref _isScanning, value, "IsScanning"))

			{

				_refreshCommand.RaiseCanExecuteChanged();

			}

		}

	}



	public string StatusText

	{

		get

		{

			return _statusText;

		}

		private set

		{

			Set(ref _statusText, value, "StatusText");

		}

	}



	public string LastScanText

	{

		get

		{

			return _lastScanText;

		}

		private set

		{

			Set(ref _lastScanText, value, "LastScanText");

		}

	}



	public string ScanSummaryText

	{

		get

		{

			return _scanSummaryText;

		}

		private set

		{

			Set(ref _scanSummaryText, value, "ScanSummaryText");

		}

	}



	public string MachineText

	{

		get

		{

			return _machineText;

		}

		private set

		{

			Set(ref _machineText, value, "MachineText");

		}

	}



	public bool IsElevated

	{

		get

		{

			return _isElevated;

		}

		private set

		{

			Set(ref _isElevated, value, "IsElevated");

		}

	}



	public string ErrorText

	{

		get

		{

			return _errorText;

		}

		private set

		{

			Set(ref _errorText, value, "ErrorText");

		}

	}



	public bool HasError => !string.IsNullOrEmpty(ErrorText);



	public string VersionText => "v1.0.0";



	public DiskViewModel SelectedDisk

	{

		get

		{

			return _selectedDisk;

		}

		set

		{

			if (!Set(ref _selectedDisk, value, "SelectedDisk"))

			{

				return;

			}

			if (value == null)

			{

				SelectedPartition = null;

				BuildMap();

				return;

			}

			PartitionViewModel selectedPartition = value.Partitions.FirstOrDefault((PartitionViewModel p) => p.Source.IsSystem && p.Source.HasVolume) ?? value.Partitions.FirstOrDefault((PartitionViewModel p) => p.Source.HasVolume) ?? value.Partitions.FirstOrDefault();

			SelectedPartition = selectedPartition;

			BuildMap();

			OnPropertyChanged("SelectedDiskTitle");

			NotifyPartitionTools();

		}

	}



	public bool IsVirtualDisk => SelectedDisk != null && string.Equals(SelectedDisk.Source.BusType, "FileBackedVirtual", StringComparison.OrdinalIgnoreCase);



	public bool CanCreatePartition => SelectedDisk != null;



	public bool CanOperatePartition

	{

		get

		{

			if (SelectedDisk == null || SelectedPartition == null)

			{

				return false;

			}

			PartitionInfo source = SelectedPartition.Source;

			return source.IsBasicData && !source.IsSystem && !source.IsBoot && !source.IsEfi && !source.IsMsr && !source.IsRecovery;

		}

	}



	public string PartitionToolHint

	{

		get

		{

			if (SelectedDisk == null)

			{

				return UiLanguage.T("先选择磁盘。", "Select a disk first.");

			}

			if (SelectedPartition == null)

			{

				return UiLanguage.T("选择分区后可拆分、格式化或删除。", "Select a partition to split, format or delete.");

			}

			if (!IsVirtualDisk)

			{

				return UiLanguage.T("当前安全模式：操作流程可预览，真实磁盘写入尚未授权。", "Safe mode: real-disk writes are not authorized in this build.");

			}

			return UiLanguage.T("操作前会二次确认；新建分区使用磁盘未分配空间。", "Writes require confirmation; new partitions use unallocated space.");

		}

	}



	public bool CanExpandC

	{

		get

		{

			if (SelectedDisk == null)

			{

				return false;

			}

			foreach (PartitionViewModel partition in SelectedDisk.Partitions)

			{

				if (partition.Source.IsSystem && partition.Source.HasVolume)

				{

					return true;

				}

			}

			return false;

		}

	}



	public string ExpandCHint => CanExpandC ? UiLanguage.T("打开 C 盘扩容向导", "Open the C: expansion wizard") : UiLanguage.T("请选择包含系统分区的磁盘", "Select a disk containing the system partition");



	public string SelectedDiskTitle => (SelectedDisk == null) ? UiLanguage.T("选择磁盘", "Select a disk") : SelectedDisk.Title;



	public PartitionViewModel SelectedPartition

	{

		get

		{

			return _selectedPartition;

		}

		set

		{

			if (Set(ref _selectedPartition, value, "SelectedPartition"))

			{

				BuildMap();

				OnPropertyChanged("HasSelectedPartition");

				NotifyPartitionTools();

			}

		}

	}



	public bool HasSelectedPartition => SelectedPartition != null;



	public string DiskCountText => Disks.Count.ToString();



	public string TotalCapacityText

	{

		get

		{

			return _totalCapacityText;

		}

		private set

		{

			if (Set(ref _totalCapacityText, value, "TotalCapacityText"))

			{

				OnPropertyChanged("TotalCapacityDisplayText");

			}

		}

	}



	public string TotalFreeText

	{

		get

		{

			return _totalFreeText;

		}

		private set

		{

			if (Set(ref _totalFreeText, value, "TotalFreeText"))

			{

				OnPropertyChanged("TotalFreeDisplayText");

			}

		}

	}



	public string TotalUsedText

	{

		get

		{

			return _totalUsedText;

		}

		private set

		{

			if (Set(ref _totalUsedText, value, "TotalUsedText"))

			{

				OnPropertyChanged("TotalUsedDisplayText");

			}

		}

	}



	public string TotalCapacityDisplayText => UiLanguage.T("总容量 ", "Capacity ") + TotalCapacityText;



	public string TotalFreeDisplayText => UiLanguage.T("空闲 ", "Free ") + TotalFreeText;



	public string TotalUsedDisplayText => UiLanguage.T("已用 ", "Used ") + TotalUsedText;



	public double TotalUsagePercent

	{

		get

		{

			return _totalUsagePercent;

		}

		private set

		{

			Set(ref _totalUsagePercent, value, "TotalUsagePercent");

		}

	}



	public string TotalUsagePercentText => _totalUsagePercent.ToString("0") + "%";



	public string ScanDurationText

	{

		get

		{

			return _scanDurationText;

		}

		private set

		{

			if (Set(ref _scanDurationText, value, "ScanDurationText"))

			{

				OnPropertyChanged("ScanDurationDisplayText");

			}

		}

	}



	public string ScanDurationDisplayText => UiLanguage.T("扫描 ", "Scan ") + ScanDurationText;



	public long LastScanDurationMs { get; private set; }



	public string ReservedSummaryText

	{

		get

		{

			return _reservedSummaryText;

		}

		private set

		{

			if (Set(ref _reservedSummaryText, value, "ReservedSummaryText"))

			{

				OnPropertyChanged("HasReservedPartitions");

			}

		}

	}



	public bool HasReservedPartitions => !string.IsNullOrEmpty(ReservedSummaryText);



	public bool HasLowSpace

	{

		get

		{

			return _hasLowSpace;

		}

		private set

		{

			Set(ref _hasLowSpace, value, "HasLowSpace");

		}

	}



	public string LowSpaceText

	{

		get

		{

			return _lowSpaceText;

		}

		private set

		{

			Set(ref _lowSpaceText, value, "LowSpaceText");

		}

	}



	public MainViewModel()

	{

		Disks = new ObservableCollection<DiskViewModel>();

		_refreshCommand = new RelayCommand(delegate(object _)

		{

			if (!IsScanning)

			{

				_ = LoadAsync();

			}

		}, (object _) => !IsScanning);

		RefreshCommand = _refreshCommand;

	}



	private void NotifyPartitionTools()

	{

		OnPropertyChanged("IsVirtualDisk");

		OnPropertyChanged("CanCreatePartition");

		OnPropertyChanged("CanOperatePartition");

		OnPropertyChanged("PartitionToolHint");

		OnPropertyChanged("CanExpandC");

		OnPropertyChanged("ExpandCHint");

	}



	public async Task LoadAsync()

	{

		if (IsScanning)

		{

			return;

		}

		IsScanning = true;

		ErrorText = null;

		StatusText = UiLanguage.T("正在读取磁盘布局…", "Reading disk layout…");

		int previousDiskNumber = ((SelectedDisk == null) ? (-1) : SelectedDisk.Source.Number);

		string previousLetter = ((SelectedPartition == null) ? null : SelectedPartition.Source.DriveLetter);

		try

		{

			ApplyResult(await Task.Run(() => DiskScanner.Scan(new ScanOptions())), previousDiskNumber, previousLetter);

		}

		catch (Exception ex2)

		{

			Exception ex = ex2;

			ErrorText = ex.Message;

			StatusText = UiLanguage.T("扫描失败", "Scan failed");

			OnPropertyChanged("HasError");

		}

		finally

		{

			IsScanning = false;

		}

	}



	private void ApplyResult(ScanResult result, int previousDiskNumber, string previousLetter)

	{

		Disks.Clear();

		foreach (DiskInfo disk in result.Disks)

		{

			Disks.Add(new DiskViewModel(disk));

		}

		IsElevated = result.IsElevated;

		MachineText = result.MachineName + " · " + result.OsDescription;

		LastScanText = UiLanguage.T("扫描于 ", "Scanned ") + DateTime.Now.ToString("HH:mm:ss");

		ScanSummaryText = (UiLanguage.English ? (result.Disks.Count + " disks · " + result.VolumeCount + " volumes") : (result.Disks.Count + " 块磁盘 · " + result.VolumeCount + " 个卷"));

		ScanDurationText = result.DurationMs + " ms";

		LastScanDurationMs = result.DurationMs;

		StatusText = ((result.Errors.Count == 0) ? UiLanguage.T("就绪 · 分区管理", "Ready · Partition manager") : UiLanguage.T("完成，有 " + result.Errors.Count + " 条扫描提示", "Done with " + result.Errors.Count + " scan notices"));

		long num = 0L;

		long num2 = 0L;

		long num3 = 0L;

		foreach (DiskInfo disk2 in result.Disks)

		{

			num += disk2.SizeBytes;

			num2 += disk2.UsageFreeBytes;

			num3 += Math.Max(0L, disk2.UsageTotalBytes - disk2.UsageFreeBytes);

		}

		TotalCapacityText = Humanize.Bytes(num);

		TotalFreeText = Humanize.Bytes(num2);

		TotalUsedText = Humanize.Bytes(num3);

		TotalUsagePercent = ((num > 0) ? Math.Max(0.0, Math.Min(100.0, (double)num3 * 100.0 / (double)num)) : 0.0);

		OnPropertyChanged("TotalUsagePercentText");

		if (result.Errors.Count > 0 && ErrorText == null)

		{

			ErrorText = string.Join("\n", result.Errors);

			OnPropertyChanged("HasError");

		}

		DiskInfo systemDisk = result.Disks.FirstOrDefault((DiskInfo d) => d.IsSystemDisk);

		DiskViewModel diskViewModel2 = (SelectedDisk = Disks.FirstOrDefault((DiskViewModel d) => d.Source.Number == previousDiskNumber) ?? Disks.FirstOrDefault((DiskViewModel d) => d.Source.Number == ((systemDisk == null) ? (-1) : systemDisk.Number)) ?? Disks.FirstOrDefault());

		if (diskViewModel2 != null && !string.IsNullOrEmpty(previousLetter))

		{

			PartitionViewModel partitionViewModel = diskViewModel2.Partitions.FirstOrDefault((PartitionViewModel p) => string.Equals(p.Source.DriveLetter, previousLetter, StringComparison.OrdinalIgnoreCase));

			if (partitionViewModel != null)

			{

				SelectedPartition = partitionViewModel;

			}

		}

		UpdateLowSpace();

		OnPropertyChanged("DiskCountText");

		OnPropertyChanged("HasError");

	}



	private void UpdateLowSpace()

	{

		foreach (DiskViewModel disk in Disks)

		{

			foreach (PartitionViewModel partition in disk.Partitions)

			{

				if (partition.IsLowSpace)

				{

					HasLowSpace = true;

					LowSpaceText = (UiLanguage.English ? (partition.LetterText.TrimEnd(':') + ": " + partition.FreeText + " free (" + partition.FreePercentText + "). Move data to another partition or clean up.") : (partition.LetterText.TrimEnd(':') + ": 剩余 " + partition.FreeText + "（" + partition.FreePercentText + "），建议搬到同一磁盘的其他分区或清理文件。"));

					return;

				}

			}

		}

		HasLowSpace = false;

		LowSpaceText = null;

	}



	private void BuildMap()

	{

		List<PartitionMapItem> list = new List<PartitionMapItem>();

		if (SelectedDisk != null)

		{

			long sizeBytes = SelectedDisk.Source.SizeBytes;

			long num = 0L;

			foreach (PartitionViewModel item in SelectedDisk.Partitions.OrderBy((PartitionViewModel p) => p.Source.OffsetBytes))

			{

				if (item.Source.OffsetBytes > num)

				{

					long num2 = item.Source.OffsetBytes - num;

					if (num2 >= 67108864)

					{

						list.Add(new PartitionMapItem

						{

							StartBytes = num,

							SizeBytes = num2,

							Label = UiLanguage.T("未分配", "Unallocated"),

							Detail = UiLanguage.T("未分配空间 ", "Unallocated ") + Humanize.Bytes(num2),

							IsUnallocated = true,

							Fill = UiBrush.Get("MapFree"),

							TextBrush = UiBrush.Get("MapTextMuted")

						});

					}

				}

				list.Add(new PartitionMapItem

				{

					StartBytes = item.Source.OffsetBytes,

					SizeBytes = item.Source.SizeBytes,

					Label = item.MapLabel,

					Detail = item.MapDetail,

					IsUnallocated = false,

					IsSelected = (item == SelectedPartition),

					Fill = item.MapBrush,

					TextBrush = item.MapTextBrush

				});

				num = item.Source.OffsetBytes + item.Source.SizeBytes;

			}

			if (sizeBytes > num + 67108864)

			{

				list.Add(new PartitionMapItem

				{

					StartBytes = num,

					SizeBytes = sizeBytes - num,

					Label = UiLanguage.T("未分配", "Unallocated"),

					Detail = UiLanguage.T("未分配空间 ", "Unallocated ") + Humanize.Bytes(sizeBytes - num),

					IsUnallocated = true,

					Fill = UiBrush.Get("MapFree"),

					TextBrush = UiBrush.Get("MapTextMuted")

				});

			}

		}

		MapItems = new ObservableCollection<PartitionMapItem>(list);

		if (SelectedDisk == null)

		{

			ReservedSummaryText = null;

			return;

		}

		List<string> list2 = new List<string>();

		foreach (PartitionViewModel partition in SelectedDisk.Partitions)

		{

			if (partition.Source.IsHidden && partition.Source.SizeBytes > 0)

			{

				list2.Add(partition.MapLabel + " " + partition.SizeText);

			}

		}

		ReservedSummaryText = ((list2.Count == 0) ? null : (UiLanguage.T("保留分区：", "Reserved: ") + string.Join("  ·  ", list2)));

	}

}

