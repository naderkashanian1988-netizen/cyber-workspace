#!/usr/bin/env python3
"""CYBER WORKSPACE — remote protocol test client (stand-in for the Android app).

Used by Test Reports/TESTING.md TEST I and by humans to verify the host server end-to-end
before installing the APK. Implements the same protocol v1 flow:

  pair  → auth → subscribe → print events → optional commands

Examples:
  python Source/Shared/tools/remote_test_client.py pair --host 192.168.1.10 --port 47770 --code 482913
  python Source/Shared/tools/remote_test_client.py watch --host 192.168.1.10 --port 47770 \
      --device-id ... --token ... --seconds 10
  python Source/Shared/tools/remote_test_client.py command --host ... --device-id ... --token ... \
      pause TASK_ID
"""
from __future__ import annotations

import argparse
import json
import ssl
import sys
import time
import uuid

import websockets

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

from cyber_workspace.protocol.messages import PROTOCOL_VERSION  # noqa: E402


def client_ssl() -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE  # fingerprint pinning happens on device
    return ctx


def envelope(op: str, payload: dict, seq: int) -> str:
    return json.dumps({"v": PROTOCOL_VERSION, "op": op, "seq": seq, "ts": "",
                       "payload": payload})


async def run(args) -> int:
    uri = f"wss://{args.host}:{args.port}"
    async with websockets.connect(uri, ssl=client_ssl(),
                                  max_size=1 << 20) as ws:
        welcome = json.loads(await ws.recv())
        assert welcome["op"] == "welcome", welcome
        print("welcome:", json.dumps(welcome["payload"], indent=2)[:400])
        seq = 0
        if args.cmd == "pair":
            seq += 1
            await ws.send(envelope("pairing",
                                   {"device_name": args.device_name, "code": args.code},
                                   seq))
            reply = json.loads(await ws.recv())
            print(reply["op"], json.dumps(reply["payload"], indent=2))
            if reply["op"] == "pairing_ok":
                print("SAVE THESE CREDENTIALS:")
                print(json.dumps({"device_id": reply["payload"]["device_id"],
                                  "token": reply["payload"]["token"]}))
            return 0
        seq += 1
        await ws.send(envelope("auth",
                               {"device_id": args.device_id, "token": args.token,
                                "device_name": "test-client"}, seq))
        reply = json.loads(await ws.recv())
        print("auth:", reply["op"], reply.get("payload", {}).get("reason", ""))
        if reply["op"] != "auth_ok":
            return 2
        seq += 1
        await ws.send(envelope("subscribe",
                               {"topics": ["state", "metrics", "notifications"]}, seq))
        if args.cmd == "command":
            seq += 1
            await ws.send(envelope("command",
                                   {"command_id": str(uuid.uuid4()),
                                    "action": args.action,
                                    "task_id": args.task_id,
                                    "params": {}}, seq))
        deadline = time.time() + args.seconds
        while time.time() < deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=max(0.2, deadline - time.time()))
            except (asyncio.TimeoutError, TimeoutError):
                break
            msg = json.loads(raw)
            op = msg.get("op")
            payload = msg.get("payload", {})
            if op == "metrics":
                continue  # too chatty for the console
            print(f"[{op}]", json.dumps(payload, ensure_ascii=False)[:300])
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="CYBER WORKSPACE remote test client")
    p.add_argument("cmd", choices=["pair", "watch", "command"])
    p.add_argument("--host", required=True)
    p.add_argument("--port", type=int, required=True)
    p.add_argument("--code", help="pairing code (pair mode)")
    p.add_argument("--device-name", default="test-client")
    p.add_argument("--device-id")
    p.add_argument("--token")
    p.add_argument("--seconds", type=float, default=10)
    p.add_argument("action", nargs="?", help="pause|resume|restart|close|set_keep_awake")
    p.add_argument("task_id", nargs="?")
    args = p.parse_args()
    import asyncio
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
