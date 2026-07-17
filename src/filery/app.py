"""Desktop UI: drop a print PDF in, get a web-ready one out."""

from __future__ import annotations

import os
import sys
import subprocess

from PySide6.QtCore import QObject, QSize, Qt, QThread, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QFont
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QFileDialog, QFrame, QHBoxLayout,
    QLabel, QMainWindow, QMessageBox, QProgressBar, QPushButton, QRadioButton,
    QVBoxLayout, QWidget,
)

from .optimizers.pdf import PROFILES, Cancelled, Profile, Stats, analyze, optimize

APP_NAME = "Filery"


def human(n: float) -> str:
    if n >= 1048576:
        return f"{n / 1048576:.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n:.0f} B"


def reveal(path: str) -> None:
    if sys.platform == "darwin":
        subprocess.run(["open", "-R", path], check=False)
    elif sys.platform.startswith("win"):
        subprocess.run(["explorer", "/select,", os.path.normpath(path)], check=False)
    else:
        subprocess.run(["xdg-open", os.path.dirname(path) or "."], check=False)


class Worker(QObject):
    """Runs the engine off the UI thread."""

    progress = Signal(float, str)
    finished = Signal(object, str)   # Stats, output path
    failed = Signal(str)

    def __init__(self, src: str, dst: str, profile: Profile):
        super().__init__()
        self._src, self._dst, self._profile = src, dst, profile
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            st = optimize(self._src, self._dst, self._profile,
                          progress=lambda f, m: self.progress.emit(f, m),
                          should_cancel=lambda: self._cancel)
            self.finished.emit(st, self._dst)
        except Cancelled:
            for p in (self._dst,):
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except OSError:
                        pass
            self.failed.emit("Cancelled.")
        except Exception as e:
            self.failed.emit(str(e))


class DropZone(QFrame):
    dropped = Signal(str)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setObjectName("drop")
        self.setMinimumHeight(120)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        self.label = QLabel("Drop a PDF here  ·  or click to browse")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setObjectName("dropLabel")
        lay.addWidget(self.label)

    def mousePressEvent(self, _):
        path, _f = QFileDialog.getOpenFileName(self, "Choose a PDF", "", "PDF files (*.pdf)")
        if path:
            self.dropped.emit(path)

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls() and any(
            u.toLocalFile().lower().endswith(".pdf") for u in e.mimeData().urls()
        ):
            e.acceptProposedAction()
            self.setProperty("hot", True)
            self.style().polish(self)

    def dragLeaveEvent(self, _):
        self.setProperty("hot", False)
        self.style().polish(self)

    def dropEvent(self, e: QDropEvent):
        self.setProperty("hot", False)
        self.style().polish(self)
        for u in e.mimeData().urls():
            p = u.toLocalFile()
            if p.lower().endswith(".pdf"):
                self.dropped.emit(p)
                return


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(QSize(560, 560))
        self.src: str | None = None
        self.thread: QThread | None = None
        self.worker: Worker | None = None

        root = QWidget()
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(22, 22, 22, 22)
        v.setSpacing(14)

        title = QLabel(APP_NAME)
        title.setObjectName("title")
        sub = QLabel("Optimize and compress your files for the web. First up: PDFs, with text, fonts and layout kept untouched.")
        sub.setObjectName("sub")
        sub.setWordWrap(True)
        v.addWidget(title)
        v.addWidget(sub)

        self.drop = DropZone()
        self.drop.dropped.connect(self.load)
        v.addWidget(self.drop)

        self.info = QLabel("")
        self.info.setObjectName("info")
        self.info.setWordWrap(True)
        self.info.setVisible(False)
        v.addWidget(self.info)

        # profiles
        box = QFrame()
        box.setObjectName("card")
        bv = QVBoxLayout(box)
        bv.setSpacing(8)
        self.group = QButtonGroup(self)
        for key, prof in PROFILES.items():
            rb = QRadioButton(f"{prof.label}   ·   {prof.ppi} ppi, quality {prof.quality}")
            rb.setProperty("key", key)
            hint = QLabel(prof.blurb)
            hint.setObjectName("hint")
            hint.setWordWrap(True)
            if key == "balanced":
                rb.setChecked(True)
            self.group.addButton(rb)
            bv.addWidget(rb)
            bv.addWidget(hint)
        v.addWidget(box)

        self.open_after = QCheckBox("Reveal the file when finished")
        self.open_after.setChecked(True)
        v.addWidget(self.open_after)

        self.bar = QProgressBar()
        self.bar.setVisible(False)
        self.bar.setTextVisible(False)
        v.addWidget(self.bar)

        self.status = QLabel("")
        self.status.setObjectName("status")
        self.status.setWordWrap(True)
        v.addWidget(self.status)

        v.addStretch(1)

        row = QHBoxLayout()
        row.addStretch(1)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self.do_cancel)
        self.go = QPushButton("Optimize")
        self.go.setObjectName("go")
        self.go.setEnabled(False)
        self.go.setDefault(True)
        self.go.clicked.connect(self.start)
        row.addWidget(self.cancel_btn)
        row.addWidget(self.go)
        v.addLayout(row)

        self.setStyleSheet(STYLE)

    # ---------- actions ----------

    def load(self, path: str) -> None:
        try:
            info = analyze(path)
        except Exception as e:
            QMessageBox.critical(self, APP_NAME, f"Couldn't read that PDF.\n\n{e}")
            return
        if info["encrypted"]:
            QMessageBox.warning(self, APP_NAME,
                                "This PDF is encrypted. Decrypt it first, then try again.")
            return
        self.src = path
        self.drop.label.setText(os.path.basename(path))
        pct_img = (info["image_bytes"] * 100 / info["size"]) if info["size"] else 0
        self.info.setText(
            f"{info['pages']} pages · {human(info['size'])} · {info['images']} images "
            f"({pct_img:.0f}% of the file)\n"
            f"Effective resolution: median {info['ppi_median']:.0f} ppi, "
            f"peak {info['ppi_max']:.0f} ppi"
            + (f" · {info['cmyk_images']} CMYK images will convert to RGB"
               if info["cmyk_images"] else "")
        )
        self.info.setVisible(True)
        self.status.setText("")
        self.go.setEnabled(True)

    def selected(self) -> Profile:
        btn = self.group.checkedButton()
        return PROFILES[btn.property("key")]

    def start(self) -> None:
        if not self.src:
            return
        prof = self.selected()
        stem, ext = os.path.splitext(self.src)
        dst, _f = QFileDialog.getSaveFileName(
            self, "Save optimized PDF as", f"{stem} - {prof.label}{ext}", "PDF files (*.pdf)"
        )
        if not dst:
            return

        self.go.setEnabled(False)
        self.drop.setEnabled(False)
        self.cancel_btn.setVisible(True)
        self.bar.setVisible(True)
        self.bar.setRange(0, 100)

        self.thread = QThread(self)
        self.worker = Worker(self.src, dst, prof)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.on_progress)
        self.worker.finished.connect(self.on_done)
        self.worker.failed.connect(self.on_fail)
        self.thread.start()

    def do_cancel(self) -> None:
        if self.worker:
            # Must stay a direct call. Routing this through a signal/slot would queue it
            # to the worker's own event loop, which is blocked inside run() - so the flag
            # would only be read after the work it was meant to interrupt had finished.
            self.worker.cancel()
            self.status.setText("Cancelling…")

    def on_progress(self, frac: float, msg: str) -> None:
        self.bar.setValue(int(frac * 100))
        self.status.setText(msg)

    def _teardown(self) -> None:
        if self.thread:
            self.thread.quit()
            self.thread.wait()
            self.thread = None
        self.worker = None
        self.go.setEnabled(True)
        self.drop.setEnabled(True)
        self.cancel_btn.setVisible(False)
        self.bar.setVisible(False)

    def on_done(self, st: Stats, dst: str) -> None:
        self._teardown()
        kept = st.skipped_lineart + st.skipped_small + st.skipped_nogain
        self.status.setText(
            f"<b>{human(st.size_before)} → {human(st.size_after)} "
            f"({st.reduction_pct:.1f}% smaller)</b><br>"
            f"{st.recompressed} images recompressed, {st.downsampled} downsampled, "
            f"{kept} kept as-is (line art / already optimal)"
            f"{', Fast Web View enabled' if st.linearized else ''}"
        )
        if self.open_after.isChecked():
            reveal(dst)

    def on_fail(self, msg: str) -> None:
        self._teardown()
        if msg == "Cancelled.":
            self.status.setText("Cancelled.")
        else:
            self.status.setText("")
            QMessageBox.critical(self, APP_NAME, f"Optimization failed.\n\n{msg}")


STYLE = """
QMainWindow, QWidget { background: palette(window); }
#title { font-size: 20px; font-weight: 600; }
#sub, #hint { color: palette(mid); }
#hint { font-size: 11px; margin-left: 22px; margin-top: -4px; }
#info { color: palette(text); font-size: 12px; }
#status { color: palette(text); font-size: 12px; }
#drop {
    border: 2px dashed palette(mid);
    border-radius: 10px;
    background: palette(base);
}
#drop[hot="true"] { border-color: palette(highlight); background: palette(alternate-base); }
#dropLabel { color: palette(mid); font-size: 13px; }
#card { border: 1px solid palette(mid); border-radius: 8px; padding: 10px; }
#go { padding: 6px 18px; font-weight: 600; }
QProgressBar { height: 6px; border-radius: 3px; background: palette(alternate-base); }
QProgressBar::chunk { border-radius: 3px; background: palette(highlight); }
"""


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    f = app.font()
    if sys.platform == "darwin":
        f.setPointSize(13)
    app.setFont(f)
    w = Window()
    w.show()
    # allow: open the app with a file argument
    if len(sys.argv) > 1 and sys.argv[1].lower().endswith(".pdf"):
        w.load(sys.argv[1])
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
