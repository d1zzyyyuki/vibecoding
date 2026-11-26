/* fake_cl.c —— 假 cl.exe：让 CUDA 8 的 nvcc 在“只有 MinGW、没有 MSVC”的机器上也能生成 PTX。
 *
 * 背景：nvcc 生成 PTX 时仍会调用 host 编译器做预处理（cl.exe -E）。这里把 -E 请求
 * 转给 MinGW 的 g++，并把 nvcc 的 MSVC 风格参数翻译成 gcc 参数；其它调用（真正编译
 * host 目标文件）直接假装成功——反正只取 PTX，host 目标文件会被丢掉。
 *
 * 环境变量（由 build_cuda_ptx.py 设置）：
 *   FAKE_CL_GXX        g++.exe 的完整路径
 *   FAKE_CL_CUDA_INC   CUDA 8 的 include 目录
 *   FAKE_CL_LOG        可选：把每次调用记录到这个文件
 *
 * 编译： gcc -O2 -o cl.exe fake_cl.c
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <process.h>

#define MAXARGS 512

static int has_arg(int argc, char **argv, const char *flag) {
    for (int i = 1; i < argc; i++)
        if (strcmp(argv[i], flag) == 0) return i;
    return 0;
}

static void log_call(int argc, char **argv) {
    const char *log = getenv("FAKE_CL_LOG");
    if (!log) return;
    FILE *f = fopen(log, "a");
    if (!f) return;
    fprintf(f, "cl");
    for (int i = 1; i < argc; i++) fprintf(f, " [%s]", argv[i]);
    fprintf(f, "\n");
    fclose(f);
}

/* 值紧跟其后的 MSVC 参数：解析输入文件时要跳过它们的值 */
static int flag_takes_value(const char *a) {
    static const char *flags[] = {"-FI", "-I", "-D", "-U", "-include", "-o",
                                  "-Fo", "-Fd", "-c", NULL};
    for (int i = 0; flags[i]; i++)
        if (strcmp(a, flags[i]) == 0) return 1;
    return 0;
}

/* 用 _spawnv 调 g++：参数逐个传递，避免 system()/cmd 的引号问题，stdout 直接继承 */
static int run_gxx(char **gargs) {
    const char *gxx = getenv("FAKE_CL_GXX");
    if (!gxx) gxx = "g++";
    const char *log = getenv("FAKE_CL_LOG");
    if (log) {
        FILE *f = fopen(log, "a");
        if (f) {
            fprintf(f, "  gxx");
            for (int i = 1; gargs[i]; i++) fprintf(f, " [%s]", gargs[i]);
            fprintf(f, "\n");
            fclose(f);
        }
    }
    intptr_t rc = _spawnv(_P_WAIT, gxx, (const char *const *)gargs);
    return rc == 0 ? 0 : 1;
}

/* ---------- 响应文件 @file 展开（MSVC 风格：空白分隔，"..." 引号成组） ---------- */
static char **g_argv_expanded = NULL;
static int g_argc_expanded = 0;

/* 从文件读入参数并接在 orig 参数之后，返回新的 argv（静态缓冲区） */
static char **expand_response_files(int argc, char **argv, int *out_argc) {
    static char buf[1 << 20];
    static char *args[MAXARGS];
    int na = 0;
    for (int i = 0; i < argc; i++) args[na++] = argv[i];
    for (int pass = 0; pass < 3; pass++) {
        int expanded_any = 0;
        char *next[MAXARGS];
        int nn = 0;
        for (int i = 0; i < na; i++) {
            if (argv == args && i == 0) { next[nn++] = args[0]; continue; }
            if (args[i][0] == '@' && args[i][1]) {
                FILE *f = fopen(args[i] + 1, "rb");
                if (!f) { next[nn++] = args[i]; continue; }
                size_t n = fread(buf, 1, sizeof(buf) - 1, f);
                buf[n] = 0;
                fclose(f);
                char *p = buf;
                while (*p) {
                    while (*p && (*p == ' ' || *p == '\t' || *p == '\r' || *p == '\n')) p++;
                    if (!*p) break;
                    char *start = p;
                    if (*p == '"') {
                        p++;
                        start = p;
                        while (*p && *p != '"') p++;
                        if (*p) *p++ = 0;
                    } else {
                        while (*p && !(*p == ' ' || *p == '\t' || *p == '\r' || *p == '\n')) p++;
                        if (*p) *p++ = 0;
                    }
                    if (nn < MAXARGS - 1) next[nn++] = start;
                }
                expanded_any = 1;
            } else {
                next[nn++] = args[i];
            }
        }
        for (int i = 0; i < nn; i++) args[i] = next[i];
        na = nn;
        if (!expanded_any) break;
    }
    *out_argc = na;
    return args;
}

int main(int argc, char **argv) {
    char **xargv = expand_response_files(argc, argv, &argc);
    argv = xargv;
    log_call(argc, argv);
    {
        const char *dbg = getenv("FAKE_CL_DEBUG");
        if (dbg) {
            FILE *f = fopen(dbg, "a");
            if (f) {
                fprintf(f, "argc=%d gxx=%s inc=%s\n", argc,
                        getenv("FAKE_CL_GXX") ? getenv("FAKE_CL_GXX") : "(none)",
                        getenv("FAKE_CL_CUDA_INC") ? getenv("FAKE_CL_CUDA_INC") : "(none)");
                for (int i = 0; i < argc; i++) fprintf(f, "  [%d] %s\n", i, argv[i]);
                fclose(f);
            }
        }
    }
    if (argc <= 1 || has_arg(argc, argv, "--version") || has_arg(argc, argv, "-Bv")) {
        printf("Microsoft (R) C/C++ Optimizing Compiler Version 19.00.24215.1 for x64\n"
               "Copyright (C) Microsoft Corporation.  All rights reserved.\n");
        return 0;
    }
    if (has_arg(argc, argv, "-E")) {
        char *gargs[MAXARGS];
        int ng = 0;
        const char *input = NULL;
        const char *gxx = getenv("FAKE_CL_GXX");
        const char *inc = getenv("FAKE_CL_CUDA_INC");
        if (!gxx) gxx = "g++";
        gargs[ng++] = (char *)gxx;
        gargs[ng++] = (char *)"-E";
        gargs[ng++] = (char *)"-P";
        gargs[ng++] = (char *)"-x";
        gargs[ng++] = (char *)(has_arg(argc, argv, "-TC") ? "c" : "c++");
        {
            /* FAKE_CL_EXTRA：额外 gcc 参数（空格分隔），用于切到 MSVC 方言预处理 */
            const char *extra = getenv("FAKE_CL_EXTRA");
            static char extra_buf[2048];
            if (extra && *extra) {
                strncpy(extra_buf, extra, sizeof(extra_buf) - 1);
                extra_buf[sizeof(extra_buf) - 1] = 0;
                char *p = extra_buf;
                while (*p && ng < MAXARGS - 6) {
                    while (*p == ' ' || *p == '\t') p++;
                    if (!*p) break;
                    char *s = p;
                    while (*p && *p != ' ' && *p != '\t') p++;
                    if (*p) *p++ = 0;
                    gargs[ng++] = s;
                }
            }
        }
        if (inc) {
            const char *shim = getenv("FAKE_CL_SHIM");
            if (shim) {
                gargs[ng++] = (char *)"-I";
                gargs[ng++] = (char *)shim;
            }
            gargs[ng++] = (char *)"-I";
            gargs[ng++] = (char *)inc;
        }
        for (int i = 1; i < argc && ng < MAXARGS - 4; i++) {
            const char *a = argv[i];
            if (!strcmp(a, "-E") || !strcmp(a, "-nologo") || !strcmp(a, "-EHsc") ||
                !strcmp(a, "-TP") || !strcmp(a, "-TC"))
                continue;
            if (!strcmp(a, "-FI") && i + 1 < argc) {
                gargs[ng++] = (char *)"-include";
                gargs[ng++] = argv[++i];
                continue;
            }
            if (!strcmp(a, "-I") && i + 1 < argc) {
                gargs[ng++] = (char *)"-I";
                gargs[ng++] = argv[++i];
                continue;
            }
            if (!strcmp(a, "-D") && i + 1 < argc) {
                gargs[ng++] = (char *)"-D";
                gargs[ng++] = argv[++i];
                continue;
            }
            if (!strncmp(a, "-I", 2) || !strncmp(a, "-D", 2) || !strncmp(a, "-U", 2)) {
                gargs[ng++] = (char *)a;
                continue;
            }
            if (flag_takes_value(a)) {
                i++;
                continue;
            }
            if (a[0] == '-') continue;
            input = a;
        }
        if (!input) {
            fprintf(stderr, "fake cl: no input file\n");
            return 1;
        }
        gargs[ng++] = (char *)input;
        gargs[ng++] = NULL;
        return run_gxx(gargs);
    }
    /* host 目标文件：假装编译成功（-ptx 模式下产物会被丢弃） */
    const char *fo = NULL;
    for (int i = 1; i < argc; i++) {
        if (!strncmp(argv[i], "-Fo", 3)) fo = argv[i] + 3;
        else if (!strcmp(argv[i], "-Fo") && i + 1 < argc) fo = argv[++i];
    }
    if (fo) {
        FILE *f = fopen(fo, "wb");
        if (f) fclose(f);
    }
    return 0;
}
