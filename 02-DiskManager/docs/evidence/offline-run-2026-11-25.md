# 离线多分区右移执行 · VHD 实测

日期：2026-11-25  
程序：`DiskManagerOffline.exe run --job ... --journal ...`  
磁盘：12 GB VHD，GPT，四个 2 GB 分区（V/W/X/Y），测试后已 detach/删除。

## 输入任务

- 目标：partition 2（V:），原偏移 16 MB，原大小 2 GB。
- donor：partition 3/4/5（W/X/Y），各 2 GB；收缩 512 / 256 / 256 MB。
- growth：1 GB。
- 目标最终 3 GB；三个 donor 均右移 1 GB，大小分别变为 1.5 / 1.75 / 1.75 GB。
- 运行前后在 W/X/Y 各放 32 MB `payload.bin` 并记录 SHA256。

## 结果

`run` 退出码 0，journal `Completed`。

| 项目 | 执行前 | 执行后 |
|---|---|---|
| 目标卷 | 2 GB | 3 GB（NTFS 同步扩展） |
| donor 1 | W: 偏移 2064 MB / 2 GB | E: 偏移 3088 MB / 1.5 GB |
| donor 2 | X: 偏移 4112 MB / 2 GB | G: 偏移 5136 MB / 1.75 GB |
| donor 3 | Y: 偏移 6160 MB / 2 GB | H: 偏移 7184 MB / 1.75 GB |
| W payload | `602E38B1…9752C24` | E: 同上 |
| X payload | `A1D53F41…6407EEB` | G: 同上 |
| Y payload | `DAB110CA…16FEF567` | H: 同上 |

卷在新位置重新挂载后可读；盘符由 Windows 自动分配为 E/G/H（测试中没有强制恢复 W/X/Y）。  
日志：`exec.log`、`journal.log`、`job.json`、`after-layout.txt`。

## 已实现的顺序

1. 校验磁盘/分区布局；
2. `diskpart shrink` 收缩 donor；
3. 锁定/卸载 donor 与目标卷；
4. 从最右侧 donor 开始，逐个用 32 MB 块右移 `growth`；
5. 更新 GPT：donor 起点 +growth，目标长度由 `IOCTL_DISK_GROW_PARTITION` 扩大；
6. `FSCTL_EXTEND_VOLUME` 扩展目标 NTFS；
7. 重新扫描验证。

## 限制

- 只允许 `FileBackedVirtual`；真实磁盘被拒绝。
- 执行入口是离线 CLI，不是 PE 镜像；PE 镜像未构建（ADK 未安装）。
- 没有实现多分区右移的逐块 resume/rollback；journal 只记录阶段和最后进度。
- 盘符没有恢复为原 W/X/Y；PE 重启后应由 Windows 重新枚举。
- 目标卷是 VHD 里的普通 NTFS 卷，不是运行中的系统 C。
