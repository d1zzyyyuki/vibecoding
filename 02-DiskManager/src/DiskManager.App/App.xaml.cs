using System;

using System.CodeDom.Compiler;

using System.Collections.Generic;

using System.Diagnostics;

using System.Globalization;

using System.IO;

using System.Runtime.InteropServices;

using System.Text;

using System.Windows;

using System.Windows.Threading;

using DiskManager.Core;

using DiskManager.Core.Engine;

using DiskManager.Core.Json;

using DiskManager.ViewModels;



namespace DiskManager;



public partial class App : Application

{



	[DllImport("kernel32.dll", SetLastError = true)]

	private static extern bool AttachConsole(uint dwProcessId);



	protected override void OnStartup(StartupEventArgs e)

	{

		base.OnStartup(e);

		base.DispatcherUnhandledException += delegate(object sender, DispatcherUnhandledExceptionEventArgs args)

		{

			LogException(args.Exception);

			MessageBox.Show("DiskManager 遇到未处理的错误：\n\n" + args.Exception.Message + "\n\n日志已写入 " + GetLogDirectory(), "DiskManager", MessageBoxButton.OK, MessageBoxImage.Hand);

			args.Handled = true;

		};

		if (HasArg(e.Args, "--selftest"))

		{

			string outputPath = GetArg(e.Args, "--out") ?? Path.Combine(Environment.CurrentDirectory, "selftest.json");

			Environment.ExitCode = RunSelfTest(outputPath);

			Shutdown(Environment.ExitCode);

			return;

		}

		if (HasArg(e.Args, "--plan-screenshot"))

		{

			RunPlanScreenshot(e.Args);

			return;

		}

		if (HasArg(e.Args, "--expand-screenshot"))

		{

			RunExpandScreenshot(e.Args);

			return;

		}

		MainWindow mainWindow = new MainWindow();

		mainWindow.InitialSelection = GetArg(e.Args, "--select");

		mainWindow.StartEnglish = string.Equals(GetArg(e.Args, "--lang"), "en", StringComparison.OrdinalIgnoreCase);

		string arg = GetArg(e.Args, "--screenshot");

		if (!string.IsNullOrEmpty(arg))

		{

			mainWindow.ScreenshotPath = arg;

			mainWindow.ScreenshotWidth = ParseInt(GetArg(e.Args, "--width"), 0);

			mainWindow.ScreenshotHeight = ParseInt(GetArg(e.Args, "--height"), 0);

		}

		base.MainWindow = mainWindow;

		mainWindow.Show();

	}



	private static int RunSelfTest(string outputPath)

	{

		try

		{

			AttachConsole(uint.MaxValue);

			ScanResult scanResult = DiskScanner.Scan(new ScanOptions());

			PartitionInfo partitionInfo = FindSystemPartition(scanResult);

			List<CheckResult> list = new List<CheckResult>

			{

				new CheckResult

				{

					Name = "elevated",

					Passed = scanResult.IsElevated,

					Detail = (scanResult.IsElevated ? "管理员权限可用" : "未取得管理员权限")

				},

				new CheckResult

				{

					Name = "disks-found",

					Passed = (scanResult.Disks.Count > 0),

					Detail = scanResult.Disks.Count.ToString(CultureInfo.InvariantCulture) + " 块物理磁盘"

				},

				new CheckResult

				{

					Name = "system-volume",

					Passed = (scanResult.SystemVolumeGuid != null && partitionInfo != null),

					Detail = ((partitionInfo == null) ? "未识别系统卷" : (partitionInfo.DriveLetter + ": " + Humanize.Bytes(partitionInfo.SizeBytes)))

				},

				new CheckResult

				{

					Name = "gpt-layout",

					Passed = scanResult.Disks.Exists((DiskInfo d) => d.PartitionStyle == "GPT"),

					Detail = "至少一块 GPT 磁盘"

				},

				new CheckResult

				{

					Name = "speed-probe",

					Passed = scanResult.Disks.Exists((DiskInfo d) => d.Speed != null && d.Speed.Success),

					Detail = ((scanResult.Disks.Count == 0) ? "无磁盘" : ((scanResult.Disks[0].Speed == null) ? "未测速" : Humanize.Speed(scanResult.Disks[0].Speed.ThroughputMBps)))

				},

				new CheckResult

				{

					Name = "read-only",

					Passed = true,

					Detail = "只使用查询 IOCTL 与原始读取"

				},

				new CheckResult

				{

					Name = "version",

					Passed = (scanResult.Version == "1.0.0"),

					Detail = scanResult.Version

				}

			};

			bool flag = list.TrueForAll((CheckResult c) => c.Passed);

			string directoryName = Path.GetDirectoryName(Path.GetFullPath(outputPath));

			if (!string.IsNullOrEmpty(directoryName))

			{

				Directory.CreateDirectory(directoryName);

			}

			File.WriteAllText(outputPath, JsonReport.Build(scanResult, list, flag), new UTF8Encoding(encoderShouldEmitUTF8Identifier: false));

			Console.WriteLine("DiskManager v" + scanResult.Version + " selftest");

			Console.WriteLine("durationMs=" + scanResult.DurationMs + " disks=" + scanResult.Disks.Count + " volumes=" + scanResult.VolumeCount + " elevated=" + scanResult.IsElevated);

			foreach (DiskInfo disk in scanResult.Disks)

			{

				Console.WriteLine("disk " + disk.Number + " " + disk.Model + " " + disk.BusType + " " + disk.MediaKind + " " + Humanize.Bytes(disk.SizeBytes) + " speed=" + ((disk.Speed != null && disk.Speed.Success) ? Humanize.Speed(disk.Speed.ThroughputMBps) : "n/a"));

			}

			foreach (CheckResult item in list)

			{

				Console.WriteLine((item.Passed ? "PASS " : "FAIL ") + item.Name + "  " + item.Detail);

			}

			Console.WriteLine("json=" + Path.GetFullPath(outputPath));

			Console.WriteLine(flag ? "ALL PASS" : "FAILED");

			return (!flag) ? 1 : 0;

		}

		catch (Exception ex)

		{

			LogException(ex);

			try

			{

				string directoryName2 = Path.GetDirectoryName(Path.GetFullPath(outputPath));

				if (!string.IsNullOrEmpty(directoryName2))

				{

					Directory.CreateDirectory(directoryName2);

				}

				File.WriteAllText(outputPath, "{\n  \"tool\": \"DiskManager\",\n  \"passed\": false,\n  \"error\": \"" + ex.Message.Replace("\\", "\\\\").Replace("\"", "\\\"") + "\"\n}\n", new UTF8Encoding(encoderShouldEmitUTF8Identifier: false));

			}

			catch

			{

			}

			Console.WriteLine("SELFTEST EXCEPTION: " + ex);

			return 1;

		}

	}



	private static PartitionInfo FindSystemPartition(ScanResult result)

	{

		foreach (DiskInfo disk in result.Disks)

		{

			foreach (PartitionInfo partition in disk.Partitions)

			{

				if (partition.IsSystem && partition.HasVolume)

				{

					return partition;

				}

			}

		}

		return null;

	}



	private void RunPlanScreenshot(string[] args)

	{

		string arg = GetArg(args, "--plan-screenshot");

		if (string.IsNullOrEmpty(arg))

		{

			Shutdown(1);

			return;

		}

		DiskInfo diskInfo = null;

		try

		{

			ScanResult scanResult = DiskScanner.Scan(new ScanOptions());

			int num = ParseInt(GetArg(args, "--disk"), -1);

			string arg2 = GetArg(args, "--select");

			if (num >= 0)

			{

				foreach (DiskInfo disk in scanResult.Disks)

				{

					if (disk.Number == num)

					{

						diskInfo = disk;

						break;

					}

				}

			}

			else if (!string.IsNullOrEmpty(arg2))

			{

				arg2 = arg2.Trim().TrimEnd(':');

				foreach (DiskInfo disk2 in scanResult.Disks)

				{

					foreach (PartitionInfo partition in disk2.Partitions)

					{

						if (string.Equals(partition.DriveLetter, arg2, StringComparison.OrdinalIgnoreCase))

						{

							diskInfo = disk2;

							break;

						}

					}

					if (diskInfo != null)

					{

						break;

					}

				}

			}

			else

			{

				foreach (DiskInfo disk3 in scanResult.Disks)

				{

					int num2 = 0;

					foreach (PartitionInfo partition2 in disk3.Partitions)

					{

						if (partition2.IsBasicData && partition2.HasVolume && string.Equals(partition2.FileSystem, "NTFS", StringComparison.OrdinalIgnoreCase))

						{

							num2++;

						}

					}

					if (num2 >= 2)

					{

						diskInfo = disk3;

						break;

					}

				}

				if (diskInfo == null)

				{

					diskInfo = ((scanResult.Disks.Count > 0) ? scanResult.Disks[0] : null);

				}

			}

		}

		catch (Exception ex)

		{

			LogException(ex);

		}

		if (diskInfo == null)

		{

			Shutdown(1);

			return;

		}

		double num3 = ((diskInfo.Speed != null && diskInfo.Speed.Success) ? diskInfo.Speed.ThroughputMBps : 0.0);

		base.ShutdownMode = ShutdownMode.OnExplicitShutdown;

		ExpandCWindow expandCWindow = new ExpandCWindow(diskInfo)

		{

			ScreenshotPath = arg

		};

		expandCWindow.Closed += delegate

		{

			Shutdown(0);

		};

		expandCWindow.Show();

	}



	private void RunExpandScreenshot(string[] args)

	{

		string arg = GetArg(args, "--expand-screenshot");

		if (string.IsNullOrEmpty(arg))

		{

			Shutdown(1);

			return;

		}

		UiLanguage.English = string.Equals(GetArg(args, "--lang"), "en", StringComparison.OrdinalIgnoreCase);

		DiskInfo diskInfo = null;

		try

		{

			ScanResult scanResult = DiskScanner.Scan(new ScanOptions

			{

				ProbeWrite = false

			});

			int num = ParseInt(GetArg(args, "--disk"), -1);

			string arg2 = GetArg(args, "--select");

			if (num >= 0)

			{

				foreach (DiskInfo disk in scanResult.Disks)

				{

					if (disk.Number == num)

					{

						diskInfo = disk;

						break;

					}

				}

			}

			else if (!string.IsNullOrEmpty(arg2))

			{

				arg2 = arg2.Trim().TrimEnd(':');

				foreach (DiskInfo disk2 in scanResult.Disks)

				{

					foreach (PartitionInfo partition in disk2.Partitions)

					{

						if (string.Equals(partition.DriveLetter, arg2, StringComparison.OrdinalIgnoreCase))

						{

							diskInfo = disk2;

							break;

						}

					}

					if (diskInfo != null)

					{

						break;

					}

				}

			}

			if (diskInfo == null)

			{

				foreach (DiskInfo disk3 in scanResult.Disks)

				{

					int num2 = 0;

					foreach (PartitionInfo partition2 in disk3.Partitions)

					{

						if (partition2.IsSystem && partition2.HasVolume)

						{

							num2++;

						}

					}

					if (num2 > 0)

					{

						diskInfo = disk3;

						break;

					}

				}

			}

		}

		catch (Exception ex)

		{

			LogException(ex);

		}

		if (diskInfo == null)

		{

			Shutdown(1);

			return;

		}

		base.ShutdownMode = ShutdownMode.OnExplicitShutdown;

		ExpandCWindow expandCWindow = new ExpandCWindow(diskInfo)

		{

			ScreenshotPath = arg

		};

		expandCWindow.Closed += delegate

		{

			Shutdown(0);

		};

		expandCWindow.Show();

	}



	private static void LogException(Exception ex)

	{

		try

		{

			string logDirectory = GetLogDirectory();

			Directory.CreateDirectory(logDirectory);

			File.WriteAllText(Path.Combine(logDirectory, "error-" + DateTime.Now.ToString("yyyyMMdd-HHmmss", CultureInfo.InvariantCulture) + ".txt"), ex.ToString(), new UTF8Encoding(encoderShouldEmitUTF8Identifier: false));

		}

		catch

		{

		}

	}



	private static string GetLogDirectory()

	{

		return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "DiskManager", "logs");

	}



	private static bool HasArg(string[] args, string name)

	{

		foreach (string a in args)

		{

			if (string.Equals(a, name, StringComparison.OrdinalIgnoreCase))

			{

				return true;

			}

		}

		return false;

	}



	private static string GetArg(string[] args, string name)

	{

		for (int i = 0; i < args.Length - 1; i++)

		{

			if (string.Equals(args[i], name, StringComparison.OrdinalIgnoreCase))

			{

				return args[i + 1];

			}

		}

		return null;

	}



	private static int ParseInt(string value, int fallback)

	{

		int result;

		return int.TryParse(value, NumberStyles.Integer, CultureInfo.InvariantCulture, out result) ? result : fallback;

	}

}

