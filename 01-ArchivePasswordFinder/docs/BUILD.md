# 构建说明

## 环境

- Windows 10 / 11 x64
- Python 3.12（3.10+ 应该也行，没测过）
- MinGW-w64 gcc（编译 `zipcpu.dll`；本项目用 8.1 测的，更新的版本一般也可以）
- 打包用 PyInstaller，其余依赖见 `requirements.txt`

```bat
python -m venv venv
venv\Scripts\python -m pip install -r requirements.txt
```

## 0. hashcat 运行包（AES-ZIP / 7z 的 GPU 加速）

```bat
venv\Scripts\python tools\get_hashcat.py
```

会下载 hashcat 8.0.0 官方包和 7z2hashcat，放到 `assets/hashcat/`（约 26 MB，未进 git）。
没有这一步时程序仍能构建运行，只是 AES-ZIP / 7z 会退回 CPU（7-Zip）校验。

## 1. CPU 引擎 zipcpu.dll

只用到 zlib 的 inflate 和 crc32。先准备 zlib 源码，解压到任意目录（下面以 `zlib-src\zlib-1.3.1` 为例）：

```bat
cd zlib-src\zlib-1.3.1
for %f in (adler32.c crc32.c inflate.c inftrees.c inffast.c zutil.c) do ^
    gcc -O3 -c %f -o %~nf.o

cd ..\..
gcc -O3 -shared -I zlib-src\zlib-1.3.1 -o zipcpu.dll zipcpu.c ^
    zlib-src\zlib-1.3.1\adler32.o zlib-src\zlib-1.3.1\crc32.o ^
    zlib-src\zlib-1.3.1\inflate.o zlib-src\zlib-1.3.1\inftrees.o ^
    zlib-src\zlib-1.3.1\inffast.o zlib-src\zlib-1.3.1\zutil.o
```

仓库里已经带了编译好的 `zipcpu.dll`，改了 `zipcpu.c` 才需要重新编译。

## 2. CUDA PTX（可选，仓库已带 25 份）

`assets/cuda/*.ptx` 由 `zipcuda.cu` 编译而来，运行时由显卡驱动 JIT，用户机器不需要 CUDA Toolkit。
下面三组命令分别覆盖新驱动、中代驱动和老卡。重工具链放在哪都行，下面用 `<cuda_build>` 表示。

### 2.1 新驱动（PTX ISA 8.8，CUDA 12.9）

```bat
venv\Scripts\python -m pip download --no-deps --only-binary=:all: ^
    --dest <cuda_build> nvidia-cuda-nvrtc-cu12==12.9.86
:: 解压 whl 到 <cuda_build>\nvrtc129，再解压 nvidia-cuda-nvcc-cu12（里面有 ptxas）到 <cuda_build>\nvcc129
venv\Scripts\python tools\build_cuda_ptx.py ^
    --nvrtc-bin <cuda_build>\nvrtc129\nvidia\cuda_nvrtc\bin ^
    --toolkit nvrtc129 --archs 50,61,75,86,90,100,120 ^
    --ptxas <cuda_build>\nvcc129\nvidia\cuda_nvcc\bin\ptxas.exe
```

### 2.2 中代驱动（PTX ISA 7.8，CUDA 11.8）

```bat
venv\Scripts\python -m pip download --no-deps --only-binary=:all: ^
    --dest <cuda_build> nvidia-cuda-nvrtc-cu11==11.8.89
:: 解压到 <cuda_build>\nvrtc118
venv\Scripts\python tools\build_cuda_ptx.py ^
    --nvrtc-bin <cuda_build>\nvrtc118\nvidia\cuda_nvrtc\bin ^
    --toolkit nvrtc118 --archs 35,50,61,70,75,86,90 ^
    --ptxas <cuda_build>\nvcc129\nvidia\cuda_nvcc\bin\ptxas.exe
```

### 2.3 老卡（PTX ISA 5.0，CUDA 8.0）

CUDA 9 之后官方不再支持 sm_20，所以 Fermi 只能用 CUDA 8.0 的 nvcc。`nvcc` 在 Windows 上默认要求 MSVC，
仓库的 `tools/fake_cl.c` 把它的预处理请求转给 MinGW g++，配合 `tools/cuda8shim` 里的精简 `cuda_runtime.h`，
可以在只有 MinGW 的机器上编译。

1. 下载 CUDA 8.0 GA2 安装包（`cuda_8.0.61_win10-exe`），用 7-Zip 解出 `compiler\` 到 `<cuda_build>\cuda8\compiler`；
2. 把 `<cuda_build>\cuda8\compiler\include\host_config.h` 换成空壳（跳过编译器版本检查）：
   ```c
   #ifndef __CUDA_HOST_CONFIG_H__
   #define __CUDA_HOST_CONFIG_H__
   #endif
   ```
3. 编译假 cl.exe：
   ```bat
   gcc -O2 -o tools\fakecl\cl.exe tools\fake_cl.c
   ```
4. 生成 PTX：
   ```bat
   venv\Scripts\python tools\build_cuda_ptx.py ^
       --nvcc <cuda_build>\cuda8\compiler\bin\nvcc.exe ^
       --gxx "C:\mingw64\bin\g++.exe" ^
       --cuda-inc <cuda_build>\cuda8\compiler\include ^
       --cuda-shim tools\cuda8shim ^
       --ptxas <cuda_build>\cuda8\compiler\bin\ptxas.exe ^
       --toolkit cuda8 --archs 20,30,32,35,37,50,52,53,60,61,62
   ```

生成的 PTX 会按 `zipcrack_sm<架构>_isa<ISA版本>.ptx` 命名写进 `assets/cuda/`。加 `--ptxas` 会顺手做静态校验，
报告寄存器用量和 spill。

## 3. 打包 exe

```bat
venv\Scripts\python -m PyInstaller --noconfirm --clean app.spec
:: 产物：dist\压缩包密码找回.exe
```

`app.spec` 里裁掉了用不到的 Qt 组件，只保留 Core / Gui / Widgets、qwindows、qico、qjpeg 和样式插件。
打包后约 48 MB（其中 hashcat 运行包约 20 MB）。

## 4. 测试

```bat
venv\Scripts\python tests\test_smoke.py
venv\Scripts\python tests\test_cuda.py
venv\Scripts\python tests\test_hashcat.py
venv\Scripts\python tests\test_capability.py
set PCA_CUDA_DLL=tools\mock\nvcuda.dll
venv\Scripts\python tests\test_cuda.py
```

没有界面时也可以直接看能力评估：

```bat
压缩包密码找回.exe --capability --out capability.json
```
