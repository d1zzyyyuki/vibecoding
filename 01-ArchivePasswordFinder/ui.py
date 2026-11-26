# -*- coding: utf-8 -*-
"""压缩包密码找回 —— 玻璃拟态界面（PySide6）。"""
import ctypes
import json
import os
import sys
import threading
import time

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QIcon, QLinearGradient, QPainter,
                           QPainterPath, QPen, QPixmap, QRadialGradient)
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QFileDialog, QFrame,
                               QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPlainTextEdit, QProgressBar,
                               QPushButton, QScrollArea, QSizeGrip, QVBoxLayout,
                               QWidget)

import capability
import core

ACCENT1 = "#E89A57"
ACCENT2 = "#D2536F"

CAP_MIN = "\uE921"
CAP_MAX = "\uE922"
CAP_RESTORE = "\uE923"
CAP_CLOSE = "\uE8BB"

# 整体压暗一档：夜里关灯不刺眼，暖橙/酒红的色调不变。
QSS = """
QWidget { color: #E7E1DF; }
QFrame#Card {
    background-color: rgba(13, 9, 13, 0.74);
    border: 1px solid rgba(255, 235, 225, 0.11);
    border-radius: 16px;
}
QLabel#H1 { font-size: 26px; font-weight: 700; color: #F3E9E2; }
QLabel#Section { color: rgba(255, 232, 222, 0.56); font-size: 12px; }
QLabel#Hint { color: rgba(255, 225, 215, 0.48); font-size: 12px; }
QLabel#Status { color: rgba(255, 230, 220, 0.56); font-size: 12px; }
QLabel#ResultLabel { color: rgba(255, 232, 222, 0.56); font-size: 12px; }
QLabel#Badge {
    background: rgba(232, 154, 87, 0.16);
    border: 1px solid rgba(232, 154, 87, 0.34);
    border-radius: 9px;
    padding: 2px 10px;
    color: #F3CBA2;
    font-size: 12px;
}
QLineEdit, QComboBox {
    background: rgba(15, 11, 16, 0.66);
    border: 1px solid rgba(255, 235, 225, 0.13);
    border-radius: 10px;
    padding: 8px 11px;
    selection-background-color: rgba(210, 83, 111, 0.55);
}
QLineEdit:focus, QComboBox:focus {
    border: 1px solid rgba(232, 154, 87, 0.82);
    background: rgba(23, 17, 22, 0.82);
}
QLineEdit:read-only { color: #F4E4D0; background: rgba(9, 7, 11, 0.45); }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox::down-arrow {
    image: url("%CHEVRON%");
    width: 9px;
    height: 6px;
    margin-right: 8px;
}
QComboBox QAbstractItemView {
    background: #181114;
    border: 1px solid rgba(255, 235, 225, 0.16);
    border-radius: 10px;
    padding: 4px;
    selection-background-color: rgba(210, 83, 111, 0.38);
    outline: none;
}
QPushButton {
    background: rgba(255, 240, 232, 0.075);
    border: 1px solid rgba(255, 235, 225, 0.13);
    border-radius: 10px;
    padding: 8px 16px;
}
QPushButton:hover { background: rgba(255, 240, 232, 0.13); }
QPushButton:pressed { background: rgba(255, 240, 232, 0.19); }
QPushButton:disabled { color: rgba(255, 240, 232, 0.28); background: rgba(255,255,255,0.025); }
QComboBox:disabled, QLineEdit:disabled {
    color: rgba(255, 240, 232, 0.30);
    background: rgba(255, 255, 255, 0.02);
    border: 1px solid rgba(255, 235, 225, 0.06);
}
QPushButton#Primary {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #E89A57, stop:1 #D2536F);
    border: none;
    border-radius: 12px;
    padding: 12px 30px;
    font-size: 15px;
    font-weight: 600;
    color: #291010;
}
QPushButton#Primary:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #F2AC6B, stop:1 #E2637F);
}
QPushButton#Primary:disabled { color: rgba(42,16,16,0.45); background: rgba(232,154,87,0.28); }
QPushButton#TitleBtn {
    background: transparent; border: none; border-radius: 0px;
    color: rgba(255, 240, 232, 0.82); padding: 0px;
}
QPushButton#TitleBtn:hover { background: rgba(255, 240, 232, 0.10); }
QPushButton#TitleBtn:pressed { background: rgba(255, 240, 232, 0.16); }
QPushButton#CloseBtn {
    background: transparent; border: none; border-radius: 0px;
    color: rgba(255, 240, 232, 0.82); padding: 0px;
}
QPushButton#CloseBtn:hover { background: #C42B1C; color: #FFFFFF; }
QPushButton#CloseBtn:pressed { background: #B0271A; color: #FFFFFF; }
QPushButton#LangBtn {
    background: rgba(255, 240, 232, 0.085);
    border: 1px solid rgba(255, 235, 225, 0.17);
    border-radius: 9px;
    padding: 3px 12px;
    font-size: 12px;
    color: rgba(255, 240, 232, 0.80);
}
QPushButton#LangBtn:hover { background: rgba(232, 154, 87, 0.26); }
QPushButton#LangBtnActive {
    background: rgba(232, 154, 87, 0.30);
    border: 1px solid rgba(232, 154, 87, 0.55);
    border-radius: 9px;
    padding: 3px 12px;
    color: #2A1010;
    font-weight: 700;
}
QProgressBar {
    background: rgba(9, 7, 11, 0.50);
    border: 1px solid rgba(255, 235, 225, 0.09);
    border-radius: 6px;
    height: 12px;
    text-align: center;
}
QProgressBar::chunk {
    border-radius: 6px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #E89A57, stop:1 #D2536F);
}
QPlainTextEdit {
    background: rgba(9, 7, 11, 0.44);
    border: 1px solid rgba(255, 235, 225, 0.09);
    border-radius: 12px;
    color: rgba(255, 235, 225, 0.74);
    font-size: 12px;
    padding: 6px;
}
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 9px; margin: 2px; }
QScrollBar::handle:vertical { background: rgba(255, 240, 232, 0.20); border-radius: 4px; min-height: 26px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QToolTip {
    background: #1E1418; color: #F7EBE2;
    border: 1px solid rgba(255, 235, 225, 0.16); border-radius: 8px; padding: 6px;
}
"""

TEXTS = {
    "zh": {
        "app_name": "压缩包密码找回",
        "by": "by cbd",
        "h1": "压缩包密码找回",
        "archive": "压缩包",
        "archive_ph": "选择 .zip / .rar / .7z 等压缩包…",
        "browse": "浏览…",
        "engine": "引擎",
        "auto": "自动",
        "cpu": "CPU",
        "gpu": "GPU",
        "start": "开始破解",
        "stop": "停止",
        "ready": "就绪",
        "searching": "破解中…",
        "stage": "阶段",
        "attempts": "尝试",
        "speed": "速度",
        "elapsed": "用时",
        "remaining": "剩余",
        "result": "结果",
        "password_ph": "找到的密码会显示在这里",
        "copy": "复制密码",
        "extract": "解压到…",
        "log": "日志",
        "done": "已完成",
        "not_found": "未找到",
        "stopped": "已停止",
        "not_encrypted": "未加密",
        "copied": "已复制",
        "engine_label": "引擎",
        "waiting": "等待任务",
        "ram": "内存",
        "vram": "显存",
        "backend_probing": "自检中…",
        "gpu_tip": "GPU 引擎：NVIDIA 优先 CUDA，AMD / Intel 走 OpenCL",
        "log_selftest": "启动自检：%s",
        "log_selftest_failed": "启动自检失败：%s（改用 CPU 引擎）",
        "warn_archive": "请先选择一个存在的压缩包文件",
        "info_not_encrypted": "这个压缩包没有加密，不需要破解。",
        "info_not_found": "没有找到密码。\n可以确认一下压缩包是否完整，或者把长度上限提高后再试。",
        "info_extracted": "已解压到：\n",
        "extract_fail": "解压失败：",
        "error": "出错了",
        "confirm_close": "正在破解，确定要退出吗？",
        "log_found": "找到密码：%s（尝试 %s 次，用时 %s）",
        "log_copied": "密码已复制到剪贴板。",
        "log_start": "开始自动破解…",
        "log_stage": "阶段 %d/%d · %s（%s 个候选）",
        "log_extracted": "解压完成。",
        "badge_none": "待选择",
        "badge_engine": "引擎 · %s",
        "title": "压缩包密码找回",
    },
    "en": {
        "app_name": "Archive Password Finder",
        "by": "by cbd",
        "h1": "Archive Password Finder",
        "archive": "Archive",
        "archive_ph": "Choose a .zip / .rar / .7z archive…",
        "browse": "Browse…",
        "engine": "Engine",
        "auto": "Auto",
        "cpu": "CPU",
        "gpu": "GPU",
        "start": "Start",
        "stop": "Stop",
        "ready": "Ready",
        "searching": "Cracking…",
        "stage": "Stage",
        "attempts": "Tries",
        "speed": "Speed",
        "elapsed": "Time",
        "remaining": "Left",
        "result": "Result",
        "password_ph": "The password will appear here",
        "copy": "Copy",
        "extract": "Extract…",
        "log": "Log",
        "done": "Done",
        "not_found": "Not found",
        "stopped": "Stopped",
        "not_encrypted": "Not encrypted",
        "copied": "Copied",
        "engine_label": "Engine",
        "waiting": "Idle",
        "ram": "RAM",
        "vram": "VRAM",
        "backend_probing": "Probing…",
        "gpu_tip": "GPU engine: CUDA on NVIDIA, OpenCL on AMD / Intel",
        "log_selftest": "Startup self-test: %s",
        "log_selftest_failed": "Startup self-test failed: %s (CPU engine)",
        "warn_archive": "Please choose an existing archive first.",
        "info_not_encrypted": "This archive is not encrypted.",
        "info_not_found": "Password not found.\nCheck the archive or let it run on a larger search.",
        "info_extracted": "Extracted to:\n",
        "extract_fail": "Extraction failed: ",
        "error": "Error",
        "confirm_close": "Cracking is running. Quit anyway?",
        "log_found": "Password found: %s (%s tries, %s)",
        "log_copied": "Password copied to clipboard.",
        "log_start": "Automatic cracking started…",
        "log_stage": "Stage %d/%d · %s (%s candidates)",
        "log_extracted": "Extraction finished.",
        "badge_none": "Waiting",
        "badge_engine": "Engine · %s",
        "title": "Archive Password Finder",
    },
}


def fmt_elapsed(sec):
    try:
        sec = float(sec)
    except Exception:
        return "--"
    if sec < 10:
        return "%.2f s" % sec
    if sec < 60:
        return "%.1f s" % sec
    return core.fmt_eta(sec)


def fmt_rate_chip(rate):
    """状态栏芯片用的紧凑吞吐：1.2 G/s / 820 M/s，中英界面通用。"""
    try:
        rate = float(rate)
    except Exception:
        return ""
    if rate <= 0:
        return ""
    if rate >= 1e9:
        return "%.1f G/s" % (rate / 1e9)
    if rate >= 1e6:
        return "%.0f M/s" % (rate / 1e6)
    return "%.0f K/s" % (rate / 1e3)


BACKEND_STYLE = {
    "probing": ("background: rgba(255, 240, 232, 0.07); "
                "border: 1px solid rgba(255, 235, 225, 0.16); color: rgba(255, 236, 226, 0.62);"),
    "cuda": ("background: rgba(118, 214, 148, 0.15); "
             "border: 1px solid rgba(118, 214, 148, 0.46); color: #BCEFC9;"),
    "opencl": ("background: rgba(122, 176, 238, 0.15); "
               "border: 1px solid rgba(122, 176, 238, 0.46); color: #C4DCF8;"),
    "cpu": ("background: rgba(232, 154, 87, 0.15); "
            "border: 1px solid rgba(232, 154, 87, 0.40); color: #F2CFA9;"),
}


def backend_chip_style(state):
    return ("QLabel { font-size: 12px; padding: 1px 9px; border-radius: 9px; %s }"
            % BACKEND_STYLE.get(state, BACKEND_STYLE["probing"]))


# ---------------------------------------------------------------------------
# Win32 亚克力
# ---------------------------------------------------------------------------
class _AccentPolicy(ctypes.Structure):
    _fields_ = [("AccentState", ctypes.c_int), ("AccentFlags", ctypes.c_int),
                ("GradientColor", ctypes.c_uint), ("AnimationId", ctypes.c_int)]


class _WinCompAttrData(ctypes.Structure):
    _fields_ = [("Attribute", ctypes.c_int), ("Data", ctypes.POINTER(_AccentPolicy)),
                ("SizeOfData", ctypes.c_size_t)]


def apply_acrylic(hwnd, tint=0x99261A1E):
    try:
        accent = _AccentPolicy(4, 2, tint, 0)
        data = _WinCompAttrData(19, ctypes.pointer(accent), ctypes.sizeof(accent))
        fn = ctypes.windll.user32.SetWindowCompositionAttribute
        fn.argtypes = [ctypes.c_void_p, ctypes.POINTER(_WinCompAttrData)]
        fn.restype = ctypes.c_int
        return bool(fn(hwnd, ctypes.byref(data)))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# 组件
# ---------------------------------------------------------------------------
class ImagePanel(QWidget):
    """右侧立绘展示区：cover 裁切 + 左侧渐变过渡。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bg = QPixmap()
        for name in ("hutao_panel.jpg", "hutao_bg.jpg", "hutao_bg.png"):
            p = core.asset_path(name)
            if os.path.isfile(p):
                pm = QPixmap(p)
                if not pm.isNull():
                    self._bg = pm
                    break
        self._cache = None
        self._cache_key = None

    def _pix(self):
        if self._bg.isNull():
            return QPixmap()
        key = (self.width(), self.height())
        if self._cache_key == key:
            return self._cache
        bw, bh = self._bg.width(), self._bg.height()
        scale = max(self.width() / bw, self.height() / bh)
        sw, sh = int(bw * scale + 0.5), int(bh * scale + 0.5)
        pm = self._bg.scaled(sw, sh, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        cx = int(sw * 0.62)
        x = max(0, min(sw - self.width(), cx - self.width() // 2))
        y = max(0, (sh - self.height()) // 2)
        self._cache = pm.copy(x, y, self.width(), self.height())
        self._cache_key = key
        return self._cache

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pm = self._pix()
        if not pm.isNull():
            p.drawPixmap(0, 0, pm)
            # 立绘压暗一档，避免夜里刺眼
            p.fillRect(self.rect(), QColor(6, 4, 8, 21))
        else:
            p.fillRect(self.rect(), QColor(26, 17, 21))
        g = QLinearGradient(0, 0, max(60, self.width() * 0.55), 0)
        g.setColorAt(0.0, QColor(10, 7, 10, 255))
        g.setColorAt(0.35, QColor(10, 7, 10, 158))
        g.setColorAt(1.0, QColor(10, 7, 10, 0))
        p.fillRect(self.rect(), g)
        gv = QLinearGradient(0, 0, 0, self.height())
        gv.setColorAt(0.0, QColor(9, 6, 9, 132))
        gv.setColorAt(0.18, QColor(9, 6, 9, 0))
        gv.setColorAt(0.82, QColor(9, 6, 9, 0))
        gv.setColorAt(1.0, QColor(9, 6, 9, 184))
        p.fillRect(self.rect(), gv)
        # 左侧玻璃分割线
        p.setPen(QPen(QColor(255, 240, 232, 30), 1))
        p.drawLine(1, 0, 1, self.height())
        p.end()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._cache_key = None


class Card(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setAttribute(Qt.WA_StyledBackground, True)


class TitleBar(QWidget):
    def __init__(self, window):
        super().__init__(window)
        self._win = window
        self._drag_pos = None
        self.setFixedHeight(50)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 8, 0, 0)
        lay.setSpacing(9)
        icon_path = os.path.join(core.ASSETS_DIR, "icon.ico")
        if os.path.exists(icon_path):
            ic = QLabel()
            ic.setPixmap(QIcon(icon_path).pixmap(22, 22))
            lay.addWidget(ic)
        self.lbl_name = QLabel()
        self.lbl_name.setStyleSheet("font-size: 13px; font-weight: 600; color: rgba(255,245,238,0.94);")
        lay.addWidget(self.lbl_name)
        self.lbl_by = QLabel("by cbd")
        self.lbl_by.setObjectName("Badge")
        lay.addWidget(self.lbl_by)
        lay.addStretch(1)
        families = set(QFontDatabase.families())
        if "Segoe Fluent Icons" in families:
            cap_family = "Segoe Fluent Icons"
        elif "Segoe MDL2 Assets" in families:
            cap_family = "Segoe MDL2 Assets"
        else:
            cap_family = "Segoe UI Symbol"
        cap_font = QFont(cap_family)
        cap_font.setPixelSize(10)
        cap = QHBoxLayout()
        cap.setContentsMargins(0, 0, 0, 0)
        cap.setSpacing(0)
        self.btn_min = QPushButton(CAP_MIN)
        self.btn_min.setObjectName("TitleBtn")
        self.btn_min.setFixedSize(46, 32)
        self.btn_min.setFont(cap_font)
        self.btn_min.setCursor(Qt.ArrowCursor)
        self.btn_min.clicked.connect(window.showMinimized)
        cap.addWidget(self.btn_min)
        self.btn_max = QPushButton(CAP_MAX)
        self.btn_max.setObjectName("TitleBtn")
        self.btn_max.setFixedSize(46, 32)
        self.btn_max.setFont(cap_font)
        self.btn_max.setCursor(Qt.ArrowCursor)
        self.btn_max.clicked.connect(window.toggle_max)
        cap.addWidget(self.btn_max)
        self.btn_close = QPushButton(CAP_CLOSE)
        self.btn_close.setObjectName("CloseBtn")
        self.btn_close.setFixedSize(46, 32)
        self.btn_close.setFont(cap_font)
        self.btn_close.setCursor(Qt.ArrowCursor)
        self.btn_close.clicked.connect(window.close_clicked)
        cap.addWidget(self.btn_close)
        lay.addLayout(cap)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self._win.frameGeometry().topLeft()
            e.accept()

    def mouseMoveEvent(self, e):
        if self._drag_pos is not None and e.buttons() & Qt.LeftButton:
            self._win.move(e.globalPosition().toPoint() - self._drag_pos)
            e.accept()

    def mouseReleaseEvent(self, e):
        self._drag_pos = None
        e.accept()

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._win.toggle_max()
            e.accept()


class EngineThread(threading.Thread):
    def __init__(self, bridge, opts, stop):
        super().__init__(daemon=True)
        self.bridge = bridge
        self.opts = opts
        self.stop = stop

    def run(self):
        try:
            result = core.run_auto_search(self.opts, self.bridge.emit_event, self.stop)
            self.bridge.emit_event({"type": "done", "result": result})
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.bridge.emit_event({"type": "error", "message": str(e)})


class Bridge(QObject):
    event = Signal(object)

    def emit_event(self, msg):
        self.event.emit(msg)


DIALOG_QSS = """
QDialog { background: #171014; }
QLabel { color: rgba(255, 240, 232, 0.86); }
QLabel#DlgTitle { font-size: 18px; font-weight: 700; color: #F3E9E2; }
QLabel#DlgHint { color: rgba(255, 225, 215, 0.55); font-size: 12px; }
QLabel#DlgCell { color: rgba(255, 240, 232, 0.88); }
"""


def _tr(lang, zh, en):
    return en if lang == "en" else zh


class CapabilityDialog(QDialog):
    """本机能力：按实测速度给出不同时间预算下的可破长度。"""

    remeasure = Signal()

    def __init__(self, parent, lang, rates, budget=24 * 3600):
        super().__init__(parent)
        self.lang = lang
        self._rates = dict(rates or {})
        self._budget = budget
        self._bg = QPixmap()
        for name in ("hutao_panel.jpg", "hutao_bg_soft.jpg", "hutao_bg.jpg"):
            p = core.asset_path(name)
            if os.path.isfile(p):
                pm = QPixmap(p)
                if not pm.isNull():
                    self._bg = pm
                    break
        self.setModal(False)
        self.setMinimumWidth(660)
        self.setStyleSheet(DIALOG_QSS)
        self.setWindowTitle(_tr(lang, "本机破解能力", "Cracking capability"))
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 16, 24, 18)
        v.setSpacing(9)

        title = QLabel(_tr(lang, "本机能试完的密码长度", "Password lengths this machine can test"))
        title.setObjectName("DlgTitle")
        v.addWidget(title)

        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(QLabel(_tr(lang, "时间预算", "Time budget")))
        self.cmb_budget = QComboBox()
        self.cmb_budget.setMinimumHeight(32)
        for label, secs in ((_tr(lang, "2 分钟", "2 min"), 120),
                            (_tr(lang, "10 分钟", "10 min"), 600),
                            (_tr(lang, "30 分钟", "30 min"), 1800),
                            (_tr(lang, "1 小时", "1 hour"), 3600),
                            (_tr(lang, "6 小时", "6 hours"), 21600),
                            (_tr(lang, "24 小时", "24 hours"), 86400),
                            (_tr(lang, "3 天", "3 days"), 259200)):
            self.cmb_budget.addItem(label, secs)
        idx = self.cmb_budget.findData(budget)
        if idx >= 0:
            self.cmb_budget.setCurrentIndex(idx)
        self.cmb_budget.currentIndexChanged.connect(self._budget_changed)
        top.addWidget(self.cmb_budget)
        top.addStretch(1)
        self.btn_remeasure = QPushButton(_tr(lang, "重新测速", "Re-measure"))
        self.btn_remeasure.setMinimumHeight(32)
        self.btn_remeasure.clicked.connect(self.remeasure.emit)
        top.addWidget(self.btn_remeasure)
        v.addLayout(top)

        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(18)
        self.grid.setVerticalSpacing(9)
        headers = [_tr(lang, "格式", "Format"), _tr(lang, "纯数字", "Digits"),
                   _tr(lang, "混合", "Mixed"),
                   _tr(lang, "可打印字符", "Printable"),
                   _tr(lang, "实测速度", "Speed")]
        for c, text in enumerate(headers):
            w = QLabel(text)
            w.setObjectName("DlgHint")
            self.grid.addWidget(w, 0, c)
        self._cells = {}
        formats = (("zip", _tr(lang, "ZIP 传统加密", "ZIP ZipCrypto")),
                   ("zip_aes", "ZIP AES"),
                   ("7z", "7z"),
                   ("rar5", _tr(lang, "RAR5", "RAR5")))
        for r, (key, label) in enumerate(formats, start=1):
            self.grid.addWidget(QLabel(label), r, 0)
            cells = []
            for c in range(1, 5):
                w = QLabel("—")
                w.setObjectName("DlgCell")
                self.grid.addWidget(w, r, c)
                cells.append(w)
            self._cells[key] = cells
        self.grid.setColumnStretch(0, 2)
        for c in range(1, 5):
            self.grid.setColumnStretch(c, 1)
        v.addLayout(self.grid)

        self.lbl_note = QLabel("")
        self.lbl_note.setObjectName("DlgHint")
        self.lbl_note.setWordWrap(True)
        v.addWidget(self.lbl_note)
        self.lbl_device = QLabel("")
        self.lbl_device.setObjectName("DlgHint")
        self.lbl_device.setWordWrap(True)
        v.addWidget(self.lbl_device)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self.btn_ok = QPushButton(_tr(lang, "知道了", "Got it"))
        self.btn_ok.setObjectName("Primary")
        self.btn_ok.setMinimumHeight(38)
        self.btn_ok.clicked.connect(self.close)
        bottom.addWidget(self.btn_ok)
        v.addLayout(bottom)
        self._refresh()

    def paintEvent(self, e):
        p = QPainter(self)
        rect = QRectF(0, 0, self.width(), self.height())
        if not self._bg.isNull():
            bw, bh = self._bg.width(), self._bg.height()
            scale = max(self.width() / bw, self.height() / bh)
            sw, sh = int(bw * scale + 0.5), int(bh * scale + 0.5)
            pm = self._bg.scaled(sw, sh, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            x = sw - self.width()
            # 顶部对齐，保证胡桃的头不会被裁掉
            y = 0
            p.drawPixmap(-x, -y, pm)
        p.fillRect(rect, QColor(10, 7, 10, 208))
        g = QLinearGradient(0, 0, self.width(), self.height())
        g.setColorAt(0.0, QColor(213, 85, 115, 42))
        g.setColorAt(1.0, QColor(10, 7, 10, 120))
        p.fillRect(rect, g)

    def _budget_changed(self, _idx):
        self._budget = int(self.cmb_budget.currentData() or 86400)
        self._refresh()

    def update_rates(self, rates):
        self._rates = dict(rates or {})
        self._refresh()

    def _refresh(self):
        rows = {row["key"]: row for row in capability.rows(self._rates, self._budget)}
        hashcat_ok = self._rates.get("hashcat_ok", True)
        for key in ("zip", "zip_aes", "7z", "rar5"):
            row = rows.get(key) or {}
            rate = row.get("rate")
            lengths = row.get("lengths") or {}
            cells = self._cells[key]
            if not rate:
                for i, c in enumerate(cells):
                    if i == 3:
                        c.setText(_tr(self.lang, "测速中…", "measuring…")
                                  if hashcat_ok else _tr(self.lang, "不可用", "n/a"))
                    else:
                        c.setText("—")
                continue
            cells[0].setText("%d 位" % lengths.get("digits", 0))
            cells[1].setText("%d 位" % lengths.get("alnum", 0))
            cells[2].setText("%d 位" % lengths.get("printable", 0))
            cells[3].setText(capability.format_rate(rate))
        self.lbl_note.setText(_tr(
            self.lang,
            "按当前显卡实测速度估算。ZIP 传统加密最多 8 位（GPU 内核上限）。",
            "Estimated from measured GPU speed. ZipCrypto is limited to 8 chars by the GPU kernel."))
        self.lbl_device.setText(_tr(
            self.lang, "设备：%s" % (self._rates.get("device") or "—"),
            "Device: %s" % (self._rates.get("device") or "—")))


CHARSET_CHOICES = (
    ("数字 0-9", "Digits 0-9", "0123456789"),
    ("小写字母 a-z", "Lowercase a-z", core.LOWER),
    ("大写字母 A-Z", "Uppercase A-Z", "ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
    ("小写 + 数字", "Lowercase + digits", core.LOWER + core.DIGITS),
    ("大小写 + 数字", "Upper + lower + digits",
     core.LOWER + "ABCDEFGHIJKLMNOPQRSTUVWXYZ" + core.DIGITS),
    ("全部可打印字符", "All printable ASCII", core.PRINTABLE),
    ("自定义", "Custom", ""),
)

_EXPECT_CHOICES = (
    (120, "2 分钟（自动）", "2 min (auto)"),
    (600, "10 分钟", "10 min"),
    (1800, "30 分钟", "30 min"),
    (3600, "1 小时", "1 hour"),
    (21600, "6 小时", "6 hours"),
    (86400, "24 小时", "24 hours"),
    (259200, "3 天", "3 days"),
    (None, "无限", "Unlimited"),
    (-1, "自定义…", "Custom…"),
)


class AdvancedDialog(QDialog):
    """攻击方式、期望破解时间、数字/混合位数、自定义字符集。"""

    def __init__(self, parent, lang, opts, rate_hint=0.0):
        super().__init__(parent)
        self.lang = lang
        self._rate = float(rate_hint or 0)
        self._ref_name = "ZIP"
        self._loading = True
        self._manual = False
        self._expect_seconds = 120
        self.setModal(True)
        self.setMinimumWidth(600)
        self.setStyleSheet(DIALOG_QSS)
        self.setWindowTitle(_tr(lang, "高级设置", "Advanced"))
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 18, 24, 18)
        v.setSpacing(9)

        title = QLabel(_tr(lang, "攻击方式", "Attack mode"))
        title.setObjectName("DlgTitle")
        v.addWidget(title)

        self.cmb_attack = QComboBox()
        for label, data in (
                (_tr(lang, "自动：字典 → 数字 → 混合", "Auto: dict → digits → mixed"), "auto"),
                (_tr(lang, "只跑字典", "Dictionary only"), "dict"),
                (_tr(lang, "只跑自定义字符集", "Custom charset only"), "space")):
            self.cmb_attack.addItem(label, data)
        self.cmb_attack.setMinimumHeight(34)
        v.addWidget(self.cmb_attack)

        form = QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(9)
        row = 0

        self.lbl_expect = QLabel(_tr(lang, "期望破解时间", "Target time"))
        form.addWidget(self.lbl_expect, row, 0)
        self.cmb_expect = QComboBox()
        for secs, zh, en in _EXPECT_CHOICES:
            self.cmb_expect.addItem(_tr(lang, zh, en), secs)
        form.addWidget(self.cmb_expect, row, 1, 1, 2)
        row += 1

        self.lbl_digits = QLabel(_tr(lang, "纯数字位数", "Digits length"))
        form.addWidget(self.lbl_digits, row, 0)
        self.cmb_digits = QComboBox()
        for L in range(0, 17):
            self.cmb_digits.addItem(_tr(lang, "关闭" if L == 0 else "%d 位" % L,
                                       "off" if L == 0 else "%d" % L), L)
        form.addWidget(self.cmb_digits, row, 1, 1, 2)
        row += 1

        self.lbl_mixed = QLabel(_tr(lang, "混合位数", "Mixed length"))
        self.lbl_mixed.setToolTip(_tr(lang, "小写字母 + 数字", "lowercase + digits"))
        form.addWidget(self.lbl_mixed, row, 0)
        self.cmb_mixed = QComboBox()
        for L in range(0, 13):
            self.cmb_mixed.addItem(_tr(lang, "关闭" if L == 0 else "%d 位" % L,
                                       "off" if L == 0 else "%d" % L), L)
        form.addWidget(self.cmb_mixed, row, 1, 1, 2)
        row += 1

        self.lbl_speed = QLabel("")
        self.lbl_speed.setObjectName("DlgHint")
        form.addWidget(self.lbl_speed, row, 0, 1, 3)
        row += 1

        self.lbl_charset = QLabel(_tr(lang, "字符集", "Charset"))
        form.addWidget(self.lbl_charset, row, 0)
        self.cmb_charset = QComboBox()
        for label_zh, label_en, data in CHARSET_CHOICES:
            self.cmb_charset.addItem(_tr(lang, label_zh, label_en), data)
        form.addWidget(self.cmb_charset, row, 1, 1, 2)
        row += 1

        self.ent_custom = QLineEdit()
        self.ent_custom.setPlaceholderText(_tr(lang, "自定义字符集，例如 abc123",
                                               "custom charset, e.g. abc123"))
        form.addWidget(self.ent_custom, row, 1, 1, 2)
        row += 1

        self.lbl_len = QLabel(_tr(lang, "长度", "Length"))
        form.addWidget(self.lbl_len, row, 0)
        lens = QHBoxLayout()
        self.cmb_min = QComboBox()
        self.cmb_max = QComboBox()
        for L in range(1, 17):
            self.cmb_min.addItem("%d 位" % L, L)
            self.cmb_max.addItem("%d 位" % L, L)
        self.cmb_min.setCurrentIndex(0)
        self.cmb_max.setCurrentIndex(7)
        self.lbl_dash = QLabel("—")
        lens.addWidget(self.cmb_min)
        lens.addWidget(self.lbl_dash)
        lens.addWidget(self.cmb_max)
        form.addLayout(lens, row, 1, 1, 2)
        row += 1

        self.lbl_wordlist = QLabel(_tr(lang, "字典", "Wordlist"))
        form.addWidget(self.lbl_wordlist, row, 0)
        wl = QHBoxLayout()
        self.ent_wordlist = QLineEdit()
        self.ent_wordlist.setPlaceholderText(
            _tr(lang, "留空使用内置字典（303 条）", "blank = built-in dictionary (303 words)"))
        wl.addWidget(self.ent_wordlist, 1)
        self.btn_wl = QPushButton("…")
        self.btn_wl.setFixedWidth(42)
        self.btn_wl.clicked.connect(self._browse_wordlist)
        wl.addWidget(self.btn_wl)
        form.addLayout(wl, row, 1, 1, 2)
        row += 1

        form.setColumnStretch(1, 1)
        form.setColumnStretch(2, 1)
        v.addLayout(form)

        self.lbl_estimate = QLabel("")
        self.lbl_estimate.setObjectName("DlgHint")
        self.lbl_estimate.setWordWrap(True)
        v.addWidget(self.lbl_estimate)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        cancel = QPushButton(_tr(lang, "取消", "Cancel"))
        cancel.clicked.connect(self.reject)
        bottom.addWidget(cancel)
        ok = QPushButton(_tr(lang, "确定", "OK"))
        ok.setObjectName("Primary")
        ok.clicked.connect(self._accept)
        bottom.addWidget(ok)
        v.addLayout(bottom)

        self.cmb_attack.currentIndexChanged.connect(self._sync)
        self.cmb_expect.currentIndexChanged.connect(self._on_expect)
        self.cmb_digits.currentIndexChanged.connect(self._on_length_edit)
        self.cmb_mixed.currentIndexChanged.connect(self._on_length_edit)
        self.cmb_charset.currentIndexChanged.connect(self._sync)
        self.cmb_min.currentIndexChanged.connect(self._update_estimate)
        self.cmb_max.currentIndexChanged.connect(self._update_estimate)
        self.ent_custom.textChanged.connect(self._update_estimate)
        opts = opts or {}
        self._load(opts)
        self._loading = False
        if opts.get("unlimited"):
            self._apply_preset(None)
        elif opts.get("digits_max") is not None or opts.get("mixed_max") is not None:
            self._loading = True
            self._manual = True
            if opts.get("digits_max") is not None:
                self._set_combo_by_data(self.cmb_digits, int(opts["digits_max"]))
            if opts.get("mixed_max") is not None:
                self._set_combo_by_data(self.cmb_mixed, int(opts["mixed_max"]))
            self.cmb_expect.setCurrentIndex(self.cmb_expect.count() - 1)
            self._loading = False
        else:
            self._apply_preset(opts.get("expect", 120))
        self._update_estimate()
        self._sync()

    # ---------- 数据 ----------
    def _load(self, opts):
        idx = self.cmb_attack.findData(opts.get("attack", "auto"))
        self.cmb_attack.setCurrentIndex(max(0, idx))
        charset = opts.get("charset") or ""
        found = False
        for i in range(self.cmb_charset.count()):
            if charset and self.cmb_charset.itemData(i) == charset:
                self.cmb_charset.setCurrentIndex(i)
                found = True
                break
        if charset and not found:
            self.cmb_charset.setCurrentIndex(self.cmb_charset.count() - 1)
            self.ent_custom.setText(charset)
        if opts.get("minlen"):
            self.cmb_min.setCurrentIndex(max(0, int(opts["minlen"]) - 1))
        if opts.get("maxlen"):
            self.cmb_max.setCurrentIndex(max(0, int(opts["maxlen"]) - 1))
        self.ent_wordlist.setText(opts.get("wordlist") or "")
        self._expect_seconds = opts.get("expect", 120)

    def _set_combo_by_data(self, combo, value):
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        idx = combo.findData(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def _apply_preset(self, seconds):
        """按秒数计算数字/混合长度并填入。seconds=None 表示无限。"""
        self._loading = True
        try:
            if seconds is None:
                self._expect_seconds = None
                self._set_combo_by_data(self.cmb_expect, None)
                self.cmb_digits.setEnabled(False)
                self.cmb_mixed.setEnabled(False)
            else:
                seconds = float(seconds)
                self._expect_seconds = seconds
                self._manual = False
                self.cmb_digits.setEnabled(True)
                self.cmb_mixed.setEnabled(True)
                D = M = 0
                if self._rate:
                    if abs(seconds - 120.0) < 1e-6:
                        D, M = core._pair_under(self._rate, seconds, 16, 12)
                    else:
                        D, M = core._nearest_pair(self._rate, seconds, 16, 12)
                else:
                    D, M = 6, 4
                D = max(0, min(D, 16))
                M = max(0, min(M, 12))
                self._set_combo_by_data(self.cmb_digits, D)
                self._set_combo_by_data(self.cmb_mixed, M)
                self._set_combo_by_data(self.cmb_expect, seconds)
        finally:
            self._loading = False
        self._update_estimate()

    def _on_expect(self, _idx):
        if self._loading:
            return
        data = self.cmb_expect.currentData()
        if data == -1:
            from PySide6.QtWidgets import QInputDialog
            minutes, ok = QInputDialog.getInt(
                self, _tr(self.lang, "自定义时间", "Custom time"),
                _tr(self.lang, "期望时间（分钟）", "Time (minutes)"),
                max(1, int((self._expect_seconds or 600) // 60)), 1, 100000)
            if not ok:
                self._apply_preset(self._expect_seconds)
                return
            seconds = minutes * 60
            self.cmb_expect.setItemText(self.cmb_expect.count() - 1,
                                        _tr(self.lang, "自定义（%d 分钟）" % minutes,
                                            "Custom (%d min)" % minutes))
            self._apply_preset(seconds)
        else:
            self._apply_preset(data)

    def _on_length_edit(self, _idx):
        if self._loading:
            return
        self._manual = True
        self._loading = True
        self.cmb_expect.setCurrentIndex(self.cmb_expect.count() - 1)
        self._loading = False
        self._update_estimate()

    def _charset(self):
        data = self.cmb_charset.currentData()
        if data == "":
            return self.ent_custom.text().strip()
        return data or ""

    def _browse_wordlist(self):
        p, _ = QFileDialog.getOpenFileName(self, _tr(self.lang, "选择字典", "Wordlist"),
                                           "", "Text (*.txt *.dic);;All files (*.*)")
        if p:
            self.ent_wordlist.setText(p)

    def _sync(self, *_a):
        attack = self.cmb_attack.currentData()
        auto = attack == "auto"
        dict_only = attack == "dict"
        custom = attack == "space"
        for w in (self.lbl_expect, self.cmb_expect, self.lbl_digits, self.cmb_digits,
                  self.lbl_mixed, self.cmb_mixed, self.lbl_speed):
            w.setVisible(auto)
        for w in (self.lbl_charset, self.cmb_charset, self.ent_custom, self.lbl_len,
                  self.cmb_min, self.lbl_dash, self.cmb_max):
            w.setVisible(custom)
        self.ent_custom.setVisible(custom and self.cmb_charset.currentData() == "")
        for w in (self.lbl_wordlist, self.ent_wordlist, self.btn_wl):
            w.setVisible(dict_only)
        self._update_estimate()

    def _update_estimate(self, *_a):
        if self._loading:
            return
        attack = self.cmb_attack.currentData()
        self.lbl_speed.setText(_tr(
            self.lang,
            "当前参考速度（%s）：%s" % (self._ref_name, core.fmt_rate(self._rate)),
            "Reference speed (%s): %s" % (self._ref_name, core.fmt_rate(self._rate))))
        if attack == "dict":
            wl = self.ent_wordlist.text().strip()
            if wl and os.path.isfile(wl):
                try:
                    n = sum(1 for _ in open(wl, "rb"))
                except Exception:
                    n = 0
                text = _tr(self.lang, "字典 %s 条" % core.fmt_num(n),
                           "%s words" % core.fmt_num(n))
            else:
                text = _tr(self.lang, "使用内置字典（303 条）", "Built-in dictionary (303 words)")
        elif attack == "space":
            charset = self._charset()
            if not charset:
                text = _tr(self.lang, "请填写自定义字符集", "Please enter a custom charset")
            else:
                lo = int(self.cmb_min.currentData())
                hi = max(lo, int(self.cmb_max.currentData()))
                total = sum(len(set(charset)) ** L for L in range(lo, hi + 1))
                text = _tr(self.lang, "候选 %s 个" % core.fmt_num(total),
                           "%s candidates" % core.fmt_num(total))
                if self._rate > 0:
                    text += _tr(self.lang, "，预计 %s" % core.fmt_eta(total / self._rate),
                                ", ETA %s" % core.fmt_eta(total / self._rate))
        elif self._expect_seconds is None:
            text = _tr(self.lang, "无限：按长度交替测，日志会写当前位数的数字/混合",
                       "Unlimited: interleaved by length; log shows digits/mixed length")
        else:
            d = int(self.cmb_digits.currentData())
            m = int(self.cmb_mixed.currentData())
            total = sum(10 ** L for L in range(1, d + 1))
            total += sum(36 ** L for L in range(1, m + 1))
            text = _tr(self.lang, "候选 %s 个" % core.fmt_num(total),
                       "%s candidates" % core.fmt_num(total))
            if self._rate > 0:
                text += _tr(
                    self.lang,
                    "，按选中位数预计 %s" % core.fmt_eta(total / self._rate),
                    ", ETA %s for these lengths" % core.fmt_eta(total / self._rate))
        self.lbl_estimate.setText(text)

    def set_ref_name(self, name):
        self._ref_name = name or "ZIP"
        self._update_estimate()

    def update_rate(self, rate, name=None):
        self._rate = float(rate or 0)
        if name:
            self._ref_name = name
        if not self._manual:
            self._apply_preset(self._expect_seconds)
        else:
            self._update_estimate()

    def _accept(self):
        if self.cmb_attack.currentData() == "space" and not self._charset():
            QMessageBox.warning(self, _tr(self.lang, "高级设置", "Advanced"),
                                _tr(self.lang, "请填写自定义字符集", "Please enter a custom charset"))
            return
        self.accept()

    def result_opts(self):
        attack = self.cmb_attack.currentData()
        return {
            "attack": attack,
            "expect": self._expect_seconds if attack == "auto" else None,
            "unlimited": attack == "auto" and self._expect_seconds is None,
            "digits_max": int(self.cmb_digits.currentData()) if attack == "auto" else None,
            "mixed_max": int(self.cmb_mixed.currentData()) if attack == "auto" else None,
            "charset": self._charset() if attack == "space" else "",
            "minlen": int(self.cmb_min.currentData()),
            "maxlen": max(int(self.cmb_min.currentData()), int(self.cmb_max.currentData())),
            "wordlist": self.ent_wordlist.text().strip() if attack == "dict" else "",
        }


# ---------------------------------------------------------------------------
# 主窗口
# ---------------------------------------------------------------------------
class MainWindow(QWidget):
    def __init__(self, demo_archive=None, force_size=None, lang=None, show_popup=True):
        super().__init__()
        self.lang = lang or "zh"
        self._no_popup = not show_popup
        self._acrylic_ok = False
        self._placed = False
        self._running = False
        self._stop = None
        self._thread = None
        self._found = None
        self._stage = ("", "")
        self._stage_idx = 0
        self._stage_count = 0
        self._engine_name = ("", "")
        self._log_entries = []
        self._boot_logs = []
        self._selftest = None
        self._selftest_event = threading.Event()
        self._cap_rates = {}
        self._cap_dialog = None
        self._adv_dialog = None
        self._adv_opts = {"attack": "auto", "expect": 120, "unlimited": False,
                          "digits_max": None, "mixed_max": None, "charset": "",
                          "minlen": 1, "maxlen": 8, "wordlist": ""}
        self._total = 0
        self._unlimited = False
        self._last_progress = {"rate": 0, "elapsed": 0, "eta": None, "done": 0}
        self._result_state = "ready"
        self._maximized = False
        self._normal_geo = None
        self._bg = self._load_bg()

        self.setWindowTitle(core.APP_NAME_ZH)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAcceptDrops(True)
        self.setMinimumSize(700, 480)

        scr = QApplication.primaryScreen().availableGeometry()
        if force_size:
            w, h = force_size
        else:
            w = min(1180, max(760, scr.width() - 50))
            h = min(800, max(520, scr.height() - 60))
        self.resize(w, h)

        self._bridge = Bridge()
        self._bridge.event.connect(self._on_event)
        self._hw = core.Hardware()
        self._hw.start()

        self._build()
        self._apply_lang()
        self._set_running(False)
        self._update_hw()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_hw)
        self._timer.start(1000)
        if demo_archive:
            self.ent_archive.setText(demo_archive)
        # 后台自检加速后端；能力评估等自检结果出来再测 hashcat 速度
        threading.Thread(target=self._run_selftest, daemon=True).start()
        threading.Thread(target=self._run_capability, daemon=True).start()

    # ---------- 背景 ----------
    def _load_bg(self):
        for name in ("hutao_bg_soft.jpg", "hutao_bg.jpg", "hutao_bg.png"):
            p = core.asset_path(name)
            if os.path.isfile(p):
                pm = QPixmap(p)
                if not pm.isNull():
                    return pm
        return QPixmap()

    def _bg_pixmap(self):
        if self._bg.isNull():
            return QPixmap()
        key = (self.width(), self.height())
        if getattr(self, "_bg_cache_key", None) == key:
            return self._bg_cache
        # cover：右对齐裁切，尽量露出右侧的胡桃
        bw, bh = self._bg.width(), self._bg.height()
        scale = max(self.width() / bw, self.height() / bh)
        sw, sh = int(bw * scale + 0.5), int(bh * scale + 0.5)
        pm = self._bg.scaled(sw, sh, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        x = max(0, sw - self.width())
        y = max(0, (sh - self.height()) // 2)
        self._bg_cache = pm.copy(x, y, self.width(), self.height())
        self._bg_cache_key = key
        return self._bg_cache

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(0, 0, self.width(), self.height())
        radius = 0 if self._maximized else 20
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        p.setClipPath(path)
        bg = self._bg_pixmap()
        if not bg.isNull():
            p.drawPixmap(0, 0, bg)
        # 暗色渐变，保证文字可读
        g = QLinearGradient(0, 0, self.width() * 0.9, self.height())
        g.setColorAt(0.0, QColor(10, 7, 10, 228))
        g.setColorAt(0.45, QColor(14, 9, 13, 205))
        g.setColorAt(1.0, QColor(8, 6, 9, 232))
        p.fillRect(rect, g)
        # 氛围光
        g2 = QRadialGradient(QPointF(self.width() * 0.85, self.height() * 0.25), self.width() * 0.65)
        g2.setColorAt(0.0, QColor(213, 85, 115, 47))
        g2.setColorAt(1.0, QColor(213, 85, 115, 0))
        p.fillRect(rect, g2)
        g3 = QRadialGradient(QPointF(self.width() * 0.10, self.height() * 0.90), self.width() * 0.55)
        g3.setColorAt(0.0, QColor(230, 152, 88, 35))
        g3.setColorAt(1.0, QColor(230, 152, 88, 0))
        p.fillRect(rect, g3)
        # 玻璃底
        p.fillPath(path, QColor(10, 8, 12, 70))
        # 顶部高光 + 边框
        gh = QLinearGradient(0, 0, 0, 200)
        gh.setColorAt(0, QColor(255, 245, 238, 20))
        gh.setColorAt(1, QColor(255, 245, 238, 0))
        p.fillRect(QRectF(1, 1, self.width() - 2, 200), gh)
        p.setPen(QPen(QColor(255, 240, 232, 40), 1.2))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        p.end()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if hasattr(self, "panel"):
            self.panel.setVisible(self.width() >= 960)
        if hasattr(self, "lbl_vram"):
            narrow = self.width() < 900
            self.lbl_vram.setVisible(not narrow)
            self.lbl_engine_status.setVisible(self.width() >= 780)
            self._refresh_backend_chip()
            self._update_hw()
        self.update()

    def showEvent(self, e):
        super().showEvent(e)
        if not self._acrylic_ok:
            self._acrylic_ok = apply_acrylic(int(self.winId()))
        if not self._placed:
            self._placed = True
            scr = QApplication.primaryScreen().availableGeometry()
            self.move(scr.x() + (scr.width() - self.width()) // 2,
                      scr.y() + (scr.height() - self.height()) // 2)

    # ---------- 窗口控制 ----------
    def toggle_max(self):
        if self._maximized:
            self._maximized = False
            self.btn_max.setText(CAP_MAX)
            if self._normal_geo:
                self.setGeometry(self._normal_geo)
            self.update()
        else:
            self._normal_geo = self.geometry()
            self._maximized = True
            self.btn_max.setText(CAP_RESTORE)
            self.setGeometry(QApplication.primaryScreen().availableGeometry())
            self.update()

    def close_clicked(self):
        if self._running and self._stop is not None:
            self._stop.set()
        self.close()

    def closeEvent(self, e):
        if self._stop is not None:
            self._stop.set()
        self._timer.stop()
        self._hw.stop()
        e.accept()

    # ---------- 界面 ----------
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.title_bar = TitleBar(self)
        root.addWidget(self.title_bar)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        content.setAttribute(Qt.WA_TranslucentBackground, True)
        hl = QHBoxLayout(content)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(0)
        left = QWidget()
        left.setAttribute(Qt.WA_TranslucentBackground, True)
        bl = QVBoxLayout(left)
        bl.setContentsMargins(32, 12, 18, 20)
        bl.setSpacing(14)
        hl.addWidget(left, 58)
        self.panel = ImagePanel()
        hl.addWidget(self.panel, 42)

        self.lbl_h1 = QLabel()
        self.lbl_h1.setObjectName("H1")
        bl.addWidget(self.lbl_h1)

        # 压缩包
        card1 = Card()
        l1 = QVBoxLayout(card1)
        l1.setContentsMargins(16, 12, 16, 14)
        l1.setSpacing(8)
        self.lbl_archive = QLabel()
        self.lbl_archive.setObjectName("Section")
        l1.addWidget(self.lbl_archive)
        row = QHBoxLayout()
        row.setSpacing(10)
        self.ent_archive = QLineEdit()
        self.ent_archive.setMinimumHeight(40)
        row.addWidget(self.ent_archive, 1)
        self.btn_browse = QPushButton()
        self.btn_browse.setMinimumHeight(40)
        self.btn_browse.clicked.connect(self._browse_archive)
        row.addWidget(self.btn_browse)
        l1.addLayout(row)
        bl.addWidget(card1)

        # 引擎 + 操作
        card2 = Card()
        l2 = QVBoxLayout(card2)
        l2.setContentsMargins(16, 14, 16, 16)
        l2.setSpacing(12)
        top = QHBoxLayout()
        top.setSpacing(8)
        self.lbl_engine = QLabel()
        self.lbl_engine.setObjectName("Section")
        top.addWidget(self.lbl_engine)
        self.cmb_engine = QComboBox()
        self.cmb_engine.setMinimumHeight(36)
        self.cmb_engine.setMinimumWidth(140)
        self.cmb_engine.currentIndexChanged.connect(self._engine_changed)
        top.addWidget(self.cmb_engine)
        self.btn_advanced = QPushButton()
        self.btn_advanced.setMinimumHeight(36)
        self.btn_advanced.setMinimumWidth(72)
        self.btn_advanced.clicked.connect(self._open_advanced)
        top.addWidget(self.btn_advanced)
        self.btn_cap = QPushButton()
        self.btn_cap.setMinimumHeight(36)
        self.btn_cap.setMinimumWidth(72)
        self.btn_cap.clicked.connect(self._open_capability)
        top.addWidget(self.btn_cap)
        top.addStretch(1)
        self.badge_engine = QLabel()
        self.badge_engine.setObjectName("Badge")
        top.addWidget(self.badge_engine)
        l2.addLayout(top)

        run = QHBoxLayout()
        run.setSpacing(10)
        self.btn_start = QPushButton()
        self.btn_start.setObjectName("Primary")
        self.btn_start.setMinimumHeight(50)
        self.btn_start.setMinimumWidth(180)
        self.btn_start.clicked.connect(self._start)
        run.addWidget(self.btn_start)
        self.btn_stop = QPushButton()
        self.btn_stop.setMinimumHeight(50)
        self.btn_stop.setMinimumWidth(96)
        self.btn_stop.clicked.connect(self._stop_clicked)
        run.addWidget(self.btn_stop)
        run.addStretch(1)
        self.lbl_status = QLabel()
        self.lbl_status.setObjectName("Hint")
        self.lbl_status.setMinimumWidth(90)
        self.lbl_status.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        run.addWidget(self.lbl_status)
        l2.addLayout(run)

        self.progress = QProgressBar()
        self.progress.setRange(0, 10000)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(12)
        l2.addWidget(self.progress)

        self.lbl_stage = QLabel("")
        self.lbl_stage.setObjectName("Status")
        l2.addWidget(self.lbl_stage)
        stats = QHBoxLayout()
        stats.setSpacing(18)
        self.lbl_attempts = QLabel("")
        self.lbl_speed = QLabel("")
        self.lbl_elapsed = QLabel("")
        self.lbl_remaining = QLabel("")
        for w in (self.lbl_attempts, self.lbl_speed, self.lbl_elapsed, self.lbl_remaining):
            w.setObjectName("Status")
            stats.addWidget(w)
        stats.addStretch(1)
        l2.addLayout(stats)
        bl.addWidget(card2)

        # 结果
        card3 = Card()
        rl = QHBoxLayout(card3)
        rl.setContentsMargins(16, 12, 16, 14)
        rl.setSpacing(10)
        left = QVBoxLayout()
        left.setSpacing(6)
        self.lbl_result = QLabel()
        self.lbl_result.setObjectName("ResultLabel")
        left.addWidget(self.lbl_result)
        self.ent_password = QLineEdit()
        self.ent_password.setReadOnly(True)
        self.ent_password.setFont(QFont("Consolas", 16, QFont.Bold))
        self.ent_password.setMinimumHeight(46)
        left.addWidget(self.ent_password)
        rl.addLayout(left, 1)
        self.btn_copy = QPushButton()
        self.btn_copy.setMinimumHeight(46)
        self.btn_copy.clicked.connect(self._copy_password)
        rl.addWidget(self.btn_copy)
        self.btn_extract = QPushButton()
        self.btn_extract.setMinimumHeight(46)
        self.btn_extract.clicked.connect(self._extract)
        rl.addWidget(self.btn_extract)
        bl.addWidget(card3)

        # 日志
        card4 = Card()
        ll = QVBoxLayout(card4)
        ll.setContentsMargins(16, 12, 16, 14)
        ll.setSpacing(6)
        self.lbl_log = QLabel()
        self.lbl_log.setObjectName("Section")
        ll.addWidget(self.lbl_log)
        self.txt_log = QPlainTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setMaximumBlockCount(400)
        self.txt_log.setFixedHeight(96)
        ll.addWidget(self.txt_log)
        bl.addWidget(card4)
        bl.addStretch(1)

        self.scroll.setWidget(content)
        root.addWidget(self.scroll, 1)

        # 底部状态栏
        bar = QFrame()
        bar.setStyleSheet(
            "QFrame { background: rgba(6, 5, 8, 0.46); "
            "border-top: 1px solid rgba(255, 235, 225, 0.08); }")
        bar.setFixedHeight(38)
        sl = QHBoxLayout(bar)
        sl.setContentsMargins(20, 0, 16, 0)
        sl.setSpacing(16)
        self.lbl_cpu = QLabel()
        self.lbl_cpu.setStyleSheet("color: rgba(255, 232, 222, 0.54); font-size: 12px;")
        sl.addWidget(self.lbl_cpu)
        sl.addSpacing(2)
        # 加速后端标签（CPU / OpenCL / CUDA），紧挨 CPU 指标
        self.lbl_backend = QLabel()
        self.lbl_backend.setObjectName("Backend")
        self.lbl_backend.setStyleSheet(backend_chip_style("probing"))
        self.lbl_backend.setToolTip("")
        sl.addWidget(self.lbl_backend)
        sl.addSpacing(2)
        self.lbl_ram = QLabel()
        self.lbl_gpu = QLabel()
        self.lbl_vram = QLabel()
        for w in (self.lbl_ram, self.lbl_gpu, self.lbl_vram):
            w.setStyleSheet("color: rgba(255, 232, 222, 0.54); font-size: 12px;")
            sl.addWidget(w)
            sl.addSpacing(2)
        sl.addStretch(1)
        self.lbl_engine_status = QLabel()
        self.lbl_engine_status.setStyleSheet("color: rgba(255, 232, 222, 0.38); font-size: 12px;")
        sl.addWidget(self.lbl_engine_status)
        self.btn_lang_zh = QPushButton("中")
        self.btn_lang_en = QPushButton("EN")
        for b in (self.btn_lang_zh, self.btn_lang_en):
            b.setObjectName("LangBtn")
            b.setFixedHeight(26)
            b.setFixedWidth(44)
        self.btn_lang_zh.clicked.connect(lambda: self._set_lang("zh"))
        self.btn_lang_en.clicked.connect(lambda: self._set_lang("en"))
        sl.addWidget(self.btn_lang_zh)
        sl.addWidget(self.btn_lang_en)
        root.addWidget(bar)

        self._tr_widgets = [
            (self.title_bar.lbl_name, "app_name"),
            (self.lbl_h1, "h1"),
            (self.lbl_archive, "archive"),
            (self.btn_browse, "browse"),
            (self.lbl_engine, "engine"),
            (self.btn_start, "start"),
            (self.btn_stop, "stop"),
            (self.lbl_result, "result"),
            (self.btn_copy, "copy"),
            (self.btn_extract, "extract"),
            (self.lbl_log, "log"),
        ]
        self._engine_changed(self.cmb_engine.currentIndex())

    def _apply_lang(self):
        t = TEXTS[self.lang]
        for w, key in self._tr_widgets:
            w.setText(t[key])
        self.ent_archive.setPlaceholderText(t["archive_ph"])
        self.ent_password.setPlaceholderText(t["password_ph"])
        for btn, code in ((self.btn_lang_zh, "zh"), (self.btn_lang_en, "en")):
            btn.setObjectName("LangBtnActive" if self.lang == code else "LangBtn")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self.btn_advanced.setText(_tr(self.lang, "高级", "Advanced"))
        self.btn_cap.setText(_tr(self.lang, "能力", "Capacity"))
        idx = max(0, self.cmb_engine.currentIndex())
        self.cmb_engine.blockSignals(True)
        self.cmb_engine.clear()
        self.cmb_engine.addItems([t["auto"], t["cpu"], t["gpu"]])
        self.cmb_engine.setCurrentIndex(min(idx, 2))
        self.cmb_engine.blockSignals(False)
        self.cmb_engine.setToolTip(t["gpu_tip"])
        self.btn_advanced.setText(_tr(self.lang, "高级", "Advanced"))
        self.btn_cap.setText(_tr(self.lang, "能力", "Capacity"))
        self.btn_advanced.setToolTip(_tr(self.lang, "攻击方式、字符集、长度、字典",
                                         "Attack mode, charset, length, wordlist"))
        self.btn_cap.setToolTip(_tr(self.lang, "本机 24 小时能覆盖的密码长度",
                                    "Password lengths this machine can cover in 24h"))
        if self.lang == "en":
            self.setWindowTitle(core.APP_NAME_EN)
        else:
            self.setWindowTitle(core.APP_NAME_ZH)
        self._refresh_badge()
        self._refresh_status()
        self._refresh_stage()
        self._refresh_stats()
        self._refresh_backend_chip()
        self._render_log()

    def _set_lang(self, lang):
        if self._running or lang == self.lang:
            return
        self.lang = lang
        self._apply_lang()

    def _t(self, key):
        return TEXTS[self.lang].get(key, TEXTS["zh"].get(key, key))

    # ---------- 状态栏 ----------
    def _update_hw(self):
        s = self._hw.snapshot()
        t = TEXTS[self.lang]
        self.lbl_cpu.setText("CPU %d%%" % int(s["cpu"]))
        self.lbl_ram.setText("%s %.1f / %.1f GB" % (t["ram"], s["ram_used"] / 1024 ** 3,
                                                   s["ram_total"] / 1024 ** 3))
        gpu = s.get("gpu_name") or "--"
        if self.width() < 980 and len(gpu) > 26:
            gpu = gpu[:25] + "…"
        self.lbl_gpu.setText("GPU %s %d%%" % (gpu, int(s.get("gpu_util", 0))))
        self.lbl_vram.setText("%s %.1f / %.1f GB" % (t["vram"], s.get("vram_used", 0) / 1024 ** 3,
                                                     s.get("vram_total", 0) / 1024 ** 3))

    # ---------- 启动自检：加速后端（CPU / OpenCL / CUDA） ----------
    def _run_selftest(self):
        try:
            res = core.quick_backend_check()
        except Exception as e:  # 自检本身绝不能崩界面
            res = {"backend": "cpu", "ok": False, "error": str(e), "rate": 0.0,
                   "name": "", "vendor": "", "cc": "", "detail": "", "elapsed": 0.0,
                   "build_ms": 0.0, "tried": []}
        try:
            self._bridge.emit_event({"type": "selftest", "result": res})
        except Exception:
            pass

    def _apply_selftest(self, res):
        self._selftest = res or {}
        self._refresh_backend_chip()
        log = self._selftest_log_text()
        if log:
            self._boot_logs = [log]
            self._log_entries = [log] + [e for e in self._log_entries if e not in
                                         [log]]
            self._render_log()
        self._selftest_event.set()
        if not self._no_popup and self._cap_dialog is None:
            QTimer.singleShot(250, self._show_capability)

    # ---------- 能力评估 ----------
    def _run_capability(self, force=False):
        if self._no_popup and not force:
            return
        try:
            self._selftest_event.wait(30)
            if force:
                capability.benchmark_hashcat()
            rates = capability.measure(self._selftest or {})
        except Exception:
            rates = {"zip": float((self._selftest or {}).get("rate") or 0),
                     "zip_aes": None, "7z": None,
                     "device": (self._selftest or {}).get("name") or ""}
        try:
            self._bridge.emit_event({"type": "capability", "rates": rates})
        except Exception:
            pass

    def _show_capability(self):
        if self._cap_dialog is not None:
            return
        rates = dict(self._cap_rates)
        rates.setdefault("zip", float((self._selftest or {}).get("rate") or 0))
        rates.setdefault("device", (self._selftest or {}).get("name") or "")
        dlg = CapabilityDialog(self, self.lang, rates)
        dlg.remeasure.connect(lambda: threading.Thread(
            target=self._run_capability, args=(True,), daemon=True).start())
        dlg.finished.connect(self._cap_dialog_closed)
        self._cap_dialog = dlg
        dlg.show()

    def _cap_dialog_closed(self, *_a):
        self._cap_dialog = None

    def _open_capability(self):
        self._show_capability()

    def _current_rate_hint(self):
        res = self._selftest or {}
        try:
            return float(res.get("rate") or 0)
        except Exception:
            return 0.0

    def _rate_for_archive(self):
        """按当前压缩包格式选择参考速度，返回 (rate, 名称)。"""
        archive = self.ent_archive.text().strip().strip('"')
        kind = core.detect_kind(archive) if os.path.isfile(archive) else None
        if kind == "zip":
            try:
                import hashcat_gpu
                if hashcat_gpu.zip_aes_hash(archive):
                    return float(self._cap_rates.get("zip_aes") or 0), "ZIP AES"
            except Exception:
                pass
            return (float(self._cap_rates.get("zip") or 0)
                    or self._current_rate_hint()), "ZIP"
        if kind == "7z":
            return float(self._cap_rates.get("7z") or 0), "7z"
        if kind == "rar":
            rate = float(self._cap_rates.get("rar5") or 0)
            return (rate, "RAR5") if rate else (240.0, "RAR CPU")
        return (float(self._cap_rates.get("zip") or 0)
                or self._current_rate_hint()), "ZIP"

    def _open_advanced(self):
        if self._running:
            return
        rate, name = self._rate_for_archive()
        dlg = AdvancedDialog(self, self.lang, self._adv_opts, rate)
        dlg.set_ref_name(name)
        self._adv_dialog = dlg
        try:
            if dlg.exec() == QDialog.Accepted:
                self._adv_opts = dlg.result_opts()
                self._add_log(_tr(self.lang,
                                  "高级设置：%s" % self._adv_desc(),
                                  "Advanced: %s" % self._adv_desc()))
        finally:
            self._adv_dialog = None

    def _adv_desc(self):
        o = self._adv_opts
        attack = o.get("attack", "auto")
        if attack == "dict":
            return _tr(self.lang, "仅字典", "dictionary only")
        if attack == "space":
            return _tr(self.lang, "字符集 %s，%d–%d 位" % (o.get("charset", ""),
                                                          o.get("minlen", 1), o.get("maxlen", 8)),
                       "charset %s, %d-%d" % (o.get("charset", ""),
                                              o.get("minlen", 1), o.get("maxlen", 8)))
        if o.get("unlimited") or o.get("expect") is None:
            return _tr(self.lang, "无限（数字/混合按位交替）", "unlimited (interleaved)")
        try:
            seconds = float(o.get("expect") or 120)
        except Exception:
            seconds = 120
        return _tr(self.lang, "自动，期望 %s" % fmt_elapsed(seconds).strip(),
                   "auto, target %s" % fmt_elapsed(seconds).strip())

    def _selftest_log_text(self):
        res = self._selftest or {}
        if not res:
            return None
        backend = (res.get("backend") or "cpu").lower()
        name = res.get("name") or ""
        rate = fmt_rate_chip(res.get("rate") or 0) or "--"
        elapsed = float(res.get("elapsed") or 0)
        if not res.get("ok"):
            err = res.get("error") or ("未知原因" if self.lang == "zh" else "unknown")
            return {
                "zh": "启动自检：%s（改用 CPU 引擎）" % err,
                "en": "Startup self-test: %s (CPU engine)" % err,
            }
        if backend == "cuda":
            cc = res.get("cc") or ""
            return {
                "zh": "启动自检：CUDA 可用（%s %s，实测 %s，%.2f 秒）"
                      % (name, cc, rate, elapsed),
                "en": "Startup self-test: CUDA ready (%s %s, %s, %.2fs)"
                      % (name, cc, rate, elapsed),
            }
        if backend == "opencl":
            return {
                "zh": "启动自检：OpenCL 可用（%s，实测 %s，%.2f 秒）" % (name, rate, elapsed),
                "en": "Startup self-test: OpenCL ready (%s, %s, %.2fs)" % (name, rate, elapsed),
            }
        return {
            "zh": "启动自检：未检测到可用 GPU，使用 CPU 多线程引擎（实测 %s）" % rate,
            "en": "Startup self-test: no usable GPU, using CPU engine (%s)" % rate,
        }

    def _backend_tooltip(self):
        res = self._selftest
        zh = self.lang != "en"
        if res is None:
            return ("正在检测加速后端：CUDA → OpenCL → CPU（约 1 秒）" if zh else
                    "Detecting acceleration backend: CUDA → OpenCL → CPU (~1s)")
        backend = (res.get("backend") or "cpu").lower()
        label = {"cuda": "CUDA", "opencl": "OpenCL"}.get(backend, "CPU")
        lines = []
        if res.get("ok"):
            lines.append(("加速后端：%s" % label) if zh else ("Backend: %s" % label))
        else:
            lines.append(("加速后端：CPU（GPU 自检未通过）" if zh else
                          "Backend: CPU (GPU self-test failed)"))
        name = res.get("name") or ""
        if name:
            lines.append(("设备：%s" % name) if zh else ("Device: %s" % name))
        if res.get("cc"):
            lines.append(("算力：%s" % res["cc"]) if zh else ("Compute: %s" % res["cc"]))
        if res.get("detail"):
            lines.append(("详情：%s" % res["detail"]) if zh else ("Detail: %s" % res["detail"]))
        rate = fmt_rate_chip(res.get("rate") or 0)
        if rate and res.get("ok"):
            lines.append(("实测吞吐：%s" % rate) if zh else ("Measured: %s" % rate))
        if res.get("elapsed"):
            lines.append(("自检耗时：%.2f 秒" % float(res["elapsed"])) if zh else
                         ("Self-test time: %.2fs" % float(res["elapsed"])))
        if res.get("error"):
            lines.append(("错误：%s" % res["error"]) if zh else ("Error: %s" % res["error"]))
        for item in res.get("tried") or []:
            if item.get("ok") or not item.get("error"):
                continue
            who = {"cuda": "CUDA", "opencl": "OpenCL"}.get(item.get("backend"), item.get("backend"))
            lines.append(("· %s 自检失败：%s" % (who, item["error"])) if zh else
                         ("· %s self-test failed: %s" % (who, item["error"])))
        return "\n".join(lines)

    def _refresh_backend_chip(self):
        if not hasattr(self, "lbl_backend"):
            return
        res = self._selftest
        if res is None:
            state = "probing"
            text = "⚡ " + self._t("backend_probing")
        else:
            backend = (res.get("backend") or "cpu").lower()
            state = backend if backend in ("cuda", "opencl") and res.get("ok") else "cpu"
            label = {"cuda": "CUDA", "opencl": "OpenCL"}.get(state, "CPU")
            rate = ""
            if res.get("ok") and self.width() >= 980:
                rate = fmt_rate_chip(res.get("rate") or 0)
            text = "⚡ " + label + (("  " + rate) if rate else "")
        self.lbl_backend.setText(text)
        self.lbl_backend.setStyleSheet(backend_chip_style(state))
        self.lbl_backend.setToolTip(self._backend_tooltip())

    # ---------- 动态文本 ----------
    def _refresh_badge(self):
        name = self._engine_name[1] if self.lang == "en" else self._engine_name[0]
        name = name or self._t("badge_none")
        self.badge_engine.setText(self._t("badge_engine") % name)

    def _refresh_status(self):
        self.lbl_status.setText(self._t(self._result_state))

    def _refresh_stage(self):
        if not self._stage_idx:
            self.lbl_stage.setText("")
            return
        label = self._stage[1] if self.lang == "en" else self._stage[0]
        self.lbl_stage.setText("%s %d/%d · %s" % (
            self._t("stage"), self._stage_idx, self._stage_count, label))

    def _refresh_stats(self):
        p = self._last_progress
        t = self._t
        if self._unlimited:
            self.lbl_attempts.setText("%s %s" % (t("attempts"),
                                                 core.fmt_num(p.get("done", 0))))
            self.lbl_remaining.setText("%s --" % t("remaining"))
        else:
            self.lbl_attempts.setText("%s %s / %s" % (
                t("attempts"), core.fmt_num(p.get("done", 0)),
                core.fmt_num(self._total)))
            self.lbl_remaining.setText("%s %s" % (t("remaining"),
                                                  core.fmt_eta(p.get("eta"))))
        self.lbl_speed.setText("%s %s" % (t("speed"), core.fmt_rate(p.get("rate", 0))))
        self.lbl_elapsed.setText("%s %s" % (t("elapsed"), fmt_elapsed(p.get("elapsed", 0))))

    # ---------- 日志 ----------
    def _add_log(self, zh, en=None):
        self._log_entries.append({"zh": zh, "en": en or zh})
        self._render_log()

    def _render_log(self):
        self.txt_log.clear()
        for e in self._log_entries[-200:]:
            self.txt_log.appendPlainText(e["en"] if self.lang == "en" else e["zh"])

    # ---------- 交互 ----------
    def _browse_archive(self):
        p, _ = QFileDialog.getOpenFileName(
            self, self._t("archive"), "",
            "Archives (*.zip *.rar *.7z *.001 *.z01 *.tar *.gz *.tgz *.xz *.bz2 *.cab *.iso *.arj *.lzh *.z *.wim);;All files (*.*)")
        if p:
            self.ent_archive.setText(p)

    def _engine_changed(self, idx):
        names = (self._t("auto"), self._t("cpu"), self._t("gpu"))
        name = names[min(max(idx, 0), 2)]
        res = self._selftest or {}
        backend = (res.get("backend") or "cpu").lower()
        hint = ""
        if idx == 2 and not (backend in ("cuda", "opencl") and res.get("ok")):
            hint = _tr(self.lang, "（没检测到 GPU，会回退 CPU）",
                       " (no GPU detected, CPU fallback)")
        self.lbl_engine_status.setText(name + hint)

    def _collect(self):
        archive = self.ent_archive.text().strip().strip('"')
        if not os.path.isfile(archive):
            QMessageBox.warning(self, self._t("app_name"), self._t("warn_archive"))
            return None
        opts = {
            "archive": archive,
            "engine": ("auto", "cpu", "gpu")[max(0, self.cmb_engine.currentIndex())],
            "workers": core.default_workers(),
        }
        o = self._adv_opts or {}
        opts.update({
            "attack": o.get("attack", "auto"),
            "expect": o.get("expect", 120),
            "unlimited": bool(o.get("unlimited")),
            "digits_max": o.get("digits_max"),
            "mixed_max": o.get("mixed_max"),
            "charset": o.get("charset") or "",
            "minlen": int(o.get("minlen") or 1),
            "maxlen": int(o.get("maxlen") or 8),
            "wordlist": o.get("wordlist") or "",
        })
        return opts

    def _start(self):
        if self._running:
            return
        opts = self._collect()
        if opts is None:
            return
        self._found = None
        self._result_state = "searching"
        self._stage_idx = 0
        self._stage = ("", "")
        self._engine_name = ("", "")
        self._total = 0
        self._last_progress = {"rate": 0, "elapsed": 0, "eta": None, "done": 0}
        self._unlimited = False
        self.ent_password.setText("")
        self.btn_copy.setEnabled(False)
        self.btn_extract.setEnabled(False)
        self.progress.setRange(0, 10000)
        self.progress.setValue(0)
        self._log_entries = list(self._boot_logs)
        self._render_log()
        self._add_log(self._t("log_start"))
        self._refresh_badge()
        self._refresh_status()
        self._refresh_stage()
        self._refresh_stats()
        self._stop = threading.Event()
        self._set_running(True)
        self._thread = EngineThread(self._bridge, opts, self._stop)
        self._thread.start()

    def _stop_clicked(self):
        if self._stop is not None:
            self._stop.set()
            self.lbl_status.setText(self._t("stopped"))
            self.btn_stop.setEnabled(False)

    def _set_running(self, running):
        self._running = running
        self.btn_start.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        self.btn_lang_zh.setEnabled(not running)
        self.btn_lang_en.setEnabled(not running)
        for w in (self.ent_archive, self.btn_browse, self.cmb_engine,
                  self.btn_advanced, self.btn_cap):
            w.setEnabled(not running)

    # ---------- 事件 ----------
    def _on_event(self, msg):
        t = msg.get("type")
        if t == "selftest":
            self._apply_selftest(msg.get("result") or {})
            return
        if t == "capability":
            rates = msg.get("rates") or {}
            self._cap_rates = rates
            if self._cap_dialog is not None:
                self._cap_dialog.update_rates(rates)
            if self._adv_dialog is not None:
                rate, name = self._rate_for_archive()
                self._adv_dialog.update_rate(rate, name)
            return
        if t == "space":
            self._total = int(msg.get("total") or 0)
            self._unlimited = bool(msg.get("unlimited"))
            self._refresh_stats()
        elif t == "stage":
            self._stage_idx = int(msg.get("index", 0))
            self._stage_count = int(msg.get("count", 0))
            self._stage = (msg.get("label_zh", ""), msg.get("label_en", ""))
            self._refresh_stage()
        elif t == "engine":
            self._engine_name = (msg.get("name", ""), msg.get("en", msg.get("name", "")))
            self._refresh_badge()
            self._add_log(msg.get("name", ""), msg.get("en"))
        elif t == "log":
            self._add_log(msg.get("text", ""), msg.get("en"))
        elif t == "progress":
            self._last_progress = {
                "done": int(msg.get("done", 0)),
                "rate": msg.get("rate", 0),
                "elapsed": msg.get("elapsed", 0),
                "eta": msg.get("eta"),
            }
            total = max(1, int(msg.get("total", 1)))
            if self._unlimited:
                self.progress.setRange(0, 0)
            else:
                self.progress.setRange(0, 10000)
                self.progress.setValue(
                    min(10000, int(self._last_progress["done"] * 10000 / total)))
            self._refresh_stats()
            if self._stage_idx == 0 and msg.get("stage_index"):
                self._stage_idx = int(msg["stage_index"])
                self._stage_count = int(msg.get("stage_count", 0))
                self._stage = (msg.get("stage_zh", ""), msg.get("stage_en", ""))
                self._refresh_stage()
            self.lbl_status.setText(self._t("searching"))
        elif t == "found":
            self._found = msg.get("password")
            self.ent_password.setText(self._found or "")
            self.btn_copy.setEnabled(True)
            self.btn_extract.setEnabled(True)
            self._add_log(self._t("log_found") % (
                self._found, core.fmt_num(msg.get("attempts", 0)),
                fmt_elapsed(msg.get("elapsed", 0))))
        elif t == "done":
            self._finish(msg.get("result", {}))
        elif t == "error":
            self._add_log(msg.get("message", ""))
            QMessageBox.critical(self, self._t("error"), msg.get("message", ""))
            self._set_running(False)
            self._result_state = "not_found"
            self._refresh_status()
        elif t == "extracted":
            msgbox = QMessageBox(self)
            if msg.get("ok"):
                msgbox.information(self, self._t("app_name"),
                                   self._t("info_extracted") + msg.get("path", ""))
            else:
                msgbox.warning(self, self._t("app_name"),
                               self._t("extract_fail") + msg.get("message", ""))

    def _finish(self, result):
        self._set_running(False)
        if result.get("found"):
            self._result_state = "done"
            self._found = result.get("password") or self._found
            self.ent_password.setText(self._found or "")
            self.btn_copy.setEnabled(True)
            self.btn_extract.setEnabled(True)
            self.progress.setValue(min(10000, int(10000 * min(
                result.get("attempts", 0), max(1, self._total)) / max(1, self._total))))
            elapsed = result.get("elapsed", 0)
            attempts = result.get("attempts", 0)
            self._last_progress.update({"done": attempts, "elapsed": elapsed,
                                        "rate": attempts / elapsed if elapsed else 0, "eta": None})
            self._refresh_stats()
        else:
            reason = result.get("reason")
            if reason == "not_encrypted":
                self._result_state = "not_encrypted"
                QMessageBox.information(self, self._t("app_name"), self._t("info_not_encrypted"))
            elif reason == "stopped":
                self._result_state = "stopped"
            else:
                self._result_state = "not_found"
                QMessageBox.information(self, self._t("app_name"), self._t("info_not_found"))
        self._refresh_status()

    def _copy_password(self):
        if self._found:
            QApplication.clipboard().setText(self._found)
            self._add_log(self._t("log_copied"))

    def _extract(self):
        if not self._found:
            return
        archive = self.ent_archive.text().strip().strip('"')
        out = QFileDialog.getExistingDirectory(self, self._t("extract"),
                                               os.path.dirname(archive) or "")
        if not out:
            return
        target = os.path.join(out, os.path.splitext(os.path.basename(archive))[0] + "_解压")
        pw = self._found

        def work():
            ok, message = core.SevenZip().extract(archive, pw, target)
            self._bridge.emit_event({"type": "extracted", "ok": ok, "message": message,
                                     "path": target})

        threading.Thread(target=work, daemon=True).start()

    # ---------- 拖拽 ----------
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        for url in e.mimeData().urls():
            p = url.toLocalFile()
            if p and os.path.isfile(p):
                self.ent_archive.setText(p)
                break


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def cli_test(archive, engine="auto", out_path=None):
    import threading
    opts = {"archive": archive, "engine": engine, "workers": core.default_workers()}
    logs = []

    def emit(m):
        t = m.get("type")
        if t in ("log", "engine", "stage", "found", "progress", "space"):
            if t in ("log", "engine", "stage", "found"):
                logs.append(m)
            try:
                if t == "log":
                    print("LOG:", m.get("text"))
                elif t == "engine":
                    print("ENGINE:", m.get("name"))
                elif t == "stage":
                    print("STAGE:", m.get("label_zh"))
                elif t == "found":
                    print("FOUND:", m.get("password"))
            except Exception:
                pass

    result = core.run_auto_search(opts, emit, threading.Event())
    try:
        print("RESULT:", result.get("reason"), "password=", result.get("password"),
              "attempts=", result.get("attempts"), "elapsed=%.2fs" % result.get("elapsed", 0))
    except Exception:
        pass
    if out_path:
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump({"result": result, "logs": logs}, f, ensure_ascii=False, indent=1)
        except Exception:
            pass
    return 0 if result.get("found") else 1


def ui_scale():
    """4K 屏幕且系统缩放较小时，放大 UI；1080p/800x600 保持 1.0。"""
    try:
        if os.name != "nt":
            return 1.0
        user32 = ctypes.windll.user32
        w = user32.GetSystemMetrics(0)
        h = user32.GetSystemMetrics(1)
        try:
            dpi = ctypes.windll.user32.GetDpiForSystem()
        except Exception:
            dpi = 96
        logical_h = h * 96.0 / max(96, dpi)
        return max(1.0, min(1.8, logical_h / 1400.0))
    except Exception:
        return 1.0


def main(argv=None):
    argv = list(argv or sys.argv)
    if "--selftest" in argv:
        # 无界面自检：打印各后端探测结果，方便在 N 卡机器上验证
        import json
        out_path = argv[argv.index("--out") + 1] if "--out" in argv else None
        res = core.quick_backend_check()
        text = json.dumps(res, ensure_ascii=False, indent=1)
        if out_path:
            try:
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(text)
            except Exception as e:
                print("write failed:", e)
        try:
            print(text)
        except Exception:
            pass
        return 0 if res.get("ok") else 1
    if "--capability" in argv:
        # 无界面能力评估：便于在别的机器上快速看能跑多少位
        import json
        out_path = argv[argv.index("--out") + 1] if "--out" in argv else None
        selftest = core.quick_backend_check()
        rates = capability.measure(selftest)
        payload = {"selftest": selftest, "rates": rates,
                   "rows": capability.rows(rates, capability.DEFAULT_BUDGET)}
        text = json.dumps(payload, ensure_ascii=False, indent=1)
        if out_path:
            try:
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(text)
            except Exception as e:
                print("write failed:", e)
        print(text)
        return 0
    if "--cli-test" in argv:
        archive = argv[argv.index("--cli-test") + 1]
        engine = argv[argv.index("--engine") + 1] if "--engine" in argv else "auto"
        out_path = argv[argv.index("--out") + 1] if "--out" in argv else None
        return cli_test(archive, engine, out_path=out_path)
    shot = argv[argv.index("--shot") + 1] if "--shot" in argv else None
    demo = argv[argv.index("--demo") + 1] if "--demo" in argv else None
    no_popup = "--no-popup" in argv or shot is not None
    if not demo:
        opts_with_value = {"--shot", "--demo", "--lang", "--size", "--out",
                           "--engine", "--cli-test"}
        i = 1
        while i < len(argv):
            a = argv[i]
            if a in opts_with_value:
                i += 2
                continue
            if not a.startswith("--") and os.path.isfile(a):
                demo = a
                break
            i += 1
    lang = argv[argv.index("--lang") + 1] if "--lang" in argv else "zh"
    force_size = None
    if "--size" in argv:
        try:
            w, h = argv[argv.index("--size") + 1].lower().split("x")
            force_size = (int(w), int(h))
        except Exception:
            force_size = None

    if os.name == "nt":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    scale = ui_scale()
    if scale > 1.01:
        os.environ["QT_SCALE_FACTOR"] = "%.3f" % scale

    app = QApplication([argv[0]])
    app.setApplicationName(core.APP_NAME_ZH)
    app.setWindowIcon(QIcon(os.path.join(core.ASSETS_DIR, "icon.ico")))
    app.setFont(QFont("Microsoft YaHei UI", 10))
    app.setStyleSheet(QSS.replace("%CHEVRON%",
                                  os.path.join(core.ASSETS_DIR, "chevron.png").replace("\\", "/")))
    win = MainWindow(demo_archive=demo, force_size=force_size, lang=lang,
                     show_popup=not no_popup)
    win.show()
    win.raise_()
    win.activateWindow()
    if shot:
        def do_shot():
            pm = win.grab()
            pm.save(shot, "PNG")
            print("screenshot saved:", shot, pm.size())
            app.quit()

        QTimer.singleShot(2000, do_shot)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())






