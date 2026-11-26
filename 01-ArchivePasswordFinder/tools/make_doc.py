# -*- coding: utf-8 -*-
"""生成带完整源码的技术文档（Markdown）。

用法：
    python tools/make_doc.py --out 文档.md
"""
import argparse
import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FILES = ["main.py", "core.py", "cuda.py", "gpu.py", "hashcat_gpu.py", "capability.py",
         "ui.py", "zipcpu.c", "zipcuda.cu", "tools/build_cuda_ptx.py",
         "tools/get_hashcat.py", "tests/common.py", "tests/test_smoke.py",
         "tests/test_cuda.py", "tests/test_hashcat.py", "tests/test_capability.py",
         "app.spec", "version_info.txt"]

TREE = """```
ArchivePassFinder/
├── main.py                  # 入口
├── core.py                  # 候选空间、ZIP 解析、CPU 引擎、GPU 后端选择、启动自检、7-Zip、硬件监控
├── cuda.py                  # CUDA 引擎（nvcuda.dll + 预编译 PTX）
├── gpu.py                   # OpenCL 引擎
├── hashcat_gpu.py           # hashcat GPU 引擎（AES-ZIP / 7z / RAR5）
├── capability.py            # 能力评估（时间预算 → 位数）+ hashcat 测速缓存
├── ui.py                    # PySide6 界面
├── zipcpu.c                 # CPU 引擎源码（Win32 线程 + zlib 校验）
├── zipcuda.cu               # CUDA 内核源码
├── app.spec                 # PyInstaller 打包配置
├── version_info.txt         # Windows 版本资源
├── requirements.txt
├── README.md
├── LICENSE
├── assets/
│   ├── 7z.exe / 7z.dll      # 7-Zip 26.06
│   ├── 7z-License.txt
│   ├── builtin_words.txt    # 内置字典（303 条）
│   ├── chevron.png
│   ├── icon.ico
│   ├── hutao_bg_soft.jpg    # 窗口背景
│   ├── hutao_panel.jpg      # 右侧立绘
│   ├── cuda/                # 25 份预编译 PTX（sm_20 … sm_120，ISA 5.0 / 7.8 / 8.8）
│   └── hashcat/             # hashcat 8.0.0 运行包 + 7z2hashcat（构建前下载，未进 git）
├── tools/
│   ├── get_hashcat.py       # 下载 hashcat 运行包
│   ├── build_cuda_ptx.py    # 构建期生成 PTX
│   ├── fake_cl.c            # 假 cl.exe（CUDA 8 在没有 MSVC 的机器上编译）
│   ├── cuda8shim/           # 精简 cuda_runtime.h
│   ├── mock_nvcuda.c        # 假 nvcuda.dll（无 N 卡测试 CUDA 链路）
│   ├── make_doc.py          # 本文档生成脚本
│   └── README.md
├── tests/
│   ├── common.py
│   ├── test_smoke.py
│   ├── test_cuda.py
│   └── test_hashcat.py
└── docs/
    ├── ARCHITECTURE.md
    ├── BUILD.md
    ├── capability.png
    ├── advanced.png
    └── screenshot.png
```"""

DOC = r"""# 压缩包密码找回 · 源码与实现说明

> 仅用于找回自己拥有或已获授权的压缩包密码。

当前版本 v1.0.0。

---

## 0. 交付形态

- 单文件便携 exe：`压缩包密码找回.exe`（Windows 10/11 x64，约 48 MB）
- 双击即用，不需要装 Python、7-Zip、运行库或 CUDA Toolkit；不联网、不写注册表、不装服务
- 打开时按实测速度弹出 24 小时能力表，明确写出能试完的密码位数
- 内置：Python 3.12 运行时、PySide6（Qt6）、7-Zip 26.06、CPU 引擎 DLL、25 份 CUDA PTX、
  hashcat 8.0.0 运行包、OpenCL 内核、界面图片
- hashcat 运行包第一次用到时解压到 `%LOCALAPPDATA%\ArchivePassFinder\`，之后复用
- 默认窗口 1180×792（逻辑像素），支持 800×600 小屏（内容滚动）和 4K（自动放大 UI）

开发机环境：
- Windows 11 26200、AMD Ryzen AI 9 H 365（10C/20T）、Radeon 880M 核显（OpenCL 2.0）、28 GB RAM
- Python 3.12.14、PySide6 6.12.0、PyInstaller 6.22.3、psutil 7.2.2
- MinGW-w64 gcc 8.1（编译 CPU 引擎，也用于 CUDA 8 的假 cl 预处理）

CUDA 路径已在一台 RTX 5080 台式机上实测通过，自检标签显示 14.1 G/s。

---

## 1. 功能清单

| 功能 | 说明 |
|---|---|
| 自动暴力破解 | 字典 → 纯数字 → 小写字母 → 小写+数字 → 可打印字符，长度按 24h 预算截断 |
| 启动能力弹窗 | 打开软件时按当前显卡实测速度，列出 24 小时内能试完的位数（数字 / 字母+数字 / 可打印） |
| 高级设置 | 期望破解时间（2 分钟默认 ~ 无限 / 自定义），纯数字与混合位数自动换算、可手改 |
| hashcat GPU | AES-ZIP、7z、RAR5 交给 hashcat；ZIP-AES 约 1.3 MH/s、RAR5 约 18 kH/s（核显） |
| 引擎选择 | 自动 / CPU / GPU 都会真正换后端；多显卡优先 NVIDIA/AMD 独显，选 GPU 但格式不支持时会明确提示 |
| CPU 引擎 | C 多线程 ZipCrypto 破解，内置 zlib 完整 CRC 校验 |
| CUDA 引擎 | NVIDIA 驱动 API + 预编译 PTX，免装 CUDA Toolkit；Fermi 到 Blackwell |
| OpenCL 引擎 | AMD / Intel / 老 NVIDIA 驱动可用，CUDA 失败时自动顶上 |
| hashcat GPU | AES-ZIP、7z、RAR5 的 KDF 交给 hashcat 在显卡上跑（ZIP-AES 实测约 1.3 MH/s @ 核显） |
| 7-Zip 引擎 | RAR / RAR5 / 7Z / AES-ZIP 等格式；hashcat 不可用时兜底 |
| 启动自检 | 打开后 1 秒内跑一次真实扫描，状态栏显示 CPU / OpenCL / CUDA 与实测速度 |
| 硬件状态栏 | CPU、内存、GPU 名称与占用、显存占用 |
| 界面 | 无边框、亚克力模糊、22px 圆角、酒红/暖橙玻璃拟态，右侧立绘（整体压暗一档） |
| 中英切换 | 右下角“中 / EN”两个按钮直接点选 |
| 响应式 | 800×600 可滚动；宽度小于 960 隐藏立绘；4K 且系统缩放小时自动放大 UI |
| 其它 | 复制密码、一键解压、拖拽压缩包、停止、最大化、窗口拖动 |

---

## 2. 项目结构

{TREE}

---

## 3. 构建与运行

详细步骤见 `docs/BUILD.md`，这里只列主干。

### 3.1 开发环境

```bat
python -m venv venv
venv\Scripts\python -m pip install -r requirements.txt
venv\Scripts\python tools\get_hashcat.py   :: 下载 hashcat 运行包（可选）
```

### 3.2 源码模式运行

```bat
venv\Scripts\python ui.py
venv\Scripts\python ui.py --shot 截图.png            :: 渲染界面截图
venv\Scripts\python ui.py --size 800x600             :: 800×600 适配
venv\Scripts\python ui.py --lang en                  :: 英文界面
venv\Scripts\python ui.py --selftest --out 自检.json  :: 无界面自检后端
venv\Scripts\python ui.py --capability --out 能力.json :: 24h 能力评估（含 hashcat 测速）
venv\Scripts\python ui.py --cli-test 包.zip --out 结果.json
```

### 3.3 打包

```bat
venv\Scripts\python -m PyInstaller --noconfirm --clean app.spec
:: 产物：dist\压缩包密码找回.exe
```

---

## 4. 核心原理

### 4.1 ZIP ZipCrypto

每个加密文件前面有 12 字节随机加密头，最后一个明文字节是已知校验值：
`flag & 8`（data descriptor）时取 DOS 修改时间高字节，否则取 CRC32 高字节。
候选密码先初始化 3 个 32 位密钥，解密 12 字节头并比对末字节；为了压低误报，
程序同时校验压缩包内前几个加密文件的头，命中后再解密文件数据做完整 CRC 校验。

```python
# core.py::prepare_zip 中计算校验字节
if zi.flag_bits & 0x08:
    check = (raw_time >> 8) & 0xFF
else:
    check = (zi.CRC >> 24) & 0xFF
plan.targets.append((enc, check))
```

### 4.2 CPU 引擎（zipcpu.dll）

- Win32 多线程，默认 `min(32, 逻辑核数)` 条线程，共享原子游标，每批 1024 个候选
- 头校验命中后继续解密文件数据，用内置 zlib 校验 CRC，避免假密码
- 支持字符集模式与字典模式（字典拼成 UTF-8 字节池 + offset 数组）

导出接口：

```c
int  zipcpu_crack(charset, base, minlen, maxlen,
                  bstart, bsize, blen, nbuckets,
                  prefix, plen, suffix, slen,
                  enc, check, ntargets,
                  total, start, nthreads,
                  words, woff, nwords);
void zipcpu_set_verify(enc12, data, datalen, method, crc);
int  zipcpu_verify(pw, pwlen, enc12, data, datalen, method, crc);
void zipcpu_stop(void);
unsigned long long zipcpu_done(void);
unsigned long long zipcpu_found_index(void);
```

### 4.3 CUDA 引擎（cuda.py + zipcuda.cu）

Windows 装好 NVIDIA 驱动后系统里就有 `nvcuda.dll`（CUDA 驱动 API），程序用它加载 PTX 文本，
由驱动现场 JIT 成本机指令，所以用户不需要 CUDA Toolkit。

PTX 由 `tools/build_cuda_ptx.py` 在构建期生成：

| 编译器 | PTX ISA | 覆盖架构 |
|---|---|---|
| NVRTC 12.9 | 8.8 | compute_50 … compute_121（Maxwell → Blackwell，5090 是 sm_120） |
| NVRTC 11.8 | 7.8 | compute_35 … compute_90（驱动较旧的机器） |
| CUDA 8.0 nvcc | 5.0 | compute_20 … compute_62（Fermi、Kepler 等老卡） |

运行时先按“设备算力 ≥ PTX 目标”和“驱动支持该 PTX ISA”筛出可用项，按架构从高到低排序；
一份都不可用时按 ISA 从低到高全部试一遍；`cuModuleLoadData` 失败会换下一份，全部失败回退 OpenCL。

内核要点（`zipcuda.cu`）：

- 一个线程试一个候选，联合校验多个目标文件的加密头
- CRC32 表放在每个 block 的共享内存里现场生成，避免常量缓存因随机索引串行化
- 密码打包进两个 64 位寄存器，避免动态下标的栈数组退化成局部内存
- 序号解码最多做一次 64 位除法（先按 base^4 拆商和余），Fermi 也能跑
- 只用 Fermi 也支持的指令，同一份源码可编到 sm_20 和 sm_120
- ptxas 静态校验：21–28 个寄存器，0 spill

### 4.4 OpenCL 引擎（gpu.py）

直接 `ctypes` 调用 `OpenCL.dll`，不依赖 pyopencl；AMD / Intel / NVIDIA 驱动都自带。
每 chunk 一次 dispatch，命中候选由宿主用 C 引擎复验。
单文件 ZIP 不走 GPU：只有一个校验字节时误报太多，逐个人工复验反而更慢。

### 4.5 7-Zip 引擎

- `7z t -y -bsp0 -bse0 -p<候选> -- <包> [<文件>]`，返回 0 且输出 `Everything is Ok` 才算命中
- 文件头未加密时只测包内最小的加密文件，命中后再整包复核
- 随机密码试一次即可判断是否加密；无法识别的格式交给 7-Zip 打开，打不开才报错

### 4.6 hashcat GPU 引擎（AES-ZIP / 7z / RAR5）

AES-ZIP、7z、RAR5 每个候选都要做几千到几十万次哈希迭代，用 7-Zip 逐候选校验（约 236 次/秒）
非常慢。`hashcat_gpu.py` 把这些格式交给 hashcat 在显卡上跑：

- hashcat 运行包随 exe 携带，第一次用到时解压到 `%LOCALAPPDATA%\ArchivePassFinder\hashcat-8.0.0\`
- 只用 OpenCL 后端：NVIDIA / AMD / Intel 的 OpenCL 编译器在驱动里，用户不需要 CUDA Toolkit 或 HIP SDK
- 哈希提取：WinZip AES 直接从 ZIP 本地头构造 `$zip2$`（mode 13600）；
  7z 调 `7z2hashcat` 得到 `$7z$`（mode 11600）；
  RAR5 解析文件头的加密记录，拼出 `$rar5$`（mode 13000）
- 候选空间用 hashcat mask 表达：AES 用 `--increment` 一次跑多个长度；
  7z / RAR5 的 `--increment` 会慢很多，改成每个长度单独跑一次固定 mask
- 字典阶段也交给 hashcat（`-a 0`），避免逐个候选开 7z.exe
- 多显卡时用 `-I` 解析设备，优先 NVIDIA / AMD 独显并加 `-d` 指定；
  指定失败会自动退回默认设备集合
- 7z / RAR5 模式可能出现假阳性：用 `--keep-guessing` 继续跑，每个结果都由 7-Zip 复核，确认后才算找到
- 没有 GPU、哈希提不出来、hashcat 异常时，自动回退 7-Zip CPU 路径

### 4.7 能力评估、期望时间与无限模式

启动后除了后端自检，还会在后台跑一次 hashcat 基准（结果按显卡缓存 7 天），
`capability.py` 据此算出不同时间预算下能试完的最大长度；启动弹窗和“能力”按钮都读这份数据。
弹窗用右侧立绘做背景并压暗，时间刻度包含 2 分钟、10 分钟、30 分钟、1 小时、6 小时、24 小时、3 天。

高级设置默认“2 分钟（自动）”：参考速度按当前压缩包格式取（ZIP / ZIP AES / 7z / RAR5 分别用各自实测速度），
换算纯数字位数和混合位数，显示在输入框里；手动改位数会切到自定义，换时间刻度会重新计算。
自动模式顺序是 字典 → 纯数字 → 混合。
“无限”不设时间上限，字典后按 1 位数字、2 位数字、1 位混合、3/4 位数字、2 位混合… 交替，
混合阶段按“第一个字母的位置”拆 mask，排除已经测过的纯数字候选，日志只写当前位数。

注意位数选择：先取不超过目标的最大位数，再和上一位比较，选总预计时间更接近目标的组合；可能略超目标。

ZIP 传统加密的 GPU 内核最多 8 位：自动模式封顶 8 位，无限模式超过 8 位的剩余长度拆到 CPU；
AES-ZIP / 7z / RAR5 走 hashcat，不受这个限制。

### 4.8 启动自检与后端选择

`core.quick_backend_check()` 在后台线程执行：

1. 探测 CUDA（`cuInit` + 枚举，不建 context），没有则探测 OpenCL
2. 用 ZipCrypto 规则造几个假加密头：先扫 4M 候选测速，再按速度扫一小段并在指定序号放一个密码，必须命中
3. 依次尝试 CUDA → OpenCL → CPU

结果缓存在 `_SELFTEST_RESULT`，`gpu_backend()` 直接沿用，保证状态栏显示的后端就是实际使用的后端。
UI 在状态栏 CPU 旁边显示 `⚡ CUDA 1.2 G/s` / `⚡ OpenCL 806 M/s` / `⚡ CPU`，悬停可看设备、算力、PTX 文件和失败原因。

### 4.9 硬件状态栏

- CPU / 内存：psutil
- GPU 名称与显存：OpenCL 设备信息 + 注册表 `HardwareInformation.qwMemorySize`；没有 OpenCL 时用 CUDA 设备信息
- GPU 占用 / 显存占用：PDH 计数器 `\GPU Engine(*)\Utilization Percentage` 与 `\GPU Adapter Memory(*)\Dedicated Usage`
- 采样线程每秒更新，UI 用 QTimer 刷新

---

## 5. UI 实现

### 5.1 无边框 + 亚克力

`Qt.FramelessWindowHint | Qt.WA_TranslucentBackground`，Win32 `SetWindowCompositionAttribute` 让 DWM 做真实模糊，
`paintEvent` 再画玻璃层、渐变、圆角和高光。标题栏自绘，可拖动、双击最大化。

### 5.2 背景与立绘

窗口背景是同一张图强模糊压暗；右侧立绘 cover 裁切并以人物为中心，左侧向深色渐变。
整体叠一层暗色，夜里关灯不刺眼，暖橙/酒红的色调不变。

### 5.3 响应式

内容放在 `QScrollArea`。宽度小于 900 隐藏显存、小于 980 截断 GPU 型号、小于 960 隐藏立绘。
4K 且系统缩放小时按逻辑高度设置 `QT_SCALE_FACTOR`。

### 5.4 中英切换

`TEXTS = {"zh": ..., "en": ...}`，静态控件登记在 `_tr_widgets`，动态文本用 `_refresh_*()` 重新渲染；
核心层日志与引擎名都带 `en` 字段。右下角是“中 / EN”两个按钮，点哪个直接切哪个语言；
搜索运行期间禁用语言按钮。

### 5.5 线程与消息

搜索在 `EngineThread` 中跑，自检在另一个线程；两者都通过 `Bridge(QObject)` 的 Signal 把消息排回 UI 线程。
消息类型：

| type | 主要字段 |
|---|---|
| start / space / stage / engine / log | 开始、候选总数、阶段、引擎、日志 |
| progress | done / total / rate / elapsed / eta |
| found | password / attempts / elapsed |
| done | result（found / password / reason / attempts / elapsed） |
| error | message |
| extracted | ok / message / path |
| selftest | backend / name / cc / rate / build_ms / error / tried |
| capability | rates（zip / zip_aes / 7z / rar5 / device / hashcat_ok） |

`run_auto_search()` 返回 `{found, password, reason, attempts, elapsed}`，`reason ∈ {found, exhausted, stopped, not_encrypted}`。

### 5.6 其它交互

文件对话框支持 zip/rar/7z/001/z01/tar/gz/tgz/xz/bz2/cab/iso/arj/lzh/z/wim；
支持拖拽压缩包到窗口或 exe 图标；复制密码到剪贴板；一键解压到 `<原目录>\<包名>_解压`。

---

## 6. 打包要点

`app.spec`：

1. `binaries=[('zipcpu.dll', '.')]`、`datas=[('assets', 'assets')]`，`hiddenimports=['cuda', 'gpu', 'hashcat_gpu', 'capability']`
2. 裁剪 Qt：只保留 Core / Gui / Widgets、qwindows、qico、qjpeg、样式插件与 MSVC 运行库
   （JPG 背景依赖 qjpeg，不能删）
3. `assets/hashcat/` 里的 hashcat 运行包约 20 MB，exe 约 50 MB

版本资源在 `version_info.txt`，版本 1.0.0。

---

## 7. 实测记录

| 测试 | 结果 |
|---|---|
| 3 文件 ZipCrypto（密码 123456） | 字典阶段命中，约 0.2 秒 |
| 单文件 ZipCrypto | 自动用 CPU 引擎，约 0.1 秒 |
| 7z 加密（密码 123456） | 字典阶段命中 |
| 未加密 tar | 正确提示“未加密” |
| 非压缩包文件 | 正确报错 |
| 运行中停止 / 中英切换 | 正常 |
| OpenCL（Radeon 880M） | 600–900 M/s |
| CUDA（RTX 5080 台式机） | 自检通过，标签显示 14.1 G/s |
| CPU C 引擎（20 线程） | 约 1–2 亿/秒 |
| hashcat AES-ZIP（Radeon 880M 核显） | 约 1.2 MH/s（-m 13600）；密码 739184 全程约 7 秒 |
| hashcat 7z（Radeon 880M 核显，2^19 次迭代） | 约 1–4 kH/s；密码 7391 全程约 36 秒（每个长度单独跑） |
| hashcat RAR5（Radeon 880M 核显） | 约 18 kH/s；7.7 MB 的 RAR5（密码 666）3 秒出结果 |
| hashcat 7z 模式 CPU 对照（7-Zip 逐候选） | 约 236 次/秒 |
| 启动能力弹窗（880M 核显） | ZIP 8 位（GPU 上限）/ AES 10 位 / 7z 8 位 / RAR5 9 位（24h 估算） |
| 引擎选择 | AES 选 GPU 走 hashcat，选 CPU 走 7-Zip；3 文件 ZipCrypto 选 GPU 走 OpenCL/CUDA，选 CPU 走原生 C |
| 多显卡显示 | 状态栏优先显示 CUDA 独显，不再被 Intel 核显抢名字 |
| 打包 exe 启动 | 约 1.5–2 秒，Defender 扫描无威胁 |
| `tests/test_smoke.py` | 9 项通过 |
| `tests/test_cuda.py` | 23 项通过（含假驱动全链路） |
| `tests/test_hashcat.py` | 7 项通过 |
| `tests/test_capability.py` | 6 项通过 |

没有 N 卡时验证 CUDA 代码：`tests/test_cuda.py` 会编译 `tools/mock_nvcuda.c` 成假
`nvcuda.dll`，用 CPU 参考实现顶替内核，覆盖 ctypes 绑定、参数顺序、显存搬运、分块与命中；
PTX 本身另有 25 份的架构/ISA 检查。

---

## 8. 已知限制

1. GPU 加速覆盖：ZIP（ZipCrypto，CUDA/OpenCL 内核）、AES-ZIP、7z、RAR5（hashcat）。
   RAR3 / 更老的 RAR 仍走 7-Zip 逐候选校验（CPU）。
2. ZIP 传统加密的 GPU 内核最长 8 位，自动模式只跑到 8 位，更长可改用自定义字符集走 CPU；
   AES-ZIP / 7z / RAR5 走 hashcat，没有这个限制。
3. 7z 的 KDF 迭代次数因压缩包而异，速度/时间要按实际日志为准。
4. CUDA 内核只支持程序实际用到的候选形态：无前后缀、密码 ≤ 8 位、字符集 ≤ 255 个字符。
5. 自动阶梯/无限模式覆盖较短密码和常见字典，超长随机密码不现实。
6. RAR / 7Z 文件头加密时只能整包校验，速度较慢。
7. hashcat 运行包首次使用需要解压约 99 MB 到 `%LOCALAPPDATA%`，之后复用。

---

## 9. 完整源码

### 9.1 main.py

```python
<<<FILE:main.py>>>
```

### 9.2 core.py

```python
<<<FILE:core.py>>>
```

### 9.3 cuda.py

```python
<<<FILE:cuda.py>>>
```

### 9.4 gpu.py

```python
<<<FILE:gpu.py>>>
```

### 9.5 ui.py

```python
<<<FILE:ui.py>>>
```

### 9.6 zipcpu.c

```c
<<<FILE:zipcpu.c>>>
```

### 9.7 zipcuda.cu

```cuda
<<<FILE:zipcuda.cu>>>
```

### 9.8 tools/build_cuda_ptx.py

```python
<<<FILE:tools/build_cuda_ptx.py>>>
```

### 9.9 tests/common.py

```python
<<<FILE:tests/common.py>>>
```

### 9.10 tests/test_smoke.py

```python
<<<FILE:tests/test_smoke.py>>>
```

### 9.11 tests/test_cuda.py

```python
<<<FILE:tests/test_cuda.py>>>
```

### 9.12 app.spec

```python
<<<FILE:app.spec>>>
```

### 9.13 version_info.txt

```python
<<<FILE:version_info.txt>>>
```

### 9.14 capability.py

```python
<<<FILE:capability.py>>>
```

### 9.15 hashcat_gpu.py

```python
<<<FILE:hashcat_gpu.py>>>
```

### 9.16 tools/get_hashcat.py

```python
<<<FILE:tools/get_hashcat.py>>>
```

### 9.17 tests/test_hashcat.py

```python
<<<FILE:tests/test_hashcat.py>>>
```

### 9.18 tests/test_capability.py

```python
<<<FILE:tests/test_capability.py>>>
```

---

## 10. 资产与版权

- 7-Zip 26.06 来自官方发布，遵循 GNU LGPL（`assets/7z-License.txt`）。
- `assets/cuda/*.ptx` 由本仓库的 `zipcuda.cu` 用 NVIDIA NVRTC / CUDA 8.0 生成，运行时由驱动 JIT。
- 界面立绘来自《原神》5.3 海灯节官方前瞻壁纸，仅作个人本地背景使用，请勿二次分发。
- 代码使用 MIT 许可证；第三方组件与图片的版权归各自作者所有。
"""


def build(out_path):
    doc = DOC.replace("{TREE}", TREE)
    for name in FILES:
        path = os.path.join(ROOT, name.replace("/", os.sep))
        code = io.open(path, encoding="utf-8").read()
        if not code.endswith("\n"):
            code += "\n"
        doc = doc.replace("<<<FILE:%s>>>" % name, code.rstrip("\n"))
    out_dir = os.path.dirname(os.path.abspath(out_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    io.open(out_path, "w", encoding="utf-8").write(doc)
    print("written:", out_path, "%.1f KB" % (os.path.getsize(out_path) / 1024.0))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "handoff.md"))
    args = ap.parse_args()
    build(args.out)


if __name__ == "__main__":
    main()
