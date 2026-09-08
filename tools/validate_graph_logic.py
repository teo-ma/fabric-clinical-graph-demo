"""Run the clinical graph logic locally against the generated CSVs.

Validates the demo answers before anything is deployed to Fabric, so bugs are
caught without spending capacity on a failed Spark run.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "fabric"))

from graph_logic import QUESTION_CATALOG, ClinicalGraph  # noqa: E402

SOURCES = {
    "ctms": ["studies", "sites", "investigators", "subjects", "protocol_deviations"],
    "edc": ["visits", "dosing_records"],
    "safety": ["adverse_events", "safety_signals", "ae_signal_links"],
    "lims": ["lab_results"],
    "knowledge": ["compounds", "targets", "pathways", "biomarkers", "ae_terms",
                  "compound_target", "target_pathway", "pathway_biomarker", "biomarker_ae"],
    "supply": ["batches", "shipments"],
}

NUMERIC = {"confidence", "result_value", "upper_normal_limit", "ctcae_grade", "dose_mg"}


def load() -> dict[tuple[str, str], list[dict]]:
    src: dict[tuple[str, str], list[dict]] = {}
    for system, tables in SOURCES.items():
        for table in tables:
            path = ROOT / "data" / "sources" / system / f"{table}.csv"
            with path.open(encoding="utf-8") as fh:
                out = []
                for row in csv.DictReader(fh):
                    for key in list(row):
                        if key in NUMERIC and row[key] != "":
                            row[key] = float(row[key])
                    out.append(row)
            src[(system, table)] = out
    return src


def main() -> None:
    graph = ClinicalGraph(load())
    tables = graph.build()

    print("=== 图规模 ===")
    print(f"节点 {len(tables['graph_nodes'])}  边 {len(tables['graph_edges'])}")
    by_type: dict[str, int] = {}
    for n in tables["graph_nodes"]:
        by_type[n["node_type_zh"]] = by_type.get(n["node_type_zh"], 0) + 1
    print("  " + "  ".join(f"{k}={v}" for k, v in sorted(by_type.items(), key=lambda x: -x[1])))
    by_sys: dict[str, int] = {}
    for e in tables["graph_edges"]:
        by_sys[e["source_system"]] = by_sys.get(e["source_system"], 0) + 1
    print(f"  边按源系统: {by_sys}")

    print("\n=== Q1 机制解释：SYN-101 与药物性肝损伤 ===")
    q1 = sorted([r for r in tables["gold_mechanism_paths"]
                 if r["compound_id"] == "CMP-001" and r["ae_pt_code"] == "PT-DILI"],
                key=lambda r: r["path_rank"])
    for r in q1:
        flag = "  <== 证据最强" if r["is_best_path"] else ""
        print(f"  #{r['path_rank']} 折损 {r['total_evidence_penalty']} "
              f"最差等级 {r['worst_evidence_grade']} | {r['path_display_zh']}{flag}")

    print("\n=== Q2 批次溯源：BATCH-007 温度偏移 ===")
    q2 = [r for r in tables["gold_batch_impact"] if r["batch_id"] == "BATCH-007"]
    sites = sorted({r["site_name_zh"] for r in q2})
    subjects = {r["subject_id"] for r in q2}
    serious = [r for r in q2 if r["serious_flag"] == "是"]
    print(f"  受影响中心 {len(sites)}: {'、'.join(sites)}")
    print(f"  受影响受试者 {len(subjects)}  严重不良事件 {len(serious)} 条")
    for r in serious[:4]:
        print(f"    {r['impact_path_zh']} | {r['ae_pt_name_zh']} "
              f"{r['ctcae_grade']}级 {r['causality_zh']}")

    print("\n=== Q3 信号证据链 ===")
    for r in tables["gold_signal_evidence"]:
        print(f"  {r['signal_id']} {r['ae_pt_name_zh']}（{r['compound_name_zh']}）"
              f" 状态 {r['signal_status_zh']}")
        print(f"    关联AE {r['linked_ae_count']} 严重 {r['serious_ae_count']} "
              f"受试者 {r['affected_subject_count']} 中心 {r['affected_site_count']} "
              f"支持性异常检验 {r['supporting_abnormal_lab_count']}")
        print(f"    机制: {r['best_mechanism_path_zh']}")

    print("\n=== Q4 同靶点风险外推（与 SYN-101 相关） ===")
    for r in tables["gold_target_crosstalk"]:
        if "CMP-001" not in (r["compound_a"], r["compound_b"]):
            continue
        print(f"  {r['compound_a_name_zh']} vs {r['compound_b_name_zh']} | "
              f"共享靶点 {r['shared_targets_zh'] or '无'} | "
              f"共享通路 {r['shared_pathways_zh'] or '无'}")
        print(f"    共享风险: {r['shared_risk_terms_zh'] or '无'} | "
              f"在研: {r['compound_b_studies']}")

    print("\n=== Q5 中心风险画像（前 5） ===")
    for r in tables["gold_site_risk"][:5]:
        print(f"  {r['site_name_zh']} {r['risk_tier_zh']} 分值 {r['risk_score']} | "
              f"受试者 {r['subject_count']} 严重AE {r['serious_ae_count']} "
              f"重要偏离 {r['important_deviation_count']} 温度偏移 {r['temperature_excursion_count']}")

    assert len(tables["graph_nodes"]) > 800
    assert len(tables["graph_edges"]) > 2000
    assert q1 and q1[0]["is_best_path"]
    assert serious, "BATCH-007 影响链中没有严重不良事件，演示问题会落空"
    assert all(r["linked_ae_count"] > 0 for r in tables["gold_signal_evidence"])
    print(f"\n全部断言通过。问题目录 {len(QUESTION_CATALOG)} 条。")


if __name__ == "__main__":
    main()
