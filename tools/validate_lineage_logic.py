"""Run the CRF-to-SDTM lineage logic locally against the generated spec CSVs."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "fabric"))

from lineage_logic import (LineageGraph, QUESTION_CATALOG,  # noqa: E402
                           gold_algorithm_usage, gold_coverage_gap,
                           gold_field_impact, gold_supp_promotion,
                           gold_variable_lineage, gold_version_diff)

TABLES = ["crf_forms", "crf_fields", "sdtm_domains", "sdtm_variables",
          "mapping_rules", "variable_derivations", "controlled_terms"]

# 与 fabric/notebooks/11_ingest_spec.py 中的 REQUIRED_COLUMNS 保持一致。
# 云端摄取按表头读，列名一旦漂移只会在图谱层表现为空结果，所以在本地就卡住。
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


def load() -> dict[tuple[str, str], list[dict]]:
    src = {}
    for table in TABLES:
        with (ROOT / "data" / "spec" / f"{table}.csv").open(encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        missing = [c for c in REQUIRED_COLUMNS[table] if rows and c not in rows[0]]
        assert not missing, f"{table} 缺少列 {missing}"
        src[("spec", table)] = rows
    return src


def check_integrity(src: dict[tuple[str, str], list[dict]]) -> None:
    forms = {(r["form_oid"], r["version"]) for r in src[("spec", "crf_forms")]}
    fields = {(r["form_oid"], r["field_oid"], r["version"])
              for r in src[("spec", "crf_fields")]}
    variables = {(r["domain"], r["variable_name"]) for r in src[("spec", "sdtm_variables")]}
    domains = {r["domain"] for r in src[("spec", "sdtm_domains")]}

    orphan_fields = sorted({(r["form_oid"], r["version"])
                            for r in src[("spec", "crf_fields")]} - forms)
    assert not orphan_fields, f"字段归属的表单不存在: {orphan_fields}"

    rules = src[("spec", "mapping_rules")]
    bad_src = sorted({(r["form_oid"], r["field_oid"], r["version"]) for r in rules} - fields)
    assert not bad_src, f"规则引用了不存在的 CRF 字段: {bad_src}"
    bad_dst = sorted({(r["target_domain"], r["target_variable"]) for r in rules} - variables)
    assert not bad_dst, f"规则指向未定义的 SDTM 变量: {bad_dst}"

    derivations = src[("spec", "variable_derivations")]
    bad_deriv = sorted(({(r["source_domain"], r["source_variable"]) for r in derivations}
                        | {(r["target_domain"], r["target_variable"]) for r in derivations})
                       - variables)
    assert not bad_deriv, f"派生关系引用了未定义的变量: {bad_deriv}"

    bad_domain = sorted({r["domain"] for r in src[("spec", "sdtm_variables")]} - domains)
    assert not bad_domain, f"变量归属的域不存在: {bad_domain}"
    print("参照完整性检查通过")


def main() -> None:
    src = load()
    check_integrity(src)
    g = LineageGraph(src, version="V2")
    graph = g.build()

    lineage = gold_variable_lineage(g)
    impact = gold_field_impact(g)
    diff = gold_version_diff(src)
    gap = gold_coverage_gap(g, lineage)
    supp = gold_supp_promotion(g, lineage)
    algos = gold_algorithm_usage(g)

    print("=== 血缘图规模（规范版本 V2） ===")
    print(f"节点 {len(graph['lineage_nodes'])}  边 {len(graph['lineage_edges'])}")
    by_type: dict[str, int] = {}
    for n in graph["lineage_nodes"]:
        by_type[n["node_type_zh"]] = by_type.get(n["node_type_zh"], 0) + 1
    print("  " + "  ".join(f"{k}={v}" for k, v in sorted(by_type.items(), key=lambda x: -x[1])))

    print("\n=== L1 最优路径：DM.ARMCD 的多条来源 ===")
    for r in [x for x in lineage if x["target_variable"] == "ARMCD"]:
        flag = "  <== 最直接" if r["is_best_path"] else ""
        print(f"  #{r['path_rank']} 折损 {r['total_mapping_penalty']} "
              f"[{r['algorithms']}] {r['path_display_zh']}{flag}")

    print("\n=== L6 多来源歧义：DS.DSSTDTC 各来源的区分条件 ===")
    for r in [x for x in lineage if x["target_variable"] == "DSSTDTC"
              and x["target_domain"] == "DS"]:
        print(f"  折损 {r['total_mapping_penalty']} [{r['algorithms']}] "
              f"{r['path_display_zh']}")
        print(f"     区分条件：{r['leading_condition_zh'] or '（未标注）'}")

    print("\n=== L2 影响分析：影响面最大的 5 个 CRF 字段 ===")
    for r in impact[:5]:
        print(f"  {r['form_name_zh']} / {r['field_label_zh']}（aCRF 第 {r['acrf_page']} 页）")
        print(f"     影响 {r['impacted_variable_count']} 个变量，跨 {r['impacted_domain_count']} 个域"
              f"（{r['impacted_domains']}），最长 {r['max_hop_depth']} 跳")
        print(f"     最长链路：{r['deepest_path_zh']}")

    print("\n=== L3 版本对比 V1 -> V2 ===")
    for r in diff:
        print(f"  [{r['change_type_zh']}] {r['form_oid']}.{r['field_oid']} -> "
              f"{r['target_domain']}.{r['target_variable']}  {r['detail']}")

    print("\n=== L4 覆盖缺口（已排除系统赋值变量） ===")
    for r in gap:
        print(f"  [{r['core']}] {r['domain']}.{r['variable_name']}  "
              f"{r['variable_label_zh']} —— {r['suggestion_zh']}")
    req = [r for r in gap if r["core"] == "Req"]
    print(f"  必填缺口 {len(req)} 个，全部缺口 {len(gap)} 个")

    print("\n=== L5 补充限定符上提候选 ===")
    for r in supp:
        print(f"  {r['supp_domain']}（父域 {r['parent_domain']}，QNAM={r['qnam']}）"
              f" 折损 {r['total_mapping_penalty']}")
        print(f"     {r['source_path_zh']}")

    print("\n=== L7 转换方式分布（按单跳统计） ===")
    for r in algos:
        print(f"  {r['algorithm']:12s} {r['usage_count']:3d} 次"
              f"（映射 {r['mapping_count']}，派生 {r['derivation_count']}）"
              f"  单跳折损 {r['unit_penalty']}  {r['meaning_zh']}")

    assert len(graph["lineage_nodes"]) > 150, "节点数异常"
    assert len(graph["lineage_edges"]) > 200, "边数异常"
    multi = [r for r in lineage if r["target_variable"] == "ARMCD"]
    assert len(multi) >= 2, "DM.ARMCD 应有多条来源用于最优路径对比"
    assert any(r["max_hop_depth"] >= 3 for r in impact), "缺少多跳影响链"
    assert diff, "版本对比结果为空"
    assert gap, "覆盖缺口应至少有一项真实缺口"
    assert all(r["expected_origin"] != "系统赋值" for r in gap), \
        "系统赋值变量不应计入覆盖缺口"
    assert len(gap) < 15, "缺口过多，演示时缺乏说服力"
    assert supp, "应存在补充限定符上提候选"
    # 单跳统计的总次数必须等于带算法的边数，否则就是又沿路径统计了。
    edges_with_algo = [e for e in graph["lineage_edges"]
                       if e["algorithm"] and e["relationship_type"] in ("MAPS_TO", "DERIVES")]
    assert sum(r["usage_count"] for r in algos) == len(edges_with_algo), \
        "算法使用次数与带算法的边数不一致，可能退回成了路径组合统计"
    assert all(" -> " not in r["algorithm"] for r in algos), \
        "算法名里出现了路径串，口径错了"
    print(f"\n全部断言通过。问题目录 {len(QUESTION_CATALOG)} 条。")


if __name__ == "__main__":
    main()
