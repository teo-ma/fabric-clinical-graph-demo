"""Step 1: create the demo workspace, the source lakehouses, and upload landing data.

Idempotent. Re-running reuses anything that already exists and only uploads
files that are missing or changed.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fabric_common import (FABRIC, ONELAKE, call, err, find_item, load_state,  # noqa: E402
                           save_state, wait_lro)

ROOT = Path(__file__).resolve().parents[1]
CAPACITY_ID = "0f6e9354-acfb-40ec-b6cb-81d94d8b8b68"
WORKSPACE_NAME = "Fabric 临床智能 Demo 20260908"

LAKEHOUSES = {
    "ctms": "LH_CTMS_临床试验管理",
    "edc": "LH_EDC_电子数据采集",
    "safety": "LH_Safety_药物警戒",
    "lims": "LH_LIMS_中心实验室",
    "knowledge": "LH_Knowledge_转化医学知识库",
    "supply": "LH_Supply_临床供应链",
    "curated": "LH_Curated_统一临床图谱",
}

SOURCE_TABLES = {
    "ctms": ["studies", "sites", "investigators", "subjects", "protocol_deviations"],
    "edc": ["visits", "dosing_records"],
    "safety": ["adverse_events", "safety_signals", "ae_signal_links"],
    "lims": ["lab_results"],
    "knowledge": ["compounds", "targets", "pathways", "biomarkers", "ae_terms",
                  "compound_target", "target_pathway", "pathway_biomarker", "biomarker_ae"],
    "supply": ["batches", "shipments"],
}


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
        "description": "跨源系统临床开发智能演示。全部为合成数据。",
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


def upload(ws_id: str, lakehouse_id: str, system: str, table: str) -> str:
    local = ROOT / "data" / "sources" / system / f"{table}.csv"
    content = local.read_bytes()
    target = f"{ONELAKE}/{ws_id}/{lakehouse_id}/Files/landing/{table}.csv"

    status, payload, _ = call("PUT", f"{target}?resource=file", resource="https://storage.azure.com")
    if status not in (201, 202):
        raise RuntimeError(f"创建 {system}/{table}.csv 失败: {err(payload)}")

    status, payload, _ = call("PATCH", f"{target}?action=append&position=0",
                              raw=content, resource="https://storage.azure.com",
                              headers={"Content-Type": "application/octet-stream"})
    if status not in (200, 202):
        raise RuntimeError(f"写入 {system}/{table}.csv 失败: {err(payload)}")

    status, payload, _ = call("PATCH", f"{target}?action=flush&position={len(content)}",
                              resource="https://storage.azure.com")
    if status not in (200, 202):
        raise RuntimeError(f"提交 {system}/{table}.csv 失败: {err(payload)}")
    return hashlib.sha256(content).hexdigest()[:12]


def main() -> None:
    state = load_state()
    ws_id = ensure_workspace(state)
    state["workspace_id"] = ws_id
    state["capacity_id"] = CAPACITY_ID
    state.setdefault("lakehouses", {})

    for key, display_name in LAKEHOUSES.items():
        item_id = ensure_lakehouse(ws_id, display_name)
        state["lakehouses"][key] = item_id
        print(f"{key:<10} {display_name:<26} {item_id}")
    save_state(state)

    print("\n上传各源系统着陆区数据")
    uploaded = 0
    for system, tables in SOURCE_TABLES.items():
        for table in tables:
            digest = upload(ws_id, state["lakehouses"][system], system, table)
            uploaded += 1
            print(f"  {system:<10} {table:<22} sha256={digest}")
    save_state(state)
    print(f"\n完成：7 个 Lakehouse，{uploaded} 个着陆文件。工作区 {ws_id}")


if __name__ == "__main__":
    main()
