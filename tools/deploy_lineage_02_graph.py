"""Lineage demo step 2: Graph model over the CRF-to-SDTM lineage tables.

The graph item uses the graphIndex definition file set. Writing a definition with
the wrong file names is accepted by the service but leaves an empty model, so the
script reads the definition back and fails loudly if the node types are missing.
"""

from __future__ import annotations

import base64
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fabric_common import (FABRIC, call, err, find_item, load_state,  # noqa: E402
                           save_state, wait_lro)

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "fabric" / "lineage_deployment_state.json"

GRAPH_NAME = "CrfSdtmLineageGraph"
SCHEMA_BASE = "https://developer.microsoft.com/json-schemas/fabric/item/graphIndex/definition"

NODE_ALIAS = "SpecNode_nodeType"
EDGE_ALIAS = "SpecRelationship_edgeType"

NODE_PROPERTIES = [
    ("NodeId", "node_id", "STRING"),
    ("NodeType", "node_type", "STRING"),
    ("NodeTypeZh", "node_type_zh", "STRING"),
    ("DisplayNameZh", "display_name_zh", "STRING"),
    ("Domain", "domain", "STRING"),
    ("FormOid", "form_oid", "STRING"),
    ("Core", "core", "STRING"),
    ("DataType", "data_type", "STRING"),
    ("Codelist", "codelist", "STRING"),
    ("AcrfPage", "acrf_page", "STRING"),
    ("IsSupplemental", "is_supplemental", "STRING"),
    ("ExpectedOrigin", "expected_origin", "STRING"),
    ("SpecVersion", "spec_version", "STRING"),
]

EDGE_PROPERTIES = [
    ("EdgeId", "edge_id", "STRING"),
    ("RelationshipType", "relationship_type", "STRING"),
    ("RelationshipTypeZh", "relationship_type_zh", "STRING"),
    ("Algorithm", "algorithm", "STRING"),
    ("ConditionZh", "condition_zh", "STRING"),
    ("RuleId", "rule_id", "STRING"),
    ("MappingPenalty", "mapping_penalty", "FLOAT"),
    ("SpecVersion", "spec_version", "STRING"),
]


def build_parts(state: dict) -> list[dict]:
    ws_id = state["workspace_id"]
    curated = state["lakehouses"]["curated"]

    graph_type = {
        "$schema": f"{SCHEMA_BASE}/graphType/1.0.0/schema.json",
        "nodeTypes": [{
            "primaryKeyProperties": ["NodeId"],
            "alias": NODE_ALIAS,
            "labels": ["SpecNode"],
            "properties": [{"name": n, "type": t} for n, _, t in NODE_PROPERTIES],
        }],
        "edgeTypes": [{
            "alias": EDGE_ALIAS,
            "sourceNodeType": {"alias": NODE_ALIAS},
            "labels": ["SPEC_RELATIONSHIP"],
            "destinationNodeType": {"alias": NODE_ALIAS},
            "properties": [{"name": n, "type": t} for n, _, t in EDGE_PROPERTIES],
        }],
    }

    data_sources = {
        "$schema": f"{SCHEMA_BASE}/dataSources/1.1.0/schema.json",
        "itemReferences": [{
            "name": "LineageLakehouseRef",
            "item": {"workspaceId": ws_id, "itemId": curated},
        }],
        "dataSources": [
            {"name": "LineageNodesTable", "type": "DeltaTable",
             "properties": {"referenceName": "LineageLakehouseRef",
                            "path": "Tables/lineage_nodes"}},
            {"name": "LineageEdgesTable", "type": "DeltaTable",
             "properties": {"referenceName": "LineageLakehouseRef",
                            "path": "Tables/lineage_edges"}},
        ],
    }

    graph_definition = {
        "$schema": f"{SCHEMA_BASE}/graphDefinition/1.0.0/schema.json",
        "nodeTables": [{
            "nodeTypeAlias": NODE_ALIAS,
            "id": "SpecNode_table",
            "dataSourceName": "LineageNodesTable",
            "propertyMappings": [{"propertyName": n, "sourceColumn": c}
                                 for n, c, _ in NODE_PROPERTIES],
        }],
        "edgeTables": [{
            "edgeTypeAlias": EDGE_ALIAS,
            "id": "SpecRelationship_table",
            "edgeIdMapping": None,
            "dataSourceName": "LineageEdgesTable",
            "sourceNodeKeyColumns": ["source_node_id"],
            "destinationNodeKeyColumns": ["target_node_id"],
            "propertyMappings": [{"propertyName": n, "sourceColumn": c}
                                 for n, c, _ in EDGE_PROPERTIES],
        }],
    }

    styling = {
        "$schema": f"{SCHEMA_BASE}/stylingConfiguration/1.0.0/schema.json",
        "modelLayout": {
            "positions": {NODE_ALIAS: {"x": 240.0, "y": 200.0}},
            "styles": {NODE_ALIAS: {"size": 36}, EDGE_ALIAS: {"size": 24}},
            "pan": {"x": 0.0, "y": 0.0},
            "zoomLevel": 1.0,
        },
        "visualFormat": {
            NODE_ALIAS: {"defaultDisplayProperty": "DisplayNameZh",
                         "color": "#4C6EF5", "shape": "Circle"},
            EDGE_ALIAS: {"defaultDisplayProperty": "RelationshipTypeZh",
                         "color": "#C99A2E", "shape": None},
        },
    }

    files = {
        "graphType.json": graph_type,
        "dataSources.json": data_sources,
        "graphDefinition.json": graph_definition,
        "stylingConfiguration.json": styling,
        "graphSettings.json": {"$schema": f"{SCHEMA_BASE}/graphSettings/1.0.0/schema.json"},
        ".platform": {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/"
                       "platformProperties/2.0.0/schema.json",
            "metadata": {"type": "GraphModel", "displayName": GRAPH_NAME,
                         "description": "CRF 字段到 SDTM 变量的映射血缘图，"
                                        "支持原生 GQL 多跳溯源与影响分析。示意性合成数据。"},
            "config": {"version": "2.0",
                       "logicalId": "00000000-0000-0000-0000-000000000000"},
        },
    }

    return [{"path": path,
             "payload": base64.b64encode(
                 json.dumps(obj, ensure_ascii=False, indent=2).encode()).decode(),
             "payloadType": "InlineBase64"}
            for path, obj in files.items()]


def verify(ws_id: str, graph_id: str) -> None:
    status, payload, headers = call(
        "POST", f"{FABRIC}/v1/workspaces/{ws_id}/items/{graph_id}/getDefinition")
    if status == 202:
        payload = wait_lro(headers, "回读图定义")
    for part in payload.get("definition", {}).get("parts", []):
        if part["path"] != "graphType.json":
            continue
        obj = json.loads(base64.b64decode(part["payload"]).decode())
        node_types = obj.get("nodeTypes") or []
        edge_types = obj.get("edgeTypes") or []
        if not node_types or not edge_types:
            raise RuntimeError("图定义回读为空，节点或边类型缺失")
        print(f"回读校验通过：节点类型 {node_types[0]['labels']}，"
              f"边类型 {edge_types[0]['labels']}，"
              f"节点属性 {len(node_types[0]['properties'])} 个")
        return
    raise RuntimeError("回读结果中没有 graphType.json")


def refresh(ws_id: str, graph_id: str) -> None:
    """Trigger a refresh, tolerating the auto-refresh that updateDefinition starts.

    A definition write already queues a refresh, so an explicit RefreshGraph job
    usually comes back as Deduped. That is not a failure: it means a refresh is
    already in flight, and the only thing that matters is that the index becomes
    queryable, which wait_until_queryable checks directly.
    """
    status, payload, headers = call(
        "POST", f"{FABRIC}/v1/workspaces/{ws_id}/items/{graph_id}/jobs/instances"
                "?jobType=RefreshGraph", {"executionData": {}})
    if status not in (200, 202):
        print(f"  跳过显式刷新（{err(payload)}），改为等待自动刷新")
        return
    location = headers.get("Location") or headers.get("location")
    if not location:
        return
    deadline = time.time() + 1800
    last = ""
    while time.time() < deadline:
        _, payload, _ = call("GET", location)
        state = (payload or {}).get("status", "")
        if state != last:
            print(f"  刷新状态 {state}")
            last = state
        if state in ("Completed", "Succeeded", "Deduped"):
            return
        if state in ("Failed", "Cancelled"):
            raise RuntimeError(f"图刷新失败: {payload.get('failureReason') or payload}")
        time.sleep(15)
    raise TimeoutError("图刷新超时")


def wait_until_queryable(ws_id: str, graph_id: str, expected_nodes: int = 100) -> None:
    gql = "MATCH (n:SpecNode) RETURN count(*) AS 数量;"
    deadline = time.time() + 1800
    while time.time() < deadline:
        try:
            rows = query(ws_id, graph_id, gql)
        except RuntimeError as exc:
            print(f"  图索引尚未就绪：{str(exc)[:120]}")
            time.sleep(20)
            continue
        count = int(next(iter(rows[0].values()))) if rows else 0
        print(f"  图索引节点数 {count}")
        if count >= expected_nodes:
            return
        time.sleep(20)
    raise TimeoutError("图索引未在预期时间内建好")


def query(ws_id: str, graph_id: str, gql: str) -> list[dict]:
    status, payload, _ = call(
        "POST", f"{FABRIC}/v1/workspaces/{ws_id}/GraphModels/{graph_id}"
                "/executeQuery?preview=true", {"query": gql})
    if status != 200:
        raise RuntimeError(f"GQL 查询失败 HTTP {status}: {err(payload)}")
    code = (payload.get("status") or {}).get("code")
    if code not in ("00000", None):
        raise RuntimeError(f"GQL 返回错误 {code}: {json.dumps(payload)[:400]}")
    return (payload.get("result") or {}).get("data") or []


SMOKE_TESTS = [
    # GQL 的 GROUP BY 只接受 RETURN 里的别名，写成 n.NodeTypeZh 会报语法错误。
    ("节点总数与分布",
     "MATCH (n:SpecNode) RETURN n.NodeTypeZh AS 类型, count(*) AS 数量 "
     "GROUP BY 类型 ORDER BY 数量 DESC;"),
    ("DM.ARMCD 的全部来源与映射折损",
     "MATCH (f:SpecNode WHERE f.NodeType = 'CRFField')"
     "-[r:SPEC_RELATIONSHIP WHERE r.RelationshipType = 'MAPS_TO']->"
     "(v:SpecNode WHERE v.NodeId = 'SDTM:DM.ARMCD') "
     "RETURN f.DisplayNameZh AS 来源字段, r.Algorithm AS 转换方式, "
     "r.MappingPenalty AS 映射折损 ORDER BY 映射折损 ASC;"),
    ("给药开始日期的下游影响链",
     "MATCH p = (f:SpecNode WHERE f.NodeId = 'CRF:EX.EXSTDAT')"
     "-[:SPEC_RELATIONSHIP]->{1,3}(v:SpecNode WHERE v.NodeType = 'SDTMVariable') "
     "RETURN v.DisplayNameZh AS 受影响变量, size(edges(p)) AS 跳数 "
     "ORDER BY 跳数 DESC LIMIT 10;"),
]


def main() -> None:
    state = load_state(STATE)
    ws_id = state["workspace_id"]
    parts = build_parts(state)

    graph_id = find_item(ws_id, GRAPH_NAME, "GraphModel")
    if graph_id:
        status, payload, headers = call(
            "POST", f"{FABRIC}/v1/workspaces/{ws_id}/items/{graph_id}/updateDefinition",
            {"definition": {"parts": parts}})
        if status == 202:
            wait_lro(headers, "更新图模型")
        elif status != 200:
            raise RuntimeError(f"更新图模型失败: {err(payload)}")
    else:
        status, payload, headers = call(
            "POST", f"{FABRIC}/v1/workspaces/{ws_id}/graphModels",
            {"displayName": GRAPH_NAME, "definition": {"parts": parts}})
        if status in (200, 201):
            graph_id = payload["id"]
        elif status == 202:
            wait_lro(headers, "创建图模型")
            graph_id = find_item(ws_id, GRAPH_NAME, "GraphModel")
        else:
            raise RuntimeError(f"创建图模型失败: {err(payload)}")

    state["graph_model_id"] = graph_id
    save_state(state, STATE)
    print(f"图模型 {GRAPH_NAME} -> {graph_id}")
    verify(ws_id, graph_id)

    refresh(ws_id, graph_id)
    wait_until_queryable(ws_id, graph_id, expected_nodes=180)
    for label, gql in SMOKE_TESTS:
        rows = query(ws_id, graph_id, gql)
        print(f"\n-- {label}  返回 {len(rows)} 行")
        for row in rows[:6]:
            print("   ", json.dumps(row, ensure_ascii=False))
        assert rows, f"GQL 冒烟测试无结果: {label}"

    print("\n图模型部署与 GQL 冒烟测试通过。")


if __name__ == "__main__":
    main()
