"""Run PySpark statements against a Fabric lakehouse via the Livy API.

Deployment jobs only report "statement execution failures" with no traceback,
so this gives a way to see the real Python error headlessly.

Usage: python3 tools/livy_run.py <state-file> <lakehouse-key> <script.py>
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fabric_common import FABRIC, call, err, load_state  # noqa: E402

API = "livyapi/versions/2023-12-01"


def wait(url: str, done: set[str], label: str, timeout_s: int = 900) -> dict:
    deadline = time.time() + timeout_s
    last = ""
    while time.time() < deadline:
        status, payload, _ = call("GET", url)
        if status != 200:
            raise RuntimeError(f"{label} 查询失败: {err(payload)}")
        state = payload.get("state", "")
        if state != last:
            print(f"  {label} {state}")
            last = state
        if state in done:
            return payload
        if state in ("error", "dead", "killed"):
            raise RuntimeError(f"{label} 进入 {state}: {json.dumps(payload)[:500]}")
        time.sleep(5)
    raise TimeoutError(f"{label} 超时")


def main() -> None:
    state_file, lakehouse_key, script = sys.argv[1:4]
    state = load_state(Path(state_file))
    ws = state["workspace_id"]
    lh = state["lakehouses"][lakehouse_key]
    base = f"{FABRIC}/v1/workspaces/{ws}/lakehouses/{lh}/{API}/sessions"

    status, payload, _ = call("POST", base, {})
    if status not in (200, 201, 202):
        raise RuntimeError(f"创建 Livy 会话失败: {status} {err(payload)}")
    sid = payload["id"]
    print(f"会话 {sid}")

    try:
        wait(f"{base}/{sid}", {"idle"}, "会话")
        code = Path(script).read_text(encoding="utf-8")
        status, payload, _ = call("POST", f"{base}/{sid}/statements",
                                  {"code": code, "kind": "pyspark"})
        if status not in (200, 201):
            raise RuntimeError(f"提交语句失败: {err(payload)}")
        stid = payload["id"]
        result = wait(f"{base}/{sid}/statements/{stid}", {"available"}, "语句")
        out = result.get("output") or {}
        if out.get("status") == "error":
            print(f"\n!! {out.get('ename')}: {out.get('evalue')}")
            print("\n".join(out.get("traceback") or []))
            sys.exit(1)
        print("\n" + (out.get("data") or {}).get("text/plain", ""))
    finally:
        call("DELETE", f"{base}/{sid}")
        print(f"已关闭会话 {sid}")


if __name__ == "__main__":
    main()
