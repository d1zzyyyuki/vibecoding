# -*- coding: utf-8 -*-
"""把 zipcuda.cu 编译成多架构 PTX（构建期工具，不打包进 exe）。

三套编译器分别生成：
    - NVRTC 12.9：PTX ISA 8.8，compute_50 … compute_121（Maxwell → Blackwell）
    - NVRTC 11.8：PTX ISA 7.8，给驱动较旧的机器
    - CUDA 8.0 nvcc：PTX ISA 5.0，compute_20 … compute_62（Fermi / Kepler）

运行时只加载 assets/cuda/*.ptx，不需要 CUDA Toolkit。用法见 tools/README.md。
"""
import argparse
import ctypes
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


# ---------------------------------------------------------------------------
# NVRTC
# ---------------------------------------------------------------------------
class Nvrtc:
    def __init__(self, bin_dir):
        bin_dir = os.path.abspath(bin_dir)
        if not os.path.isdir(bin_dir):
            raise SystemExit("NVRTC bin dir not found: %s" % bin_dir)
        os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
        os.add_dll_directory(bin_dir)
        names = [n for n in os.listdir(bin_dir) if n.lower().startswith("nvrtc-builtins64")]
        for n in names:
            ctypes.WinDLL(os.path.join(bin_dir, n))  # 必须预加载，NVRTC 自己按名字找不到
        dlls = [n for n in os.listdir(bin_dir)
                if n.lower().startswith("nvrtc64") and n.lower().endswith(".dll")
                and ".alt." not in n.lower()]
        if not dlls:
            raise SystemExit("nvrtc64*.dll not found in %s" % bin_dir)
        self.lib = ctypes.WinDLL(os.path.join(bin_dir, dlls[0]))
        lib = self.lib
        lib.nvrtcCreateProgram.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_char_p,
                                           ctypes.c_char_p, ctypes.c_int,
                                           ctypes.POINTER(ctypes.c_char_p),
                                           ctypes.POINTER(ctypes.c_char_p)]
        lib.nvrtcCreateProgram.restype = ctypes.c_int
        lib.nvrtcCompileProgram.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                            ctypes.POINTER(ctypes.c_char_p)]
        lib.nvrtcCompileProgram.restype = ctypes.c_int
        lib.nvrtcGetPTXSize.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t)]
        lib.nvrtcGetPTXSize.restype = ctypes.c_int
        lib.nvrtcGetPTX.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        lib.nvrtcGetPTX.restype = ctypes.c_int
        lib.nvrtcGetProgramLogSize.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t)]
        lib.nvrtcGetProgramLogSize.restype = ctypes.c_int
        lib.nvrtcGetProgramLog.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        lib.nvrtcGetProgramLog.restype = ctypes.c_int
        lib.nvrtcDestroyProgram.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
        lib.nvrtcDestroyProgram.restype = ctypes.c_int
        lib.nvrtcGetNumSupportedArchs.argtypes = [ctypes.POINTER(ctypes.c_int)]
        lib.nvrtcGetNumSupportedArchs.restype = ctypes.c_int
        lib.nvrtcGetSupportedArchs.argtypes = [ctypes.POINTER(ctypes.c_int)]
        lib.nvrtcGetSupportedArchs.restype = ctypes.c_int
        lib.nvrtcGetErrorString.argtypes = [ctypes.c_int]
        lib.nvrtcGetErrorString.restype = ctypes.c_char_p

    def _err(self, code):
        s = self.lib.nvrtcGetErrorString(code)
        return s.decode() if s else str(code)

    def supported_archs(self):
        n = ctypes.c_int()
        self.lib.nvrtcGetNumSupportedArchs(ctypes.byref(n))
        arr = (ctypes.c_int * n.value)()
        self.lib.nvrtcGetSupportedArchs(arr)
        return [arr[i] for i in range(n.value)]

    def compile_ptx(self, src, arch, extra_opts=()):
        lib = self.lib
        prog = ctypes.c_void_p()
        rc = lib.nvrtcCreateProgram(ctypes.byref(prog), src.encode(), b"zipcuda.cu", 0, None, None)
        if rc != 0:
            raise RuntimeError("nvrtcCreateProgram: " + self._err(rc))
        opts = ["--gpu-architecture=compute_%d" % arch]
        opts.extend(extra_opts)
        arr = (ctypes.c_char_p * len(opts))(*[o.encode() for o in opts])
        try:
            rc = lib.nvrtcCompileProgram(prog, len(opts), arr)
            size = ctypes.c_size_t()
            lib.nvrtcGetProgramLogSize(prog, ctypes.byref(size))
            log = ""
            if size.value:
                buf = ctypes.create_string_buffer(size.value)
                lib.nvrtcGetProgramLog(prog, buf)
                log = buf.value.decode("utf-8", "replace")
            if rc != 0:
                raise RuntimeError("nvrtcCompileProgram(compute_%d): %s\n%s"
                                   % (arch, self._err(rc), log))
            lib.nvrtcGetPTXSize(prog, ctypes.byref(size))
            buf = ctypes.create_string_buffer(size.value)
            if lib.nvrtcGetPTX(prog, buf) != 0:
                raise RuntimeError("nvrtcGetPTX failed")
            return buf.value.decode("utf-8", "replace"), log
        finally:
            lib.nvrtcDestroyProgram(ctypes.byref(prog))


def ptx_meta(ptx):
    """从 PTX 文本里读出 (isa 版本字符串, target 名称)。"""
    ver = "?"
    target = "?"
    for line in ptx.splitlines():
        line = line.strip()
        if line.startswith(".version"):
            ver = line.split(None, 1)[1]
        elif line.startswith(".target"):
            target = line.split(None, 1)[1]
        elif line.startswith(".entry") or line.startswith(".visible .entry"):
            break
    return ver, target


def write_ptx(out_dir, arch, ptx, toolkit):
    ver, target = ptx_meta(ptx)
    isa = ver.replace(".", "")
    name = "zipcrack_sm%d_isa%s.ptx" % (arch, isa)
    path = os.path.join(out_dir, name)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(ptx)
    print("  sm_%-3d ISA %-4s target %-8s %6.1f KB  %s  [%s]"
          % (arch, ver, target, len(ptx) / 1024.0, name, toolkit))
    return path


# ---------------------------------------------------------------------------
# nvcc（仅用于 Fermi/Kepler 的 legacy PTX）
# ---------------------------------------------------------------------------
def find_nvcc(path):
    if os.path.isfile(path):
        return path
    raise SystemExit("nvcc not found: %s" % path)


def compile_nvcc(nvcc, src_path, arch, toolkit_name, fake_cl_dir=None, gxx=None,
                 cuda_inc=None, cuda_shim=None):
    """用 CUDA 8.0 的 nvcc 生成 compute_XX 的 PTX。

    没有 MSVC 的机器上通过 fake cl.exe 转给 MinGW g++ 预处理，再由 cudafe/cicc 生成。
    """
    out = os.path.join(os.path.dirname(nvcc), "_zipcuda_%d.ptx" % arch)
    src_path = os.path.abspath(src_path)
    env = dict(os.environ)
    if fake_cl_dir:
        env["PATH"] = os.path.abspath(fake_cl_dir) + os.pathsep + env.get("PATH", "")
        env["FAKE_CL_GXX"] = os.path.abspath(gxx or "g++")
        if cuda_inc:
            env["FAKE_CL_CUDA_INC"] = os.path.abspath(cuda_inc)
        if cuda_shim:
            env["FAKE_CL_SHIM"] = os.path.abspath(cuda_shim)
        env["FAKE_CL_EXTRA"] = ("-U__GNUC__ -U__declspec -U__stdcall -U__cdecl "
                                "-U__fastcall -U__thiscall -D_MSC_VER=1900 "
                                "-D_MSC_FULL_VER=190024215 -D_WIN32=1 -D_WIN64=1 "
                                "-D_M_X64=100")
    cmd = [nvcc, "--use-local-env", "--cl-version=2015", "-ptx",
           "-arch=compute_%d" % arch, "-o", out, src_path]
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       cwd=os.path.dirname(nvcc), env=env)
    txt = (r.stdout or b"").decode("utf-8", "replace")
    if r.returncode != 0 or not os.path.isfile(out):
        raise RuntimeError("nvcc compute_%d failed (rc=%d):\n%s" % (arch, r.returncode, txt))
    with open(out, "r", encoding="utf-8", errors="replace") as f:
        ptx = f.read()
    os.remove(out)
    if ".entry zipcrack" not in ptx:
        raise RuntimeError("nvcc compute_%d produced no kernel:\n%s" % (arch, txt))
    return ptx, txt


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--nvrtc-bin", default=None, help="NVRTC bin 目录（内含 nvrtc64*.dll）")
    ap.add_argument("--nvcc", default=None, help="legacy nvcc.exe（CUDA 8.0）")
    ap.add_argument("--fake-cl-dir", default=os.path.join(HERE, "fakecl"),
                    help="假 cl.exe 所在目录（由 tools/fake_cl.c 编译）")
    ap.add_argument("--gxx", default=None, help="MinGW g++.exe 路径（fake cl 用）")
    ap.add_argument("--cuda-inc", default=None, help="CUDA 8 include 目录")
    ap.add_argument("--cuda-shim", default=os.path.join(HERE, "cuda8shim"),
                    help="精简版 cuda_runtime.h 所在目录")
    ap.add_argument("--archs", default=None, help="要编译的架构列表，逗号分隔；默认自动")
    ap.add_argument("--out", default=os.path.join(ROOT, "assets", "cuda"))
    ap.add_argument("--toolkit", default="nvrtc", help="写入日志的标签")
    ap.add_argument("--ptxas", default=None, help="可选：用 ptxas 静态校验生成的 PTX")
    args = ap.parse_args(argv)

    out_dir = os.path.abspath(args.out)
    os.makedirs(out_dir, exist_ok=True)
    src_path = os.path.join(ROOT, "zipcuda.cu")
    with open(src_path, "r", encoding="utf-8") as f:
        src = f.read()

    archs = None
    if args.archs:
        archs = [int(x) for x in args.archs.split(",") if x.strip()]

    made = []
    if args.nvrtc_bin:
        nv = Nvrtc(args.nvrtc_bin)
        sup = nv.supported_archs()
        todo = archs if archs else sup
        todo = [a for a in todo if a in sup]
        print("NVRTC %s supported: %s" % (args.toolkit, sup))
        print("compiling %d archs -> %s" % (len(todo), out_dir))
        for a in todo:
            ptx, log = nv.compile_ptx(src, a)
            made.append(write_ptx(out_dir, a, ptx, args.toolkit))
    elif args.nvcc:
        nvcc = find_nvcc(args.nvcc)
        todo = archs or [20, 30, 32, 35, 37, 50, 52, 53, 60, 61, 62]
        print("nvcc %s: compiling %d archs -> %s" % (nvcc, len(todo), out_dir))
        for a in todo:
            ptx, txt = compile_nvcc(nvcc, src_path, a, args.toolkit,
                                    fake_cl_dir=args.fake_cl_dir, gxx=args.gxx,
                                    cuda_inc=args.cuda_inc, cuda_shim=args.cuda_shim)
            made.append(write_ptx(out_dir, a, ptx, args.toolkit))
    else:
        raise SystemExit("either --nvrtc-bin or --nvcc is required")

    if args.ptxas and made:
        print("validating %d PTX with ptxas..." % len(made))
        for path in made:
            arch = int(re.search(r"sm(\d+)", os.path.basename(path)).group(1))
            cubin = os.path.join(out_dir, "_check.cubin")
            ok = False
            for use_arch in (arch, 50, 75):
                r = subprocess.run([args.ptxas, "-arch=sm_%d" % use_arch, "-v", path,
                                    "-o", cubin], stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT)
                txt = (r.stdout or b"").decode("utf-8", "replace")
                if "is not defined for option" in txt:
                    continue  # 这份 ptxas 不认这个架构，换个架构只做语法校验
                if r.returncode != 0:
                    raise SystemExit("ptxas rejected %s:\n%s" % (path, txt))
                info = [ln.strip() for ln in txt.splitlines() if "Used" in ln or "spill" in ln]
                print("  OK sm_%-3d %s" % (arch, " | ".join(info)))
                ok = True
                break
            if not ok:
                print("  SKIP sm_%-3d（当前 ptxas 不支持该校验架构）" % arch)
            if os.path.isfile(cubin):
                os.remove(cubin)

    print("done: %d PTX files in %s" % (len(made), out_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
