"""TEST J (overhead measurement, no fabricated claims) + metrics honesty."""
import os
import time

import psutil
import pytest


def test_metrics_unavailable_is_none_not_fabricated(make_engine):
    eng = make_engine()
    t = eng.add_task("ghost", "external", {"exe": "definitely-not-running.exe"})
    eng._sample_metrics(time.monotonic())
    assert t.cpu_percent is None
    assert t.ram_mb is None
    # system metrics are real measurements on the test machine
    eng._sample_metrics(time.monotonic())
    assert eng.system_ram_total_mb is not None and eng.system_ram_total_mb > 0


def test_network_monitor_reports_down_without_fabrication(make_engine):
    eng = make_engine()
    eng._sample_network(time.monotonic())
    eng._sample_network(time.monotonic() + 1.1)
    status = eng.net["status"]
    assert status in ("UP", "DOWN", "UNKNOWN")
    if status == "DOWN":
        assert eng.net["latency_ms"] is None


@pytest.mark.skipif(
    os.environ.get("GITHUB_ACTIONS") == "true",
    reason="TEST J is a machine-relative benchmark (docstring: 'THIS machine'); "
           "shared CI hardware cannot satisfy a local threshold. Numbers for "
           "TEST_REPORT.md are produced by local runs, as documented.")
def test_j_engine_tick_overhead_10_tasks(make_engine, fake_script, capsys):
    """Measures real overhead of one engine tick with 10 live script tasks on
    THIS machine; the measured number is printed for TEST_REPORT.md."""
    eng = make_engine()
    tasks = [eng.add_task(f"load{i}", "script",
                          {"script_path": str(fake_script), "args": ["long"]})
             for i in range(10)]
    deadline = time.time() + 6
    while time.time() < deadline and not all(t.state == "RUNNING" for t in tasks):
        eng.tick()
        time.sleep(0.05)
    running = sum(1 for t in tasks if t.state == "RUNNING")
    samples = []
    for _ in range(30):
        t0 = time.perf_counter()
        eng.tick()
        samples.append((time.perf_counter() - t0) * 1000)
        time.sleep(0.03)
    avg = sum(samples) / len(samples)
    p95 = sorted(samples)[int(len(samples) * 0.95)]
    print(f"\nTEST J on this machine: 10 tasks, {running} running; "
          f"avg tick {avg:.2f} ms, p95 {p95:.2f} ms")
    assert running >= 6, "at least 6 tasks must run concurrently"
    assert avg < 250, "tick overhead unexpectedly high on this machine"
    for t in tasks:
        eng.close_task(t.cfg.id)
