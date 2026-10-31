"""Raw Sorter Setup - double-click to install. Keep it in the same folder as raw_sorter_final.py.
Installs a standalone app, adds shortcuts, and registers Raw Sorter in Windows "Apps & features"."""
import os, sys, time, subprocess, importlib, importlib.util, ctypes, traceback, shutil, tempfile

NOWIN = 0x08000000 if sys.platform == "win32" else 0
HERE = os.path.dirname(os.path.abspath(__file__))
REG = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\RawSorter"


def pyexe():
    d, b = os.path.split(sys.executable)
    py = os.path.join(d, "python.exe")
    return py if b.lower() == "pythonw.exe" and os.path.exists(py) else sys.executable


def alert(text):
    try:
        ctypes.windll.user32.MessageBoxW(0, text[-900:], "Raw Sorter Setup", 0x10)
    except Exception:
        print(text, file=sys.stderr)


sys.excepthook = lambda *a: alert("".join(traceback.format_exception(*a)))

try:
    import PyQt6.QtWidgets  # noqa: F401
except ImportError:  # first run: fetch PyQt6 once, with a small status window
    import tkinter as tk
    root = tk.Tk()
    root.title("Raw Sorter Setup")
    root.geometry("320x90")
    tk.Label(root, text="Preparing the installer…\nThis only happens once.", pady=20).pack()
    root.update()
    subprocess.run([pyexe(), "-m", "pip", "install", "PyQt6"], creationflags=NOWIN, capture_output=True)
    root.destroy()
    importlib.invalidate_caches()
    try:
        import PyQt6.QtWidgets  # noqa: F401
    except ImportError:
        alert("Couldn't install PyQt6. Check your internet connection and try again.")
        sys.exit(1)

sys.path.insert(0, HERE)
try:
    import raw_sorter_final as R
except ImportError:
    alert("raw_sorter_final.py must be in the same folder as this installer.")
    sys.exit(1)

from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtProperty, QTimer, QRectF, QPropertyAnimation
from PyQt6.QtGui import QPainter, QColor, QPen, QIcon, QShortcut, QKeySequence
from PyQt6.QtWidgets import (QApplication, QWidget, QFrame, QAbstractButton, QVBoxLayout, QHBoxLayout,
                             QFileDialog, QStackedLayout, QGraphicsOpacityEffect)

A = R.A
SHORTCUT_PS = """$w = New-Object -ComObject WScript.Shell
foreach ($n in @(@NAMES@)) {
  $s = $w.CreateShortcut((Join-Path ([Environment]::GetFolderPath($n)) 'Raw Sorter.lnk'))
  $s.TargetPath = '@EXE@'; $s.WorkingDirectory = '@DIR@'; $s.IconLocation = '@EXE@,0'
  $s.Description = 'Sort JPG and RAW photos into separate folders'; $s.Save() }"""
REMOVE_PS = """foreach ($n in @('Desktop','Programs')) {
  Remove-Item (Join-Path ([Environment]::GetFolderPath($n)) 'Raw Sorter.lnk') -ErrorAction SilentlyContinue }"""


def ps(script):
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                   check=True, creationflags=NOWIN, capture_output=True)


def default_dir():
    return os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~/.local/share")),
                        "Programs", "RawSorter")


# ----------------------------------------------------------------------------- worker
class Cancelled(Exception):
    pass


class Job(QThread):
    phase = pyqtSignal(float, float, int, str, str)   # start, end, step index, title, detail
    done = pyqtSignal(bool, str)

    def __init__(self, o, tmp, un):
        super().__init__()
        self.o, self.tmp, self.un = o, tmp, un
        self._stop, self.proc, self.log, self.can_cancel = False, None, [], not un

    def cancel(self):
        self._stop = True
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()

    def ph(self, a, b, i, title, detail=""):
        if self._stop:
            raise Cancelled()
        self.phase.emit(a, b, i, title, detail)

    def cmd(self, args, on_line=None):
        self.proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                     errors="replace", creationflags=NOWIN, cwd=self.tmp)
        for line in self.proc.stdout:
            self.log.append(line.rstrip())
            if on_line:
                on_line(line)
        rc = self.proc.wait()
        if self._stop:
            raise Cancelled()
        if rc:
            raise RuntimeError(next((l for l in reversed(self.log) if l.strip()), "A step failed."))

    def run(self):
        try:
            (self.remove if self.un else self.install)()
            self.done.emit(True, "")
        except Cancelled:
            self.done.emit(False, "cancelled")
        except Exception as e:
            try:
                with open(os.path.join(tempfile.gettempdir(), "rawsorter_setup.log"), "w", encoding="utf-8") as f:
                    f.write("\n".join(self.log) + "\n" + traceback.format_exc())
            except OSError:
                pass
            self.done.emit(False, str(e) or e.__class__.__name__)
        finally:
            shutil.rmtree(self.tmp, ignore_errors=True)

    def install(self):
        o, tmp, dest, win = self.o, self.tmp, self.o["dest"], sys.platform == "win32"
        src = os.path.join(HERE, "raw_sorter_final.py")
        exe = os.path.join(dest, "RawSorter.exe" if win else "RawSorter")
        self.ph(0, .06, 0, "Preparing", "Checking the install location")
        if os.path.exists(dest) and os.listdir(dest) and not os.path.exists(exe):
            raise RuntimeError("That folder isn't empty. Choose a different install location.")
        self.ph(.06, .2, 1, "Checking components", "Making sure the app builder is ready")
        if importlib.util.find_spec("PyInstaller") is None:
            self.cmd([pyexe(), "-m", "pip", "install", "pyinstaller"])
        miles = {"Building Analysis": (.2, .5, "Analyzing the app"), "Building PYZ": (.5, .6, "Compressing modules"),
                 "Building PKG": (.6, .66, "Packaging"), "Building EXE": (.66, .72, "Creating the executable"),
                 "Building COLLECT": (.72, .8, "Collecting files")}
        seen = set()

        def on_line(line):
            for k, (a, b, d) in miles.items():
                if k in line and k not in seen:
                    seen.add(k)
                    self.ph(a, b, 2, "Building Raw Sorter", d)

        self.ph(.2, .5, 2, "Building Raw Sorter", "Getting started")
        self.cmd([pyexe(), "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--name", "RawSorter",
                  "--icon", os.path.join(tmp, "RawSorter.ico"), "--distpath", os.path.join(tmp, "dist"),
                  "--workpath", os.path.join(tmp, "build"), "--specpath", tmp, src], on_line)
        self.can_cancel = False   # from here on the install can't be rolled back cleanly
        self.ph(.8, .9, 3, "Installing files", dest)
        if os.path.isdir(dest):
            try:
                shutil.rmtree(dest)
            except OSError:
                raise RuntimeError("Raw Sorter is open. Close it and try again.")
        shutil.copytree(os.path.join(tmp, "dist", "RawSorter"), dest)
        sd = os.path.join(dest, "setup")
        os.makedirs(sd)
        for f in (os.path.abspath(__file__), src):
            shutil.copy2(f, sd)
        self.ph(.9, .96, 4, "Creating shortcuts", "Desktop and Start menu")
        names = [n for k, n in (("desktop", "Desktop"), ("start", "Programs")) if o[k]]
        q = lambda t: t.replace("'", "''")
        if win and names:
            ps(SHORTCUT_PS.replace("@NAMES@", ",".join(f"'{n}'" for n in names))
               .replace("@EXE@", q(exe)).replace("@DIR@", q(dest)))
        self.ph(.96, 1, 5, "Finishing up", "Adding Raw Sorter to Apps & features")
        if win:
            import winreg
            pw = os.path.join(os.path.dirname(pyexe()), "pythonw.exe")
            un = f'"{pw}" "{os.path.join(sd, os.path.basename(__file__))}" --uninstall'
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG)
            for k, v in (("DisplayName", "Raw Sorter"), ("DisplayVersion", "1.0"), ("Publisher", "Raw Sorter"),
                         ("InstallLocation", dest), ("DisplayIcon", exe), ("UninstallString", un)):
                winreg.SetValueEx(key, k, 0, winreg.REG_SZ, v)
            for k in ("NoModify", "NoRepair"):
                winreg.SetValueEx(key, k, 0, winreg.REG_DWORD, 1)
            kb = sum(os.path.getsize(os.path.join(r_, f)) for r_, _, fs in os.walk(dest) for f in fs) // 1024
            winreg.SetValueEx(key, "EstimatedSize", 0, winreg.REG_DWORD, int(kb))
            winreg.SetValueEx(key, "InstallDate", 0, winreg.REG_SZ, time.strftime("%Y%m%d"))
            winreg.CloseKey(key)

    def remove(self):
        dest, win = self.o["dest"], sys.platform == "win32"
        self.ph(0, .3, 0, "Removing shortcuts", "Desktop and Start menu")
        if win:
            ps(REMOVE_PS)
        self.ph(.3, .9, 1, "Removing files", dest)
        if os.path.basename(dest).lower() == "rawsorter":   # never delete an unrelated folder
            shutil.rmtree(dest, ignore_errors=True)
        if os.path.exists(os.path.join(dest, "RawSorter.exe")):
            raise RuntimeError("Raw Sorter is open. Close it and try again.")
        self.ph(.9, 1, 2, "Finishing up", "Cleaning the registry")
        if win:
            import winreg
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, REG)
            except OSError:
                pass


# ----------------------------------------------------------------------------- widgets
class Switch(QAbstractButton):
    """iOS-style toggle with a sliding knob."""
    def __init__(self, on=True):
        super().__init__()
        self.setCheckable(True)
        self.setChecked(on)
        self._t = 1.0 if on else 0.0
        self.setFixedSize(46, 28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.a = R.anim(self, b"t", 180)
        self.toggled.connect(lambda c: R.retarget(self.a, self._t, 1.0 if c else 0.0))

    t = pyqtProperty(float, lambda s: s._t, lambda s, v: (setattr(s, "_t", v), s.update()))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(R.mix("#E5E5EA", "#34C759", self._t))
        p.drawRoundedRect(QRectF(self.rect()), 14, 14)
        p.setPen(QPen(QColor(0, 0, 0, 30), 0.8))
        p.setBrush(QColor("white"))
        p.drawEllipse(QRectF(2 + self._t * 18, 2, 24, 24))


def option_row(title, right, sub=None):
    w = QWidget()
    w.setMinimumHeight(52)
    h = QHBoxLayout(w)
    h.setContentsMargins(24, 0, 24, 0)
    h.setSpacing(16)
    col = QVBoxLayout()
    col.setSpacing(0)
    col.addStretch()
    col.addWidget(R.lbl(title, "h3"))
    if sub is not None:
        w.sub = R.Elided("muted")
        w.sub.setText(sub)
        col.addWidget(w.sub)
    col.addStretch()
    h.addLayout(col, 1)
    h.addWidget(right)
    return w


def group(rows):
    card = QFrame(objectName="card")
    v = QVBoxLayout(card)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(0)
    for i, r in enumerate(rows):
        if i:
            rule, line = QWidget(), QFrame(objectName="rule")
            QHBoxLayout(rule).setContentsMargins(24, 0, 0, 0)
            line.setFixedHeight(1)
            rule.layout().addWidget(line)
            v.addWidget(rule)
        v.addWidget(r, 1)
    return card


# ----------------------------------------------------------------------------- window
class Setup(QWidget):
    can_max = False

    def __init__(self, uninstall=False):
        super().__init__()
        self.un, self.job, self.o = uninstall, None, {}
        self.dest = os.path.dirname(HERE) if uninstall and os.path.basename(HERE).lower() == "setup" else default_dir()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowMinimizeButtonHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("Raw Sorter Setup")
        self.setWindowIcon(R.qicon())
        self.setFixedSize(560, 520)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(R.TitleBar(self, "Raw Sorter Setup"))
        body = QWidget()
        self.stack = QStackedLayout(body)
        root.addWidget(body, 1)
        self.primary = {}
        self.p_welcome, self.p_work, self.p_done = self.build_welcome(), self.build_work(), self.build_done()
        for p in (self.p_welcome, self.p_work, self.p_done):
            p.layout().setContentsMargins(24, 0, 24, 24)
            self.stack.addWidget(p)
        self.anim = R.anim(self.bar, b"level", 450)
        self.target = self.cap = 0.0
        self.creep = QTimer(self)
        self.creep.setInterval(250)
        self.creep.timeout.connect(self.tick)
        for k in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            QShortcut(QKeySequence(k), self).activated.connect(self.enter)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self).activated.connect(self.escape)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor("#D2D2D7"), 1))
        p.setBrush(QColor("#F5F5F7"))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(.5, .5, -.5, -.5), 12, 12)

    def toggle_max(self):
        pass

    # ---- pages
    def build_welcome(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setSpacing(0)
        v.addStretch(1)
        v.addWidget(R.Icon("folder", 72), 0, A.AlignHCenter)
        v.addSpacing(16)
        v.addWidget(R.lbl("Remove Raw Sorter" if self.un else "Install Raw Sorter", "title", True))
        v.addSpacing(4)
        v.addWidget(R.lbl("This deletes the app and its shortcuts. Your photos are never touched." if self.un
                          else "Sorts JPG and RAW photos into separate folders.", "muted", True, True))
        v.addStretch(1)
        if not self.un:
            change = R.btn("Change…", "secondary")
            change.setFixedHeight(32)
            change.clicked.connect(self.change)
            self.loc = option_row("Install location", change, self.dest)
            self.sw_desk, self.sw_start, self.sw_open = Switch(), Switch(), Switch()
            v.addWidget(group([self.loc, option_row("Desktop shortcut", self.sw_desk),
                               option_row("Start menu shortcut", self.sw_start),
                               option_row("Open Raw Sorter when finished", self.sw_open)]))
            v.addSpacing(16)
        self.go = R.btn("Remove" if self.un else "Install", "primary")
        self.go.setFixedHeight(44)
        self.go.clicked.connect(self.start)
        v.addWidget(self.go)
        self.primary[page] = self.go
        return page

    def build_work(self):
        page = QWidget()
        QVBoxLayout(page)
        card = QFrame(objectName="card")
        c = QVBoxLayout(card)
        c.setContentsMargins(32, 32, 32, 32)
        c.setSpacing(0)
        c.addStretch()
        self.w_title, self.w_pct = R.lbl("", "h3", True), R.lbl("0%", "huge", True)
        self.bar = R.PillBar()
        self.bar.changed.connect(lambda x: self.w_pct.setText(f"{int(x * 100)}%"))
        for w, gap in ((self.w_title, 8), (self.w_pct, 24), (self.bar, 12)):
            c.addWidget(w)
            c.addSpacing(gap)
        row = QHBoxLayout()
        row.setSpacing(16)
        self.w_count, self.w_file = R.lbl("", "muted"), R.Elided("muted")
        self.w_file.setAlignment(A.AlignRight | A.AlignVCenter)
        row.addWidget(self.w_count)
        row.addWidget(self.w_file, 1)
        c.addLayout(row)
        c.addStretch()
        self.w_cancel = R.btn("Cancel", "secondary")
        self.w_cancel.clicked.connect(lambda: self.job and self.job.cancel())
        c.addWidget(self.w_cancel, 0, A.AlignHCenter)
        page.layout().addWidget(card)
        return page

    def build_done(self):
        page = QWidget()
        QVBoxLayout(page)
        card = QFrame(objectName="card")
        c = QVBoxLayout(card)
        c.setContentsMargins(32, 32, 32, 32)
        c.setSpacing(0)
        c.addStretch()
        self.d_icon = R.Icon("check", 72)
        self.d_title, self.d_sub = R.lbl("", "title", True), R.lbl("", "muted", True, True)
        c.addWidget(self.d_icon, 0, A.AlignHCenter)
        c.addSpacing(24)
        c.addWidget(self.d_title)
        c.addSpacing(8)
        c.addWidget(self.d_sub)
        c.addStretch()
        row = QHBoxLayout()
        row.setSpacing(12)
        self.d_main, self.d_alt = R.btn("", "primary"), R.btn("Close", "secondary")
        self.d_main.clicked.connect(lambda: self.d_action())
        self.d_alt.clicked.connect(self.close)
        row.addWidget(self.d_main, 1)
        row.addWidget(self.d_alt, 1)
        c.addLayout(row)
        page.layout().addWidget(card)
        self.primary[page] = self.d_main
        return page

    # ---- helpers
    def show_page(self, page):
        self.stack.setCurrentWidget(page)
        fx = QGraphicsOpacityEffect(page)
        page.setGraphicsEffect(fx)
        a = QPropertyAnimation(fx, b"opacity", page)
        a.setDuration(240)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.setEasingCurve(R.QEasingCurve.Type.OutCubic)
        a.finished.connect(lambda: page.setGraphicsEffect(None))
        a.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def escape(self):
        if self.job and self.job.isRunning() and self.job.can_cancel:
            self.job.cancel()

    def enter(self):
        b = self.primary.get(self.stack.currentWidget())
        if b and b.isEnabled():
            b.click()

    def change(self):
        d = QFileDialog.getExistingDirectory(self, "Choose where to install Raw Sorter", os.path.dirname(self.dest))
        if d:
            d = os.path.normpath(d)
            self.dest = d if os.path.basename(d).lower() == "rawsorter" else os.path.join(d, "RawSorter")
            self.loc.sub.setText(self.dest)

    def push(self):
        R.retarget(self.anim, self.bar.level, self.target)

    def tick(self):   # the bar keeps drifting toward the next milestone, so long steps never look frozen
        if self.target < self.cap - 0.002:
            self.target += (self.cap - self.target) * 0.05
            self.push()

    # ---- flow
    def start(self):
        tmp = tempfile.mkdtemp(prefix="rawsorter_setup_")
        try:
            if not self.un:
                R.write_ico(os.path.join(tmp, "RawSorter.ico"))
        except Exception as e:
            shutil.rmtree(tmp, ignore_errors=True)
            return self.show_done(False, f"Couldn't create the app icon: {e}")
        self.o = {"dest": self.dest} if self.un else {
            "dest": self.dest, "desktop": self.sw_desk.isChecked(), "start": self.sw_start.isChecked(),
            "open": self.sw_open.isChecked()}
        self.nsteps = 3 if self.un else 6
        self.anim.stop()
        self.bar.setLevel(0.0)
        self.target = self.cap = 0.0
        self.w_cancel.setEnabled(not self.un)
        self.w_cancel.setVisible(not self.un)
        self.job = Job(self.o, tmp, self.un)
        self.job.phase.connect(self.on_phase)
        self.job.done.connect(self.finish)
        self.job.start()
        self.creep.start()
        self.show_page(self.p_work)

    def on_phase(self, a, b, i, title, detail):
        self.w_title.setText(title + "…")
        self.w_count.setText(f"Step {i + 1} of {self.nsteps}")
        self.w_file.setText(detail)
        self.target, self.cap = max(self.target, a), b
        self.push()
        self.w_cancel.setEnabled(self.job.can_cancel)

    def finish(self, ok, msg):
        self.creep.stop()
        if msg == "cancelled":
            return self.show_page(self.p_welcome)
        if ok:
            self.target = 1.0
            self.push()
        QTimer.singleShot(520 if ok else 0, lambda: self.show_done(ok, msg))

    def launch(self):
        exe = os.path.join(self.o["dest"], "RawSorter.exe")
        if sys.platform == "win32" and os.path.exists(exe):
            os.startfile(exe)

    def show_done(self, ok, msg=""):
        self.d_alt.setVisible(True)
        if not ok:
            self.d_icon.set("alert")
            self.d_title.setText("Something went wrong")
            self.d_sub.setText(msg[:160] + "\nDetails: rawsorter_setup.log in your Temp folder.")
            self.d_main.setText("Try Again")
            self.d_action = lambda: self.show_page(self.p_welcome)
        elif self.un:
            self.d_icon.set("check")
            self.d_title.setText("Raw Sorter was removed")
            self.d_sub.setText("The app and its shortcuts are gone. Your photos were not touched.")
            self.d_main.setText("Close")
            self.d_action = self.close
            self.d_alt.setVisible(False)
        else:
            self.d_icon.set("check")
            self.d_title.setText("Raw Sorter is installed")
            self.d_sub.setText("Open it any time from your Desktop or Start menu.")
            if self.o["open"]:
                self.launch()
                self.d_main.setText("Done")
                self.d_action = self.close
                self.d_alt.setVisible(False)
            else:
                self.d_main.setText("Open Raw Sorter")
                self.d_action = lambda: (self.launch(), self.close())
        self.show_page(self.p_done)
        self.d_icon.play()

    def closeEvent(self, e):
        if self.job and self.job.isRunning():
            if not self.job.can_cancel:
                self.w_file.setText("Almost done, please wait a moment")
                return e.ignore()   # finishing; closing now would leave a half install
            self.job.cancel()
            self.job.wait()
        e.accept()


if __name__ == "__main__":
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("RawSorter.Setup")
    except Exception:
        pass
    if sys.platform == "win32":
        os.environ.setdefault("QT_QPA_PLATFORM", "windows:darkmode=0")   # keep the light design in dark mode
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(R.QSS)
    w = Setup("--uninstall" in sys.argv)
    w.move(app.primaryScreen().availableGeometry().center() - w.rect().center())
    w.setWindowOpacity(0.0)
    w.show()
    fade = QPropertyAnimation(w, b"windowOpacity", w)
    fade.setDuration(260)
    fade.setStartValue(0.0)
    fade.setEndValue(1.0)
    fade.start()
    sys.exit(app.exec())
