"""Build the CRF-to-SDTM lineage graph and answer the mapping questions.

Pure Python with no Spark dependency so the same code runs in local validation
and is inlined into the Fabric notebook at deploy time.

Mapping penalty is a dimensionless weight, not a monetary cost. It expresses how
much interpretation a transformation needs: a straight copy is trusted almost
completely, a conditional assignment or a coding step much less. Paths are ranked
by the accumulated penalty, so the cheapest path is the most directly traceable
one rather than merely the shortest.
"""

from __future__ import annotations

SPEC_VERSION_DEFAULT = "V2"

# 转换算法的映射折损：越小越直接可信
ALGORITHM_PENALTY = {
    "Copy": 0.02,          # 原样拷贝
    "CopyUpcase": 0.03,    # 拷贝并转大写
    "Assigned": 0.05,      # 常量赋值，不依赖源字段取值
    "DT2DTC": 0.10,        # 日期转 ISO8601
    "Lookup": 0.15,        # 查外部字典
    "IfAssigned": 0.20,    # 条件赋值，含分支逻辑
    "Coding": 0.25,        # 医学编码，依赖外部词典版本
    "Derived": 0.30,       # 计算派生，依赖多个输入
}
SUPP_SURCHARGE = 0.15      # 落在补充限定符域而非标准域
NO_CT_SURCHARGE = 0.10     # 目标变量无受控术语约束


class LineageGraph:
    def __init__(self, src: dict[tuple[str, str], list[dict]], version: str = SPEC_VERSION_DEFAULT):
        self.src = src
        self.version = version
        self.nodes: dict[str, dict] = {}
        self.edges: list[dict] = []

        self.domains = {d["domain"]: d for d in src[("spec", "sdtm_domains")]}
        self.variables = {(v["domain"], v["variable_name"]): v
                          for v in src[("spec", "sdtm_variables")]}
        self.fields = {(f["form_oid"], f["field_oid"]): f
                       for f in src[("spec", "crf_fields")] if f["version"] == version}
        self.forms = {f["form_oid"]: f for f in src[("spec", "crf_forms")]
                      if f["version"] == version}
        self.mappings = [m for m in src[("spec", "mapping_rules")] if m["version"] == version]
        self.derivations = src[("spec", "variable_derivations")]

    # ------------------------------------------------------------ 节点与边

    @staticmethod
    def field_id(form: str, field: str) -> str:
        return f"CRF:{form}.{field}"

    @staticmethod
    def var_id(domain: str, variable: str) -> str:
        return f"SDTM:{domain}.{variable}"

    def add_node(self, node_id, node_type, node_type_zh, name_zh, **attrs) -> None:
        if node_id in self.nodes:
            return
        self.nodes[node_id] = {
            "node_id": node_id,
            "node_type": node_type,
            "node_type_zh": node_type_zh,
            "display_name_zh": name_zh,
            "domain": attrs.get("domain"),
            "form_oid": attrs.get("form_oid"),
            "core": attrs.get("core"),
            "data_type": attrs.get("data_type"),
            "codelist": attrs.get("codelist"),
            "acrf_page": attrs.get("acrf_page"),
            "is_supplemental": attrs.get("is_supplemental"),
            "expected_origin": attrs.get("expected_origin"),
            "spec_version": self.version,
        }

    def add_edge(self, source, target, rel_type, rel_type_zh, algorithm=None,
                 condition=None, rule_id=None, penalty=0.01) -> None:
        if source not in self.nodes or target not in self.nodes:
            return
        self.edges.append({
            "edge_id": f"E{len(self.edges) + 1:05d}",
            "source_node_id": source,
            "target_node_id": target,
            "relationship_type": rel_type,
            "relationship_type_zh": rel_type_zh,
            "algorithm": algorithm,
            "condition_zh": condition or "",
            "rule_id": rule_id or "",
            "mapping_penalty": round(penalty, 4),
            "spec_version": self.version,
        })

    def _penalty(self, algorithm: str, domain: str, variable: str) -> float:
        p = ALGORITHM_PENALTY.get(algorithm, 0.30)
        if self.domains.get(domain, {}).get("is_supplemental") == "是":
            p += SUPP_SURCHARGE
        if not (self.variables.get((domain, variable), {}).get("codelist") or ""):
            p += NO_CT_SURCHARGE
        return p

    def build(self) -> dict[str, list[dict]]:
        for form in self.forms.values():
            self.add_node(f"FORM:{form['form_oid']}", "CRFForm", "CRF 表单",
                          form["form_name_zh"], form_oid=form["form_oid"],
                          acrf_page=form["page"])

        for field in self.fields.values():
            self.add_node(self.field_id(field["form_oid"], field["field_oid"]),
                          "CRFField", "CRF 字段", field["field_label_zh"],
                          form_oid=field["form_oid"], data_type=field["field_type"],
                          codelist=field["codelist"], acrf_page=field["acrf_page"])
            self.add_edge(f"FORM:{field['form_oid']}",
                          self.field_id(field["form_oid"], field["field_oid"]),
                          "HAS_FIELD", "包含字段")

        for domain in self.domains.values():
            self.add_node(f"DOMAIN:{domain['domain']}", "SDTMDomain", "SDTM 域",
                          f"{domain['domain']} {domain['domain_label_zh']}",
                          domain=domain["domain"],
                          is_supplemental=domain["is_supplemental"])

        for (domain, name), var in self.variables.items():
            self.add_node(self.var_id(domain, name), "SDTMVariable", "SDTM 变量",
                          f"{domain}.{name} {var['variable_label_zh']}",
                          domain=domain, core=var["core"],
                          data_type=var["data_type"], codelist=var["codelist"],
                          expected_origin=var.get("expected_origin"),
                          is_supplemental=self.domains[domain]["is_supplemental"])
            self.add_edge(self.var_id(domain, name), f"DOMAIN:{domain}",
                          "BELONGS_TO", "属于域")

        for rule in self.mappings:
            source = self.field_id(rule["form_oid"], rule["field_oid"])
            target = self.var_id(rule["target_domain"], rule["target_variable"])
            self.add_edge(source, target, "MAPS_TO", "映射到",
                          algorithm=rule["algorithm"], condition=rule["condition_zh"],
                          rule_id=rule["rule_id"],
                          penalty=self._penalty(rule["algorithm"], rule["target_domain"],
                                                rule["target_variable"]))

        for d in self.derivations:
            source = self.var_id(d["source_domain"], d["source_variable"])
            target = self.var_id(d["target_domain"], d["target_variable"])
            self.add_edge(source, target, "DERIVES", "派生出",
                          algorithm=d["algorithm"], condition=d["note_zh"],
                          penalty=self._penalty(d["algorithm"], d["target_domain"],
                                                d["target_variable"]))

        self._adj = {}
        for e in self.edges:
            self._adj.setdefault(e["source_node_id"], []).append(e)
        self._radj = {}
        for e in self.edges:
            self._radj.setdefault(e["target_node_id"], []).append(e)

        return {"lineage_nodes": list(self.nodes.values()),
                "lineage_edges": self.edges}

    # ------------------------------------------------------------ 路径遍历

    def paths_to_variable(self, target: str, max_hops: int = 4) -> list[list[dict]]:
        """Enumerate CRF-field-rooted paths that reach the target variable."""
        results: list[list[dict]] = []

        def walk(node: str, trail: list[dict], seen: set[str]) -> None:
            for edge in self._radj.get(node, []):
                if edge["relationship_type"] not in ("MAPS_TO", "DERIVES"):
                    continue
                prev = edge["source_node_id"]
                if prev in seen or len(trail) >= max_hops:
                    continue
                new_trail = [edge] + trail
                if self.nodes[prev]["node_type"] == "CRFField":
                    results.append(new_trail)
                else:
                    walk(prev, new_trail, seen | {prev})

        walk(target, [], {target})
        return results

    def downstream(self, start: str, max_hops: int = 4) -> list[list[dict]]:
        """Enumerate everything reachable from a CRF field or SDTM variable."""
        results: list[list[dict]] = []

        def walk(node: str, trail: list[dict], seen: set[str]) -> None:
            for edge in self._adj.get(node, []):
                if edge["relationship_type"] not in ("MAPS_TO", "DERIVES"):
                    continue
                nxt = edge["target_node_id"]
                if nxt in seen or len(trail) >= max_hops:
                    continue
                results.append(trail + [edge])
                walk(nxt, trail + [edge], seen | {nxt})

        walk(start, [], {start})
        return results

    def describe(self, trail: list[dict]) -> dict:
        ids = [trail[0]["source_node_id"]] + [e["target_node_id"] for e in trail]
        algorithms = [e["algorithm"] for e in trail if e["algorithm"]]
        return {
            "path_node_ids": " -> ".join(ids),
            "path_display_zh": " -> ".join(self.nodes[i]["display_name_zh"] for i in ids),
            "hop_count": len(trail),
            "total_mapping_penalty": round(sum(e["mapping_penalty"] for e in trail), 4),
            "algorithms": " -> ".join(algorithms),
            "leading_condition_zh": trail[0]["condition_zh"],
            "worst_algorithm": max(algorithms, key=lambda a: ALGORITHM_PENALTY.get(a, 0.3))
            if algorithms else "",
            "passes_supplemental": any(
                self.nodes[i].get("is_supplemental") == "是" for i in ids),
        }


# ---------------------------------------------------------------- 五类分析

def gold_variable_lineage(g: LineageGraph) -> list[dict]:
    """Q1 反向溯源：每个 SDTM 变量的全部 CRF 来源路径，按映射折损排序。"""
    out = []
    for (domain, name), var in g.variables.items():
        target = g.var_id(domain, name)
        paths = [g.describe(t) for t in g.paths_to_variable(target)]
        if not paths:
            continue
        paths.sort(key=lambda p: (p["total_mapping_penalty"], p["hop_count"]))
        for rank, p in enumerate(paths, start=1):
            out.append({
                "spec_version": g.version,
                "target_domain": domain,
                "target_variable": name,
                "target_label_zh": var["variable_label_zh"],
                "core": var["core"],
                "path_rank": rank,
                "is_best_path": rank == 1,
                "source_count": len(paths),
                **p,
            })
    return out


def gold_field_impact(g: LineageGraph) -> list[dict]:
    """Q2 影响分析：修改某个 CRF 字段会波及哪些变量与数据集。"""
    out = []
    for (form, field), meta in g.fields.items():
        start = g.field_id(form, field)
        trails = g.downstream(start)
        if not trails:
            continue
        variables, domains = set(), set()
        for t in trails:
            node = g.nodes[t[-1]["target_node_id"]]
            if node["node_type"] == "SDTMVariable":
                variables.add(node["node_id"])
                domains.add(node["domain"])
        deepest = max(trails, key=lambda t: len(t))
        out.append({
            "spec_version": g.version,
            "form_oid": form,
            "form_name_zh": g.forms[form]["form_name_zh"],
            "field_oid": field,
            "field_label_zh": meta["field_label_zh"],
            "acrf_page": int(meta["acrf_page"]),
            "impacted_variable_count": len(variables),
            "impacted_domain_count": len(domains),
            "impacted_domains": "、".join(sorted(domains)),
            "impacted_variables": "、".join(
                sorted(v.replace("SDTM:", "") for v in variables)),
            "max_hop_depth": len(deepest),
            "deepest_path_zh": g.describe(deepest)["path_display_zh"],
        })
    out.sort(key=lambda r: r["impacted_variable_count"], reverse=True)
    return out


def gold_version_diff(src, v1: str = "V1", v2: str = "V2") -> list[dict]:
    """Q3 版本对比：两个规范版本之间新增、删除与算法变更的映射。"""
    def key(m):
        return (m["form_oid"], m["field_oid"], m["target_domain"], m["target_variable"])

    a = {key(m): m for m in src[("spec", "mapping_rules")] if m["version"] == v1}
    b = {key(m): m for m in src[("spec", "mapping_rules")] if m["version"] == v2}

    out = []
    for k in sorted(set(a) | set(b)):
        old, new = a.get(k), b.get(k)
        if old and new and old["algorithm"] == new["algorithm"]:
            continue
        if old and new:
            change, detail = "算法变更", f"{old['algorithm']} -> {new['algorithm']}"
        elif new:
            change, detail = f"{v2} 新增", new["algorithm"]
        else:
            change, detail = f"{v2} 移除", old["algorithm"]
        ref = new or old
        out.append({
            "from_version": v1, "to_version": v2,
            "change_type_zh": change, "detail": detail,
            "form_oid": k[0], "field_oid": k[1],
            "target_domain": k[2], "target_variable": k[3],
            "annotation_text": ref["annotation_text"],
        })
    return out


def gold_coverage_gap(g: LineageGraph, lineage: list[dict]) -> list[dict]:
    """Q4 覆盖缺口：哪些变量没有任何 CRF 来源，必填的优先。

    系统赋值类变量（STUDYID、DOMAIN、USUBJID 等）本就不由 CRF 采集，
    计入缺口会淹没真正需要处理的项，因此单独标识并排除。
    """
    covered = {(r["target_domain"], r["target_variable"]) for r in lineage}
    priority = {"Req": 1, "Exp": 2, "Perm": 3}
    out = []
    for (domain, name), var in g.variables.items():
        if (domain, name) in covered:
            continue
        if var.get("expected_origin") == "系统赋值":
            continue
        out.append({
            "spec_version": g.version,
            "domain": domain,
            "variable_name": name,
            "variable_label_zh": var["variable_label_zh"],
            "core": var["core"],
            "expected_origin": var.get("expected_origin", ""),
            "gap_priority": priority.get(var["core"], 9),
            "suggestion_zh": {
                "Req": "必填变量缺少来源，需补充映射或确认采集方式",
                "Exp": "预期变量缺少来源，建议确认是否适用于本研究",
                "Perm": "可选变量，未映射通常可接受",
            }.get(var["core"], "待确认"),
        })
    out.sort(key=lambda r: (r["gap_priority"], r["domain"], r["variable_name"]))
    return out


def gold_supp_promotion(g: LineageGraph, lineage: list[dict]) -> list[dict]:
    """Q5 补充限定符上提候选：落在 SUPP 域的映射，评估能否移入标准域。"""
    out = []
    for r in lineage:
        if g.domains.get(r["target_domain"], {}).get("is_supplemental") != "是":
            continue
        if not r["is_best_path"]:
            continue
        parent = g.domains[r["target_domain"]]["parent_domain"]
        rule = next((m for m in g.mappings
                     if m["target_domain"] == r["target_domain"]
                     and r["path_node_ids"].split(" -> ")[0].endswith(m["field_oid"])), None)
        out.append({
            "spec_version": g.version,
            "supp_domain": r["target_domain"],
            "parent_domain": parent,
            "qnam": rule["qnam"] if rule else "",
            "source_path_zh": r["path_display_zh"],
            "total_mapping_penalty": r["total_mapping_penalty"],
            "algorithms": r["algorithms"],
            "promotion_note_zh": (
                f"当前落在 {r['target_domain']}，若 {parent} 域存在语义相符的标准变量，"
                "上提后可去除补充限定符折损，下游消费更简单"),
        })
    out.sort(key=lambda r: r["total_mapping_penalty"], reverse=True)
    return out


def gold_algorithm_usage(g: LineageGraph) -> list[dict]:
    """Per-hop算法使用分布。

    存在的理由是防一个具体的错答：gold_variable_lineage.algorithms 存的是整条
    路径的算法串（如 "DT2DTC -> Derived"），按它分组统计出来的不是"某个算法用了
    多少次"，而是"某种算法组合出现了多少条路径"。两者数字完全不同，但后者看起来
    很像答案，问答时极易被当成前者给出去。把正确口径预先算好，让 SQL 也能答对。
    """
    rows: dict[str, dict] = {}
    for e in g.edges:
        if e["relationship_type"] not in ("MAPS_TO", "DERIVES") or not e["algorithm"]:
            continue
        r = rows.setdefault(e["algorithm"], {
            "spec_version": g.version,
            "algorithm": e["algorithm"],
            "usage_count": 0,
            "mapping_count": 0,
            "derivation_count": 0,
            "unit_penalty": ALGORITHM_PENALTY.get(e["algorithm"], 0.30),
            "meaning_zh": {
                "Copy": "原样拷贝，不做任何转换",
                "CopyUpcase": "拷贝并转为大写",
                "Assigned": "赋常量，不依赖源字段取值",
                "DT2DTC": "日期转 ISO8601 标准格式",
                "Lookup": "查外部字典换取标准值",
                "IfAssigned": "按条件分支赋值",
                "Coding": "医学编码，依赖外部词典版本",
                "Derived": "由一个或多个变量计算得出",
            }.get(e["algorithm"], "待补充说明"),
        })
        r["usage_count"] += 1
        if e["relationship_type"] == "MAPS_TO":
            r["mapping_count"] += 1
        else:
            r["derivation_count"] += 1

    out = sorted(rows.values(), key=lambda r: r["usage_count"], reverse=True)
    for r in out:
        r["counting_basis_zh"] = "按单跳统计：一条边算一次，不是按整条路径的算法组合统计"
    return out


QUESTION_CATALOG = [
    {"question_id": "L1", "category_zh": "反向溯源",
     "question_zh": "DM 域的治疗组代码 ARMCD 是从哪个字段来的？有几条来源，哪条最直接？",
     "answer_table": "gold_variable_lineage",
     "guidance_zh": "按 total_mapping_penalty 升序，is_best_path 为真的是最直接的来源。"
                    "映射折损是无量纲指标，衡量转换需要多少解释，与费用无关。"},
    {"question_id": "L2", "category_zh": "影响分析",
     "question_zh": "如果修改给药开始日期这个字段，会影响哪些 SDTM 变量和数据集？",
     "answer_table": "gold_field_impact",
     "guidance_zh": "按 impacted_variable_count 降序，deepest_path_zh 给出最长影响链。"},
    {"question_id": "L3", "category_zh": "版本对比",
     "question_zh": "规范从 V1 升到 V2，映射规则有哪些变化？",
     "answer_table": "gold_version_diff",
     "guidance_zh": "change_type_zh 区分新增、移除与算法变更。"},
    {"question_id": "L4", "category_zh": "覆盖缺口",
     "question_zh": "还有哪些必填的 SDTM 变量没有对应的 CRF 采集来源？",
     "answer_table": "gold_coverage_gap",
     "guidance_zh": "gap_priority 为 1 的是必填变量，应优先处理。"},
    {"question_id": "L5", "category_zh": "补充限定符治理",
     "question_zh": "哪些数据落在了补充限定符域？有没有可能上提到标准域？",
     "answer_table": "gold_supp_promotion",
     "guidance_zh": "按 total_mapping_penalty 降序，折损高的上提收益大。"},
    {"question_id": "L6", "category_zh": "多来源歧义",
     "question_zh": "DS.DSSTDTC 有多个表单都在往里写，分别是哪些？靠什么条件区分？",
     "answer_table": "gold_variable_lineage",
     "guidance_zh": "source_count 大于 1 说明多来源；此时各条路径并非优劣关系，"
                    "而是分别对应不同的处置事件，应结合 condition_zh 说明区分条件。"},
    {"question_id": "L7", "category_zh": "转换方式分布",
     "question_zh": "我们的映射里各种转换方式分别用了多少次？哪些是需要人工解释的？",
     "answer_table": "gold_algorithm_usage",
     "guidance_zh": "usage_count 是按单跳统计的次数。不要用 gold_variable_lineage 的 "
                    "algorithms 列分组代替，那一列是整条路径的算法串，"
                    "统计出来是路径组合数而不是算法使用次数，口径完全不同。"},
]
