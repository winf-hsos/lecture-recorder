"""Remote control for OBS Studio via obs-websocket (protocol v5).

Only depends on the `websockets` package. The password comes from OBS's own
websocket configuration (or the environment variable OBS_WEBSOCKET_PASSWORD) and
is never printed. If the websocket server is switched off and OBS is not running
yet, it is switched on with a fresh random password, so nothing has to be set up
by hand. OBS listens on 127.0.0.1:4455.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import subprocess
import time
import uuid
import winreg
from pathlib import Path

from websockets.sync.client import connect

from hardware import NO_WINDOW

PORT = 4455
ADDRESS = f"ws://127.0.0.1:{PORT}"
WEBSOCKET_CONFIG = Path(os.environ["APPDATA"]) / "obs-studio" / "plugin_config" / "obs-websocket" / "config.json"


class ObsError(RuntimeError):
    pass


def obs_exe() -> Path:
    """obs64.exe from the install location the OBS installer writes to the registry."""
    candidates = []
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(hive, r"SOFTWARE\OBS Studio") as key:
                candidates.append(Path(winreg.QueryValueEx(key, "")[0]) / "bin" / "64bit" / "obs64.exe")
        except OSError:
            pass
    candidates.append(Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "obs-studio" / "bin" / "64bit" / "obs64.exe")
    for exe in candidates:
        if exe.exists():
            return exe
    raise ObsError("OBS Studio ist nicht installiert (https://obsproject.com).")


def _websocket_config() -> dict:
    try:
        return json.loads(WEBSOCKET_CONFIG.read_text(encoding="utf-8"))
    except Exception:
        return {}


def password() -> str:
    pw = _websocket_config().get("server_password") or os.environ.get("OBS_WEBSOCKET_PASSWORD")
    if not pw:
        # A user variable set after this process started is not in os.environ yet.
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                pw = winreg.QueryValueEx(key, "OBS_WEBSOCKET_PASSWORD")[0]
        except OSError:
            pw = None
    if not pw:
        raise ObsError("Kein Passwort für die OBS-Fernsteuerung gefunden.")
    return pw


def enable_websocket() -> None:
    """Switch the websocket server on in OBS's config. Only call while OBS is not running:
    OBS reads the file on start and writes it back on exit."""
    c = _websocket_config()
    wanted = {"server_enabled": True, "server_port": PORT, "auth_required": True, "first_load": False}
    if all(c.get(k) == v for k, v in wanted.items()) and c.get("server_password"):
        return
    c.update(wanted)
    c.setdefault("alerts_enabled", False)
    if not c.get("server_password"):
        c["server_password"] = secrets.token_urlsafe(18)
    WEBSOCKET_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    WEBSOCKET_CONFIG.write_text(json.dumps(c, indent=4), encoding="utf-8")


def is_running() -> bool:
    # tasklist prints in the OEM code page; compare bytes against the ASCII name only
    r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq obs64.exe", "/NH"], capture_output=True,
                       creationflags=NO_WINDOW)
    return b"obs64.exe" in r.stdout


def start(profile: str | None = None, collection: str | None = None, timeout: float = 30.0) -> None:
    """Start OBS minimized to the tray unless it is already running, then wait for the websocket."""
    running = is_running()
    if not running:
        exe = obs_exe()
        enable_websocket()
        args = [str(exe), "--minimize-to-tray", "--disable-shutdown-check"]
        if profile:
            args += ["--profile", profile]
        if collection:
            args += ["--collection", collection]
        # OBS needs its own folder as working directory, otherwise it cannot find its locale files.
        subprocess.Popen(args, cwd=str(exe.parent))
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with Obs() as o:
                o.request("GetVersion")
            return
        except Exception:
            time.sleep(1)
    if running and not _websocket_config().get("server_enabled"):
        raise ObsError("In OBS ist die Fernsteuerung (WebSocket-Server) ausgeschaltet. "
                       "Bitte OBS schließen und das Programm neu starten, dann schaltet es sie selbst ein.")
    raise ObsError("OBS antwortet nicht auf die Fernsteuerung.")


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
