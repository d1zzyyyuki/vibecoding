# M2 在线搬移引擎 · VHD 实测记录

日期：2026-11-24  
环境：Windows 11 25H2 build 26200，管理员权限  
引擎：`OnlineResizeEngine`（仅允许 `FileBackedVirtual` 磁盘；真实磁盘会被拒绝）  
测试盘：两个动态 VHD：`tail.vhdx`（9 GB，V: 3 GB + W: 4 GB + 尾部约 2 GB）和 `notail.vhdx`（8 GB，X: 2 GB + Y: 5.859 GB + 尾部约 127 MB）

## 1. 完整执行（尾部有空间）

命令：

```text
DiskManager.Tests.exe engine-run --disk 2 --system 2 --data 3 --growth-mb 1024 --journal <path>
```

结果：`success=True exit=0 message=completed`，journal `Completed`。

| 项目 | 执行前 | 执行后 |
|---|---|---|
| V:（目标） | 分区 3 GB / NTFS 3 GB | 分区 4 GB / NTFS 4 GB |
| W:（数据） | 偏移 3088 MB / 4 GB | 偏移 4112 MB / 4 GB |
| W: 盘符 | W: | W:（自动恢复） |
| 测试文件 | `payload.bin` 64 MB | SHA256 前后一致：`D89D18C095B80739B7AAE206EEA1136F2F2C9AF56900E2B7EB60A25570B00707` |
| 目标标记 | `V:\marker.txt` | 内容一致 |

日志：`full-move.log`。

## 2. 受控中断 + 续传

- 引擎在搬移 512 MB 后抛出受控中断（先保存 journal 进度再退出）。
- 第一次退出码 **3**，journal：`phase=Moving`，`progressSourceOffset=6996099072`。
- 再执行 `engine-resume --journal <path>`：`exit=0`，完成后目标与数据分区尺寸正确，`payload.bin` SHA256 仍为 `6A89EEDF9A082040DFCD3E513C5CC8AC760225031F1CD4D7EF42E3CA0AF2C09A`。

日志：`interrupt.log`、`interrupt-resume.log`。

## 3. 回滚

- 同样在搬移 512 MB 后中断（退出码 3）。
- 执行 `engine-rollback --journal <path>`：`exit=0 message=rolled back`，journal `RolledBack`。
- 分区恢复为 V: 3 GB / 偏移 16 MB，W: 4 GB / 偏移 3088 MB；`payload.bin` SHA256 与中断前一致：`221ED2A32717CD9E525F5FB88F1196CB169F4EA77BA86291AA6DB58FDB6FD8FA`。

日志：`rollback-interrupt.log`、`rollback.log`。

## 4. 强杀进程 + 续传

- 引擎带 `--chunk-delay-ms 200` 运行，搬移进行中用管理员 `taskkill /F` 强杀测试进程（PID 8528）。
- 强杀后 journal 仍为 `phase=Moving`，`progressSourceOffset=7029653504`（约搬到一半）。
- 执行 `engine-resume`：`exit=0`；最终 V: 4 GB、W: 偏移 4112 MB；`payload.bin` SHA256 为 `B34C86801E0281B362AD9A6A9C5163E80E4FA50B777217772380F65F5FDF675B`，与执行前一致。

日志：`hard-kill.log`、`hard-kill-resume.log`、`hard-kill.journal`。

## 5. 需要收缩的布局（no-tail VHD）

命令：

```text
DiskManager.Tests.exe engine-run --disk 3 --system 2 --data 3 --growth-mb 1024 --journal <path>
```

引擎先用 `diskpart shrink desired=<MB>` 把 Y: 从 5.859 GB 收缩到 4.983 GB（实际收缩 940,572,672 B = 897 MB），然后锁卷、右移 1 GB、扩大 X: 到 3 GB、扩展 NTFS。

| 项目 | 执行前 | 执行后 |
|---|---|---|
| X:（目标） | 2 GB / NTFS 2 GB | 3 GB / NTFS 3 GB |
| Y:（数据） | 偏移 2064 MB / 5.859 GB | 偏移 3088 MB / 4.983 GB（先收缩 897 MB） |
| 测试文件 | `Y:\payload.bin` 64 MB | SHA256 前后一致：`38DA14C8E228EB99CD96AF7E2234981FB9F89F66B3A6D0F9CFAC68798CC4F903` |
| 目标标记 | `X:\marker.txt` | 内容一致 |

日志：`shrink-full.log`。

### 5.1 收缩 + 受控中断 + 续传

- 收缩完成后、搬移 512 MB 时受控中断；退出码 3，journal `Moving`，`progressSourceOffset=6978273280`。
- 执行 `engine-resume`：`exit=0`；X: 3 GB、Y: 偏移 3088 MB / 4.983 GB；`payload.bin` SHA256 为 `1EDA0EB75466784DDD2ED7A7F2388927B87937AE5D837DD353D86C128C5626EC`，与执行前一致。

日志：`shrink-interrupt.log`、`shrink-interrupt-resume.log`、`shrink-interrupt.journal`。

## 6. UI 全流程执行

在 9 GB tail VHD 上，用 Windows UI Automation 操作真实窗口，而不是调用测试程序：

1. 主窗口选择 VHD，点击“规划扩 C”；
2. 输入 1 GB，点击“生成计划”；
3. “开始执行”已启用，点击后出现确认层；
4. 勾选“我已备份数据，并了解执行期间不能断电”，点击“确认执行”；
5. 状态显示 `执行完成；盘符已恢复，请重新扫描确认。`。

结果：V: 3→4 GB，W: 偏移 3088→4112 MB，`payload.bin` SHA256 前后一致：`F9286CC38467A31AD03AE8E0868A0C0017E2557475BADE30676CE4BA65839704`；journal 写入 `%ProgramData%\DiskManager\journal`。

日志：`ui-execute.log`；journal：`ui-execute.journal`、`ui-execute.journal.gpt`。

### 6.1 GPT 数据起点更新后的恢复

使用测试开关 `--fail-gpt-start`，在“数据已右移、数据分区 GPT 起点已更新、目标分区尚未扩大”之后强制失败。

- 失败退出码 3，journal `GptDataStartUpdated`。
- `engine-rollback`：`exit=0`，数据复制回原位置，恢复原始 GPT；分区回到 V: 3 GB / W: 偏移 3088 MB；`payload.bin` SHA256 仍为 `3BDAF5C70F0F3DB3BE497D2D6449CF9EBB4ABE98CDA5BD8A053BA952675F5C83`。
- 再次制造同一失败后执行 `engine-resume`：`exit=0`，最终 V: 4 GB / W: 偏移 4112 MB；文件哈希不变。

日志：`recovery-gptstart-fail.log`、`recovery-gptstart-rollback.log`、`recovery-gptstart-fail2.log`、`recovery-gptstart-resume.log`。

### 6.2 目标分区扩大后的恢复

使用测试开关 `--fail-gpt-updated`，在“数据已右移、数据 GPT 起点已更新、目标分区已扩大但文件系统尚未扩展”之后强制失败。

- 失败退出码 3，journal `GptUpdated`。
- `engine-rollback`：先锁定目标卷，用 `IOCTL_DISK_GROW_PARTITION` 负值把目标分区缩回 3 GB，再锁定数据卷、把数据复制回原位置、恢复原始 GPT；`exit=0`，V: 3 GB / W: 偏移 3088 MB。
- `payload.bin` SHA256 仍为 `B3E7CC730A50799816E687F01F6F1A97E5E7B6AEDD920B03CA1624EE321BC47D`。
- 同一失败后执行 `engine-resume`：`exit=0`，最终 V: 4 GB / W: 偏移 4112 MB，文件哈希不变。

日志：`recovery-gptupdated-fail.log`、`recovery-gptupdated-rollback.log`、`recovery-gptupdated-fail2.log`、`recovery-gptupdated-resume.log`。

## 7. 拒绝路径

| 场景 | 结果 |
|---|---|
| 真实 NVMe 磁盘（disk 0） | `exit=2`，提示只允许虚拟磁盘；不创建 journal，不写盘 |

日志：`refuse-real-disk.log`。

## 8. 当前边界

- 收缩步骤通过 Windows 自带 `diskpart shrink` 执行，尚未用纯 FSCTL 实现；收缩过程中断后不能自动恢复，会进入人工检查状态。
- 收缩之后再执行 `engine-rollback` 会被拒绝，因为需要先恢复卷大小；当前回滚只覆盖未收缩的布局。
- `GptDataStartUpdated` 和 `GptUpdated` 已支持回滚/续传；`Completed`（文件系统已扩展）之后不提供自动回滚。
- 只允许虚拟磁盘；真实磁盘的执行入口在 UI 禁用，引擎也会拒绝。真实 C 盘未验证。
- 目标卷为 VHD 内的普通 NTFS 卷，不是本机正在运行的 C 盘；真正“在线扩 C”仍需 M3 的同盘真机或原生启动 VHD 验证。
- GPT 更新失败后的完整回滚、断电后的自动恢复尚未覆盖；当前验证了搬移中断、受控回滚、强杀续传、收缩中断续传、UI 执行。
- 盘符恢复使用 mount manager 删除自动盘符 + `SetVolumeMountPoint` / `DefineDosDevice` 回退，VHD 实测成功。
