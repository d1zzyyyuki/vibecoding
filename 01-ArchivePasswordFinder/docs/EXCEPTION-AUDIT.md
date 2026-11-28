# 01 异常处理审计

日期：2026-11-28  
范围：`01-ArchivePasswordFinder/*.py`

## 静态统计

当前 `except Exception` 共 102 处：

| 文件 | 数量 |
|---|---:|
| core.py | 53 |
| ui.py | 22 |
| hashcat_gpu.py | 13 |
| cuda.py | 9 |
| capability.py | 3 |
| gpu.py | 2 |

这些不全是缺陷：GPU 驱动探测、哈希提取失败降级、UI 状态刷新等场景需要宽捕获。但下面几类应当优先收窄或记录：

## 优先审计点

1. `core._run_7z`
   - 旧实现把 7-Zip 超时、杀软拦截和“密码不对”混淆成同一个 `False`。
   - v1.0.1 已增加 `SevenZip.test_checked`，把环境错误与密码错误分开；后续继续补超时和句柄耗尽用例。

2. `core.verify_zip_with_zipfile`
   - 旧实现只打开 `infos[0]`，压缩方法不支持时会否决正确密码。
   - 已改为遍历所有受支持的加密条目。

3. `hashcat_gpu._run_once`
   - 旧实现把 hashcat `rc=0` 当“正常跑完”，已破解但 7-Zip 复核失败时会误报未找到。
   - 已改为 rc=0 且无通过复核时返回 `error`；同时保留 `$HEX` 解码和尾部空格。

4. `NativeZip` / `HashcatJob` 初始化
   - DLL/哈希提取失败应降级到 7-Zip，这是预期的宽捕获；但需要把失败原因写入日志，不能只留空后端。

5. UI 线程和关窗
   - `closeEvent` 中的 `join/kill` 仍需保留宽捕获，但至少应记录失败，避免窗口已关、子进程仍在跑。

## 后续动作

- 逐文件把 `except Exception` 标成 `expected` / `fallback` / `unexpected`。
- `unexpected` 统一走 `log_exception()`，不再静默。
- 为错误路径补 smoke 用例：7-Zip 超时、hashcat rc=0 但复核失败、单文件 ZIP 10 位。
- 暂不做大拆包，先让错误可见，再拆 `core.py` / `ui.py`。
