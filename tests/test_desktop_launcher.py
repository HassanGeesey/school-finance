"""Tests for the desktop launcher seams (ticket 13).

The tray icon and browser are user-visible and not exercised here; everything
behind them (data-dir choice, port resolution, single-instance lock, uvicorn
lifecycle, shutdown wiring) is tested directly with real loopback sockets.
"""

from __future__ import annotations

import socket
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.desktop import launcher
from tests.helpers import authenticated_admin


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_until(predicate, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def test_app_data_dir_is_next_to_the_exe_when_frozen(monkeypatch):
    monkeypatch.setattr(launcher.sys, "frozen", True, raising=False)
    monkeypatch.setattr(launcher.sys, "executable", r"C:\SchoolFinance\SchoolFinance.exe")

    assert launcher.app_data_dir() == Path(r"C:\SchoolFinance\data")


def test_app_data_dir_points_at_the_repo_data_folder_from_source(monkeypatch):
    monkeypatch.delattr(launcher.sys, "frozen", raising=False)

    assert launcher.app_data_dir() == Path(__file__).resolve().parents[1] / "data"


def test_resource_path_uses_the_packaging_folder_from_source(monkeypatch):
    monkeypatch.delattr(launcher.sys, "_MEIPASS", raising=False)

    assert launcher._resource_path("icon.png") == (
        Path(__file__).resolve().parents[1] / "packaging" / "icon.png"
    )


# ---------------------------------------------------------------------------
# Ports
# ---------------------------------------------------------------------------


def test_resolve_port_returns_the_preferred_port_when_free():
    port = _free_port()

    assert launcher.resolve_port(port) == port


def test_resolve_port_skips_a_port_that_is_in_use():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as blocker:
        blocker.bind(("127.0.0.1", 0))
        blocker.listen(1)
        port = blocker.getsockname()[1]

        resolved = launcher.resolve_port(port)

        assert resolved != port
        assert not launcher._port_in_use(resolved)


def test_instance_url():
    assert launcher.instance_url(8000) == "http://127.0.0.1:8000"


# ---------------------------------------------------------------------------
# Single instance
# ---------------------------------------------------------------------------


def test_second_launch_signals_the_running_instance():
    ctrl = _free_port()
    activated: list[bool] = []
    first = launcher.InstanceGuard(ctrl, on_activate=lambda: activated.append(True))
    assert first.acquire() is True
    try:
        second = launcher.InstanceGuard(ctrl, on_activate=lambda: activated.append(False))
        assert second.acquire() is False
        second.close()

        assert launcher.notify_running_instance(ctrl) is True
        assert _wait_until(lambda: bool(activated)) is True
        assert activated == [True]
    finally:
        first.close()


def test_notify_fails_when_no_instance_is_listening():
    assert launcher.notify_running_instance(_free_port()) is False


def test_acquire_after_close_works_again():
    ctrl = _free_port()
    first = launcher.InstanceGuard(ctrl, on_activate=lambda: None)
    assert first.acquire() is True
    first.close()

    again = launcher.InstanceGuard(ctrl, on_activate=lambda: None)
    assert again.acquire() is True
    again.close()


# ---------------------------------------------------------------------------
# Server lifecycle
# ---------------------------------------------------------------------------


def test_server_handle_starts_serves_and_stops():
    from app.main import create_app

    app = create_app(database_url="sqlite://")
    handle = launcher.ServerHandle(_free_port(), app=app)
    handle.start()
    try:
        assert handle.wait_until_serving(timeout=15) is True
        assert handle.is_running() is True

        response = httpx.get(handle.url + "/login")
        # No admin set up yet, so /login bounces to the setup wizard; any of
        # these means the server answered rather than refusing the connection.
        assert response.status_code in (200, 302, 303)
    finally:
        handle.stop()
        handle.join(timeout=10)

    assert handle.is_running() is False


def test_shutdown_coordinator_stops_handle_then_runs_callbacks():
    stopped: list[bool] = []
    after: list[bool] = []

    class FakeHandle:
        def stop(self) -> None:
            stopped.append(True)

    coordinator = launcher.ShutdownCoordinator()
    coordinator.register_handle(FakeHandle())  # type: ignore[arg-type]
    coordinator.add_after_stop(lambda: after.append(True))

    coordinator.stop()

    assert stopped == [True]
    assert after == [True]


def test_in_app_shutdown_button_reaches_the_coordinator():
    from app.main import create_app

    stopped: list[bool] = []

    class RecordingHandle:
        def stop(self) -> None:
            stopped.append(True)

    coordinator = launcher.ShutdownCoordinator()
    coordinator.register_handle(RecordingHandle())  # type: ignore[arg-type]

    app = create_app(database_url="sqlite://", shutdown_stopper=coordinator.stop)
    with TestClient(app) as client:
        authenticated_admin(client)
        response = client.post("/system/shutdown")

    assert response.status_code == 200
    assert stopped == [True]


def test_main_exits_when_another_instance_is_running(tmp_path, monkeypatch):
    ctrl = _free_port()
    first = launcher.InstanceGuard(ctrl, on_activate=lambda: None)
    assert first.acquire() is True
    try:
        rc = launcher.main(
            [
                "--ctrl-port",
                str(ctrl),
                "--port",
                str(_free_port()),
                "--data-dir",
                str(tmp_path),
                "--no-tray",
            ]
        )
        assert rc == 0
        assert (tmp_path / "launcher.log").exists()
    finally:
        first.close()


def test_main_fails_when_the_control_port_is_held_by_another_program(tmp_path):
    # A raw socket owns the control port but does not answer pings — so the
    # launcher must report the conflict instead of silently opening a dead tab.
    ctrl = _free_port()
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.bind(("127.0.0.1", ctrl))
    try:
        rc = launcher.main(
            [
                "--ctrl-port",
                str(ctrl),
                "--port",
                str(_free_port()),
                "--data-dir",
                str(tmp_path),
                "--no-tray",
            ]
        )
        assert rc == 1
    finally:
        blocker.close()
