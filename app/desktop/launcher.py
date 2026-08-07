"""Desktop launcher for the packaged School Finance app (ticket 13).

The shipped artifact is a single hidden ``.exe`` (PyInstaller, ``--windowed``).
Double-clicking it starts the FastAPI server on localhost in a background
thread, opens the default browser, and shows a system-tray icon (Open app /
Quit). A fixed control port on loopback acts as a single-instance lock: a
second launch pokes the running instance (which re-opens its browser) and exits
instead of starting another server. Data (SQLite DB, backups, logo) lives next
to the .exe so the school can back up by copying the folder (ADR 0001).

Everything testable is a plain function/class with no GUI imports at module
scope, so the test suite never needs pystray/Pillow installed. ``main()`` is
the only entry point that touches the tray and the browser.
"""

from __future__ import annotations

import logging
import os
import socket
import sys
import threading
import time
import webbrowser
from argparse import ArgumentParser, Namespace
from pathlib import Path
from typing import Any, Callable

APP_NAME = "School Finance"
DEFAULT_PORT = 8000
# Loopback control port for single-instance signalling. 48913 sits in the IANA
# dynamic/private range (49152-65535 is ephemeral; 1024-49151 is registered but
# 48913 is effectively unused in practice).
DEFAULT_CTRL_PORT = 48913
# How many loopback ports past the preferred one to scan before giving up.
MAX_PORT_SCAN = 100

_LOGGER = logging.getLogger("school_finance.launcher")


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def is_frozen() -> bool:
    """True when running from a PyInstaller bundle."""
    return bool(getattr(sys, "frozen", False))


def app_data_dir() -> Path:
    """The writable data folder: next to the .exe when packaged, else the repo.

    Database, backups and the uploaded logo all live here so the school backs up
    by copying the whole folder.
    """
    if is_frozen():
        return Path(sys.executable).resolve().parent / "data"
    return Path(__file__).resolve().parents[2] / "data"


def _resource_path(name: str) -> Path:
    """A bundled data file: inside the PyInstaller archive when frozen."""
    base = getattr(sys, "_MEIPASS", None)
    if base is None:
        base = Path(__file__).resolve().parents[2] / "packaging"
    return Path(base) / name


# ---------------------------------------------------------------------------
# Ports / URLs
# ---------------------------------------------------------------------------


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return True
    return False


def resolve_port(preferred: int) -> int:
    """Return ``preferred`` if free, otherwise the next free loopback port."""
    if not _port_in_use(preferred):
        return preferred
    for port in range(preferred + 1, preferred + MAX_PORT_SCAN):
        if not _port_in_use(port):
            return port
    raise RuntimeError(f"No free port found near {preferred}.")


def instance_url(port: int) -> str:
    return f"http://127.0.0.1:{port}"


# ---------------------------------------------------------------------------
# Single instance
# ---------------------------------------------------------------------------


class InstanceGuard:
    """Loopback control socket: the single-instance lock and activation channel.

    The first process binds the control port and keeps it open for its whole
    life; a second process fails to bind (exclusive on Windows) and instead
    connects to signal the first, whose listener fires ``on_activate`` (which
    re-opens the browser). The socket is bound without SO_REUSEADDR so two
    instances can never both hold it.
    """

    def __init__(self, ctrl_port: int, on_activate: Callable[[], None]) -> None:
        self._ctrl_port = ctrl_port
        self._on_activate = on_activate
        self._sock: socket.socket | None = None
        self._closing = False

    def acquire(self) -> bool:
        """Bind the control socket; ``False`` means another instance is running."""
        if self._sock is not None:
            return True
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(("127.0.0.1", self._ctrl_port))
        except OSError:
            sock.close()
            return False
        sock.listen(1)
        self._sock = sock
        threading.Thread(
            target=self._accept_loop, name="instance-listener", daemon=True
        ).start()
        return True

    def _accept_loop(self) -> None:
        sock = self._sock
        if sock is None:
            return
        while not self._closing:
            try:
                conn, _ = sock.accept()
            except OSError:
                break
            with conn:
                pass  # a ping; closing it tells the sender the poke arrived
            try:
                self._on_activate()
            except Exception:
                _LOGGER.exception("on_activate callback failed")

    def close(self) -> None:
        self._closing = True
        sock = self._sock
        self._sock = None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass


def notify_running_instance(ctrl_port: int, *, timeout: float = 2.0) -> bool:
    """Poke the running instance so it opens its browser. Returns success."""
    try:
        with socket.create_connection(("127.0.0.1", ctrl_port), timeout=timeout):
            return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Server management
# ---------------------------------------------------------------------------


class ServerHandle:
    """Runs uvicorn on loopback in a background thread and can stop it.

    ``stop()`` is non-blocking (sets uvicorn's ``should_exit`` so the current
    request finishes and the server drains); ``join()`` waits for the thread.
    The in-app shutdown button runs in a uvicorn worker thread, so the stopper
    must never block on ``join`` or the request could never complete.
    """

    def __init__(self, port: int, app: Any) -> None:
        self.port = port
        self._app = app
        self._server: Any = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        return instance_url(self.port)

    def start(self) -> None:
        import uvicorn

        config = uvicorn.Config(
            self._app,
            host="127.0.0.1",
            port=self.port,
            log_level="info",
            access_log=False,
            log_config=None,
        )
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(
            target=self._server.run, name="uvicorn-server", daemon=True
        )
        self._thread.start()

    def wait_until_serving(self, timeout: float = 20.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._server is not None and getattr(self._server, "started", False):
                return True
            if self._thread is not None and not self._thread.is_alive():
                return False
            time.sleep(0.05)
        return bool(self._server is not None and getattr(self._server, "started", False))

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True

    def join(self, timeout: float = 10.0) -> None:
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=timeout)


class ShutdownCoordinator:
    """Wires the server and the tray to one shutdown request.

    Registered as the app's ``shutdown_stopper`` (so the Admin's in-app
    shutdown button reaches it) and as the tray's Quit action. ``stop()`` asks
    the server to drain, then runs any post-stop callbacks (stopping the tray
    icon so ``icon.run()`` returns and the process can exit).
    """

    def __init__(self) -> None:
        self._handle: ServerHandle | None = None
        self._after_stop: list[Callable[[], None]] = []

    def register_handle(self, handle: ServerHandle) -> None:
        self._handle = handle

    def add_after_stop(self, fn: Callable[[], None]) -> None:
        self._after_stop.append(fn)

    def stop(self) -> None:
        if self._handle is not None:
            self._handle.stop()
        for fn in list(self._after_stop):
            try:
                fn()
            except Exception:
                _LOGGER.exception("post-shutdown callback failed")


# ---------------------------------------------------------------------------
# User-visible actions (browser + tray)
# ---------------------------------------------------------------------------


def open_browser(url: str) -> None:
    """Open the default browser; failures are logged, never fatal."""
    try:
        webbrowser.open(url)
    except Exception:
        _LOGGER.exception("Could not open the browser")


def _run_tray(url: str, coordinator: ShutdownCoordinator) -> None:
    import pystray  # type: ignore[import-untyped]
    from PIL import Image
    from pystray import Menu, MenuItem

    icon = pystray.Icon(
        "school-finance",
        Image.open(_resource_path("icon.png")),
        APP_NAME,
        menu=Menu(
            MenuItem(
                "Open app",
                lambda icon_, item: open_browser(url),
                default=True,
            ),
            MenuItem("Quit", lambda icon_, item: coordinator.stop()),
        ),
    )
    coordinator.add_after_stop(icon.stop)
    icon.run()


def _show_fatal_error(message: str | None = None) -> None:
    """Surface a startup failure.

    The packaged exe is a hidden window, so a fatal error must pop a message
    box or the user sees nothing. When run from source there is a console to
    read instead, and popping a modal dialog would block a terminal session.
    """
    if not is_frozen():
        return
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            None,
            message
            or (
                "School Finance could not start.\n"
                "See launcher.log in the data folder next to the app for details."
            ),
            APP_NAME,
            0x10,  # MB_ICONERROR
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None) -> Namespace:
    parser = ArgumentParser(prog=APP_NAME)
    parser.add_argument(
        "--port", type=int, default=None, help=f"HTTP port (default {DEFAULT_PORT})"
    )
    parser.add_argument(
        "--ctrl-port",
        type=int,
        default=None,
        help=f"single-instance control port (default {DEFAULT_CTRL_PORT})",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="writable data folder (default: a 'data' folder next to the app)",
    )
    parser.add_argument("--no-tray", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Launch the app: env/data wiring, server, browser, tray, single instance."""
    args = _parse_args(argv)
    data = args.data_dir or app_data_dir()
    os.environ.setdefault("SCHOOL_FINANCE_DATA", str(data))
    data.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    handler = logging.FileHandler(data / "launcher.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(handler)

    port = args.port or int(os.environ.get("SCHOOL_FINANCE_PORT", str(DEFAULT_PORT)))
    ctrl_port = args.ctrl_port or int(
        os.environ.get("SCHOOL_FINANCE_CTRL_PORT", str(DEFAULT_CTRL_PORT))
    )

    try:
        from app.main import create_app  # deferred: config must see the env above

        # The browser URL is only known after the port is resolved below; the
        # activation callback reads it from this holder at call time.
        state: dict[str, str] = {"url": ""}
        guard = InstanceGuard(
            ctrl_port, on_activate=lambda: open_browser(state["url"])
        )
        if not guard.acquire():
            if notify_running_instance(ctrl_port):
                _LOGGER.info("Another instance is running; asking it to open the browser.")
                return 0
            # The control port is taken by something that is not our app. Do
            # not silently open a dead browser tab — surface the conflict.
            _LOGGER.error(
                "Control port %d is held by another program; not starting.", ctrl_port
            )
            _show_fatal_error(
                "Another program is using the app's control port "
                f"({ctrl_port}).\nClose that program and try again."
            )
            return 1

        bound_port = resolve_port(port)
        state["url"] = instance_url(bound_port)

        coordinator = ShutdownCoordinator()
        handle = ServerHandle(bound_port, app=create_app(shutdown_stopper=coordinator.stop))
        coordinator.register_handle(handle)
        handle.start()
        if not handle.wait_until_serving():
            raise RuntimeError("The server did not start within the timeout.")
        _LOGGER.info("Serving %s (data folder: %s)", state["url"], data)
        open_browser(state["url"])

        if args.no_tray:
            stopped = threading.Event()
            coordinator.add_after_stop(stopped.set)
            stopped.wait()
        else:
            _run_tray(state["url"], coordinator)

        if handle.is_running():
            handle.join()
            if handle.is_running():
                _LOGGER.warning("Server did not stop within the drain timeout.")
        guard.close()
        return 0
    except Exception:
        _LOGGER.exception("Startup failed")
        _show_fatal_error()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
