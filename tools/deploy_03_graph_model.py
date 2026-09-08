"""Step 3: create the Fabric Graph model over the unified clinical graph tables.

The graph item uses the graphIndex definition file set. Writing a definition with
the wrong file names is accepted by the service but leaves an empty model, so the
script reads the definition back and fails loudly if the node types are missing.
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fabric_common import (FABRIC, call, err, find_item, load_state,  # noqa: E402
                           save_state, wait_lro)

GRAPH_NAME = "ClinicalKnowledgeGraph"
SCHEMA_BASE = "https://developer.microsoft.com/json-schemas/fabric/item/graphIndex/definition"

NODE_ALIAS = "ClinicalNode_nodeType"
EDGE_ALIAS = "ClinicalRelationship_edgeType"

NODE_PROPERTIES = [
    ("NodeId", "node_id", "STRING"),
    ("NodeType", "node_type", "STRING"),
    ("NodeTypeZh", "node_type_zh", "STRING"),
    ("DisplayNameZh", "display_name_zh", "STRING"),
    ("SourceSystem", "source_system", "STRING"),
    ("StudyId", "study_id", "STRING"),
    ("Category", "category", "STRING"),
    ("Status", "status", "STRING"),
    ("NumericValue", "numeric_value", "FLOAT"),
    ("EventDate", "event_date", "STRING"),
    ("DataVersion", "data_version", "INT"),
]

EDGE_PROPERTIES = [
    ("EdgeId", "edge_id", "STRING"),
    ("RelationshipType", "relationship_type", "STRING"),
    ("RelationshipTypeZh", "relationship_type_zh", "STRING"),
    ("EvidenceGrade", "evidence_grade", "STRING"),
    ("Confidence", "confidence", "FLOAT"),
    ("ClinicalCost", "clinical_cost", "FLOAT"),
    ("EdgeClass", "edge_class", "STRING"),
    ("SourceSystem", "source_system", "STRING"),
    ("DataVersion", "data_version", "INT"),
]


def build_parts(state: dict) -> list[dict]:
    ws_id = state["workspace_id"]
    curated = state["lakehouses"]["curated"]

    graph_type = {
        "$schema": f"{SCHEMA_BASE}/graphType/1.0.0/schema.json",
        "nodeTypes": [{
            "primaryKeyProperties": ["NodeId"],
            "alias": NODE_ALIAS,
            "labels": ["ClinicalNode"],
            "properties": [{"name": n, "type": t} for n, _, t in NODE_PROPERTIES],
        }],
        "edgeTypes": [{
            "alias": EDGE_ALIAS,
            "sourceNodeType": {"alias": NODE_ALIAS},
            "labels": ["CLINICAL_RELATIONSHIP"],
            "destinationNodeType": {"alias": NODE_ALIAS},
            "properties": [{"name": n, "type": t} for n, _, t in EDGE_PROPERTIES],
        }],
    }

    data_sources = {
        "$schema": f"{SCHEMA_BASE}/dataSources/1.1.0/schema.json",
        "itemReferences": [{
            "name": "CuratedLakehouseRef",
            "item": {"workspaceId": ws_id, "itemId": curated},
        }],
        "dataSources": [
            {"name": "GraphNodesTable", "type": "DeltaTable",
             "properties": {"referenceName": "CuratedLakehouseRef",
                            "path": "Tables/graph_nodes"}},
            {"name": "GraphEdgesTable", "type": "DeltaTable",
             "properties": {"referenceName": "CuratedLakehouseRef",
                            "path": "Tables/graph_edges"}},
        ],
    }

    graph_definition = {
        "$schema": f"{SCHEMA_BASE}/graphDefinition/1.0.0/schema.json",
        "nodeTables": [{
            "nodeTypeAlias": NODE_ALIAS,
            "id": "ClinicalNode_table",
            "dataSourceName": "GraphNodesTable",
            "propertyMappings": [{"propertyName": n, "sourceColumn": c}
                                 for n, c, _ in NODE_PROPERTIES],
        }],
        "edgeTables": [{
            "edgeTypeAlias": EDGE_ALIAS,
            "id": "ClinicalRelationship_table",
            "edgeIdMapping": None,
            "dataSourceName": "GraphEdgesTable",
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
                         "color": "#277DA1", "shape": "Circle"},
            EDGE_ALIAS: {"defaultDisplayProperty": "RelationshipTypeZh",
                         "color": "#2A9D8F", "shape": None},
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
                         "description": "跨六个源系统的统一临床知识图谱，支持原生 GQL 多跳查询。合成数据。"},
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


def main() -> None:
    state = load_state()
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
    save_state(state)
    print(f"图模型 {GRAPH_NAME} -> {graph_id}")
    verify(ws_id, graph_id)


if __name__ == "__main__":
    main()
