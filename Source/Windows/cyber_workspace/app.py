"""CYBER WORKSPACE — application entry point (Windows desktop).

Bootstrap order: logging → single-instance lock → data dir + settings →
engine (recovers previous session) → remote control server (optional) →
tray + main window → Qt loop. On exit: engine.shutdown() closes timer
segments, persists the session and restores normal power behaviour.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtCore import QLockFile, QStandardPaths, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from .core.engine import TaskEngine
from .platform.power import PowerManager
from .persistence.repos import default_data_dir
from .settings import AppSettings
from .ui.main_window import MainWindow
from .ui.tray import TrayIcon

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("cyber.app")

APP_VERSION = "1.0.0-rc.1"


def app_icon() -> QIcon:
    """Application icon from the bundled asset (Source/Windows/assets/icon).

    Search order: PyInstaller bundle (onedir _internal/assets/icon), then the
    development checkout next to the package. Returns a null icon when the
    asset is absent — the tray glyph stays programmatic in that case.
    """
    name = "assets/icon/app_icon_256.png"
    candidates = []
    if getattr(sys, "_MEIPASS", None):
        candidates.append(Path(sys._MEIPASS) / name)          # frozen (onedir)
    candidates.append(Path(__file__).resolve().parent.parent / name)  # dev tree
    for path in candidates:
        if path.is_file():
            return QIcon(str(path))
    log.warning("app icon asset not found; window icon left to Qt default")
    return QIcon()


def setup_remote(engine: TaskEngine, settings: AppSettings):
    """Start the remote control server when enabled. Returns
    (server|None, fingerprint|None, pairing_provider|None)."""
    if not settings.remote_enabled:
        return None, None, None
    from .remote.certgen import cert_fingerprint, generate_keypair, ssl_server_context
    from .remote.pairing import PairingManager
    from .remote.server import RemoteServer

    data = Path(engine.data_dir)
    cert = data / "remote-cert.pem"
    key = data / "remote-key.pem"
    try:
        if not cert.exists() or not key.exists():
            fingerprint = generate_keypair(cert, key)
        else:
            fingerprint = cert_fingerprint(cert)
    except Exception as exc:
        log.error("remote TLS setup failed: %s", exc)
        return None, None, None
    pairing = PairingManager(engine.device_repo, engine.audit_repo)

    def provider() -> str:
        return pairing.new_code()

    server = RemoteServer(engine, engine.bus, settings.remote_host,
                          settings.remote_port, cert, key, fingerprint, pairing)
    server.start()
    return server, fingerprint, provider


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    QApplication.setApplicationName("Cyber Workspace")
    QApplication.setApplicationVersion(APP_VERSION)
    app = QApplication(argv)
    app.setQuitOnLastWindowClosed(False)
    icon = app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)

    lock = QLockFile(str(Path(QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.TempLocation)) / "cyber-workspace.lock"))
    if not lock.tryLock(100):
        QMessageBox.warning(None, "CYBER WORKSPACE",
                            "Another instance is already running.")
        return 1

    data_dir = default_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    settings = AppSettings.load(data_dir)
    power = PowerManager()
    engine = TaskEngine(data_dir, settings=settings.engine_overrides(), power=power)
    log.info("engine ready: %d task(s) recovered", len(engine.tasks))

    server, fingerprint, pairing_provider = setup_remote(engine, settings)

    tray = TrayIcon(engine) if TrayIcon.isSystemTrayAvailable() else None
    window = MainWindow(engine, settings, power, tray, fingerprint, pairing_provider)
    if tray:
        tray.show()
        tray.restore_requested.connect(window.showNormal)
        tray.exit_requested.connect(window._exit)
        tray.notifications_requested.connect(lambda: window._show_panel(3))
        tray.open_task_requested.connect(window.open_task_from_tray)
        window.rain.setEnabled(settings.rain_enabled)
        app.aboutToQuit.connect(tray.hide)
    app.aboutToQuit.connect(lambda: (engine.shutdown(), settings.save(data_dir)))
    if server:
        app.aboutToQuit.connect(server.stop)

    window.show()
    if settings.start_minimized and tray:
        window.hide()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
