from __future__ import annotations

import json
import os
import asyncio
import struct
import sys
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCAL_URL = os.environ.get("HUA_TFSU_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
REMOTE_URL = os.environ.get("HUA_TFSU_REMOTE_URL", "").rstrip("/")


checks: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))


def request_json(url: str, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="GET" if body is None else "POST",
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def request_text(url: str) -> str:
    with urllib.request.urlopen(url, timeout=30) as response:
        return response.read().decode("utf-8")


def check_endpoint(name: str, url: str) -> None:
    try:
        health = request_json(f"{url}/health")
        record(f"{name}: health", health.get("status") == "ok", str(health))

        html = request_text(url)
        for label, needle in [
            ("captions tab", "\u5b9e\u65f6\u5b57\u5e55"),
            ("terms tab", "\u672f\u8bed\u5e93"),
            ("corpus tab", "\u53cc\u8bed\u8bed\u6599\u5e93"),
            ("notes tab", "\u624b\u5199\u7b14\u8bb0"),
        ]:
            record(f"{name}: {label}", needle in html)

        term = "Transformer \u67b6\u6784"
        translated = request_json(
            f"{url}/api/translate",
            {
                "direction": "en-zh",
                "text": "Transformer improves attention.",
                "terms": {"Transformer": term},
            },
        )
        record(f"{name}: translate status", translated.get("type") == "translation", str(translated))
        record(f"{name}: glossary priority", term in translated.get("translation", ""), translated.get("translation", ""))

        extracted = request_json(
            f"{url}/api/extract-terms",
            {
                "direction": "en-zh",
                "text": "Transformer, Retrieval Augmented Generation, and BLEU are used in MT evaluation.",
                "existing_terms": {},
            },
        )
        terms = extracted.get("terms", {})
        record(f"{name}: term extraction", any(key in terms for key in ["Transformer", "Retrieval Augmented Generation", "BLEU"]), str(terms))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        record(f"{name}: endpoint reachable", False, repr(exc))


async def check_websocket_endpoint(name: str, url: str) -> None:
    try:
        import websockets
    except ImportError:
        record(f"{name}: websocket dependency", False, "websockets is not installed")
        return

    ws_proto = "wss" if url.startswith("https://") else "ws"
    host = url.split("://", 1)[1]
    target = "".join(chr(code) for code in [0x6F14, 0x793A, 0x542C, 0x5199])
    payload = struct.pack("<" + "f" * 32000, *([0.01] * 32000))

    try:
        async with websockets.connect(f"{ws_proto}://{host}/ws/subtitle", open_timeout=30) as ws:
            await ws.send(
                json.dumps(
                    {
                        "direction": "en-zh",
                        "sample_rate": 16000,
                        "terms": {"Demo transcript": target},
                    },
                    ensure_ascii=False,
                )
            )
            ready = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
            record(f"{name}: websocket ready", ready.get("type") == "ready", str(ready))
            await ws.send(payload)
            await ws.send("flush")
            subtitle = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
            record(f"{name}: websocket subtitle", subtitle.get("type") == "subtitle", str(subtitle))
            record(f"{name}: websocket glossary", target in subtitle.get("translation", ""), subtitle.get("translation", ""))
            await ws.send("stop")
    except Exception as exc:
        record(f"{name}: websocket reachable", False, repr(exc))


def check_static_files() -> None:
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    css = (ROOT / "frontend" / "styles.css").read_text(encoding="utf-8")
    schemas = (ROOT / "backend" / "app" / "schemas.py").read_text(encoding="utf-8")
    main = (ROOT / "backend" / "app" / "main.py").read_text(encoding="utf-8")

    static_checks = [
        ("html has 4 tab buttons", html.count("data-view=") == 4),
        ("terms view present", 'id="view-terms"' in html),
        ("corpus view present", 'id="view-corpus"' in html),
        ("notes view present", 'id="view-notes"' in html),
        ("API key local storage", "hua_tfsu_openai_api_key" in js),
        ("glossary local storage", "hua_tfsu_terms" in js),
        ("corpus local storage", "hua_tfsu_corpus" in js),
        ("notes local storage", "hua_tfsu_notes" in js),
        ("AI extract endpoint call", "/api/extract-terms" in js),
        ("translate sends terms", "terms: loadTerms()" in js),
        ("WebSocket sends terms", "terms: loadTerms()" in js and "sample_rate: TARGET_RATE" in js),
        ("canvas pointer notes", "pointerdown" in js and "setPointerCapture" in js),
        ("techy color tokens", "--primary: #38f8ff" in css and "--accent: #ff4f8b" in css),
        ("responsive mobile CSS", "@media (max-width:" in css),
        ("session config supports terms", "terms: dict[str, str]" in schemas),
        ("server path uses glossary", "config.terms" in main and "terms=terms" in main),
    ]
    for name, ok in static_checks:
        record(name, ok)


def main() -> int:
    check_static_files()
    check_endpoint("local", LOCAL_URL)
    asyncio.run(check_websocket_endpoint("local", LOCAL_URL))
    if REMOTE_URL:
        check_endpoint("remote", REMOTE_URL)
        asyncio.run(check_websocket_endpoint("remote", REMOTE_URL))

    for index, (name, ok, detail) in enumerate(checks, 1):
        status = "PASS" if ok else "FAIL"
        suffix = f" - {detail}" if detail else ""
        print(f"{index:02d}. {status} {name}{suffix}")

    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"\n{passed}/{len(checks)} checks passed")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
