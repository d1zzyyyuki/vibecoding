# 实现说明

## 模块

| 文件 | 职责 |
|---|---|
| `main.py` | 入口，`multiprocessing.freeze_support()` + `ui.main()` |
| `core.py` | 候选空间、ZIP 解析、CPU 引擎、GPU 后端选择、启动自检、7-Zip、硬件监控 |
| `cuda.py` | CUDA 驱动 API 绑定 + PTX 选型 + 扫描 |
| `gpu.py` | OpenCL 绑定 + 扫描 |
| `hashcat_gpu.py` | hashcat 调用、AES-ZIP / 7z 哈希提取、进度与取消 |
| `capability.py` | 24 小时长度评估、hashcat 基准测速与缓存 |
| `ui.py` | PySide6 界面、i18n、响应式、状态栏后端标签 |
| `zipcpu.c` | CPU 引擎（Win32 多线程 + zlib 校验） |
| `zipcuda.cu` | CUDA 内核源码 |
| `tools/build_cuda_ptx.py` | 构建期把内核编译成多架构 PTX |
| `tests/` | 冒烟测试与 CUDA 测试 |

## ZipCrypto 校验

传统 ZIP 加密的每个文件前面有 12 字节加密头，最后一个明文字节是已知值：

- 有 data descriptor（`flag & 8`）时是 DOS 修改时间的高字节
- 否则是 CRC32 的高字节

破解时用候选密码初始化 3 个 32 位密钥，解密 12 字节头并比对最后一个字节。
为了压误报，程序同时校验压缩包内前几个加密文件的头；命中后再用完整文件数据做一次 CRC 校验。

## 引擎

### CPU（`zipcpu.c`）

- 默认 `min(32, 逻辑核数)` 条线程，共享原子游标，每批 1024 个候选
- 头校验命中后继续解密文件数据，用内置 zlib 校验 CRC，避免假密码
- 支持字符集模式和字典模式（字典被拼成 UTF-8 字节池 + offset 数组）

### CUDA（`cuda.py` / `zipcuda.cu`）

- 通过 `nvcuda.dll` 的驱动 API（`cuModuleLoadData` 等）加载 PTX，驱动现场 JIT，不需要 CUDA Toolkit
- 内核每个线程试一个候选，CRC32 表放在每个 block 的共享内存里生成，密码打包进两个 64 位寄存器
- 序号解码最多做一次 64 位除法，Fermi 这类没有 64 位硬件除法的卡也能跑
- PTX 覆盖 sm_20 到 sm_120，按设备算力和驱动支持的 PTX ISA 排序挑选；加载失败会自动换下一份
- 命中结果回传后仍用 CPU 端的 `zipcpu_verify` 做完整校验

### OpenCL（`gpu.py`）

- 直接 `ctypes` 调 `OpenCL.dll`，AMD / Intel / NVIDIA 驱动即可，不需要额外运行库
- 每 chunk 一次 dispatch，命中候选由宿主用 C 引擎复验
- 单文件 ZIP 不用 GPU：只有一个校验字节时误报太多，逐个人工校验反而比 CPU 慢

### 7-Zip

- 用内置 `7z.exe` 的 `t` 命令校验 RAR / 7Z / AES-ZIP 等
- 文件头未加密时只测包内最小的加密文件，命中后再整包复核

### hashcat（GPU，AES-ZIP / 7z / RAR5）

- `hashcat_gpu.py` 在第一次用到时把随程序携带的 hashcat 压缩包解压到
  `%LOCALAPPDATA%\ArchivePassFinder\hashcat-8.0.0\`，之后复用
- 只使用 OpenCL 后端（`--backend-ignore-cuda --backend-ignore-hip`）：NVIDIA/AMD/Intel
  的 OpenCL 编译器在驱动里，不需要用户装 CUDA Toolkit 或 HIP SDK
- 哈希提取：WinZip AES 从 ZIP 本地头直接算 `$zip2$`（mode 13600）；
  7z 调 `7z2hashcat.exe` 得到 `$7z$`（mode 11600）；
  RAR5 自己解析文件头里的加密记录，拼 `$rar5$`（mode 13000）
- 破解阶段用 hashcat 的 mask 对应程序里的候选空间；AES 用 `--increment`，
  7z / RAR5 因 `--increment` 慢很多改成每个长度单独跑固定 mask
- 字典阶段也交给 hashcat（`-a 0`），避免逐个候选开 `7z.exe`
- 多显卡时从 `-I` 解析设备，优先 NVIDIA / AMD 独显并用 `-d` 指定；
  指定失败自动退回默认设备集合
- 7z / RAR5 可能出假阳性，用 `--keep-guessing` 持续跑，宿主用 7-Zip 复核每个结果
- 失败（没有 GPU、哈希提不出来、进程异常）自动回退 7-Zip CPU 路径

## 能力评估与自动阶梯

`capability.py` 把实测速度换算成不同时间预算下能试完的密码长度，启动弹窗和“能力”按钮都用它；
hashcat 各模式的基准测试结果按显卡缓存 7 天。

高级设置的“期望破解时间”默认 2 分钟（自动），按当前参考速度换算成纯数字位数和混合位数；
用户手动改位数会切到自定义，重新选时间则重新计算。自动阶梯就是：字典 → 纯数字 → 混合。
“无限”模式不设时间上限，字典后按 1/2 位数字、1 位混合、3/4 位数字、2 位混合… 交替，
混合阶段用“第一个字母的位置”拆 mask，排除已经测过的纯数字候选。

ZIP 的 CUDA/OpenCL 内核最多 8 位：自动模式封顶 8 位；无限模式超过 8 位的剩余长度会拆到 CPU。
AES-ZIP / 7z / RAR5 没有这个限制。

总进度按各阶段候选数加权，`Emitter` 负责阶段速度与剩余时间。

## 启动自检

`core.quick_backend_check()` 在后台线程跑：

1. 探测 CUDA（`cuInit` + 枚举，不建 context），不行再探测 OpenCL
2. 用 ZipCrypto 规则造几个假加密头，先扫 4M 候选测速，再按速度扫一小段并在指定序号放一个密码，必须命中
3. 失败顺序：CUDA → OpenCL → CPU

结果缓存在 `_SELFTEST_RESULT`，`gpu_backend()` 直接沿用，保证状态栏写着什么是实际就会用什么。

UI 把结果画成状态栏 CPU 旁边的芯片：`⚡ CUDA 1.2 G/s` / `⚡ OpenCL 806 M/s` / `⚡ CPU`。
悬停显示设备、算力、PTX 文件名和失败原因。

## 界面

- 无边框 + `WA_TranslucentBackground`，Win32 `SetWindowCompositionAttribute` 做亚克力模糊
- `paintEvent` 画圆角、暗色渐变、氛围光；右侧立绘 cover 裁切
- 能力弹窗用立绘做背景并压暗；右下角“中 / EN”两个按钮直接选语言
- 内容放在 `QScrollArea` 里，窗口窄时隐藏立绘/次要状态栏信息
- 搜索线程通过 `Bridge(QObject)` 的 Qt Signal 把消息回主线程，类型见 `core.py` 的 `Emitter`

## 打包

`app.spec` 把 `zipcpu.dll`、`assets`（7-Zip、图片、PTX）一起塞进单文件，并裁掉不用的 Qt 模块。
