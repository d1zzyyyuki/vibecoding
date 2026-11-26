# Changelog

## v1.0.1

- 修复 hashcat 输出 `$HEX[...]`、含冒号或尾部空格的密码被误读，已破解不再误报“未找到”
- 修复单文件 ZIP 被错误限制在 8 位，CPU 现在能继续跑 9–16 位
- 关闭窗口时增加确认；退出时清理仍在运行的 7z / hashcat 子进程并等待线程结束
- 运行中禁止拖拽替换压缩包，避免界面显示 B 包、实际用 A 包密码
- 7-Zip 异常、超时不再被当成“密码错误”静默跳过，会直接报错
- ZIP 复核改为尝试包内所有受支持的加密条目，不再被第一个 Deflate64 条目误判
- 本机能力弹窗加宽并自适应，避免小屏右侧列被裁切
- 窗口标题改为中英双语；产品名和 exe 改为 `ArchivePasswordFinder`
- 补充 hashcat MIT、PySide6/Qt LGPLv3、7-Zip 及第三方组件许可说明

## v1.0.0

- 首个公开版本：CPU / CUDA / OpenCL / 7-Zip / hashcat 多后端
- ZipCrypto、AES-ZIP、7z、RAR5 等格式
- 自动阶梯、能力评估、期望时间、无限模式
