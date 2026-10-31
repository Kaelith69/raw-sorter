"""Raw Sorter - final (macOS style).  python raw_sorter_final.py --install  adds Start menu + Desktop shortcuts. - split a photo folder into <name>-jpg and <name>-raw.
Requires:  pip install PyQt6      Run:  python raw_sorter_apple.py
"""
import os, sys, time, math, shutil, ctypes, subprocess, tempfile
from pathlib import Path
from PyQt6.QtCore import (Qt, QThread, pyqtSignal, QPropertyAnimation, QEasingCurve,
                          QRectF, QPointF, QUrl, QTimer, QSize, QVariantAnimation, pyqtProperty)
from PyQt6.QtGui import (QPainter, QColor, QPen, QKeySequence, QShortcut, QDesktopServices,
                         QLinearGradient, QPolygonF, QPainterPath, QFont, QPixmap, QIcon)
from PyQt6.QtWidgets import (QApplication, QWidget, QFrame, QLabel, QAbstractButton,
                             QVBoxLayout, QHBoxLayout, QStackedLayout, QFileDialog, QMessageBox,
                             QGraphicsOpacityEffect, QSizePolicy)

A = Qt.AlignmentFlag
JPG = {".jpg", ".jpeg", ".jpe"}
RAW = {".cr2", ".cr3", ".crw", ".nef", ".nrw", ".arw", ".srf", ".sr2", ".raf", ".orf", ".rw2",
       ".pef", ".dng", ".raw", ".rwl", ".iiq", ".3fr", ".erf", ".kdc", ".mrw", ".srw", ".x3f",
       ".gpr", ".fff", ".mef", ".mos", ".dcr"}
BLUE, GREEN, ORANGE = "#007AFF", "#34C759", "#FF9500"   # Apple system colors

QSS = """
* { font-family: "SF Pro Text", "Segoe UI Variable Text", "Segoe UI", "Helvetica Neue", sans-serif;
    font-size: 14px; color: #1D1D1F; }
QLabel { background: transparent; }
QLabel[role="title"] { font-size: 26px; font-weight: 600; }
QLabel[role="huge"]  { font-size: 56px; font-weight: 600; }
QLabel[role="h3"]    { font-size: 15px; font-weight: 600; }
QLabel[role="muted"] { color: #86868B; }
QLabel[role="bar"]   { color: #6E6E73; font-size: 13px; font-weight: 600; }
QFrame#card { background: #FFFFFF; border: 1px solid #E5E5EA; border-radius: 12px; }
QFrame#rule { background: #E5E5EA; border: none; }
"""


# ----------------------------------------------------------------------------- logic
def human(n):
    n = float(n)
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} B" if u == "B" else f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} TB"


def scan(folder):
    """Top-level files only. Returns (jpg, raw, other_count); jpg/raw = [(path, size)]."""
    jpg, raw, other = [], [], 0
    with os.scandir(folder) as it:
        for e in it:
            try:
                if not e.is_file() or e.name.startswith("._"):   # "._" = macOS card leftovers
                    continue
                st = e.stat()
                if getattr(st, "st_file_attributes", 0) & 0x6:     # hidden / system (Windows)
                    continue
                ext = os.path.splitext(e.name)[1].lower()
                item = (e.path, st.st_size)
                if ext in JPG:
                    jpg.append(item)
                elif ext in RAW:
                    raw.append(item)
                else:
                    other += 1
            except OSError:
                continue
    key = lambda t: os.path.basename(t[0]).lower()
    return sorted(jpg, key=key), sorted(raw, key=key), other


def lp(path):
    """Windows long-path form so folders nested past 260 characters still work."""
    path = os.path.abspath(path)
    if sys.platform == "win32" and len(path) > 240 and not path.startswith("\\\\"):
        return "\\\\?\\" + path
    return path


def unique(path):
    if not os.path.exists(lp(path)):
        return path
    stem, ext = os.path.splitext(path)
    i = 1
    while os.path.exists(lp(f"{stem} ({i}){ext}")):
        i += 1
    return f"{stem} ({i}){ext}"


class Mover(QThread):
    progress = pyqtSignal(int, int, str)
    done = pyqtSignal(list, list, bool)  # moved [(src, dst)], failed [(src, reason)], cancelled

    def __init__(self, jobs):
        super().__init__()
        self.jobs, self._stop = jobs, False

    def cancel(self):
        self._stop = True

    def run(self):
        moved, failed, total, last, made = [], [], len(self.jobs), 0.0, set()
        for i, (src, dst) in enumerate(self.jobs, 1):
            if self._stop:
                break
            try:
                folder = os.path.dirname(dst)
                if folder not in made:
                    os.makedirs(lp(folder), exist_ok=True)
                    made.add(folder)
                final = unique(dst)
                shutil.move(lp(src), lp(final))
                moved.append((src, final))
            except Exception as e:
                failed.append((src, str(e)))
            now = time.monotonic()
            if now - last > 0.03 or i == total:
                last = now
                self.progress.emit(i, total, os.path.basename(src))
        self.done.emit(moved, failed, self._stop)


# ----------------------------------------------------------------------------- widgets
def lbl(text="", role=None, center=False, wrap=False):
    l = QLabel(text)
    if role:
        l.setProperty("role", role)
    if center:
        l.setAlignment(A.AlignCenter)
    l.setWordWrap(wrap)
    return l


def mix(a, b, t):
    a, b = QColor(a), QColor(b)
    return QColor(*(int(x + (y - x) * t) for x, y in
                    ((a.red(), b.red()), (a.green(), b.green()), (a.blue(), b.blue()))))


def anim(obj, prop, ms=160, curve=QEasingCurve.Type.OutCubic):
    a = QPropertyAnimation(obj, prop, obj)
    a.setDuration(ms)
    a.setEasingCurve(curve)
    return a


def retarget(a, cur, to):
    a.stop()
    a.setStartValue(cur)
    a.setEndValue(to)
    a.start()


class Button(QAbstractButton):
    """Pill button: color eases on hover, label squeezes slightly on press."""
    def __init__(self, text, kind):
        super().__init__()
        self.setText(text)
        self.kind, self._h, self._p = kind, 0.0, 0.0
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # Enter / Esc drive the keyboard
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.ah, self.ap = anim(self, b"hov", 160), anim(self, b"prs", 100)

    hov = pyqtProperty(float, lambda s: s._h, lambda s, v: (setattr(s, "_h", v), s.update()))
    prs = pyqtProperty(float, lambda s: s._p, lambda s, v: (setattr(s, "_p", v), s.update()))

    def sizeHint(self):
        return QSize(self.fontMetrics().horizontalAdvance(self.text()) + 48, 40)

    def enterEvent(self, e):
        retarget(self.ah, self._h, 1.0)

    def leaveEvent(self, e):
        retarget(self.ah, self._h, 0.0)
        retarget(self.ap, self._p, 0.0)

    def mousePressEvent(self, e):
        super().mousePressEvent(e)
        retarget(self.ap, self._p, 1.0)

    def mouseReleaseEvent(self, e):
        super().mouseReleaseEvent(e)
        retarget(self.ap, self._p, 0.0)

    def changeEvent(self, e):
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QRectF(self.rect()).center()
        sc = 1 - 0.03 * self._p
        p.translate(c)
        p.scale(sc, sc)
        p.translate(-c)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        en, h, d = self.isEnabled(), self._h, self._p
        if self.kind == "primary":
            top = mix(mix("#3C9DFF", "#5AAEFF", h), "#0062D1", d) if en else QColor("#E5E5EA")
            bot = mix(mix("#007AFF", "#1C88FF", h), "#0058BF", d) if en else QColor("#E5E5EA")
            g = QLinearGradient(0, r.top(), 0, r.bottom())
            g.setColorAt(0, top)
            g.setColorAt(1, bot)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(g)
            ink = "#FFFFFF" if en else "#A1A1A6"
        else:
            p.setPen(QPen(mix("#D2D2D7", "#B8B8BF", h), 1))
            p.setBrush(mix(mix("#FFFFFF", "#F5F5F7", h), "#E5E5EA", d))
            ink = "#1D1D1F" if en else "#A1A1A6"
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        f = self.font()
        f.setWeight(QFont.Weight.Medium)
        p.setFont(f)
        p.setPen(QColor(ink))
        p.drawText(QRectF(self.rect()), A.AlignCenter, self.text())


def btn(text, kind):
    return Button(text, kind)


class PillBar(QWidget):
    """Gradient pill progress bar with a soft shine that sweeps while it works."""
    changed = pyqtSignal(float)

    def __init__(self):
        super().__init__()
        self._v, self._ph = 0.0, 0.0
        self.setFixedHeight(10)
        self.tm = QTimer(self)
        self.tm.setInterval(16)
        self.tm.setTimerType(Qt.TimerType.PreciseTimer)
        self.tm.timeout.connect(self._tick)

    def getLevel(self):
        return self._v

    def setLevel(self, v):
        self._v = max(0.0, min(1.0, float(v)))
        self.changed.emit(self._v)
        self.update()

    level = pyqtProperty(float, getLevel, setLevel)

    def showEvent(self, e):
        self.tm.start()

    def hideEvent(self, e):
        self.tm.stop()

    def _tick(self):
        self._ph = (self._ph + 0.014) % 1.5
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        h = r.height()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#E5E5EA"))
        p.drawRoundedRect(r, h / 2, h / 2)
        if self._v <= 0:
            return
        w = max(h, r.width() * self._v)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, w, h), h / 2, h / 2)
        g = QLinearGradient(0, 0, w, 0)
        g.setColorAt(0, QColor("#0A84FF"))
        g.setColorAt(1, QColor("#5AC8FA"))
        p.setBrush(g)
        p.drawPath(path)
        if self._v < 1:
            p.setClipPath(path)
            x = (self._ph - 0.25) * w
            s = QLinearGradient(x - 48, 0, x + 48, 0)
            s.setColorAt(0, QColor(255, 255, 255, 0))
            s.setColorAt(.5, QColor(255, 255, 255, 120))
            s.setColorAt(1, QColor(255, 255, 255, 0))
            p.setBrush(s)
            p.drawRect(QRectF(0, 0, w, h))


class Drop(QWidget):
    """Drop zone: border and tint ease to blue on hover / while dragging; click to browse."""
    clicked = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._h = 0.0
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.a = anim(self, b"hov", 180)

    hov = pyqtProperty(float, lambda s: s._h, lambda s, v: (setattr(s, "_h", v), s.update()))

    def set_hover(self, on):
        retarget(self.a, self._h, 1.0 if on else 0.0)

    def enterEvent(self, e):
        self.set_hover(True)

    def leaveEvent(self, e):
        self.set_hover(False)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(mix("#E5E5EA", "#007AFF", self._h), 2))
        p.setBrush(mix("#FFFFFF", "#F0F7FF", self._h))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 12, 12)


class Elided(QLabel):
    """Single-line label that truncates instead of widening the layout."""
    def __init__(self, role=None, mode=Qt.TextElideMode.ElideMiddle):
        super().__init__()
        self._t, self._m = "", mode
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        if role:
            self.setProperty("role", role)

    def setText(self, t):
        self._t = t
        self.setToolTip(t)
        self._fit()

    def _fit(self):
        QLabel.setText(self, self.fontMetrics().elidedText(self._t, self._m, max(self.width() - 2, 0)))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit()


class Icon(QWidget):
    """Folder, or a success / warning badge that pops in and draws its mark."""
    def __init__(self, kind, size):
        super().__init__()
        self.kind, self._pop = kind, 1.0
        self.setFixedSize(size, size)
        self.a = anim(self, b"pop", 520, QEasingCurve.Type.OutBack)

    pop = pyqtProperty(float, lambda s: s._pop, lambda s, v: (setattr(s, "_pop", v), s.update()))

    def set(self, kind):
        self.kind = kind
        self.update()

    def play(self):
        self.a.stop()
        self.a.setStartValue(0.0)
        self.a.setEndValue(1.0)
        self.a.start()

    def paintEvent(self, _):
        s = self.width()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pt = lambda x, y: QPointF(x * s, y * s)
        p.setPen(Qt.PenStyle.NoPen)
        if self.kind == "folder":
            back = QPainterPath()
            back.addRoundedRect(QRectF(.08 * s, .16 * s, .84 * s, .68 * s), .09 * s, .09 * s)
            p.setBrush(QColor("#3D8FE8"))
            p.drawPath(back)
            g = QLinearGradient(0, .26 * s, 0, .84 * s)
            g.setColorAt(0, QColor("#6CB8FF"))
            g.setColorAt(1, QColor("#2F8CFF"))
            p.setBrush(g)
            p.drawRoundedRect(QRectF(.08 * s, .28 * s, .84 * s, .56 * s), .09 * s, .09 * s)
            return
        k = max(self._pop, 0.001)
        p.translate(s / 2, s / 2)
        p.scale(k, k)
        p.translate(-s / 2, -s / 2)
        p.setBrush(QColor(GREEN if self.kind == "check" else ORANGE))
        p.drawEllipse(QRectF(.04 * s, .04 * s, .92 * s, .92 * s))
        t = min(1.0, max(0.0, (self._pop - 0.3) / 0.5))
        p.setPen(QPen(QColor("white"), s * 0.075, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        if self.kind == "check":
            pts = [pt(.30, .52), pt(.44, .66), pt(.71, .37)]
            segs = list(zip(pts, pts[1:]))
            lens = [math.hypot(b.x() - a.x(), b.y() - a.y()) for a, b in segs]
            rem, out = t * sum(lens), [pts[0]]
            for (a, b), l in zip(segs, lens):
                if rem >= l:
                    out.append(b)
                    rem -= l
                else:
                    out.append(a + (b - a) * (rem / l))
                    break
            p.drawPolyline(QPolygonF(out))
        else:
            p.drawLine(pt(.5, .27), pt(.5, .27 + .29 * t))
            if t > .6:
                p.drawPoint(pt(.5, .72))


class Lights(QWidget):
    """Close / minimize / maximize-restore. Glyphs appear when the group is hovered."""
    COL = ("#FF5F57", "#FEBC2E", "#28C840")

    def __init__(self, win):
        super().__init__()
        self.win, self.hov = win, False
        self.setFixedSize(60, 24)

    def enterEvent(self, e):
        self.hov = True
        self.update()

    def leaveEvent(self, e):
        self.hov = False
        self.update()

    def mousePressEvent(self, e):
        e.accept()  # keep the title bar from starting a window drag

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton or not self.rect().contains(e.position().toPoint()):
            return
        i = int(e.position().x() // 20)
        if i == 0:
            self.win.close()
        elif i == 1:
            self.win.showMinimized()
        elif i == 2 and getattr(self.win, "can_max", True):
            self.win.toggle_max()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        ink = QColor(0, 0, 0, 150)
        for i, c in enumerate(self.COL):
            cx, cy = 10 + i * 20, 12
            p.setPen(QPen(QColor(0, 0, 0, 36), 0.8))
            fixed = i == 2 and not getattr(self.win, "can_max", True)   # e.g. the installer window
            p.setBrush(QColor("#D1D1D6" if fixed else c))
            p.drawEllipse(QPointF(cx, cy), 6, 6)
            if not self.hov or fixed:
                continue
            p.setPen(QPen(ink, 1.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            if i == 0:
                p.drawLine(QPointF(cx - 2.2, cy - 2.2), QPointF(cx + 2.2, cy + 2.2))
                p.drawLine(QPointF(cx + 2.2, cy - 2.2), QPointF(cx - 2.2, cy + 2.2))
            elif i == 1:
                p.drawLine(QPointF(cx - 2.8, cy), QPointF(cx + 2.8, cy))
            else:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(ink)
                q = lambda x, y: QPointF(cx + x, cy + y)
                if self.win.isMaximized():   # arrows point inward: restore
                    t1 = [q(2.9, -.5), q(.5, -.5), q(.5, -2.9)]
                    t2 = [q(-2.9, .5), q(-.5, .5), q(-.5, 2.9)]
                else:                        # arrows point outward: maximize
                    t1 = [q(2.9, -2.9), q(-.3, -2.9), q(2.9, .3)]
                    t2 = [q(-2.9, 2.9), q(.3, 2.9), q(-2.9, -.3)]
                p.drawPolygon(QPolygonF(t1))
                p.drawPolygon(QPolygonF(t2))


class TitleBar(QWidget):
    """Drag to move (drag from maximized restores), double-click to maximize / restore."""
    def __init__(self, win, title="Raw Sorter"):
        super().__init__()
        self.win, self._down = win, False
        self.setFixedHeight(48)
        h = QHBoxLayout(self)
        h.setContentsMargins(20, 0, 20, 0)
        h.addWidget(Lights(win))
        h.addWidget(lbl(title, "bar", True), 1)
        spacer = QWidget()
        spacer.setFixedWidth(60)
        h.addWidget(spacer)

    def mousePressEvent(self, e):
        self._down = e.button() == Qt.MouseButton.LeftButton

    def mouseReleaseEvent(self, e):
        self._down = False

    def mouseMoveEvent(self, e):
        h = self.win.windowHandle()
        if self._down and h and e.buttons() & Qt.MouseButton.LeftButton:
            self._down = False
            if self.win.isMaximized():
                self.win.showNormal()
            h.startSystemMove()

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.win.toggle_max()


class Row(QWidget):
    """One line of the grouped list: colored badge, count + destination, size."""
    def __init__(self, tag, color):
        super().__init__()
        h = QHBoxLayout(self)
        h.setContentsMargins(24, 0, 24, 0)
        h.setSpacing(16)
        badge = lbl(tag, center=True)
        badge.setFixedSize(48, 32)
        badge.setStyleSheet(f"background:{color}; color:#fff; border-radius:8px; font-size:12px; font-weight:700;")
        col = QVBoxLayout()
        col.setSpacing(0)
        self.count, self.dest = lbl("", "h3"), Elided("muted")
        col.addStretch()
        col.addWidget(self.count)
        col.addWidget(self.dest)
        col.addStretch()
        self.size = lbl("", "muted")
        self.a = QVariantAnimation(self)
        self.a.setDuration(520)
        self.a.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.a.setStartValue(0)
        self.a.valueChanged.connect(lambda v: self.count.setText(self.fmt(v)))
        h.addWidget(badge)
        h.addLayout(col, 1)
        h.addWidget(self.size)

    @staticmethod
    def fmt(v):
        return f"{int(v):,} {'file' if int(v) == 1 else 'files'}"

    def fill(self, n, size, dest):
        self.a.stop()
        self.a.setEndValue(n)
        self.count.setText(self.fmt(0) if n else "No files")
        if n:
            self.a.start()
        self.dest.setText(f"Moves to {dest}" if n else "Nothing to create")
        self.size.setText(human(size) if n else "")


# ----------------------------------------------------------------------------- window
class Window(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowMinimizeButtonHint
                            | Qt.WindowType.WindowMaximizeButtonHint)
        self.setWindowIcon(qicon())
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("Raw Sorter")
        self.setMinimumSize(560, 440)
        self.resize(560, 440)
        self.setAcceptDrops(True)
        self.folder, self.jpg, self.raw, self.others = None, [], [], 0
        self.mover, self.moved, self.created, self.used = None, [], [], []
        self.res, self._after, self.primary = (0, 0, False), None, {}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(TitleBar(self))
        body = QWidget()
        pad = QHBoxLayout(body)
        pad.setContentsMargins(24, 0, 24, 24)
        holder = QWidget()                      # content keeps a comfortable size when maximized
        holder.setMaximumSize(760, 520)
        self.stack = QStackedLayout(holder)
        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.addStretch(1)
        col.addWidget(holder, 1000)
        col.addStretch(1)
        pad.addStretch(1)
        pad.addLayout(col, 1000)
        pad.addStretch(1)
        root.addWidget(body, 1)
        self.p_empty, self.p_ready = self.build_empty(), self.build_ready()
        self.p_work, self.p_done = self.build_work(), self.build_done()
        for p in (self.p_empty, self.p_ready, self.p_work, self.p_done):
            self.stack.addWidget(p)

        self.anim = QPropertyAnimation(self.bar, b"level", self)
        self.anim.setDuration(220)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.anim.finished.connect(self._anim_done)
        for k in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            QShortcut(QKeySequence(k), self).activated.connect(self.enter)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self).activated.connect(self.escape)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        mx = self.isMaximized()   # square and borderless when maximized
        p.setPen(Qt.PenStyle.NoPen if mx else QPen(QColor("#D2D2D7"), 1))
        p.setBrush(QColor("#F5F5F7"))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(*([0] * 4 if mx else [.5, .5, -.5, -.5])), *([0, 0] if mx else [12, 12]))

    def toggle_max(self):
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def changeEvent(self, e):
        super().changeEvent(e)
        self.update()
        for w in self.findChildren(Lights):
            w.update()

    # ---- pages
    def build_empty(self):
        page = QWidget()
        QVBoxLayout(page).setContentsMargins(0, 0, 0, 0)
        self.drop = Drop()
        self.drop.clicked.connect(self.choose)
        v = QVBoxLayout(self.drop)
        v.setSpacing(0)
        v.addStretch()
        v.addWidget(Icon("folder", 96), 0, A.AlignHCenter)
        v.addSpacing(24)
        v.addWidget(lbl("Drop a Photo Folder", "title", True))
        v.addSpacing(8)
        v.addWidget(lbl("JPG and RAW files are sorted into two separate folders.", "muted", True))
        v.addSpacing(32)
        b = btn("Choose Folder…", "primary")
        b.setFixedWidth(176)
        b.clicked.connect(self.choose)
        v.addWidget(b, 0, A.AlignHCenter)
        v.addStretch()
        page.layout().addWidget(self.drop)
        self.primary[page] = b
        return page

    def build_ready(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        head, col = QHBoxLayout(), QVBoxLayout()
        head.setSpacing(16)
        col.setSpacing(0)
        self.r_name, self.r_path = Elided("title", Qt.TextElideMode.ElideRight), Elided("muted")
        col.addWidget(self.r_name)
        col.addWidget(self.r_path)
        change = btn("Change…", "secondary")
        change.clicked.connect(self.choose)
        head.addLayout(col, 1)
        head.addWidget(change, 0, A.AlignVCenter)
        v.addLayout(head)
        v.addSpacing(24)
        card = QFrame(objectName="card")
        c = QVBoxLayout(card)
        c.setContentsMargins(0, 0, 0, 0)
        c.setSpacing(0)
        self.c_jpg, self.c_raw = Row("JPG", BLUE), Row("RAW", ORANGE)
        rule = QWidget()
        QHBoxLayout(rule).setContentsMargins(24, 0, 0, 0)
        line = QFrame(objectName="rule")
        line.setFixedHeight(1)
        rule.layout().addWidget(line)
        c.addWidget(self.c_jpg, 1)
        c.addWidget(rule)
        c.addWidget(self.c_raw, 1)
        v.addWidget(card, 1)
        v.addSpacing(16)
        self.r_note = lbl("", "muted", wrap=True)
        v.addWidget(self.r_note)
        v.addSpacing(16)
        self.go = btn("Organize", "primary")
        self.go.setFixedHeight(44)
        self.go.clicked.connect(self.start)
        v.addWidget(self.go)
        self.primary[page] = self.go
        return page

    def build_work(self):
        page = QWidget()
        QVBoxLayout(page).setContentsMargins(0, 0, 0, 0)
        card = QFrame(objectName="card")
        c = QVBoxLayout(card)
        c.setContentsMargins(32, 32, 32, 32)
        c.setSpacing(0)
        c.addStretch()
        self.w_title = lbl("Organizing…", "h3", True)
        self.w_pct = lbl("0%", "huge", True)
        self.bar = PillBar()
        self.bar.changed.connect(lambda x: self.w_pct.setText(f"{int(x * 100)}%"))
        c.addWidget(self.w_title)
        c.addSpacing(8)
        c.addWidget(self.w_pct)
        c.addSpacing(24)
        c.addWidget(self.bar)
        c.addSpacing(12)
        row = QHBoxLayout()
        row.setSpacing(16)
        self.w_count, self.w_file = lbl("", "muted"), Elided("muted")
        self.w_file.setAlignment(A.AlignRight | A.AlignVCenter)
        row.addWidget(self.w_count)
        row.addWidget(self.w_file, 1)
        c.addLayout(row)
        c.addStretch()
        self.w_cancel = btn("Cancel", "secondary")
        self.w_cancel.clicked.connect(self.escape)
        c.addWidget(self.w_cancel, 0, A.AlignHCenter)
        page.layout().addWidget(card)
        return page

    def build_done(self):
        page = QWidget()
        QVBoxLayout(page).setContentsMargins(0, 0, 0, 0)
        card = QFrame(objectName="card")
        c = QVBoxLayout(card)
        c.setContentsMargins(32, 32, 32, 32)
        c.setSpacing(0)
        c.addStretch()
        self.d_icon = Icon("check", 72)
        self.d_title, self.d_sub = lbl("", "title", True), lbl("", "muted", True, True)
        c.addWidget(self.d_icon, 0, A.AlignHCenter)
        c.addSpacing(24)
        c.addWidget(self.d_title)
        c.addSpacing(8)
        c.addWidget(self.d_sub)
        c.addStretch()
        row = QHBoxLayout()
        row.setSpacing(12)
        self.d_open = btn("Open Folder", "primary")
        self.d_undo, again = btn("Undo", "secondary"), btn("Sort Another", "secondary")
        self.d_open.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.folder))))
        self.d_undo.clicked.connect(self.undo)
        again.clicked.connect(lambda: self.show_page(self.p_empty))
        for b in (self.d_open, self.d_undo, again):
            row.addWidget(b, 1)
        c.addLayout(row)
        page.layout().addWidget(card)
        self.primary[page] = self.d_open
        return page

    # ---- navigation helpers
    def show_page(self, page):
        self.stack.setCurrentWidget(page)
        fx = QGraphicsOpacityEffect(page)
        page.setGraphicsEffect(fx)
        a = QPropertyAnimation(fx, b"opacity", page)
        a.setDuration(240)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.setEasingCurve(QEasingCurve.Type.OutCubic)
        a.finished.connect(lambda: page.setGraphicsEffect(None))
        a.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def busy(self):
        return self.mover is not None and self.mover.isRunning()

    def enter(self):
        f = QApplication.focusWidget()
        b = f if isinstance(f, QAbstractButton) else self.primary.get(self.stack.currentWidget())
        if b and b.isEnabled() and not self.busy():
            b.click()

    def escape(self):
        if self.busy():
            self.w_cancel.setEnabled(False)
            self.w_title.setText("Stopping…")
            self.mover.cancel()

    def hover(self, on):
        self.drop.set_hover(on)

    # ---- drag & drop
    def _dropped(self, e):
        if self.busy():
            return None
        for u in e.mimeData().urls():
            if u.isLocalFile():
                p = u.toLocalFile()
                return p if os.path.isdir(p) else os.path.dirname(p)
        return None

    def dragEnterEvent(self, e):
        if self._dropped(e):
            e.acceptProposedAction()
            self.hover(True)

    def dragLeaveEvent(self, e):
        self.hover(False)

    def dropEvent(self, e):
        self.hover(False)
        d = self._dropped(e)
        if d:
            e.acceptProposedAction()
            self.load(d)

    # ---- flow
    @property
    def base(self):
        return self.folder.name or self.folder.drive.rstrip(":\\/") or "photos"

    def choose(self):
        start = str(self.folder.parent) if self.folder else str(Path.home() / "Pictures")
        d = QFileDialog.getExistingDirectory(self, "Choose a photo folder", start)
        if d:
            self.load(d)

    def load(self, path):
        folder = Path(os.path.normpath(path))
        try:
            jpg, raw, other = scan(folder)
        except OSError as e:
            QMessageBox.warning(self, "Can’t open this folder", f"{folder}\n\n{e.strerror or e}")
            return
        self.folder, self.jpg, self.raw, self.others = folder, jpg, raw, other
        nj, nr, b = len(jpg), len(raw), self.base
        self.r_name.setText(folder.name or str(folder))
        self.r_path.setText(str(folder))
        self.c_jpg.fill(nj, sum(s for _, s in jpg), f"{b}-jpg")
        self.c_raw.fill(nr, sum(s for _, s in raw), f"{b}-raw")
        n = nj + nr
        self.go.setEnabled(n > 0)
        self.go.setText(f"Organize {n:,} {'file' if n == 1 else 'files'}" if n else "Nothing to Organize")
        if not n:
            note = "No JPG or RAW files in this folder. Choose a different one."
        else:
            note = "New folders are created inside this folder." if nj and nr else \
                   f"Only {'JPG' if nj else 'RAW'} files found, so one folder will be created."
            if other:
                note += f" {other:,} other {'file stays' if other == 1 else 'files stay'} where {'it is' if other == 1 else 'they are'}."
        self.r_note.setText(note)
        self.show_page(self.p_ready)

    def start(self):
        b, f = self.base, self.folder
        dirs = []
        if self.jpg:
            dirs.append((f / f"{b}-jpg", self.jpg))
        if self.raw:
            dirs.append((f / f"{b}-raw", self.raw))
        for d, _ in dirs:
            if d.exists() and not d.is_dir():
                QMessageBox.warning(self, "Can’t create folder", f"A file named “{d.name}” is in the way.")
                return
        self.created = [d for d, _ in dirs if not d.exists()]
        self.used = [d.name for d, _ in dirs]
        jobs = [(p, str(d / os.path.basename(p))) for d, items in dirs for p, _ in items]
        self.run(jobs, "Organizing…", self.on_done)

    def run(self, jobs, title, after):
        self.anim.stop()
        self._after = None
        self.bar.setLevel(0.0)
        self.w_title.setText(title)
        self.w_count.setText(f"0 of {len(jobs):,} files")
        self.w_file.setText("")
        self.w_cancel.setEnabled(True)
        self.mover = Mover(jobs)
        self.mover.progress.connect(self.on_progress)
        self.mover.done.connect(after)
        self.mover.start()
        self.show_page(self.p_work)

    def on_progress(self, i, total, name):
        self.w_count.setText(f"{i:,} of {total:,} files")
        self.w_file.setText(name)
        self.set_progress(i / total)

    def set_progress(self, frac, then=None):
        self._after = then
        self.anim.stop()
        self.anim.setStartValue(self.bar.level)
        self.anim.setEndValue(float(frac))
        self.anim.start()

    def _anim_done(self):
        cb, self._after = self._after, None
        if cb:
            cb()

    def on_done(self, moved, failed, cancelled):
        self.moved = moved
        self.res = (len(moved), len(failed), cancelled)
        if cancelled:
            self.anim.stop()
            self.show_done()
        else:
            self.set_progress(1.0, self.show_done)

    def show_done(self):
        n, bad, cancelled = self.res
        total = len(self.jpg) + len(self.raw)
        files = lambda k: f"{k:,} {'file' if k == 1 else 'files'}"
        if cancelled:
            self.d_icon.set("alert")
            self.d_title.setText("Stopped")
            self.d_sub.setText(f"{files(n)} of {total:,} moved before you stopped.")
        elif bad:
            self.d_icon.set("alert")
            self.d_title.setText(f"{files(n)} Organized")
            self.d_sub.setText(f"{files(bad)} couldn’t be moved. They may be open in another app.")
        else:
            self.d_icon.set("check")
            self.d_title.setText(f"{files(n)} Organized")
            self.d_sub.setText("Created " + " and ".join(self.used) + ".")
        self.d_undo.setVisible(n > 0)
        self.show_page(self.p_done)
        self.d_icon.play()

    def undo(self):
        self.run([(dst, src) for src, dst in reversed(self.moved)], "Undoing…", self.on_undone)

    def on_undone(self, moved, failed, cancelled):
        for d in self.created:
            try:
                d.rmdir()  # only succeeds when empty
            except OSError:
                pass
        self.set_progress(1.0, lambda: self.after_undo(len(failed)))

    def after_undo(self, bad):
        self.load(str(self.folder))
        if bad:
            QMessageBox.warning(self, "Undo incomplete", f"{bad:,} files couldn’t be moved back.")

    def closeEvent(self, e):
        if self.busy():
            self.mover.cancel()
            self.mover.wait()
        e.accept()


def app_icon(size=256):
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    Icon("folder", size).render(pm)
    return pm


def qicon():
    ic = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        ic.addPixmap(app_icon(s))
    return ic


def write_ico(path):
    """Multi-size .ico (PNG-compressed entries) so the exe and taskbar icons stay sharp."""
    import struct
    from PyQt6.QtCore import QBuffer, QByteArray, QIODevice
    sizes, blobs = (16, 24, 32, 48, 64, 128, 256), []
    for s in sizes:
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        app_icon(s).save(buf, "PNG")
        buf.close()
        blobs.append(bytes(ba))
    head, off = struct.pack("<HHH", 0, 1, len(sizes)), 6 + 16 * len(sizes)
    for s, b in zip(sizes, blobs):
        head += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(b), off)
        off += len(b)
    with open(path, "wb") as f:
        f.write(head + b"".join(blobs))


def single_instance(title):
    """Windows: only one copy at a time (two could fight over the same folder). Returns False if
    another copy is already running, after bringing its window to the front."""
    if sys.platform != "win32":
        return True
    try:
        k, u = ctypes.WinDLL("kernel32", use_last_error=True), ctypes.WinDLL("user32")
        k.CreateMutexW.restype = ctypes.c_void_p
        u.FindWindowW.restype = ctypes.c_void_p
        for f in (u.ShowWindow, u.SetForegroundWindow, u.IsIconic):
            f.argtypes = [ctypes.c_void_p] + ([ctypes.c_int] if f is u.ShowWindow else [])
        single_instance.handle = k.CreateMutexW(None, False, "Local\\RawSorter.SingleInstance")
        if ctypes.get_last_error() == 183:   # ERROR_ALREADY_EXISTS
            hw = u.FindWindowW(None, title)
            if hw:
                if u.IsIconic(hw):
                    u.ShowWindow(hw, 9)
                u.SetForegroundWindow(hw)
            return False
    except Exception:
        pass
    return True


def _ps(script):
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script], check=True)


def _app_dir():
    return os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "Programs", "RawSorter")


def install():
    """Build RawSorter.exe, copy it to your local Programs folder, add Desktop + Start menu shortcuts."""
    app = QApplication.instance() or QApplication(sys.argv)
    tmp, dest = tempfile.mkdtemp(prefix="rawsorter_"), _app_dir()
    ico = os.path.join(tmp, "RawSorter.ico")
    write_ico(ico)
    print("Building Raw Sorter (about a minute)...")
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
                    "--name", "RawSorter", "--icon", ico, "--distpath", os.path.join(tmp, "dist"),
                    "--workpath", os.path.join(tmp, "build"), "--specpath", tmp, os.path.abspath(__file__)],
                   check=True)
    try:
        shutil.rmtree(dest, ignore_errors=False) if os.path.isdir(dest) else None
    except OSError:
        print("Raw Sorter is running. Close it and run the installer again.")
        return
    shutil.copytree(os.path.join(tmp, "dist", "RawSorter"), dest)
    exe = os.path.join(dest, "RawSorter.exe")
    q = lambda t: t.replace("'", "''")
    _ps("""$w = New-Object -ComObject WScript.Shell
foreach ($d in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) {
  $s = $w.CreateShortcut((Join-Path $d 'Raw Sorter.lnk'))
  $s.TargetPath = '@EXE@'; $s.WorkingDirectory = '@DIR@'; $s.IconLocation = '@EXE@,0'
  $s.Description = 'Sort JPG and RAW photos into separate folders'; $s.Save() }""".replace("@EXE@", q(exe)).replace("@DIR@", q(dest)))
    shutil.rmtree(tmp, ignore_errors=True)
    print("Installed. Shortcuts added to your Desktop and Start menu.")
    os.startfile(exe)


def uninstall():
    _ps("""foreach ($d in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) {
  Remove-Item (Join-Path $d 'Raw Sorter.lnk') -ErrorAction SilentlyContinue }""")
    shutil.rmtree(_app_dir(), ignore_errors=True)
    print("Raw Sorter was removed.")


if __name__ == "__main__":
    if "--install" in sys.argv:
        install()
        sys.exit(0)
    if "--uninstall" in sys.argv:
        uninstall()
        sys.exit(0)
    if sys.platform == "win32":
        os.environ.setdefault("QT_QPA_PLATFORM", "windows:darkmode=0")   # keep the light design in dark mode
        if not getattr(sys, "frozen", False):   # the installed .exe groups with its own shortcut
            try:
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("RawSorter.App")
            except Exception:
                pass
    if not single_instance("Raw Sorter"):
        sys.exit(0)
    app = QApplication(sys.argv)
    app.setWindowIcon(qicon())
    app.setStyle("Fusion")
    app.setStyleSheet(QSS)
    w = Window()
    w.move(app.primaryScreen().availableGeometry().center() - w.rect().center())
    w.setWindowOpacity(0.0)
    w.show()
    fade = QPropertyAnimation(w, b"windowOpacity", w)
    fade.setDuration(260)
    fade.setStartValue(0.0)
    fade.setEndValue(1.0)
    fade.start()
    sys.exit(app.exec())
