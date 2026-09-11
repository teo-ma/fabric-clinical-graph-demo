# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {"name": "synapse_pyspark"},
# META   "language_info": {"name": "python"}
# META }

# CELL ********************

# MARKDOWN ********************

# MAGIC %md
# MAGIC # 11 摄取 CRF 到 SDTM 映射规范
# MAGIC
# MAGIC 把 7 张规范 CSV 从 landing 区读入并写成 Delta 表。
# MAGIC 全部为合成的示意性数据，不含任何客户真实资料。

# CELL ********************

from pyspark.sql import functions as F

SPEC_LAKEHOUSE_ID = "__SPEC_LAKEHOUSE_ID__"
BASE = f"abfss://__WORKSPACE_ID__@onelake.dfs.fabric.microsoft.com/{SPEC_LAKEHOUSE_ID}"

# 按表头读、不推断类型：全部保留为字符串。
# 不写显式 schema 是有意为之——显式 schema 会按位置套用而无视表头，
# 一旦生成脚本调整列顺序就会静默错位，且错误只会在下游分析里表现为空结果。
SPEC_TABLES = ["crf_forms", "crf_fields", "sdtm_domains", "sdtm_variables",
               "mapping_rules", "variable_derivations", "controlled_terms"]

# 每张表下游必须存在的列，读入后立即校验，避免列名漂移到图谱层才暴露。
REQUIRED_COLUMNS = {
    "crf_forms": ["version", "form_oid", "form_name_zh", "page"],
    "crf_fields": ["version", "form_oid", "field_oid", "field_label_zh",
                   "field_type", "codelist", "acrf_page"],
    "sdtm_domains": ["domain", "domain_label_zh", "is_supplemental", "parent_domain"],
    "sdtm_variables": ["domain", "variable_name", "variable_label_zh", "core",
                       "data_type", "codelist", "expected_origin"],
    "mapping_rules": ["version", "rule_id", "form_oid", "field_oid", "target_domain",
                      "target_variable", "qnam", "algorithm", "condition_zh",
                      "annotation_text"],
    "variable_derivations": ["source_domain", "source_variable", "target_domain",
                             "target_variable", "algorithm", "note_zh"],
    "controlled_terms": ["codelist", "submission_value", "decode_zh"],
}

# CELL ********************

for name in SPEC_TABLES:
    df = (spark.read.option("header", "true").option("multiLine", "true")
          .option("encoding", "UTF-8").csv(f"{BASE}/Files/landing/{name}.csv"))
    missing = [c for c in REQUIRED_COLUMNS[name] if c not in df.columns]
    assert not missing, f"{name} 缺少列 {missing}，实际列为 {df.columns}"
    df.write.mode("overwrite").option("overwriteSchema", "true") \
        .format("delta").save(f"{BASE}/Tables/{name}")
    print(f"{name}  rows={df.count()}  cols={len(df.columns)}")

# CELL ********************

# 摄取自检：数量对得上、外键连得上，否则后续图谱一定是错的。


def table(name):
    return spark.read.format("delta").load(f"{BASE}/Tables/{name}")


forms = table("crf_forms")
fields = table("crf_fields")
variables = table("sdtm_variables")
rules = table("mapping_rules")

orphan_fields = (fields.join(forms, ["form_oid", "version"], "left_anti").count())
orphan_rules = (rules.join(variables,
                           (rules.target_domain == variables.domain)
                           & (rules.target_variable == variables.variable_name),
                           "left_anti").count())

print(f"孤立字段 {orphan_fields}  指向不存在变量的规则 {orphan_rules}")
assert orphan_fields == 0, "存在没有归属表单的 CRF 字段"
assert orphan_rules == 0, "存在指向未定义 SDTM 变量的映射规则"

for version in ["V1", "V2"]:
    print(f"{version}: 字段 {fields.filter(F.col('version') == version).count()} "
          f"映射 {rules.filter(F.col('version') == version).count()}")

print("规范摄取完成")

# CELL ********************

# 当前版本视图与稳定主键。
# Ontology 的实体主键必须唯一，而规范表同时保存 V1/V2 两个版本，
# 且 CRF 字段、SDTM 变量的天然主键都是复合键，所以这里物化出
# 带单列主键的当前版本表，供本体绑定与 SQL 问答直接使用。
CURRENT_VERSION = "V2"


def save(df, name):
    df.write.mode("overwrite").option("overwriteSchema", "true") \
        .format("delta").save(f"{BASE}/Tables/{name}")
    print(f"{name}  rows={df.count()}")


forms_cur = forms.filter(F.col("version") == CURRENT_VERSION)
fields_cur = (fields.filter(F.col("version") == CURRENT_VERSION)
              .withColumn("field_uid", F.concat_ws(".", "form_oid", "field_oid")))
rules_cur = (rules.filter(F.col("version") == CURRENT_VERSION)
             .withColumn("field_uid", F.concat_ws(".", "form_oid", "field_oid"))
             .withColumn("variable_uid",
                         F.concat_ws(".", "target_domain", "target_variable")))
variables_keyed = variables.withColumn(
    "variable_uid", F.concat_ws(".", "domain", "variable_name"))
terms = table("controlled_terms").withColumn(
    "term_uid", F.concat_ws(".", "codelist", "submission_value"))
codelists = terms.groupBy("codelist").agg(F.count("*").alias("term_count"))

save(forms_cur, "crf_forms_current")
save(fields_cur, "crf_fields_current")
save(rules_cur, "mapping_rules_current")
save(variables_keyed, "sdtm_variables_keyed")
save(terms, "controlled_terms_keyed")
save(codelists, "codelists")

# 主键唯一性是本体绑定能否成立的硬前提，这里直接断言而不是相信约定。
for df, key, label in [(forms_cur, "form_oid", "crf_forms_current"),
                       (fields_cur, "field_uid", "crf_fields_current"),
                       (rules_cur, "rule_id", "mapping_rules_current"),
                       (variables_keyed, "variable_uid", "sdtm_variables_keyed"),
                       (terms, "term_uid", "controlled_terms_keyed"),
                       (codelists, "codelist", "codelists")]:
    total, distinct = df.count(), df.select(key).distinct().count()
    assert total == distinct, f"{label} 的 {key} 不唯一：{total} 行但只有 {distinct} 个值"

print("当前版本视图构建完成，主键唯一性校验通过")
