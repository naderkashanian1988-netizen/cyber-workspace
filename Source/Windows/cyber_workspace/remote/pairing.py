"""CYBER WORKSPACE — pairing manager (single-use 6-digit codes, 5-minute TTL)."""
from __future__ import annotations

import time as _time

from ..persistence.repos import DeviceRepo, new_id
from .auth import hash_token, new_pairing_code, new_token

CODE_TTL_S = 300


class PairingManager:
    def __init__(self, devices: DeviceRepo, audit):
        self.devices = devices
        self.audit = audit
        self._code: str | None = None
        self._expires = 0.0
        self._used = True

    def new_code(self) -> str:
        self._code = new_pairing_code()
        self._expires = _time.time() + CODE_TTL_S
        self._used = False
        self.audit.add("local", "pairing_code_issued", f"valid {CODE_TTL_S}s")
        return self._code

    def available(self) -> bool:
        return not self._used and self._code is not None and _time.time() < self._expires

    def pair(self, code: str, device_name: str) -> dict | None:
        """Validate the code; on success register the device and return the
        one-time pairing payload. The plaintext token exists exactly once —
        it is stored hashed and sent only over TLS during this reply."""
        if not self.available():
            return None
        if not self._code or code != self._code:
            return None
        self._used = True  # single use, even on failure paths below
        token = new_token()
        device_id = new_id()
        permissions = ["view", "control"]  # paired phones may control; revocable
        self.devices.add(device_id, device_name or "Android device",
                         hash_token(token), permissions)
        self.audit.add("local", "device_paired", f"{device_name} ({device_id[:8]}…)")
        return {"device_id": device_id, "token": token,
                "permissions": permissions, "token_ttl_days": 30}
