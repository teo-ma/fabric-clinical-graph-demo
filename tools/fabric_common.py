"""Shared Fabric REST helpers for the clinical demo deployment scripts."""

from __future__ import annotations

import json
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

FABRIC = "https://api.fabric.microsoft.com"
ONELAKE = "https://onelake.dfs.fabric.microsoft.com"
STATE_PATH = Path(__file__).resolve().parents[1] / "fabric" / "deployment_state.json"


def token(resource: str = FABRIC) -> str:
    proc = subprocess.run(
        ["az", "account", "get-access-token", "--resource", resource,
         "--query", "accessToken", "-o", "tsv"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, check=False,
    )
    value = proc.stdout.strip()
    if not value:
        raise RuntimeError("无法获取访问令牌，请确认 az login 状态")
    return value


def call(method: str, url: str, body=None, resource: str = FABRIC,
         raw: bytes | None = None, headers: dict | None = None):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    hdrs = {"Authorization": "Bearer " + token(resource), "Accept": "application/json"}
    if body is not None:
        hdrs["Content-Type"] = "application/json"
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            text = resp.read().decode("utf-8", "replace")
            payload = json.loads(text) if text.strip().startswith(("{", "[")) else {}
            return resp.status, payload, dict(resp.headers)
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", "replace")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = {"raw": text[:400]}
        return exc.code, payload, dict(exc.headers)


def err(payload) -> str:
    if not isinstance(payload, dict):
        return str(payload)[:200]
    nested = payload.get("error") if isinstance(payload.get("error"), dict) else {}
    code = payload.get("errorCode") or nested.get("errorCode") or nested.get("code") or ""
    message = payload.get("message") or nested.get("message") or payload.get("raw") or ""
    return f"{code} {message}".strip()[:300]


def wait_lro(headers: dict, label: str, timeout_s: int = 900) -> dict:
    location = headers.get("Location") or headers.get("location")
    if not location:
        return {}
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        status, payload, _ = call("GET", location)
        state = (payload or {}).get("status")
        if state in ("Succeeded", "Completed"):
            rs, result, _ = call("GET", location.rstrip("/") + "/result")
            return result if rs == 200 else payload
        if state in ("Failed", "Cancelled"):
            raise RuntimeError(f"{label} 失败: {err(payload)}")
        time.sleep(5)
    raise TimeoutError(f"{label} 等待超时")


def load_state(path: Path | None = None) -> dict:
    target = path or STATE_PATH
    if target.exists():
        return json.loads(target.read_text(encoding="utf-8"))
    return {}


def save_state(state: dict, path: Path | None = None) -> None:
    target = path or STATE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def find_item(workspace_id: str, display_name: str, item_type: str) -> str | None:
    status, payload, _ = call("GET", f"{FABRIC}/v1/workspaces/{workspace_id}/items")
    if status != 200:
        return None
    for item in payload.get("value", []):
        if item.get("displayName") == display_name and item.get("type") == item_type:
            return item.get("id")
    return None
