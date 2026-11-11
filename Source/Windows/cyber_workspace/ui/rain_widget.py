"""CYBER WORKSPACE — lightweight digital rain header widget.

Subtle matrix-inspired animation for the dashboard header. Performance rules:
~15 FPS, only runs when visible AND enabled in settings, paints only visible
columns, no timers allocated when hidden. This is decorative — it can be
disabled without affecting any functionality.
"""
from __future__ import annotations

import random

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor, QPainter, QFont
from PySide6.QtWidgets import QWidget

from . import theme


class RainWidget(QWidget):
    """Falling katakana/digit columns in neon green. Height is small (header)."""

    GLYPHS = "01アイウエオカキクケコサシスセソ<>*+#"

    def __init__(self, parent: QWidget | None = None, fps: int = 15):
        super().__init__(parent)
        self.setFixedHeight(46)
        self._fps = fps
        self._drops: list[float] = []
        self._speeds: list[float] = []
        self._cols = 0
        self._font = theme.mono_font(10)
        self._timer = QTimer(self)
        self._timer.setInterval(int(1000 / fps))
        self._timer.timeout.connect(self._step)
        self._rng = random.Random(0xC7BA)

    # -- control -----------------------------------------------------------
    def set_running(self, on: bool) -> None:
        if on and self.isVisible() and self.isEnabled():
            self._ensure_drops()
            self._timer.start()
        else:
            self._timer.stop()
            self.update()

    def showEvent(self, e) -> None:  # noqa: N802
        super().showEvent(e)
        self.set_running(True)

    def hideEvent(self, e) -> None:  # noqa: N802
        self._timer.stop()
        super().hideEvent(e)

    def _ensure_drops(self) -> None:
        w = max(1, self.width())
        n = w // 12
        if n != self._cols:
            self._cols = n
            rng = self._rng
            self._drops = [rng.uniform(-20, 0) for _ in range(n)]
            self._speeds = [rng.uniform(0.35, 1.1) for _ in range(n)]

    def _step(self) -> None:
        self._ensure_drops()
        for i in range(self._cols):
            self._drops[i] += self._speeds[i]
            if self._drops[i] > self.height() / 12 + 4:
                self._drops[i] = self._rng.uniform(-6, 0)
        self.update()

    # -- painting ------------------------------------------------------------
    def paintEvent(self, e) -> None:  # noqa: N802
        if not self.isEnabled():
            return
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(theme.BG_ALT))
        p.setFont(self._font)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        for i in range(self._cols):
            x = i * 12 + 2
            head = self._drops[i]
            for tail in range(6):
                row = head - tail
                if row < 0 or row > self.height() / 12:
                    continue
                g = self.GLYPHS[(i * 7 + tail * 13 + int(row * 3)) % len(self.GLYPHS)]
                if tail == 0:
                    color = QColor(theme.NEON)
                else:
                    alpha = max(24, 200 - tail * 42)
                    color = QColor(theme.NEON_DIM)
                    color.setAlpha(alpha)
                p.setPen(color)
                p.drawText(x, int(row * 12) + 11, g)
        p.end()
