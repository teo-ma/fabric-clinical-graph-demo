"""Lineage demo step 3: Ontology over the CDISC concepts behind the mapping spec.

An ontology earns its place here more clearly than in a single-company data model:
SDTM domains, variables and controlled terminology are an internationally agreed
vocabulary, so naming the concepts once lets a question phrased in business terms
("受试者的处置结论") resolve to the right standard object without the asker knowing
the domain code.
"""

from __future__ import annotations

import base64
import json
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fabric_common import (FABRIC, call, err, find_item, load_state,  # noqa: E402
                           save_state, wait_lro)

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "fabric" / "lineage_deployment_state.json"
ONTOLOGY_NAME = "ClinicalDataStandardOntology"

# name, source table, key column, display column, description, synonyms,
# [(property name, source column, value type)]
ENTITY_TYPES = [
    ("CRFForm", "crf_forms_current", "form_oid", "form_name_zh",
     "CRF 表单。研究中心录入数据的一页表单，是临床数据进入系统的第一站。",
     ["表单", "病例报告表", "采集表", "eCRF"],
     [("FormOid", "form_oid", "String"),
      ("FormNameZh", "form_name_zh", "String"),
      ("FormNameEn", "form_name_en", "String"),
      ("Page", "page", "String"),
      ("Version", "version", "String")]),

    ("CRFField", "crf_fields_current", "field_uid", "field_label_zh",
     "CRF 字段。表单上的一个录入项，是所有下游标准数据集的原始来源。",
     ["采集字段", "录入项", "表单字段", "题目"],
     [("FieldUid", "field_uid", "String"),
      ("FormOid", "form_oid", "String"),
      ("FieldOid", "field_oid", "String"),
      ("FieldLabelZh", "field_label_zh", "String"),
      ("FieldType", "field_type", "String"),
      ("Codelist", "codelist", "String"),
      ("AcrfPage", "acrf_page", "String")]),

    ("SDTMDomain", "sdtm_domains", "domain", "domain_label_zh",
     "SDTM 域。CDISC 标准中按主题划分的数据集，例如 AE 不良事件、DM 人口学。",
     ["数据集", "标准域", "SDTM 数据集", "提交数据集"],
     [("Domain", "domain", "String"),
      ("DomainLabelZh", "domain_label_zh", "String"),
      ("ObservationClass", "observation_class", "String"),
      ("IsSupplemental", "is_supplemental", "String"),
      ("ParentDomain", "parent_domain", "String")]),

    ("SDTMVariable", "sdtm_variables_keyed", "variable_uid", "variable_label_zh",
     "SDTM 变量。标准数据集中的一列，Core 标注它是必填、预期还是可选。",
     ["标准变量", "提交变量", "SDTM 字段", "列"],
     [("VariableUid", "variable_uid", "String"),
      ("Domain", "domain", "String"),
      ("VariableName", "variable_name", "String"),
      ("VariableLabelZh", "variable_label_zh", "String"),
      ("Core", "core", "String"),
      ("DataType", "data_type", "String"),
      ("Codelist", "codelist", "String"),
      ("ExpectedOrigin", "expected_origin", "String")]),

    ("MappingRule", "mapping_rules_current", "rule_id", "annotation_text",
     "映射规则。把一个 CRF 字段转换成一个 SDTM 变量的具体做法，"
     "算法说明了这次转换需要多少解释。",
     ["映射", "转换规则", "标注", "annotation"],
     [("RuleId", "rule_id", "String"),
      ("FieldUid", "field_uid", "String"),
      ("VariableUid", "variable_uid", "String"),
      ("Algorithm", "algorithm", "String"),
      ("ConditionZh", "condition_zh", "String"),
      ("Qnam", "qnam", "String"),
      ("AnnotationText", "annotation_text", "String"),
      ("Version", "version", "String")]),

    ("Codelist", "codelists", "codelist", "codelist",
     "受控术语集。限定某个变量只能取标准取值的字典，是跨研究可比性的基础。",
     ["值域", "受控术语", "码表", "CT"],
     [("CodelistName", "codelist", "String"),
      ("TermCount", "term_count", "BigInt")]),

    ("ControlledTerm", "controlled_terms_keyed", "term_uid", "decode_zh",
     "受控术语。术语集中的一个标准取值及其中文解释。",
     ["术语", "标准取值", "码值"],
     [("TermUid", "term_uid", "String"),
      ("CodelistName", "codelist", "String"),
      ("SubmissionValue", "submission_value", "String"),
      ("DecodeZh", "decode_zh", "String")]),
]

# name, source entity, target entity, table, source column, target column, description
RELATIONSHIP_TYPES = [
    ("fieldBelongsToForm", "CRFField", "CRFForm", "crf_fields_current",
     "field_uid", "form_oid", "CRF 字段属于某张表单。"),
    ("variableBelongsToDomain", "SDTMVariable", "SDTMDomain", "sdtm_variables_keyed",
     "variable_uid", "domain", "SDTM 变量属于某个标准域。"),
    ("ruleReadsField", "MappingRule", "CRFField", "mapping_rules_current",
     "rule_id", "field_uid", "映射规则从某个 CRF 字段取值。"),
    ("ruleWritesVariable", "MappingRule", "SDTMVariable", "mapping_rules_current",
     "rule_id", "variable_uid", "映射规则写入某个 SDTM 变量。"),
    ("variableUsesCodelist", "SDTMVariable", "Codelist", "sdtm_variables_keyed",
     "variable_uid", "codelist", "SDTM 变量的取值受某个术语集约束。"),
    ("termInCodelist", "ControlledTerm", "Codelist", "controlled_terms_keyed",
     "term_uid", "codelist", "受控术语属于某个术语集。"),
]


def build_parts(state: dict) -> list[dict]:
    ws_id = state["workspace_id"]
    spec = state["lakehouses"]["spec"]
    files: dict[str, dict] = {"definition.json": {}}

    entity_ids: dict[str, str] = {}
    entity_key_prop: dict[str, str] = {}

    for n, (name, table, key_col, display_col, desc, synonyms, props) in \
            enumerate(ENTITY_TYPES, start=1):
        entity_id = f"9101{n:09d}"
        entity_ids[name] = entity_id

        properties, prop_ids = [], {}
        for p, (prop_name, column, value_type) in enumerate(props, start=1):
            prop_id = f"9101{(n * 1000 + p):09d}"
            prop_ids[column] = prop_id
            properties.append({
                "id": prop_id,
                "name": prop_name,
                "redefines": None,
                "baseTypeNamespaceType": None,
                "valueType": value_type,
            })

        entity_key_prop[name] = prop_ids[key_col]
        files[f"EntityTypes/{entity_id}/definition.json"] = {
            "id": entity_id,
            "namespace": "usertypes",
            "baseEntityTypeId": None,
            "name": name,
            "entityIdParts": [prop_ids[key_col]],
            "displayNamePropertyId": prop_ids[display_col],
            "namespaceType": "Custom",
            "visibility": "Visible",
            "semanticEnrichment": {
                "description": desc,
                "synonyms": synonyms,
                "customAttributes": {
                    "standard": "CDISC SDTM 风格（示意）",
                    "sourceTable": table,
                    "dataClassification": "Synthetic",
                    "containsPHI": "false",
                },
            },
            "properties": properties,
            "timeseriesProperties": [],
        }

        binding_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"lineage-{name}"))
        files[f"EntityTypes/{entity_id}/DataBindings/{binding_id}.json"] = {
            "id": binding_id,
            "dataBindingConfiguration": {
                "dataBindingType": "NonTimeSeries",
                "propertyBindings": [
                    {"sourceColumnName": column, "targetPropertyId": prop_ids[column]}
                    for _, column, _ in props
                ],
                "sourceTableProperties": {
                    "sourceType": "LakehouseTable",
                    "workspaceId": ws_id,
                    "itemId": spec,
                    "sourceTableName": table,
                },
            },
        }

    for n, (name, source, target, table, src_col, tgt_col, desc) in \
            enumerate(RELATIONSHIP_TYPES, start=1):
        rel_id = f"9102{n:09d}"
        files[f"RelationshipTypes/{rel_id}/definition.json"] = {
            "namespace": "usertypes",
            "id": rel_id,
            "name": name,
            "namespaceType": "Custom",
            "source": {"entityTypeId": entity_ids[source]},
            "target": {"entityTypeId": entity_ids[target]},
            "semanticEnrichment": {
                "description": desc,
                "customAttributes": {"sourceTable": table},
            },
        }
        ctx_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"lineage-rel-{name}"))
        files[f"RelationshipTypes/{rel_id}/Contextualizations/{ctx_id}.json"] = {
            "id": ctx_id,
            "dataBindingTable": {
                "workspaceId": ws_id,
                "itemId": spec,
                "sourceTableName": table,
                "sourceType": "LakehouseTable",
            },
            "sourceKeyRefBindings": [
                {"sourceColumnName": src_col, "targetPropertyId": entity_key_prop[source]}],
            "targetKeyRefBindings": [
                {"sourceColumnName": tgt_col, "targetPropertyId": entity_key_prop[target]}],
        }

    return [{"path": path,
             "payload": base64.b64encode(
                 json.dumps(obj, ensure_ascii=False, indent=2).encode()).decode(),
             "payloadType": "InlineBase64"}
            for path, obj in files.items()]


def companion_graph(ws_id: str, ontology_id: str) -> str:
    """Find the GraphModel the service auto-creates to back the ontology.

    Importing a definition is not enough to make an ontology answerable: the
    entities live in a companion GraphModel named
    "<ontology>_graph_<ontologyIdWithoutDashes>", and until that index is
    refreshed every query fails with "The Graph Model is not ready". The Data
    Agent hides this by silently falling back to the model's general knowledge,
    so the ontology looks like it works while answering from nothing.
    """
    expected = f"{ONTOLOGY_NAME}_graph_{ontology_id.replace('-', '')}"
    graph_id = find_item(ws_id, expected, "GraphModel")
    if not graph_id:
        raise RuntimeError(f"未找到本体配套图模型 {expected}")
    return graph_id


def refresh_companion_graph(ws_id: str, graph_id: str) -> None:
    status, payload, headers = call(
        "POST", f"{FABRIC}/v1/workspaces/{ws_id}/items/{graph_id}/jobs/instances"
                "?jobType=RefreshGraph", {"executionData": {}})
    if status not in (200, 202):
        raise RuntimeError(f"触发本体索引刷新失败: {err(payload)}")
    location = headers.get("Location") or headers.get("location")
    if not location:
        return
    deadline = time.time() + 1800
    last = ""
    while time.time() < deadline:
        _, payload, _ = call("GET", location)
        state = (payload or {}).get("status", "")
        if state != last:
            print(f"  本体索引 {state}")
            last = state
        if state in ("Completed", "Succeeded", "Deduped"):
            return
        if state in ("Failed", "Cancelled"):
            raise RuntimeError(f"本体索引刷新失败: {payload.get('failureReason') or payload}")
        time.sleep(15)
    raise TimeoutError("本体索引刷新超时")


def verify_instantiated(ws_id: str, graph_id: str) -> None:
    """Prove the ontology actually has instances, not just type definitions."""
    checks = [
        ("实体总数", "MATCH (n) RETURN count(*) AS v;", 200),
        ("SDTM 变量", "MATCH (n:SDTMVariable) RETURN count(*) AS v;", 90),
        ("CRF 字段", "MATCH (n:CRFField) RETURN count(*) AS v;", 50),
    ]
    for label, gql, minimum in checks:
        status, payload, _ = call(
            "POST", f"{FABRIC}/v1/workspaces/{ws_id}/GraphModels/{graph_id}"
                    "/executeQuery?preview=true", {"query": gql})
        code = (payload.get("status") or {}).get("code")
        if status != 200 or code not in ("00000", None):
            raise RuntimeError(f"本体查询失败 {label}: {json.dumps(payload)[:300]}")
        rows = (payload.get("result") or {}).get("data") or []
        count = int(next(iter(rows[0].values()))) if rows else 0
        print(f"  {label} {count}")
        assert count >= minimum, f"{label} 只有 {count}，本体未正确实例化"

    status, payload, _ = call(
        "POST", f"{FABRIC}/v1/workspaces/{ws_id}/GraphModels/{graph_id}"
                "/executeQuery?preview=true",
        {"query": "MATCH (v:SDTMVariable)-[]->(c:Codelist) "
                  "RETURN v.VariableName AS 变量, c.CodelistName AS 术语集 LIMIT 3;"})
    rows = (payload.get("result") or {}).get("data") or []
    assert rows, "本体关系未实例化：变量与术语集之间查不到连接"
    print(f"  关系抽样 {json.dumps(rows, ensure_ascii=False)}")


def verify(ws_id: str, ontology_id: str) -> None:
    status, payload, headers = call(
        "POST", f"{FABRIC}/v1/workspaces/{ws_id}/items/{ontology_id}/getDefinition")
    if status == 202:
        payload = wait_lro(headers, "回读本体定义")
    paths = [p["path"] for p in payload.get("definition", {}).get("parts", [])]
    entities = [p for p in paths if p.startswith("EntityTypes/") and p.endswith("definition.json")]
    relations = [p for p in paths if p.startswith("RelationshipTypes/") and p.endswith("definition.json")]
    bindings = [p for p in paths if "DataBindings/" in p]
    if len(entities) != len(ENTITY_TYPES) or len(relations) != len(RELATIONSHIP_TYPES):
        raise RuntimeError(f"本体回读不完整：实体 {len(entities)}，关系 {len(relations)}")
    print(f"回读校验通过：实体 {len(entities)} 个，关系 {len(relations)} 个，"
          f"数据绑定 {len(bindings)} 个")


def main() -> None:
    state = load_state(STATE)
    ws_id = state["workspace_id"]

    ontology_id = find_item(ws_id, ONTOLOGY_NAME, "Ontology")
    if not ontology_id:
        status, payload, headers = call(
            "POST", f"{FABRIC}/v1/workspaces/{ws_id}/items",
            {"displayName": ONTOLOGY_NAME, "type": "Ontology"})
        if status in (200, 201):
            ontology_id = payload["id"]
        elif status == 202:
            wait_lro(headers, "创建本体")
            ontology_id = find_item(ws_id, ONTOLOGY_NAME, "Ontology")
        else:
            raise RuntimeError(f"创建本体失败: {err(payload)}")
        print(f"已创建本体 {ontology_id}")
    else:
        print(f"复用本体 {ontology_id}")

    parts = build_parts(state)
    status, payload, headers = call(
        "POST", f"{FABRIC}/v1/workspaces/{ws_id}/items/{ontology_id}/updateDefinition",
        {"definition": {"parts": parts}})
    if status == 202:
        wait_lro(headers, "导入本体定义")
    elif status != 200:
        raise RuntimeError(f"导入本体定义失败: {err(payload)}")

    state["ontology_id"] = ontology_id
    save_state(state, STATE)
    print(f"已导入 {len(parts)} 个定义文件："
          f"{len(ENTITY_TYPES)} 个实体类型，{len(RELATIONSHIP_TYPES)} 个关系类型")
    verify(ws_id, ontology_id)

    # 定义导入只建了类型，实例要等配套图索引刷新完才能查。
    graph_id = companion_graph(ws_id, ontology_id)
    state["ontology_graph_id"] = graph_id
    save_state(state, STATE)
    print(f"本体配套图模型 -> {graph_id}")
    refresh_companion_graph(ws_id, graph_id)
    verify_instantiated(ws_id, graph_id)
    print("本体已实例化并可查询。")


if __name__ == "__main__":
    main()
