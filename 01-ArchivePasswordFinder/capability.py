# -*- coding: utf-8 -*-
"""本机 24 小时可覆盖的密码长度评估。

速度来源：
    ZIP 传统加密  —— 启动自检里真实扫描出来的速度
    AES-ZIP / 7z  —— hashcat 基准测试（结果按显卡缓存 7 天）

长度按“该字符集 1..L 位的候选总数 ≤ 速度 × 预算”计算。
"""
import json
import os
import time

import core
import hashcat_gpu

DEFAULT_BUDGET = 24 * 3600
_CACHE_DAYS = 7
_CACHE_VERSION = 1

_BASES = (
    ("digits", "纯数字", 10, core.DIGITS),
    ("alnum", "字母+数字", 36, core.LOWER + core.DIGITS),
    ("printable", "可打印字符", 95, core.PRINTABLE),
)

# 这些格式的估算基准：真实压缩包常用的 KDF 迭代次数
_REAL_ITERS = {
    hashcat_gpu.HASHCAT_MODE_ZIP_AES: 1000,
    hashcat_gpu.HASHCAT_MODE_7Z: 2 ** 19,
    hashcat_gpu.HASHCAT_MODE_RAR5: 2 ** 15,
}


def _cache_path():
    return os.path.join(hashcat_gpu._local_appdata(), "capability.json")


def _cache_key():
    return "%s|%s" % (hashcat_gpu.HASHCAT_VERSION,
                      hashcat_gpu.device_name() or "none")


def hashcat_rate(mode):
    """返回该 hashcat 模式在真实迭代次数下的估算速度（H/s），未知返回 None。"""
    cache = load_cache()
    if not cache and not hashcat_gpu.device_name():
        hashcat_gpu.available(extract=True)
        cache = load_cache()
    rates = cache.get("hashcat") or {}
    return rates.get(str(mode))


def load_cache():
    try:
        with open(_cache_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}
    if data.get("version") != _CACHE_VERSION:
        return {}
    if data.get("key") != _cache_key():
        return {}
    if time.time() - float(data.get("ts") or 0) > _CACHE_DAYS * 86400:
        return {}
    return data


def save_cache(hashcat_rates, device):
    data = {"version": _CACHE_VERSION, "key": _cache_key(), "ts": time.time(),
            "device": device, "hashcat": hashcat_rates}
    try:
        os.makedirs(os.path.dirname(_cache_path()), exist_ok=True)
        with open(_cache_path(), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


def benchmark_hashcat():
    """跑一次 hashcat benchmark，按真实迭代次数换算后写缓存。"""
    if not hashcat_gpu.available(extract=True):
        return {}
    modes = [hashcat_gpu.HASHCAT_MODE_ZIP_AES, hashcat_gpu.HASHCAT_MODE_7Z,
             hashcat_gpu.HASHCAT_MODE_RAR5]
    raw = hashcat_gpu.benchmark_modes(modes)
    rates = {}
    for mode, info in raw.items():
        rate = info.get("rate") or 0
        iters = info.get("iters") or 0
        real = _REAL_ITERS.get(mode)
        if rate and real and iters:
            rate = rate * iters / float(real)
        rates[str(mode)] = rate
    save_cache(rates, hashcat_gpu.device_name())
    return rates


def measure(selftest=None):
    """汇总当前机器的速度。返回 dict，可直接给界面用。"""
    selftest = selftest or {}
    zipcrypto = float(selftest.get("rate") or 0)
    hashcat_ok = hashcat_gpu.available(extract=True)
    cache = load_cache()
    rates = cache.get("hashcat") or {}
    if not rates and hashcat_ok:
        rates = benchmark_hashcat()
    return {
        "zip": zipcrypto,
        "zip_aes": rates.get(str(hashcat_gpu.HASHCAT_MODE_ZIP_AES)),
        "7z": rates.get(str(hashcat_gpu.HASHCAT_MODE_7Z)),
        "rar5": rates.get(str(hashcat_gpu.HASHCAT_MODE_RAR5)),
        "device": hashcat_gpu.device_name() or selftest.get("name") or "",
        "backend": selftest.get("backend") or "cpu",
        "hashcat_ok": bool(hashcat_ok),
    }


def _max_len(rate, base, budget):
    if not rate or rate <= 0 or base <= 1 or budget <= 0:
        return 0
    limit = rate * budget
    total = 0
    p = 1
    length = 0
    while length < 20:
        p *= base
        total += p
        if total > limit:
            return length
        length += 1
    return length


def rows(rates, budget=DEFAULT_BUDGET):
    """把速度换算成每个字符集的最大长度。"""
    out = []
    for key, label, base, charset in _BASES:
        out.append({"key": key, "label": label, "base": base,
                    "charset": charset})
    specs = (
        ("zip", "ZIP 传统加密", rates.get("zip"), "CUDA / OpenCL"),
        ("zip_aes", "ZIP AES", rates.get("zip_aes"), "hashcat"),
        ("7z", "7z 加密", rates.get("7z"), "hashcat"),
        ("rar5", "RAR5", rates.get("rar5"), "hashcat"),
    )
    result = []
    for key, label, rate, engine in specs:
        row = {"key": key, "label": label, "engine": engine, "rate": rate,
               "lengths": {}}
        for item in out:
            if key == "zip" and rate:
                # ZipCrypto 的 GPU 内核最长 8 位，自动模式不会跑更长的
                row["lengths"][item["key"]] = min(
                    _max_len(rate, item["base"], budget), 8)
            else:
                row["lengths"][item["key"]] = (
                    _max_len(rate, item["base"], budget) if rate else 0)
        result.append(row)
    return result


def format_rate(rate):
    if not rate:
        return "—"
    if rate >= 1e9:
        return "%.1f G/s" % (rate / 1e9)
    if rate >= 1e6:
        return "%.1f M/s" % (rate / 1e6)
    if rate >= 1e3:
        return "%.1f K/s" % (rate / 1e3)
    return "%d H/s" % int(rate)


def estimate_seconds(charset, minlen, maxlen, rate):
    if not rate or rate <= 0:
        return None
    try:
        total = sum(len(set(charset)) ** L for L in range(int(minlen), int(maxlen) + 1))
    except Exception:
        return None
    return total / rate
