# 开发日志

这是一个个人作品集仓库，记录的是实际做过、实际验证过的取舍，而不是补写的完美过程。

## 2026-11-28 · 04 v1.0.0

- 把桌面单文件脚本整理成独立项目：源码、构建、测试和 Release 分离。
- 移除硬编码的 DSH 安装路径，改成从进程映像或常见安装位置查找。
- 增加 dry-run、路径越界检查、毫秒级回收站批次和恢复冲突保护。
- 用假档案覆盖列表、删除、恢复、空壳登记、dry-run 和单文件 CMD 启动；不碰真实 DSH 数据。

## 2026-11-28 · v1.2.1 工程化

- 增加 GitHub Actions，覆盖 01 的 Python 测试、02 的 .NET 8 测试、03 的 Edge 无头 fixture 测试。
- 根目录补 MIT LICENSE，并保留各项目目录内的许可证。
- 03 把版本脚本、翻译词表和评论选择器加入可重复的 fixture 测试。
- 02 修正改名残留文案，把 PE/ADK 构建阻塞移入 `docs/TODO.md`。
- 01 锁定依赖版本，并新增 `docs/EXCEPTION-AUDIT.md` 记录异常处理审计结论。

## 2026-11-27 · 03 v1.0.0 → v1.2.0

- 从“广告全部隐藏”转向“广告清理 + 翻译/别称 + 赔率区保护”。
- 发现 `.thread-message-text` 是登录提示而不是评论正文，评论区实际在 `.forum-middle`；修正后评论翻译才真正生效。
- Wildcard 反复被翻译：根因是旧 localStorage 缓存一直复用错误结果，升级为 `hltv_zh_cache_v2` 后解决。
- `nice try` / `NT` 按 CS 语境处理为“尽力了”；补 `olofmeister（奥拉夫）`。
- 处理 `dispatch ... to make Stage 2` / `outlast ... to progress to Stage 2` 这类新闻标题，统一为“战胜……，晋级 Stage 2”。
- 广告清理和翻译脚本曾互相误伤：翻译生成的“领取/首充”会被广告文本规则当成广告并连带隐藏评论容器。v1.2.0 通过跳过翻译节点、限定清理范围解决。
- 性能从“DOM 一变就全文档扫”改为增量 MutationObserver、选择器合并和正则预编译。
- Edge 本地 CRX 的 proof 限制仍然存在；安装说明改为“开发者模式 + CRX 为主，CMD 可选，加载解压兜底”。

## 2026-11-27 · 02 v1.0.0

- WPF `.NET Framework 4.8` 单文件版，38 项检查。
- VHD 上完成收缩、右移、GPT 更新、扩 C 的 journal/resume 测试；真实盘执行保持拒绝，必须显式 `--allow-real`。
- PE 构建脚本已写好，但 ADK 安装被 Windows Installer 1618 阻塞，移入 TODO，不把未完成能力写成已完成。

## 2026-11-26 · 01 v1.0.0 / v1.0.1

- 初始 C ZipCrypto CPU 引擎，后续接 Python UI、CUDA/OpenCL 和 hashcat。
- 实测定位并修复：hashcat `$HEX` 输出被当普通密码、尾部空格被 `strip()` 掉、单文件 ZIP 被错误限制到 8 位、关窗不清理 7z/hashcat 子进程、ZIP 只复核第一个条目。
- 单文件 ZIP 的 GPU 路径因只有一个校验字节而误报概率高，设计上主动退回 CPU；这是取舍，不是遗漏。
- 用 mock `nvcuda.dll` 在没有 NVIDIA 显卡的机器上覆盖 CUDA 绑定、显存搬运和扫描链路。

## 已知不完美

- 01 的 `core.py` / `ui.py` 仍然偏大，异常捕获还需继续收窄。
- 02 的真实磁盘写入仍未授权，PE 镜像未完成。
- 03 的翻译依赖 MyMemory，有额度和隐私外发边界；真实 HLTV DOM 变更会影响选择器。
