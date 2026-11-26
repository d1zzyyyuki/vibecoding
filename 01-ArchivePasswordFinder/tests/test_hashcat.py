# -*- coding: utf-8 -*-
"""hashcat GPU 路径测试：AES-ZIP / 7z 的哈希提取与自动破解。

需要先运行 tools/get_hashcat.py，否则相关用例自动跳过。
"""
import os
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import common  # noqa: E402
import core  # noqa: E402
import hashcat_gpu  # noqa: E402


def auto_search(archive, **kw):
    events, emit = common.collect_events()
    opts = {"archive": archive, "engine": "auto", "workers": core.default_workers()}
    opts.update(kw)
    res = core.run_auto_search(opts, emit, threading.Event())
    engines = [e.get("name", "") for e in events if e.get("type") == "engine"]
    return res, engines


def main():
    rep = common.Reporter()
    if not os.path.isfile(hashcat_gpu._pack_path()):
        print("没找到 hashcat 运行包，先运行 tools/get_hashcat.py；跳过")
        return rep.summary()
    if not hashcat_gpu.available():
        print("hashcat 不可用（%s）；跳过" % (hashcat_gpu.probe_error() or "未知"))
        return rep.summary()

    tmp = tempfile.mkdtemp(prefix="apf_hc_")
    files = {"a.txt": b"A" * 1200, "b.txt": b"B" * 2400, "c.txt": b"C" * 3600}

    # 1. AES-ZIP
    aes = common.make_archive(os.path.join(tmp, "aes.zip"), files, "739184",
                              zip_crypto=False)
    info = hashcat_gpu.zip_aes_hash(aes)
    rep.check("AES-ZIP 提取到 $zip2$ 哈希", bool(info and info["hash"].startswith("$zip2$")))
    res, engines = auto_search(aes)
    rep.check("AES-ZIP 找到密码", res.get("found") and res.get("password") == "739184",
              str(res.get("password")))
    rep.check("AES-ZIP 使用 GPU · hashcat", any("hashcat" in e for e in engines),
              str(engines))
    res, engines = auto_search(aes, attack="space", charset=core.DIGITS,
                               minlen=1, maxlen=6)
    rep.check("AES-ZIP 自定义字符集找到密码",
              res.get("found") and res.get("password") == "739184",
              str(res.get("password")))

    # 2. 7z
    seven = common.make_archive(os.path.join(tmp, "test.7z"), files, "7391", kind="7z")
    info = hashcat_gpu.sevenzip_hash(seven)
    rep.check("7z 提取到 $7z$ 哈希", bool(info and info["hash"].startswith("$7z$")))
    res, engines = auto_search(seven)
    rep.check("7z 找到密码", res.get("found") and res.get("password") == "7391",
              str(res.get("password")))
    rep.check("7z 使用 GPU · hashcat", any("hashcat" in e for e in engines),
              str(engines))

    return rep.summary()


if __name__ == "__main__":
    sys.exit(main())
