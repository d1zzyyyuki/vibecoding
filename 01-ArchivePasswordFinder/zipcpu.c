/* zipcpu.c —— 最早动手写的就是这一版 CPU 引擎。
 * Win32 线程 + zlib，先把 ZipCrypto 的 12 字节头和解压后的 CRC 校验跑通；
 * Python 那边通过 ctypes 加载这个 DLL。后面 CUDA/OpenCL 的验证结果都以这里为准。 */
#include <windows.h>
#include <stdint.h>
#include <string.h>
#include <stdlib.h>
#include "zlib.h"

#define MAXPW 64
#define BATCH 1024

static uint32_t CRCT[256];
static volatile LONG g_inited = 0;

static void init_crc(void) {
    if (InterlockedCompareExchange(&g_inited, 1, 0) == 0) {
        for (uint32_t n = 0; n < 256; n++) {
            uint32_t c = n;
            for (int k = 0; k < 8; k++)
                c = (c >> 1) ^ (0xEDB88320u & (uint32_t)(-(int32_t)(c & 1)));
            CRCT[n] = c;
        }
        InterlockedExchange(&g_inited, 2);
    }
    while (InterlockedCompareExchange(&g_inited, 2, 2) != 2) Sleep(0);
}

/* ---------- 任务参数 ---------- */
static const unsigned char *j_charset;
static uint32_t j_base;
static const unsigned long long *j_bstart, *j_bsize;
static const unsigned char *j_blen;
static uint32_t j_nbuckets;
static const unsigned char *j_prefix, *j_suffix;
static uint32_t j_plen, j_slen;
static const unsigned char *j_enc, *j_check;
static uint32_t j_ntargets;
static unsigned long long j_total;
static const unsigned char *j_words;
static const unsigned long long *j_woff;
static uint32_t j_nwords;
static int j_words_mode;

/* ---------- 验证目标 ---------- */
static const unsigned char *v_enc;
static const unsigned char *v_data;
static unsigned long long v_datalen;
static int v_method;
static uint32_t v_crc;

static volatile LONG64 g_next, g_done, g_found_idx;
static volatile LONG g_found, g_stop;

/* 用密码解密 12 字节加密头并继续解密数据，deflate 解压后对 CRC 校验。
   返回 1 正确、0 错误、-1 不支持。 */
static int verify_with(const unsigned char *pw, int n,
                       const unsigned char *enc12, const unsigned char *data,
                       unsigned long long datalen, int method, uint32_t expected_crc)
{
    if (!data || datalen == 0 || datalen > (128ull << 20)) return -1;
    if (method != 0 && method != 8) return -1;

    uint32_t k0 = 0x12345678u, k1 = 0x23456789u, k2 = 0x34567890u;
    const uint32_t *tbl = CRCT;
    for (int i = 0; i < n; i++) {
        unsigned char b = pw[i];
        k0 = tbl[(k0 ^ b) & 0xFF] ^ (k0 >> 8);
        k1 = (k1 + (k0 & 0xFF)) * 134775813u + 1u;
        k2 = tbl[(k2 ^ (k1 >> 24)) & 0xFF] ^ (k2 >> 8);
    }
    /* 先“解密”12 字节加密头，只为了推进密钥状态 */
    for (int i = 0; i < 12; i++) {
        uint32_t tt = (k2 | 2) & 0xFFFF;
        unsigned char p = enc12[i] ^ (unsigned char)(((tt * (tt ^ 1)) >> 8) & 0xFF);
        k0 = tbl[(k0 ^ p) & 0xFF] ^ (k0 >> 8);
        k1 = (k1 + (k0 & 0xFF)) * 134775813u + 1u;
        k2 = tbl[(k2 ^ (k1 >> 24)) & 0xFF] ^ (k2 >> 8);
    }
    unsigned char *buf = (unsigned char *)malloc((size_t)datalen);
    if (!buf) return -1;
    for (unsigned long long i = 0; i < datalen; i++) {
        uint32_t tt = (k2 | 2) & 0xFFFF;
        unsigned char p = data[i] ^ (unsigned char)(((tt * (tt ^ 1)) >> 8) & 0xFF);
        buf[i] = p;
        k0 = tbl[(k0 ^ p) & 0xFF] ^ (k0 >> 8);
        k1 = (k1 + (k0 & 0xFF)) * 134775813u + 1u;
        k2 = tbl[(k2 ^ (k1 >> 24)) & 0xFF] ^ (k2 >> 8);
    }
    int ok = 0;
    uint32_t crc = 0;
    if (method == 0) {
        crc = crc32(0, buf, (uInt)datalen);
        ok = 1;
    } else {
        z_stream zs;
        memset(&zs, 0, sizeof(zs));
        if (inflateInit2(&zs, -15) == Z_OK) {
            unsigned char out[64 * 1024];
            zs.next_in = buf;
            zs.avail_in = (uInt)datalen;
            int done = 0;
            while (!done) {
                zs.next_out = out;
                zs.avail_out = sizeof(out);
                int ret = inflate(&zs, Z_NO_FLUSH);
                uInt produced = (uInt)(sizeof(out) - zs.avail_out);
                if (produced) crc = crc32(crc, out, produced);
                if (ret == Z_STREAM_END) { done = 1; ok = 1; }
                else if (ret != Z_OK && ret != Z_BUF_ERROR) break;
                else if (ret == Z_BUF_ERROR && produced == 0) break;
                else if (zs.avail_in == 0 && produced == 0) break;
            }
            inflateEnd(&zs);
        }
    }
    free(buf);
    return ok && (crc == expected_crc);
}

static int try_password(const unsigned char *pw, int n) {
    uint32_t k0 = 0x12345678u, k1 = 0x23456789u, k2 = 0x34567890u;
    const uint32_t *tbl = CRCT;
    for (int i = 0; i < n; i++) {
        unsigned char b = pw[i];
        k0 = tbl[(k0 ^ b) & 0xFF] ^ (k0 >> 8);
        k1 = (k1 + (k0 & 0xFF)) * 134775813u + 1u;
        k2 = tbl[(k2 ^ (k1 >> 24)) & 0xFF] ^ (k2 >> 8);
    }
    for (uint32_t t = 0; t < j_ntargets; t++) {
        uint32_t a0 = k0, a1 = k1, a2 = k2;
        unsigned char last = 0;
        for (int i = 0; i < 12; i++) {
            uint32_t tt = (a2 | 2) & 0xFFFF;
            unsigned char p = j_enc[t * 12 + i] ^ (unsigned char)(((tt * (tt ^ 1)) >> 8) & 0xFF);
            if (i == 11) { last = p; break; }
            a0 = tbl[(a0 ^ p) & 0xFF] ^ (a0 >> 8);
            a1 = (a1 + (a0 & 0xFF)) * 134775813u + 1u;
            a2 = tbl[(a2 ^ (a1 >> 24)) & 0xFF] ^ (a2 >> 8);
        }
        if (last != j_check[t]) return 0;
    }
    if (v_data) {
        int vr = verify_with(pw, n, v_enc, v_data, v_datalen, v_method, v_crc);
        if (vr == 0) return 0;
    }
    return 1;
}

static DWORD WINAPI worker(LPVOID unused) {
    (void)unused;
    unsigned char pw[MAXPW];
    for (;;) {
        if (g_found || g_stop) break;
        LONG64 start = InterlockedExchangeAdd64(&g_next, BATCH);
        if ((unsigned long long)start >= j_total) break;
        uint64_t n = j_total - (uint64_t)start;
        if (n > BATCH) n = BATCH;
        uint64_t k = 0;
        for (; k < n; k++) {
            if (g_found || g_stop) break;
            uint64_t idx = (uint64_t)start + k;
            int len = 0;
            if (j_words_mode) {
                const unsigned char *w = j_words + j_woff[idx];
                len = (int)(j_woff[idx + 1] - j_woff[idx]);
                if (len > MAXPW) len = MAXPW;
                memcpy(pw, w, (size_t)len);
            } else {
                uint64_t off = 0;
                uint32_t L = 0;
                for (uint32_t i = 0; i < j_nbuckets; i++) {
                    if (idx < j_bstart[i] + j_bsize[i]) { L = j_blen[i]; off = idx - j_bstart[i]; break; }
                }
                uint32_t pos = 0;
                memcpy(pw, j_prefix, j_plen); pos += j_plen;
                for (uint32_t q = 0; q < L; q++) {
                    pw[pos + L - 1 - q] = j_charset[off % j_base];
                    off /= j_base;
                }
                pos += L;
                memcpy(pw + pos, j_suffix, j_slen); pos += j_slen;
                len = (int)pos;
            }
            if (try_password(pw, len)) {
                InterlockedExchange64(&g_found_idx, (LONG64)idx);
                InterlockedExchange(&g_found, 1);
                InterlockedAdd64(&g_done, (LONG64)(k + 1));
                return 0;
            }
        }
        InterlockedAdd64(&g_done, (LONG64)k);
    }
    return 0;
}

__declspec(dllexport) int zipcpu_crack(
    const unsigned char *charset, uint32_t base, int minlen, int maxlen,
    const unsigned long long *bstart, const unsigned long long *bsize,
    const unsigned char *blen, uint32_t nbuckets,
    const unsigned char *prefix, uint32_t plen,
    const unsigned char *suffix, uint32_t slen,
    const unsigned char *enc, const unsigned char *check, uint32_t ntargets,
    unsigned long long total, unsigned long long start,
    int nthreads,
    const unsigned char *words, const unsigned long long *woff, uint32_t nwords)
{
    init_crc();
    if (nthreads < 1) nthreads = 1;
    if (nthreads > 256) nthreads = 256;

    j_charset = charset; j_base = base;
    j_bstart = bstart; j_bsize = bsize; j_blen = blen; j_nbuckets = nbuckets;
    j_prefix = prefix; j_plen = plen; j_suffix = suffix; j_slen = slen;
    j_enc = enc; j_check = check; j_ntargets = ntargets;
    j_total = total;
    j_words = words; j_woff = woff; j_nwords = nwords;
    j_words_mode = (words != NULL) ? 1 : 0;

    g_next = (LONG64)start; g_done = 0; g_found = 0; g_stop = 0; g_found_idx = -1;

    HANDLE th[256];
    int started = 0;
    for (int i = 0; i < nthreads; i++) {
        th[i] = CreateThread(NULL, 0, worker, NULL, 0, NULL);
        if (!th[i]) break;
        started++;
    }
    if (started > 0) WaitForMultipleObjects((DWORD)started, th, TRUE, INFINITE);
    for (int i = 0; i < started; i++) if (th[i]) CloseHandle(th[i]);

    if (g_found) return 1;
    if (g_stop) return -1;
    return 0;
}

__declspec(dllexport) void zipcpu_set_verify(const unsigned char *enc12,
                                             const unsigned char *data,
                                             unsigned long long datalen,
                                             int method, uint32_t expected_crc)
{
    v_enc = enc12; v_data = data; v_datalen = datalen; v_method = method; v_crc = expected_crc;
}

__declspec(dllexport) void zipcpu_clear_verify(void) { v_data = NULL; }

__declspec(dllexport) void zipcpu_stop(void) { InterlockedExchange(&g_stop, 1); }

__declspec(dllexport) unsigned long long zipcpu_done(void) { return (unsigned long long)g_done; }

__declspec(dllexport) unsigned long long zipcpu_found_index(void) { return (unsigned long long)g_found_idx; }

__declspec(dllexport) void zipcpu_reset_stop(void) { InterlockedExchange(&g_stop, 0); }

__declspec(dllexport) int zipcpu_try(const unsigned char *pw, int n,
                                     const unsigned char *enc, const unsigned char *check,
                                     uint32_t ntargets)
{
    init_crc();
    j_enc = enc; j_check = check; j_ntargets = ntargets;
    return try_password(pw, n);
}

__declspec(dllexport) int zipcpu_verify(const unsigned char *pw, int pwlen,
                                        const unsigned char *enc12,
                                        const unsigned char *data,
                                        unsigned long long datalen,
                                        int method, uint32_t expected_crc)
{
    init_crc();
    return verify_with(pw, pwlen, enc12, data, datalen, method, expected_crc);
}
