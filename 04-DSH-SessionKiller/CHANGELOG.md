# Changelog

## v1.0.0 — 2026-11-28

### Added

- 从桌面单文件脚本整理为 `04-DSH-SessionKiller` 项目
- 单文件 CMD 构建脚本，产物可复现
- `DSH_DRYRUN=1` 预览模式
- 路径越界检查
- 会话回收站 manifest 和恢复流程
- 假档案集成测试和 CI job

### Changed

- 移除硬编码的 `C:\Users\22700\...` DSH 安装路径，改为从进程/常见安装位置动态查找
- 回收站批次名增加毫秒，降低同秒碰撞
- 恢复缓存时遇到已存在目标会跳过，不再覆盖

### Fixed

- 恢复路径同样经过 profile root 校验
- 单文件 CMD 的构建说明改为项目相对路径
