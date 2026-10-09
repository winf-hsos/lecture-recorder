"""Remote control for OBS Studio via obs-websocket (protocol v5).

Only depends on the `websockets` package. The password is read from the
environment variable OBS_WEBSOCKET_PASSWORD and is never printed. OBS listens
on 127.0.0.1:4455.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import time
import uuid
from pathlib import Path

from websockets.sync.client import connect

OBS_EXE = Path(r"C:\Program Files\obs-studio\bin\64bit\obs64.exe")
ADDRESS = "ws://127.0.0.1:4455"


class ObsError(RuntimeError):
    pass


def password() -> str:
    pw = os.environ.get("OBS_WEBSOCKET_PASSWORD")
    if not pw:
        # A user variable set after this process started is not in os.environ yet.
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                pw = winreg.QueryValueEx(key, "OBS_WEBSOCKET_PASSWORD")[0]
        except OSError:
            pw = None
    if not pw:
        raise ObsError("OBS_WEBSOCKET_PASSWORD is not set")
    return pw


def is_running() -> bool:
    # tasklist prints in the OEM code page; compare bytes against the ASCII name only
    r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq obs64.exe", "/NH"], capture_output=True)
    return b"obs64.exe" in r.stdout


def start(profile: str | None = None, collection: str | None = None, timeout: float = 30.0) -> None:
    """Start OBS minimized to the tray unless it is already running, then wait for the websocket."""
    if not is_running():
        args = [str(OBS_EXE), "--minimize-to-tray", "--disable-shutdown-check"]
        if profile:
            args += ["--profile", profile]
        if collection:
            args += ["--collection", collection]
        # OBS needs its own folder as working directory, otherwise it cannot find its locale files.
        subprocess.Popen(args, cwd=str(OBS_EXE.parent))
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with Obs() as o:
                o.request("GetVersion")
            return
        except Exception:
            time.sleep(1)
    raise ObsError("OBS does not answer on the websocket")


class Obs:
    VOLUME_METERS = 1 << 16   # InputVolumeMeters event, about 20 per second

    def __init__(self, address: str = ADDRESS, events: int = 0):
        self.address = address
        self.events = events
        self.ws = None

    def __enter__(self) -> "Obs":
        self.ws = connect(self.address, open_timeout=5)
        hello = json.loads(self.ws.recv())
        auth = hello["d"].get("authentication")
        identify = {"rpcVersion": 1, "eventSubscriptions": self.events}
        if auth:
            secret = base64.b64encode(hashlib.sha256((password() + auth["salt"]).encode()).digest()).decode()
            identify["authentication"] = base64.b64encode(
                hashlib.sha256((secret + auth["challenge"]).encode()).digest()).decode()
        self.ws.send(json.dumps({"op": 1, "d": identify}))
        if json.loads(self.ws.recv()).get("op") != 2:
            raise ObsError("OBS rejected the authentication")
        return self

    def __exit__(self, *exc) -> None:
        if self.ws:
            self.ws.close()

    def event(self, timeout: float = 5.0) -> dict | None:
        """Next event (op 5) as {eventType, eventData}, or None."""
        try:
            m = json.loads(self.ws.recv(timeout=timeout))
        except TimeoutError:
            return None
        return m["d"] if m.get("op") == 5 else None

    def request(self, kind: str, data: dict | None = None, check: bool = True) -> dict:
        rid = str(uuid.uuid4())
        self.ws.send(json.dumps({"op": 6, "d": {"requestType": kind, "requestId": rid, "requestData": data or {}}}))
        while True:
            m = json.loads(self.ws.recv(timeout=30))
            if m.get("op") == 7 and m["d"]["requestId"] == rid:
                status = m["d"]["requestStatus"]
                if check and not status["result"]:
                    raise ObsError(f"{kind}: {status.get('code')} {status.get('comment', '')}")
                return m["d"].get("responseData", {}) or {}
