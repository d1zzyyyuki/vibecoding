# -*- coding: utf-8 -*-
"""冒烟测试：造几个压缩包，跑一遍自动破解流程。"""
import os
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import common  # noqa: E402
import core  # noqa: E402


def auto_search(archive, engine="auto", stop=None):
    events, emit = common.collect_events()
    opts = {"archive": archive, "engine": engine, "workers": core.default_workers()}
    res = core.run_auto_search(opts, emit, stop or threading.Event())
    engines = [e.get("name") for e in events if e.get("type") == "engine"]
    return res, events, engines


def main():
    rep = common.Reporter()
    tmp = tempfile.mkdtemp(prefix="apf_smoke_")

    # 1. 3 文件 ZipCrypto，密码在字典里
    multi = common.make_archive(os.path.join(tmp, "multi.zip"),
                                {"a.txt": b"a" * 4096, "b.txt": b"b" * 8192,
                                 "c.txt": b"c" * 16384}, "123456")
    res, _, engines = auto_search(multi)
    rep.check("3 文件 ZIP 找到密码", res.get("found") and res.get("password") == "123456",
              "engines=%s" % engines)

    # 2. 单文件 ZIP 自动走 CPU
    single = common.make_archive(os.path.join(tmp, "single.zip"),
                                 {"only.txt": b"x" * 8192}, "123456")
    res, _, engines = auto_search(single)
    rep.check("单文件 ZIP 找到密码", res.get("found") and res.get("password") == "123456")
    rep.check("单文件 ZIP 使用 CPU 引擎", any("CPU" in e for e in engines), str(engines))

    # 3. 7z 加密包走 7-Zip 引擎
    seven = common.make_archive(os.path.join(tmp, "test.7z"),
                                {"data.txt": b"z" * 4096}, "123456", kind="7z")
    res, _, engines = auto_search(seven)
    rep.check("7z 加密包找到密码", res.get("found") and res.get("password") == "123456")
    rep.check("7z 使用 GPU 或 7-Zip 引擎",
              any(("7-Zip" in e) or ("hashcat" in e) for e in engines), str(engines))

    # 4. 未加密 tar
    plain = common.make_plain_tar(os.path.join(tmp, "plain.tar"))
    res, _, _ = auto_search(plain)
    rep.check("未加密 tar 正确提示", res.get("reason") == "not_encrypted", res.get("reason"))

    # 5. 不是压缩包
    junk = os.path.join(tmp, "junk.bin")
    with open(junk, "wb") as f:
        f.write(os.urandom(4096))
    try:
        auto_search(junk)
        rep.check("非压缩包报错", False)
    except Exception as e:
        rep.check("非压缩包报错", True, type(e).__name__)

    # 6. 中途停止
    stop = threading.Event()
    slow = common.make_archive(os.path.join(tmp, "slow.zip"),
                               {"a.bin": b"a" * 1000, "b.bin": b"b" * 1000,
                                "c.bin": b"c" * 1000}, "zzq7x9")
    timer = threading.Timer(0.4, stop.set)
    timer.start()
    t0 = time.time()
    res, _, _ = auto_search(slow, stop=stop)
    timer.cancel()
    rep.check("运行中停止", res.get("reason") == "stopped",
              "reason=%s elapsed=%.2fs" % (res.get("reason"), time.time() - t0))

    # 7. 启动自检
    selftest = core.quick_backend_check()
    rep.check("启动自检有结论", "backend" in selftest and selftest.get("ok") is not None,
              "backend=%s" % selftest.get("backend"))

    return rep.summary()


if __name__ == "__main__":
    sys.exit(main())
