# -*- coding: utf-8 -*-
"""CUDA 后端测试：PTX 资源、选型、内核索引映射、假驱动全链路。

本机没有 N 卡也能跑——PTX 相关的用例不需要显卡；模拟驱动部分会尝试用 gcc
编译 tools/mock_nvcuda.c，没有 gcc 就自动跳过。
"""
import os
import shutil
import subprocess
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import common  # noqa: E402

# 有模拟驱动就设好环境变量，cuda.py 在导入时才读它
MOCK_DLL = os.path.join(common.ROOT, "tools", "mock", "nvcuda.dll")
MOCK_SRC = os.path.join(common.ROOT, "tools", "mock_nvcuda.c")
if not os.path.isfile(MOCK_DLL) and os.path.isfile(MOCK_SRC):
    gcc = shutil.which("gcc")
    if gcc:
        os.makedirs(os.path.dirname(MOCK_DLL), exist_ok=True)
        subprocess.run([gcc, "-shared", "-O2", "-o", MOCK_DLL, MOCK_SRC],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
HAS_MOCK = os.path.isfile(MOCK_DLL)
if HAS_MOCK:
    os.environ["PCA_CUDA_DLL"] = MOCK_DLL

import core  # noqa: E402
import cuda  # noqa: E402


def pick(cc, driver):
    return cuda._ptx_candidates({"cc": cc, "driver": driver})


def kernel_decode(space, idx):
    """按 zipcuda.cu 的算法复刻：桶定位 → base^4 拆分 → 寄存器打包。"""
    length = 0
    off = 0
    for bl, boff, bcnt in space.buckets[:8]:
        if idx < boff + bcnt:
            length = bl
            off = idx - boff
            break
    if length == 0 or length > 8:
        return None

    base = space.base
    base4 = base ** 4
    o = off
    q, r = divmod(o, base4)
    q &= 0xFFFFFFFF

    lo = hi = 0
    pos = length - 1

    def put(ch):
        nonlocal lo, hi, pos
        if pos < 8:
            if pos >= 4:
                hi |= ch << (8 * (pos - 4))
            else:
                lo |= ch << (8 * pos)
        pos -= 1

    for k in range(4):
        if k < length:
            put(ord(space.charset[r % base]))
            r //= base
    for k in range(4, 8):
        if k < length:
            put(ord(space.charset[q % base]))
            q //= base

    out = []
    for i in range(length):
        byte = (lo >> (8 * i)) & 0xFF if i < 4 else (hi >> (8 * (i - 4))) & 0xFF
        out.append(chr(byte))
    return space.prefix + "".join(out) + space.suffix


def test_ptx_assets(rep):
    print("[1] PTX 资源")
    blobs = cuda.ptx_blobs()
    rep.check("PTX 文件存在", len(blobs) >= 20, "count=%d" % len(blobs))
    archs = sorted({b["arch"] for b in blobs})
    isas = sorted({b["isa"] for b in blobs})
    rep.check("覆盖 sm_20", 20 in archs, str(archs))
    rep.check("覆盖 sm_86", 86 in archs)
    rep.check("覆盖 sm_120", 120 in archs)
    rep.check("包含老 ISA", any(i[0] == 5 for i in isas), str(isas))
    rep.check("包含新 ISA", any(i[0] == 8 for i in isas))
    for b in blobs:
        with open(b["path"], "rb") as f:
            text = f.read().decode("utf-8", "replace")
        if ".entry zipcrack" not in text:
            rep.check("PTX 内容完整", False, b["name"])
            return
    rep.check("PTX 内容完整", True)


def test_selection(rep):
    print("[2] PTX 选型")
    c = pick(20, 9010)
    rep.check("Fermi → sm_20/ISA5", bool(c) and c[0]["arch"] == 20 and c[0]["isa"][0] == 5,
              str(c[0] if c else None))
    c = pick(35, 11040)
    rep.check("Kepler → ISA5 或 7.x", bool(c) and c[0]["arch"] <= 35 and c[0]["isa"] <= (7, 4),
              str(c[0] if c else None))
    c = pick(86, 12090)
    rep.check("3090 → sm_86/ISA8", bool(c) and c[0]["arch"] == 86 and c[0]["isa"][0] == 8,
              str(c[0] if c else None))
    c = pick(86, 11080)
    rep.check("旧驱动 → ISA7.8", bool(c) and c[0]["isa"] <= (7, 8), str(c[0] if c else None))
    c = pick(120, 12090)
    rep.check("5090 → sm_120", bool(c) and c[0]["arch"] == 120, str(c[0] if c else None))
    c = pick(70, 11080)
    rep.check("V100 → sm_70", bool(c) and c[0]["arch"] == 70, str(c[0] if c else None))
    c = pick(20, 9010)
    rep.check("兜底顺序按 ISA 升序", [b["isa"] for b in c] == sorted(b["isa"] for b in c))


def test_kernel_decode(rep):
    print("[3] 内核索引映射")
    cases = [(core.DIGITS, 1, 8), (core.LOWER, 1, 6),
             (core.LOWER + core.DIGITS, 1, 6), (core.PRINTABLE, 1, 5),
             (core.DIGITS, 8, 8)]
    bad = 0
    for charset, mn, mx in cases:
        sp = core.Space(charset, mn, mx)
        for idx in [0, 1, 2, 17, 255, 256, 4095, sp.total // 3, sp.total // 2,
                    sp.total - 1, 4294967295 % sp.total, 4294967296 % sp.total]:
            idx = min(idx, sp.total - 1)
            if kernel_decode(sp, idx) != sp.decode(idx):
                bad += 1
    rep.check("映射与 Space.decode 一致", bad == 0, "bad=%d" % bad)

    sp = core.Space(core.PRINTABLE, 5, 5)
    for idx in [0, 4294967295, 4294967296, 4294967297, 5_000_000_000, sp.total - 1]:
        if idx < sp.total and kernel_decode(sp, idx) != sp.decode(idx):
            bad += 1
    rep.check("超过 2^32 的大桶一致", bad == 0)


def test_mock_chain(rep):
    print("[4] 假驱动全链路")
    dev = cuda.best_device()
    if not rep.check("模拟设备可见", dev is not None, str(dev and dev.get("name"))):
        return
    engine = cuda.CudaZipCracker(dev)
    try:
        rep.check("PTX 加载成功", bool(engine.ptx_name), engine.ptx_name)
        sp = core.Space(core.DIGITS, 6, 6)
        total = sp.total
        idx = total - 1
        pw = sp.decode(idx).encode("latin-1")
        targets = core.make_selftest_targets(pw, 3)
        matches = []
        for chunk, _done in engine.iter_chunks(sp, targets, total):
            matches.extend(int(x) for x in chunk)
        rep.check("扫描命中指定候选", idx in matches, "matches=%d" % len(matches))

        small = core.Space(core.LOWER, 3, 3)
        targets = core.make_selftest_targets(small.decode(small.total - 1).encode(), 3)
        matches = []
        for chunk, _done in engine.iter_chunks(small, targets, small.total + 7):
            matches.extend(int(x) for x in chunk)
        rep.check("非整块边界正常", (small.total - 1) in matches)
    finally:
        engine.close()


def test_real_search(rep, tmp):
    print("[5] 真实压缩包走 CUDA 路径")
    archive = common.make_archive(os.path.join(tmp, "cuda.zip"),
                                  {"a.txt": b"a" * 2048, "b.txt": b"b" * 4096,
                                   "c.txt": b"c" * 6144}, "739184")
    events, emit = common.collect_events()
    opts = {"archive": archive, "mode": "space", "charset": core.DIGITS,
            "minlen": 6, "maxlen": 6, "engine": "gpu",
            "workers": core.default_workers()}
    res = core.run_search(opts, emit, threading.Event())
    rep.check("找到密码", res.get("found") and res.get("password") == "739184",
              str(res.get("password")))
    engines = [e.get("name", "") for e in events if e.get("type") == "engine"]
    rep.check("引擎为 GPU · CUDA", any("CUDA" in e for e in engines), str(engines))


def test_selftest_consistency(rep):
    print("[6] 自检与后端选择一致")
    res = core.quick_backend_check()
    backend = core.gpu_backend()
    kind = backend.kind if backend is not None else "cpu"
    ok = res.get("backend") == kind or (res.get("backend") == "cpu" and backend is None)
    rep.check("自检结论 == gpu_backend()", ok,
              "selftest=%s backend=%s" % (res.get("backend"), kind))


def main():
    rep = common.Reporter()
    tmp = tempfile.mkdtemp(prefix="apf_cuda_")
    print("模拟驱动:", MOCK_DLL if HAS_MOCK else "(未启用，跳过相关用例)")
    test_ptx_assets(rep)
    test_selection(rep)
    test_kernel_decode(rep)
    if HAS_MOCK:
        test_mock_chain(rep)
        test_real_search(rep, tmp)
    test_selftest_consistency(rep)
    return rep.summary()


if __name__ == "__main__":
    sys.exit(main())
