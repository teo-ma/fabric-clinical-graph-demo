# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {"name": "synapse_pyspark"},
# META   "language_info": {"name": "python"}
# META }

# CELL ********************

# MARKDOWN ********************

# MAGIC %md
# MAGIC # 12 构建 CRF 到 SDTM 血缘图谱与治理洞察
# MAGIC
# MAGIC 读规范层 Delta 表，构建血缘图的节点与边，再产出六张业务结果表。
# MAGIC 图构建与分析逻辑来自 fabric/lineage_logic.py，部署时原样内联到此处，
# MAGIC 保证本地验证与云端运行是同一份代码。

# CELL ********************

from pyspark.sql import Row
from pyspark.sql.types import (BooleanType, DoubleType, IntegerType, StringType,
                               StructField, StructType)

SPEC_LAKEHOUSE_ID = "__SPEC_LAKEHOUSE_ID__"
CURATED_LAKEHOUSE_ID = "__CURATED_LAKEHOUSE_ID__"
WORKSPACE_ID = "__WORKSPACE_ID__"
SPEC_VERSION = "V2"

SPEC_BASE = f"abfss://{WORKSPACE_ID}@onelake.dfs.fabric.microsoft.com/{SPEC_LAKEHOUSE_ID}"
CURATED_BASE = f"abfss://{WORKSPACE_ID}@onelake.dfs.fabric.microsoft.com/{CURATED_LAKEHOUSE_ID}"

SPEC_TABLES = ["crf_forms", "crf_fields", "sdtm_domains", "sdtm_variables",
               "mapping_rules", "variable_derivations", "controlled_terms"]

src = {}
for table in SPEC_TABLES:
    rows = spark.read.format("delta").load(f"{SPEC_BASE}/Tables/{table}").collect()
    src[("spec", table)] = [r.asDict() for r in rows]
    print(f"{table}  {len(src[('spec', table)])}")

# CELL ********************

# __LINEAGE_LOGIC__

# CELL ********************

g = LineageGraph(src, version=SPEC_VERSION)
graph = g.build()

lineage = gold_variable_lineage(g)
impact = gold_field_impact(g)
diff = gold_version_diff(src)
gap = gold_coverage_gap(g, lineage)
supp = gold_supp_promotion(g, lineage)
algos = gold_algorithm_usage(g)

print(f"节点 {len(graph['lineage_nodes'])}  边 {len(graph['lineage_edges'])}")
print(f"溯源路径 {len(lineage)}  影响字段 {len(impact)}  版本差异 {len(diff)} "
      f"覆盖缺口 {len(gap)}  上提候选 {len(supp)}  转换方式 {len(algos)}")

# CELL ********************

NODE_SCHEMA = StructType([
    StructField("node_id", StringType(), False),
    StructField("node_type", StringType(), True),
    StructField("node_type_zh", StringType(), True),
    StructField("display_name_zh", StringType(), True),
    StructField("domain", StringType(), True),
    StructField("form_oid", StringType(), True),
    StructField("core", StringType(), True),
    StructField("data_type", StringType(), True),
    StructField("codelist", StringType(), True),
    StructField("acrf_page", StringType(), True),
    StructField("is_supplemental", StringType(), True),
    StructField("expected_origin", StringType(), True),
    StructField("spec_version", StringType(), True),
])

EDGE_SCHEMA = StructType([
    StructField("edge_id", StringType(), False),
    StructField("source_node_id", StringType(), True),
    StructField("target_node_id", StringType(), True),
    StructField("relationship_type", StringType(), True),
    StructField("relationship_type_zh", StringType(), True),
    StructField("algorithm", StringType(), True),
    StructField("condition_zh", StringType(), True),
    StructField("rule_id", StringType(), True),
    StructField("mapping_penalty", DoubleType(), True),
    StructField("spec_version", StringType(), True),
])

LINEAGE_SCHEMA = StructType([
    StructField("spec_version", StringType(), True),
    StructField("target_domain", StringType(), True),
    StructField("target_variable", StringType(), True),
    StructField("target_label_zh", StringType(), True),
    StructField("core", StringType(), True),
    StructField("path_rank", IntegerType(), True),
    StructField("is_best_path", BooleanType(), True),
    StructField("source_count", IntegerType(), True),
    StructField("path_node_ids", StringType(), True),
    StructField("path_display_zh", StringType(), True),
    StructField("hop_count", IntegerType(), True),
    StructField("total_mapping_penalty", DoubleType(), True),
    StructField("algorithms", StringType(), True),
    StructField("leading_condition_zh", StringType(), True),
    StructField("worst_algorithm", StringType(), True),
    StructField("passes_supplemental", BooleanType(), True),
])

IMPACT_SCHEMA = StructType([
    StructField("spec_version", StringType(), True),
    StructField("form_oid", StringType(), True),
    StructField("form_name_zh", StringType(), True),
    StructField("field_oid", StringType(), True),
    StructField("field_label_zh", StringType(), True),
    StructField("acrf_page", IntegerType(), True),
    StructField("impacted_variable_count", IntegerType(), True),
    StructField("impacted_domain_count", IntegerType(), True),
    StructField("impacted_domains", StringType(), True),
    StructField("impacted_variables", StringType(), True),
    StructField("max_hop_depth", IntegerType(), True),
    StructField("deepest_path_zh", StringType(), True),
])

DIFF_SCHEMA = StructType([
    StructField("from_version", StringType(), True),
    StructField("to_version", StringType(), True),
    StructField("change_type_zh", StringType(), True),
    StructField("detail", StringType(), True),
    StructField("form_oid", StringType(), True),
    StructField("field_oid", StringType(), True),
    StructField("target_domain", StringType(), True),
    StructField("target_variable", StringType(), True),
    StructField("annotation_text", StringType(), True),
])

GAP_SCHEMA = StructType([
    StructField("spec_version", StringType(), True),
    StructField("domain", StringType(), True),
    StructField("variable_name", StringType(), True),
    StructField("variable_label_zh", StringType(), True),
    StructField("core", StringType(), True),
    StructField("expected_origin", StringType(), True),
    StructField("gap_priority", IntegerType(), True),
    StructField("suggestion_zh", StringType(), True),
])

SUPP_SCHEMA = StructType([
    StructField("spec_version", StringType(), True),
    StructField("supp_domain", StringType(), True),
    StructField("parent_domain", StringType(), True),
    StructField("qnam", StringType(), True),
    StructField("source_path_zh", StringType(), True),
    StructField("total_mapping_penalty", DoubleType(), True),
    StructField("algorithms", StringType(), True),
    StructField("promotion_note_zh", StringType(), True),
])

CATALOG_SCHEMA = StructType([
    StructField("question_id", StringType(), True),
    StructField("category_zh", StringType(), True),
    StructField("question_zh", StringType(), True),
    StructField("answer_table", StringType(), True),
    StructField("guidance_zh", StringType(), True),
])

ALGO_SCHEMA = StructType([
    StructField("spec_version", StringType(), True),
    StructField("algorithm", StringType(), True),
    StructField("usage_count", IntegerType(), True),
    StructField("mapping_count", IntegerType(), True),
    StructField("derivation_count", IntegerType(), True),
    StructField("unit_penalty", DoubleType(), True),
    StructField("meaning_zh", StringType(), True),
    StructField("counting_basis_zh", StringType(), True),
])

# CELL ********************


def write(name, rows, schema):
    df = spark.createDataFrame([Row(**{f.name: r.get(f.name) for f in schema.fields})
                                for r in rows], schema=schema)
    df.write.mode("overwrite").format("delta").save(f"{CURATED_BASE}/Tables/{name}")
    print(f"{name}  rows={df.count()}")
    return df


write("lineage_nodes", graph["lineage_nodes"], NODE_SCHEMA)
write("lineage_edges", graph["lineage_edges"], EDGE_SCHEMA)
write("gold_variable_lineage", lineage, LINEAGE_SCHEMA)
write("gold_field_impact", impact, IMPACT_SCHEMA)
write("gold_version_diff", diff, DIFF_SCHEMA)
write("gold_coverage_gap", gap, GAP_SCHEMA)
write("gold_supp_promotion", supp, SUPP_SCHEMA)
write("gold_algorithm_usage", algos, ALGO_SCHEMA)
write("gold_question_catalog", QUESTION_CATALOG, CATALOG_SCHEMA)

# CELL ********************

# 结果自检：植入的演示场景必须都能被查出来，否则演示当场会翻车。
assert len(graph["lineage_nodes"]) > 150, "节点数异常"
assert len(graph["lineage_edges"]) > 200, "边数异常"

armcd = [r for r in lineage if r["target_variable"] == "ARMCD"]
assert len(armcd) >= 2, "DM.ARMCD 应有多条来源用于最优路径对比"
best = next(r for r in armcd if r["is_best_path"])
print(f"ARMCD 最直接来源 折损 {best['total_mapping_penalty']}  {best['path_display_zh']}")

deep = [r for r in impact if r["max_hop_depth"] >= 3]
assert deep, "缺少多跳影响链"
print(f"影响面最大字段: {deep[0]['field_label_zh']} 影响 {deep[0]['impacted_variable_count']} 个变量")

assert diff, "版本对比结果为空"
assert any(r["change_type_zh"] == "算法变更" for r in diff), "缺少算法变更场景"
assert gap and all(r["expected_origin"] != "系统赋值" for r in gap), "覆盖缺口口径不对"
assert supp, "应存在补充限定符上提候选"

# 算法分布必须是单跳口径：总次数等于带算法的边数，且算法名里不能出现路径串。
edges_with_algo = [e for e in graph["lineage_edges"]
                   if e["algorithm"] and e["relationship_type"] in ("MAPS_TO", "DERIVES")]
assert sum(r["usage_count"] for r in algos) == len(edges_with_algo), "算法使用次数口径错了"
assert all(" -> " not in r["algorithm"] for r in algos), "算法名里出现了路径串"
print(f"转换方式 {len(algos)} 种，单跳总次数 {len(edges_with_algo)}")

print("血缘图谱与治理洞察构建完成")
