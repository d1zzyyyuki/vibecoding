# DiskManager 测试报告



日期：2026-11-25  

版本：v1.0.0（冷色重设计 + 离线多分区执行 + 主界面中英切换）  

机器：TEST-PC，Windows 11 25H2 build 26200



## 1. 环境与边界



- 会话以非管理员启动；UAC 自动提权，应用 manifest 要求管理员权限。

- 本轮没有写真实分区表；真实磁盘上的新建/拆分/格式化/删除会打开确认窗口，但执行端拒绝。

- 破坏性测试的历史证据全部来自 VHD，测试后 VHD 已清理。

- PE 离线执行尚未构建和实测。



## 2. 自动化检查



### 2.1 单元测试



```powershell

.\tests\DiskManager.Tests\bin\Release\net8.0\DiskManager.Tests.exe

```



结果：**38/38 PASS**。



新增覆盖：



- `expand-alloc-waterfill`：512 MB / 1 GB / 4 GB 容量、目标 3 GB 时，分摊为 512 MB / 1 GB / 1.5 GB。

- `expand-alloc-fixed`：固定第二个分区 512 MB 后，其余两个分区各 1.28 GB，总和保持 3 GB。

- `expand-max`：只含 C 后续一个可回收分区时，可扩容上限等于其空闲空间。

- `gpt-patch-multi`：多 donor 场景下只右移 donor 起点，目标分区长度留给 `IOCTL_DISK_GROW_PARTITION`。



### 2.2 selftest



最终 `DiskManager.exe --selftest`：7/7 PASS，包含 elevated、disks、system volume、GPT、read speed、read-only、version；最近一次约 59 ms（首次冷启动可能更慢）。



## 3. 离线校验器



`src/DiskManager.Offline` 已编码（net8.0 控制台，可发布为自包含单文件）：



```powershell

dotnet build .\src\DiskManager.Offline\DiskManager.Offline.csproj

DiskManagerOffline validate --job job.json

DiskManagerOffline plan --job job.json

DiskManagerOffline run --job job.json --journal journal.log

```



在 12 GB / 四个 2 GB 分区的 VHD 上：



- `validate`：通过；

- `plan`：正确输出 C 扩展和三个 donor 的新起点/大小；

- `run`：完成 donor 收缩、逐块右移、GPT 更新、目标分区扩大、NTFS 扩展；V 2→3 GB，三个 donor 变为 1.5/1.75/1.75 GB，三个 32 MB payload SHA256 前后一致。

- 证据：`docs/evidence/offline-run-2026-11-25.md`、`docs/evidence/offline-2026-11-25/`。



**未执行**：PE 镜像未构建，ADK 未安装；执行器默认只允许虚拟磁盘，真实盘需显式 `--allow-real` 且尚未授权；没有逐块 resume/rollback。



## 4. UI 验收



| 项目 | 结果 |

|---|---|

| 冷色蓝主题、玻璃卡片、蓝色状态字 | 已截图确认 |

| 芙宁娜背景 | 已截图确认（素材为外部图片，见 README） |

| 蓝色齿轮图标 | 新 exe 图标已生成 |

| 名称统一 | 中文“磁盘管理器”、英文“DiskManager”、`by cbd` |

| 右上角重复刷新 | 已移除 |

| 整卷搬移预计面板 | 已移除 |

| “进入规划”旧流程卡 | 已移除，改为快捷 C 扩容卡 |

| VHD 字样（主界面/工具窗口） | 已移除；旧 PlanWindow 不再从主界面进入 |

| 读写测速 | 主界面/右侧均显示读 + 写，单位 MB/s |

| 基本操作窗口 | 新建/拆分/格式化/删除均能打开确认窗口；真实写入被拒绝 |

| 中/EN | 主界面静态导航/快捷卡片可切换；数据字段和子窗口尚未完整英文 |

| C 扩容 | 只 C 盘显示 0 MB；多分区显示上限、可编辑分摊、GB/MB、生成任务 JSON |



截图：`docs/screenshots/main-1320.png`、`data-d-1180.png`、`main-en-1320.png`、`expand-c-zero-820.png`。



## 5. C 盘扩容规划验证



- 单元测试验证分摊算法和总和守恒。

- 多分区 VHD 截图验证：三个后续分区各 2 GB 空闲时，可扩容上限显示为 5.7 GB（按 0.1 GB 显示粒度），三行分摊各 1.9 GB，总和一致。

- 规划窗口提供 GB/MB 切换；切换单位后重新量化，保持显示总和不变。

- “生成计划”写出任务 JSON，包含磁盘序列号、分区号、偏移、大小、分摊字节、SHA256；文件后续交给 PE 离线引擎。



## 6. 读写测速



- 读取：沿用的原始无缓冲 16 MB × 最多 3 次采样，结果按中位数。

- 写入：在可用 NTFS 卷根目录创建 8 MB 临时文件，`WriteThrough` 写入并 `Flush(true)`，读速度/写速度均以 MB/s 展示。

- 临时文件测速不是分区表写入；但仍会在磁盘上产生短暂文件，已在实现中删除。

- 本机实测写入约 0.7–1.0 GB/s，读取约 2.2–2.9 GB/s；受 Defender、缓存和负载影响。



## 7. Defender



```

Scan starting...

Scan finished.

Scanning ...\DiskManager\dist\DiskManager.exe found no threats.

```



单文件 `dist\DiskManager.exe`：623,104 字节，SHA256 `691D1A1E9C5108D0B533174648C10457D0C16A3606635104594EF543E381194C`。



## 8. 历史核心证据



以下证据来自重命名前的同一套 Core 代码，仍可作为 VHD 验证依据：



- `docs/evidence/m2-online-engine-2026-11-24.md`：整卷右移、中断续传、强杀续传、滚动回滚、GPT 起点/目标分区扩大后的回滚与续传。

- `docs/evidence/m4-partition-ops-2026-11-24.md`：新建、格式化、删除、拆分、真实盘拒绝。



本轮没有重跑这些破坏性 VHD 测试；不能把旧截图当作新 UI 的执行截图。



## 9. 未验证 / 已知限制



- **真实 C 盘系统卷未实测**；本轮也没有授权写真实分区表。

- C 扩容实际执行尚未接入；目前只生成计划和任务 JSON。

- PE 镜像未制作，离线引擎未构建；设计见 `docs/PE-OFFLINE.md`。

- 多分区右移的物理执行顺序、BitLocker、页面文件、恢复分区障碍尚未在真实盘验证。

- 英文只覆盖主界面静态导航；分区类型、状态、提示等仍为中文。

- 写入测速使用卷根目录临时文件；若卷无权限或无 NTFS 卷，会显示“写 —”。

- 无代码签名；Defender 实测无威胁，不保证所有环境。

