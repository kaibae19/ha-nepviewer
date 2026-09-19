#!/usr/bin/env python3
"""Probe the NEPViewer cloud API and dump raw responses.

Reads NEPVIEWER_USER / NEPVIEWER_PASS from the environment or ~/.env.
Nothing is written to the repo; dumps land in the directory given by --out
(default: a temp dir). Credentials are never printed.

Usage:
    python3 tools/probe_api.py [--out DIR] [--sn SN]
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import ssl
import sys
import tempfile
import urllib.error
import urllib.request

BASE = "https://api.nepviewer.net"
HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Origin": "https://user.nepviewer.com",
    "Oem": "NEP",
    "Client": "web",
    "App": "0",
}


def ssl_context() -> ssl.SSLContext:
    """Trust certifi's roots when the interpreter has no usable store."""
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


SSL_CTX = ssl_context()


def load_env() -> tuple[str, str]:
    user = os.environ.get("NEPVIEWER_USER")
    pw = os.environ.get("NEPVIEWER_PASS")
    env = pathlib.Path.home() / ".env"
    if (not user or not pw) and env.is_file():
        for line in env.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            v = v.strip().strip('"').strip("'")
            if k.strip() == "NEPVIEWER_USER" and not user:
                user = v
            elif k.strip() == "NEPVIEWER_PASS" and not pw:
                pw = v
    if not user or not pw:
        sys.exit("NEPVIEWER_USER / NEPVIEWER_PASS not found in env or ~/.env")
    return user, pw


def call(path: str, payload: dict, token: str | None = None) -> dict:
    headers = dict(HEADERS)
    if token:
        headers["Authorization"] = token
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(payload).encode(),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20, context=SSL_CTX) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as err:
        return {"_http_error": err.code, "_body": err.read().decode()[:400]}
    except Exception as err:  # noqa: BLE001 - probe script, report anything
        return {"_error": repr(err)}


def dump(out: pathlib.Path, name: str, data: dict) -> None:
    path = out / f"{name}.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    code = data.get("code", data.get("_http_error", data.get("_error")))
    print(f"  -> {path}  (code={code})")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    ap.add_argument("--sn", default=None)
    args = ap.parse_args()

    out = pathlib.Path(args.out or tempfile.mkdtemp(prefix="nepprobe-"))
    out.mkdir(parents=True, exist_ok=True)
    print(f"dumping to {out}")

    user, pw = load_env()

    print("sign-in ...")
    auth = call("/v2/sign-in", {"account": user, "password": pw})
    if auth.get("code") != 200:
        dump(out, "00-sign-in-FAILED", auth)
        sys.exit(f"sign-in failed: {auth.get('msg', auth)}")
    token = auth["data"]["tokenInfo"]["token"]
    redacted = json.loads(json.dumps(auth))
    redacted["data"]["tokenInfo"]["token"] = "<redacted>"
    dump(out, "00-sign-in", redacted)
    print(f"  token acquired ({len(token)} chars)")

    print("device/list ...")
    devices = call("/v2/device/list", {"page": {"size": 50}}, token)
    dump(out, "01-device-list", devices)

    sns: list[str] = []
    if args.sn:
        sns = [args.sn]
    else:
        for dev in (devices.get("data") or {}).get("list") or []:
            if dev.get("sn"):
                sns.append(dev["sn"])
    if not sns:
        sys.exit("no device SNs found; pass --sn explicitly")
    print(f"devices: {', '.join(sns)}")

    # Endpoints worth probing per device. Unknown ones are expected to fail;
    # a non-200 code here is information, not an error.
    probes = [
        ("device/statistics/overview", {}),
        ("device/detail", {}),
        ("device/info", {}),
        ("device/inverter/list", {}),
        ("device/module/list", {}),
        ("device/statistics/realtime", {}),
        ("device/alert/list", {"page": {"size": 20}}),
        ("device/statistics/echarts", {"types": 1, "rangeDate": ""}),
    ]

    for sn in sns:
        for path, extra in probes:
            payload = {"sn": sn, **extra}
            print(f"{path} (sn={sn}) ...")
            dump(out, f"02-{sn}-{path.replace('/', '_')}", call(f"/v2/{path}", payload, token))

    print(f"\ndone. review the JSON in {out}")


if __name__ == "__main__":
    main()
