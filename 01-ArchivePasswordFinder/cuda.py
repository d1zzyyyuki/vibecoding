# -*- coding: utf-8 -*-
"""CUDA 引擎：通过 nvcuda.dll（驱动 API）加载预编译 PTX，运行时不需要 CUDA Toolkit。

PTX 由 tools/build_cuda_ptx.py 生成，覆盖 sm_20（Fermi）到 sm_120（RTX 5090）。
运行时按设备算力和驱动版本挑选，见 _ptx_candidates()；接口与 gpu.GPUZipCracker 一致。
"""
import ctypes
import os
import re
import threading
import time

__all__ = ["CudaError", "probe", "best_device", "enum_devices", "CudaZipCracker",
           "ptx_blobs", "available"]

# ---------------------------------------------------------------------------
# 错误码与常量
# ---------------------------------------------------------------------------
CUDA_SUCCESS = 0
CU_DEVICE_ATTRIBUTE_MAX_THREADS_PER_BLOCK = 1
CU_DEVICE_ATTRIBUTE_MULTIPROCESSOR_COUNT = 16
CU_DEVICE_ATTRIBUTE_COMPUTE_CAPABILITY_MAJOR = 75
CU_DEVICE_ATTRIBUTE_COMPUTE_CAPABILITY_MINOR = 76

# 驱动 CUDA 版本 → 可 JIT 的最高 PTX ISA
_ISA_BY_DRIVER = (
    (12090, (8, 8)),
    (12080, (8, 7)),
    (12060, (8, 5)),
    (12040, (8, 5)),
    (12020, (8, 2)),
    (12000, (8, 0)),
    (11080, (7, 8)),
    (11040, (7, 4)),
    (11000, (7, 1)),
    (10020, (6, 5)),
    (10000, (6, 4)),
    (9020, (6, 2)),
    (9000, (6, 0)),
    (8000, (5, 0)),
    (7000, (4, 0)),
)


class CudaError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# nvcuda.dll（驱动 API）绑定
# ---------------------------------------------------------------------------
_DRV = None
_DRV_ERR = None
_DLL_NAME = os.environ.get("PCA_CUDA_DLL") or "nvcuda.dll"  # 测试钩子：可指向 mock DLL


def _bind(lib, name, argtypes, restype=ctypes.c_int):
    fn = getattr(lib, name, None)
    if fn is None:
        alt = name[:-3] if name.endswith("_v2") else name + "_v2"
        fn = getattr(lib, alt, None)
    if fn is None:
        raise CudaError("驱动缺少 API：%s" % name)
    fn.argtypes = argtypes
    fn.restype = restype
    return fn


def _driver():
    """加载并绑定 nvcuda.dll。"""
    global _DRV, _DRV_ERR
    if _DRV is not None:
        return _DRV
    if _DRV_ERR is not None:
        raise CudaError(_DRV_ERR)
    try:
        lib = ctypes.WinDLL(_DLL_NAME)
    except OSError:
        _DRV_ERR = "未找到 nvcuda.dll（本机没有安装 NVIDIA 显卡驱动）"
        raise CudaError(_DRV_ERR)
    d = {"lib": lib}
    try:
        d["cuInit"] = _bind(lib, "cuInit", [ctypes.c_uint])
        d["cuDriverGetVersion"] = _bind(lib, "cuDriverGetVersion",
                                        [ctypes.POINTER(ctypes.c_int)])
        d["cuDeviceGetCount"] = _bind(lib, "cuDeviceGetCount",
                                      [ctypes.POINTER(ctypes.c_int)])
        d["cuDeviceGet"] = _bind(lib, "cuDeviceGet",
                                 [ctypes.POINTER(ctypes.c_int), ctypes.c_int])
        d["cuDeviceGetName"] = _bind(lib, "cuDeviceGetName",
                                     [ctypes.c_char_p, ctypes.c_int, ctypes.c_int])
        d["cuDeviceGetAttribute"] = _bind(lib, "cuDeviceGetAttribute",
                                          [ctypes.POINTER(ctypes.c_int), ctypes.c_int,
                                           ctypes.c_int])
        d["cuDeviceTotalMem_v2"] = _bind(lib, "cuDeviceTotalMem_v2",
                                         [ctypes.POINTER(ctypes.c_size_t), ctypes.c_int])
        d["cuCtxCreate_v2"] = _bind(lib, "cuCtxCreate_v2",
                                    [ctypes.POINTER(ctypes.c_void_p), ctypes.c_uint,
                                     ctypes.c_int])
        d["cuCtxDestroy_v2"] = _bind(lib, "cuCtxDestroy_v2", [ctypes.c_void_p])
        d["cuCtxSetCurrent"] = _bind(lib, "cuCtxSetCurrent", [ctypes.c_void_p])
        d["cuCtxSynchronize"] = _bind(lib, "cuCtxSynchronize", [])
        d["cuModuleLoadData"] = _bind(lib, "cuModuleLoadData",
                                      [ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p])
        d["cuModuleUnload"] = _bind(lib, "cuModuleUnload", [ctypes.c_void_p])
        d["cuModuleGetFunction"] = _bind(lib, "cuModuleGetFunction",
                                         [ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p,
                                          ctypes.c_char_p])
        d["cuMemAlloc_v2"] = _bind(lib, "cuMemAlloc_v2",
                                   [ctypes.POINTER(ctypes.c_ulonglong), ctypes.c_size_t])
        d["cuMemFree_v2"] = _bind(lib, "cuMemFree_v2", [ctypes.c_ulonglong])
        d["cuMemcpyHtoD_v2"] = _bind(lib, "cuMemcpyHtoD_v2",
                                     [ctypes.c_ulonglong, ctypes.c_void_p, ctypes.c_size_t])
        d["cuMemcpyDtoH_v2"] = _bind(lib, "cuMemcpyDtoH_v2",
                                     [ctypes.c_void_p, ctypes.c_ulonglong, ctypes.c_size_t])
        d["cuMemsetD32_v2"] = _bind(lib, "cuMemsetD32_v2",
                                    [ctypes.c_ulonglong, ctypes.c_uint, ctypes.c_size_t])
        d["cuLaunchKernel"] = _bind(lib, "cuLaunchKernel",
                                    [ctypes.c_void_p,
                                     ctypes.c_uint, ctypes.c_uint, ctypes.c_uint,
                                     ctypes.c_uint, ctypes.c_uint, ctypes.c_uint,
                                     ctypes.c_uint, ctypes.c_void_p,
                                     ctypes.POINTER(ctypes.c_void_p),
                                     ctypes.POINTER(ctypes.c_void_p)])
        try:
            d["cuGetErrorName"] = _bind(lib, "cuGetErrorName",
                                        [ctypes.c_int, ctypes.POINTER(ctypes.c_char_p)])
            d["cuGetErrorString"] = _bind(lib, "cuGetErrorString",
                                          [ctypes.c_int, ctypes.POINTER(ctypes.c_char_p)])
        except CudaError:
            d["cuGetErrorName"] = None
            d["cuGetErrorString"] = None
    except CudaError:
        _DRV_ERR = "nvcuda.dll 接口不完整（显卡驱动太旧？）"
        raise CudaError(_DRV_ERR)
    _DRV = d
    return d


def error_text(code):
    code = int(code)
    for key in ("cuGetErrorName", "cuGetErrorString"):
        fn = _DRV.get(key) if _DRV else None
        if not fn:
            continue
        p = ctypes.c_char_p()
        try:
            if fn(code, ctypes.byref(p)) == CUDA_SUCCESS and p.value:
                return "%s(%d)" % (p.value.decode("utf-8", "replace"), code)
        except Exception:
            pass
    return "CUDA 错误码 %d" % code


def _check(code, what):
    code = int(code)
    if code != CUDA_SUCCESS:
        raise CudaError("%s 失败：%s" % (what, error_text(code)))


# ---------------------------------------------------------------------------
# 设备枚举
# ---------------------------------------------------------------------------
_PROBE = None
_PROBE_ERR = None


def _driver_version(d):
    v = ctypes.c_int(0)
    if d["cuDriverGetVersion"](ctypes.byref(v)) != CUDA_SUCCESS:
        return 0
    return int(v.value)


def _max_isa(driver_version):
    for limit, isa in _ISA_BY_DRIVER:
        if driver_version >= limit:
            return isa
    return None


def enum_devices():
    """列出所有 CUDA 设备。"""
    d = _driver()
    if not d.get("_inited"):
        _check(d["cuInit"](0), "cuInit")
        d["_inited"] = True
    n = ctypes.c_int(0)
    _check(d["cuDeviceGetCount"](ctypes.byref(n)), "cuDeviceGetCount")
    drv = _driver_version(d)
    out = []
    for i in range(n.value):
        dev = ctypes.c_int(0)
        if d["cuDeviceGet"](ctypes.byref(dev), i) != CUDA_SUCCESS:
            continue
        name = ctypes.create_string_buffer(256)
        if d["cuDeviceGetName"](name, 256, dev.value) != CUDA_SUCCESS:
            continue
        major = ctypes.c_int(0)
        minor = ctypes.c_int(0)
        mp = ctypes.c_int(0)
        maxthr = ctypes.c_int(0)
        d["cuDeviceGetAttribute"](ctypes.byref(major),
                                  CU_DEVICE_ATTRIBUTE_COMPUTE_CAPABILITY_MAJOR, dev.value)
        d["cuDeviceGetAttribute"](ctypes.byref(minor),
                                  CU_DEVICE_ATTRIBUTE_COMPUTE_CAPABILITY_MINOR, dev.value)
        d["cuDeviceGetAttribute"](ctypes.byref(mp),
                                  CU_DEVICE_ATTRIBUTE_MULTIPROCESSOR_COUNT, dev.value)
        d["cuDeviceGetAttribute"](ctypes.byref(maxthr),
                                  CU_DEVICE_ATTRIBUTE_MAX_THREADS_PER_BLOCK, dev.value)
        mem = ctypes.c_size_t(0)
        d["cuDeviceTotalMem_v2"](ctypes.byref(mem), dev.value)
        out.append({
            "index": i,
            "device": dev.value,
            "name": name.value.decode("utf-8", "replace").strip(),
            "cc_major": int(major.value),
            "cc_minor": int(minor.value),
            "cc": int(major.value) * 10 + int(minor.value),
            "mp": int(mp.value),
            "max_threads": int(maxthr.value) or 1024,
            "mem": int(mem.value),
            "driver": drv,
            "vendor": "NVIDIA",
            "version": "CUDA driver %.1f" % (drv / 1000.0),
            "type": 4,
            "cus": int(mp.value),
            "max_wg": int(maxthr.value) or 1024,
        })
    return out


def best_device():
    """挑显存最大的设备，失败原因写入 _PROBE_ERR。"""
    global _PROBE, _PROBE_ERR
    if _PROBE is not None:
        return _PROBE
    if _PROBE_ERR is not None:
        return None
    try:
        devs = enum_devices()
    except CudaError as e:
        _PROBE_ERR = str(e)
        return None
    except Exception as e:  # pragma: no cover
        _PROBE_ERR = "CUDA 探测失败：%s" % e
        return None
    if not devs:
        _PROBE_ERR = "NVIDIA 驱动存在，但没有可见的 CUDA 设备"
        return None
    _PROBE = max(devs, key=lambda x: x["mem"])
    return _PROBE


def probe_error():
    return _PROBE_ERR


def available():
    return best_device() is not None


# ---------------------------------------------------------------------------
# PTX 资源与选择
# ---------------------------------------------------------------------------
_BLOBS = None


def ptx_blobs():
    """扫描 assets/cuda/*.ptx，解析架构与 ISA 版本。"""
    global _BLOBS
    if _BLOBS is not None:
        return _BLOBS
    from core import asset_path  # 延迟导入避免循环依赖
    d = asset_path("cuda")
    blobs = []
    try:
        names = sorted(os.listdir(d))
    except OSError:
        names = []
    for name in names:
        if not name.lower().endswith(".ptx"):
            continue
        path = os.path.join(d, name)
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                head = f.read(4096)
        except OSError:
            continue
        arch = None
        isa = None
        for line in head.splitlines():
            s = line.strip()
            if s.startswith(".version"):
                try:
                    isa = tuple(int(x) for x in s.split()[1].split(".")[:2])
                except Exception:
                    isa = None
            elif s.startswith(".target"):
                m = re.search(r"sm_(\d+)", s)
                if m:
                    arch = int(m.group(1))
        if arch is None or isa is None:
            continue
        blobs.append({"path": path, "name": name, "arch": arch, "isa": isa,
                      "text": None})
    _BLOBS = blobs
    return blobs


def _ptx_candidates(dev):
    """按设备算力和驱动 ISA 排序，最匹配的在前。"""
    blobs = ptx_blobs()
    if not blobs:
        return []
    cc = dev.get("cc") or 0
    isa_max = _max_isa(dev.get("driver") or 0)

    def feasible(b):
        if b["arch"] > cc:
            return False
        if isa_max is not None and b["isa"] > isa_max:
            return False
        return True

    good = [b for b in blobs if feasible(b)]
    good.sort(key=lambda b: (b["arch"], b["isa"]), reverse=True)
    rest = [b for b in blobs if not feasible(b)]
    rest.sort(key=lambda b: (b["isa"], b["arch"]))
    return good + rest


def _read_blob(blob):
    if blob.get("text") is None:
        with open(blob["path"], "rb") as f:
            blob["text"] = f.read()
    return blob["text"]


# ---------------------------------------------------------------------------
# 引擎
# ---------------------------------------------------------------------------
class CudaZipCracker:
    """ZipCrypto 的 CUDA 扫描器：一次 launch 处理一个 chunk，收集候选序号。"""

    MAX_MATCHES = 1024
    BLOCK = 256

    def __init__(self, device=None):
        d = _driver()
        dev = device or best_device()
        if dev is None:
            raise CudaError(probe_error() or "没有可用的 CUDA 设备")
        self.dev = dev
        self.build_ms = 0.0
        self.ptx_name = ""
        self._ctx = None
        self._module = None
        self._func = None
        self._thread = None
        err = ctypes.c_void_p()
        _check(d["cuCtxCreate_v2"](ctypes.byref(err), 0, ctypes.c_int(dev["device"])),
               "cuCtxCreate")
        self._ctx = err
        try:
            _check(d["cuCtxSetCurrent"](self._ctx), "cuCtxSetCurrent")
            t0 = time.time()
            self._module = self._load_module()
            func = ctypes.c_void_p()
            _check(d["cuModuleGetFunction"](ctypes.byref(func), self._module, b"zipcrack"),
                   "cuModuleGetFunction(zipcrack)")
            self._func = func
            self.build_ms = (time.time() - t0) * 1000.0
        except Exception:
            self.close()
            raise

    # ---- 资源 ----
    def _load_module(self):
        d = _driver()
        errors = []
        cands = _ptx_candidates(self.dev)
        if not cands:
            raise CudaError("安装包缺少 assets/cuda/*.ptx（CUDA 内核未打包）")
        for blob in cands:
            text = _read_blob(blob)
            mod = ctypes.c_void_p()
            rc = d["cuModuleLoadData"](ctypes.byref(mod), ctypes.c_char_p(text))
            if rc == CUDA_SUCCESS:
                self.ptx_name = blob["name"]
                self.ptx_arch = blob["arch"]
                self.ptx_isa = blob["isa"]
                return mod
            errors.append("%s: %s" % (blob["name"], error_text(rc)))
        raise CudaError("PTX 加载失败（驱动不支持任何已打包内核）：\n  " + "\n  ".join(errors))

    def _set_current(self):
        tid = threading.current_thread()
        if self._thread is not tid:
            _check(_driver()["cuCtxSetCurrent"](self._ctx), "cuCtxSetCurrent")
            self._thread = tid

    def close(self):
        d = None
        try:
            d = _driver()
        except Exception:
            pass
        try:
            if self._module and d:
                d["cuModuleUnload"](self._module)
        except Exception:
            pass
        self._module = None
        try:
            if self._ctx and d:
                d["cuCtxDestroy_v2"](self._ctx)
        except Exception:
            pass
        self._ctx = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    # ---- 显存搬运 ----
    def _alloc(self, nbytes):
        d = _driver()
        p = ctypes.c_ulonglong(0)
        _check(d["cuMemAlloc_v2"](ctypes.byref(p), ctypes.c_size_t(max(1, int(nbytes)))),
               "cuMemAlloc(%d)" % nbytes)
        return p.value

    def _free(self, ptr):
        if ptr:
            try:
                _driver()["cuMemFree_v2"](ctypes.c_ulonglong(ptr))
            except Exception:
                pass

    def _upload(self, data):
        d = _driver()
        ptr = self._alloc(len(data))
        _check(d["cuMemcpyHtoD_v2"](ctypes.c_ulonglong(ptr), ctypes.c_char_p(data),
                                    ctypes.c_size_t(len(data))), "cuMemcpyHtoD")
        return ptr

    def _download(self, ptr, size):
        d = _driver()
        buf = ctypes.create_string_buffer(int(size))
        _check(d["cuMemcpyDtoH_v2"](ctypes.cast(buf, ctypes.c_void_p),
                                    ctypes.c_ulonglong(ptr), ctypes.c_size_t(int(size))),
               "cuMemcpyDtoH")
        return buf.raw

    # ---- 扫描 ----
    def _chunk_size(self, ntargets):
        if ntargets >= 3:
            return 4_000_000
        if ntargets == 2:
            return 1_000_000
        return 65_536

    def iter_chunks(self, space, targets, total, start=0, stop=None):
        """逐块扫描，产出 (命中列表, 已扫数量)。"""
        d = _driver()
        self._set_current()
        base = int(space.base)
        if base < 2 or base > 255:
            raise CudaError("CUDA 内核只支持 2–255 字符集（当前 %d）" % base)
        if len(space.buckets) > 8 or space.max_len > 8:
            raise CudaError("CUDA 内核只支持最长 8 位密码（当前 %d）" % space.max_len)
        charset = space.charset.encode("latin-1")
        buckets = space.buckets
        nb = len(buckets)
        ntargets = len(targets)
        enc = b"".join(bytes(t[0]) for t in targets)
        check = bytes(t[1] for t in targets)
        base4 = base ** 4

        bufs = {}
        try:
            bufs["charset"] = self._upload(charset)
            bufs["bstart"] = self._upload(b"".join(int(b[1]).to_bytes(8, "little")
                                                   for b in buckets))
            bufs["bsize"] = self._upload(b"".join(int(b[2]).to_bytes(8, "little")
                                                  for b in buckets))
            bufs["blen"] = self._upload(bytes(b[0] for b in buckets))
            bufs["enc"] = self._upload(enc)
            bufs["check"] = self._upload(check)
            bufs["cnt"] = self._alloc(4)
            bufs["matches"] = self._alloc(8 * self.MAX_MATCHES)
            chunk = self._chunk_size(ntargets)
            done = max(0, int(start))
            while done < total:
                if stop is not None and stop.is_set():
                    return
                n = min(chunk, total - done)
                _check(d["cuMemsetD32_v2"](ctypes.c_ulonglong(bufs["cnt"]), 0,
                                           ctypes.c_size_t(1)), "cuMemsetD32")
                self._launch(bufs, nb, base, base4, ntargets, done, n)
                _check(d["cuCtxSynchronize"](), "cuCtxSynchronize")
                raw = self._download(bufs["cnt"], 4)
                got = int.from_bytes(raw, "little")
                found = []
                if got:
                    cnt_read = min(got, self.MAX_MATCHES)
                    data = self._download(bufs["matches"], 8 * cnt_read)
                    found = [int.from_bytes(data[i * 8:(i + 1) * 8], "little")
                             for i in range(cnt_read)]
                done += n
                yield found, done
        finally:
            for key in ("charset", "bstart", "bsize", "blen", "enc", "check", "cnt",
                        "matches"):
                self._free(bufs.get(key))

    def _launch(self, bufs, nb, base, base4, ntargets, start, count):
        d = _driver()
        vals = [
            ctypes.c_uint64(bufs["charset"]),
            ctypes.c_uint64(bufs["bstart"]),
            ctypes.c_uint64(bufs["bsize"]),
            ctypes.c_uint64(bufs["blen"]),
            ctypes.c_uint(nb),
            ctypes.c_uint(base),
            ctypes.c_uint(base4),
            ctypes.c_uint64(bufs["enc"]),
            ctypes.c_uint64(bufs["check"]),
            ctypes.c_uint(ntargets),
            ctypes.c_uint64(int(start)),
            ctypes.c_uint64(int(count)),
            ctypes.c_uint64(bufs["cnt"]),
            ctypes.c_uint64(bufs["matches"]),
            ctypes.c_uint(self.MAX_MATCHES),
        ]
        params = (ctypes.c_void_p * len(vals))(
            *[ctypes.c_void_p(ctypes.addressof(v)) for v in vals])
        grid = (int(count) + self.BLOCK - 1) // self.BLOCK
        _check(d["cuLaunchKernel"](self._func,
                                   ctypes.c_uint(grid), ctypes.c_uint(1), ctypes.c_uint(1),
                                   ctypes.c_uint(self.BLOCK), ctypes.c_uint(1),
                                   ctypes.c_uint(1),
                                   ctypes.c_uint(0), None, params, None),
               "cuLaunchKernel(grid=%d)" % grid)


def probe():
    """快速探测，不创建 context。"""
    return best_device()
