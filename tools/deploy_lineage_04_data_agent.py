"""Lineage demo step 4: the Chinese-language Data Agent over spec, graph, ontology.

Follows the Files/Config layout the service expects: a draft stage, an identical
published stage, and a publish_info file. The ontology source type is not in the
published dataSource schema enum, so it is attempted first and dropped if rejected.
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fabric_common import (FABRIC, call, err, find_item, load_state,  # noqa: E402
                           save_state, wait_lro)
from deploy_lineage_02_graph import GRAPH_NAME  # noqa: E402
from deploy_lineage_03_ontology import ONTOLOGY_NAME  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "fabric" / "lineage_deployment_state.json"

AGENT_NAME = "ClinicalDataLineageAgent"
LAKEHOUSE_DISPLAY = "LH_Lineage_血缘图谱"

SCHEMA_BASE = "https://developer.microsoft.com/json-schemas/fabric/item/dataAgent/definition"

AI_INSTRUCTIONS = """你是面向临床数据管理与统计编程团队的中文数据助手。数据是一套 CRF 到 SDTM 的映射规范，全部为示意性合成数据，标准名称仅参考公开的 CDISC 命名习惯。

回答规则：
一、一律使用简体中文。SDTM 域名与变量名如 DM.ARMCD、DS.DSDECOD 保持英文原样，后面补一句中文解释。
二、只依据结果表回答，不要自行编造映射规则，也不要给出医学或监管结论。
三、"映射折损"是一个无量纲权重，衡量一次转换需要多少人为解释：直接拷贝最低，条件赋值与编码最高，落在补充限定符域会再加权。它与金额、工时、预算都没有任何关系，回答时必须说明这一点。
四、反向溯源问题查询 dbo.gold_variable_lineage：按 total_mapping_penalty 升序，is_best_path 为 true 的是最直接的来源；source_count 大于 1 说明该变量有多个来源，此时要提醒各来源并非优劣关系，而是由 leading_condition_zh 里的条件区分不同记录。
五、影响分析问题查询 dbo.gold_field_impact：说明受影响的变量数、涉及的域，并用 deepest_path_zh 展示最长的影响链，提醒用户改动需要连带复核这些下游变量。
六、版本对比问题查询 dbo.gold_version_diff：change_type_zh 区分新增、移除与算法变更，算法变更要说明从什么改成了什么。
七、问“哪种转换方式用了多少次”必须查 dbo.gold_algorithm_usage。绝不要拿 gold_variable_lineage 的 algorithms 列去分组统计：那一列存的是整条路径的算法串，分组结果是路径组合数，不是算法使用次数，两个数字完全不同。
八、覆盖缺口问题查询 dbo.gold_coverage_gap：gap_priority 为 1 的是必填变量应优先处理；该表已排除系统赋值变量，因此列出的都是真正需要人跟进的缺口。
九、补充限定符治理问题查询 dbo.gold_supp_promotion：折损越高上提到标准域的收益越大。
十、数据源选择规则：
    ① 上述五类已预先计算的问题，优先使用血缘图谱 Lakehouse 的 gold_ 结果表。
    ② 当用户提出结果表未覆盖的关系探索问题，例如任意两个对象之间怎么连通、
       某个字段往外几跳能触及哪些变量、图上各类节点的统计，
       使用图数据源 CrfSdtmLineageGraph 写 GQL 查询。
       注意 GQL 的 GROUP BY 只能引用 RETURN 里的别名，不能写成 n.属性名。
    ③ 当用户询问概念的定义、属性或概念之间的关系，例如"什么是补充限定符域"、
       "受控术语和变量是什么关系"，使用本体数据源 ClinicalDataStandardOntology。
    ④ 回答时说明本次结论来自哪个数据源，以及使用的是 SQL 还是 GQL。
十一、不要跨数据源替代作答。如果某个问题按上面的规则应当用图或本体回答，而对应数据源
    查询失败，就明确告诉用户该数据源当前不可用、这个问题需要它才能回答，然后停下。
    绝对不要改用 gold_ 结果表凑一个近似答案：口径不同的数字看起来合理但是错的，
    比不回答更糟。
十二、每次回答结尾提示：本结果基于示意性合成数据，不代表任何真实研究的映射规范。"""

DATASOURCE_INSTRUCTIONS = """本 Lakehouse 存放 CRF 到 SDTM 映射规范构建出的血缘图谱与治理结果表。

优先使用 gold_ 开头的结果表回答问题，不要从 lineage_edges 自行推导路径。
lineage_nodes 与 lineage_edges 用于展示图规模，node_type 区分对象类别，
mapping_penalty 为单跳映射折损，数值越小转换越直接。该值是无量纲权重，不是金额。"""

TABLES: dict[str, tuple[str, list[tuple[str, str]]]] = {
    "gold_variable_lineage": (
        "每个 SDTM 变量的全部 CRF 来源路径，按映射折损排序，用于反向溯源。",
        [("target_domain", "目标 SDTM 域，如 DM、DS、AE。"),
         ("target_variable", "目标 SDTM 变量名，如 ARMCD、DSDECOD。"),
         ("target_label_zh", "目标变量的中文标签。"),
         ("core", "变量的 Core 属性，Req 必填、Exp 预期、Perm 可选。"),
         ("path_rank", "同一变量下按映射折损升序的排名，1 为最直接。"),
         ("is_best_path", "是否为该变量最直接的来源路径。"),
         ("source_count", "该变量一共有多少条来源路径，大于 1 表示多来源。"),
         ("path_display_zh", "中文来源路径，形如 CRF 字段 -> 中间变量 -> 目标变量。"),
         ("hop_count", "路径跳数，1 表示直接映射。"),
         ("total_mapping_penalty", "路径累计映射折损，越小越直接。无量纲，与费用无关。"),
         ("algorithms", "路径上依次使用的转换算法。"),
         ("leading_condition_zh", "首跳映射的适用条件，多来源时靠它区分。"),
         ("worst_algorithm", "路径上折损最高的那个算法。"),
         ("passes_supplemental", "路径是否经过补充限定符域。")]),
    "gold_field_impact": (
        "修改某个 CRF 字段会波及的下游 SDTM 变量与数据集，用于影响分析。",
        [("form_oid", "CRF 表单编号，如 EX、IC、LB。"),
         ("form_name_zh", "表单中文名，如 研究药物给药。"),
         ("field_oid", "CRF 字段编号，如 EXSTDAT。"),
         ("field_label_zh", "字段中文标签，如 给药开始日期。"),
         ("acrf_page", "该字段在标注 CRF 上的页码。"),
         ("impacted_variable_count", "受影响的 SDTM 变量数量。"),
         ("impacted_domain_count", "受影响的 SDTM 域数量。"),
         ("impacted_domains", "受影响的域列表。"),
         ("impacted_variables", "受影响的变量列表。"),
         ("max_hop_depth", "最长影响链的跳数。"),
         ("deepest_path_zh", "最长影响链的中文表述。")]),
    "gold_version_diff": (
        "规范两个版本之间映射规则的差异，用于升级评估。",
        [("from_version", "起始版本。"),
         ("to_version", "目标版本。"),
         ("change_type_zh", "变化类型，取值 算法变更、V2 新增、V2 移除。"),
         ("detail", "变化详情，算法变更时形如 Lookup -> Assigned。"),
         ("form_oid", "涉及的 CRF 表单编号。"),
         ("field_oid", "涉及的 CRF 字段编号。"),
         ("target_domain", "涉及的 SDTM 域。"),
         ("target_variable", "涉及的 SDTM 变量。"),
         ("annotation_text", "该规则在标注 CRF 上的标注文本。")]),
    "gold_coverage_gap": (
        "没有任何 CRF 来源的 SDTM 变量，已排除系统赋值变量，用于覆盖率检查。",
        [("domain", "SDTM 域。"),
         ("variable_name", "SDTM 变量名。"),
         ("variable_label_zh", "变量中文标签。"),
         ("core", "Core 属性，Req 必填、Exp 预期、Perm 可选。"),
         ("expected_origin", "该变量预期的来源方式。"),
         ("gap_priority", "缺口优先级，1 最高，对应必填变量。"),
         ("suggestion_zh", "针对该缺口的处理建议。")]),
    "gold_supp_promotion": (
        "落在补充限定符域的映射，评估能否上提到标准域。",
        [("supp_domain", "补充限定符域名，如 SUPPDM、SUPPDS。"),
         ("parent_domain", "对应的父标准域。"),
         ("qnam", "补充限定符的变量短名。"),
         ("source_path_zh", "来源路径的中文表述。"),
         ("total_mapping_penalty", "累计映射折损。无量纲，与费用无关。"),
         ("algorithms", "路径上使用的转换算法。"),
         ("promotion_note_zh", "上提建议说明。")]),
    "gold_algorithm_usage": (
        "各种转换算法的使用次数，按单跳统计。问“哪种转换方式用了多少次”必须用本表，"
        "不要拿 gold_variable_lineage 的 algorithms 列分组代替，那一列是整条路径的算法串，"
        "分组出来是路径组合数而不是算法使用次数。",
        [("algorithm", "转换算法名，如 Copy、DT2DTC、Lookup、Derived。"),
         ("usage_count", "该算法共被用了多少次，一条边算一次。"),
         ("mapping_count", "其中用在 CRF 字段到 SDTM 变量映射上的次数。"),
         ("derivation_count", "其中用在变量间派生上的次数。"),
         ("unit_penalty", "该算法的单跳映射折损。无量纲，与费用无关。"),
         ("meaning_zh", "该算法的中文含义。"),
         ("counting_basis_zh", "统计口径说明。")]),
    "gold_question_catalog": (
        "示例业务问题与对应结果表，仅用于理解演示意图。",
        [("question_id", "问题编号。"),
         ("category_zh", "问题类别。"),
         ("question_zh", "中文业务问题。"),
         ("answer_table", "回答该问题应使用的结果表。"),
         ("guidance_zh", "回答该问题时的口径说明。")]),
    "lineage_nodes": (
        "血缘图节点，涵盖 CRF 表单、CRF 字段、SDTM 域、SDTM 变量。",
        [("node_id", "节点编号，形如 CRF:EX.EXSTDAT 或 SDTM:DM.ARMCD。"),
         ("node_type_zh", "节点类别中文名。"),
         ("display_name_zh", "节点中文显示名。"),
         ("domain", "若为 SDTM 对象，所属域。"),
         ("core", "若为 SDTM 变量，其 Core 属性。"),
         ("expected_origin", "若为 SDTM 变量，其预期来源方式。")]),
    "lineage_edges": (
        "血缘图有向边，包含映射与派生关系。",
        [("source_node_id", "起点节点编号。"),
         ("target_node_id", "终点节点编号。"),
         ("relationship_type_zh", "关系中文名，如 映射到、派生出、包含字段。"),
         ("algorithm", "转换算法。"),
         ("condition_zh", "适用条件。"),
         ("mapping_penalty", "单跳映射折损，越小越直接。无量纲，与费用无关。")]),
}

FEW_SHOTS = [
    ("DM 域的治疗组代码 ARMCD 是从哪个字段来的？有几条来源，哪条最直接？",
     "SELECT path_rank, is_best_path, source_count, path_display_zh, algorithms, "
     "leading_condition_zh, total_mapping_penalty FROM dbo.gold_variable_lineage "
     "WHERE target_domain = 'DM' AND target_variable = 'ARMCD' ORDER BY path_rank"),
    ("如果修改研究药物给药表单上的给药开始日期，会影响哪些 SDTM 变量和数据集？",
     "SELECT field_label_zh, impacted_variable_count, impacted_domain_count, "
     "impacted_domains, impacted_variables, max_hop_depth, deepest_path_zh "
     "FROM dbo.gold_field_impact WHERE form_oid = 'EX' AND field_oid = 'EXSTDAT'"),
    ("规范从 V1 升到 V2，映射规则有哪些变化？",
     "SELECT change_type_zh, detail, form_oid, field_oid, target_domain, "
     "target_variable, annotation_text FROM dbo.gold_version_diff "
     "ORDER BY change_type_zh, target_domain"),
    ("还有哪些 SDTM 变量没有对应的 CRF 采集来源？必填的有哪些？",
     "SELECT domain, variable_name, variable_label_zh, core, expected_origin, "
     "suggestion_zh FROM dbo.gold_coverage_gap ORDER BY gap_priority, domain"),
    ("哪些数据落在了补充限定符域？能不能上提到标准域？",
     "SELECT supp_domain, parent_domain, qnam, source_path_zh, algorithms, "
     "total_mapping_penalty, promotion_note_zh FROM dbo.gold_supp_promotion "
     "ORDER BY total_mapping_penalty DESC"),
    ("哪几个 CRF 字段改动风险最大？",
     "SELECT form_name_zh, field_label_zh, acrf_page, impacted_variable_count, "
     "impacted_domains, max_hop_depth FROM dbo.gold_field_impact "
     "ORDER BY impacted_variable_count DESC, max_hop_depth DESC"),
    ("各种转换方式分别用了多少次？哪些需要人工解释？",
     "SELECT algorithm, usage_count, mapping_count, derivation_count, "
     "unit_penalty, meaning_zh FROM dbo.gold_algorithm_usage "
     "ORDER BY usage_count DESC"),
]

GRAPH_DESCRIPTION = (
    "CRF 字段到 SDTM 变量的映射血缘图，节点标签 SpecNode，边标签 SPEC_RELATIONSHIP。"
    "用于结果表未覆盖的任意关系探索：两个对象之间怎么连通、某个字段往外几跳能触及什么、"
    "图上各类节点与关系的统计。示意性合成数据。")

GRAPH_INSTRUCTIONS = """使用 GQL 查询 CRF 到 SDTM 的映射血缘图。

节点标签 SpecNode，关键属性：
NodeId 形如 CRF:表单.字段 或 SDTM:域.变量；NodeType 取值 CRFForm、CRFField、SDTMDomain、SDTMVariable；
NodeTypeZh 中文类别；DisplayNameZh 中文显示名；Domain 所属域；Core 必填属性；
ExpectedOrigin 预期来源方式；IsSupplemental 是否补充限定符域。

边标签 SPEC_RELATIONSHIP，关键属性：
RelationshipType 取值 HAS_FIELD 包含字段、MAPS_TO 映射到、BELONGS_TO 属于域、DERIVES 派生出；
Algorithm 转换算法；ConditionZh 适用条件；MappingPenalty 单跳映射折损，越小越直接，
该值无量纲，只表示转换需要多少解释，与费用无关。

语法要点：
一、变长路径写作 -[:SPEC_RELATIONSHIP]->{1,4}，跳数用 size(edges(路径变量)) 取得。
二、GROUP BY 只能引用 RETURN 里定义的别名，写 GROUP BY n.NodeTypeZh 会报语法错误。
三、过滤写在模式内部的 WHERE 里，例如 (n:SpecNode WHERE n.NodeId = 'SDTM:DM.ARMCD')。
四、语句以分号结尾。"""

GRAPH_FEW_SHOTS = [
    ("图里一共有哪些类型的对象，各有多少个？",
     "MATCH (n:SpecNode) RETURN n.NodeTypeZh AS 类型, count(*) AS 数量 "
     "GROUP BY 类型 ORDER BY 数量 DESC;"),
    ("从知情同意签署日期这个字段出发，最多四跳能影响到哪些 SDTM 变量？",
     "MATCH p = (f:SpecNode WHERE f.NodeId = 'CRF:IC.ICDAT')"
     "-[:SPEC_RELATIONSHIP]->{1,4}(v:SpecNode WHERE v.NodeType = 'SDTMVariable') "
     "RETURN v.DisplayNameZh AS 受影响变量, size(edges(p)) AS 跳数 "
     "ORDER BY 跳数 DESC LIMIT 20;"),
    ("哪些 CRF 字段能连到 DS.DSDECOD？分别用了什么转换方式？",
     "MATCH (f:SpecNode WHERE f.NodeType = 'CRFField')"
     "-[r:SPEC_RELATIONSHIP WHERE r.RelationshipType = 'MAPS_TO']->"
     "(v:SpecNode WHERE v.NodeId = 'SDTM:DS.DSDECOD') "
     "RETURN f.DisplayNameZh AS 来源字段, r.Algorithm AS 转换方式, "
     "r.ConditionZh AS 适用条件, r.MappingPenalty AS 映射折损 ORDER BY 映射折损 ASC;"),
    ("各种转换算法分别用了多少次？",
     "MATCH ()-[r:SPEC_RELATIONSHIP WHERE r.RelationshipType = 'MAPS_TO']->() "
     "RETURN r.Algorithm AS 转换方式, count(*) AS 次数 "
     "GROUP BY 转换方式 ORDER BY 次数 DESC;"),
    ("哪些 SDTM 变量的来源路径最长？",
     "MATCH p = (f:SpecNode WHERE f.NodeType = 'CRFField')"
     "-[:SPEC_RELATIONSHIP]->{2,4}(v:SpecNode WHERE v.NodeType = 'SDTMVariable') "
     "RETURN v.DisplayNameZh AS 变量, f.DisplayNameZh AS 起点字段, "
     "size(edges(p)) AS 跳数 ORDER BY 跳数 DESC LIMIT 10;"),
]

ONTOLOGY_DESCRIPTION = (
    "临床数据标准本体，用业务语言描述 CRF 表单、CRF 字段、SDTM 域、SDTM 变量、"
    "映射规则、术语集与受控术语这些概念，以及它们之间的关系。"
    "当用户问某个概念是什么、有哪些属性、和别的概念是什么关系时使用。")


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
        "userDescription": "CRF 到 SDTM 映射血缘图谱与治理结果表。示意性合成数据。",
        "metadata": None,
        "elements": [{
            "id": None, "is_selected": True, "display_name": "dbo",
            "type": "lakehouse_tables.schema",
            "description": "血缘图谱与治理结果表所在的默认架构。",
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
        "fewShots": [{"id": f"40000000-0000-4000-8000-{i:012d}",
                      "question": question, "query": query}
                     for i, (question, query) in enumerate(FEW_SHOTS, start=1)],
    }
    graph_fewshots = {
        "$schema": f"{SCHEMA_BASE}/fewShots/1.0.0/schema.json",
        "fewShots": [{"id": f"50000000-0000-4000-8000-{i:012d}",
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
            "description": "CRF 到 SDTM 映射规范的中文智能问数：反向溯源、影响分析、"
                           "版本对比、覆盖缺口、补充限定符治理，并支持图上多跳关系探索。"},
        ".platform": {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/"
                       "platformProperties/2.0.0/schema.json",
            "metadata": {"type": "DataAgent", "displayName": AGENT_NAME,
                         "description": "CRF 到 SDTM 映射血缘的中文智能问数代理。"
                                        "示意性合成数据。"},
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


def verify(ws_id: str, agent_id: str) -> list[str]:
    status, payload, headers = call(
        "POST", f"{FABRIC}/v1/workspaces/{ws_id}/items/{agent_id}/getDefinition")
    if status == 202:
        payload = wait_lro(headers, "回读代理配置")
    sources = sorted({p["path"].split("/")[3]
                      for p in payload.get("definition", {}).get("parts", [])
                      if p["path"].startswith("Files/Config/published/")
                      and p["path"].endswith("datasource.json")})
    if not sources:
        raise RuntimeError("代理配置回读为空，没有已发布的数据源")
    return sources


def main() -> None:
    state = load_state(STATE)
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
    save_state(state, STATE)

    sources = verify(ws_id, agent_id)
    print(f"已导入 {len(parts)} 个配置文件")
    print(f"回读到已发布数据源 {len(sources)} 个：{'、'.join(sources)}")
    print(f"Lakehouse 选入 {len(TABLES)} 张表，SQL 示例 {len(FEW_SHOTS)} 条，"
          f"GQL 示例 {len(GRAPH_FEW_SHOTS)} 条")
    print(f"MCP 端点 {state['data_agent_mcp']}")


if __name__ == "__main__":
    main()
