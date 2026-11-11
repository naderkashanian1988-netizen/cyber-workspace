"""TEST I (remote control) — end-to-end over real TLS with the websockets
library, standing in for the Android client: pairing → auth → subscribe →
events → approved command. Security negatives included."""
import asyncio
import json
import time

import pytest
import websockets

from cyber_workspace.core.engine import TaskEngine
from cyber_workspace.core.events import EventBus
from cyber_workspace.remote.auth import new_pairing_code
from cyber_workspace.remote.certgen import generate_keypair
from cyber_workspace.remote.pairing import PairingManager
from cyber_workspace.remote.server import RemoteServer

PORT = 48771


def _free_port() -> int:
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture()
def server(tmp_path):
    port = _free_port()
    data = tmp_path / "cw"
    data.mkdir()
    eng = TaskEngine(data, settings={"unresponsive_timeout_s": 1.0,
                                     "unknown_grace_s": 0.5,
                                     "net_probe_target": ("127.0.0.1", 9),
                                     "max_tasks": 12},
                     power=None)
    cert = tmp_path / "c.pem"
    key = tmp_path / "k.pem"
    fp = generate_keypair(cert, key)
    pairing = PairingManager(eng.device_repo, eng.audit_repo)
    srv = RemoteServer(eng, eng.bus, "127.0.0.1", port, cert, key, fp, pairing)
    srv.start()
    time.sleep(0.6)  # let the loop bind
    yield eng, srv, fp, pairing, port
    srv.stop()
    eng.db.close()


def _ctx():
    import ssl
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def test_i_full_pairing_subscribe_command(server):
    eng, srv, fp, pairing, port = server
    code = pairing.new_code()

    async def flow():
        uri = f"wss://127.0.0.1:{port}"
        async with websockets.connect(uri, ssl=_ctx(), max_size=1 << 20) as ws:
            welcome = json.loads(await ws.recv())
            assert welcome["op"] == "welcome"
            assert welcome["payload"]["fingerprint"] == fp
            assert welcome["payload"]["protocol_version"] == 1
            # reject commands before auth
            await ws.send(json.dumps({"v": 1, "op": "command", "seq": 1, "ts": "",
                                      "payload": {"action": "pause", "task_id": "x"}}))
            err = json.loads(await ws.recv())
            assert err["op"] == "error" and err["payload"]["code"] == "NOT_AUTHENTICATED"
            # pair
            await ws.send(json.dumps({"v": 1, "op": "pairing", "seq": 2, "ts": "",
                                      "payload": {"device_name": "Pixel 9",
                                                  "code": code}}))
            ok = json.loads(await ws.recv())
            assert ok["op"] == "pairing_ok", ok
            device_id, token = ok["payload"]["device_id"], ok["payload"]["token"]
            creds = {"device_id": device_id, "token": token}
            # auth
            await ws.send(json.dumps({"v": 1, "op": "auth", "seq": 3, "ts": "",
                                      "payload": creds}))
            auth = json.loads(await ws.recv())
            assert auth["op"] == "auth_ok", auth
            assert "control" in auth["payload"]["permissions"]
            # subscribe
            await ws.send(json.dumps({"v": 1, "op": "subscribe", "seq": 4, "ts": "",
                                      "payload": {"topics": ["state", "metrics",
                                                             "notifications"]}}))
            snap = json.loads(await ws.recv())
            assert snap["op"] == "state_snapshot"
            assert snap["payload"]["tasks"] == []
            return creds, ws

    creds, _ws = asyncio.run(flow())

    # second connection with same device id must CONFLICT
    async def conflict():
        uri = f"wss://127.0.0.1:{port}"
        async with websockets.connect(uri, ssl=_ctx(), max_size=1 << 20) as ws:
            await ws.recv()  # welcome
            await ws.send(json.dumps({"v": 1, "op": "auth", "seq": 1, "ts": "",
                                      "payload": creds}))
            reply = json.loads(await ws.recv())
            assert reply["op"] == "auth_ok"
            ws2 = await websockets.connect(uri, ssl=_ctx(), max_size=1 << 20)
            await ws2.recv()
            await ws2.send(json.dumps({"v": 1, "op": "auth", "seq": 1, "ts": "",
                                       "payload": creds}))
            err = json.loads(await ws2.recv())
            assert err["op"] == "error" and err["payload"]["code"] == "CONFLICT"
            await ws2.close()
            return True

    assert asyncio.run(conflict())


def test_i_invalid_token_rejected(server):
    eng, srv, fp, pairing, port = server
    pairing.new_code()

    async def flow():
        uri = f"wss://127.0.0.1:{port}"
        async with websockets.connect(uri, ssl=_ctx(), max_size=1 << 20) as ws:
            await ws.recv()  # welcome
            await ws.send(json.dumps({"v": 1, "op": "pairing", "seq": 1, "ts": "",
                                      "payload": {"device_name": "Pixel",
                                                  "code": "000000"}}))
            # '000000' almost never matches the real code; accept either explicit
            # error or (if astronomically unlucky) skip
            reply = json.loads(await ws.recv())
            if reply["op"] == "error":
                assert reply["payload"]["code"] == "UNPAIRED"
            # bogus auth
            await ws.send(json.dumps({"v": 1, "op": "auth", "seq": 2, "ts": "",
                                      "payload": {"device_id": "nope",
                                                  "token": "nope"}}))
            reply = json.loads(await ws.recv())
            assert reply["op"] == "auth_failed"
            assert reply["payload"]["reason"] in ("UNKNOWN_DEVICE", "INVALID_TOKEN")

    asyncio.run(flow())


def test_i_remote_command_flows_through_engine(server):
    """Subscribe and verify a remote pause command reaches the engine command
    queue and produces an ack + audit entry."""
    eng, srv, fp, pairing, port = server
    code = pairing.new_code()
    t = eng.add_task("remote target", "script",
                     {"script_path": str(__import__("pathlib").Path(__file__).parent / "fake_task_scripts.py"),
                      "args": ["long"]})
    eng.tick()
    assert t.state == "RUNNING"

    async def flow():
        uri = f"wss://127.0.0.1:{port}"
        async with websockets.connect(uri, ssl=_ctx(), max_size=1 << 20) as ws:
            await ws.recv()
            await ws.send(json.dumps({"v": 1, "op": "pairing", "seq": 1, "ts": "",
                                      "payload": {"device_name": "Pixel",
                                                  "code": code}}))
            ok = json.loads(await ws.recv())
            creds = {"device_id": ok["payload"]["device_id"],
                     "token": ok["payload"]["token"]}
            await ws.send(json.dumps({"v": 1, "op": "auth", "seq": 2, "ts": "",
                                      "payload": creds}))
            assert json.loads(await ws.recv())["op"] == "auth_ok"
            await ws.send(json.dumps({"v": 1, "op": "subscribe", "seq": 3, "ts": "",
                                      "payload": {"topics": ["state"]}}))
            snap = json.loads(await ws.recv())
            assert any(task["id"] == t.cfg.id for task in snap["payload"]["tasks"])
            await ws.send(json.dumps({"v": 1, "op": "command", "seq": 4, "ts": "",
                                      "payload": {"command_id": "c-1",
                                                  "action": "pause",
                                                  "task_id": t.cfg.id}}))
            ack = json.loads(await ws.recv())
            assert ack["op"] == "command_ack" and ack["payload"]["ok"] is True
            # engine executes it on next tick
            eng.tick()
            assert t.state == "PAUSED"
            # audit trail
            rows = eng.db.query("SELECT * FROM audit_log WHERE action='pause'")
            assert rows and "remote:" in rows[-1]["actor"]

    asyncio.run(flow())
    eng.close_task(t.cfg.id)
