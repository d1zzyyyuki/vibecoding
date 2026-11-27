# PE 离线右移与自动化执行设计

状态：**校验/计划/离线执行器已编码；执行器在 VHD 上完成多分区右移、GPT 更新和 C 文件系统扩展**。PE 镜像仍未构建（本机 ADK 安装被 Windows Installer 1618 阻挡，需重启后重试），真实 C 盘写入未授权。

## 为什么需要 PE

在线移动 D/E/F 数据卷本身可以完成；难点是运行中的 C 盘：

1. C 盘不能像 D 盘一样锁定并卸载。
2. 右移完成后要把 C 的 GPT 长度和 NTFS 文件系统都扩大；在运行中的系统卷上同时改 GPT 和卷大小，失败窗口更大。
3. 如果 D/E/F 中有页面文件、休眠文件、BitLocker 或正在写入的卷，在线锁卷可能失败。

因此正式执行采用两条路：

- **在线路径**：只移动可锁定的数据卷，C 仍在线；适合尾部空间足够、D/E/F 都能安全卸载的情况。
- **PE 路径**：重启进入 WinPE，在没有任何卷被 Windows 占用时统一执行“收缩 → 右移 → GPT → 扩展 C → 重启”。优先实现 PE 路径的自动化，因为它最可控。

## 推荐镜像与组件

使用 Windows ADK 的 WinPE（不要直接改系统自带 WinRE）：

- `copype amd64 C:\WinPE\DiskManager`
- 给 WinPE 添加 PowerShell 可选包（诊断）和 .NET 8 自包含离线引擎（单文件，不依赖 WinPE 的 .NET）。
- 离线引擎是控制台程序 `DiskManagerOffline.exe`，复用现有 Core 的 GPT/BlockMover/Journal 代码，不引用 WPF。
- 把任务文件、日志和备份放在 U 盘或 PE 的 `X:\DiskManager\`。

## 任务文件

在线 UI 生成 `job.json`，至少包含：

```json
{
  "version": 1,
  "diskSerial": "磁盘序列号",
  "diskSize": 1024209543168,
  "systemPartitionGuid": "GPT 分区 GUID",
  "donors": [
    { "partitionGuid": "...", "shrinkBytes": 1073741824 },
    { "partitionGuid": "...", "shrinkBytes": 536870912 }
  ],
  "growthBytes": 1610612736,
  "createdUtc": "...",
  "checksum": "对关键字段的 SHA256"
}
```

PE 启动后：

1. 等待磁盘和卷稳定。
2. 校验磁盘序列号、容量、GPT GUID 和当前大小；任何不匹配立即退出，不写入。
3. 写入 journal 和 GPT 备份。
4. 按 `donors` 从右到左收缩并移动分区，逐块 flush；每块更新 journal。
5. 更新所有受影响分区的 GPT 起点/长度（同一事务缓冲，`IOCTL_DISK_SET_DRIVE_LAYOUT_EX`）。
6. 扩展 C 分区并执行 `FSCTL_EXTEND_VOLUME`。
7. 校验文件系统、盘符/卷 GUID，写完成标记，自动重启。
8. 失败时保持 PE 或进入回滚；回滚使用 journal 中保存的原始 GPT 和已搬移进度。

## 自动化启动

优先采用 **一次性 PE 启动项**，不改默认启动顺序：

```text
bcdedit /copy {current} /d "DiskManager Offline"
bcdedit /set {新GUID} path \Windows\System32\winload.efi
bcdedit /set {新GUID} device partition=<PE分区>
bcdedit /set {新GUID} osdevice partition=<PE分区>
bcdedit /set {新GUID} systemroot \Windows
bcdedit /set {bootmgr} path \EFI\Microsoft\Boot\bootmgfw.efi
bcdedit /displayorder {新GUID} /addfirst
bcdedit /bootsequence {新GUID}
```

实际命令需要按 PE 构建方式调整；不要把示例命令直接执行。执行完成后用 `bcdedit /delete {新GUID}` 删除临时项。也可以制作 U 盘手动启动，作为更保守的 v1 方案。

`startnet.cmd`：

```text
wpeinit
diskpart /s X:\DiskManager\wait-disks.txt
X:\DiskManager\DiskManagerOffline.exe --job X:\DiskManager\job.json --journal X:\DiskManager\journal
```

## 自动右移算法

多分区右移的最小安全顺序：

1. 从最右侧分区开始，向右移动到新的 GPT 起点（目标：所有受影响分区整体右移 `growthBytes`）。
2. 每次移动前确认目标区间没有其他分区、没有 BitLocker、没有活动页面文件。
3. 每个 32 MB 块写后 `FlushFileBuffers`，并持久化 `progressSourceOffset`。
4. 全部移动完成后，一次写入新的 GPT 表；GPT 备份写失败则不提交。
5. 最后扩大 C 的 GPT 长度并扩展 NTFS；扩展失败时保留 PE 环境，按 journal 回滚数据。

数据卷可以在 PE 中先收缩：收缩量由 UI 分配；如果 `diskpart shrink` 在 PE 中不可用，改用 `FSCTL_SHRINK_VOLUME` + `FSCTL_MOVE_FILE` 的离线实现。

## 参考产品交互

- DiskGenius：分区表备份/还原、操作前预览、执行进度、失败恢复入口。
- 本项目保留：布局预览、二次确认、逐块 journal、GPT sidecar、自动恢复。
- 不建议照搬“直接拖拽就写盘”；所有写操作必须在执行前显示目标布局和回滚条件。

## 当前已经写好的部分

- `src/DiskManager.Offline`：.NET 8 控制台离线程序，支持：
  - `validate --job job.json`：校验磁盘号、磁盘大小、系统分区偏移/大小、donor 偏移/大小、收缩总量、最终 END 是否越界；
  - `plan --job job.json`：打印 C 扩展后的偏移/大小和每个 donor 的新起点/新大小；
  - `run --job job.json [--journal path]`：虚拟磁盘上的收缩、逐块右移、GPT 更新、目标分区扩大和 NTFS 扩展。
- `tools/pe/build-pe.ps1`：ADK 检测 → 发布单文件自包含离线程序 → `copype` → 挂载 boot.wim 注入 → 生成 ISO。当前机器未安装 ADK，脚本会明确报错而不是跳过。
- `tools/pe/startnet.cmd`：启动后调用 `run`；尚未在真实 PE 中验证。
- UI 的“生成计划”已写出 `%ProgramData%\DiskManager\jobs\job-*.json`。

### 已验证

用 12 GB、四个 2 GB 分区的 VHD 生成任务，`validate` 通过，`plan` 输出正确；`run` 完成：

- V 目标 2→3 GB，NTFS 同步扩展；
- W/X/Y 各右移 1 GB，收缩为 1.5/1.75/1.75 GB；
- 三个 32 MB payload SHA256 前后一致；
- 卷在 VHD 重新 attach 后正确挂载。

证据：`docs/evidence/offline-run-2026-11-25.md`。

## 尚未实现

- PE 镜像未构建；ADK 安装在本机被 Windows Installer 1618 阻挡（已尝试 winget、静默安装、重启 msiserver），需要重启后再试。`build-pe.ps1` 未在安装 ADK 的机器上运行过。
- 多分区右移没有逐块 resume/rollback；journal 只记录阶段和最后进度。
- 真实磁盘写入默认拒绝；只有显式 `--allow-real` 且用户明确授权后才允许。PE 脚本默认不添加该参数。
- 盘符恢复未做，PE 重启后由 Windows 重新分配。

