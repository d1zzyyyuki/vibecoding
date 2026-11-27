# DiskManager 架构

## 产品层

- 名称：磁盘管理器 / DiskManager；左上角 `by cbd`。
- WPF `net48`，单 exe；产品名、图标、版本元数据在 App 项目中设置。
- 主题：`Themes/Colors.xaml` 改为冷蓝渐变、蓝色描边、冷色卡片；背景使用 `Assets/Furina.jpg`，叠加深蓝色渐变保证文字对比。
- 图标：`tools/make_icon.py` 生成蓝色齿轮 `assets/DiskManager.ico`，exe 使用该图标。
- 主界面：左列磁盘、中间布局/分区表、右列分区详情/读写测速/安全边界；快捷 C 扩容卡替换旧三步骤流程卡。
- 右下角 `中 / EN` 按钮：主界面静态导航使用字典切换；数据字段和子窗口的完整本地化仍待做。
- 隐藏技术细节：VHD 字样从主界面和分区工具窗口移除；确认窗口统一使用“操作风险/备份”语言。

## Core 层

### 扫描与展示

`DiskScanner` 枚举物理磁盘、GPT 分区、卷、总线、介质、PCIe 链路；`SpeedProbe` 做原始无缓冲读取；`WriteSpeedProbe` 在可用 NTFS 卷创建 8 MB 临时文件并 `WriteThrough + Flush`，显示 MB/s 读写。两者都不改分区表。

### 分区操作

`PartitionOperations` 通过 `diskpart` 执行新建、格式化、删除、拆分；所有入口先检查 `FileBackedVirtual`，真实磁盘直接拒绝。日志在 `%ProgramData%\DiskManager\operations`；目前 UI 在真实磁盘上只展示确认流程，不执行写入。

### C 盘扩容规划

`ExpandCPlanner`：

- 目标为系统分区；后续基本数据 NTFS 卷作为 donor；
- 上限为 donor 空闲空间之和；
- `Allocate` 采用 water-fill：先补足容量低于均分额的分区，再在剩余分区均分；
- `Reallocate` 固定一个 donor 的值，重新分配其余 donor，保持总和不变；
- UI 使用 0.1 GB/MB 量子进行量化，显示一位小数并保持总和与目标相等；
- `生成计划` 输出带 SHA256 的 JSON，交由后续 PE 离线引擎消费。

### 在线搬移引擎（历史 VHD 验证）

`OnlineResizeEngine` 仍然保留：

1. 收缩 donor（可选，当前用 diskpart）。
2. 锁定/卸载数据卷。
3. 32 MB 块从右到左搬移，逐块 journal + flush。
4. 更新数据分区 GPT 起点，扩大目标分区。
5. `FSCTL_EXTEND_VOLUME` 扩展目标 NTFS。
6. 恢复盘符。

支持中断续传、强杀续传、`GptDataStartUpdated`/`GptUpdated` 之后回滚。历史 VHD 证据见 `docs/evidence/m2-online-engine-2026-11-24.md`。

## PE 离线路径

见 `docs/PE-OFFLINE.md`：

- 在线 UI 生成 job.json；
- `DiskManagerOffline` 已实现 `validate`/`plan`/`run`；`run` 在 VHD 上完成收缩、逐块右移、GPT 更新、目标分区扩大和 C 扩展，payload 哈希一致；
- `tools/pe/build-pe.ps1` 已写：ADK 检测、发布自包含单文件、copype、注入 boot.wim、ISO；
- `startnet.cmd` 已改为调用 `run` 并在成功后 `wpeutil reboot`；
- PE 镜像未构建，真实 C 盘写入未授权；离线执行没有逐块 resume/rollback。

## 关键安全原则

- 真实磁盘写入口默认关闭；界面不把“预览/确认”伪装成已执行。
- 所有破坏性测试只写 VHD；测试后清理。
- 分区表更新前保留原始 GPT sidecar；搬移逐块持久化进度。
- C 扩容规划只生成计划，不自动写盘。
