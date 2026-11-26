# -*- coding: utf-8 -*-
"""测试公用工具：路径、临时压缩包、消息收集。"""
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

SEVENZIP = os.path.join(ROOT, "assets", "7z.exe")


def make_archive(out_path, files, password="", kind="zip", zip_crypto=True):
    """用仓库自带的 7z.exe 造一个测试压缩包。files: {相对路径: bytes}。"""
    out_path = os.path.abspath(out_path)
    tmp = tempfile.mkdtemp(prefix="apf_")
    for name, data in files.items():
        p = os.path.join(tmp, name)
        d = os.path.dirname(p)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(p, "wb") as f:
            f.write(data)
    args = [SEVENZIP, "a", "-t" + kind, "-y", out_path]
    if password:
        args.append("-p" + password)
    if kind == "zip":
        args.append("-mem=ZipCrypto" if zip_crypto else "-mem=AES256")
    args.extend(files.keys())
    subprocess.run(args, cwd=tmp, check=True, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)
    return out_path


def make_plain_tar(out_path):
    import io
    import tarfile

    buf = io.BytesIO(b"hello archive\n" * 100)
    with tarfile.open(out_path, "w") as tf:
        info = tarfile.TarInfo("hello.txt")
        info.size = len(buf.getvalue())
        tf.addfile(info, buf)
    return out_path


def collect_events():
    events = []

    def emit(msg):
        events.append(msg)

    return events, emit


class Reporter:
    def __init__(self):
        self.passed = 0
        self.failed = 0

    def check(self, name, cond, detail=""):
        if cond:
            self.passed += 1
            print("  PASS  %s %s" % (name, detail))
        else:
            self.failed += 1
            print("  FAIL  %s %s" % (name, detail))
        return bool(cond)

    def summary(self):
        print("\n==== %d passed, %d failed ====" % (self.passed, self.failed))
        return 0 if self.failed == 0 else 1
