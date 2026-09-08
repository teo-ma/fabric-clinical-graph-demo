"""Step 4: create the Ontology semantic layer spanning the source lakehouses.

Each entity type binds directly to the system that owns it, so the ontology is a
real cross-system semantic layer rather than a view over one curated table.
"""

from __future__ import annotations

import base64
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fabric_common import (FABRIC, call, err, find_item, load_state,  # noqa: E402
                           save_state, wait_lro)

ONTOLOGY_NAME = "ClinicalDevelopmentOntology"

# name, lakehouse key, source table, key column, display column,
# description, [(property name, source column, value type)]
ENTITY_TYPES = [
    ("Compound", "knowledge", "compounds", "compound_id", "compound_name_zh",
     "在研化合物。制药研发管线中的候选药物，是安全信号、批次与研究的共同锚点。",
     ["候选药物", "研究药物", "化合物"],
     [("CompoundId", "compound_id", "String"),
      ("CompoundCode", "compound_code", "String"),
      ("CompoundNameZh", "compound_name_zh", "String"),
      ("Modality", "modality", "String"),
      ("PrimaryTargetId", "primary_target_id", "String"),
      ("DevelopmentPhase", "dev_phase", "String")]),

    ("Study", "ctms", "studies", "study_id", "protocol_no",
     "临床研究。一个方案编号对应一项在研临床试验。",
     ["临床试验", "研究", "方案"],
     [("StudyId", "study_id", "String"),
      ("ProtocolNo", "protocol_no", "String"),
      ("CompoundId", "compound_id", "String"),
      ("Phase", "phase", "String"),
      ("IndicationZh", "indication_zh", "String"),
      ("StudyStatus", "study_status", "String")]),

    ("Site", "ctms", "sites", "site_id", "site_name_zh",
     "研究中心。承担受试者入组与给药的临床机构。",
     ["中心", "研究机构", "站点"],
     [("SiteId", "site_id", "String"),
      ("SiteNameZh", "site_name_zh", "String"),
      ("StudyId", "study_id", "String"),
      ("Country", "country", "String"),
      ("City", "city", "String"),
      ("SiteStatus", "site_status", "String")]),

    ("Subject", "ctms", "subjects", "subject_id", "subject_id",
     "受试者。参加临床研究的个体，本演示中均为合成记录，不含任何真实个人信息。",
     ["病人", "患者", "入组对象"],
     [("SubjectId", "subject_id", "String"),
      ("StudyId", "study_id", "String"),
      ("SiteId", "site_id", "String"),
      ("TreatmentArm", "treatment_arm", "String"),
      ("AgeGroup", "age_group", "String"),
      ("SubjectStatus", "subject_status", "String")]),

    ("AdverseEvent", "safety", "adverse_events", "ae_id", "pt_code",
     "不良事件。受试者在研究期间发生的医学事件，严重性与因果关系由药物警戒判定。",
     ["AE", "不良反应", "安全性事件"],
     [("AdverseEventId", "ae_id", "String"),
      ("SubjectId", "subject_id", "String"),
      ("PtCode", "pt_code", "String"),
      ("SeriousFlag", "serious_flag", "String"),
      ("CtcaeGrade", "ctcae_grade", "BigInt"),
      ("CausalityZh", "causality_zh", "String"),
      ("OutcomeZh", "outcome_zh", "String")]),

    ("SafetySignal", "safety", "safety_signals", "signal_id", "pt_code",
     "安全信号。针对某个化合物与某个不良事件术语的潜在风险，需要证据支持与评估结论。",
     ["信号", "风险信号", "安全性信号"],
     [("SignalId", "signal_id", "String"),
      ("CompoundId", "compound_id", "String"),
      ("PtCode", "pt_code", "String"),
      ("SignalStatusZh", "signal_status_zh", "String"),
      ("EvidenceGrade", "evidence_grade", "String")]),

    ("Batch", "supply", "batches", "batch_id", "batch_id",
     "药品批次。临床供应的生产批次，是质量事件溯源的起点。",
     ["批号", "生产批次", "供应批次"],
     [("BatchId", "batch_id", "String"),
      ("CompoundId", "compound_id", "String"),
      ("QcStatusZh", "qc_status_zh", "String")]),

    ("LabResult", "lims", "lab_results", "lab_id", "biomarker_id",
     "实验室检验结果。中心实验室对生物标志物的一次测量，异常值是安全信号的客观证据。",
     ["化验结果", "检验值", "实验室数据"],
     [("LabId", "lab_id", "String"),
      ("SubjectId", "subject_id", "String"),
      ("BiomarkerId", "biomarker_id", "String"),
      ("AbnormalFlag", "abnormal_flag", "String"),
      ("Unit", "unit", "String")]),
]

# name, source entity, target entity, lakehouse key, table,
# source column, target column, description
RELATIONSHIP_TYPES = [
    ("enrolledInStudy", "Subject", "Study", "ctms", "subjects",
     "subject_id", "study_id", "受试者入组于某项临床研究。"),
    ("treatedAtSite", "Subject", "Site", "ctms", "subjects",
     "subject_id", "site_id", "受试者在某研究中心接受治疗与随访。"),
    ("siteBelongsToStudy", "Site", "Study", "ctms", "sites",
     "site_id", "study_id", "研究中心隶属于某项临床研究。"),
    ("studyEvaluatesCompound", "Study", "Compound", "ctms", "studies",
     "study_id", "compound_id", "临床研究评价某个在研化合物。"),
    ("subjectExperiencedEvent", "Subject", "AdverseEvent", "safety", "adverse_events",
     "subject_id", "ae_id", "受试者发生了某个不良事件。"),
    ("eventSupportsSignal", "AdverseEvent", "SafetySignal", "safety", "ae_signal_links",
     "ae_id", "signal_id", "不良事件构成某个安全信号的证据。"),
    ("signalAboutCompound", "SafetySignal", "Compound", "safety", "safety_signals",
     "signal_id", "compound_id", "安全信号针对某个在研化合物。"),
    ("batchOfCompound", "Batch", "Compound", "supply", "batches",
     "batch_id", "compound_id", "药品批次属于某个在研化合物。"),
    ("labResultOfSubject", "LabResult", "Subject", "lims", "lab_results",
     "lab_id", "subject_id", "实验室检验结果属于某位受试者。"),
]


def build_parts(state: dict) -> list[dict]:
    ws_id = state["workspace_id"]
    lh = state["lakehouses"]
    files: dict[str, dict] = {"definition.json": {}}

    entity_ids: dict[str, str] = {}
    entity_key_prop: dict[str, str] = {}

    for n, (name, lh_key, table, key_col, display_col, desc, synonyms, props) in \
            enumerate(ENTITY_TYPES, start=1):
        entity_id = f"9001{n:09d}"
        entity_ids[name] = entity_id

        properties, prop_ids = [], {}
        for p, (prop_name, column, value_type) in enumerate(props, start=1):
            prop_id = f"9001{(n * 1000 + p):09d}"
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
                    "sourceSystem": lh_key,
                    "sourceTable": table,
                    "dataClassification": "Synthetic",
                    "containsPHI": "false",
                },
            },
            "properties": properties,
            "timeseriesProperties": [],
        }

        files[f"EntityTypes/{entity_id}/DataBindings/{uuid.uuid5(uuid.NAMESPACE_DNS, name)}.json"] = {
            "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, name)),
            "dataBindingConfiguration": {
                "dataBindingType": "NonTimeSeries",
                "propertyBindings": [
                    {"sourceColumnName": column, "targetPropertyId": prop_ids[column]}
                    for column, _ in [(c, t) for _, c, t in props]
                ],
                "sourceTableProperties": {
                    "sourceType": "LakehouseTable",
                    "workspaceId": ws_id,
                    "itemId": lh[lh_key],
                    "sourceTableName": table,
                },
            },
        }

    for n, (name, source, target, lh_key, table, src_col, tgt_col, desc) in \
            enumerate(RELATIONSHIP_TYPES, start=1):
        rel_id = f"9002{n:09d}"
        files[f"RelationshipTypes/{rel_id}/definition.json"] = {
            "namespace": "usertypes",
            "id": rel_id,
            "name": name,
            "namespaceType": "Custom",
            "source": {"entityTypeId": entity_ids[source]},
            "target": {"entityTypeId": entity_ids[target]},
            "semanticEnrichment": {
                "description": desc,
                "customAttributes": {"sourceSystem": lh_key, "sourceTable": table},
            },
        }
        ctx_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"rel-{name}"))
        files[f"RelationshipTypes/{rel_id}/Contextualizations/{ctx_id}.json"] = {
            "id": ctx_id,
            "dataBindingTable": {
                "workspaceId": ws_id,
                "itemId": lh[lh_key],
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


def main() -> None:
    state = load_state()
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
    save_state(state)
    print(f"已导入 {len(parts)} 个定义文件："
          f"{len(ENTITY_TYPES)} 个实体类型，{len(RELATIONSHIP_TYPES)} 个关系类型")

    bound = {e[1] for e in ENTITY_TYPES}
    print(f"实体绑定覆盖源系统: {'、'.join(sorted(bound))}")


if __name__ == "__main__":
    main()
