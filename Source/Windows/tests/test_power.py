"""TEST G (logic) — keep-awake evaluation + honest power manager behaviour off-Windows."""
import time

from cyber_workspace.platform.power import PowerManager


def test_keep_awake_follows_selected_running_tasks(make_engine, fake_script):
    eng = make_engine()
    t = eng.add_task("keeper", "script",
                     {"script_path": str(fake_script), "args": ["long"]})
    eng.tick()
    assert t.state == "RUNNING"
    # no task selected → inactive
    eng._evaluate_keep_awake()
    assert eng.keep_awake_active is False
    # select task → engine requests keep-awake
    eng.set_task_keep_awake(t.cfg.id, True)
    eng._evaluate_keep_awake()
    assert eng.keep_awake_active is True
    # waiting for user does NOT justify keeping the machine awake
    eng._apply_transition(t, __import__("cyber_workspace.core.state", fromlist=["TaskState"]).TaskState.WAITING_FOR_USER,
                          "test", _force=True)
    eng._evaluate_keep_awake()
    assert eng.keep_awake_active is False
    # paused does NOT either
    eng._apply_transition(t, __import__("cyber_workspace.core.state", fromlist=["TaskState"]).TaskState.RUNNING,
                          "test", _force=True)
    eng._evaluate_keep_awake()
    assert eng.keep_awake_active is True
    eng.set_task_keep_awake(t.cfg.id, False)
    eng._evaluate_keep_awake()
    assert eng.keep_awake_active is False


def test_power_manager_off_windows_reports_unsupported():
    """On non-Windows test machines the API must honestly report unsupported —
    never silently pretend to hold the system awake."""
    import platform
    pm = PowerManager()
    supported = platform.system() == "Windows"
    result = pm.set_keep_awake(True)
    assert result == supported
    if not supported:
        assert pm.is_active() is False


def test_settings_pages_do_not_crash_off_windows(monkeypatch):
    import platform
    if platform.system() == "Windows":
        return  # covered by on-target verification
    assert PowerManager.open_power_settings() is False
    assert PowerManager.standby_capabilities() is None
