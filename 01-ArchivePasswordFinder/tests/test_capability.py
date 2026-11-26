# -*- coding: utf-8 -*-
"""能力评估的纯计算部分（不需要显卡/hashcat）。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import common  # noqa: E402
import capability  # noqa: E402


def main():
    rep = common.Reporter()
    rep.check("1 MH/s 纯数字 24h 约 10 位",
              capability._max_len(1e6, 10, 86400) == 10,
              str(capability._max_len(1e6, 10, 86400)))
    rep.check("速度越高长度不降",
              capability._max_len(1e9, 10, 86400) >= capability._max_len(1e8, 10, 86400))
    rows = capability.rows({"zip": 1.5e9, "zip_aes": 2e7, "7z": 5000}, 86400)
    by_key = {r["key"]: r for r in rows}
    rep.check("ZIP 行不超过 GPU 内核 8 位",
              by_key["zip"]["lengths"]["digits"] <= 8,
              str(by_key["zip"]["lengths"]["digits"]))
    rep.check("AES 行数字长度 > 7z 行",
              by_key["zip_aes"]["lengths"]["digits"] > by_key["7z"]["lengths"]["digits"])
    rep.check("速度格式化", capability.format_rate(1.5e9) == "1.5 G/s"
              and capability.format_rate(5000) == "5.0 K/s",
              "%s / %s" % (capability.format_rate(1.5e9),
                           capability.format_rate(5000)))
    rep.check("估算耗时为数字", capability.estimate_seconds("0123456789", 1, 4, 1000) == 11110 / 1000.0)
    return rep.summary()


if __name__ == "__main__":
    sys.exit(main())
