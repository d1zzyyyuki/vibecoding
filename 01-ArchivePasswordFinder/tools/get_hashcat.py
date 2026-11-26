# -*- coding: utf-8 -*-
"""下载 hashcat 运行包和 7z2hashcat（构建 exe 前运行一次）。

运行时这部分是可选的：文件缺失时程序自动跳过 GPU hashcat 路径。
"""
import hashlib
import os
import sys
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets", "hashcat")

HASHCAT_NAME = "hashcat-8.0.0.7z"
HASHCAT_URL = "https://hashcat.net/files/hashcat-8.0.0.7z"
HASHCAT_SHA256 = "9fa86e1bfd5dd898d3c83aa38a67b08db1ba5d2f5252dffa2af44a8c62585f49"

Z2H_NAME = "7z2hashcat64-2.0.exe"
Z2H_URL = "https://github.com/philsmd/7z2hashcat/releases/download/2.0/7z2hashcat64-2.0.zip"
Z2H_SHA256 = "dc9261eaad1a58971236682d309b3d79bdc784ce48edd0557b2a66575679c345"


def download(url, path):
    print("下载", url)
    with urllib.request.urlopen(url, timeout=300) as r, open(path, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if total:
                print("\r  %d%%" % (done * 100 // total), end="", flush=True)
    print()


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    os.makedirs(OUT, exist_ok=True)
    pack = os.path.join(OUT, HASHCAT_NAME)
    if os.path.isfile(pack) and sha256(pack) == HASHCAT_SHA256:
        print("已存在:", pack)
    else:
        download(HASHCAT_URL, pack)
        if sha256(pack) != HASHCAT_SHA256:
            sys.exit("hashcat 包校验失败")

    tool = os.path.join(OUT, Z2H_NAME)
    if os.path.isfile(tool) and sha256(tool) == Z2H_SHA256:
        print("已存在:", tool)
    else:
        tmp = os.path.join(OUT, "7z2hashcat.zip")
        download(Z2H_URL, tmp)
        with zipfile.ZipFile(tmp) as z:
            names = [n for n in z.namelist() if n.lower().endswith(".exe")]
            if not names:
                sys.exit("压缩包里没找到 exe")
            with z.open(names[0]) as src, open(tool, "wb") as dst:
                dst.write(src.read())
        os.remove(tmp)
        if sha256(tool) != Z2H_SHA256:
            sys.exit("7z2hashcat 校验失败")

    print("完成:", OUT)


if __name__ == "__main__":
    main()
