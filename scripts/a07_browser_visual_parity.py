"""A07.3: run a local real-browser *synthetic* Studio preview/export check.

No Playwright, Chrome download, network call, service, operational database or
credential. Only a file:// fixture and the repo's studio_export_e4.js are loaded.
Browser absence is NOT success. This does not demonstrate rights, publication,
actual Studio authentication or cross-browser/pixel-fidelity acceptance.
"""
from __future__ import annotations

import argparse
from html import unescape
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "frontend" / "studio_export_browser_a07.html"
ENGINE = ROOT / "src" / "tapi_gate0" / "web" / "studio_export_e4.js"
RESULT_TAG = re.compile(
    r'<output\b(?P<attrs>[^>]*)\bid="a073-result"(?P<tail>[^>]*)>'
    r'(?P<body>.*?)</output>',
    flags=re.IGNORECASE | re.DOTALL,
)


def find_browser(explicit: str | None = None) -> Path | None:
    if explicit:
        candidate = Path(explicit).expanduser()
        return candidate if candidate.is_file() else None
    env = os.environ.get("TAPI_A073_BROWSER")
    if env:
        candidate = Path(env).expanduser()
        return candidate if candidate.is_file() else None
    candidates = [
        "chromium", "chromium-browser", "google-chrome", "google-chrome-stable",
        "chrome", "msedge",
    ]
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return Path(resolved)
    if sys.platform == "win32":
        bases = [os.environ.get("PROGRAMFILES"),
                 os.environ.get("PROGRAMFILES(X86)"),
                 os.environ.get("LOCALAPPDATA")]
        suffixes = [
            Path("Google/Chrome/Application/chrome.exe"),
            Path("Microsoft/Edge/Application/msedge.exe"),
            Path("Chromium/Application/chrome.exe"),
        ]
        for base in bases:
            if base:
                for suffix in suffixes:
                    candidate = Path(base) / suffix
                    if candidate.is_file():
                        return candidate
    return None


def read_result(html: str) -> tuple[bool, str]:
    found = RESULT_TAG.search(html)
    if not found:
        return False, "A073_BROWSER_DID_NOT_COMPLETE"
    attrs = found.group("attrs") + found.group("tail")
    status = re.search(r'\bdata-status="([^"]+)"', attrs)
    passed = re.search(r'\bdata-passed="([^"]+)"', attrs)
    total = re.search(r'\bdata-total="([^"]+)"', attrs)
    detail = unescape(re.sub(r'<[^>]*>', '', found.group("body"))).strip()
    if not status or not passed or not total:
        return False, "A073_RESULT_ATTRIBUTES_MISSING"
    if (status.group(1) == "PASS" and passed.group(1) == "7"
            and total.group(1) == "7" and detail == "A073_BROWSER_PARITY_PASS"):
        return True, "A073_BROWSER_PARITY_PASS 7/7"
    # The fixture contains fictional source text only; still avoid printing
    # raw DOM, browser stderr, user paths or browser profile contents.
    return False, "A073_BROWSER_CHECK_FAILED " + detail[:350]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser", help="Caminho explícito ao Chrome/Edge/Chromium local")
    args = parser.parse_args(argv)

    if not FIXTURE.is_file() or not ENGINE.is_file():
        print("A073_LOCAL_FIXTURE_OR_EXPORTER_MISSING")
        return 2
    browser = find_browser(args.browser)
    if browser is None:
        print("A073_BROWSER_NOT_INSTALLED — nenhum PASS; forneça --browser")
        return 2

    # Isolate from any signed-in user profile and browser extensions.
    # The Chromium process is not allowed to resolve public hosts.
    with tempfile.TemporaryDirectory(prefix="stone-a073-browser-") as profile:
        flags = [
            str(browser), "--headless=new", "--no-first-run",
            "--no-default-browser-check", "--disable-extensions",
            "--disable-background-networking", "--disable-component-update",
            "--disable-sync", "--disable-features=MediaRouter",
            "--host-resolver-rules=MAP * 0.0.0.0, EXCLUDE localhost",
            "--disable-popup-blocking", "--hide-scrollbars",
            f"--user-data-dir={profile}", "--virtual-time-budget=12000",
            "--dump-dom", FIXTURE.as_uri(),
        ]
        # Only for a root-owned disposable Linux dev container. Never used
        # on Windows or with a real user profile.
        if getattr(os, "geteuid", lambda: -1)() == 0:
            flags.insert(1, "--no-sandbox")
        try:
            result = subprocess.run(
                flags, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=45,
                check=False,
            )
        except subprocess.TimeoutExpired:
            print("A073_BROWSER_TIMEOUT — nenhum PASS")
            return 1
        except OSError:
            print("A073_BROWSER_LAUNCH_FAILED — nenhum PASS")
            return 2
        if result.returncode != 0:
            print("A073_BROWSER_PROCESS_FAILED — nenhum PASS")
            return 1
        ok, summary = read_result(result.stdout)
        print(summary)
        return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
