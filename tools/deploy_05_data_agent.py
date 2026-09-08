"""Step 5: create and publish the Chinese-language Fabric Data Agent.

The Data Agent definition follows the exact Files/Config layout the service
expects: a draft stage, an identical published stage, and a publish_info file.
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fabric_common import (FABRIC, call, err, find_item, load_state,  # noqa: E402
                           save_state, wait_lro)
from agent_graph_sources import (GRAPH_DESCRIPTION, GRAPH_FEW_SHOTS,  # noqa: E402
                                 GRAPH_INSTRUCTIONS, GRAPH_NAME,
                                 ONTOLOGY_DESCRIPTION, ONTOLOGY_NAME)

AGENT_NAME = "ClinicalInsightAgent"
LAKEHOUSE_DISPLAY = "LH_Curated_统一临床图谱"

SCHEMA_BASE = "https://developer.microsoft.com/json-schemas/fabric/item/dataAgent/definition"

AI_INSTRUCTIONS = """你是面向制药企业临床开发团队的中文数据助手。数据来自六个源系统统一而成的临床知识图谱，全部为合成数据。

回答规则：
一、一律使用简体中文，业务编号如 SYN-101、BATCH-007、SIG-002 保持原样。
二、只依据结果表回答，不要自行推断因果关系，不要给出医学建议。
三、机制类问题查询 dbo.gold_mechanism_paths，按 total_evidence_penalty 升序，is_best_path 为 true 的是证据最强链路，必须同时说明最差证据等级 worst_evidence_grade 与最低置信度 min_confidence。向用户描述时称之为“证据折损”，并说明它是衡量不确定度的无量纲指标，与费用或预算无关。
四、批次质量事件溯源查询 dbo.gold_batch_impact，需给出受影响中心与受试者数量，并单独列出 serious_flag 为“是”的严重不良事件。
五、安全信号问题查询 dbo.gold_signal_evidence，需说明关联不良事件数、严重事件数、受影响受试者与中心数量、支持性异常检验数量，并给出最优机制路径。
六、共享靶点或通路的风险外推查询 dbo.gold_target_crosstalk；研究中心风险画像查询 dbo.gold_site_risk。
七、业务编号映射：SYN-101 为 CMP-001，SYN-102 为 CMP-002，SYN-201 为 CMP-003，SYN-301 为 CMP-004，SYN-401 为 CMP-005；药物性肝损伤为 PT-DILI，QT间期延长为 PT-QTP，血小板减少症为 PT-THROM，中性粒细胞减少症为 PT-NEUT。
八、当用户问“最佳”“风险最高”这类含糊口径时，先说明判定依据再给结论。
九、数据源选择规则：
    ① 上述五类已预先计算的业务问题，优先使用统一临床图谱 Lakehouse 的 gold_ 结果表。
    ② 当用户提出结果表未覆盖的关系探索问题，例如任意两个实体之间怎么连通、
       某个节点往外几跳能触及哪些对象、图上各类节点或跨系统连接的统计，
       使用图数据源 ClinicalKnowledgeGraph 写 GQL 查询。
    ③ 当用户询问业务概念的定义、属性或概念之间的关系，使用本体数据源
       ClinicalDevelopmentOntology。
    ④ 回答时说明本次结论来自哪个数据源，以及使用的是 SQL 还是 GQL。
十、每次回答结尾提示：本结果基于合成演示数据，不构成任何真实医学或用药结论。"""

DATASOURCE_INSTRUCTIONS = """本 Lakehouse 存放跨六个源系统统一而成的临床知识图谱与业务结果表。

优先使用 gold_ 开头的结果表回答业务问题，不要从 graph_edges 自行推导路径。
graph_nodes 与 graph_edges 用于展示图规模与跨系统连接，node_type 区分实体类别，edge_class 区分“知识”边与“运营”边，evidence_penalty 为证据折损，数值越小证据越强。该值是无量纲的不确定度权重，不是金额。"""

TABLES: dict[str, tuple[str, list[tuple[str, str]]]] = {
    "gold_mechanism_paths": (
        "化合物到不良事件术语的机制解释链路，每个组合按证据折损排序。",
        [("compound_id", "化合物编号，如 CMP-001。"),
         ("compound_name_zh", "化合物中文名，如 研究化合物 SYN-101。"),
         ("ae_pt_code", "不良事件术语编号，如 PT-DILI。"),
         ("ae_pt_name_zh", "不良事件中文名，如 药物性肝损伤。"),
         ("path_rank", "同一组合下按证据折损升序的排名，1 为证据最强。"),
         ("is_best_path", "是否为该组合下证据最强的链路。"),
         ("path_display_zh", "中文机制链路，形如 化合物 -> 靶点 -> 通路 -> 生物标志物 -> 不良事件。"),
         ("hop_count", "链路跳数。"),
         ("total_evidence_penalty", "证据折损合计，越小证据越强。无量纲，与费用无关。"),
         ("worst_evidence_grade", "链路中最差的证据等级。"),
         ("min_confidence", "链路中最低的置信度。")]),
    "gold_batch_impact": (
        "药品批次温度偏移的影响溯源，从批次经运单、研究中心到受试者与不良事件。",
        [("batch_id", "药品批次号，如 BATCH-007。"),
         ("shipment_id", "运单号。"),
         ("site_name_zh", "接收该批次的研究中心中文名。"),
         ("subject_id", "使用该批次的受试者编号。"),
         ("ae_pt_name_zh", "该受试者发生的不良事件中文名。"),
         ("serious_flag", "是否为严重不良事件，取值 是 或 否。"),
         ("ctcae_grade", "CTCAE 分级，数值越大越严重。"),
         ("causality_zh", "与研究药物的因果关系判定。"),
         ("impact_path_zh", "完整影响链路的中文表述。")]),
    "gold_signal_evidence": (
        "每个安全信号的证据汇总，包含受影响范围与最优机制解释。",
        [("signal_id", "安全信号编号，如 SIG-002。"),
         ("compound_name_zh", "信号针对的化合物中文名。"),
         ("ae_pt_name_zh", "信号对应的不良事件中文名。"),
         ("signal_status_zh", "信号状态，如 评估中、已确认。"),
         ("linked_ae_count", "关联的不良事件数量。"),
         ("serious_ae_count", "其中严重不良事件数量。"),
         ("affected_subject_count", "涉及受试者数量。"),
         ("affected_site_count", "涉及研究中心数量。"),
         ("supporting_abnormal_lab_count", "支持该信号的异常实验室检验数量。"),
         ("supporting_biomarkers_zh", "相关生物标志物中文名。"),
         ("best_mechanism_path_zh", "证据最强的机制解释链路。")]),
    "gold_target_crosstalk": (
        "共享靶点或生物通路的化合物组合，用于风险外推。",
        [("compound_a_name_zh", "化合物 A 中文名。"),
         ("compound_b_name_zh", "化合物 B 中文名。"),
         ("shared_targets_zh", "共享靶点中文名。"),
         ("shared_pathways_zh", "共享生物通路中文名。"),
         ("shared_risk_terms_zh", "可能共享的不良事件风险。"),
         ("compound_b_studies", "化合物 B 的在研研究方案号。")]),
    "gold_site_risk": (
        "研究中心运营与安全风险画像。",
        [("site_name_zh", "研究中心中文名。"),
         ("country", "所在国家。"),
         ("investigator_name", "主要研究者姓名。"),
         ("subject_count", "该中心受试者数量。"),
         ("serious_ae_count", "严重不良事件数量。"),
         ("important_deviation_count", "重要方案偏离数量。"),
         ("temperature_excursion_count", "温度偏移运单数量。"),
         ("risk_score", "综合风险分值，越高风险越大。"),
         ("risk_tier_zh", "风险等级，取值 高风险、中风险、低风险。")]),
    "gold_question_catalog": (
        "示例业务问题与对应结果表，仅用于理解演示意图。",
        [("question_id", "问题编号。"),
         ("category_zh", "问题类别。"),
         ("question_zh", "中文业务问题。"),
         ("answer_table", "回答该问题应使用的结果表。")]),
    "graph_nodes": (
        "统一图谱节点，覆盖六个源系统的所有业务实体。",
        [("node_id", "节点编号。"),
         ("node_type_zh", "节点类别中文名，如 受试者、不良事件、药品批次。"),
         ("display_name_zh", "节点中文显示名。"),
         ("source_system", "该节点来自哪个源系统。")]),
    "graph_edges": (
        "统一图谱有向边，跨系统连接各类实体。",
        [("source_node_id", "起点节点编号。"),
         ("target_node_id", "终点节点编号。"),
         ("relationship_type_zh", "关系中文名。"),
         ("edge_class", "边类别，取值 知识 或 运营。"),
         ("evidence_grade", "证据等级。"),
         ("confidence", "置信度。"),
         ("evidence_penalty", "证据折损，越小证据越强。无量纲，与费用无关。"),
         ("source_system", "该边来自哪个源系统。")]),
}

FEW_SHOTS = [
    ("研究化合物 SYN-101 与药物性肝损伤之间有哪些机制通路？哪条证据最强？",
     "SELECT path_display_zh, hop_count, total_evidence_penalty, worst_evidence_grade, "
     "min_confidence, is_best_path FROM dbo.gold_mechanism_paths "
     "WHERE compound_id = 'CMP-001' AND ae_pt_code = 'PT-DILI' ORDER BY path_rank"),
    ("批次 BATCH-007 发生温度偏移，影响了哪些中心和受试者？其中谁发生了严重不良事件？",
     "SELECT site_name_zh, subject_id, ae_pt_name_zh, serious_flag, ctcae_grade, "
     "causality_zh, impact_path_zh FROM dbo.gold_batch_impact "
     "WHERE batch_id = 'BATCH-007' ORDER BY serious_flag DESC, site_name_zh"),
    ("安全信号 SIG-002 的证据链是什么？涉及多少受试者和异常检验？",
     "SELECT signal_id, compound_name_zh, ae_pt_name_zh, signal_status_zh, linked_ae_count, "
     "serious_ae_count, affected_subject_count, affected_site_count, "
     "supporting_abnormal_lab_count, supporting_biomarkers_zh, best_mechanism_path_zh "
     "FROM dbo.gold_signal_evidence WHERE signal_id = 'SIG-002'"),
    ("与 SYN-101 共享靶点或通路的其他化合物有哪些？可能共享哪些风险？",
     "SELECT compound_a_name_zh, compound_b_name_zh, shared_targets_zh, shared_pathways_zh, "
     "shared_risk_terms_zh, compound_b_studies FROM dbo.gold_target_crosstalk "
     "WHERE compound_a = 'CMP-001' OR compound_b = 'CMP-001'"),
    ("哪些研究中心风险最高？分别因为什么？",
     "SELECT site_name_zh, country, subject_count, serious_ae_count, important_deviation_count, "
     "temperature_excursion_count, risk_score, risk_tier_zh FROM dbo.gold_site_risk "
     "ORDER BY risk_score DESC"),
]


def datasource_config(state: dict) -> dict:
    children = []
    for table, (desc, columns) in TABLES.items():
        children.append({
            "id": None, "is_selected": True, "display_name": table,
            "type": "lakehouse_tables.table", "description": desc,
            "children": [{
                "id": None, "is_selected": True, "display_name": name,
                "type": "lakehouse_tables.column", "data_type": "varchar",
                "description": column_desc, "children": [],
            } for name, column_desc in columns],
        })
    return {
        "$schema": f"{SCHEMA_BASE}/dataSource/1.0.0/schema.json",
        "artifactId": state["lakehouses"]["curated"],
        "workspaceId": state["workspace_id"],
        "dataSourceInstructions": DATASOURCE_INSTRUCTIONS,
        "displayName": LAKEHOUSE_DISPLAY,
        "type": "lakehouse",
        "userDescription": "跨六个源系统统一的临床知识图谱与业务结果表。全部为合成数据。",
        "metadata": None,
        "elements": [{
            "id": None, "is_selected": True, "display_name": "dbo",
            "type": "lakehouse_tables.schema",
            "description": "统一临床图谱与业务结果表所在的默认架构。",
            "children": children,
        }],
    }


def graph_datasource(state: dict) -> dict:
    return {
        "$schema": f"{SCHEMA_BASE}/dataSource/1.0.0/schema.json",
        "artifactId": state["graph_model_id"],
        "workspaceId": state["workspace_id"],
        "dataSourceInstructions": GRAPH_INSTRUCTIONS,
        "displayName": GRAPH_NAME,
        "type": "graph",
        "userDescription": GRAPH_DESCRIPTION,
        "metadata": None,
        "elements": [],
    }


def ontology_datasource(state: dict) -> dict:
    return {
        "$schema": f"{SCHEMA_BASE}/dataSource/1.0.0/schema.json",
        "artifactId": state["ontology_id"],
        "workspaceId": state["workspace_id"],
        "dataSourceInstructions": None,
        "displayName": ONTOLOGY_NAME,
        "type": "ontology",
        "userDescription": ONTOLOGY_DESCRIPTION,
        "metadata": None,
        "elements": [],
    }


def build_parts(state: dict, include_ontology: bool) -> list[dict]:
    stage_config = {
        "$schema": f"{SCHEMA_BASE}/stageConfiguration/1.0.0/schema.json",
        "aiInstructions": AI_INSTRUCTIONS,
    }
    lakehouse_fewshots = {
        "$schema": f"{SCHEMA_BASE}/fewShots/1.0.0/schema.json",
        "fewShots": [{"id": f"20000000-0000-4000-8000-{i:012d}",
                      "question": question, "query": query}
                     for i, (question, query) in enumerate(FEW_SHOTS, start=1)],
    }
    graph_fewshots = {
        "$schema": f"{SCHEMA_BASE}/fewShots/1.0.0/schema.json",
        "fewShots": [{"id": f"30000000-0000-4000-8000-{i:012d}",
                      "question": question, "query": query}
                     for i, (question, query) in enumerate(GRAPH_FEW_SHOTS, start=1)],
    }

    lakehouse_folder = f"lakehouse-{LAKEHOUSE_DISPLAY}"
    graph_folder = f"graph-{GRAPH_NAME}"
    ontology_folder = f"ontology-{ONTOLOGY_NAME}"

    files: dict[str, dict] = {
        "Files/Config/data_agent.json": {
            "$schema": f"{SCHEMA_BASE}/dataAgent/2.1.0/schema.json"},
        "Files/Config/publish_info.json": {
            "$schema": f"{SCHEMA_BASE}/publishInfo/1.0.0/schema.json",
            "description": "临床开发跨系统中文智能问数：机制解释、质量溯源、信号评估、"
                           "风险外推、中心画像，并支持图上多跳关系探索。"},
        ".platform": {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/"
                       "platformProperties/2.0.0/schema.json",
            "metadata": {"type": "DataAgent", "displayName": AGENT_NAME,
                         "description": "跨六个源系统的临床开发中文智能问数代理。合成数据。"},
            "config": {"version": "2.0",
                       "logicalId": "00000000-0000-0000-0000-000000000000"}},
    }
    for stage in ("draft", "published"):
        files[f"Files/Config/{stage}/stage_config.json"] = stage_config
        files[f"Files/Config/{stage}/{lakehouse_folder}/datasource.json"] = \
            datasource_config(state)
        files[f"Files/Config/{stage}/{lakehouse_folder}/fewshots.json"] = lakehouse_fewshots
        files[f"Files/Config/{stage}/{graph_folder}/datasource.json"] = graph_datasource(state)
        files[f"Files/Config/{stage}/{graph_folder}/fewshots.json"] = graph_fewshots
        if include_ontology:
            files[f"Files/Config/{stage}/{ontology_folder}/datasource.json"] = \
                ontology_datasource(state)

    return [{"path": path,
             "payload": base64.b64encode(
                 json.dumps(obj, ensure_ascii=False, indent=2).encode()).decode(),
             "payloadType": "InlineBase64"}
            for path, obj in files.items()]


def main() -> None:
    state = load_state()
    ws_id = state["workspace_id"]

    agent_id = find_item(ws_id, AGENT_NAME, "DataAgent")
    if not agent_id:
        status, payload, headers = call(
            "POST", f"{FABRIC}/v1/workspaces/{ws_id}/items",
            {"displayName": AGENT_NAME, "type": "DataAgent"})
        if status in (200, 201):
            agent_id = payload["id"]
        elif status == 202:
            wait_lro(headers, "创建数据代理")
            agent_id = find_item(ws_id, AGENT_NAME, "DataAgent")
        else:
            raise RuntimeError(f"创建数据代理失败: {err(payload)}")
        print(f"已创建数据代理 {agent_id}")

    # The published dataSource schema (1.0.0) does not yet list "ontology" in its
    # type enum, so the ontology source is attempted first and dropped if rejected.
    for include_ontology in (True, False):
        parts = build_parts(state, include_ontology)
        status, payload, headers = call(
            "POST", f"{FABRIC}/v1/workspaces/{ws_id}/items/{agent_id}/updateDefinition",
            {"definition": {"parts": parts}})
        try:
            if status == 202:
                wait_lro(headers, "导入数据代理配置")
            elif status != 200:
                raise RuntimeError(err(payload))
        except Exception as exc:
            if include_ontology:
                print(f"含本体数据源的配置被拒绝，改为不含本体重试。原因: {exc}")
                continue
            raise RuntimeError(f"导入数据代理配置失败: {exc}") from exc
        state["agent_has_ontology_source"] = include_ontology
        break

    state["data_agent_id"] = agent_id
    state["data_agent_mcp"] = (f"{FABRIC}/v1/mcp/workspaces/{ws_id}"
                               f"/dataagents/{agent_id}/agent")
    save_state(state)
    sources = ["Lakehouse（SQL）", "Graph 模型（GQL）"]
    if state.get("agent_has_ontology_source"):
        sources.append("Ontology")
    print(f"已导入 {len(parts)} 个配置文件")
    print(f"数据源：{'、'.join(sources)}")
    print(f"Lakehouse 选入 {len(TABLES)} 张表，SQL 示例 {len(FEW_SHOTS)} 条，"
          f"GQL 示例 {len(GRAPH_FEW_SHOTS)} 条")
    print(f"MCP 端点 {state['data_agent_mcp']}")


if __name__ == "__main__":
    main()
