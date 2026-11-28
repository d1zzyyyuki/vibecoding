# DSH 会话清理器（DSH-SessionKiller）

DeepSeek Harness 的对话清理工具：列出全部 session，选中后移入回收站，并清理侧栏索引；支持从回收站恢复。

## 为什么需要它

DSH 的“归档”只会隐藏对话，不删除磁盘上的会话文件和工作区登记。时间久了，`%USERPROFILE%\.dsh\sessions` 和 `sessions_projcache` 会一直累积。

DSH 桌面端没有外部优雅退出接口：窗口关闭事件会被 Electron 主进程拦截并隐藏到托盘，所以本工具在用户确认后会结束 DSH 进程，再修改数据。

## 一个对话由三部分组成

1. `%USERPROFILE%\.dsh\sessions\<工作区目录>\<sessionId>\session.v4.jsonl.zstd`
   会话本体。
2. `%USERPROFILE%\.dsh\storages\session_projcache\sessions\<sessionId>.json`
   侧栏标题/最近活动缓存。
3. `%USERPROFILE%\.dsh\storages\workspace.json`
   工作区里的 `sessionIds`、`archivedSessionIds`、`pinnedSessionIds`。

删除时必须三处一起处理，否则会留下空壳登记或孤立缓存。

## 安全设计

- 删除前把文件移动到 `%USERPROFILE%\.dsh\trash\<时间戳>\`，不是直接 `Remove-Item`
- 同一批次写入 `manifest.json`，保存 sessionId、原相对路径、工作区、归档/置顶状态
- 修改 `workspace.json` 前先备份到回收站批次，写回走 `.tmp` + 重新解析校验
- 路径操作限制在 profile root 内，拒绝 `..` 逃逸
- 结束 DSH 时只精确结束枚举到的 PID，不杀进程树
- 结束进程后再次检查 DSH 是否被自动拉起，以及 `workspace.json` 是否仍被占用
- 支持 `DSH_DRYRUN=1`：只打印将要删除的对话，不关 DSH、不改磁盘

## 使用

下载 Release 里的 `DSH-SessionKiller.cmd`，双击运行即可，不需要管理员权限。

[下载 v1.0.0](https://github.com/d1zzyyyuki/vibecoding/releases/download/dsh-sessionkiller-v1.0.0/DSH-SessionKiller.cmd)

也可以用源码运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File src\DSH-SessionCleanup.ps1
```

交互：

```text
1 3 5     多选
1-3       范围
1,3,5     逗号
r         从回收站恢复
0         刷新列表
q         退出
```

## 环境变量

| 变量 | 作用 |
|---|---|
| `DSH_PROFILE_ROOT` | 覆盖 DSH 数据目录，默认 `%USERPROFILE%\.dsh` |
| `DSH_SKIP_APP_CHECK=1` | 跳过 DSH 运行检查，自动化测试用 |
| `DSH_NO_PAUSE=1` | 结束后不等待回车 |
| `DSH_DRYRUN=1` | 只预览删除，不关 DSH、不改磁盘 |
| `DSH_APP_CLOSE_DRYRUN=1` | 只打印将结束的 PID，不实际结束 |

## 构建

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\build-cmd.ps1
```

产物：`dist\DSH-SessionKiller.cmd`。它由批处理头 + PowerShell 载荷组成，批处理只负责把载荷解到 `%TEMP%` 后执行，中文不受 CMD 代码页影响。

## 测试

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tests\run-tests.ps1
```

测试使用假的 DSH 档案，覆盖列表、dry-run、删除、恢复、空壳登记、越界输入和单文件 CMD 启动。不会碰真实档案。

## 限制

- 仅支持 Windows PowerShell 5.1 / Windows 10/11
- 需要先让 DSH 退出才能改数据；工具会在确认后结束进程
- 删除是移动到本地回收站，不是安全擦除；要彻底清理需自行删除 `trash`
- DSH 的存储格式变化可能导致列表/索引逻辑失效，升级 DSH 后先小范围验证

## 许可证

MIT，见 [LICENSE](LICENSE)。
