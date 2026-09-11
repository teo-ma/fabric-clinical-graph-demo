"""Lineage demo step 1: workspace, lakehouses, spec upload, notebooks.

Separate state file so the clinical-graph demo (v2) is never touched.
Idempotent: re-running reuses whatever already exists.
"""

from __future__ import annotations

import base64
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fabric_common import (FABRIC, ONELAKE, call, err, find_item,  # noqa: E402
                           load_state, save_state, wait_lro)

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "fabric" / "lineage_deployment_state.json"
CAPACITY_ID = "0f6e9354-acfb-40ec-b6cb-81d94d8b8b68"
WORKSPACE_NAME = "Fabric CRF-SDTM 血缘 Demo"

LAKEHOUSES = {
    "spec": "LH_Spec_映射规范库",
    "curated": "LH_Lineage_血缘图谱",
}

SPEC_TABLES = ["crf_forms", "crf_fields", "sdtm_domains", "sdtm_variables",
               "mapping_rules", "variable_derivations", "controlled_terms"]

NOTEBOOKS = [
    ("11_映射规范摄取", "fabric/notebooks/11_ingest_spec.py"),
    ("12_血缘图谱与治理洞察", "fabric/notebooks/12_build_lineage_graph.py"),
]


def ensure_workspace(state: dict) -> str:
    if state.get("workspace_id"):
        status, payload, _ = call("GET", f"{FABRIC}/v1/workspaces/{state['workspace_id']}")
        if status == 200:
            print(f"复用工作区 {payload.get('displayName')}")
            return state["workspace_id"]

    status, payload, _ = call("GET", f"{FABRIC}/v1/workspaces")
    for ws in payload.get("value", []) if status == 200 else []:
        if ws.get("displayName") == WORKSPACE_NAME:
            print(f"发现同名工作区，直接复用: {ws['id']}")
            return ws["id"]

    status, payload, _ = call("POST", f"{FABRIC}/v1/workspaces", {
        "displayName": WORKSPACE_NAME,
        "description": "CRF 到 SDTM 映射血缘演示。全部为合成的示意性数据。",
    })
    if status not in (200, 201):
        raise RuntimeError(f"创建工作区失败: {err(payload)}")
    ws_id = payload["id"]
    print(f"已创建工作区 {ws_id}")

    status, payload, _ = call("POST", f"{FABRIC}/v1/workspaces/{ws_id}/assignToCapacity",
                              {"capacityId": CAPACITY_ID})
    if status not in (200, 202):
        raise RuntimeError(f"绑定容量失败: {err(payload)}")
    print("已绑定容量")
    return ws_id


def ensure_lakehouse(ws_id: str, display_name: str) -> str:
    existing = find_item(ws_id, display_name, "Lakehouse")
    if existing:
        return existing
    status, payload, headers = call("POST", f"{FABRIC}/v1/workspaces/{ws_id}/lakehouses",
                                    {"displayName": display_name})
    if status in (200, 201):
        return payload["id"]
    if status == 202:
        wait_lro(headers, f"创建 {display_name}")
        found = find_item(ws_id, display_name, "Lakehouse")
        if found:
            return found
    raise RuntimeError(f"创建 Lakehouse {display_name} 失败: {err(payload)}")


def upload(ws_id: str, lakehouse_id: str, table: str) -> int:
    content = (ROOT / "data" / "spec" / f"{table}.csv").read_bytes()
    target = f"{ONELAKE}/{ws_id}/{lakehouse_id}/Files/landing/{table}.csv"
    store = "https://storage.azure.com"

    status, payload, _ = call("PUT", f"{target}?resource=file", resource=store)
    if status not in (201, 202):
        raise RuntimeError(f"创建 {table}.csv 失败: {err(payload)}")

    status, payload, _ = call("PATCH", f"{target}?action=append&position=0",
                              raw=content, resource=store,
                              headers={"Content-Type": "application/octet-stream"})
    if status not in (200, 202):
        raise RuntimeError(f"写入 {table}.csv 失败: {err(payload)}")

    status, payload, _ = call("PATCH", f"{target}?action=flush&position={len(content)}",
                              resource=store)
    if status not in (200, 202):
        raise RuntimeError(f"提交 {table}.csv 失败: {err(payload)}")
    return len(content)


def render(source: str, state: dict) -> str:
    for placeholder, value in {
        "__WORKSPACE_ID__": state["workspace_id"],
        "__SPEC_LAKEHOUSE_ID__": state["lakehouses"]["spec"],
        "__CURATED_LAKEHOUSE_ID__": state["lakehouses"]["curated"],
    }.items():
        source = source.replace(placeholder, value)

    if "# __LINEAGE_LOGIC__" in source:
        logic = (ROOT / "fabric" / "lineage_logic.py").read_text(encoding="utf-8")
        logic = re.sub(r'^""".*?"""\n', "", logic, count=1, flags=re.DOTALL)
        logic = logic.replace("from __future__ import annotations\n", "")
        source = source.replace("# __LINEAGE_LOGIC__", logic.strip())

    leftovers = re.findall(r"__[A-Z_]+__", source)
    assert not leftovers, f"存在未替换的占位符: {set(leftovers)}"
    return source


def upsert_notebook(ws_id: str, name: str, content: str) -> str:
    definition = {"parts": [{
        "path": "notebook-content.py",
        "payload": base64.b64encode(content.encode("utf-8")).decode(),
        "payloadType": "InlineBase64",
    }]}

    existing = find_item(ws_id, name, "Notebook")
    if existing:
        status, body, headers = call(
            "POST", f"{FABRIC}/v1/workspaces/{ws_id}/items/{existing}/updateDefinition",
            {"definition": definition})
        if status == 202:
            wait_lro(headers, f"更新 {name}")
        elif status != 200:
            raise RuntimeError(f"更新笔记本 {name} 失败: {err(body)}")
        return existing

    status, body, headers = call("POST", f"{FABRIC}/v1/workspaces/{ws_id}/notebooks",
                                 {"displayName": name, "definition": definition})
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
        _, payload, _ = call("GET", location)
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
    state = load_state(STATE)
    ws_id = ensure_workspace(state)
    state["workspace_id"] = ws_id
    state["capacity_id"] = CAPACITY_ID
    state.setdefault("lakehouses", {})

    for key, display_name in LAKEHOUSES.items():
        state["lakehouses"][key] = ensure_lakehouse(ws_id, display_name)
        print(f"{display_name} -> {state['lakehouses'][key]}")
    save_state(state, STATE)

    total = 0
    for table in SPEC_TABLES:
        total += upload(ws_id, state["lakehouses"]["spec"], table)
    print(f"已上传 {len(SPEC_TABLES)} 个规范文件，共 {total} 字节")

    state.setdefault("notebooks", {})
    for name, rel_path in NOTEBOOKS:
        source = render((ROOT / rel_path).read_text(encoding="utf-8"), state)
        item_id = upsert_notebook(ws_id, name, source)
        state["notebooks"][name] = item_id
        save_state(state, STATE)
        print(f"{name} -> {item_id}")
        print(f"  {name} {run_notebook(ws_id, item_id, name)}\n")

    save_state(state, STATE)
    print("规范摄取与血缘图谱构建完成。")


if __name__ == "__main__":
    main()
