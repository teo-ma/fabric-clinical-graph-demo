"""Pure-Python clinical knowledge graph construction and business analytics.

No Spark or Fabric dependency, so the exact same code runs in local validation
and is inlined into the Fabric notebook at deploy time. Keeping one copy avoids
the two implementations drifting apart.

Input is a mapping of (source_system, table_name) -> list of row dicts.
Output is the unified graph plus the gold tables that answer the demo questions.
"""

from __future__ import annotations

DATA_VERSION = 1
GRADE_PENALTY = {"A": 0.0, "B": 0.05, "C": 0.15, "D": 0.30}
# Records from transactional systems are facts, not evidence claims, so they carry
# a near-zero penalty that still keeps shorter operational chains preferred.
OPERATIONAL_PENALTY = 0.01
KNOWLEDGE_TYPES = ["Compound", "Target", "Pathway", "Biomarker", "AEType"]


class ClinicalGraph:
    def __init__(self, src: dict[tuple[str, str], list[dict]]):
        self.src = src
        self.nodes: dict[str, dict] = {}
        self.edges: list[dict] = []
        self.ae_pt = {r["pt_code"]: r["pt_name_zh"] for r in src[("knowledge", "ae_terms")]}
        self.bm_name = {r["biomarker_id"]: r["biomarker_name_zh"]
                        for r in src[("knowledge", "biomarkers")]}
        self.abnormal_labs = [r for r in src[("lims", "lab_results")]
                              if r["abnormal_flag"] == "异常"]

    # ------------------------------------------------------------ building

    def add_node(self, node_id, node_type, node_type_zh, name_zh, source_system,
                 study_id=None, category=None, status=None,
                 numeric_value=None, event_date=None) -> None:
        if node_id is None or str(node_id) in self.nodes:
            return
        self.nodes[str(node_id)] = {
            "node_id": str(node_id),
            "node_type": node_type,
            "node_type_zh": node_type_zh,
            "display_name_zh": str(name_zh),
            "source_system": source_system,
            "study_id": study_id,
            "category": category,
            "status": status,
            "numeric_value": float(numeric_value) if numeric_value is not None else None,
            "event_date": str(event_date) if event_date is not None else None,
            "data_version": DATA_VERSION,
        }

    def add_edge(self, source, target, rel_type, rel_type_zh, source_system,
                 evidence_grade="A", confidence=1.0, knowledge=False) -> None:
        if source is None or target is None:
            return
        if str(source) not in self.nodes or str(target) not in self.nodes:
            return
        # Evidence penalty is a dimensionless uncertainty weight, not a monetary cost.
        penalty = (round((1.0 - float(confidence)) + GRADE_PENALTY.get(evidence_grade, 0.3), 4)
                   if knowledge else OPERATIONAL_PENALTY)
        self.edges.append({
            "edge_id": f"E{len(self.edges) + 1:06d}",
            "source_node_id": str(source),
            "target_node_id": str(target),
            "relationship_type": rel_type,
            "relationship_type_zh": rel_type_zh,
            "evidence_grade": evidence_grade,
            "confidence": round(float(confidence), 4),
            "evidence_penalty": penalty,
            "edge_class": "知识" if knowledge else "运营",
            "source_system": source_system,
            "data_version": DATA_VERSION,
        })

    def build_nodes(self) -> None:
        s = self.src
        for r in s[("knowledge", "compounds")]:
            self.add_node(r["compound_id"], "Compound", "化合物", r["compound_name_zh"],
                          "knowledge", category=r["modality"], status=r["dev_phase"])
        for r in s[("knowledge", "targets")]:
            self.add_node(r["target_id"], "Target", "靶点", r["target_name_zh"],
                          "knowledge", category=r["gene_symbol"])
        for r in s[("knowledge", "pathways")]:
            self.add_node(r["pathway_id"], "Pathway", "生物通路", r["pathway_name_zh"], "knowledge")
        for r in s[("knowledge", "biomarkers")]:
            self.add_node(r["biomarker_id"], "Biomarker", "生物标志物", r["biomarker_name_zh"],
                          "knowledge", category=r["analyte_code"],
                          numeric_value=r["upper_normal_limit"])
        for r in s[("knowledge", "ae_terms")]:
            self.add_node(r["pt_code"], "AEType", "不良事件术语", r["pt_name_zh"],
                          "knowledge", category=r["soc_name_zh"])

        for r in s[("ctms", "studies")]:
            self.add_node(r["study_id"], "Study", "临床研究", r["protocol_no"], "ctms",
                          study_id=r["study_id"], category=r["indication_zh"],
                          status=r["study_status"])
        for r in s[("ctms", "investigators")]:
            self.add_node(r["investigator_id"], "Investigator", "研究者",
                          r["investigator_name"], "ctms", category=r["specialty_zh"])
        for r in s[("ctms", "sites")]:
            self.add_node(r["site_id"], "Site", "研究中心", r["site_name_zh"], "ctms",
                          study_id=r["study_id"], category=r["country"], status=r["site_status"])
        for r in s[("ctms", "subjects")]:
            self.add_node(r["subject_id"], "Subject", "受试者", f"受试者 {r['subject_id']}",
                          "ctms", study_id=r["study_id"], category=r["treatment_arm"],
                          status=r["subject_status"])
        for r in s[("ctms", "protocol_deviations")]:
            self.add_node(r["deviation_id"], "ProtocolDeviation", "方案偏离",
                          r["deviation_category_zh"], "ctms", study_id=r["study_id"],
                          category=r["deviation_severity"], event_date=r["deviation_date"])

        for r in s[("edc", "visits")]:
            self.add_node(r["visit_id"], "Visit", "访视",
                          f"{r['visit_name_zh']}（{r['subject_id']}）", "edc",
                          study_id=r["study_id"], category=r["visit_name_zh"],
                          event_date=r["visit_date"])

        for r in s[("supply", "batches")]:
            self.add_node(r["batch_id"], "Batch", "药品批次", r["batch_id"], "supply",
                          status=r["qc_status_zh"], event_date=r["manufacture_date"])
        for r in s[("supply", "shipments")]:
            self.add_node(r["shipment_id"], "Shipment", "运单", r["shipment_id"], "supply",
                          category=("温度偏移" if r["temperature_excursion_flag"] == "是" else "正常"),
                          status=r["temperature_excursion_flag"], event_date=r["ship_date"])

        for r in s[("safety", "adverse_events")]:
            self.add_node(r["ae_id"], "AdverseEvent", "不良事件",
                          f"{self.ae_pt.get(r['pt_code'], r['pt_code'])}（{r['subject_id']}）",
                          "safety", study_id=r["study_id"],
                          category=("严重" if r["serious_flag"] == "是" else "非严重"),
                          status=r["causality_zh"], numeric_value=r["ctcae_grade"],
                          event_date=r["onset_date"])
        for r in s[("safety", "safety_signals")]:
            self.add_node(r["signal_id"], "SafetySignal", "安全信号",
                          f"{self.ae_pt.get(r['pt_code'], r['pt_code'])} 信号", "safety",
                          category=r["evidence_grade"], status=r["signal_status_zh"],
                          event_date=r["detected_date"])

        # Only abnormal lab results become graph nodes; normal results stay in the
        # source table so the graph keeps a workable size for interactive queries.
        for r in self.abnormal_labs:
            self.add_node(r["lab_id"], "LabResult", "异常检验结果",
                          f"{self.bm_name.get(r['biomarker_id'], r['biomarker_id'])} 异常",
                          "lims", category=r["biomarker_id"],
                          numeric_value=r["result_value"], event_date=r["collected_date"])

    def build_edges(self) -> None:
        s = self.src
        for r in s[("knowledge", "compound_target")]:
            self.add_edge(r["compound_id"], r["target_id"], "ACTS_ON", "作用于", "knowledge",
                          r["evidence_grade"], r["confidence"], knowledge=True)
        for r in s[("knowledge", "target_pathway")]:
            self.add_edge(r["target_id"], r["pathway_id"], "PARTICIPATES_IN", "参与", "knowledge",
                          r["evidence_grade"], r["confidence"], knowledge=True)
        for r in s[("knowledge", "pathway_biomarker")]:
            self.add_edge(r["pathway_id"], r["biomarker_id"], "REGULATES", "调控", "knowledge",
                          r["evidence_grade"], r["confidence"], knowledge=True)
        for r in s[("knowledge", "biomarker_ae")]:
            self.add_edge(r["biomarker_id"], r["pt_code"], "INDICATES_RISK", "提示风险",
                          "knowledge", r["evidence_grade"], r["confidence"], knowledge=True)

        for r in s[("ctms", "studies")]:
            self.add_edge(r["study_id"], r["compound_id"], "STUDIES_COMPOUND", "研究药物", "ctms")
        for r in s[("ctms", "sites")]:
            self.add_edge(r["study_id"], r["site_id"], "HAS_SITE", "包含中心", "ctms")
            self.add_edge(r["site_id"], r["investigator_id"], "LED_BY", "由研究者负责", "ctms")
        for r in s[("ctms", "subjects")]:
            self.add_edge(r["subject_id"], r["study_id"], "ENROLLED_IN", "入组", "ctms")
            self.add_edge(r["subject_id"], r["site_id"], "TREATED_AT", "就诊于", "ctms")
        for r in s[("ctms", "protocol_deviations")]:
            self.add_edge(r["deviation_id"], r["site_id"], "OCCURRED_AT", "发生于", "ctms")
            self.add_edge(r["deviation_id"], r["subject_id"], "AFFECTS", "涉及", "ctms")

        for r in s[("edc", "visits")]:
            self.add_edge(r["subject_id"], r["visit_id"], "HAS_VISIT", "产生访视", "edc")
        for r in s[("edc", "dosing_records")]:
            self.add_edge(r["visit_id"], r["batch_id"], "USED_BATCH", "使用批次", "edc")

        for r in self.abnormal_labs:
            self.add_edge(r["visit_id"], r["lab_id"], "HAS_LAB_RESULT", "产生检验", "lims")
            self.add_edge(r["lab_id"], r["biomarker_id"], "MEASURES", "检测指标", "lims")

        for r in s[("safety", "adverse_events")]:
            self.add_edge(r["subject_id"], r["ae_id"], "EXPERIENCED", "发生", "safety")
            self.add_edge(r["ae_id"], r["pt_code"], "CODED_AS", "编码为", "safety")
        for r in s[("safety", "ae_signal_links")]:
            self.add_edge(r["ae_id"], r["signal_id"], "SUPPORTS_SIGNAL", "支持信号", "safety")
        for r in s[("safety", "safety_signals")]:
            self.add_edge(r["signal_id"], r["compound_id"], "SIGNAL_ABOUT", "针对药物", "safety")

        for r in s[("supply", "batches")]:
            self.add_edge(r["batch_id"], r["compound_id"], "BATCH_OF", "批次药物", "supply")
        for r in s[("supply", "shipments")]:
            self.add_edge(r["batch_id"], r["shipment_id"], "SHIPPED_AS", "发运", "supply")
            self.add_edge(r["shipment_id"], r["site_id"], "DELIVERED_TO", "送达", "supply")

    # ----------------------------------------------------------- traversal

    def _adjacency(self) -> dict[str, list[dict]]:
        adj: dict[str, list[dict]] = {}
        for e in self.edges:
            adj.setdefault(e["source_node_id"], []).append(e)
        return adj

    def typed_paths(self, start: str, type_sequence: list[str]) -> list[list[dict]]:
        adj = self._adj
        results: list[list[dict]] = []

        def walk(current: str, depth: int, trail: list[dict], seen: set[str]) -> None:
            if depth == len(type_sequence) - 1:
                results.append(list(trail))
                return
            for edge in adj.get(current, []):
                nxt = edge["target_node_id"]
                if nxt in seen or self.nodes[nxt]["node_type"] != type_sequence[depth + 1]:
                    continue
                trail.append(edge)
                seen.add(nxt)
                walk(nxt, depth + 1, trail, seen)
                trail.pop()
                seen.remove(nxt)

        walk(start, 0, [], {start})
        return results

    def _summarize(self, start: str, trail: list[dict]) -> dict:
        ids = [start] + [e["target_node_id"] for e in trail]
        grades = [e["evidence_grade"] for e in trail]
        return {
            "path_node_ids": " -> ".join(ids),
            "path_display_zh": " -> ".join(self.nodes[i]["display_name_zh"] for i in ids),
            "hop_count": len(trail),
            "total_evidence_penalty": round(sum(e["evidence_penalty"] for e in trail), 4),
            "worst_evidence_grade": max(grades) if grades else "A",
            "min_confidence": round(min(e["confidence"] for e in trail), 4),
        }

    # ------------------------------------------------------------ analytics

    def mechanism_paths(self) -> list[dict]:
        out = []
        for compound in [n for n in self.nodes.values() if n["node_type"] == "Compound"]:
            grouped: dict[str, list[dict]] = {}
            for trail in self.typed_paths(compound["node_id"], KNOWLEDGE_TYPES):
                grouped.setdefault(trail[-1]["target_node_id"], []).append(
                    self._summarize(compound["node_id"], trail))
            for ae_code, paths in grouped.items():
                paths.sort(key=lambda p: (p["total_evidence_penalty"], p["hop_count"]))
                for rank, p in enumerate(paths, start=1):
                    out.append({
                        "compound_id": compound["node_id"],
                        "compound_name_zh": compound["display_name_zh"],
                        "ae_pt_code": ae_code,
                        "ae_pt_name_zh": self.nodes[ae_code]["display_name_zh"],
                        "path_rank": rank,
                        "is_best_path": rank == 1,
                        **p,
                        "data_version": DATA_VERSION,
                    })
        return out

    def batch_impact(self) -> list[dict]:
        s = self.src
        subject_row = {r["subject_id"]: r for r in s[("ctms", "subjects")]}
        site_row = {r["site_id"]: r for r in s[("ctms", "sites")]}
        batch_to_subjects: dict[str, set[str]] = {}
        for r in s[("edc", "dosing_records")]:
            batch_to_subjects.setdefault(r["batch_id"], set()).add(r["subject_id"])
        ae_by_subject: dict[str, list[dict]] = {}
        for r in s[("safety", "adverse_events")]:
            ae_by_subject.setdefault(r["subject_id"], []).append(r)

        out = []
        for ship in [r for r in s[("supply", "shipments")]
                     if r["temperature_excursion_flag"] == "是"]:
            for subject_id in sorted(batch_to_subjects.get(ship["batch_id"], set())):
                subj = subject_row[subject_id]
                if subj["site_id"] != ship["site_id"]:
                    continue
                for ae in ae_by_subject.get(subject_id, []) or [None]:
                    out.append({
                        "batch_id": ship["batch_id"],
                        "shipment_id": ship["shipment_id"],
                        "site_id": ship["site_id"],
                        "site_name_zh": site_row[ship["site_id"]]["site_name_zh"],
                        "study_id": subj["study_id"],
                        "subject_id": subject_id,
                        "treatment_arm": subj["treatment_arm"],
                        "ae_id": ae["ae_id"] if ae else None,
                        "ae_pt_name_zh": self.ae_pt.get(ae["pt_code"]) if ae else None,
                        "serious_flag": ae["serious_flag"] if ae else None,
                        "ctcae_grade": int(ae["ctcae_grade"]) if ae else None,
                        "causality_zh": ae["causality_zh"] if ae else None,
                        "impact_path_zh": " -> ".join(
                            [ship["batch_id"], ship["shipment_id"],
                             site_row[ship["site_id"]]["site_name_zh"], subject_id]
                            + ([self.ae_pt.get(ae["pt_code"], "")] if ae else [])),
                        "data_version": DATA_VERSION,
                    })
        return out

    def signal_evidence(self, mechanism_rows: list[dict]) -> list[dict]:
        s = self.src
        ae_row = {r["ae_id"]: r for r in s[("safety", "adverse_events")]}
        subject_row = {r["subject_id"]: r for r in s[("ctms", "subjects")]}
        labs_by_subject: dict[str, list[dict]] = {}
        for r in s[("lims", "lab_results")]:
            labs_by_subject.setdefault(r["subject_id"], []).append(r)
        pt_biomarkers: dict[str, list[str]] = {}
        for r in s[("knowledge", "biomarker_ae")]:
            pt_biomarkers.setdefault(r["pt_code"], []).append(r["biomarker_id"])
        best = {(r["compound_id"], r["ae_pt_code"]): r
                for r in mechanism_rows if r["is_best_path"]}

        out = []
        for sig in s[("safety", "safety_signals")]:
            linked = [ae_row[l["ae_id"]] for l in s[("safety", "ae_signal_links")]
                      if l["signal_id"] == sig["signal_id"] and l["ae_id"] in ae_row]
            subjects = {a["subject_id"] for a in linked}
            sites = {subject_row[x]["site_id"] for x in subjects if x in subject_row}
            relevant = set(pt_biomarkers.get(sig["pt_code"], []))
            abnormal = [l for x in subjects for l in labs_by_subject.get(x, [])
                        if l["abnormal_flag"] == "异常" and l["biomarker_id"] in relevant]
            mech = best.get((sig["compound_id"], sig["pt_code"]))
            out.append({
                "signal_id": sig["signal_id"],
                "compound_id": sig["compound_id"],
                "compound_name_zh": self.nodes[sig["compound_id"]]["display_name_zh"],
                "ae_pt_code": sig["pt_code"],
                "ae_pt_name_zh": self.ae_pt.get(sig["pt_code"]),
                "signal_status_zh": sig["signal_status_zh"],
                "signal_evidence_grade": sig["evidence_grade"],
                "linked_ae_count": len(linked),
                "serious_ae_count": sum(1 for a in linked if a["serious_flag"] == "是"),
                "affected_subject_count": len(subjects),
                "affected_site_count": len(sites),
                "supporting_abnormal_lab_count": len(abnormal),
                "supporting_biomarkers_zh": "、".join(
                    sorted({self.bm_name.get(b, b) for b in relevant})),
                "best_mechanism_path_zh": mech["path_display_zh"] if mech else None,
                "best_mechanism_penalty": mech["total_evidence_penalty"] if mech else None,
                "data_version": DATA_VERSION,
            })
        return out

    def target_crosstalk(self, mechanism_rows: list[dict]) -> list[dict]:
        s = self.src
        compound_targets: dict[str, set[str]] = {}
        for r in s[("knowledge", "compound_target")]:
            compound_targets.setdefault(r["compound_id"], set()).add(r["target_id"])
        target_pathways: dict[str, set[str]] = {}
        for r in s[("knowledge", "target_pathway")]:
            target_pathways.setdefault(r["target_id"], set()).add(r["pathway_id"])
        study_by_compound: dict[str, list[str]] = {}
        for r in s[("ctms", "studies")]:
            study_by_compound.setdefault(r["compound_id"], []).append(r["protocol_no"])
        risks: dict[str, set[str]] = {}
        for r in mechanism_rows:
            risks.setdefault(r["compound_id"], set()).add(r["ae_pt_code"])

        out = []
        ids = sorted(compound_targets)
        for a in ids:
            for b in ids:
                if a >= b:
                    continue
                shared_targets = compound_targets[a] & compound_targets[b]
                pa = {p for t in compound_targets[a] for p in target_pathways.get(t, set())}
                pb = {p for t in compound_targets[b] for p in target_pathways.get(t, set())}
                shared_pathways = pa & pb
                if not shared_targets and not shared_pathways:
                    continue
                shared_risks = sorted(risks.get(a, set()) & risks.get(b, set()))
                out.append({
                    "compound_a": a,
                    "compound_a_name_zh": self.nodes[a]["display_name_zh"],
                    "compound_b": b,
                    "compound_b_name_zh": self.nodes[b]["display_name_zh"],
                    "shared_target_count": len(shared_targets),
                    "shared_targets_zh": "、".join(
                        sorted(self.nodes[t]["display_name_zh"] for t in shared_targets)),
                    "shared_pathway_count": len(shared_pathways),
                    "shared_pathways_zh": "、".join(
                        sorted(self.nodes[p]["display_name_zh"] for p in shared_pathways)),
                    "shared_risk_terms_zh": "、".join(
                        self.nodes[p]["display_name_zh"] for p in shared_risks),
                    "compound_a_studies": "、".join(study_by_compound.get(a, [])) or "无在研研究",
                    "compound_b_studies": "、".join(study_by_compound.get(b, [])) or "无在研研究",
                    "data_version": DATA_VERSION,
                })
        return out

    def site_risk(self) -> list[dict]:
        s = self.src
        dev_by_site: dict[str, list[dict]] = {}
        for r in s[("ctms", "protocol_deviations")]:
            dev_by_site.setdefault(r["site_id"], []).append(r)
        subjects_by_site: dict[str, list[dict]] = {}
        for r in s[("ctms", "subjects")]:
            subjects_by_site.setdefault(r["site_id"], []).append(r)
        ship_by_site: dict[str, list[dict]] = {}
        for r in s[("supply", "shipments")]:
            ship_by_site.setdefault(r["site_id"], []).append(r)
        ae_by_subject: dict[str, list[dict]] = {}
        for r in s[("safety", "adverse_events")]:
            ae_by_subject.setdefault(r["subject_id"], []).append(r)
        inv_name = {r["investigator_id"]: r["investigator_name"]
                    for r in s[("ctms", "investigators")]}

        out = []
        for site in s[("ctms", "sites")]:
            site_id = site["site_id"]
            site_subjects = subjects_by_site.get(site_id, [])
            subject_ids = {x["subject_id"] for x in site_subjects}
            site_aes = [a for x in subject_ids for a in ae_by_subject.get(x, [])]
            serious = [a for a in site_aes if a["serious_flag"] == "是"]
            devs = dev_by_site.get(site_id, [])
            important = [d for d in devs if d["deviation_severity"] == "重要"]
            excursions = [x for x in ship_by_site.get(site_id, [])
                          if x["temperature_excursion_flag"] == "是"]
            n = max(len(site_subjects), 1)
            risk = round(len(serious) / n * 60 + len(important) / n * 30 + len(excursions) * 4, 2)
            out.append({
                "site_id": site_id,
                "site_name_zh": site["site_name_zh"],
                "study_id": site["study_id"],
                "country": site["country"],
                "investigator_name": inv_name.get(site["investigator_id"]),
                "subject_count": len(site_subjects),
                "adverse_event_count": len(site_aes),
                "serious_ae_count": len(serious),
                "deviation_count": len(devs),
                "important_deviation_count": len(important),
                "temperature_excursion_count": len(excursions),
                "risk_score": risk,
                "risk_tier_zh": "高风险" if risk >= 60 else ("中风险" if risk >= 35 else "低风险"),
                "data_version": DATA_VERSION,
            })
        out.sort(key=lambda r: r["risk_score"], reverse=True)
        return out

    # ---------------------------------------------------------------- entry

    def build(self) -> dict[str, list[dict]]:
        self.build_nodes()
        self.build_edges()
        self._adj = self._adjacency()
        mechanism = self.mechanism_paths()
        return {
            "graph_nodes": list(self.nodes.values()),
            "graph_edges": self.edges,
            "gold_mechanism_paths": mechanism,
            "gold_batch_impact": self.batch_impact(),
            "gold_signal_evidence": self.signal_evidence(mechanism),
            "gold_target_crosstalk": self.target_crosstalk(mechanism),
            "gold_site_risk": self.site_risk(),
        }


QUESTION_CATALOG = [
    {"question_id": "Q1", "category_zh": "机制解释",
     "question_zh": "研究化合物 SYN-101 与药物性肝损伤之间有哪些机制通路？哪条证据最强？",
     "answer_table": "gold_mechanism_paths",
     "guidance_zh": "按 total_evidence_penalty 升序，is_best_path 为真的即为证据最强链路。该值为证据折损，无量纲，与费用无关。"},
    {"question_id": "Q2", "category_zh": "质量事件溯源",
     "question_zh": "批次 BATCH-007 发生温度偏移，影响了哪些中心和受试者？其中谁发生了严重不良事件？",
     "answer_table": "gold_batch_impact",
     "guidance_zh": "按 batch_id 过滤，serious_flag 为是的记录即严重不良事件。"},
    {"question_id": "Q3", "category_zh": "信号评估",
     "question_zh": "安全信号 SIG-002 的证据链是什么？涉及多少受试者和异常检验？",
     "answer_table": "gold_signal_evidence",
     "guidance_zh": "读取该信号行，包含关联不良事件数、受试者数、支持性异常检验数与机制路径。"},
    {"question_id": "Q4", "category_zh": "组合风险外推",
     "question_zh": "与 SYN-101 共享靶点或通路的其他在研化合物有哪些？可能共享哪些风险？",
     "answer_table": "gold_target_crosstalk",
     "guidance_zh": "筛选 compound_a 或 compound_b 为 CMP-001 的行。"},
    {"question_id": "Q5", "category_zh": "中心风险画像",
     "question_zh": "哪些研究中心风险最高？分别因为什么？",
     "answer_table": "gold_site_risk",
     "guidance_zh": "按 risk_score 降序，结合严重不良事件、重要方案偏离与温度偏移次数解释。"},
]
for _row in QUESTION_CATALOG:
    _row["data_version"] = DATA_VERSION
