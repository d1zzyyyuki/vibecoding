# tools

构建期用到的脚本，不打包进 exe。

| 文件 | 用途 |
|---|---|
| `get_hashcat.py` | 下载 hashcat 运行包和 7z2hashcat 到 `assets/hashcat/`（未进 git） |
| `build_cuda_ptx.py` | 把 `zipcuda.cu` 编译成 `assets/cuda/*.ptx`（NVRTC / CUDA 8 nvcc 两种路径） |
| `fake_cl.c` | 假 `cl.exe`：把 CUDA 8 nvcc 的预处理请求转给 MinGW g++，用于没有 MSVC 的机器 |
| `cuda8shim/cuda_runtime.h` | 精简版设备侧运行时声明，绕开 MinGW 头文件里 cudafe 解析不了的语法 |
| `mock_nvcuda.c` | 假 `nvcuda.dll`：用 CPU 参考实现顶替 CUDA 内核，让 `tests/test_cuda.py` 在没有 N 卡时也能测通链路 |
| `make_doc.py` | 生成带完整源码的技术文档（默认输出 `handoff.md`，已在 .gitignore 里） |

## 编译辅助工具

```bat
gcc -O2 -o tools\fakecl\cl.exe tools\fake_cl.c
gcc -shared -O2 -o tools\mock\nvcuda.dll tools\mock_nvcuda.c
```

## 重新生成 PTX

三套编译器各负责一段，详见 [docs/BUILD.md](../docs/BUILD.md) 第 2 节。简要命令：

```bat
:: 新驱动 ISA 8.8
python tools\build_cuda_ptx.py --nvrtc-bin <nvrtc129-bin> --toolkit nvrtc129 ^
    --archs 50,61,75,86,90,100,120 --ptxas <ptxas>

:: 中代驱动 ISA 7.8
python tools\build_cuda_ptx.py --nvrtc-bin <nvrtc118-bin> --toolkit nvrtc118 ^
    --archs 35,50,61,70,75,86,90 --ptxas <ptxas>

:: 老卡 ISA 5.0（需要先编译 tools\fakecl\cl.exe 和 CUDA 8.0 的 compiler 目录）
python tools\build_cuda_ptx.py --nvcc <cuda8>\bin\nvcc.exe --gxx <g++> ^
    --cuda-inc <cuda8>\include --cuda-shim tools\cuda8shim ^
    --ptxas <cuda8>\bin\ptxas.exe --toolkit cuda8 ^
    --archs 20,30,32,35,37,50,52,53,60,61,62
```

`--ptxas` 是可选的静态校验，会打印寄存器用量与 spill。

## 用假驱动跑 CUDA 测试

```bat
gcc -shared -O2 -o tools\mock\nvcuda.dll tools\mock_nvcuda.c
set PCA_CUDA_DLL=tools\mock\nvcuda.dll
python tests\test_cuda.py
```
