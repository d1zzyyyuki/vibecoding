# -*- coding: utf-8 -*-
"""OpenCL GPU 引擎：ZipCrypto 候选扫描（ctypes 直接调用 OpenCL.dll，无第三方依赖）。"""
import ctypes
import struct
import time

cl = ctypes.WinDLL("OpenCL.dll")

cl_platform_id = ctypes.c_void_p
cl_device_id = ctypes.c_void_p
cl_context = ctypes.c_void_p
cl_command_queue = ctypes.c_void_p
cl_program = ctypes.c_void_p
cl_kernel = ctypes.c_void_p
cl_mem = ctypes.c_void_p

CL_DEVICE_TYPE_ALL = 0xFFFFFFFF
CL_DEVICE_TYPE_GPU = 1 << 2
CL_DEVICE_NAME = 0x102B
CL_DEVICE_VENDOR = 0x102C
CL_DEVICE_VERSION = 0x102F
CL_DEVICE_MAX_COMPUTE_UNITS = 0x1002
CL_DEVICE_GLOBAL_MEM_SIZE = 0x101F
CL_DEVICE_MAX_WORK_GROUP_SIZE = 0x1004
CL_DEVICE_TYPE = 0x1000

CL_MEM_READ_ONLY = 1 << 0
CL_MEM_WRITE_ONLY = 1 << 1
CL_MEM_COPY_HOST_PTR = 1 << 5
CL_TRUE = 1
CL_SUCCESS = 0

_APIS = {
    "clGetPlatformIDs": [ctypes.c_uint, ctypes.POINTER(cl_platform_id), ctypes.POINTER(ctypes.c_uint)],
    "clGetDeviceIDs": [cl_platform_id, ctypes.c_ulonglong, ctypes.c_uint,
                       ctypes.POINTER(cl_device_id), ctypes.POINTER(ctypes.c_uint)],
    "clGetDeviceInfo": [cl_device_id, ctypes.c_uint, ctypes.c_size_t, ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t)],
    "clCreateContext": [ctypes.c_void_p, ctypes.c_uint, ctypes.POINTER(cl_device_id),
                        ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_int)],
    "clCreateCommandQueue": [cl_context, cl_device_id, ctypes.c_ulonglong, ctypes.POINTER(ctypes.c_int)],
    "clCreateProgramWithSource": [cl_context, ctypes.c_uint, ctypes.POINTER(ctypes.c_char_p),
                                  ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(ctypes.c_int)],
    "clBuildProgram": [cl_program, ctypes.c_uint, ctypes.POINTER(cl_device_id), ctypes.c_char_p,
                       ctypes.c_void_p, ctypes.c_void_p],
    "clGetProgramBuildInfo": [cl_program, cl_device_id, ctypes.c_uint, ctypes.c_size_t,
                              ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t)],
    "clCreateKernel": [cl_program, ctypes.c_char_p, ctypes.POINTER(ctypes.c_int)],
    "clCreateBuffer": [cl_context, ctypes.c_ulonglong, ctypes.c_size_t, ctypes.c_void_p, ctypes.POINTER(ctypes.c_int)],
    "clEnqueueWriteBuffer": [cl_command_queue, cl_mem, ctypes.c_uint, ctypes.c_size_t, ctypes.c_size_t,
                             ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p],
    "clSetKernelArg": [cl_kernel, ctypes.c_uint, ctypes.c_size_t, ctypes.c_void_p],
    "clEnqueueNDRangeKernel": [cl_command_queue, cl_kernel, ctypes.c_uint, ctypes.POINTER(ctypes.c_size_t),
                               ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(ctypes.c_size_t),
                               ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p],
    "clEnqueueReadBuffer": [cl_command_queue, cl_mem, ctypes.c_uint, ctypes.c_size_t, ctypes.c_size_t,
                            ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p],
    "clFinish": [cl_command_queue],
    "clReleaseMemObject": [cl_mem],
    "clReleaseKernel": [cl_kernel],
    "clReleaseProgram": [cl_program],
    "clReleaseCommandQueue": [cl_command_queue],
    "clReleaseContext": [cl_context],
}
for _name, _args in _APIS.items():
    _fn = getattr(cl, _name)
    _fn.argtypes = _args
    _fn.restype = ctypes.c_int
cl.clCreateContext.restype = cl_context
cl.clCreateCommandQueue.restype = cl_command_queue
cl.clCreateProgramWithSource.restype = cl_program
cl.clCreateKernel.restype = cl_kernel
cl.clCreateBuffer.restype = cl_mem


def error_string(code):
    try:
        fn = cl.clGetErrorString
        fn.argtypes = [ctypes.c_int]
        fn.restype = ctypes.c_char_p
        s = fn(code)
        return s.decode() if s else str(code)
    except Exception:
        return str(code)


_CRC_TABLE = []
for _n in range(256):
    _c = _n
    for _ in range(8):
        _c = (_c >> 1) ^ (0xEDB88320 if _c & 1 else 0)
    _CRC_TABLE.append(_c)

KERNEL_SRC = r"""
typedef unsigned char uchar;
typedef unsigned int uint;
typedef unsigned long ulong;

__constant uint CRCT[256] = { %TABLE% };

__kernel void zipcrack(
    __global const uchar* charset,
    __global const ulong* bucket_start,
    __global const ulong* bucket_size,
    __global const uchar* bucket_len,
    const uint nbuckets,
    const uint base,
    __global const uchar* prefix,
    const uint plen,
    __global const uchar* suffix,
    const uint slen,
    __global const uchar* enc,
    __global const uchar* check,
    const uint ntargets,
    const ulong start,
    const ulong count,
    __global uint* match_count,
    __global ulong* matches,
    const uint max_matches)
{
    ulong gid = (ulong)get_global_id(0);
    if (gid >= count) return;
    ulong idx = start + gid;

    uint L = 0;
    ulong off = 0;
    for (uint i = 0; i < nbuckets; i++) {
        if (idx < bucket_start[i] + bucket_size[i]) {
            L = (uint)bucket_len[i];
            off = idx - bucket_start[i];
            break;
        }
    }

    uchar pw[48];
    uint pos = 0;
    for (uint i = 0; i < plen; i++) pw[pos++] = prefix[i];
    for (uint k = 0; k < L; k++) {
        pw[pos + L - 1 - k] = charset[off % base];
        off /= base;
    }
    pos += L;
    for (uint i = 0; i < slen; i++) pw[pos++] = suffix[i];

    uint k0 = 0x12345678u, k1 = 0x23456789u, k2 = 0x34567890u;
    for (uint i = 0; i < pos; i++) {
        uchar b = pw[i];
        k0 = CRCT[(k0 ^ b) & 0xFF] ^ (k0 >> 8);
        k1 = (k1 + (k0 & 0xFF)) * 134775813u + 1u;
        k2 = CRCT[(k2 ^ (k1 >> 24)) & 0xFF] ^ (k2 >> 8);
    }

    for (uint t = 0; t < ntargets; t++) {
        uint a0 = k0, a1 = k1, a2 = k2;
        uchar last = 0;
        for (uint i = 0; i < 12; i++) {
            uint tt = (a2 | 2) & 0xFFFF;
            uchar p = enc[t * 12 + i] ^ (uchar)(((tt * (tt ^ 1)) >> 8) & 0xFF);
            if (i == 11) { last = p; break; }
            a0 = CRCT[(a0 ^ p) & 0xFF] ^ (a0 >> 8);
            a1 = (a1 + (a0 & 0xFF)) * 134775813u + 1u;
            a2 = CRCT[(a2 ^ (a1 >> 24)) & 0xFF] ^ (a2 >> 8);
        }
        if (last != check[t]) return;
    }
    uint slot = atomic_inc(match_count);
    if (slot < max_matches) matches[slot] = idx;
}
"""


def _dev_info(device, param, typ):
    size = ctypes.c_size_t()
    cl.clGetDeviceInfo(device, param, 0, None, ctypes.byref(size))
    buf = (ctypes.c_char * size.value)()
    cl.clGetDeviceInfo(device, param, size, buf, ctypes.byref(size))
    if typ is str:
        return buf.value.decode("utf-8", "replace").strip("\x00")
    return typ.from_buffer_copy(buf).value


def enum_devices():
    out = []
    try:
        n = ctypes.c_uint()
        if cl.clGetPlatformIDs(0, None, ctypes.byref(n)) != CL_SUCCESS or n.value == 0:
            return out
        plats = (cl_platform_id * n.value)()
        cl.clGetPlatformIDs(n, plats, None)
        for i in range(n.value):
            p = plats[i]
            nd = ctypes.c_uint()
            if cl.clGetDeviceIDs(p, CL_DEVICE_TYPE_ALL, 0, None, ctypes.byref(nd)) != CL_SUCCESS:
                continue
            devs = (cl_device_id * nd.value)()
            cl.clGetDeviceIDs(p, CL_DEVICE_TYPE_ALL, nd.value, devs, None)
            for j in range(nd.value):
                d = devs[j]
                out.append({
                    "platform": p, "device": d,
                    "name": _dev_info(d, CL_DEVICE_NAME, str),
                    "vendor": _dev_info(d, CL_DEVICE_VENDOR, str),
                    "version": _dev_info(d, CL_DEVICE_VERSION, str),
                    "type": _dev_info(d, CL_DEVICE_TYPE, ctypes.c_ulonglong),
                    "cus": _dev_info(d, CL_DEVICE_MAX_COMPUTE_UNITS, ctypes.c_uint),
                    "max_wg": _dev_info(d, CL_DEVICE_MAX_WORK_GROUP_SIZE, ctypes.c_size_t),
                    "mem": _dev_info(d, CL_DEVICE_GLOBAL_MEM_SIZE, ctypes.c_ulonglong),
                })
    except Exception:
        return []
    return out


def best_gpu():
    gpus = [d for d in enum_devices() if d["type"] & CL_DEVICE_TYPE_GPU]
    if not gpus:
        return None

    def score(d):
        vendor = (d.get("vendor") or "").lower()
        if "nvidia" in vendor:
            tier = 3
        elif "amd" in vendor or "advanced micro" in vendor:
            tier = 2
        elif "intel" in vendor:
            tier = 0
        else:
            tier = 1
        return (tier, d["mem"])

    # 优先独显（NVIDIA / AMD），避免默认选中 Intel 核显
    return max(gpus, key=score)


class _Buffer:
    def __init__(self, ctx, data, flags=CL_MEM_READ_ONLY | CL_MEM_COPY_HOST_PTR):
        err = ctypes.c_int()
        raw = bytes(data) if isinstance(data, (bytes, bytearray)) else data
        if flags & CL_MEM_COPY_HOST_PTR:
            host = ctypes.cast(ctypes.c_char_p(raw), ctypes.c_void_p) if raw else None
        else:
            host = None
        self.handle = ctypes.c_void_p(cl.clCreateBuffer(ctx, flags, max(1, len(raw)), host,
                                                        ctypes.byref(err)))
        if err.value != CL_SUCCESS:
            raise RuntimeError("clCreateBuffer: " + error_string(err.value))


class GPUZipCracker:
    """ZipCrypto 的 GPU 扫描器：一次 dispatch 处理一个 chunk，收集候选。"""

    CHUNK = 4_000_000
    MAX_MATCHES = 1024

    def __init__(self):
        dev = best_gpu()
        if dev is None:
            raise RuntimeError("没有可用的 OpenCL GPU")
        self.dev = dev
        self.build_ms = 0
        err = ctypes.c_int()
        devs = (cl_device_id * 1)()
        devs[0] = dev["device"]
        self.ctx = cl.clCreateContext(None, 1, devs, None, None, ctypes.byref(err))
        if err.value != CL_SUCCESS:
            raise RuntimeError("clCreateContext: " + error_string(err.value))
        self.queue = cl.clCreateCommandQueue(self.ctx, dev["device"], 0, ctypes.byref(err))
        if err.value != CL_SUCCESS:
            raise RuntimeError("clCreateCommandQueue: " + error_string(err.value))
        src = KERNEL_SRC.replace("%TABLE%", ",".join(str(x) for x in _CRC_TABLE)).encode()
        csrc = ctypes.c_char_p(src)
        csz = ctypes.c_size_t(len(src))
        t0 = time.time()
        self.prog = cl.clCreateProgramWithSource(self.ctx, 1, ctypes.byref(csrc), ctypes.byref(csz),
                                                 ctypes.byref(err))
        if err.value != CL_SUCCESS:
            raise RuntimeError("clCreateProgramWithSource: " + error_string(err.value))
        r = cl.clBuildProgram(self.prog, 0, None, b"-cl-mad-enable", None, None)
        if r != CL_SUCCESS:
            size = ctypes.c_size_t()
            cl.clGetProgramBuildInfo(self.prog, dev["device"], 0x1183, 0, None, ctypes.byref(size))
            log = (ctypes.c_char * size.value)()
            cl.clGetProgramBuildInfo(self.prog, dev["device"], 0x1183, size, log, ctypes.byref(size))
            raise RuntimeError("GPU 内核编译失败：\n" + log.value.decode("utf-8", "replace"))
        self.kernel = cl.clCreateKernel(self.prog, b"zipcrack", ctypes.byref(err))
        if err.value != CL_SUCCESS:
            raise RuntimeError("clCreateKernel: " + error_string(err.value))
        self.build_ms = (time.time() - t0) * 1000

    def _chunk_size(self, ntargets):
        if ntargets >= 3:
            return 4_000_000
        if ntargets == 2:
            return 1_000_000
        return 65_536

    def iter_chunks(self, space, targets, total, start=0, stop=None):
        """生成 (matches, done) —— done 为已扫描到的候选序号（绝对）。"""
        charset = space.charset.encode("latin-1")
        pfx = space.prefix.encode("latin-1")
        sfx = space.suffix.encode("latin-1")
        buckets = space.buckets
        nb = len(buckets)
        bufs = {}
        # 预先创建所有只读 buffer（保持引用直到结束）
        bufs["charset"] = _Buffer(self.ctx, charset)
        bufs["bstart"] = _Buffer(self.ctx, struct.pack("<%dQ" % nb, *[b[1] for b in buckets]))
        bufs["bsize"] = _Buffer(self.ctx, struct.pack("<%dQ" % nb, *[b[2] for b in buckets]))
        bufs["blen"] = _Buffer(self.ctx, bytes(b[0] for b in buckets))
        bufs["prefix"] = _Buffer(self.ctx, pfx or b"\x00")
        bufs["suffix"] = _Buffer(self.ctx, sfx or b"\x00")
        bufs["enc"] = _Buffer(self.ctx, b"".join(bytes(t[0]) for t in targets))
        bufs["check"] = _Buffer(self.ctx, bytes(t[1] for t in targets))
        cnt = _Buffer(self.ctx, struct.pack("<I", 0))
        matches = _Buffer(self.ctx, b"\x00" * (8 * self.MAX_MATCHES), flags=CL_MEM_WRITE_ONLY)
        ntargets = len(targets)
        chunk = self._chunk_size(ntargets)
        bufs["_cnt"] = cnt
        bufs["_matches"] = matches
        bufs["_meta"] = (space, ntargets, chunk)

        def setarg(i, ptr, size):
            r = cl.clSetKernelArg(self.kernel, i, size, ctypes.byref(ptr))
            if r != CL_SUCCESS:
                raise RuntimeError("clSetKernelArg %d: %s" % (i, error_string(r)))

        setarg(0, bufs["charset"].handle, 8)
        setarg(1, bufs["bstart"].handle, 8)
        setarg(2, bufs["bsize"].handle, 8)
        setarg(3, bufs["blen"].handle, 8)
        setarg(4, ctypes.c_uint(nb), 4)
        setarg(5, ctypes.c_uint(space.base), 4)
        setarg(6, bufs["prefix"].handle, 8)
        setarg(7, ctypes.c_uint(len(pfx)), 4)
        setarg(8, bufs["suffix"].handle, 8)
        setarg(9, ctypes.c_uint(len(sfx)), 4)
        setarg(10, bufs["enc"].handle, 8)
        setarg(11, bufs["check"].handle, 8)
        setarg(12, ctypes.c_uint(ntargets), 4)
        setarg(17, ctypes.c_uint(self.MAX_MATCHES), 4)
        done = max(0, start)
        while done < total:
            if stop is not None and stop.is_set():
                return
            n = min(chunk, total - done)
            zero = b"\x00\x00\x00\x00"
            cl.clEnqueueWriteBuffer(self.queue, cnt.handle, CL_TRUE, 0, 4,
                                    ctypes.cast(ctypes.c_char_p(zero), ctypes.c_void_p), 0, None, None)
            setarg(13, ctypes.c_ulonglong(done), 8)
            setarg(14, ctypes.c_ulonglong(n), 8)
            setarg(15, cnt.handle, 8)
            setarg(16, matches.handle, 8)
            gsize = ctypes.c_size_t(((n + 255) // 256) * 256)
            lsize = ctypes.c_size_t(256)
            r = cl.clEnqueueNDRangeKernel(self.queue, self.kernel, 1, None, ctypes.byref(gsize),
                                          ctypes.byref(lsize), 0, None, None)
            if r != CL_SUCCESS:
                raise RuntimeError("clEnqueueNDRangeKernel: " + error_string(r))
            cl.clFinish(self.queue)
            got = ctypes.c_uint()
            cl.clEnqueueReadBuffer(self.queue, cnt.handle, CL_TRUE, 0, 4, ctypes.byref(got), 0, None, None)
            found = []
            if got.value:
                cnt_read = min(got.value, self.MAX_MATCHES)
                arr = (ctypes.c_ulonglong * cnt_read)()
                cl.clEnqueueReadBuffer(self.queue, matches.handle, CL_TRUE, 0, 8 * cnt_read,
                                       arr, 0, None, None)
                found = [int(v) for v in arr]
            done += n
            yield found, done
