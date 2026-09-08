# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {"name": "synapse_pyspark"},
# META   "language_info": {"name": "python"}
# META }

# CELL ********************

# MARKDOWN ********************

# MAGIC %md
# MAGIC # 02 统一临床知识图谱与业务洞察
# MAGIC
# MAGIC 把六个源系统的 Delta 表统一成一张跨系统临床知识图谱，并回答五类制药业务问题。
# MAGIC 图算法为确定性实现，结果落成结果表，供 Fabric Graph、Ontology 与 Data Agent 共同消费。
# MAGIC
# MAGIC 下方的图逻辑与仓库中的 `fabric/graph_logic.py` 完全一致，由部署脚本内联注入，
# MAGIC 因此本地验证与云端运行不会产生逻辑漂移。
# MAGIC
# MAGIC 全部为合成数据，不构成任何真实医学或用药结论。

# CELL ********************

WORKSPACE_ID = "__WORKSPACE_ID__"

SOURCE_LAKEHOUSES = {
    "ctms": "__LH_CTMS__",
    "edc": "__LH_EDC__",
    "safety": "__LH_SAFETY__",
    "lims": "__LH_LIMS__",
    "knowledge": "__LH_KNOWLEDGE__",
    "supply": "__LH_SUPPLY__",
}
CURATED_LAKEHOUSE = "__LH_CURATED__"

SOURCE_TABLES = {
    "ctms": ["studies", "sites", "investigators", "subjects", "protocol_deviations"],
    "edc": ["visits", "dosing_records"],
    "safety": ["adverse_events", "safety_signals", "ae_signal_links"],
    "lims": ["lab_results"],
    "knowledge": ["compounds", "targets", "pathways", "biomarkers", "ae_terms",
                  "compound_target", "target_pathway", "pathway_biomarker", "biomarker_ae"],
    "supply": ["batches", "shipments"],
}


def root(item_id: str) -> str:
    return f"abfss://{WORKSPACE_ID}@onelake.dfs.fabric.microsoft.com/{item_id}"


src = {}
for system, tables_ in SOURCE_TABLES.items():
    for table in tables_:
        path = f"{root(SOURCE_LAKEHOUSES[system])}/Tables/{table}"
        src[(system, table)] = [r.asDict() for r in spark.read.format("delta").load(path).collect()]
        print(f"{system:<10} {table:<22} {len(src[(system, table)])}")

# CELL ********************

# __GRAPH_LOGIC__

# CELL ********************

graph = ClinicalGraph(src)
tables = graph.build()

print(f"节点 {len(tables['graph_nodes'])}  边 {len(tables['graph_edges'])}")
by_type = {}
for n in tables["graph_nodes"]:
    by_type[n["node_type_zh"]] = by_type.get(n["node_type_zh"], 0) + 1
print("  ".join(f"{k}={v}" for k, v in sorted(by_type.items(), key=lambda x: -x[1])))

for name in ["gold_mechanism_paths", "gold_batch_impact", "gold_signal_evidence",
             "gold_target_crosstalk", "gold_site_risk"]:
    print(f"{name:<26} {len(tables[name])}")

# CELL ********************

from pyspark.sql.types import (BooleanType, DoubleType, LongType, StringType,
                               StructField, StructType)

CURATED = root(CURATED_LAKEHOUSE)


def s(name):
    return StructField(name, StringType(), True)


def d(name):
    return StructField(name, DoubleType(), True)


def i(name):
    return StructField(name, LongType(), True)


SCHEMAS = {
    "graph_nodes": StructType([
        s("node_id"), s("node_type"), s("node_type_zh"), s("display_name_zh"),
        s("source_system"), s("study_id"), s("category"), s("status"),
        d("numeric_value"), s("event_date"), i("data_version"),
    ]),
    "graph_edges": StructType([
        s("edge_id"), s("source_node_id"), s("target_node_id"), s("relationship_type"),
        s("relationship_type_zh"), s("evidence_grade"), d("confidence"), d("evidence_penalty"),
        s("edge_class"), s("source_system"), i("data_version"),
    ]),
    "gold_mechanism_paths": StructType([
        s("compound_id"), s("compound_name_zh"), s("ae_pt_code"), s("ae_pt_name_zh"),
        i("path_rank"), StructField("is_best_path", BooleanType(), True),
        s("path_node_ids"), s("path_display_zh"), i("hop_count"),
        d("total_evidence_penalty"), s("worst_evidence_grade"), d("min_confidence"),
        i("data_version"),
    ]),
    "gold_batch_impact": StructType([
        s("batch_id"), s("shipment_id"), s("site_id"), s("site_name_zh"), s("study_id"),
        s("subject_id"), s("treatment_arm"), s("ae_id"), s("ae_pt_name_zh"),
        s("serious_flag"), i("ctcae_grade"), s("causality_zh"), s("impact_path_zh"),
        i("data_version"),
    ]),
    "gold_signal_evidence": StructType([
        s("signal_id"), s("compound_id"), s("compound_name_zh"), s("ae_pt_code"),
        s("ae_pt_name_zh"), s("signal_status_zh"), s("signal_evidence_grade"),
        i("linked_ae_count"), i("serious_ae_count"), i("affected_subject_count"),
        i("affected_site_count"), i("supporting_abnormal_lab_count"),
        s("supporting_biomarkers_zh"), s("best_mechanism_path_zh"),
        d("best_mechanism_penalty"), i("data_version"),
    ]),
    "gold_target_crosstalk": StructType([
        s("compound_a"), s("compound_a_name_zh"), s("compound_b"), s("compound_b_name_zh"),
        i("shared_target_count"), s("shared_targets_zh"), i("shared_pathway_count"),
        s("shared_pathways_zh"), s("shared_risk_terms_zh"),
        s("compound_a_studies"), s("compound_b_studies"), i("data_version"),
    ]),
    "gold_site_risk": StructType([
        s("site_id"), s("site_name_zh"), s("study_id"), s("country"), s("investigator_name"),
        i("subject_count"), i("adverse_event_count"), i("serious_ae_count"),
        i("deviation_count"), i("important_deviation_count"),
        i("temperature_excursion_count"), d("risk_score"), s("risk_tier_zh"), i("data_version"),
    ]),
    "gold_question_catalog": StructType([
        s("question_id"), s("category_zh"), s("question_zh"),
        s("answer_table"), s("guidance_zh"), i("data_version"),
    ]),
}

payload = dict(tables)
payload["gold_question_catalog"] = QUESTION_CATALOG

for name, records in payload.items():
    df = spark.createDataFrame(records, schema=SCHEMAS[name])
    df.write.mode("overwrite").option("overwriteSchema", "true") \
        .format("delta").save(f"{CURATED}/Tables/{name}")
    print(f"{name:<26} 已写入 {df.count()} 行")

# CELL ********************

# 结果断言：任一失败都说明跨系统关联断裂，演示问题会落空。
mechanism = tables["gold_mechanism_paths"]
batch_impact = tables["gold_batch_impact"]

assert len(tables["graph_nodes"]) > 800, f"节点数异常 {len(tables['graph_nodes'])}"
assert len(tables["graph_edges"]) > 2000, f"边数异常 {len(tables['graph_edges'])}"
assert any(r["compound_id"] == "CMP-001" and r["ae_pt_code"] == "PT-DILI" and r["is_best_path"]
           for r in mechanism), "缺少 SYN-101 到药物性肝损伤的最优机制路径"
assert any(r["batch_id"] == "BATCH-007" and r["serious_flag"] == "是"
           for r in batch_impact), "BATCH-007 影响链中缺少严重不良事件"
assert all(r["linked_ae_count"] > 0 for r in tables["gold_signal_evidence"]), "存在无证据支持的安全信号"

print("全部断言通过。统一图与业务结果表已就绪。")
