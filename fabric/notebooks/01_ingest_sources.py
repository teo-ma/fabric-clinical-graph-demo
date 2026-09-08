# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {"name": "synapse_pyspark"},
# META   "language_info": {"name": "python"}
# META }

# CELL ********************

# MARKDOWN ********************

# MAGIC %md
# MAGIC # 01 多源临床数据摄取
# MAGIC
# MAGIC 将六个模拟源系统的着陆区 CSV 转换为各自 Lakehouse 中的托管 Delta 表。
# MAGIC 每个源系统对应一个独立 Lakehouse，用于体现真实企业中系统边界的存在。
# MAGIC
# MAGIC 全部为合成数据，不含任何真实受试者、试验或产品信息。

# CELL ********************

# 由部署脚本注入：workspaceId 与各源系统 Lakehouse 的 itemId
WORKSPACE_ID = "__WORKSPACE_ID__"

SOURCE_LAKEHOUSES = {
    "ctms": "__LH_CTMS__",
    "edc": "__LH_EDC__",
    "safety": "__LH_SAFETY__",
    "lims": "__LH_LIMS__",
    "knowledge": "__LH_KNOWLEDGE__",
    "supply": "__LH_SUPPLY__",
}

SOURCE_TABLES = {
    "ctms": ["studies", "sites", "investigators", "subjects", "protocol_deviations"],
    "edc": ["visits", "dosing_records"],
    "safety": ["adverse_events", "safety_signals", "ae_signal_links"],
    "lims": ["lab_results"],
    "knowledge": [
        "compounds", "targets", "pathways", "biomarkers", "ae_terms",
        "compound_target", "target_pathway", "pathway_biomarker", "biomarker_ae",
    ],
    "supply": ["batches", "shipments"],
}


def lakehouse_root(item_id: str) -> str:
    return f"abfss://{WORKSPACE_ID}@onelake.dfs.fabric.microsoft.com/{item_id}"

# CELL ********************

from pyspark.sql import functions as F

summary = []

for system, item_id in SOURCE_LAKEHOUSES.items():
    root = lakehouse_root(item_id)
    for table in SOURCE_TABLES[system]:
        df = (
            spark.read
            .option("header", "true")
            .option("inferSchema", "true")
            .option("encoding", "UTF-8")
            .csv(f"{root}/Files/landing/{table}.csv")
        )
        df = df.withColumn("_source_system", F.lit(system))
        df.write.mode("overwrite").format("delta").save(f"{root}/Tables/{table}")
        summary.append((system, table, df.count(), len(df.columns)))

for system, table, rows, cols in summary:
    print(f"{system:<10} {table:<22} rows={rows:<6} cols={cols}")

# CELL ********************

# 摄取校验：每个源系统的表都必须非空，否则后续图构建会静默产生空结果。
empty = [f"{s}.{t}" for s, t, rows, _ in summary if rows == 0]
assert not empty, f"以下表摄取后为空: {empty}"
print(f"摄取完成：{len(summary)} 张表，覆盖 {len(SOURCE_LAKEHOUSES)} 个源系统。")
