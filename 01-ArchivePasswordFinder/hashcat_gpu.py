# -*- coding: utf-8 -*-
"""hashcat GPU 引擎：AES-ZIP、7z 这类 KDF 重的格式交给 hashcat 在显卡上跑。

hashcat 运行包随程序携带，第一次用到时解压到 %LOCALAPPDATA%\\ArchivePassFinder\\ 并复用。
只使用 OpenCL 后端：各家驱动的 OpenCL 编译器随驱动提供，不需要 CUDA Toolkit / HIP SDK。
"""
import mmap
import os
import re
import subprocess
import tempfile
import threading
import time

import core

HASHCAT_VERSION = "8.0.0"
HASHCAT_PACK = "hashcat-8.0.0.7z"
HASHCAT_MODE_ZIP_AES = 13600
HASHCAT_MODE_7Z = 11600
HASHCAT_MODE_RAR5 = 13000
_PER_LENGTH_MODES = (HASHCAT_MODE_7Z, HASHCAT_MODE_RAR5)

_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_BACKEND_FLAGS = ["--backend-ignore-cuda", "--backend-ignore-hip"]
_PROBE = None
_PROBE_ERROR = None
_PROBE_DEVICE = None
_PROBE_DEVICES = []

_RATE_UNITS = {"h/s": 1.0, "kh/s": 1e3, "mh/s": 1e6, "gh/s": 1e9, "th/s": 1e12}


# ---------------------------------------------------------------------------
# 路径与运行包
# ---------------------------------------------------------------------------
def _local_appdata():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "ArchivePassFinder")


def _pack_path():
    return core.asset_path("hashcat", HASHCAT_PACK)


def _seven_zip():
    return core.asset_path("7z.exe")


def _rmtree(path):
    import shutil
    shutil.rmtree(path, ignore_errors=True)


def hashcat_dir(extract=True):
    target = os.path.join(_local_appdata(), "hashcat-%s" % HASHCAT_VERSION)
    exe = os.path.join(target, "hashcat.exe")
    if os.path.isfile(exe):
        return target
    if not extract:
        return None
    pack = _pack_path()
    seven = _seven_zip()
    if not os.path.isfile(pack) or not os.path.isfile(seven):
        return None
    tmp = target + ".tmp-%d" % os.getpid()
    try:
        if os.path.isdir(tmp):
            _rmtree(tmp)
        os.makedirs(tmp, exist_ok=True)
        r = subprocess.run([seven, "x", "-y", "-bd", "-o" + tmp, pack],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=600, creationflags=_CREATE_NO_WINDOW)
        if r.returncode not in (0, 1):
            return None
        inner = os.path.join(tmp, "hashcat-%s" % HASHCAT_VERSION)
        src = inner if os.path.isdir(inner) else tmp
        if os.path.isdir(target):
            _rmtree(target)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        os.rename(src, target)
    except Exception:
        return None
    finally:
        if os.path.isdir(tmp):
            _rmtree(tmp)
    return target if os.path.isfile(os.path.join(target, "hashcat.exe")) else None


def _hashcat_exe(extract=True):
    d = hashcat_dir(extract=extract)
    return os.path.join(d, "hashcat.exe") if d else None


# ---------------------------------------------------------------------------
# 设备探测
# ---------------------------------------------------------------------------
def _parse_devices(text):
    devices = []
    cur = None
    for line in text.splitlines():
        s = line.strip()
        m = re.match(r"Backend Device ID #(\d+)", s)
        if m:
            cur = {"id": int(m.group(1)), "type": "", "vendor": "", "name": "", "mem": 0}
            devices.append(cur)
            continue
        if cur is None:
            continue
        m = re.search(r"Type\s*\.+:\s*(\w+)", s)
        if m:
            cur["type"] = m.group(1)
            continue
        m = re.search(r"Vendor\s*\.+:\s*(.+)", s)
        if m and not cur["vendor"]:
            cur["vendor"] = m.group(1).strip()
            continue
        m = re.search(r"Name\s*\.+:\s*(.+)", s)
        if m and not cur["name"]:
            cur["name"] = m.group(1).strip()
            continue
        m = re.search(r"Memory\.Total\s*\.+:\s*(\d+)\s*MB", s)
        if m:
            cur["mem"] = int(m.group(1))
    return [d for d in devices if d.get("type", "").upper() == "GPU"]


def _device_score(dev):
    vendor = (dev.get("vendor") or "").lower()
    if "nvidia" in vendor:
        tier = 3
    elif "amd" in vendor or "advanced micro" in vendor:
        tier = 2
    elif "intel" in vendor:
        tier = 1
    else:
        tier = 0
    return (tier, dev.get("mem", 0))


def available(extract=True):
    """是否有 hashcat + 可用 GPU；结果进程内缓存。"""
    global _PROBE, _PROBE_ERROR, _PROBE_DEVICE, _PROBE_DEVICES
    if _PROBE is not None:
        return _PROBE
    if _PROBE_ERROR is not None:
        return False
    exe = _hashcat_exe(extract=extract)
    if not exe:
        _PROBE_ERROR = "缺少 hashcat 运行包"
        return False
    try:
        r = subprocess.run([exe, "-I"] + _BACKEND_FLAGS, cwd=os.path.dirname(exe),
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           timeout=120, creationflags=_CREATE_NO_WINDOW)
        text = (r.stdout or b"").decode("utf-8", "replace")
        devices = _parse_devices(text)
        if not devices:
            _PROBE_ERROR = "hashcat 没有检测到 GPU"
            return False
        devices.sort(key=_device_score, reverse=True)
        _PROBE_DEVICES = devices
        _PROBE_DEVICE = devices[0]
        _PROBE = True
        return True
    except Exception as e:
        _PROBE_ERROR = str(e)
        return False


def probe_error():
    return _PROBE_ERROR


def device_name():
    return (_PROBE_DEVICE or {}).get("name") or ""


def device_args():
    dev = _PROBE_DEVICE
    if not dev:
        return []
    return ["-d", str(dev["id"])]


def _disable_device_selection():
    global _PROBE_DEVICE
    _PROBE_DEVICE = None


# ---------------------------------------------------------------------------
# 哈希提取
# ---------------------------------------------------------------------------
def zip_aes_hash(path, max_data=4 * 1024 * 1024):
    """从 WinZip AES 加密的 ZIP 里提取 $zip2$ 哈希（取压缩数据最小的 AES 条目）。"""
    import struct

    best = None
    with open(path, "rb") as f:
        with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as data:
            size = len(data)
            pos = 0
            while pos + 30 <= size:
                if data[pos:pos + 4] != b"PK\x03\x04":
                    nxt = data.find(b"PK\x03\x04", pos)
                    if nxt < 0:
                        break
                    pos = nxt
                    continue
                (sig, ver, flags, method, mtime, mdate, crc, csize, usize,
                 nlen, elen) = struct.unpack_from("<IHHHHHIIIHH", data, pos)
                name = bytes(data[pos + 30:pos + 30 + nlen])
                extra = bytes(data[pos + 30 + nlen:pos + 30 + nlen + elen])
                body = pos + 30 + nlen + elen
                if method == 99 and csize:
                    strength = None
                    ep = 0
                    while ep + 4 <= len(extra):
                        hid, hsz = struct.unpack_from("<HH", extra, ep)
                        body_ep = ep + 4
                        if hid == 0x9901 and hsz >= 7 and body_ep + 7 <= len(extra):
                            strength = extra[body_ep + 4]
                            break
                        ep += 4 + hsz
                    if strength and 1 <= strength <= 3:
                        salt_len = 4 + 4 * strength
                        enc_len = csize - salt_len - 2 - 10
                        if (enc_len > 0 and enc_len <= max_data
                                and body + csize <= size):
                            cand = (enc_len, name, strength,
                                    bytes(data[body:body + salt_len]),
                                    bytes(data[body + salt_len:body + salt_len + 2]),
                                    bytes(data[body + salt_len + 2:
                                              body + salt_len + 2 + enc_len]),
                                    bytes(data[body + csize - 10:body + csize]))
                            if best is None or cand[0] < best[0]:
                                best = cand
                if csize:
                    pos = body + csize
                else:
                    nxt = data.find(b"PK\x03\x04", body)
                    if nxt < 0:
                        break
                    pos = nxt
    if best is None:
        return None
    enc_len, name, strength, salt, verify, encrypted, auth = best
    h = "$zip2$*0*%x*0*%s*%s*%x*%s*%s*$/zip2$" % (
        strength, salt.hex(), verify.hex(), enc_len, encrypted.hex(), auth.hex())
    bits = {1: 128, 2: 192, 3: 256}.get(strength, strength * 64)
    return {"mode": HASHCAT_MODE_ZIP_AES, "hash": h,
            "label": "WinZip AES-%d" % bits,
            "file": name.decode("utf-8", "replace")}


def _seven_zip_hash_tool():
    return core.asset_path("hashcat", "7z2hashcat64-2.0.exe")


def sevenzip_hash(path):
    tool = _seven_zip_hash_tool()
    if not os.path.isfile(tool):
        return None
    try:
        r = subprocess.run([tool, path], stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, timeout=180,
                           creationflags=_CREATE_NO_WINDOW)
    except Exception:
        return None
    text = (r.stdout or b"").decode("utf-8", "replace")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip().startswith("$7z$")]
    if not lines:
        return None
    return {"mode": HASHCAT_MODE_7Z, "hash": lines[0], "label": "7z (AES-256)"}


# ---------------------------------------------------------------------------
# RAR5 哈希提取（从 RAR5 文件头的加密记录里读 salt / IV / PswCheck）
# ---------------------------------------------------------------------------
_RAR5_MAGIC = b"Rar!\x1a\x07\x01\x00"
_RAR5_FILE = 2
_RAR5_SERVICE = 3
_RAR5_CRYPT = 4
_RAR5_ENDARC = 5
_RAR5_HFL_EXTRA = 1
_RAR5_HFL_DATA = 2
_RAR5_FHFL_UTIME = 2
_RAR5_FHFL_CRC32 = 4
_RAR5_FHEXTRA_CRYPT = 1


def _vint(buf, pos):
    n = 0
    shift = 0
    for _ in range(10):
        if pos >= len(buf):
            return None, pos
        c = buf[pos]
        pos += 1
        n |= (c & 0x7F) << shift
        shift += 7
        if not (c & 0x80):
            return n, pos
    return None, pos


def _rar5_parse_extra(data, epos, end):
    while epos < end:
        fsize, epos = _vint(data, epos)
        if fsize is None or fsize <= 0:
            return None
        ftype, epos = _vint(data, epos)
        if ftype is None:
            return None
        body = epos
        if ftype == _RAR5_FHEXTRA_CRYPT:
            ver, epos = _vint(data, epos)
            flags, epos = _vint(data, epos)
            if ver is None or flags is None or epos + 1 + 16 + 16 + 8 > end:
                return None
            lg2 = data[epos]
            epos += 1
            salt = data[epos:epos + 16]
            epos += 16
            iv = data[epos:epos + 16]
            epos += 16
            psw = data[epos:epos + 8]
            return {
                "mode": HASHCAT_MODE_RAR5,
                "hash": "$rar5$16$%s$%d$%s$8$%s" % (
                    salt.hex(), lg2, iv.hex(), psw.hex()),
                "label": "RAR5 (AES-256)",
            }
        epos = body + fsize
    return None


def rar5_hash(path, max_size=512 * 1024 * 1024):
    """从 RAR5 文件头里提取 hashcat $rar5$ 哈希；RAR3 / headers 不支持时返回 None。"""
    try:
        if os.path.getsize(path) > max_size:
            return None
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return None
    pos = data.find(_RAR5_MAGIC)
    if pos < 0:
        return None
    pos += len(_RAR5_MAGIC)
    encrypted = False
    salt = None
    lg2 = 0
    pswcheck = b"\x00" * 8
    while pos + 4 <= len(data):
        cur = pos
        if encrypted:
            iv = data[pos:pos + 16]
            if len(iv) != 16 or salt is None:
                return None
            return {
                "mode": HASHCAT_MODE_RAR5,
                "hash": "$rar5$16$%s$%d$%s$8$%s" % (
                    salt.hex(), lg2, iv.hex(), pswcheck.hex()),
                "label": "RAR5 (headers)",
            }
        pos += 4  # header CRC
        start = pos
        block_size, pos = _vint(data, pos)
        if block_size is None:
            return None
        size_len = pos - start
        if pos >= len(data):
            return None
        header_type = data[pos]
        pos += 1
        flags, pos = _vint(data, pos)
        if flags is None:
            return None
        extra_size = 0
        data_size = 0
        if flags & _RAR5_HFL_EXTRA:
            extra_size, pos = _vint(data, pos)
        if flags & _RAR5_HFL_DATA:
            data_size, pos = _vint(data, pos)
        if extra_size is None or data_size is None:
            return None
        head_size = block_size + 4 + size_len
        next_pos = cur + head_size + data_size
        if header_type == _RAR5_CRYPT:
            ver, pos = _vint(data, pos)
            eflags, pos = _vint(data, pos)
            if ver is None or eflags is None or pos + 1 + 16 > len(data):
                return None
            lg2 = data[pos]
            pos += 1
            salt = data[pos:pos + 16]
            pos += 16
            if eflags & 1:
                pswcheck = data[pos:pos + 8]
                pos += 12
            encrypted = True
        elif header_type in (_RAR5_FILE, _RAR5_SERVICE):
            fflags, pos = _vint(data, pos)
            unpsize, pos = _vint(data, pos)
            fattr, pos = _vint(data, pos)
            if fflags is None or unpsize is None or fattr is None:
                return None
            if fflags & _RAR5_FHFL_UTIME:
                pos += 4
            if fflags & _RAR5_FHFL_CRC32:
                pos += 4
            compinfo, pos = _vint(data, pos)
            hostos, pos = _vint(data, pos)
            namesize, pos = _vint(data, pos)
            if None in (compinfo, hostos, namesize):
                return None
            name = data[pos:pos + namesize]
            pos += namesize
            if extra_size:
                end = cur + head_size
                info = _rar5_parse_extra(data, end - extra_size, end)
                if info is None:
                    info = _rar5_parse_extra(data, pos, end)
                if info:
                    info["file"] = name.decode("utf-8", "replace")
                    return info
        elif header_type == _RAR5_ENDARC:
            break
        pos = next_pos
    return None


def detect(archive, kind):
    try:
        if kind == "zip":
            return zip_aes_hash(archive)
        if kind == "7z":
            return sevenzip_hash(archive)
        if kind == "rar":
            return rar5_hash(archive)
    except Exception:
        return None
    return None


# ---------------------------------------------------------------------------
# 字符集 → hashcat mask
# ---------------------------------------------------------------------------
_UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_ALNUM = core.LOWER + core.DIGITS


def charset_spec(charset, minlen, maxlen):
    """返回 (mask, 额外参数, 每字符集大小) 或 None。

    只接受能精确映射到 hashcat 内建字符集/自定义字符集的 ASCII 字符集。
    """
    if not charset or len(set(charset)) != len(charset):
        return None
    if charset == core.DIGITS:
        return "?d", [], 10
    if charset == core.LOWER:
        return "?l", [], 26
    if charset == _UPPER:
        return "?u", [], 26
    if charset == core.LOWER + _UPPER:
        return "?1", ["-1", "?l?u"], 52
    if charset == _ALNUM:
        return "?1", ["-1", "?l?d"], 36
    if charset == core.LOWER + _UPPER + core.DIGITS:
        return "?1", ["-1", "?l?u?d"], 62
    if charset == core.PRINTABLE:
        return "?a", [], 95
    if not all(32 <= ord(c) < 127 for c in charset):
        return None
    # 自定义字符集：按字面量传给 -1，转义 hashcat 的 ? 与 \
    lit = "".join(("\\" + c) if c in "?\\" else c for c in charset)
    return "?1", ["-1", lit], len(charset)


def _parse_rate(text):
    m = re.search(r"Speed\.#\d+\.+:\s*([\d.]+)\s*([kKmMgGtT]?[hH]/s)", text)
    if not m:
        return None
    try:
        return float(m.group(1)) * _RATE_UNITS.get(m.group(2).lower(), 1.0)
    except Exception:
        return None


def _parse_progress(text):
    m = re.search(r"Progress\.+:\s*(\d+)/(\d+)", text)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


# ---------------------------------------------------------------------------
# 执行
# ---------------------------------------------------------------------------
class HashcatJob:
    def __init__(self, info, archive):
        self.info = info
        self.archive = archive
        self.mode = info["mode"]

    def _verify(self, pw):
        try:
            seven = core.SevenZip()
            return seven.test(self.archive, pw)
        except Exception:
            return False

    def _run_once(self, args, total, emitter, stop, default_total=None,
                  progress_offset=0, progress_total=None):
        """跑一次 hashcat。返回 (status, password, done_equiv, keyspace)。"""
        exe = _hashcat_exe()
        if not exe:
            return ("unavailable", None, 0, 0)
        hc_dir = os.path.dirname(exe)
        tmpdir = tempfile.mkdtemp(prefix="apf_hc_")
        try:
            hash_file = os.path.join(tmpdir, "hash.txt")
            with open(hash_file, "w", encoding="utf-8", newline="\n") as f:
                f.write(self.info["hash"] + "\n")
            out_file = os.path.join(tmpdir, "out.txt")
            cmd = ([exe, "-m", str(self.mode)] +
                   [a.replace("%HASH%", hash_file) for a in args] +
                   ["--potfile-disable", "--outfile", out_file, "--outfile-format=2",
                    "--status", "--status-timer=1", "--quiet"] +
                   _BACKEND_FLAGS + device_args())
            if self.mode in (HASHCAT_MODE_7Z, HASHCAT_MODE_RAR5):
                cmd.append("--keep-guessing")
            proc = subprocess.Popen(cmd, cwd=hc_dir, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                    creationflags=_CREATE_NO_WINDOW)
            verified = [None]
            done_hc = [0, 0]
            stop_seen = [False]

            def pump():
                try:
                    for raw in iter(proc.stdout.readline, b""):
                        for part in re.split(r"[\r\n]+",
                                             raw.decode("utf-8", "replace")):
                            pg = _parse_progress(part.strip())
                            if pg:
                                done_hc[0], done_hc[1] = pg
                except Exception:
                    pass

            reader = threading.Thread(target=pump, daemon=True)
            reader.start()
            last = 0.0
            while proc.poll() is None:
                if stop is not None and stop.is_set():
                    stop_seen[0] = True
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    break
                if os.path.isfile(out_file):
                    try:
                        with open(out_file, "r", encoding="utf-8",
                                  errors="replace") as f:
                            lines = [ln.strip() for ln in f if ln.strip()]
                    except OSError:
                        lines = []
                    for pw in lines:
                        if pw == verified[0]:
                            continue
                        verified[0] = pw
                        if self._verify(pw):
                            try:
                                proc.kill()
                            except Exception:
                                pass
                            break
                now = time.time()
                if now - last >= 0.2 and emitter is not None:
                    last = now
                    if done_hc[1] > 0 and total:
                        ratio = min(1.0, done_hc[0] / done_hc[1])
                        val = progress_offset + int(total * ratio)
                        if progress_total:
                            val = min(progress_total, val)
                        emitter.progress(val)
                time.sleep(0.1)
            try:
                reader.join(timeout=1.0)
            except Exception:
                pass
            try:
                proc.wait(timeout=2.0)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
            keyspace = done_hc[1] or default_total or 0
            done_equiv = progress_offset + (done_hc[0] if done_hc[1] else keyspace)
            if verified[0] and self._verify(verified[0]):
                return ("found", verified[0], done_equiv, keyspace)
            if stop_seen[0] or (stop is not None and stop.is_set()):
                return ("stopped", None, done_equiv, keyspace)
            if proc.returncode in (0, 1):
                return ("exhausted", None, keyspace, keyspace)
            if _PROBE_DEVICE is not None:
                # -d 在少数多显卡机器上可能对不上，退回默认设备集合再试一次
                _disable_device_selection()
                return self._run_once(args, total, emitter, stop,
                                      default_total=default_total,
                                      progress_offset=progress_offset,
                                      progress_total=progress_total)
            return ("error", None, done_equiv, keyspace)
        finally:
            _rmtree(tmpdir)

    # -- 单 mask ----------------------------------------------------------
    def run_stage(self, stage, total, emitter, stop):
        spec = charset_spec(stage["charset"], stage["minlen"], stage["maxlen"])
        if spec is None:
            return ("unsupported", None, 0)
        token, extra, base = spec
        minlen = int(stage["minlen"])
        maxlen = int(stage["maxlen"])
        if stage.get("dedupe_digits") and stage["charset"] == core.LOWER + core.DIGITS:
            return self._run_mixed_dedupe(minlen, maxlen, total, emitter, stop)
        if self.mode in _PER_LENGTH_MODES:
            # 7z / RAR5 用 --increment 会慢很多，改成每个长度单独跑
            return self._run_stage_lengths(token, extra, base, minlen, maxlen,
                                           total, emitter, stop)
        mask = token * maxlen
        args = ["-a", "3"] + extra + [
            "%HASH%", mask,
            "--increment", "--increment-min=%d" % minlen,
            "--increment-max=%d" % maxlen]
        status, pw, done, _keys = self._run_once(args, total, emitter, stop,
                                                 default_total=total)
        if status == "found":
            return ("found", pw, done)
        if status == "stopped":
            return ("stopped", None, total)
        if status == "exhausted":
            return ("exhausted", None, total)
        return (status, None, total)

    def _run_mixed_dedupe(self, minlen, maxlen, total, emitter, stop):
        """字母+数字阶段里排除纯数字：按“第一个字母的位置”拆 mask，精确去重。"""
        offset = 0
        for L in range(minlen, maxlen + 1):
            for k in range(1, L + 1):
                mask = "?d" * (k - 1) + "?l" + "?1" * (L - k)
                keyspace = (10 ** (k - 1)) * 26 * (36 ** (L - k))
                args = ["-a", "3", "-1", "?l?d", "%HASH%", mask]
                status, pw, done, _keys = self._run_once(
                    args, keyspace, emitter, stop, default_total=keyspace,
                    progress_offset=offset, progress_total=total)
                if status in ("found", "stopped", "error", "unavailable"):
                    return (status, pw, done)
                offset += keyspace
        return ("exhausted", None, total)

    def _run_stage_lengths(self, token, extra, base, minlen, maxlen, total,
                           emitter, stop):
        offset = 0
        for L in range(minlen, maxlen + 1):
            keyspace = base ** L
            args = ["-a", "3"] + extra + ["%HASH%", token * L]
            status, pw, _done, _keys = self._run_once(
                args, keyspace, emitter, stop, default_total=keyspace,
                progress_offset=offset, progress_total=total)
            if status in ("found", "stopped", "error", "unavailable"):
                return (status, pw, _done)
            offset += keyspace
        return ("exhausted", None, total)

    # -- 字典 -------------------------------------------------------------
    def run_words(self, words, emitter, stop):
        tmpdir = tempfile.mkdtemp(prefix="apf_hcw_")
        try:
            wl = os.path.join(tmpdir, "words.txt")
            with open(wl, "w", encoding="utf-8", newline="\n") as f:
                for w in words:
                    if w:
                        f.write(w + "\n")
            args = ["-a", "0", "%HASH%", wl]
            status, pw, _done, _keys = self._run_once(args, len(words), emitter, stop,
                                                      default_total=len(words))
            if status == "found":
                return ("found", pw, len(words))
            if status == "stopped":
                return ("stopped", None, 0)
            if status == "exhausted":
                return ("exhausted", None, len(words))
            return (status, None, 0)
        finally:
            _rmtree(tmpdir)


# ---------------------------------------------------------------------------
# 基准测试（给能力评估用）
# ---------------------------------------------------------------------------
def benchmark_modes(modes, timeout=120):
    """跑 hashcat -b，返回 {mode: {"rate": H/s, "iters": N, "device": name}}。"""
    exe = _hashcat_exe()
    if not exe or not available():
        return {}
    hc_dir = os.path.dirname(exe)
    out = {}
    for mode in modes:
        try:
            r = subprocess.run([exe, "-b", "-m", str(mode)] + _BACKEND_FLAGS + device_args(),
                               cwd=hc_dir, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, timeout=timeout,
                               creationflags=_CREATE_NO_WINDOW)
            text = (r.stdout or b"").decode("utf-8", "replace")
            iters = 0
            m = re.search(r"\[Iterations:\s*(\d+)\]", text)
            if m:
                iters = int(m.group(1))
            rate = None
            for line in text.splitlines():
                r2 = _parse_rate(line)
                if r2:
                    rate = r2
                    break
            if rate:
                out[mode] = {"rate": rate, "iters": iters, "device": device_name()}
            elif _PROBE_DEVICE is not None:
                _disable_device_selection()
                return benchmark_modes(modes, timeout)
        except Exception:
            continue
    return out
