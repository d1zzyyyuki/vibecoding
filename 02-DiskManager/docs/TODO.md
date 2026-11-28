# DiskManager TODO

## PE 构建

- `tools/pe/build-pe.ps1` 已写好，但本机安装 Windows ADK 时遇到过 Windows Installer 1618（另一个安装正在进行），重启后重试即可。
- 构建完成前，PE 离线执行能力仍以 VHD 测试为准，不要把它描述成已在真实 PE 中验证。

## 真实磁盘验收

- 必须先在 VHD 或备份盘验证。
- 真实磁盘操作需要显式授权，并保留恢复日志。
