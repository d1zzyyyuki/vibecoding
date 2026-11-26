/* mock_nvcuda.c —— 假 nvcuda.dll：用于在没有 NVIDIA 显卡的机器上测试 cuda.py 的
 * ctypes 绑定、参数顺序、缓冲区分块调度与回退逻辑。
 *
 * 它不执行 PTX，而是在 cuLaunchKernel 里用 CPU 跑一份 ZipCrypto 参考实现，
 * 从“设备内存”（其实就是 malloc 出来的宿主内存）里读同一批参数。
 *
 * 环境变量：
 *   MOCK_REJECT_ISA=88   -> 拒绝 ISA 8.x 的 PTX（模拟旧驱动），验证 cuda.py 会降级到 7.8
 *   MOCK_FAIL_ALL=1      -> 所有 PTX 都加载失败，验证调用方回退 OpenCL/CPU
 *
 * 编译： gcc -shared -O2 -o nvcuda.dll mock_nvcuda.c
 */
#include <windows.h>
#include <stdint.h>
#include <string.h>
#include <stdlib.h>
#include <stdio.h>

typedef uint32_t CUresult;
typedef uint64_t CUdeviceptr;
typedef int32_t CUdevice;
typedef void *CUcontext;
typedef void *CUmodule;
typedef void *CUfunction;
typedef void *CUstream;

#define MOCK_OK 0
#define MOCK_ERR_INVALID_PTX 218
#define MOCK_ERR_NO_BINARY 209

static uint32_t CRCT[256];
static int crc_ready = 0;

static void init_crc(void) {
    if (crc_ready) return;
    for (uint32_t n = 0; n < 256; n++) {
        uint32_t c = n;
        for (int k = 0; k < 8; k++) c = (c >> 1) ^ (0xEDB88320u & (uint32_t)(-(int)(c & 1)));
        CRCT[n] = c;
    }
    crc_ready = 1;
}

static const char *errname(CUresult code) {
    (void)code;
    return "MOCK_ERROR";
}

__declspec(dllexport) CUresult __cdecl cuGetErrorName(CUresult code, const char **p) {
    if (p) *p = errname(code);
    return MOCK_OK;
}
__declspec(dllexport) CUresult __cdecl cuGetErrorString(CUresult code, const char **p) {
    if (p) *p = "mock error";
    return MOCK_OK;
}

__declspec(dllexport) CUresult __cdecl cuInit(unsigned int flags) {
    (void)flags;
    init_crc();
    return MOCK_OK;
}

__declspec(dllexport) CUresult __cdecl cuDriverGetVersion(int *v) {
    if (v) *v = 12090; /* CUDA 12.9 驱动 */
    return MOCK_OK;
}

__declspec(dllexport) CUresult __cdecl cuDeviceGetCount(int *n) {
    if (n) *n = 1;
    return MOCK_OK;
}

__declspec(dllexport) CUresult __cdecl cuDeviceGet(CUdevice *dev, int ordinal) {
    if (dev) *dev = ordinal;
    return MOCK_OK;
}

__declspec(dllexport) CUresult __cdecl cuDeviceGetName(char *name, int len, CUdevice dev) {
    (void)dev;
    strncpy(name, "Mock CUDA Device (RTX Test)", (size_t)len);
    name[len - 1] = 0;
    return MOCK_OK;
}

__declspec(dllexport) CUresult __cdecl cuDeviceGetAttribute(int *pi, int attrib, CUdevice dev) {
    (void)dev;
    if (!pi) return 1;
    switch (attrib) {
    case 75: *pi = 8; break;     /* CC major */
    case 76: *pi = 6; break;     /* CC minor */
    case 16: *pi = 84; break;    /* SM count */
    case 1:  *pi = 1024; break;  /* max threads/block */
    default: *pi = 0; break;
    }
    return MOCK_OK;
}

__declspec(dllexport) CUresult __cdecl cuDeviceTotalMem_v2(size_t *bytes, CUdevice dev) {
    (void)dev;
    if (bytes) *bytes = (size_t)24ull * 1024 * 1024 * 1024;
    return MOCK_OK;
}

__declspec(dllexport) CUresult __cdecl cuCtxCreate_v2(CUcontext *pctx, unsigned int flags,
                                                      CUdevice dev) {
    (void)flags; (void)dev;
    if (pctx) *pctx = (CUcontext)1;
    return MOCK_OK;
}
__declspec(dllexport) CUresult __cdecl cuCtxDestroy_v2(CUcontext ctx) { (void)ctx; return MOCK_OK; }
__declspec(dllexport) CUresult __cdecl cuCtxSetCurrent(CUcontext ctx) { (void)ctx; return MOCK_OK; }
__declspec(dllexport) CUresult __cdecl cuCtxSynchronize(void) { return MOCK_OK; }

__declspec(dllexport) CUresult __cdecl cuModuleLoadData(CUmodule *mod, const void *image) {
    const char *txt = (const char *)image;
    const char *env = getenv("MOCK_FAIL_ALL");
    if (env && env[0] == '1') return MOCK_ERR_NO_BINARY;
    if (!txt || strstr(txt, ".version") == NULL || strstr(txt, "zipcrack") == NULL)
        return MOCK_ERR_INVALID_PTX;
    env = getenv("MOCK_REJECT_ISA");
    if (env && env[0] != 0) {
        /* 找 .version 行 */
        const char *v = strstr(txt, ".version");
        if (v) {
            int major = 0;
            sscanf(v + 8, " %d", &major);
            if (major == atoi(env)) return MOCK_ERR_NO_BINARY;
        }
    }
    if (mod) *mod = (CUmodule)0x1000;
    return MOCK_OK;
}
__declspec(dllexport) CUresult __cdecl cuModuleUnload(CUmodule mod) { (void)mod; return MOCK_OK; }
__declspec(dllexport) CUresult __cdecl cuModuleGetFunction(CUfunction *fn, CUmodule mod,
                                                            const char *name) {
    (void)mod;
    if (!name || strcmp(name, "zipcrack") != 0) return 1;
    if (fn) *fn = (CUfunction)0x2000;
    return MOCK_OK;
}

__declspec(dllexport) CUresult __cdecl cuMemAlloc_v2(CUdeviceptr *ptr, size_t n) {
    void *p = malloc(n ? n : 1);
    if (!p) return 2;
    memset(p, 0, n ? n : 1);
    if (ptr) *ptr = (CUdeviceptr)(uintptr_t)p;
    return MOCK_OK;
}
__declspec(dllexport) CUresult __cdecl cuMemFree_v2(CUdeviceptr ptr) {
    free((void *)(uintptr_t)ptr);
    return MOCK_OK;
}
__declspec(dllexport) CUresult __cdecl cuMemcpyHtoD_v2(CUdeviceptr dst, const void *src, size_t n) {
    memcpy((void *)(uintptr_t)dst, src, n);
    return MOCK_OK;
}
__declspec(dllexport) CUresult __cdecl cuMemcpyDtoH_v2(void *dst, CUdeviceptr src, size_t n) {
    memcpy(dst, (const void *)(uintptr_t)src, n);
    return MOCK_OK;
}
__declspec(dllexport) CUresult __cdecl cuMemsetD32_v2(CUdeviceptr dst, unsigned int v, size_t n) {
    unsigned int *p = (unsigned int *)(uintptr_t)dst;
    for (size_t i = 0; i < n; i++) p[i] = v;
    return MOCK_OK;
}

/* ---------- 参考内核（与 zipcpu.c::try_password 同算法） ---------- */
static int try_password(const unsigned char *pw, int n,
                        const unsigned char *enc, const unsigned char *check,
                        uint32_t ntargets, int *reason) {
    uint32_t k0 = 0x12345678u, k1 = 0x23456789u, k2 = 0x34567890u;
    for (int i = 0; i < n; i++) {
        unsigned char b = pw[i];
        k0 = CRCT[(k0 ^ b) & 0xFF] ^ (k0 >> 8);
        k1 = (k1 + (k0 & 0xFF)) * 134775813u + 1u;
        k2 = CRCT[(k2 ^ (k1 >> 24)) & 0xFF] ^ (k2 >> 8);
    }
    for (uint32_t t = 0; t < ntargets; t++) {
        uint32_t a0 = k0, a1 = k1, a2 = k2;
        unsigned char last = 0;
        for (int i = 0; i < 12; i++) {
            uint32_t tt = (a2 | 2) & 0xFFFF;
            unsigned char p = enc[t * 12 + i] ^ (unsigned char)(((tt * (tt ^ 1)) >> 8) & 0xFF);
            if (i == 11) { last = p; break; }
            a0 = CRCT[(a0 ^ p) & 0xFF] ^ (a0 >> 8);
            a1 = (a1 + (a0 & 0xFF)) * 134775813u + 1u;
            a2 = CRCT[(a2 ^ (a1 >> 24)) & 0xFF] ^ (a2 >> 8);
        }
        if (last != check[t]) { *reason = 1; return 0; }
    }
    *reason = 0;
    return 1;
}

__declspec(dllexport) CUresult __cdecl cuLaunchKernel(
    CUfunction f, unsigned gx, unsigned gy, unsigned gz,
    unsigned bx, unsigned by, unsigned bz, unsigned shmem,
    CUstream stream, void **params, void **extra) {
    (void)f; (void)gy; (void)gz; (void)by; (void)bz; (void)shmem;
    (void)stream; (void)extra;
    if (!params) return 1;
    const unsigned char *charset = (const unsigned char *)(uintptr_t)(*(uint64_t *)params[0]);
    const uint64_t *bstart = (const uint64_t *)(uintptr_t)(*(uint64_t *)params[1]);
    const uint64_t *bsize = (const uint64_t *)(uintptr_t)(*(uint64_t *)params[2]);
    const unsigned char *blen = (const unsigned char *)(uintptr_t)(*(uint64_t *)params[3]);
    uint32_t nb = *(uint32_t *)params[4];
    uint32_t base = *(uint32_t *)params[5];
    const unsigned char *enc = (const unsigned char *)(uintptr_t)(*(uint64_t *)params[7]);
    const unsigned char *check = (const unsigned char *)(uintptr_t)(*(uint64_t *)params[8]);
    uint32_t ntargets = *(uint32_t *)params[9];
    uint64_t start = *(uint64_t *)params[10];
    uint64_t count = *(uint64_t *)params[11];
    uint32_t *cnt = (uint32_t *)(uintptr_t)(*(uint64_t *)params[12]);
    uint64_t *matches = (uint64_t *)(uintptr_t)(*(uint64_t *)params[13]);
    uint32_t max_matches = *(uint32_t *)params[14];
    uint64_t threads = (uint64_t)gx * bx;
    if (threads > count) threads = count;
    unsigned char pw[48];
    for (uint64_t gid = 0; gid < threads; gid++) {
        uint64_t idx = start + gid;
        uint32_t L = 0;
        uint64_t off = 0;
        for (uint32_t i = 0; i < nb; i++) {
            if (idx < bstart[i] + bsize[i]) { L = blen[i]; off = idx - bstart[i]; break; }
        }
        if (L == 0 || base < 2) continue;
        for (uint32_t k = 0; k < L; k++) {
            pw[L - 1 - k] = charset[off % base];
            off /= base;
        }
        int reason = 0;
        if (try_password(pw, (int)L, enc, check, ntargets, &reason)) {
            uint32_t slot = (*cnt)++;
            if (slot < max_matches) matches[slot] = idx;
        }
    }
    return MOCK_OK;
}
