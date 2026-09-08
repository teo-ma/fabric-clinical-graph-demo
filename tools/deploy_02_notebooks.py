"""Step 2: deploy and run the ingestion and graph notebooks.

The graph logic module is inlined into notebook 02 so the deployed code is
byte-identical to what local validation exercised.
"""

from __future__ import annotations

import base64
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fabric_common import (FABRIC, call, err, find_item, load_state,  # noqa: E402
                           save_state, wait_lro)

ROOT = Path(__file__).resolve().parents[1]

NOTEBOOKS = [
    ("01_多源临床数据摄取", "fabric/notebooks/01_ingest_sources.py"),
    ("02_统一临床图谱与业务洞察", "fabric/notebooks/02_build_graph_and_insights.py"),
]


def render(source: str, state: dict) -> str:
    lh = state["lakehouses"]
    replacements = {
        "__WORKSPACE_ID__": state["workspace_id"],
        "__LH_CTMS__": lh["ctms"],
        "__LH_EDC__": lh["edc"],
        "__LH_SAFETY__": lh["safety"],
        "__LH_LIMS__": lh["lims"],
        "__LH_KNOWLEDGE__": lh["knowledge"],
        "__LH_SUPPLY__": lh["supply"],
        "__LH_CURATED__": lh["curated"],
    }
    for placeholder, value in replacements.items():
        source = source.replace(placeholder, value)

    if "# __GRAPH_LOGIC__" in source:
        logic = (ROOT / "fabric" / "graph_logic.py").read_text(encoding="utf-8")
        # Drop the module docstring; the notebook already carries the narrative.
        logic = re.sub(r'^""".*?"""\n', "", logic, count=1, flags=re.DOTALL)
        source = source.replace("# __GRAPH_LOGIC__", logic.strip())

    leftovers = re.findall(r"__[A-Z_]+__", source)
    assert not leftovers, f"存在未替换的占位符: {set(leftovers)}"
    return source


def upsert_notebook(ws_id: str, name: str, content: str) -> str:
    payload = {
        "displayName": name,
        "definition": {
            # .py notebook source uses the default git-source format, not ipynb.
            "parts": [{
                "path": "notebook-content.py",
                "payload": base64.b64encode(content.encode("utf-8")).decode(),
                "payloadType": "InlineBase64",
            }],
        },
    }
    existing = find_item(ws_id, name, "Notebook")
    if existing:
        status, body, headers = call(
            "POST", f"{FABRIC}/v1/workspaces/{ws_id}/items/{existing}/updateDefinition",
            {"definition": payload["definition"]})
        if status == 202:
            wait_lro(headers, f"更新 {name}")
        elif status != 200:
            raise RuntimeError(f"更新笔记本 {name} 失败: {err(body)}")
        return existing

    status, body, headers = call("POST", f"{FABRIC}/v1/workspaces/{ws_id}/notebooks", payload)
    if status in (200, 201):
        return body["id"]
    if status == 202:
        wait_lro(headers, f"创建 {name}")
        found = find_item(ws_id, name, "Notebook")
        if found:
            return found
    raise RuntimeError(f"创建笔记本 {name} 失败: {err(body)}")


def run_notebook(ws_id: str, item_id: str, name: str) -> str:
    status, body, headers = call(
        "POST", f"{FABRIC}/v1/workspaces/{ws_id}/items/{item_id}/jobs/instances"
                "?jobType=RunNotebook", {"executionData": {}})
    if status not in (200, 202):
        raise RuntimeError(f"提交 {name} 作业失败: {err(body)}")

    location = headers.get("Location") or headers.get("location")
    print(f"  已提交 {name}，等待完成…")
    deadline = time.time() + 3600
    last = ""
    while time.time() < deadline:
        st, payload, _ = call("GET", location)
        state = (payload or {}).get("status", "")
        if state != last:
            print(f"    状态 {state}")
            last = state
        if state in ("Completed", "Succeeded"):
            return state
        if state in ("Failed", "Cancelled", "Deduped"):
            raise RuntimeError(f"{name} 运行失败: {payload.get('failureReason') or payload}")
        time.sleep(20)
    raise TimeoutError(f"{name} 运行超时")


def main() -> None:
    state = load_state()
    ws_id = state["workspace_id"]
    state.setdefault("notebooks", {})

    for name, rel_path in NOTEBOOKS:
        source = render((ROOT / rel_path).read_text(encoding="utf-8"), state)
        item_id = upsert_notebook(ws_id, name, source)
        state["notebooks"][name] = item_id
        save_state(state)
        print(f"{name} -> {item_id}")
        result = run_notebook(ws_id, item_id, name)
        print(f"  {name} {result}\n")

    print("两个笔记本均已运行完成。")


if __name__ == "__main__":
    main()
