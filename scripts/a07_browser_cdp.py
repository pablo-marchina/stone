"""A07.3 — stdlib-only, loopback Chrome DevTools driver for local synthetic HTML.

The browser runs in a disposable profile. It receives trusted fixture + existing
exporter via document.write into about:blank; NO HTTP server, file navigation,
external URLs, client credential, package download or global browser profile.

CDP is bound to the loopback address. The driver polls REAL wall-clock status;
Chrome --dump-dom/--virtual-time-budget is not an async Canvas completion oracle.
This does not authorize creative generation, Studio writes or publication.
"""
from __future__ import annotations

import base64
from hashlib import sha1
import json
import os
from pathlib import Path
import secrets
import socket
import struct
import subprocess
import tempfile
import time


class BrowserDiagnostic(RuntimeError):
    """Fixed, non-sensitive local browser driver failure."""


def compose_fixture(fixture: Path, exporter: Path) -> str:
    html = fixture.read_text(encoding="utf-8")
    js = exporter.read_text(encoding="utf-8")
    expected = '<script src="../../src/tapi_gate0/web/studio_export_e4.js"></script>'
    if (html.count(expected) != 1 or "</script" in js.lower()
            or html.lower().count("<script") != 2
            or html.lower().count("</script>") != 2
            or "http://" in html.lower() or "https://" in html.lower()):
        raise BrowserDiagnostic("A073_LOCAL_FIXTURE_NOT_ISOLATED")
    return html.replace(expected, "<script>" + js + "</script>")


def _recv_exact(sock: socket.socket, count: int, buffered: bytearray) -> bytes:
    while len(buffered) < count:
        part = sock.recv(min(65536, count - len(buffered)))
        if not part:
            raise BrowserDiagnostic("A073_CDP_SOCKET_CLOSED")
        buffered.extend(part)
    result = bytes(buffered[:count])
    del buffered[:count]
    return result


class LocalCDP:
    """Minimal masked RFC 6455 client for Chrome's local DevTools socket."""

    def __init__(self, port: int, path: str):
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=5)
        self.sock.settimeout(6)
        self.buffer = bytearray()
        self.next_id = 0
        key = base64.b64encode(secrets.token_bytes(16)).decode("ascii")
        request = (
            f"GET {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
            "Upgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Version: 13\r\nSec-WebSocket-Key: {key}\r\n\r\n"
        )
        self.sock.sendall(request.encode("ascii"))
        response = bytearray()
        while b"\r\n\r\n" not in response and len(response) < 8192:
            part = self.sock.recv(4096)
            if not part:
                raise BrowserDiagnostic("A073_CDP_HANDSHAKE_FAILED")
            response.extend(part)
        header, _, remainder = bytes(response).partition(b"\r\n\r\n")
        expected = base64.b64encode(sha1(
            (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")
        ).digest()).decode("ascii")
        if (not header.startswith(b"HTTP/1.1 101")
                or f"Sec-WebSocket-Accept: {expected}".lower().encode("ascii")
                not in header.lower()):
            raise BrowserDiagnostic("A073_CDP_HANDSHAKE_FAILED")
        self.buffer.extend(remainder)

    def close(self):
        self.sock.close()

    def _send_frame(self, opcode: int, data: bytes):
        if len(data) > 4_000_000:
            raise BrowserDiagnostic("A073_CDP_FRAME_TOO_LARGE")
        mask = secrets.token_bytes(4)
        first = bytes([0x80 | opcode])
        if len(data) < 126:
            prefix = bytes([0x80 | len(data)])
        elif len(data) < 65536:
            prefix = b"\xfe" + struct.pack("!H", len(data))
        else:
            prefix = b"\xff" + struct.pack("!Q", len(data))
        encoded = bytes(value ^ mask[index % 4] for index, value in enumerate(data))
        self.sock.sendall(first + prefix + mask + encoded)

    def _read_json(self) -> dict:
        while True:
            initial = _recv_exact(self.sock, 2, self.buffer)
            opcode = initial[0] & 0x0F
            length = initial[1] & 0x7F
            if length == 126:
                length = struct.unpack("!H", _recv_exact(self.sock, 2, self.buffer))[0]
            elif length == 127:
                length = struct.unpack("!Q", _recv_exact(self.sock, 8, self.buffer))[0]
            if length > 4_000_000 or initial[1] & 0x80:
                raise BrowserDiagnostic("A073_CDP_UNEXPECTED_FRAME")
            payload = _recv_exact(self.sock, length, self.buffer)
            if opcode == 9:
                self._send_frame(10, payload)
                continue
            if opcode != 1:
                raise BrowserDiagnostic("A073_CDP_UNEXPECTED_FRAME")
            return json.loads(payload)

    def call(self, method: str, params: dict | None = None, session: str | None = None):
        self.next_id += 1
        message = {"id": self.next_id, "method": method, "params": params or {}}
        if session is not None:
            message["sessionId"] = session
        self._send_frame(1, json.dumps(message, ensure_ascii=False).encode("utf-8"))
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            response = self._read_json()
            if response.get("id") == self.next_id:
                if "error" in response:
                    raise BrowserDiagnostic("A073_CDP_COMMAND_FAILED")
                return response.get("result") or {}
        raise BrowserDiagnostic("A073_CDP_COMMAND_TIMEOUT")


def _port_from_profile(profile: Path, process: subprocess.Popen) -> tuple[int, str]:
    deadline = time.monotonic() + 10
    port_file = profile / "DevToolsActivePort"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise BrowserDiagnostic("A073_BROWSER_PROCESS_EXITED")
        if port_file.is_file():
            parts = port_file.read_text(encoding="ascii").splitlines()
            if (len(parts) >= 2 and parts[0].isdigit()
                    and parts[1].startswith("/devtools/browser/")):
                return int(parts[0]), parts[1]
        time.sleep(0.1)
    raise BrowserDiagnostic("A073_CDP_PORT_NOT_READY")


def run_browser_cdp(browser: Path, fixture: Path, exporter: Path,
                    *, timeout_seconds: float = 25) -> str:
    """Return actual final DOM output element or the latest incomplete state.

    A test runner MUST parse and fail closed on anything other than exact 7/7.
    """
    payload = compose_fixture(fixture, exporter)
    with tempfile.TemporaryDirectory(prefix="stone-a073-cdp-") as directory:
        profile = Path(directory)
        command = [
            str(browser), "--headless=new", "--no-first-run",
            "--no-default-browser-check", "--disable-extensions",
            "--disable-background-networking", "--disable-component-update",
            "--disable-sync", "--disable-features=MediaRouter",
            "--host-resolver-rules=MAP * 0.0.0.0, EXCLUDE localhost",
            "--remote-debugging-address=127.0.0.1",
            "--remote-debugging-port=0", f"--user-data-dir={profile}",
            "about:blank",
        ]
        if getattr(os, "geteuid", lambda: -1)() == 0:
            command.insert(1, "--no-sandbox")
        process = subprocess.Popen(
            command, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        connection = None
        try:
            port, path = _port_from_profile(profile, process)
            connection = LocalCDP(port, path)
            target = connection.call(
                "Target.createTarget", {"url": "about:blank"}
            )["targetId"]
            session = connection.call(
                "Target.attachToTarget", {"targetId": target, "flatten": True}
            )["sessionId"]
            connection.call("Page.enable", session=session)
            expression = (
                "document.open();document.write("
                + json.dumps(payload, ensure_ascii=False)
                + ");document.close();"
            )
            result = connection.call(
                "Runtime.evaluate", {
                    "expression": expression, "returnByValue": True,
                }, session=session,
            )
            if "exceptionDetails" in result:
                raise BrowserDiagnostic("A073_LOCAL_FIXTURE_JAVASCRIPT_ERROR")

            deadline = time.monotonic() + timeout_seconds
            last_dom = ""
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise BrowserDiagnostic("A073_BROWSER_PROCESS_EXITED")
                value = connection.call(
                    "Runtime.evaluate", {
                        "expression": (
                            "document.getElementById('a073-result')?.outerHTML || ''"
                        ),
                        "returnByValue": True,
                    }, session=session,
                ).get("result", {}).get("value")
                if isinstance(value, str) and value:
                    last_dom = value
                    if ('data-status="PASS"' in value
                            or 'data-status="FAIL"' in value):
                        return value
                time.sleep(0.12)
            return last_dom
        finally:
            if connection is not None:
                connection.close()
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
