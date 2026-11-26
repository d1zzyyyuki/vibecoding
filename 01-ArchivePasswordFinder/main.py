# -*- coding: utf-8 -*-
"""压缩包密码找回 —— 程序入口。"""
import multiprocessing
import sys


if __name__ == "__main__":
    multiprocessing.freeze_support()
    from ui import main

    sys.exit(main())
