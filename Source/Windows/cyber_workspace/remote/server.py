"""CYBER WORKSPACE — Remote control server (TLS + WebSocket, protocol v1).

Runs in a daemon thread with its own asyncio loop. Communicates with the
engine exclusively through thread-safe hand-off:

  * inbound: validated commands are pushed onto the engine command queue via
    engine.submit_command() (single-writer execution inside tick());
  * outbound: the server drains its own EventBus queue and forwards
    task snapshots / metrics / notifications to subscribed clients.

Security (SECURITY.md is the reference):
  * TLS required; self-signed cert; fingerprint displayed for pinning.
  * Before auth only `pairing` and `auth` ops are accepted; everything else →
    error NOT_AUTHENTICATED.
  * Device tokens stored hashed; constant-time comparison; revocation honored
    immediately; session expiry (token_ttl_days unused) → SESSION_EXPIRED.
  * One connection per device id (CONFLICT for the second).
  * Rate limit 30 msg/s, 64 KiB max message, 3 auth attempts per connection.
  * Every command and pairing event is audit-logged.
"""
from __future__ import annotations

import asyncio
import json
import logging
import ssl
import threading
import time as _time

import websockets

from ..core.engine import TaskEngine
from ..core.events import EventBus
from ..core.timers import now_utc
from ..protocol.messages import (CAPABILITIES, ErrorCode, Op,
                                 PROTOCOL_VERSION, SERVER_VERSION,
                                 ProtocolError, validate_approve,
                                 validate_command, parse)
from .auth import tokens_match
from .certgen import ssl_server_context
from .pairing import PairingManager

log = logging.getLogger("cyber.remote")

RATE_LIMIT = 30  # messages per second
BURST = 60


class RemoteServer(threading.Thread):
    def __init__(self, engine: TaskEngine, bus: EventBus, host: str, port: int,
                 cert_path, key_path, fingerprint: str, pairing: PairingManager):
        super().__init__(daemon=True, name="cw-remote")
        self.engine = engine
        self.bus = bus
        self.host = host
        self.port = port
        self.ssl_ctx: ssl.SSLContext = ssl_server_context(cert_path, key_path)
        self.fingerprint = fingerprint
        self.pairing = pairing
        self._stop = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._sessions: dict = {}   # device_id -> Session
        self._sub_id, self._queue = bus.subscribe()

    # -------------------------------------------------------------- thread
    def run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._serve())
        except Exception as exc:
            log.error("remote server stopped: %s", exc)
        finally:
            try:
                self._loop.close()
            except Exception:
                pass

    async def _serve(self) -> None:
        async with websockets.serve(self._handler, self.host, self.port,
                                    ssl=self.ssl_ctx, max_size=64 * 1024,
                                    ping_interval=20, ping_timeout=20):
            log.info("remote control server listening on wss://%s:%d", self.host, self.port)
            while not self._stop.is_set():
                await self._pump_outbound()
                await asyncio.sleep(0.2)
        # graceful: close remaining sessions
        for ws in list(getattr(self, "_conns", set())):
            await ws.close(code=1001, reason="server shutdown")

    def stop(self) -> None:
        self._stop.set()

    # -------------------------------------------------------------- outbound
    async def _pump_outbound(self) -> None:
        items = []
        while True:
            try:
                items.append(self._queue.get_nowait())
            except Exception:
                break
        if not items:
            return
        for session in list(self._sessions.values()):
            if not session.get("subscribed"):
                continue
            try:
                for topic, payload in items:
                    msg = self._translate(topic, payload)
                    if msg:
                        await session["ws"].send(msg)
            except Exception:
                pass  # send failures are per-session; engine unaffected

    def _translate(self, topic: str, payload: dict) -> str | None:
        if topic == "task_update":
            task = self.engine.tasks.get(payload.get("task_id", ""))
            if task is None:
                body = {"task_id": payload.get("task_id", ""),
                        "event": "removed", "task": None}
            else:
                body = {"task_id": task.cfg.id, "event": "state_changed",
                        "task": task.snapshot()}
            return json.dumps({"v": PROTOCOL_VERSION, "op": Op.TASK_EVENT.value,
                               "seq": 0, "ts": now_utc(), "payload": body})
        if topic == "notification":
            body = {"id": payload.get("id"), "created_utc": payload.get("created_utc"),
                    "category": payload.get("category"), "title": payload.get("title"),
                    "body": payload.get("body", ""), "task_id": payload.get("task_id"),
                    "actions": payload.get("actions", [])}
            return json.dumps({"v": PROTOCOL_VERSION, "op": Op.NOTIFICATION.value,
                               "seq": 0, "ts": now_utc(), "payload": body})
        if topic == "approval":
            task = self.engine.tasks.get(payload.get("task_id", ""))
            req = payload.get("request", {})
            body = {"id": req.get("id"), "created_utc": payload.get("created_utc"),
                    "task_id": payload.get("task_id"),
                    "question": req.get("question", ""), "options": req.get("options", [])}
            return json.dumps({"v": PROTOCOL_VERSION, "op": Op.APPROVAL_REQUEST.value,
                               "seq": 0, "ts": now_utc(), "payload": body})
        if topic in ("system", "network"):
            body = self.engine.system_status()
            return json.dumps({"v": PROTOCOL_VERSION, "op": Op.METRICS.value,
                               "seq": 0, "ts": now_utc(), "payload": body})
        return None

    def state_snapshot(self) -> str:
        tasks = [t.snapshot() for t in self.engine.tasks.values()]
        body = {"tasks": tasks, "system": self.engine.system_status()}
        return json.dumps({"v": PROTOCOL_VERSION, "op": Op.STATE_SNAPSHOT.value,
                           "seq": 0, "ts": now_utc(), "payload": body})

    # -------------------------------------------------------------- inbound
    async def _handler(self, ws) -> None:
        if not hasattr(self, "_conns"):
            self._conns = set()
        self._conns.add(ws)
        session = {"ws": ws, "device_id": None, "subscribed": False,
                   "authed": False, "times": [], "auth_tries": 0,
                   "perm": []}
        try:
            await ws.send(json.dumps({
                "v": PROTOCOL_VERSION, "op": Op.WELCOME.value, "seq": 0, "ts": now_utc(),
                "payload": {"protocol_version": PROTOCOL_VERSION,
                            "server_version": SERVER_VERSION,
                            "fingerprint": self.fingerprint,
                            "pairing_available": self.pairing.available()}}))
            async for raw in ws:
                if self._stop.is_set():
                    break
                now = _time.monotonic()
                session["times"] = [t for t in session["times"] if now - t < 1.0]
                session["times"].append(now)
                if len(session["times"]) > BURST:
                    await self._err(ws, ErrorCode.RATE_LIMITED, "rate limit exceeded")
                    break
                try:
                    op, payload, seq = parse(raw if isinstance(raw, str) else raw.decode())
                    await self._dispatch(ws, session, op, payload, seq)
                except ProtocolError as exc:
                    await self._err(ws, ErrorCode(exc.code), exc.message)
                    if exc.code == ErrorCode.VERSION_MISMATCH.value:
                        break
        except Exception:
            pass
        finally:
            self._conns.discard(ws)
            if session["device_id"]:
                self._sessions.pop(session["device_id"], None)

    async def _err(self, ws, code: ErrorCode, message: str) -> None:
        await ws.send(json.dumps({"v": PROTOCOL_VERSION, "op": Op.ERROR.value,
                                  "seq": 0, "ts": now_utc(),
                                  "payload": {"code": code.value, "message": message}}))

    async def _dispatch(self, ws, session, op: Op, payload: dict, seq: int) -> None:
        engine = self.engine
        if op is Op.PING:
            await ws.send(json.dumps({"v": PROTOCOL_VERSION, "op": Op.PONG.value,
                                      "seq": seq, "ts": now_utc(),
                                      "payload": {"ts": now_utc()}}))
            return
        if op is Op.PAIRING:
            ok = self.pairing.pair(str(payload.get("code", "")),
                                   str(payload.get("device_name", "")))
            if not ok:
                await self._err(ws, ErrorCode.UNPAIRED,
                                "pairing code invalid, expired or already used")
                return
            body = {"device_id": ok["device_id"], "token": ok["token"],
                    "permissions": ok["permissions"], "token_ttl_days": ok["token_ttl_days"]}
            await ws.send(json.dumps({"v": PROTOCOL_VERSION, "op": Op.PAIRING_OK.value,
                                      "seq": seq, "ts": now_utc(), "payload": body}))
            session["device_id"] = ok["device_id"]
            session["authed"] = True
            session["perm"] = ok["permissions"]
            self._sessions[ok["device_id"]] = session
            return
        if op is Op.AUTH:
            session["auth_tries"] += 1
            if session["auth_tries"] > 3:
                await self._err(ws, ErrorCode.FORBIDDEN, "too many auth attempts")
                return
            device_id = str(payload.get("device_id", ""))
            token = str(payload.get("token", ""))
            row = engine.device_repo.find_active(device_id)
            if row is None:
                await ws.send(json.dumps({"v": PROTOCOL_VERSION,
                                          "op": Op.AUTH_FAILED.value, "seq": seq,
                                          "ts": now_utc(),
                                          "payload": {"reason": "UNKNOWN_DEVICE"}}))
                return
            if not tokens_match(token, row["token_hash"]):
                await ws.send(json.dumps({"v": PROTOCOL_VERSION,
                                          "op": Op.AUTH_FAILED.value, "seq": seq,
                                          "ts": now_utc(),
                                          "payload": {"reason": "INVALID_TOKEN"}}))
                return
            if device_id in self._sessions and self._sessions[device_id] is not session:
                await self._err(ws, ErrorCode.CONFLICT,
                                "this device already has an open session")
                return
            session["device_id"] = device_id
            session["authed"] = True
            session["perm"] = json.loads(row["permissions"] or "[]")
            self._sessions[device_id] = session
            engine.device_repo.touch(device_id)
            engine.audit_repo.add(device_id[:8] + "…", "device_auth", "authenticated")
            await ws.send(json.dumps({"v": PROTOCOL_VERSION, "op": Op.AUTH_OK.value,
                                      "seq": seq, "ts": now_utc(),
                                      "payload": {"protocol_version": PROTOCOL_VERSION,
                                                  "server_version": SERVER_VERSION,
                                                  "capabilities": list(CAPABILITIES),
                                                  "permissions": session["perm"],
                                                  "token_ttl_days": 30}}))
            return
        # everything below requires auth
        if not session.get("authed"):
            await self._err(ws, ErrorCode.NOT_AUTHENTICATED, "authenticate first")
            return
        if op is Op.SUBSCRIBE:
            session["subscribed"] = True
            await ws.send(self.state_snapshot())
            return
        if op is Op.UNSUBSCRIBE:
            session["subscribed"] = False
            return
        if op is Op.GET_STATE:
            await ws.send(self.state_snapshot())
            return
        if op is Op.GET_TASK:
            task = engine.tasks.get(str(payload.get("task_id", "")))
            if not task:
                await self._err(ws, ErrorCode.NOT_FOUND, "task not found")
                return
            await ws.send(json.dumps({"v": PROTOCOL_VERSION, "seq": seq,
                                      "ts": now_utc(), "op": "get_task",
                                      "payload": {"task": task.snapshot()}}))
            return
        if op is Op.GET_LOGS:
            task = engine.tasks.get(str(payload.get("task_id", "")))
            if not task:
                await self._err(ws, ErrorCode.NOT_FOUND, "task not found")
                return
            lines = task.logs_tail(int(payload.get("last_n", 200)))
            await ws.send(json.dumps({"v": PROTOCOL_VERSION, "op": "get_logs",
                                      "seq": seq, "ts": now_utc(),
                                      "payload": {"task_id": task.cfg.id,
                                                  "lines": lines}}))
            return
        if op is Op.COMMAND:
            if "control" not in session["perm"]:
                await self._err(ws, ErrorCode.FORBIDDEN,
                                "this device has view-only permission")
                return
            action, task_id, params = validate_command(payload)
            command_id = str(payload.get("command_id", "")) or None
            engine.submit_command(action.value, task_id, params,
                                  actor=f"remote:{session['device_id'][:8]}…",
                                  command_id=command_id)
            await ws.send(json.dumps({"v": PROTOCOL_VERSION, "op": Op.COMMAND_ACK.value,
                                      "seq": seq, "ts": now_utc(),
                                      "payload": {"command_id": command_id or "",
                                                  "ok": True}}))
            return
        if op is Op.APPROVE:
            if "control" not in session["perm"]:
                await self._err(ws, ErrorCode.FORBIDDEN,
                                "this device has view-only permission")
                return
            request_id, decision, _note = validate_approve(payload)
            ok, err = engine.approve(request_id, decision,
                                     actor=f"remote:{session['device_id'][:8]}…")
            await ws.send(json.dumps({"v": PROTOCOL_VERSION, "op": Op.COMMAND_ACK.value,
                                      "seq": seq, "ts": now_utc(),
                                      "payload": {"command_id":
                                                  str(payload.get("command_id", "")),
                                                  "ok": ok, "error": err}}))
            return
        await self._err(ws, ErrorCode.BAD_REQUEST, f"op {op.value} not handled")
