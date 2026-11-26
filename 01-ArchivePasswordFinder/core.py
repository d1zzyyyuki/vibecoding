# -*- coding: utf-8 -*-
"""压缩包密码找回 —— 核心引擎（CPU / CUDA / OpenCL / 7-Zip）与硬件监控。"""
import ctypes
import os
import struct
import subprocess
import sys
import threading
import time
import zipfile
import zlib

try:
    import psutil
except Exception:  # pragma: no cover
    psutil = None

APP_NAME = "压缩包密码找回"
APP_NAME_ZH = "压缩包密码找回"
APP_NAME_EN = "ArchivePasswordFinder"
VERSION = "1.0.1"

IS_FROZEN = bool(getattr(sys, "frozen", False))
IS_WINDOWS = os.name == "nt"
BASE_DIR = (
    getattr(sys, "_MEIPASS", None)
    or os.path.dirname(os.path.abspath(sys.executable if IS_FROZEN else __file__))
)
if not IS_FROZEN:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
DEVNULL = subprocess.DEVNULL


def asset_path(*parts):
    p = os.path.join(ASSETS_DIR, *parts)
    if os.path.exists(p):
        return p
    p2 = os.path.join(BASE_DIR, *parts)
    return p2 if os.path.exists(p2) else p


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------
def default_workers():
    try:
        cpu = os.cpu_count() or 4
    except Exception:
        cpu = 4
    return max(1, min(32, cpu))


def kill_child_processes():
    """关窗时清掉仍在跑的 7z / hashcat，避免线程被它们拖住。"""
    try:
        import psutil
        me = psutil.Process()
    except Exception:
        return
    victims = []
    for ch in me.children(recursive=True):
        try:
            if ch.name().lower() in ("7z.exe", "7zg.exe", "hashcat.exe"):
                victims.append(ch)
        except Exception:
            pass
    for ch in victims:
        try:
            ch.kill()
        except Exception:
            pass
    try:
        psutil.wait_procs(victims, timeout=2)
    except Exception:
        pass


def fmt_num(n):
    try:
        return format(int(n), ",")
    except Exception:
        return str(n)


def fmt_rate(rate):
    if not rate or rate <= 0:
        return "--"
    if rate >= 1e8:
        return "%.1f 亿次/秒" % (rate / 1e8)
    if rate >= 1e4:
        return "%.1f 万次/秒" % (rate / 1e4)
    return "%s 次/秒" % format(int(rate), ",")


def fmt_eta(seconds):
    if seconds is None or seconds < 0:
        return "--"
    seconds = int(seconds)
    if seconds < 60:
        return "%d 秒" % seconds
    if seconds < 3600:
        return "%d 分 %d 秒" % (seconds // 60, seconds % 60)
    if seconds < 86400:
        return "%d 小时 %d 分" % (seconds // 3600, (seconds % 3600) // 60)
    return "%d 天" % (seconds // 86400)


def fmt_bytes(n):
    try:
        n = float(n)
    except Exception:
        return "--"
    for unit in ("B", "K", "M", "G", "T"):
        if abs(n) < 1024.0 or unit == "T":
            return ("%.1f%s" % (n, unit)) if unit != "B" else ("%d%s" % (n, unit))
        n /= 1024.0
    return "--"


def _import_cuda():
    """延迟导入 CUDA 引擎。"""
    try:
        import cuda
        return cuda
    except Exception:
        return None


# ---------------------------------------------------------------------------
# ZipCrypto 辅助：自检用的假加密头 / CRC 表
# ---------------------------------------------------------------------------
_CRC_TABLE = None


def crc_table():
    global _CRC_TABLE
    if _CRC_TABLE is None:
        t = []
        for n in range(256):
            c = n
            for _ in range(8):
                c = (c >> 1) ^ (0xEDB88320 if c & 1 else 0)
            t.append(c)
        _CRC_TABLE = t
    return _CRC_TABLE


def make_selftest_targets(pw, count=3):
    """按 ZipCrypto 规则造 count 个假加密头，返回 [(enc12, check_byte), ...]。"""
    tbl = crc_table()
    targets = []
    pw = bytes(pw)
    for t in range(max(1, int(count))):
        plain = bytearray(((t * 37 + i * 11 + 7) & 0xFF) for i in range(12))
        k0, k1, k2 = 0x12345678, 0x23456789, 0x34567890
        for b in pw:
            k0 = tbl[(k0 ^ b) & 0xFF] ^ (k0 >> 8)
            k1 = ((k1 + (k0 & 0xFF)) * 134775813 + 1) & 0xFFFFFFFF
            k2 = tbl[(k2 ^ (k1 >> 24)) & 0xFF] ^ (k2 >> 8)
        enc = bytearray(12)
        for i, p in enumerate(plain):
            tt = (k2 | 2) & 0xFFFF
            enc[i] = p ^ (((tt * (tt ^ 1)) >> 8) & 0xFF)
            k0 = tbl[(k0 ^ p) & 0xFF] ^ (k0 >> 8)
            k1 = ((k1 + (k0 & 0xFF)) * 134775813 + 1) & 0xFFFFFFFF
            k2 = tbl[(k2 ^ (k1 >> 24)) & 0xFF] ^ (k2 >> 8)
        targets.append((bytes(enc), plain[11]))
    return targets


def detect_kind(path):
    try:
        with open(path, "rb") as f:
            head = f.read(16)
    except OSError:
        return None
    if head.startswith(b"Rar!\x1a\x07\x01\x00") or head.startswith(b"Rar!\x1a\x07\x00"):
        return "rar"
    if head.startswith(b"7z\xbc\xaf\x27\x1c"):
        return "7z"
    if head.startswith(b"PK\x03\x04") or head.startswith(b"PK\x05\x06"):
        return "zip"
    ext = os.path.splitext(path)[1].lower()
    return {".zip": "zip", ".rar": "rar", ".7z": "7z"}.get(ext)


KIND_NAMES = {"zip": "ZIP", "rar": "RAR", "7z": "7Z", "other": "压缩包"}


# ---------------------------------------------------------------------------
# 候选空间
# ---------------------------------------------------------------------------
class Space:
    def __init__(self, charset, min_len, max_len, prefix="", suffix=""):
        seen = set()
        chars = []
        for c in charset:
            if c not in seen:
                seen.add(c)
                chars.append(c)
        self.charset = "".join(chars)
        self.base = len(self.charset)
        if self.base <= 0:
            raise ValueError("字符集不能为空")
        if min_len < 1 or max_len < min_len:
            raise ValueError("长度范围无效")
        self.min_len = min_len
        self.max_len = max_len
        self.prefix = prefix or ""
        self.suffix = suffix or ""
        if len(self.prefix) + max_len + len(self.suffix) > 64:
            raise ValueError("密码长度超过 64 个字符（引擎上限）")
        self.buckets = []
        off = 0
        for L in range(min_len, max_len + 1):
            cnt = self.base ** L
            self.buckets.append((L, off, cnt))
            off += cnt
            if off > (1 << 63) - 1:
                raise ValueError("候选空间太大，请缩短长度或字符集")
        self.total = off

    def decode(self, idx):
        base = self.base
        for L, off, cnt in self.buckets:
            if idx < off + cnt:
                n = idx - off
                out = [""] * L
                for pos in range(L - 1, -1, -1):
                    out[pos] = self.charset[n % base]
                    n //= base
                return self.prefix + "".join(out) + self.suffix
        raise IndexError(idx)

    def iterate(self):
        for i in range(self.total):
            yield self.decode(i)

    @property
    def ascii_ok(self):
        return (self.prefix.isascii() and self.suffix.isascii() and self.charset.isascii())


def load_wordlist(path):
    with open(path, "rb") as f:
        raw = f.read()
    text = None
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        for enc in ("utf-16", "utf-16-le", "utf-16-be"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
    if text is None:
        for enc in ("utf-8-sig", "utf-8", "gbk", "latin-1"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
    if text is None:
        text = raw.decode("utf-8", "replace")
    words = []
    seen = set()
    for line in text.splitlines():
        w = line.strip()
        if w and w not in seen:
            seen.add(w)
            words.append(w)
    return words


def build_words_blob(words):
    """把（已加前后缀的）字典转成 C 引擎使用的 UTF-8 字节池。"""
    blob = bytearray()
    offsets = [0]
    for w in words:
        b = w.encode("utf-8")
        blob.extend(b)
        offsets.append(len(blob))
    return bytes(blob), offsets


# ---------------------------------------------------------------------------
# ZIP 解析：加密头 + 用于完整验证的最小文件
# ---------------------------------------------------------------------------
class ZipPlan:
    def __init__(self):
        self.targets = []       # [(enc12, check_byte)]
        self.verify = None      # (enc12, data, method, crc)
        self.verify_reason = None

    @property
    def gpu_ok(self):
        return len(self.targets) >= 2


def _zip_raw_time(zi):
    y, mo, d, h, mi, s = zi.date_time
    return (h << 11) | (mi << 5) | (s // 2)


def prepare_zip(path, max_targets=6):
    plan = ZipPlan()
    try:
        zf = zipfile.ZipFile(path)
    except Exception as e:
        plan.verify_reason = "无法打开 ZIP：%s" % e
        return plan
    with zf:
        infos = [i for i in zf.infolist() if (i.flag_bits & 0x1) and not i.is_dir()]
        if not infos:
            return plan
        try:
            f = open(path, "rb")
        except OSError:
            return plan
        with f:
            for zi in infos[:max_targets]:
                if zi.compress_type == 99 or (zi.flag_bits & 0x40):
                    return plan  # AES/强加密，交给 7-Zip
                f.seek(zi.header_offset)
                hdr = f.read(30)
                if len(hdr) < 30 or hdr[:4] != b"PK\x03\x04":
                    return plan
                (sig, ver, flags, method, mtime, mdate, crc, csize, usize, nlen, elen) = struct.unpack(
                    "<IHHHHHIIIHH", hdr)
                f.seek(zi.header_offset + 30 + nlen + elen)
                enc = f.read(12)
                if len(enc) != 12:
                    return plan
                if zi.flag_bits & 0x08:
                    check = (_zip_raw_time(zi) >> 8) & 0xFF
                else:
                    check = (zi.CRC >> 24) & 0xFF
                plan.targets.append((enc, check))
            # 找一个最小的 store/deflate 加密文件，供完整 CRC 验证
            cand = [i for i in infos if i.compress_type in (0, 8) and i.compress_size > 0
                    and i.compress_size <= 64 * 1024 * 1024]
            if not cand:
                plan.verify_reason = "包内没有可用于校验的 store/deflate 文件"
                return plan
            zi = min(cand, key=lambda x: x.compress_size)
            f.seek(zi.header_offset)
            hdr = f.read(30)
            if len(hdr) < 30 or hdr[:4] != b"PK\x03\x04":
                return plan
            (sig, ver, flags, method, mtime, mdate, crc, csize, usize, nlen, elen) = struct.unpack(
                "<IHHHHHIIIHH", hdr)
            f.seek(zi.header_offset + 30 + nlen + elen)
            enc = f.read(12)
            data = f.read(zi.compress_size)
            if len(data) != zi.compress_size:
                return plan
            plan.verify = (enc, data, zi.compress_type, zi.CRC)
    return plan


def verify_zip_with_zipfile(path, pw_bytes):
    try:
        with zipfile.ZipFile(path) as zf:
            infos = [i for i in zf.infolist() if (i.flag_bits & 0x1) and not i.is_dir()]
            # 不能只看第一个文件：它可能是 Deflate64 等 Python 不支持的压缩方式
            for zi in infos:
                if zi.compress_type not in (0, 8):
                    continue
                try:
                    with zf.open(zi, pwd=pw_bytes) as fh:
                        while fh.read(1 << 16):
                            pass
                    return True
                except Exception:
                    continue
        return False
    except Exception:
        return False


# ---------------------------------------------------------------------------
# C 原生 CPU 引擎（zipcpu.dll）
# ---------------------------------------------------------------------------
class NativeZip:
    def __init__(self):
        self.lib = None
        self.error = None
        candidates = [asset_path("zipcpu.dll"), os.path.join(BASE_DIR, "zipcpu.dll")]
        for p in candidates:
            if not os.path.isfile(p):
                continue
            try:
                lib = ctypes.WinDLL(p)
                lib.zipcpu_crack.argtypes = [
                    ctypes.c_char_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_int,
                    ctypes.POINTER(ctypes.c_ulonglong), ctypes.POINTER(ctypes.c_ulonglong),
                    ctypes.c_char_p, ctypes.c_uint32,
                    ctypes.c_char_p, ctypes.c_uint32, ctypes.c_char_p, ctypes.c_uint32,
                    ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint32,
                    ctypes.c_ulonglong, ctypes.c_ulonglong, ctypes.c_int,
                    ctypes.c_char_p, ctypes.POINTER(ctypes.c_ulonglong), ctypes.c_uint32,
                ]
                lib.zipcpu_crack.restype = ctypes.c_int
                lib.zipcpu_set_verify.argtypes = [ctypes.c_char_p, ctypes.c_char_p,
                                                  ctypes.c_ulonglong, ctypes.c_int, ctypes.c_uint32]
                lib.zipcpu_set_verify.restype = None
                lib.zipcpu_clear_verify.argtypes = []
                lib.zipcpu_clear_verify.restype = None
                lib.zipcpu_verify.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p,
                                              ctypes.c_char_p, ctypes.c_ulonglong, ctypes.c_int,
                                              ctypes.c_uint32]
                lib.zipcpu_verify.restype = ctypes.c_int
                lib.zipcpu_done.argtypes = []
                lib.zipcpu_done.restype = ctypes.c_ulonglong
                lib.zipcpu_found_index.argtypes = []
                lib.zipcpu_found_index.restype = ctypes.c_ulonglong
                lib.zipcpu_stop.argtypes = []
                lib.zipcpu_stop.restype = None
                self.lib = lib
                break
            except Exception as e:  # pragma: no cover
                self.error = str(e)
        if self.lib is None and not self.error:
            self.error = "缺少 zipcpu.dll"

    @property
    def available(self):
        return self.lib is not None

    def set_verify(self, verify):
        if verify is None:
            self.lib.zipcpu_clear_verify()
        else:
            enc, data, method, crc = verify
            self.lib.zipcpu_set_verify(enc, data, len(data), method, crc)

    def verify_candidate(self, pw_bytes):
        """优先用 C 的完整 CRC 验证；不支持时返回 None。"""
        verify = getattr(self, "_verify", None)
        if not verify:
            return None
        enc, data, method, crc = verify
        r = self.lib.zipcpu_verify(pw_bytes, len(pw_bytes), enc, data, len(data), method, crc)
        return None if r < 0 else bool(r)

    def crack(self, space, targets, verify, words_blob=None, words_offsets=None,
              total=0, start=0, nthreads=20, progress=None, stop=None):
        """阻塞运行 C 多线程扫描。返回 (ret, found_index, done_abs)。

        ret: 1=找到, 0=扫完, -1=被停止。
        """
        self._verify = verify
        self.set_verify(verify)
        enc = b"".join(t[0] for t in targets) if targets else b""
        check = bytes(t[1] for t in targets) if targets else b""
        ntargets = len(targets or [])
        if words_blob is not None:
            woff = (ctypes.c_ulonglong * len(words_offsets))(*words_offsets)
            args = (b"", 0, 0, 0, None, None, b"", 0, b"", 0, b"", 0,
                    enc, check, ntargets, total, start, nthreads,
                    words_blob, woff, len(words_offsets) - 1)
        else:
            charset = space.charset.encode("latin-1")
            buckets = space.buckets
            bstart = (ctypes.c_ulonglong * len(buckets))(*[b[1] for b in buckets])
            bsize = (ctypes.c_ulonglong * len(buckets))(*[b[2] for b in buckets])
            blen = bytes(b[0] for b in buckets)
            prefix = space.prefix.encode("latin-1")
            suffix = space.suffix.encode("latin-1")
            args = (charset, space.base, space.min_len, space.max_len,
                    bstart, bsize, blen, len(buckets),
                    prefix, len(prefix), suffix, len(suffix),
                    enc, check, ntargets, total, start, nthreads,
                    None, None, 0)
        finished = threading.Event()

        def monitor():
            while not finished.wait(0.1):
                if stop is not None and stop.is_set():
                    try:
                        self.lib.zipcpu_stop()
                    except Exception:
                        pass
                if progress:
                    try:
                        progress(start + int(self.lib.zipcpu_done()))
                    except Exception:
                        pass

        mon = threading.Thread(target=monitor, daemon=True)
        mon.start()
        try:
            ret = int(self.lib.zipcpu_crack(*args))
        finally:
            finished.set()
            mon.join(timeout=0.5)
        done = start + int(self.lib.zipcpu_done())
        idx = int(self.lib.zipcpu_found_index())
        return ret, idx, done


# ---------------------------------------------------------------------------
# 7-Zip 引擎
# ---------------------------------------------------------------------------
def find_7z():
    for p in (
        asset_path("7z.exe"),
        os.path.join(ASSETS_DIR, "7z.exe"),
        r"C:\Program Files\7-Zip\7z.exe",
        r"C:\Program Files (x86)\7-Zip\7z.exe",
    ):
        if p and os.path.isfile(p):
            return p
    return None


class SevenZip:
    def __init__(self):
        self.exe = find_7z()

    @property
    def available(self):
        return bool(self.exe)

    def _run(self, args, timeout=120, capture_stderr=False):
        return subprocess.run([self.exe] + args,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE if capture_stderr else DEVNULL,
                              timeout=timeout, creationflags=CREATE_NO_WINDOW)

    def probe_verbose(self, archive):
        try:
            r = self._run(["l", "-slt", "-y", "--", archive], capture_stderr=True)
            return r.returncode, (r.stdout or b"") + b"\n" + (r.stderr or b"")
        except Exception as e:
            return -1, str(e).encode("utf-8", "replace")

    def test(self, archive, password, target=None, timeout=120):
        ok, _err = self.test_checked(archive, password, target, timeout)
        return ok

    def test_checked(self, archive, password, target=None, timeout=120):
        """返回 (success, error)。error=None 表示密码不对，不是环境问题。"""
        if not self.exe:
            return False, "找不到 7z.exe"
        args = ["t", "-y", "-bsp0", "-bse0", "-p" + password, "--", archive]
        if target:
            args.append(target)
        try:
            r = self._run(args, timeout)
        except subprocess.TimeoutExpired:
            return False, "7-Zip 校验超时（%d 秒）" % timeout
        except Exception as e:
            return False, "7-Zip 调用失败：%s" % e
        out = (r.stdout or b"").decode("utf-8", "replace")
        if r.returncode == 0 and "Everything is Ok" in out:
            return True, None
        low = out.lower()
        # 先分清“环境坏了”和“密码不对”：7z 对错误密码通常只报 Sub items Errors
        if ("error:" in low or "can not open" in low or "cannot open" in low
                or "no more files" in low):
            tail = " ".join(out.strip().splitlines()[-2:])[:200]
            return False, "7-Zip 返回码 %d：%s" % (r.returncode, tail or "无输出")
        if ("wrong password" in low or "data error in encrypted file" in low
                or "crc failed" in low or "no files to process" in low
                or "sub items errors" in low or "archives with errors" in low):
            return False, None
        tail = " ".join(out.strip().splitlines()[-2:])[:200]
        return False, "7-Zip 返回码 %d：%s" % (r.returncode, tail or "无输出")

    def probe(self, archive, password):
        try:
            r = self._run(["t", "-y", "-bsp0", "-bse0", "-p" + password, "--", archive])
            return r.returncode, (r.stdout or b"")
        except Exception:
            return -1, b""

    def is_encrypted(self, archive):
        rc, out = self.probe(archive, "__probe_%d_%d__" % (os.getpid(), int(time.time() * 1000)))
        return not (rc == 0 and b"Everything is Ok" in out)

    def list(self, archive):
        try:
            r = self._run(["l", "-slt", "-y", "--", archive])
        except Exception:
            return None
        if r.returncode != 0:
            return None
        text = (r.stdout or b"").decode("utf-8", "replace")
        records = []
        cur = {}

        def flush():
            nonlocal cur
            if cur.get("Path") is not None:
                records.append(cur)
            cur = {}

        for line in text.splitlines():
            line = line.rstrip("\r")
            if not line.strip() or line.startswith("---"):
                continue
            if " = " not in line:
                continue
            k, v = line.split(" = ", 1)
            if k == "Path":
                if cur.get("Path") is not None:
                    flush()
                cur["Path"] = v
            else:
                cur[k] = v
        flush()
        entries = []
        for rec in records:
            if "Type" in rec and "Physical Size" in rec:
                continue
            p = rec.get("Path")
            if not p or rec.get("Folder") == "+":
                continue
            try:
                size = int(rec.get("Size", "0"))
            except ValueError:
                size = 0
            entries.append({"path": p, "size": size, "encrypted": rec.get("Encrypted") == "+"})
        return entries

    def pick_target(self, archive, kind):
        if kind not in ("rar", "7z", "zip"):
            return None
        entries = self.list(archive)
        if not entries:
            return None
        cand = []
        for e in entries:
            p = e["path"]
            if not e["encrypted"] or e["size"] <= 0 or not p.isascii():
                continue
            if any(ch in p for ch in "*?<>|"):
                continue
            cand.append(e)
        if not cand:
            return None
        target = min(cand, key=lambda x: x["size"])["path"]
        rc, out = self.probe(archive, "__filter_probe__")
        if b"No files to process" in out:
            return None
        return target

    def extract(self, archive, password, outdir):
        if not self.exe:
            return False, "找不到 7z.exe"
        os.makedirs(outdir, exist_ok=True)
        try:
            r = subprocess.run(
                [self.exe, "x", "-y", "-bsp0", "-bse0", "-p" + password, "-o" + outdir, "--", archive],
                stdout=subprocess.PIPE, stderr=DEVNULL, timeout=3600,
                creationflags=CREATE_NO_WINDOW)
        except Exception as e:
            return False, str(e)
        ok = r.returncode == 0 and b"Everything is Ok" in (r.stdout or b"")
        return ok, "解压完成" if ok else "解压失败（返回码 %s）" % r.returncode


# ---------------------------------------------------------------------------
# 硬件监控
# ---------------------------------------------------------------------------
class _PDHItem(ctypes.Structure):
    _fields_ = [("szName", ctypes.c_wchar_p), ("FmtValue", ctypes.c_byte * 16)]


class _PDH:
    FMT_DOUBLE = 0x200

    def __init__(self):
        self.ok = False
        try:
            self.pdh = ctypes.WinDLL("pdh.dll")
            self.pdh.PdhOpenQueryW.argtypes = [ctypes.c_wchar_p, ctypes.c_size_t,
                                               ctypes.POINTER(ctypes.c_void_p)]
            self.pdh.PdhAddEnglishCounterW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p,
                                                       ctypes.c_size_t, ctypes.POINTER(ctypes.c_void_p)]
            self.pdh.PdhCollectQueryData.argtypes = [ctypes.c_void_p]
            self.pdh.PdhGetFormattedCounterArrayW.argtypes = [
                ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong),
                ctypes.POINTER(ctypes.c_ulong), ctypes.c_void_p]
            self.pdh.PdhCloseQuery.argtypes = [ctypes.c_void_p]
            self.ok = True
        except Exception:
            self.ok = False

    def counter(self, path):
        if not self.ok:
            return None
        q = ctypes.c_void_p()
        if self.pdh.PdhOpenQueryW(None, 0, ctypes.byref(q)) != 0:
            return None
        c = ctypes.c_void_p()
        if self.pdh.PdhAddEnglishCounterW(q, path, 0, ctypes.byref(c)) != 0:
            self.pdh.PdhCloseQuery(q)
            return None
        return (q, c)

    def values(self, ctr):
        if not ctr:
            return []
        q, c = ctr
        if self.pdh.PdhCollectQueryData(q) != 0:
            return []
        size = ctypes.c_ulong(0)
        count = ctypes.c_ulong(0)
        r = self.pdh.PdhGetFormattedCounterArrayW(c, self.FMT_DOUBLE, ctypes.byref(size),
                                                  ctypes.byref(count), None)
        if (r & 0xFFFFFFFF) != 0x800007D2 or count.value == 0:
            return []
        buf = (ctypes.c_byte * size.value)()
        if self.pdh.PdhGetFormattedCounterArrayW(c, self.FMT_DOUBLE, ctypes.byref(size),
                                                 ctypes.byref(count), buf) != 0:
            return []
        arr = ctypes.cast(buf, ctypes.POINTER(_PDHItem))
        out = []
        for i in range(count.value):
            item = arr[i]
            # 第一个字段是 CStatus（DWORD），随后 union 里是 double
            raw = bytes(item.FmtValue)
            status = struct.unpack_from("<I", raw, 0)[0]
            val = struct.unpack_from("<d", raw, 8)[0]
            if status == 0:
                out.append((item.szName, val))
        return out

    def close(self):
        pass


class Hardware:
    def __init__(self):
        self.cpu_name = self._cpu_name()
        self.ram_total = 0
        self.gpu_name = ""
        self.gpu_vendor = ""
        self.gpu_mem_total = 0
        self.gpu_opencl_mem = 0
        self._pdh = _PDH()
        self._ctr_util = self._pdh.counter(r"\GPU Engine(*)\Utilization Percentage")
        self._ctr_ded = self._pdh.counter(r"\GPU Adapter Memory(*)\Dedicated Usage")
        self._ram_used = 0
        self._cpu_pct = 0.0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._sample_gpu()
        if psutil:
            try:
                self.ram_total = psutil.virtual_memory().total
                self._cpu_pct = psutil.cpu_percent(interval=None)
            except Exception:
                self.ram_total = 0
        try:
            self._pdh.values(self._ctr_util)
            self._pdh.values(self._ctr_ded)
        except Exception:
            pass
        self._apply()

    # ---- 静态信息 ----
    def _cpu_name(self):
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as k:
                return winreg.QueryValueEx(k, "ProcessorNameString")[0].strip()
        except Exception:
            return "CPU"

    def _sample_gpu(self):
        self.gpu_name = ""
        self.gpu_opencl_name = ""
        # CUDA 优先（N 卡独显），其次 OpenCL 里优先非 Intel 的独显
        try:
            cuda_mod = _import_cuda()
            dev = cuda_mod.best_device() if cuda_mod else None
            if dev is not None:
                self.gpu_name = dev.get("name") or ""
                self.gpu_vendor = "NVIDIA"
                self.gpu_opencl_mem = int(dev.get("mem") or 0)
                self.gpu_cuda = True
        except Exception:
            pass
        try:
            from gpu import enum_devices
            gpus = [d for d in enum_devices() if d["type"] & 4]
            if gpus:
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
                best = max(gpus, key=score)
                self.gpu_opencl_name = best["name"]
                if not self.gpu_name:
                    self.gpu_name = best["name"]
                    self.gpu_vendor = best["vendor"]
                    self.gpu_opencl_mem = best["mem"]
        except Exception:
            pass
        adapters = self._registry_adapters()
        best_adapter = None
        if adapters:
            if self.gpu_vendor == "NVIDIA":
                nv = [a for a in adapters if "nvidia" in a[0].lower()]
                if nv:
                    best_adapter = max(nv, key=lambda x: x[1])
            if best_adapter is None:
                best_adapter = max(adapters, key=lambda x: x[1])
        if best_adapter and best_adapter[1] > 0:
            desc = best_adapter[0]
            # 用显卡型号名（如 “AMD Radeon(TM) 880M Graphics”）代替 gfx1150
            if desc and (not self.gpu_name or self.gpu_name.lower().startswith(("gfx", "unknown"))):
                self.gpu_name = desc
            self.gpu_mem_total = int(best_adapter[1])
        else:
            self.gpu_mem_total = self.gpu_opencl_mem

    def _registry_adapters(self):
        out = []
        try:
            import winreg
            base = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base) as root:
                i = 0
                while True:
                    try:
                        name = winreg.EnumKey(root, i)
                    except OSError:
                        break
                    i += 1
                    if not name.isdigit():
                        continue
                    try:
                        with winreg.OpenKey(root, name) as sub:
                            desc = winreg.QueryValueEx(sub, "DriverDesc")[0]
                            mem = 0
                            try:
                                mem = winreg.QueryValueEx(sub, "HardwareInformation.qwMemorySize")[0]
                                if isinstance(mem, bytes):
                                    mem = int.from_bytes(mem, "little")
                            except OSError:
                                mem = 0
                            out.append((str(desc), int(mem)))
                    except OSError:
                        continue
        except Exception:
            return []
        return out

    # ---- 采样 ----
    def start(self, interval=1.0):
        if self._thread:
            return
        self._stop.clear()

        def loop():
            while not self._stop.wait(interval):
                self._apply()

        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    def _apply(self):
        cpu_pct = 0.0
        ram_used = 0
        gpu_util = 0.0
        vram_used = 0.0
        try:
            if psutil:
                cpu_pct = psutil.cpu_percent(interval=None)
                vm = psutil.virtual_memory()
                ram_used = vm.total - vm.available
        except Exception:
            pass
        try:
            vals = self._pdh.values(self._ctr_util)
            if vals:
                gpu_util = max(0.0, min(100.0, max(v for _, v in vals)))
        except Exception:
            pass
        try:
            vals = self._pdh.values(self._ctr_ded)
            if vals:
                vram_used = sum(v for _, v in vals)
        except Exception:
            pass
        with self._lock:
            self._cpu_pct = cpu_pct
            self._ram_used = ram_used
            self._gpu_util = gpu_util
            self._vram_used = vram_used

    def snapshot(self):
        with self._lock:
            return {
                "cpu": self._cpu_pct,
                "ram_used": self._ram_used,
                "ram_total": self.ram_total,
                "gpu_name": self.gpu_name,
                "gpu_util": getattr(self, "_gpu_util", 0.0),
                "vram_used": getattr(self, "_vram_used", 0.0),
                "vram_total": self.gpu_mem_total,
            }

def registry_gpu_name():
    """从注册表读取显卡型号名（如 AMD Radeon(TM) 880M Graphics）。"""
    best = None
    try:
        import winreg
        base = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base) as root:
            i = 0
            while True:
                try:
                    name = winreg.EnumKey(root, i)
                except OSError:
                    break
                i += 1
                if not name.isdigit():
                    continue
                try:
                    with winreg.OpenKey(root, name) as sub:
                        desc = winreg.QueryValueEx(sub, "DriverDesc")[0]
                        mem = 0
                        try:
                            mem = winreg.QueryValueEx(sub, "HardwareInformation.qwMemorySize")[0]
                            if isinstance(mem, bytes):
                                mem = int.from_bytes(mem, "little")
                        except OSError:
                            mem = 0
                        if best is None or mem > best[1]:
                            best = (str(desc), int(mem))
                except OSError:
                    continue
    except Exception:
        return ""
    return best[0] if best else ""


# ---------------------------------------------------------------------------
# GPU 后端：CUDA 优先，OpenCL 兜底
# ---------------------------------------------------------------------------
_GPU_BACKEND = None
_GPU_BACKEND_ERR = None
_OPENCL_BACKEND = None
_GPU_BACKEND_LOCK = threading.Lock()
_SELFTEST_RESULT = None      # 启动自检结果：搜索时优先沿用，保证“标签写的”和“实际用的”一致


class GpuBackend:
    """统一的 GPU 后端封装：CUDA（nvcuda.dll + PTX）或 OpenCL（OpenCL.dll）。"""

    def __init__(self, kind, mod, device):
        self.kind = kind            # "cuda" / "opencl"
        self.mod = mod
        self.dev = device
        self._engine = None
        self._engine_error = None

    # ---- 展示 ----
    @property
    def label_zh(self):
        return "GPU · CUDA" if self.kind == "cuda" else "GPU · OpenCL"

    @property
    def label_en(self):
        return "GPU · CUDA" if self.kind == "cuda" else "GPU · OpenCL"

    def describe(self, engine):
        dev = getattr(engine, "dev", None) or self.dev or {}
        name = dev.get("name") or "GPU"
        if self.kind == "cuda":
            cc = dev.get("cc") or 0
            drv = dev.get("driver") or 0
            zh = ("GPU：%s（NVIDIA CUDA %.1f · sm_%d · PTX %s，驱动 JIT %.0f ms）"
                  % (name, drv / 1000.0, cc, getattr(engine, "ptx_name", "?"),
                     getattr(engine, "build_ms", 0.0)))
            en = ("GPU: %s (NVIDIA CUDA %.1f · sm_%d · PTX %s, driver JIT %.0f ms)"
                  % (name, drv / 1000.0, cc, getattr(engine, "ptx_name", "?"),
                     getattr(engine, "build_ms", 0.0)))
        else:
            zh = "GPU：%s（%s，内核编译 %.0f ms）" % (
                name, dev.get("vendor", ""), getattr(engine, "build_ms", 0.0))
            en = "GPU: %s (%s, kernel build %.0f ms)" % (
                name, dev.get("vendor", ""), getattr(engine, "build_ms", 0.0))
        return zh, en

    # ---- 能力 ----
    def supports(self, space):
        if space is None:
            return False
        if not space.ascii_ok:
            return False
        if self.kind == "cuda":
            # CUDA 内核限制：无前后缀、≤ 8 位、2–255 字符集
            return (not space.prefix and not space.suffix and space.max_len <= 8
                    and 2 <= space.base <= 255 and len(space.buckets) <= 8)
        return True

    # ---- 引擎实例（懒创建 + 复用） ----
    def engine(self):
        if self._engine is not None:
            return self._engine
        if self._engine_error is not None:
            raise RuntimeError(self._engine_error)
        try:
            if self.kind == "cuda":
                self._engine = self.mod.CudaZipCracker(self.dev)
            else:
                self._engine = self.mod.GPUZipCracker()
        except Exception as e:
            self._engine_error = str(e)
            raise
        return self._engine

    def reset_engine(self):
        try:
            if self._engine is not None and hasattr(self._engine, "close"):
                self._engine.close()
        except Exception:
            pass
        self._engine = None
        self._engine_error = None


def _opencl_backend():
    global _OPENCL_BACKEND
    if _OPENCL_BACKEND is not None:
        return _OPENCL_BACKEND
    try:
        import gpu as gpu_mod
        dev = gpu_mod.best_gpu()
    except Exception:
        return None
    if dev is None:
        return None
    _OPENCL_BACKEND = GpuBackend("opencl", gpu_mod, dev)
    return _OPENCL_BACKEND


def gpu_backend(kind=None):
    """返回可用的 GPU 后端（CUDA 优先，其次 OpenCL），结果进程内缓存。"""
    global _GPU_BACKEND, _GPU_BACKEND_ERR
    if kind == "opencl":
        return _opencl_backend()
    if _GPU_BACKEND is not None:
        return _GPU_BACKEND
    if _GPU_BACKEND_ERR is not None:
        return None
    st = _SELFTEST_RESULT
    with _GPU_BACKEND_LOCK:
        if _GPU_BACKEND is not None:
            return _GPU_BACKEND
        # 启动自检已经跑过：按它的结论选后端，避免 CUDA 内核在自检里失败、
        # 搜索时却还硬走 CUDA 导致“扫完却没有命中”的静默错误。
        if st is not None:
            chosen = st.get("backend")
            if chosen == "opencl":
                oc = _opencl_backend()
                if oc is not None:
                    _GPU_BACKEND = oc
                    return _GPU_BACKEND
                _GPU_BACKEND_ERR = "启动自检 CUDA 未通过，且 OpenCL 不可用"
                return None
            if chosen == "cpu":
                _GPU_BACKEND_ERR = "启动自检未发现可用 GPU 后端"
                return None
        cuda_mod = _import_cuda()
        if cuda_mod is not None:
            try:
                dev = cuda_mod.best_device()
            except Exception:
                dev = None
            if dev is not None:
                _GPU_BACKEND = GpuBackend("cuda", cuda_mod, dev)
                return _GPU_BACKEND
        oc = _opencl_backend()
        if oc is not None:
            _GPU_BACKEND = oc
            return _GPU_BACKEND
        _GPU_BACKEND_ERR = "未检测到可用的 GPU 后端（CUDA / OpenCL 都不可用）"
        return None


def gpu_backend_error():
    return _GPU_BACKEND_ERR


def gpu_backend_fallback(backend):
    """当前后端是 CUDA 且不可用时，返回 OpenCL 后端（没有则 None）。"""
    if backend is not None and backend.kind == "cuda":
        return _opencl_backend()
    return None


# ---------------------------------------------------------------------------
# 启动自检：探测 CPU / OpenCL / CUDA，并跑一次真实扫描
# ---------------------------------------------------------------------------
def _selftest_scan(engine, space, targets, total, expect=None, stop=None):
    """扫描并收集命中，返回 (命中列表, 已扫数量, 耗时秒)。"""
    t0 = time.time()
    found = []
    done = 0
    for matches, done in engine.iter_chunks(space, targets, total, stop=stop):
        found.extend(int(x) for x in matches)
        if expect is not None and int(expect) in found:
            break
    return found, done, time.time() - t0


def _selftest_gpu(backend):
    """在指定 GPU 后端上跑一次小规模扫描，返回自检结果。"""
    t0 = time.time()
    info = {"backend": backend.kind, "name": "", "vendor": "", "cc": "", "rate": 0.0,
            "elapsed": 0.0, "build_ms": 0.0, "ok": False, "error": None,
            "detail": ""}
    engine = None
    try:
        engine = backend.engine()
        dev = getattr(engine, "dev", None) or backend.dev or {}
        info["name"] = dev.get("name") or ""
        info["vendor"] = dev.get("vendor") or ""
        if backend.kind == "cuda":
            info["cc"] = "sm_%d" % (dev.get("cc") or 0)
            info["detail"] = "NVIDIA CUDA %.1f · %s" % (
                (dev.get("driver") or 0) / 1000.0, getattr(engine, "ptx_name", ""))
        else:
            # OpenCL 的 CL_DEVICE_NAME 常常是 gfx1150 这类代号，换成注册表里的型号名
            try:
                info["name"] = registry_gpu_name() or info["name"]
            except Exception:
                pass
            info["detail"] = "%s · %s" % (dev.get("vendor", ""), dev.get("version", ""))
        info["build_ms"] = float(getattr(engine, "build_ms", 0.0) or 0.0)

        # 第 1 段：先用一个不可能命中的目标测吞吐（8 位数字共 1 亿候选）
        space = Space(DIGITS, 8, 8)
        total = space.total
        dummy = make_selftest_targets(b"\x01" * 8, 3)
        probe_n = min(total, 4_000_000)
        _, done, cost = _selftest_scan(engine, space, dummy, probe_n)
        rate = done / cost if cost > 0 else 0.0

        # 第 2 段：按吞吐决定扫描量（目标 ~150 ms），真找一个指定候选并核对
        n = int(rate * 0.15)
        n = max(2_000_000, min(n, 80_000_000, total))
        idx = n - 1
        pw = space.decode(idx).encode("latin-1")
        targets = make_selftest_targets(pw, 3)
        found, done, cost = _selftest_scan(engine, space, targets, idx + 1, expect=idx)
        ok = bool(found) and any(int(i) == idx for i in found)
        if not ok and found:
            ok = any(space.decode(int(i)).encode("latin-1") == pw for i in found[:16])
        if not ok:
            raise RuntimeError("内核扫描没有命中自检候选（可能内核/内核参数不对）")
        if cost <= 0:
            cost = 1e-6
        info["rate"] = (done / cost) if cost > 0 else rate
        info["elapsed"] = time.time() - t0
        info["ok"] = True
    except Exception as e:
        info["error"] = str(e)
        info["elapsed"] = time.time() - t0
    finally:
        if engine is not None:
            try:
                info["build_ms"] = float(getattr(engine, "build_ms", info["build_ms"]) or 0.0)
            except Exception:
                pass
            try:
                if hasattr(engine, "close"):
                    engine.close()
            except Exception:
                pass
    return info


def _selftest_cpu():
    """CPU 引擎自检，返回吞吐。"""
    info = {"backend": "cpu", "name": "", "vendor": "", "cc": "", "rate": 0.0,
            "elapsed": 0.0, "build_ms": 0.0, "ok": False, "error": None,
            "detail": ""}
    t0 = time.time()
    try:
        native = NativeZip()
        if not native.available:
            raise RuntimeError(native.error or "缺少 zipcpu.dll")
        info["name"] = "CPU · Native"
        space = Space(DIGITS, 6, 6)
        total = space.total
        pw = space.decode(total - 1).encode("latin-1")
        targets = make_selftest_targets(pw, 3)
        t1 = time.time()
        native.set_verify(None)
        ret, idx, done = native.crack(space, targets, None, total=total, start=0,
                                      nthreads=default_workers())
        cost = max(1e-6, time.time() - t1)
        if int(ret) != 1 or int(idx) != total - 1:
            raise RuntimeError("CPU 引擎自检未命中（ret=%s idx=%s）" % (ret, idx))
        info["rate"] = max(1.0, int(done) / cost)
        info["ok"] = True
        info["detail"] = "%d 线程" % default_workers()
    except Exception as e:
        info["error"] = str(e)
    info["elapsed"] = time.time() - t0
    return info


def quick_backend_check():
    """启动自检：返回 {backend, name, rate, ...}，结果缓存给 gpu_backend() 复用。"""
    global _SELFTEST_RESULT
    result = _quick_backend_check_impl()
    _SELFTEST_RESULT = result
    return result


def _quick_backend_check_impl():
    result = {"backend": "cpu", "name": "", "vendor": "", "cc": "", "rate": 0.0,
              "elapsed": 0.0, "build_ms": 0.0, "ok": False, "error": None,
              "detail": "", "tried": []}
    t0 = time.time()

    cuda_mod = _import_cuda()
    if cuda_mod is not None:
        try:
            dev = cuda_mod.best_device()
        except Exception:
            dev = None
        if dev is not None:
            info = _selftest_gpu(GpuBackend("cuda", cuda_mod, dev))
            result["tried"].append(info)
            if info["ok"]:
                result.update(info)
                result["backend"] = "cuda"
                result["elapsed"] = time.time() - t0
                return result

    oc = _opencl_backend()
    if oc is not None:
        info = _selftest_gpu(oc)
        result["tried"].append(info)
        if info["ok"]:
            result.update(info)
            result["backend"] = "opencl"
            result["elapsed"] = time.time() - t0
            return result

    info = _selftest_cpu()
    result["tried"].append(info)
    result.update(info)
    result["backend"] = "cpu"
    result["elapsed"] = time.time() - t0
    return result


# ---------------------------------------------------------------------------
# 搜索调度
# ---------------------------------------------------------------------------
class Emitter:
    def __init__(self, emit, interval=0.12):
        self.emit = emit
        self.interval = interval
        self.last = 0.0
        self.t0 = time.time()
        self.total = 0
        self.base = 0
        self.grand_total = 0
        self.stage_t0 = time.time()
        self.stage_zh = ""
        self.stage_en = ""
        self.stage_index = 0
        self.stage_count = 0

    def start(self, total):
        self.total = int(total)
        self.grand_total = self.total
        self.base = 0
        self.stage_t0 = time.time()
        self.emit({"type": "space", "total": self.total})

    def set_scope(self, base, grand_total, stage_zh="", stage_en="", index=0, count=0):
        self.base = int(base)
        self.grand_total = int(grand_total)
        self.total = self.grand_total
        self.stage_t0 = time.time()
        self.stage_zh = stage_zh
        self.stage_en = stage_en
        self.stage_index = index
        self.stage_count = count

    def event(self, kind, **kw):
        self.emit(dict(type=kind, **kw))

    def log(self, text, en=None):
        self.emit({"type": "log", "text": text, "en": en or text})

    def engine(self, name, gpu=False, en=None):
        self.emit({"type": "engine", "name": name, "gpu": gpu, "en": en or name})

    def progress(self, done, force=False):
        now = time.time()
        if not force and now - self.last < self.interval:
            return
        self.last = now
        overall = self.base + done
        stage_elapsed = max(1e-6, now - self.stage_t0)
        rate = done / stage_elapsed
        remain = max(0, self.grand_total - overall)
        eta = remain / rate if rate > 0 else None
        self.emit({"type": "progress", "done": int(overall), "total": int(self.grand_total),
                   "rate": rate, "elapsed": now - self.t0, "eta": eta,
                   "stage_index": self.stage_index, "stage_count": self.stage_count,
                   "stage_zh": self.stage_zh, "stage_en": self.stage_en})

    def found(self, password, attempts):
        self.emit({"type": "found", "password": password,
                   "attempts": int(self.base + attempts),
                   "elapsed": time.time() - self.t0})


def decode_password_bytes(pw_bytes):
    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            return pw_bytes.decode(enc)
        except UnicodeDecodeError:
            continue
    return repr(pw_bytes)


def candidate_bytes(space, words_blob, words_offsets, idx):
    if words_blob is not None:
        return words_blob[words_offsets[idx]:words_offsets[idx + 1]]
    return space.decode(idx).encode("latin-1")


def _run_native_zip(native, plan, archive, space, words_blob, words_offsets,
                    total, nthreads, emitter, stop):
    emitter.engine("CPU · 原生多线程（C 引擎）", en="CPU · Native (C engine)")
    start = 0
    last_done = 0
    while start < total:
        if stop.is_set():
            return {"found": False, "password": None, "reason": "stopped",
                    "attempts": last_done, "elapsed": time.time() - emitter.t0}

        def progress(abs_done):
            nonlocal last_done
            last_done = abs_done
            if not stop.is_set():
                emitter.progress(abs_done)

        ret, idx, done = native.crack(
            space, plan.targets, plan.verify,
            words_blob=words_blob, words_offsets=words_offsets,
            total=total, start=start, nthreads=nthreads,
            progress=progress, stop=stop)
        last_done = done
        if ret == 1:
            pw_bytes = candidate_bytes(space, words_blob, words_offsets, idx)
            if verify_zip_with_zipfile(archive, pw_bytes):
                text = decode_password_bytes(pw_bytes)
                emitter.progress(idx + 1, force=True)
                emitter.found(text, idx + 1)
                return {"found": True, "password": text, "reason": "found",
                        "attempts": idx + 1, "elapsed": time.time() - emitter.t0}
            emitter.log("候选未通过整包校验，继续搜索…")
            start = idx + 1
            continue
        if ret == -1:
            return {"found": False, "password": None, "reason": "stopped",
                    "attempts": last_done, "elapsed": time.time() - emitter.t0}
        break
    emitter.progress(total, force=True)
    return {"found": False, "password": None, "reason": "exhausted",
            "attempts": total, "elapsed": time.time() - emitter.t0}


def _run_gpu_zip(backend, native, plan, archive, space, total, emitter, stop):
    gpu_engine = backend.engine()
    if native.available and plan.verify is not None:
        native.set_verify(plan.verify)
    emitter.engine(backend.label_zh, en=backend.label_en)
    zh, en = backend.describe(gpu_engine)
    emitter.log(zh, en=en)
    for matches, done in gpu_engine.iter_chunks(space, plan.targets, total, stop=stop):
        for idx in matches:
            pw_text = space.decode(idx)
            pw_bytes = pw_text.encode("latin-1")
            ok = None
            if native.available and plan.verify is not None:
                ok = native.verify_candidate(pw_bytes)
            if ok is None:
                ok = verify_zip_with_zipfile(archive, pw_bytes)
            if ok:
                if verify_zip_with_zipfile(archive, pw_bytes):
                    emitter.progress(idx + 1, force=True)
                    emitter.found(pw_text, idx + 1)
                    return {"found": True, "password": pw_text, "reason": "found",
                            "attempts": idx + 1, "elapsed": time.time() - emitter.t0}
        if stop.is_set():
            break
        emitter.progress(done)
    if stop.is_set():
        return {"found": False, "password": None, "reason": "stopped",
                "attempts": 0, "elapsed": time.time() - emitter.t0}
    emitter.progress(total, force=True)
    return {"found": False, "password": None, "reason": "exhausted",
            "attempts": total, "elapsed": time.time() - emitter.t0}


def _run_7z(seven, space, words, archive, total, workers, emitter, stop, target,
            emit_engine=True):
    from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

    if emit_engine:
        emitter.engine("7-Zip（CPU 校验）", en="7-Zip (CPU verification)")
    if words is not None:
        it = iter(words)
    else:
        it = space.iterate()
    attempts = 0
    found = None
    pending = {}
    error = None
    ex = ThreadPoolExecutor(max_workers=max(1, workers))
    exhausted = False
    try:
        while not stop.is_set():
            while len(pending) < workers * 2 and not exhausted:
                try:
                    pw = next(it)
                except StopIteration:
                    exhausted = True
                    break
                pending[ex.submit(seven.test_checked, archive, pw, target)] = pw
            if not pending:
                break
            done, _ = wait(list(pending.keys()), timeout=0.2, return_when=FIRST_COMPLETED)
            for fut in done:
                pw = pending.pop(fut)
                attempts += 1
                try:
                    ok, err = fut.result()
                except Exception as e:
                    ok, err = False, "7-Zip 校验异常：%s" % e
                if err:
                    error = err
                    stop.set()
                    break
                if ok and target is not None:
                    ok, err = seven.test_checked(archive, pw, None)
                    if err:
                        error = err
                        stop.set()
                        break
                if ok:
                    found = pw
                    stop.set()
                    break
            if error or found:
                break
            emitter.progress(attempts)
    finally:
        try:
            ex.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            ex.shutdown(wait=False)
    if error:
        return {"found": False, "password": None, "reason": "error",
                "message": error, "attempts": attempts,
                "elapsed": time.time() - emitter.t0}
    if found:
        emitter.progress(attempts, force=True)
        emitter.found(found, attempts)
        return {"found": True, "password": found, "reason": "found",
                "attempts": attempts, "elapsed": time.time() - emitter.t0}
    reason = "stopped" if stop.is_set() else "exhausted"
    return {"found": False, "password": None, "reason": reason,
            "attempts": attempts, "elapsed": time.time() - emitter.t0}


def run_search(opts, emit, stop):
    """执行一次破解任务。opts: archive/mode/charset/minlen/maxlen/wordlist/prefix/suffix/workers/engine。"""
    t0 = time.time()
    archive = os.path.abspath(opts["archive"])
    if not os.path.isfile(archive):
        raise RuntimeError("压缩包不存在：%s" % archive)
    kind = detect_kind(archive)
    if kind is None:
        raise RuntimeError("无法识别的压缩包格式")
    seven = SevenZip()
    if not seven.available:
        raise RuntimeError("找不到 7z.exe（安装包不完整）")
    emitter = Emitter(emit)
    emitter.t0 = t0
    emit({"type": "start", "kind": kind, "archive": archive})
    if not seven.is_encrypted(archive):
        return {"found": False, "password": None, "reason": "not_encrypted",
                "attempts": 0, "elapsed": time.time() - t0}

    words = None
    words_blob = None
    words_offsets = None
    space = None
    mode = opts["mode"]
    if mode == "dict":
        raw_words = load_wordlist(opts["wordlist"])
        if not raw_words:
            raise RuntimeError("字典文件为空")
        prefix = opts.get("prefix", "")
        suffix = opts.get("suffix", "")
        words = [prefix + w + suffix for w in raw_words]
        words_blob, words_offsets = build_words_blob(words)
        total = len(words)
    else:
        space = Space(opts["charset"], int(opts["minlen"]), int(opts["maxlen"]),
                      opts.get("prefix", ""), opts.get("suffix", ""))
        total = space.total
    emitter.start(total)
    emitter.log("候选总数：%s" % fmt_num(total))
    workers = max(1, min(64, int(opts.get("workers") or default_workers())))
    prefer = opts.get("engine", "auto")

    gpu = gpu_backend()
    if gpu is not None:
        gpu_dev = gpu.dev
    else:
        gpu_dev = None
    gpu_mod = None

    if kind == "zip":
        plan = prepare_zip(archive)
        if plan.targets:
            native = NativeZip()
            is_dict = words_blob is not None
            can_native = native.available and (
                is_dict or (space is not None and space.ascii_ok))
            use_gpu = False
            if (prefer in ("auto", "gpu") and gpu is not None and not is_dict
                    and space is not None and gpu.supports(space)
                    and plan.verify is not None and len(plan.targets) >= 2):
                if prefer == "gpu":
                    use_gpu = True
                elif len(plan.targets) >= 2:
                    use_gpu = True
            if use_gpu:
                try:
                    res = _run_gpu_zip(gpu, native, plan, archive, space, total,
                                       emitter, stop)
                    return res
                except Exception as e:
                    emitter.log("GPU 不可用：%s，回退 CPU" % e)
                    fb = gpu_backend_fallback(gpu)
                    if fb is not None:
                        try:
                            emitter.log("尝试 OpenCL 后端…", en="Trying the OpenCL backend…")
                            return _run_gpu_zip(fb, native, plan, archive, space, total,
                                                emitter, stop)
                        except Exception as e2:
                            emitter.log("OpenCL 也不可用：%s，回退 CPU" % e2)
            else:
                if prefer == "gpu":
                    emitter.log("该压缩包不适合 GPU（单文件校验强度不足或不是 ZipCrypto），改用 CPU")
                elif is_dict:
                    emitter.log("字典模式使用 CPU 原生引擎")
                elif len(plan.targets) < 2:
                    emitter.log("单文件 ZIP 校验强度不足以支撑 GPU 误报筛选，自动选择 CPU 原生引擎")
                elif gpu is None or not gpu.supports(space):
                    emitter.log("该候选空间超出 CUDA 内核范围（长度/字符集/前后缀），改用 CPU")
            if can_native:
                return _run_native_zip(native, plan, archive, space, words_blob, words_offsets,
                                       total, min(workers, os.cpu_count() or 4), emitter, stop)
            emitter.log("该压缩包无法使用原生引擎，改用 7-Zip 校验")
        else:
            emitter.log("ZIP 使用 AES/强加密或解析失败，GPU/原生引擎不适用，改用 7-Zip")
        target = seven.pick_target(archive, kind)
        return _run_7z(seven, space, words, archive, total, workers, emitter, stop, target)

    if prefer == "gpu":
        emitter.log("RAR / 7Z 暂不支持 GPU 加速（需要 AES + PBKDF2 内核），使用 7-Zip（CPU）校验")
    target = seven.pick_target(archive, kind)
    if target:
        emitter.log("加速校验：只测试包内最小的加密文件（%s）" % target)
    return _run_7z(seven, space, words, archive, total, workers, emitter, stop, target)



# ---------------------------------------------------------------------------
# 自动暴力破解阶梯（无需用户选择密码格式）
# ---------------------------------------------------------------------------
LOWER = "abcdefghijklmnopqrstuvwxyz"
UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
DIGITS = "0123456789"
PRINTABLE = "".join(chr(c) for c in range(32, 127))


def builtin_wordlist():
    words = []
    for name in ("builtin_words.txt",):
        p = asset_path(name)
        try:
            with open(p, "r", encoding="utf-8") as f:
                for line in f:
                    w = line.strip()
                    if w:
                        words.append(w)
        except Exception:
            pass
    return words


MIXED = LOWER + DIGITS
_DIGITS_MAX = 16
_MIXED_MAX = 12

_ZH_NAMES = {DIGITS: "纯数字", LOWER: "小写字母", MIXED: "混合",
             PRINTABLE: "全部可打印字符"}
_EN_NAMES = {DIGITS: "Digits", LOWER: "Lowercase", MIXED: "Mixed",
             PRINTABLE: "Printable ASCII"}


def _stage_max_len(charset, lo, limit, abs_max):
    """在给定候选预算内，该字符集从 lo 位起能跑到多少位。"""
    if limit <= 0:
        return lo - 1
    base = len(charset)
    total = 0
    p = 1
    hi = lo - 1
    for L in range(1, abs_max + 1):
        p *= base
        if L < lo:
            continue
        total += p
        if total > limit:
            break
        hi = L
    return hi


def _cum_sums(base, abs_max):
    out = [0]
    total = 0
    p = 1
    for _ in range(abs_max):
        p *= base
        total += p
        out.append(total)
    return out


def _pair_under(rate, seconds, digits_abs=_DIGITS_MAX, mixed_abs=_MIXED_MAX):
    """自动 2 分钟档专用：选总预计严格小于目标的组合，尽量多覆盖。"""
    if not rate or rate <= 0 or seconds <= 0:
        return 0, 0
    target = rate * seconds
    dcum = _cum_sums(len(DIGITS), digits_abs)
    mcum = _cum_sums(len(MIXED), mixed_abs)
    best = None
    for d in range(digits_abs + 1):
        for m in range(mixed_abs + 1):
            if d == 0 or m == 0:
                continue
            total = dcum[d] + mcum[m]
            if total >= target:
                continue
            if best is None or total > best[0]:
                best = (total, d, m)
    if best is None:
        return _nearest_pair(rate, seconds, digits_abs, mixed_abs)
    return best[1], best[2]


def _nearest_pair(rate, seconds, digits_abs=_DIGITS_MAX, mixed_abs=_MIXED_MAX):
    """数字/混合各取“向下/向上一位”，选总预计最接近目标的那一组。"""
    if not rate or rate <= 0 or seconds <= 0:
        return 0, 0
    target = rate * seconds
    floor_d = _stage_max_len(DIGITS, 1, target, digits_abs)
    floor_m = _stage_max_len(MIXED, 1, target, mixed_abs)
    options_d = {floor_d}
    options_m = {floor_m}
    if floor_d < digits_abs:
        options_d.add(floor_d + 1)
    if floor_m < mixed_abs:
        options_m.add(floor_m + 1)
    dcum = _cum_sums(len(DIGITS), digits_abs)
    mcum = _cum_sums(len(MIXED), mixed_abs)
    best = None
    for d in sorted(options_d):
        for m in sorted(options_m):
            total = dcum[d] + mcum[m]
            diff = abs(total - target)
            if best is None or diff < best[0] or (diff == best[0] and total > best[1]):
                best = (diff, total, d, m)
    return best[2], best[3]


def _space_stage(charset, lo, hi, zh, en, **kwargs):
    if hi < lo:
        return None
    stage = {"type": "space", "charset": charset, "minlen": lo, "maxlen": hi,
             "label_zh": zh, "label_en": en}
    stage.update(kwargs)
    return stage


def build_stages(attack="auto", expect=120, digits_max=None, mixed_max=None,
                 charset=None, minlen=1, maxlen=8, wordlist=None, rate=0,
                 unlimited=False):
    """构造破解阶段。

    auto     ：字典 → 纯数字 → 混合（字母+数字），长度按期望时间/手填值
    dict     ：只跑字典
    space    ：自定义字符集
    unlimited：字典后按 1 位数字、2 位数字、1 位混合、3/4 位数字、2 位混合… 交替
    """
    words = load_wordlist(wordlist) if wordlist else builtin_wordlist()
    stages = [{
        "type": "dict",
        "words": words,
        "label_zh": "常见密码字典 (%d 条)" % len(words),
        "label_en": "Password dictionary (%d words)" % len(words),
    }]
    if attack == "dict":
        return stages
    if attack == "space":
        stage = _space_stage(charset or DIGITS, int(minlen), int(maxlen),
                             "自定义字符集 %d–%d 位" % (int(minlen), int(maxlen)),
                             "Custom charset %d-%d" % (int(minlen), int(maxlen)))
        if stage is None:
            raise RuntimeError("长度范围无效")
        stages.append(stage)
        return stages

    if unlimited:
        n = 1
        while True:
            added = False
            for L in (2 * n - 1, 2 * n):
                if L <= _DIGITS_MAX:
                    stages.append(_space_stage(
                        DIGITS, L, L, "纯数字 %d 位" % L, "Digits %d" % L,
                        unlimited=True))
                    added = True
            if n <= _MIXED_MAX:
                stages.append(_space_stage(
                    MIXED, n, n, "混合 %d 位" % n, "Mixed %d" % n,
                    dedupe_digits=True, unlimited=True))
                added = True
            if not added:
                break
            n += 1
        return stages

    if digits_max is None or mixed_max is None:
        if expect and abs(float(expect) - 120.0) < 1e-6:
            d, m = _pair_under(rate, expect)
        else:
            d, m = _nearest_pair(rate, expect or 0)
        if rate and rate > 0:
            if digits_max is None:
                digits_max = d
            if mixed_max is None:
                mixed_max = m
        else:
            if digits_max is None:
                digits_max = 6
            if mixed_max is None:
                mixed_max = 4
    digits_max = max(0, min(int(digits_max), _DIGITS_MAX))
    mixed_max = max(0, min(int(mixed_max), _MIXED_MAX))
    if digits_max >= 1:
        stages.append(_space_stage(DIGITS, 1, digits_max,
                                   "纯数字 1–%d 位" % digits_max,
                                   "Digits (1-%d)" % digits_max))
    if mixed_max >= 1:
        stages.append(_space_stage(MIXED, 1, mixed_max,
                                   "混合 1–%d 位" % mixed_max,
                                   "Mixed (1-%d)" % mixed_max))
    return stages


def stage_total(stage):
    if stage["type"] == "dict":
        return len(stage["words"])
    base = len(stage["charset"])
    return sum(base ** L for L in range(stage["minlen"], stage["maxlen"] + 1))


def _split_zip_gpu_stages(stages, split=8):
    """ZIP 的 CUDA/OpenCL 内核最长支持 8 位；更长的部分拆成 CPU 阶段。"""
    out = []
    for st in stages:
        if st.get("type") != "space" or st["maxlen"] <= split:
            out.append(st)
            continue
        zh = _ZH_NAMES.get(st["charset"], "字符")
        en = _EN_NAMES.get(st["charset"], "Chars")
        if st["minlen"] <= split:
            gpu = dict(st)
            gpu["maxlen"] = split
            gpu["label_zh"] = "%s %d–%d 位（GPU）" % (zh, st["minlen"], split)
            gpu["label_en"] = "%s (%d-%d, GPU)" % (en, st["minlen"], split)
            out.append(gpu)
        cpu = dict(st)
        cpu["minlen"] = max(split + 1, st["minlen"])
        cpu["label_zh"] = "%s %d–%d 位（CPU）" % (zh, cpu["minlen"], st["maxlen"])
        cpu["label_en"] = "%s (%d-%d, CPU)" % (en, cpu["minlen"], st["maxlen"])
        out.append(cpu)
    return out


def _search_rate(kind, plan, prefer, gpu, hashcat_job=None):
    """估算当前格式/引擎的候选速度（用于期望时间换算长度）。"""
    if hashcat_job is not None and prefer != "cpu":
        try:
            import capability
            rate = capability.hashcat_rate(hashcat_job.mode)
            if rate:
                return float(rate)
        except Exception:
            pass
        return None
    if kind == "zip" and plan is not None and plan.targets:
        st = _SELFTEST_RESULT or {}
        if (prefer != "cpu" and gpu is not None and len(plan.targets) >= 2
                and plan.verify is not None
                and st.get("backend") in ("cuda", "opencl") and st.get("rate")):
            return float(st["rate"])
        return 1.2e8
    return 240.0


def run_auto_search(opts, emit, stop):
    """自动/字典/自定义字符集破解。"""
    t0 = time.time()
    archive = os.path.abspath(opts["archive"])
    if not os.path.isfile(archive):
        raise RuntimeError("压缩包不存在：%s" % archive)
    seven = SevenZip()
    if not seven.available:
        raise RuntimeError("找不到 7z.exe（安装包不完整）")

    emitter = Emitter(emit)
    emitter.t0 = t0
    emit({"type": "start", "archive": archive})

    # ---- 格式识别（支持 7-Zip 能打开的各种格式）----
    kind = detect_kind(archive)
    if kind is None:
        entries = seven.list(archive)
        if entries is None:
            rc, out = seven.probe_verbose(archive)
            text = out.decode("utf-8", "replace").lower()
            if "wrong password" in text or "password" in text:
                kind = "other"
            elif "everything is ok" in text or rc == 0:
                return {"found": False, "password": None, "reason": "not_encrypted",
                        "attempts": 0, "elapsed": time.time() - t0}
            else:
                raise RuntimeError("7-Zip 无法打开这个文件，可能不是受支持的压缩包")
        else:
            kind = "other"

    if not seven.is_encrypted(archive):
        return {"found": False, "password": None, "reason": "not_encrypted",
                "attempts": 0, "elapsed": time.time() - t0}

    plan = prepare_zip(archive) if kind == "zip" else None
    native = NativeZip()
    gpu = gpu_backend()
    gpu_mod = None
    gpu_dev = gpu.dev if gpu is not None else None

    # 非 ZipCrypto 的 KDF 格式（AES-ZIP / 7z / RAR5）交给 hashcat 在 GPU 上跑
    prefer = opts.get("engine", "auto")
    hashcat_job = None
    if prefer != "cpu" and kind in ("zip", "7z", "rar"):
        try:
            import hashcat_gpu
            info = hashcat_gpu.detect(archive, kind)
            if info is not None:
                emit({"type": "log",
                      "text": "检测到 %s，正在准备 GPU 引擎（hashcat）…" % info["label"],
                      "en": "Detected %s, preparing GPU engine (hashcat)…" % info["label"]})
                if hashcat_gpu.available(extract=True):
                    hashcat_job = hashcat_gpu.HashcatJob(info, archive)
                else:
                    emit({"type": "log",
                          "text": "hashcat 不可用（%s），改用 7-Zip CPU 校验"
                                  % (hashcat_gpu.probe_error() or "未知原因"),
                          "en": "hashcat unavailable, falling back to CPU verification"})
        except Exception:
            hashcat_job = None

    fast = hashcat_job is not None
    if kind == "zip" and plan is not None and plan.targets and plan.verify:
        fast = native.available or (gpu is not None) or hashcat_job is not None

    attack = opts.get("attack", "auto")
    custom_charset = opts.get("charset") or ""
    try:
        amin = max(1, int(opts.get("minlen") or 1))
        amax = min(20, max(amin, int(opts.get("maxlen") or 8)))
    except Exception:
        amin, amax = 1, 8
    wordlist = opts.get("wordlist")

    rate = _search_rate(kind, plan, prefer, gpu, hashcat_job)
    expect = opts.get("expect")
    unlimited = bool(opts.get("unlimited")) and attack == "auto"
    if unlimited:
        expect = 0
    else:
        try:
            expect = float(expect) if expect is not None else 120.0
        except Exception:
            expect = 120.0
    stages = build_stages(attack=attack,
                          expect=float(expect),
                          digits_max=opts.get("digits_max"),
                          mixed_max=opts.get("mixed_max"),
                          charset=custom_charset, minlen=amin, maxlen=amax,
                          wordlist=wordlist, rate=rate or 0,
                          unlimited=unlimited)
    gpu_zip = (kind == "zip" and plan is not None and plan.targets
               and len(plan.targets) >= 2 and plan.verify
               and prefer != "cpu" and gpu is not None)
    if gpu_zip and attack == "auto":
        if unlimited:
            if any(s.get("type") == "space" and s["maxlen"] > 8 for s in stages):
                stages = _split_zip_gpu_stages(stages)
                emit({"type": "log",
                      "text": "GPU 内核最长 8 位，超过的部分拆成 CPU 阶段（速度会慢很多）",
                      "en": "GPU kernel supports up to 8 chars; longer parts run on CPU"})
        else:
            capped = False
            for st in stages:
                if st.get("type") != "space" or st["maxlen"] <= 8:
                    continue
                st["maxlen"] = 8
                st["label_zh"] = "%s %d–8 位" % (
                    _ZH_NAMES.get(st["charset"], "字符"), st["minlen"])
                st["label_en"] = "%s (%d-8)" % (
                    _EN_NAMES.get(st["charset"], "Chars"), st["minlen"])
                capped = True
            if capped:
                emit({"type": "log",
                      "text": "ZIP 传统加密的 GPU 内核最多 8 位，更长的长度没有加入本次自动范围",
                      "en": "ZipCrypto GPU kernel is limited to 8 chars; longer lengths skipped"})

    grand = sum(stage_total(s) for s in stages)
    emit({"type": "space", "total": grand, "unlimited": unlimited})
    if unlimited:
        emit({"type": "log",
              "text": "无限模式：字典后按 1/2 位数字、1 位混合、3/4 位数字、2 位混合… 交替，"
                      "直到数字 %d 位 / 混合 %d 位" % (_DIGITS_MAX, _MIXED_MAX),
              "en": "Unlimited: digits 1-2, mixed 1, digits 3-4, mixed 2… "
                    "up to digits %d / mixed %d" % (_DIGITS_MAX, _MIXED_MAX)})
    else:
        emit({"type": "log",
              "text": "候选总数：%s（分 %d 个阶段）" % (fmt_num(grand), len(stages)),
              "en": "Total candidates: %s in %d stages" % (fmt_num(grand), len(stages))})
    if rate and grand and not unlimited:
        emit({"type": "log",
              "text": "当前速度约 %s；预计全部跑完约 %s"
                      % (fmt_rate(rate), fmt_eta(grand / rate)),
              "en": "Estimated %s, ETA %s" % (fmt_rate(rate), fmt_eta(grand / rate))})
    if attack == "auto" and not unlimited:
        parts_zh = []
        parts_en = []
        for stage in stages:
            if stage["type"] != "space":
                continue
            hi = stage["maxlen"]
            parts_zh.append("%s %d 位" % (_ZH_NAMES.get(stage["charset"], "字符"), hi))
            parts_en.append("%s %d" % (_EN_NAMES.get(stage["charset"], "Chars"), hi))
        emit({"type": "log",
              "text": "目标时间 %s：%s（字典之后按顺序跑）"
                      % (fmt_eta(expect), "，".join(parts_zh)),
              "en": "Target %s: %s after the dictionary" % (fmt_eta(expect),
                                                            ", ".join(parts_en))})
    if hashcat_job is not None:
        emitter.engine("GPU · hashcat（%s）" % hashcat_job.info["label"],
                       en="GPU · hashcat (%s)" % hashcat_job.info["label"])
        emitter.log("hashcat 模式：%s → -m %d" % (hashcat_job.info["label"],
                                                 hashcat_job.mode))
    if prefer == "gpu" and hashcat_job is None and not (kind == "zip" and plan and plan.targets):
        if kind == "rar":
            emitter.log("RAR3 / 旧 RAR 暂时没有 GPU 哈希提取，使用 7-Zip CPU 校验",
                        en="No GPU hash extraction for RAR3/old RAR; using 7-Zip CPU")
        else:
            emitter.log("该格式暂时没有 GPU 引擎，使用 7-Zip CPU 校验（选 GPU 也不会换后端）",
                        en="No GPU engine for this format; using 7-Zip CPU verification")
    if not fast:
        emit({"type": "log",
              "text": "当前只能逐候选调用 7-Zip 校验（较慢）",
              "en": "7-Zip per-candidate verification (slow)"})

    workers = max(1, min(64, int(opts.get("workers") or default_workers())))
    target = seven.pick_target(archive, kind) if not (kind == "zip" and plan and plan.targets) else None
    completed = 0
    total_attempts = 0

    for si, stage in enumerate(stages):
        if stop.is_set():
            break
        st = stage_total(stage)
        emitter.set_scope(completed, grand, stage["label_zh"], stage["label_en"],
                          si + 1, len(stages))
        emit({"type": "stage", "index": si + 1, "count": len(stages),
              "label_zh": stage["label_zh"], "label_en": stage["label_en"]})
        if stage.get("unlimited"):
            emitter.log(stage["label_zh"], en=stage["label_en"])
        elif unlimited and stage["type"] == "dict":
            emitter.log("常见密码字典", en="Password dictionary")
        else:
            emitter.log("阶段 %d/%d · %s（%s 个候选）" % (
                si + 1, len(stages), stage["label_zh"], fmt_num(st)),
                en="Stage %d/%d · %s (%s candidates)" % (
                    si + 1, len(stages), stage["label_en"], fmt_num(st)))
        res = _dispatch_stage(stage, kind, plan, archive, seven, native, gpu,
                              prefer, workers, target, emitter, stop, hashcat_job)
        completed += st
        total_attempts = completed
        if res.get("reason") == "error":
            raise RuntimeError(res.get("message") or "7-Zip 校验失败")
        if res.get("found"):
            res["attempts"] = emitter.base + int(res.get("attempts", 0))
            res["elapsed"] = time.time() - t0
            return res
        if res.get("reason") == "stopped":
            res["attempts"] = completed - st + int(res.get("attempts", 0))
            res["elapsed"] = time.time() - t0
            return res

    if stop.is_set():
        return {"found": False, "password": None, "reason": "stopped",
                "attempts": total_attempts, "elapsed": time.time() - t0}
    return {"found": False, "password": None, "reason": "exhausted",
            "attempts": grand, "elapsed": time.time() - t0}


def _run_hashcat_stage(job, stage, space, total, emitter, stop):
    """用 hashcat 跑一个字符集阶段。"""
    total = int(total or stage_total(stage))
    status, password, attempts = job.run_stage(stage, total, emitter, stop)
    if status == "found":
        attempts = int(attempts or total)
        emitter.progress(attempts, force=True)
        emitter.found(password, attempts)
        return {"found": True, "password": password, "reason": "found",
                "attempts": attempts, "elapsed": time.time() - emitter.t0}
    if status == "stopped":
        return {"found": False, "password": None, "reason": "stopped",
                "attempts": int(attempts or 0), "elapsed": time.time() - emitter.t0}
    if status == "exhausted":
        emitter.progress(total, force=True)
        return {"found": False, "password": None, "reason": "exhausted",
                "attempts": total, "elapsed": time.time() - emitter.t0}
    raise RuntimeError("hashcat 阶段失败：%s" % status)


def _run_hashcat_words(job, words, emitter, stop):
    """字典阶段也交给 hashcat，省得逐个候选开 7z.exe。"""
    total = len(words)
    status, password, _attempts = job.run_words(words, emitter, stop)
    if status == "found":
        emitter.progress(total, force=True)
        emitter.found(password, total)
        return {"found": True, "password": password, "reason": "found",
                "attempts": total, "elapsed": time.time() - emitter.t0}
    if status == "stopped":
        return {"found": False, "password": None, "reason": "stopped",
                "attempts": 0, "elapsed": time.time() - emitter.t0}
    if status == "exhausted":
        emitter.progress(total, force=True)
        return {"found": False, "password": None, "reason": "exhausted",
                "attempts": total, "elapsed": time.time() - emitter.t0}
    raise RuntimeError("hashcat 字典阶段失败：%s" % status)


def _dispatch_stage(stage, kind, plan, archive, seven, native, gpu,
                    prefer, workers, target, emitter, stop, hashcat_job=None):
    is_zip_native = kind == "zip" and plan is not None and plan.targets and plan.verify
    if stage["type"] == "dict":
        words = stage["words"]
        if hashcat_job is not None:
            try:
                return _run_hashcat_words(hashcat_job, words, emitter, stop)
            except Exception as e:
                emitter.log("GPU（hashcat）字典阶段失败：%s，改用 CPU 校验" % e,
                            en="GPU (hashcat) dictionary stage failed: %s, CPU fallback" % e)
        if is_zip_native and native.available:
            blob, offsets = build_words_blob(words)
            return _run_native_zip(native, plan, archive, None, blob, offsets,
                                   len(words), workers, emitter, stop)
        return _run_7z(seven, None, words, archive, len(words), workers, emitter, stop,
                       target, emit_engine=(hashcat_job is None))

    space = Space(stage["charset"], stage["minlen"], stage["maxlen"])
    total = space.total
    if hashcat_job is not None:
        try:
            return _run_hashcat_stage(hashcat_job, stage, space, total, emitter, stop)
        except Exception as e:
            emitter.log("GPU（hashcat）阶段失败：%s，改用 7-Zip（CPU）" % e,
                        en="GPU (hashcat) stage failed: %s, falling back to CPU" % e)
    if (is_zip_native and space.max_len > 8 and prefer != "cpu"
            and gpu is not None and len(plan.targets) >= 2):
        emitter.log("该阶段超过 8 位（GPU 内核上限），改用 CPU 原生引擎",
                    en="Stage exceeds the 8-char GPU kernel limit, using CPU engine")
    if is_zip_native:
        use_gpu = (prefer != "cpu" and gpu is not None and gpu.supports(space)
                   and plan.verify is not None and len(plan.targets) >= 2)
        if use_gpu:
            try:
                return _run_gpu_zip(gpu, native, plan, archive, space, total, emitter, stop)
            except Exception as e:
                emitter.log("GPU 不可用：%s，改用 CPU" % e,
                            en="GPU unavailable: %s, falling back to CPU" % e)
                fb = gpu_backend_fallback(gpu)
                if fb is not None and fb.supports(space):
                    try:
                        emitter.log("尝试 OpenCL 后端…", en="Trying the OpenCL backend…")
                        return _run_gpu_zip(fb, native, plan, archive, space, total,
                                            emitter, stop)
                    except Exception as e2:
                        emitter.log("OpenCL 也不可用：%s，改用 CPU" % e2,
                                    en="OpenCL unavailable too: %s, falling back to CPU" % e2)
        if native.available and space.ascii_ok:
            return _run_native_zip(native, plan, archive, space, None, None,
                                   total, workers, emitter, stop)
        if plan.verify is None:
            emitter.log("该压缩包缺少可用于校验的文件，改用 7-Zip",
                        en="No verifiable entry, falling back to 7-Zip")
    return _run_7z(seven, space, None, archive, total, workers, emitter, stop, target)