"""CYBER WORKSPACE — fake scripts used by the engine test suite.

Each script exercises one acceptance-test scenario (Test Reports/TESTING.md).
Marker protocol is documented in adapters/script.py and USER_MANUAL.md.
"""
import sys
import time

MODE = sys.argv[1] if len(sys.argv) > 1 else "loop"


def stamp(msg: str) -> None:
    print(f"@@CW:PROGRESS@@ {{\"note\": \"{msg}\"}}", flush=True)


if MODE == "done":
    stamp("finishing quickly")
    sys.exit(0)

if MODE == "fail":
    time.sleep(0.2)
    print("fatal: simulated failure", file=sys.stderr, flush=True)
    sys.exit(3)

if MODE == "approval":
    stamp("requesting approval")
    print('@@CW:APPROVAL@@ {"question": "Proceed with cleanup?", "options": ["Yes","No"]}',
          flush=True)
    line = sys.stdin.readline()  # "approve <id>" / "deny <id>"
    first = (line or "").strip().split(" ")[0]
    stamp(f"decision received: {first}")
    time.sleep(0.3)
    sys.exit(0 if first == "approve" else 4)

if MODE == "netwait":
    stamp("network phase")
    print('@@CW:NETWAIT@@ {"reason": "upload endpoint unreachable"}', flush=True)
    time.sleep(0.8)
    print("@@CW:NETOK@@", flush=True)
    stamp("upload finished")
    sys.exit(0)

if MODE == "heartbeat":
    # automation-style: heartbeats for ~1s, then stalls (TEST E / unresponsive)
    stamp("automation starting")
    for _ in range(4):
        print("@@CW:HEARTBEAT@@", flush=True)
        time.sleep(0.25)
    stamp("automation stalled")
    time.sleep(30)

if MODE == "long":
    # long-running productive work (TEST A concurrency)
    for i in range(600):
        stamp(f"working step {i}")
        time.sleep(0.2)
    sys.exit(0)

stamp("unknown mode; exiting")
sys.exit(1)
