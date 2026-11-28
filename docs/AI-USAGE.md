# AI 使用说明

本仓库是 cbd 的个人作品集。AI 编程工具参与了代码生成、评审和修复建议，但提交前均经过本机运行验证；没有把未验证的生成结果直接当作完成品。

## 验证边界

- 01：本机跑过 smoke/capability/cuda/hashcat 测试；CUDA 路径在无 N 卡机器上通过 mock 驱动测试。
- 02：38 项检查在仓库源码上跑过；真实磁盘写入未授权，VHD 测试证据留在 `docs/evidence/`。
- 03：Edge 无头 fixture、MyMemory 真实接口和 HLTV 结构片段验证过；未在真实 HLTV 页面长期跑过，Cloudflare 会阻止命令行直接抓取。

## 评审与修复

代码评审报告和逐条修复记录在 `docs/DEVLOG.md`。如果 AI 建议与实际测试冲突，以测试结果为准。
