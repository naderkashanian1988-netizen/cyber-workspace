"""CYBER WORKSPACE — visual identity: black + neon green cybersecurity theme."""
from __future__ import annotations

from PySide6.QtGui import QColor, QFont

# ---------------------------------------------------------------- palette
BG = "#0A0C0A"            # deep black-green
BG_ALT = "#0E120D"        # charcoal panel
SURFACE = "#111611"       # card surface
SURFACE_HI = "#16201A"    # hovered
LINE = "#1E2A20"          # subtle borders
NEON = "#00FF66"          # primary neon green
NEON_DIM = "#00C853"
NEON_DARK = "#062F16"
AMBER = "#FFB300"         # waiting
CYAN = "#00E5FF"          # info / network waiting
RED = "#FF3D3D"           # error
GRAY = "#9AA09A"          # unknown / muted
TEXT = "#C8FACC"          # main text (green-tinted white)
TEXT_DIM = "#6F8F75"

STATE_COLORS = {
    "RUNNING": NEON, "WAITING_FOR_USER": AMBER, "NETWORK_WAITING": CYAN,
    "COMPLETED": NEON_DIM, "ERROR": RED, "UNRESPONSIVE": RED,
    "PAUSED": GRAY, "UNKNOWN": GRAY,
}

MONO_CANDIDATES = ["Cascadia Mono", "Consolas", "JetBrainsMono NFM",
                   "DejaVu Sans Mono", "Courier New"]


def mono_font(point_size: int = 9, bold: bool = False) -> QFont:
    f = QFont()
    f.setFamilies(MONO_CANDIDATES)
    f.setPointSize(point_size)
    f.setBold(bold)
    f.setStyleHint(QFont.StyleHint.Monospace)
    return f


def ui_font(point_size: int = 10, bold: bool = False) -> QFont:
    f = QFont()
    f.setFamilies(["Segoe UI Variable", "Segoe UI", "Inter", "Noto Sans"])
    f.setPointSize(point_size)
    f.setBold(bold)
    return f


def qss() -> str:
    return f"""
    QWidget {{ background: {BG}; color: {TEXT}; font-size: 10pt; }}
    QMainWindow, QDialog {{ background: {BG}; }}

    /* ---- top bar / headers ---- */
    #TitleLabel {{ color: {NEON}; font-size: 15pt; font-weight: 700;
                   letter-spacing: 2px; }}
    #SubtitleLabel {{ color: {TEXT_DIM}; font-size: 9pt; }}
    #HeaderFrame {{ background: {BG_ALT}; border-bottom: 1px solid {LINE}; }}

    /* ---- panels ---- */
    QFrame#Panel {{ background: {SURFACE}; border: 1px solid {LINE};
                    border-radius: 6px; }}
    QLabel#PanelTitle {{ color: {NEON}; font-weight: 600; letter-spacing: 1px; }}
    QLabel#Mono {{ font-family: "Cascadia Mono", "Consolas", monospace;
                   color: {TEXT}; }}
    QLabel#MonoDim {{ font-family: "Cascadia Mono", "Consolas", monospace;
                      color: {TEXT_DIM}; }}

    /* ---- task cards ---- */
    QFrame#TaskCard {{ background: {SURFACE}; border: 1px solid {LINE};
                       border-radius: 6px; }}
    QFrame#TaskCard:hover {{ border: 1px solid {NEON_DARK};
                             background: {SURFACE_HI}; }}
    QLabel#CardTitle {{ color: {TEXT}; font-weight: 600; font-size: 10.5pt; }}
    QLabel#StateChip {{ font-family: "Cascadia Mono", monospace;
                        font-size: 8.5pt; font-weight: 700; }}
    QLabel#TimerValue {{ font-family: "Cascadia Mono", "Consolas", monospace; }}

    /* ---- buttons ---- */
    QPushButton {{ background: {BG_ALT}; color: {TEXT};
                   border: 1px solid {LINE}; border-radius: 4px;
                   padding: 5px 12px; }}
    QPushButton:hover {{ border-color: {NEON}; color: {NEON}; }}
    QPushButton:disabled {{ color: {TEXT_DIM}; border-color: {LINE}; }}
    QPushButton#Primary {{ background: {NEON_DARK}; color: {NEON};
                           border: 1px solid {NEON_DIM}; font-weight: 600; }}
    QPushButton#Primary:hover {{ background: #0A3D1E; }}
    QPushButton#Danger {{ color: {RED}; border-color: #4A1616; }}
    QPushButton#Danger:hover {{ border-color: {RED}; }}

    /* ---- lists ---- */
    QListWidget {{ background: {BG_ALT}; border: 1px solid {LINE};
                   border-radius: 6px; outline: 0; }}
    QListWidget::item {{ margin: 6px; border-radius: 6px; background: transparent; }}
    QListWidget::item:selected {{ background: transparent;
                                  border: 1px solid {NEON_DARK}; }}

    /* ---- inputs ---- */
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit {{
        background: {BG}; border: 1px solid {LINE}; border-radius: 4px;
        padding: 5px; selection-background-color: {NEON_DARK}; }}
    QLineEdit:focus, QComboBox:focus {{ border-color: {NEON_DIM}; }}
    QComboBox QAbstractItemView {{ background: {SURFACE};
                                   selection-background-color: {NEON_DARK}; }}

    /* ---- misc ---- */
    QStatusBar {{ background: {BG_ALT}; color: {TEXT_DIM};
                  border-top: 1px solid {LINE}; }}
    QMenu {{ background: {SURFACE}; border: 1px solid {LINE}; }}
    QMenu::item:selected {{ background: {NEON_DARK}; color: {NEON}; }}
    QToolTip {{ background: {SURFACE}; color: {TEXT}; border: 1px solid {NEON_DIM}; }}
    QProgressBar {{ background: {BG}; border: 1px solid {LINE};
                    border-radius: 3px; text-align: center;
                    color: {TEXT_DIM}; height: 12px; }}
    QProgressBar::chunk {{ background: {NEON_DIM}; border-radius: 2px; }}
    QCheckBox {{ color: {TEXT}; }}
    QTabWidget::pane {{ border: 1px solid {LINE}; background: {SURFACE}; }}
    QTabBar::tab {{ background: {BG_ALT}; color: {TEXT_DIM}; padding: 6px 14px;
                    border: 1px solid {LINE}; }}
    QTabBar::tab:selected {{ color: {NEON}; border-bottom: 2px solid {NEON}; }}
    QScrollArea {{ border: 0; }}
    """


def hex_color(s: str) -> QColor:
    return QColor(s)
