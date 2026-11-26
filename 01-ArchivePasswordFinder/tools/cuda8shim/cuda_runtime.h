/* cuda_runtime.h（shim）—— 极简 CUDA 8 设备侧运行时声明。
 *
 * 只在 build_cuda_ptx.py 用 CUDA 8 生成 Fermi/Kepler 的旧版 PTX 时使用：
 * 把 nvcc 的 `-FI cuda_runtime.h` 指到这个目录（假 cl.exe 会把本目录放在 -I 最前），
 * 从而避免拉起 MinGW 的 C 运行库头（cudafe 在 MSVC 方言下解析不了它们的 __extension__）。
 *
 * 只声明 zipcuda.cu 用到的内建：threadIdx / blockIdx / blockDim / gridDim、
 * __syncthreads、atomicAdd（CUDA 8 里是 __uAtomicAdd 宏）、以及 __global__ 等修饰词。
 */
#ifndef __MINI_CUDA_RUNTIME_H__
#define __MINI_CUDA_RUNTIME_H__

#define __device_builtin__ __declspec(__device_builtin__)
#define __device__ __declspec(__device__)
#define __global__ __declspec(__global__)
#define __shared__ __declspec(__shared__)
#define __constant__ __declspec(__constant__)
#define __restrict__ __restrict
#define __forceinline__ inline
#define __noinline__

struct __device_builtin__ uint3 {
    unsigned int x, y, z;
};
struct __device_builtin__ dim3 {
    unsigned int x, y, z;
};

uint3 __device_builtin__ extern const threadIdx;
uint3 __device_builtin__ extern const blockIdx;
dim3 __device_builtin__ extern const blockDim;
dim3 __device_builtin__ extern const gridDim;

extern "C" __device_builtin__ __device__ void __syncthreads(void);

extern "C" __device_builtin__ __device__ unsigned int __uAtomicAdd(unsigned int *address,
                                                                   unsigned int val);
#define atomicAdd(p, v) __uAtomicAdd((unsigned int *)(p), (unsigned int)(v))

#endif /* __MINI_CUDA_RUNTIME_H__ */
