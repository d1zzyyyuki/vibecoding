# M4 分区操作核心 · VHD 实测记录

日期：2026-11-24  
环境：Windows 11 25H2 build 26200，管理员权限  
测试盘：`out\vhd\tail.vhdx`（9 GB，GPT；V: 3 GB + W: 4 GB + 尾部约 2 GB）  
实现：`PartitionOperations`，通过 Windows 自带 `diskpart` 执行；只允许 `FileBackedVirtual`，真实磁盘被拒绝。

## 1. 新建分区

命令：

```text
DiskManager.Tests.exe partition-create --disk 2 --size-mb 512 --letter Z --label NEWDATA --log <path>
```

结果：`success=True`；新分区 512 MB、NTFS、盘符 Z:。  
日志：`create.log`、`create.out`。

## 2. 格式化

```text
partition-format --disk 2 --partition 4 --fs NTFS --label FORMATTED --log <path>
```

结果：`success=True`；分区 4 格式化为 NTFS，卷标 `FORMATTED`。  
日志：`format.log`、`format.out`。

## 3. 删除分区

```text
partition-delete --disk 2 --partition 4 --log <path>
```

结果：`success=True`；分区 4 删除。  
日志：`delete.log`、`delete.out`。

## 4. 拆分分区

在 W: 放入 64 MB `payload.bin`，然后：

```text
partition-split --disk 2 --partition 3 --size-mb 512 --letter Z --label SPLIT --log <path>
```

结果：

- W: 4 GB → 3.5 GB；Z: 新增 512 MB；
- `payload.bin` SHA256 前后一致：`202CCE8A0025B81810E7872A2C303303E748F6351D4C00E1CCC875828BBAA301`；
- journal 式操作日志：`split.log`、`split.out`。

## 5. 真实磁盘拒绝

```text
partition-create --disk 1 --size-mb 64 --letter Z
```

结果：`success=False`，提示“分区操作只允许虚拟磁盘（VHD）；真实磁盘被拒绝”；真实 D 盘分区未变化。  
日志：`refuse-real.out`。

## 6. UI 工具窗口（Windows UI Automation）

在 tail VHD 上从主界面点击“新建分区”，打开 `PartitionToolsWindow`，设置：

- 大小 512 MB
- 盘符 Z:
- 卷标 UITEST
- 勾选“我已备份数据，并确认这是 VHD 测试盘”
- 点击“确认执行”

结果：状态显示 `完成：已创建 Z:`；分区 4 = 512 MB、NTFS、卷标 UITEST。日志：`ui-create.log`、`ui-create.operation.log`。

### 6.1 拆分 / 格式化 / 删除（同一 UI）

在重建的 tail VHD 上，用同一 UI Automation 流程继续：

- **拆分**：主界面选中 W: →“拆分分区”→ 512 MB / Z: / UISPLIT → 确认。W: 4→3.5 GB，新增 Z: 512 MB；`payload.bin` SHA256 前后一致 `FCE2839D…C964C3D6`。日志：`ui-split.log`。
- **格式化**：选中 Z: →“格式化”→ 卷标 UIFORMAT → 确认。Z: 为 NTFS/UIFORMAT。日志：`ui-format.log`。
- **删除**：选中 Z: →“删除”→ 确认。分区 4 删除，W: 数据哈希不变。日志：`ui-delete.log`。

## 7. 当前边界

- 通过 `diskpart` 实现；主界面工具窗口已接入四种操作，但只开放 VHD 测试盘。
- 只允许 VHD；真实磁盘保护在 Core 层硬拒绝。
- 新建/拆分/格式化/删除没有自动回滚或 journal 恢复；执行前需要人工确认。
- 拆分日志记录 diskpart 命令和输出，但不具备 C 扩容引擎那样的逐块续传能力。
