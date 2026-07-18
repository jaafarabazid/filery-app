"""Desktop UI: drop a print file in, get a web-ready one out.

Frameless dark window in Filery's design language. The engine runs on a worker
thread so the window stays responsive; see Worker and the cancel path.
"""

from __future__ import annotations

import os
import sys
import subprocess

from PySide6.QtCore import QObject, QPoint, QRectF, Qt, QThread, Signal
from PySide6.QtGui import (
    QBrush, QColor, QDragEnterEvent, QDropEvent, QPainter, QPainterPath,
)
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFileDialog, QFrame, QGraphicsDropShadowEffect,
    QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton, QVBoxLayout,
    QWidget,
)

from .optimizers.pdf import PROFILES, Cancelled, Profile, Stats, analyze, optimize

APP_NAME = "Filery"

# --- design tokens (shared with the app's visual identity) ---
# All solid, no alpha. Transparent colors double-composite at rounded-border
# corners and leave visible light "dots" at the joins, so everything is opaque.
BG = "#14161A"           # window base
PANEL = "#1B1D21"        # cards, drop zone, titlebar
ELEV = "#25272C"         # raised chips / progress track
FG = "#EBEBF0"           # primary text (neutral, minimal blue tint)
TXT2 = "#A6A8AF"         # secondary text
TXT3 = "#83858C"         # tertiary text
TXT4 = "#63656C"         # muted labels
LINE = "#2A2C31"         # subtle borders
LINE2 = "#3C3F45"        # stronger borders (ghost buttons, unselected radio)
LINE_HOVER = "#55585F"   # border on hover
ACTIVE = "#E6E6EC"       # selected / primary action (light grey, no blue)
ACTIVE_HI = "#F2F2F6"    # primary action hover
SEL_BORDER = "#83858D"   # selected card border
SEL_BORDER_HI = "#9D9FA7"  # selected card border on hover
SEL_BG = "#24262C"       # selected card fill
AMBER = "#F59E0B"        # window control dot only
RED = "#B91C1C"          # window control dot only
GREEN = "#3FB950"        # success text only


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


def estimate_size(info: dict, profile: Profile) -> int:
    """Rough predicted output size, shown with a '≈'. Biased slightly high so the
    real result tends to beat it. The exact figure replaces it after a run."""
    img = info["image_bytes"]
    other = max(0, info["size"] - img)
    ppi = info["ppi_median"] or profile.ppi
    downscale = min(1.0, profile.ppi / ppi) ** 2       # JPEG size tracks pixel area
    qf = {88: 0.52, 82: 0.40, 74: 0.32}.get(profile.quality, 0.4)
    return int(other * 0.6 + img * downscale * qf)


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
            if os.path.exists(self._dst):
                try:
                    os.remove(self._dst)
                except OSError:
                    pass
            self.failed.emit("Cancelled.")
        except Exception as e:  # noqa: BLE001 - surfaced to the user verbatim
            self.failed.emit(str(e))


class TitleBar(QFrame):
    """Custom chrome: frameless windows lose the native bar, so we draw our own,
    including a drag region and functional window buttons."""

    def __init__(self, win: "Window"):
        super().__init__()
        self.win = win
        self.setObjectName("titlebar")
        self.setFixedHeight(44)
        self._press: QPoint | None = None

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 14, 0)
        lay.setSpacing(8)
        for color, slot in ((RED, win.close), (AMBER, win.showMinimized)):
            b = QPushButton()
            b.setFixedSize(13, 13)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(f"background:{color}; border:none; border-radius:6px;")
            b.clicked.connect(slot)
            lay.addWidget(b)
        disabled = QLabel()
        disabled.setFixedSize(13, 13)
        disabled.setStyleSheet(f"background:{LINE2}; border-radius:6px;")
        lay.addWidget(disabled)
        lay.addStretch(1)
        t = QLabel(APP_NAME)
        t.setObjectName("winTitle")
        lay.addWidget(t)
        lay.addStretch(1)
        lay.addSpacing(52)

    # drag the frameless window by its titlebar
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._press = e.globalPosition().toPoint() - self.win.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._press is not None and e.buttons() & Qt.LeftButton:
            self.win.move(e.globalPosition().toPoint() - self._press)

    def mouseReleaseEvent(self, _):
        self._press = None


class DropZone(QFrame):
    dropped = Signal(str)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setObjectName("drop")
        self.setFixedHeight(104)
        self.setCursor(Qt.PointingHandCursor)

        self.lay = QHBoxLayout(self)
        self.lay.setContentsMargins(20, 0, 20, 0)
        self.lay.setSpacing(16)
        self._build_empty()

    def _clear(self):
        def drop(layout):
            while layout.count():
                item = layout.takeAt(0)
                w = item.widget()
                if w:
                    # setParent(None) removes it from view now; deleteLater alone
                    # defers until the event loop unwinds, leaving it painted.
                    w.setParent(None)
                    w.deleteLater()
                elif item.layout():      # nested layouts hold their own widgets
                    drop(item.layout())
                    item.layout().deleteLater()
        drop(self.lay)

    def _build_empty(self):
        self._clear()
        self.setProperty("loaded", False)
        self.style().polish(self)
        icon = QLabel("+")
        icon.setObjectName("dropPlus")
        icon.setFixedSize(44, 44)
        icon.setAlignment(Qt.AlignCenter)
        text = QVBoxLayout()
        text.setSpacing(2)
        a = QLabel("Drop a PDF here")
        a.setObjectName("dropMain")
        b = QLabel("or click to browse")
        b.setObjectName("dropSub")
        text.addWidget(a)
        text.addWidget(b)
        self.lay.addStretch(1)
        self.lay.addWidget(icon)
        self.lay.addLayout(text)
        self.lay.addStretch(1)

    def show_file(self, name: str, meta: str):
        self._clear()
        self.setProperty("loaded", True)
        self.style().polish(self)
        icon = QLabel("PDF")
        icon.setObjectName("fileIcon")
        icon.setFixedSize(52, 52)
        icon.setAlignment(Qt.AlignCenter)
        col = QVBoxLayout()
        col.setSpacing(3)
        fn = QLabel(name)
        fn.setObjectName("fileName")
        fp = QLabel(meta)
        fp.setObjectName("filePath")
        col.addWidget(fn)
        col.addWidget(fp)
        change = QPushButton("Change")
        change.setObjectName("ghost")
        change.setCursor(Qt.PointingHandCursor)
        change.clicked.connect(self._browse)
        self.lay.addWidget(icon)
        self.lay.addLayout(col, 1)
        self.lay.addWidget(change)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose a PDF", "", "PDF files (*.pdf)")
        if path:
            self.dropped.emit(path)

    def mousePressEvent(self, _):
        if not self.property("loaded"):
            self._browse()

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


class RadioDot(QWidget):
    """Radio indicator painted as single antialiased circles.

    A CSS border-radius circle is drawn by Qt as four arcs that seam where they
    meet; painting one ellipse path per element avoids those light "dot" joins.
    """

    def __init__(self):
        super().__init__()
        self.setFixedSize(18, 18)
        self._on = False

    def set_on(self, on: bool):
        if on != self._on:
            self._on = on
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        c = QRectF(1.5, 1.5, 15, 15)
        if self._on:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(ACTIVE))
            p.drawEllipse(c)                       # solid light disc
            p.setBrush(QColor(BG))
            p.drawEllipse(QRectF(6.2, 6.2, 5.6, 5.6))   # dark center
        else:
            pen = p.pen()
            pen.setColor(QColor(LINE2))
            pen.setWidthF(1.6)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(c)                       # thin ring only


class ProfileCard(QFrame):
    """Selectable quality card. Background and border are painted (not CSS) so
    the rounded corners stay clean and hover/selected transitions are seamless."""

    clicked = Signal(str)

    def __init__(self, key: str, profile: Profile):
        super().__init__()
        self.key = key
        self.profile = profile
        self.setCursor(Qt.PointingHandCursor)
        self._selected = False
        self._hover = False

        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 13, 16, 13)
        lay.setSpacing(12)
        self.radio = RadioDot()
        left = QVBoxLayout()
        left.setSpacing(3)
        t = QLabel(profile.label)
        t.setObjectName("cardTitle")
        s = QLabel(f"{profile.ppi} ppi  ·  quality {profile.quality}")
        s.setObjectName("cardSpec")
        left.addWidget(t)
        left.addWidget(s)
        right = QVBoxLayout()
        right.setSpacing(3)
        self.size = QLabel("")
        self.size.setObjectName("cardSize")
        self.size.setAlignment(Qt.AlignRight)
        self.note = QLabel("")
        self.note.setObjectName("cardNote")
        self.note.setAlignment(Qt.AlignRight)
        right.addWidget(self.size)
        right.addWidget(self.note)
        lay.addWidget(self.radio)
        lay.addLayout(left, 1)
        lay.addLayout(right)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(0.75, 0.75, self.width() - 1.5, self.height() - 1.5)
        path = QPainterPath()
        path.addRoundedRect(r, 11, 11)
        if self._selected:
            fill = QColor(SEL_BG)
            border = QColor(SEL_BORDER_HI if self._hover else SEL_BORDER)
            width = 1.5
        else:
            fill = QColor(PANEL)
            border = QColor(LINE_HOVER if self._hover else LINE)
            width = 1.0
        p.fillPath(path, QBrush(fill))
        pen = p.pen()
        pen.setColor(border)
        pen.setWidthF(width)
        p.setPen(pen)
        p.drawPath(path)

    def set_estimate(self, text: str, note: str):
        self.size.setText(text)
        self.note.setText(note)

    def set_selected(self, on: bool):
        self._selected = on
        self.radio.set_on(on)
        self.size.setObjectName("cardSizeSel" if on else "cardSize")
        self.size.style().unpolish(self.size)
        self.size.style().polish(self.size)
        self.update()

    def enterEvent(self, _):
        self._hover = True
        self.update()

    def leaveEvent(self, _):
        self._hover = False
        self.update()

    def mousePressEvent(self, _):
        self.clicked.emit(self.key)


class Window(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setFixedSize(660, 720)

        self.src: str | None = None
        self.info: dict | None = None
        self.cards: dict[str, ProfileCard] = {}
        self.selected_key = "balanced"
        self.thread: QThread | None = None
        self.worker: Worker | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(TitleBar(self))

        body = QVBoxLayout()
        body.setContentsMargins(28, 18, 28, 22)
        body.setSpacing(15)

        header = QVBoxLayout()
        header.setSpacing(5)
        kicker = QLabel("YOUR FILES BAKERY")
        kicker.setObjectName("kicker")
        h = QLabel("Optimize for the web")
        h.setObjectName("h1")
        sub = QLabel("Compress files without wrecking quality. First up: PDFs, "
                     "with text, fonts and layout untouched.")
        sub.setObjectName("sub")
        sub.setWordWrap(True)
        header.addWidget(kicker)
        header.addWidget(h)
        header.addWidget(sub)
        body.addLayout(header)

        self.drop = DropZone()
        self.drop.dropped.connect(self.load)
        body.addWidget(self.drop)

        self.chips = QHBoxLayout()
        self.chips.setSpacing(10)
        self.chips_host = QWidget()
        self.chips_host.setLayout(self.chips)
        self.chips_host.setVisible(False)
        body.addWidget(self.chips_host)

        self.section = QLabel("QUALITY")
        self.section.setObjectName("sectionLbl")
        body.addWidget(self.section)
        for key, prof in PROFILES.items():
            card = ProfileCard(key, prof)
            card.clicked.connect(self.select)
            self.cards[key] = card
            body.addWidget(card)
        self.cards[self.selected_key].set_selected(True)

        body.addStretch(1)

        self.status = QLabel("")
        self.status.setObjectName("status")
        self.status.setWordWrap(True)
        body.addWidget(self.status)

        self.bar = QProgressBar()
        self.bar.setObjectName("bar")
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(6)
        self.bar.setVisible(False)
        body.addWidget(self.bar)

        footer = QHBoxLayout()
        self.reveal_cb = QCheckBox("Reveal when finished")
        self.reveal_cb.setObjectName("reveal")
        self.reveal_cb.setChecked(True)
        self.reveal_cb.setCursor(Qt.PointingHandCursor)
        footer.addWidget(self.reveal_cb)
        footer.addStretch(1)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("ghost")
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self.do_cancel)
        self.go = QPushButton("Optimize")
        self.go.setObjectName("go")
        self.go.setFixedHeight(40)
        self.go.setMinimumWidth(132)
        self.go.setCursor(Qt.PointingHandCursor)
        self.go.setEnabled(False)
        self.go.clicked.connect(self.start)
        shadow = QGraphicsDropShadowEffect()
        shadow.setColor(QColor(0, 0, 0, 150))   # depth under the light button
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 2)
        self.go.setGraphicsEffect(shadow)
        footer.addWidget(self.cancel_btn)
        footer.addWidget(self.go)
        body.addLayout(footer)

        outer.addLayout(body)
        self.setStyleSheet(STYLE)

    # rounded dark window background
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, self.width(), self.height()), 14, 14)
        p.fillPath(path, QBrush(QColor(BG)))
        p.setPen(QColor(LINE))
        p.drawPath(path)

    # ---------- data ----------

    def _chip(self, value: str, label: str) -> QWidget:
        w = QFrame()
        w.setObjectName("chip")
        v = QVBoxLayout(w)
        v.setContentsMargins(14, 8, 14, 8)
        v.setSpacing(1)
        a = QLabel(value)
        a.setObjectName("chipVal")
        b = QLabel(label)
        b.setObjectName("chipLbl")
        v.addWidget(a)
        v.addWidget(b)
        return w

    def load(self, path: str):
        try:
            info = analyze(path)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, APP_NAME, f"Couldn't read that PDF.\n\n{e}")
            return
        if info["encrypted"]:
            QMessageBox.warning(self, APP_NAME,
                                "This PDF is encrypted. Decrypt it first, then try again.")
            return
        self.src = path
        self.info = info
        self.drop.show_file(
            os.path.basename(path),
            f"{info['pages']} pages  ·  {human(info['size'])}  ·  ready",
        )

        while self.chips.count():
            item = self.chips.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        pct_img = (info["image_bytes"] * 100 / info["size"]) if info["size"] else 0
        stats = [
            (str(info["images"]), "images"),
            (f"{pct_img:.0f}%", "is image data"),
            (f"{info['ppi_median']:.0f}", "median ppi"),
        ]
        if info["cmyk_images"]:
            stats.append(("CMYK", "will go sRGB"))
        for v, l in stats:
            self.chips.addWidget(self._chip(v, l))
        self.chips.addStretch(1)
        self.chips_host.setVisible(True)

        for key, card in self.cards.items():
            est = estimate_size(info, card.profile)
            saved = 100 - est * 100 / info["size"] if info["size"] else 0
            note = f"≈{saved:.0f}% smaller"
            if key == "balanced":
                note += "  ·  recommended"
            card.set_estimate(f"≈ {human(est)}", note)

        self.status.setText("")
        self.go.setEnabled(True)

    def select(self, key: str):
        if self.selected_key == key:
            return
        self.cards[self.selected_key].set_selected(False)
        self.cards[key].set_selected(True)
        self.selected_key = key

    # ---------- run ----------

    def start(self):
        if not self.src:
            return
        prof = PROFILES[self.selected_key]
        stem, ext = os.path.splitext(self.src)
        dst, _ = QFileDialog.getSaveFileName(
            self, "Save optimized PDF as", f"{stem} - {prof.label}{ext}", "PDF files (*.pdf)"
        )
        if not dst:
            return

        self.go.setEnabled(False)
        self.drop.setEnabled(False)
        for c in self.cards.values():
            c.setEnabled(False)
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

    def do_cancel(self):
        if self.worker:
            # Direct call on purpose. A queued signal would land in the worker's own
            # blocked event loop and only run after the work it meant to interrupt.
            self.worker.cancel()
            self.status.setText("Cancelling…")

    def on_progress(self, frac: float, msg: str):
        self.bar.setValue(int(frac * 100))
        self.status.setText(msg)

    def _teardown(self):
        if self.thread:
            self.thread.quit()
            self.thread.wait()
            self.thread = None
        self.worker = None
        self.go.setEnabled(True)
        self.drop.setEnabled(True)
        for c in self.cards.values():
            c.setEnabled(True)
        self.cancel_btn.setVisible(False)
        self.bar.setVisible(False)

    def on_done(self, st: Stats, dst: str):
        self._teardown()
        self.status.setProperty("kind", "ok")
        self.status.style().polish(self.status)
        self.status.setText(
            f"Done. {human(st.size_before)} → {human(st.size_after)} "
            f"({st.reduction_pct:.0f}% smaller)"
            f"{'  ·  Fast Web View' if st.linearized else ''}"
        )
        if self.reveal_cb.isChecked():
            reveal(dst)

    def on_fail(self, msg: str):
        self._teardown()
        if msg == "Cancelled.":
            self.status.setText("Cancelled.")
        else:
            self.status.setText("")
            QMessageBox.critical(self, APP_NAME, f"Optimization failed.\n\n{msg}")


STYLE = f"""
* {{ color: {FG}; font-family: -apple-system, 'SF Pro Display', 'Segoe UI', 'Inter', sans-serif; }}
QToolTip {{ color:{FG}; background:{ELEV}; border:1px solid {LINE}; }}

#titlebar {{ background:{PANEL}; border-top-left-radius:14px; border-top-right-radius:14px;
             border-bottom:1px solid {LINE}; }}
#winTitle {{ color:{TXT3}; font-size:12px; font-weight:600; letter-spacing:0.5px; }}

#kicker {{ color:{TXT3}; font-size:10.5px; font-weight:700; letter-spacing:2.2px; }}
#h1 {{ font-size:22px; font-weight:700; letter-spacing:-0.3px; }}
#sub {{ color:{TXT2}; font-size:12.5px; }}
#sectionLbl {{ color:{TXT4}; font-size:10.5px; font-weight:700; letter-spacing:1.6px; }}

#drop {{ background:{PANEL}; border:1.5px dashed {LINE2}; border-radius:12px; }}
#drop[loaded="true"] {{ border:1px solid {LINE}; }}
#drop[hot="true"] {{ border:1.5px solid {SEL_BORDER}; background:{SEL_BG}; }}
#dropPlus {{ background:{ELEV}; border-radius:10px; color:{TXT3}; font-size:22px; font-weight:400; }}
#dropMain {{ font-size:14px; font-weight:600; }}
#dropSub {{ color:{TXT3}; font-size:12px; }}
#fileIcon {{ background:{ELEV}; border:1px solid {LINE}; border-radius:10px;
             color:{TXT2}; font-size:13px; font-weight:800; }}
#fileName {{ font-size:14px; font-weight:600; }}
#filePath {{ color:{TXT3}; font-size:12px; }}

#chip {{ background:{PANEL}; border:1px solid {LINE}; border-radius:9px; }}
#chipVal {{ font-size:15px; font-weight:700; }}
#chipLbl {{ color:{TXT4}; font-size:10px; }}

/* ProfileCard and RadioDot paint themselves; only their text is styled here. */
#cardTitle {{ font-size:14.5px; font-weight:650; }}
#cardSpec {{ color:{TXT3}; font-size:12px; }}
#cardSize {{ font-size:14px; font-weight:700; color:{TXT2}; }}
#cardSizeSel {{ font-size:14px; font-weight:800; color:{FG}; }}
#cardNote {{ color:{TXT3}; font-size:11px; }}

#ghost {{ background:transparent; border:1px solid {LINE2}; border-radius:8px;
          padding:7px 15px; color:{TXT2}; font-size:12px; font-weight:600; }}
#ghost:hover {{ border-color:{LINE_HOVER}; color:{FG}; }}
#reveal {{ color:{TXT3}; font-size:12px; }}
#reveal::indicator {{ width:16px; height:16px; border:1px solid {LINE2};
                      border-radius:5px; background:{PANEL}; }}
#reveal::indicator:checked {{ background:{ACTIVE}; border-color:{ACTIVE}; }}
#status {{ color:{TXT2}; font-size:12px; }}
#status[kind="ok"] {{ color:{GREEN}; font-weight:600; }}

#bar {{ background:{ELEV}; border-radius:3px; }}
#bar::chunk {{ background:{ACTIVE}; border-radius:3px; }}

#go {{ background:{ACTIVE}; border:none; border-radius:9px; color:{BG}; font-size:14px; font-weight:700; }}
#go:hover {{ background:{ACTIVE_HI}; }}
#go:disabled {{ background:{LINE2}; color:{TXT4}; }}
"""


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    w = Window()
    w.show()
    if len(sys.argv) > 1 and sys.argv[1].lower().endswith(".pdf"):
        w.load(sys.argv[1])
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
