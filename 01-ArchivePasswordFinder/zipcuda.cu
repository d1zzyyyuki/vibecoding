/* zipcuda.cu —— ZipCrypto 候选扫描内核（CUDA）。
 *
 * 算法与 zipcpu.c、gpu.py 一致：一个线程试一个候选密码，联合校验各目标文件的
 * 12 字节加密头，全部命中才记录。
 *
 * GPU 上的几处取舍：
 *   - CRC32 表放在每个 block 的共享内存里现场生成（常量内存遇到随机索引会串行化）。
 *   - 密码打包进两个 64 位寄存器，避免动态下标的栈数组退化成局部内存。
 *   - 序号解码最多做一次 64 位除法：先按 base^4 拆成商和余，其余用 32 位除法。
 *   - 只用 Fermi 也支持的指令，同一份源码可编到 sm_20 和 sm_120。
 *
 * 由 build_cuda_ptx.py 编译成 assets/cuda/*.ptx。
 */
typedef unsigned char u8;
typedef unsigned int u32;
typedef unsigned long long u64;

#define MAXLEN 8

extern "C" __global__ void zipcrack(
    const u8* __restrict__ charset,
    const u64* __restrict__ bucket_start,
    const u64* __restrict__ bucket_size,
    const u8* __restrict__ bucket_len,
    const u32 nbuckets,
    const u32 base,
    const u32 base4,
    const u8* __restrict__ enc,
    const u8* __restrict__ check,
    const u32 ntargets,
    const u64 start,
    const u64 count,
    u32* match_count,
    u64* matches,
    const u32 max_matches)
{
    /* CRC32 表：每个 block 现场生成一份 */
    __shared__ u32 tbl[256];
    {
        u32 c = (u32)threadIdx.x;
        #pragma unroll
        for (int k = 0; k < 8; k++) {
            c = (c >> 1) ^ (0xEDB88320u & (u32)(-(int)(c & 1u)));
        }
        tbl[threadIdx.x] = c;
    }
    __syncthreads();

    u64 gid = (u64)blockIdx.x * (u64)blockDim.x + (u64)threadIdx.x;
    if (gid >= count) return;
    u64 idx = start + gid;

    /* 候选序号 → 长度桶 */
    u32 L = 0;
    u64 off = 0;
    u32 nb = nbuckets < 8u ? nbuckets : 8u;
    #pragma unroll 1
    for (u32 i = 0; i < nb; i++) {
        if (idx < bucket_start[i] + bucket_size[i]) {
            L = (u32)bucket_len[i];
            off = idx - bucket_start[i];
            break;
        }
    }
    if (L > (u32)MAXLEN) L = (u32)MAXLEN;
    if (base < 2u || L == 0u) return;

    /* 拆成 base^4 的商和余，最多一次 64 位除法 */
    u32 q, r;
    if (off <= 0xFFFFFFFFull) {
        u32 o = (u32)off;
        q = o / base4;
        r = o - q * base4;
    } else {
        u64 qq = off / (u64)base4;
        q = (u32)qq;
        r = (u32)(off - qq * (u64)base4);
    }

    /* 密码打包进 lo / hi 两个寄存器 */
    u64 lo = 0, hi = 0;
    u32 pos = L - 1u;
    #pragma unroll
    for (u32 k = 0; k < 4u; k++) {
        if (k < L) {
            u32 d = (u32)charset[r % base];
            r /= base;
            if (pos < 8u) { if (pos >= 4u) hi |= (u64)d << (8u * (pos - 4u)); else lo |= (u64)d << (8u * pos); }
            pos--;
        }
    }
    #pragma unroll
    for (u32 k = 4u; k < (u32)MAXLEN; k++) {
        if (k < L) {
            u32 d = (u32)charset[q % base];
            q /= base;
            if (pos < 8u) { if (pos >= 4u) hi |= (u64)d << (8u * (pos - 4u)); else lo |= (u64)d << (8u * pos); }
            pos--;
        }
    }

    /* 密码 → ZipCrypto 三密钥 */
    u32 k0 = 0x12345678u, k1 = 0x23456789u, k2 = 0x34567890u;
    #pragma unroll
    for (u32 i = 0; i < (u32)MAXLEN; i++) {
        if (i < L) {
            u8 b = (u8)(i < 4u ? (u32)((lo >> (8u * i)) & 0xFFu)
                              : (u32)((hi >> (8u * (i - 4u))) & 0xFFu));
            k0 = tbl[(k0 ^ b) & 0xFFu] ^ (k0 >> 8);
            k1 = (k1 + (k0 & 0xFFu)) * 134775813u + 1u;
            k2 = tbl[(k2 ^ (k1 >> 24)) & 0xFFu] ^ (k2 >> 8);
        }
    }

    /* 联合校验所有目标的加密头 */
    #pragma unroll 1
    for (u32 t = 0; t < ntargets; t++) {
        u32 a0 = k0, a1 = k1, a2 = k2;
        u8 last = 0;
        #pragma unroll
        for (u32 i = 0; i < 12u; i++) {
            u32 tt = (a2 | 2u) & 0xFFFFu;
            u8 p = enc[t * 12u + i] ^ (u8)(((tt * (tt ^ 1u)) >> 8) & 0xFFu);
            if (i == 11u) { last = p; break; }
            a0 = tbl[(a0 ^ p) & 0xFFu] ^ (a0 >> 8);
            a1 = (a1 + (a0 & 0xFFu)) * 134775813u + 1u;
            a2 = tbl[(a2 ^ (a1 >> 24)) & 0xFFu] ^ (a2 >> 8);
        }
        if (last != check[t]) return;
    }

    /* 命中：原子分配槽位 */
    u32 slot = atomicAdd(match_count, 1u);
    if (slot < max_matches) matches[slot] = idx;
}
