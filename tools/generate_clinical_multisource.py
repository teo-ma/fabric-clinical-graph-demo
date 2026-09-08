"""Generate synthetic multi-source clinical development data for the Fabric demo.

All data is synthetic. No real patient, trial, or product information is used.
Compound and site names are invented and must not be read as real assets.

Six simulated source systems are produced, each into its own folder:

    ctms       Clinical Trial Management System
    edc        Electronic Data Capture
    safety     Pharmacovigilance / safety database
    lims       Central laboratory and biomarker results
    knowledge  Translational knowledge base
    supply     Clinical supply chain

The generator is deterministic so the demo answers are stable and verifiable.
Key mechanistic and traceability chains are planted explicitly rather than left
to chance, so that the business questions always have a correct answer.
"""

from __future__ import annotations

import csv
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

SEED = 20260908
ROOT = Path(__file__).resolve().parents[1] / "data" / "sources"

STUDY_START = date(2026, 1, 12)


def w(system: str, name: str, header: list[str], rows: list[list]) -> None:
    out = ROOT / system
    out.mkdir(parents=True, exist_ok=True)
    with (out / f"{name}.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(rows)
    print(f"{system}/{name}.csv  rows={len(rows)}")


@dataclass
class Ctx:
    rng: random.Random
    subjects: list[dict] = field(default_factory=list)
    visits: list[dict] = field(default_factory=list)
    labs: list[dict] = field(default_factory=list)
    aes: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------- knowledge

COMPOUNDS = [
    ("CMP-001", "SYN-101", "研究化合物 SYN-101", "小分子", "TGT-JAK1", "II期"),
    ("CMP-002", "SYN-102", "研究化合物 SYN-102", "小分子", "TGT-JAK1", "I期"),
    ("CMP-003", "SYN-201", "研究化合物 SYN-201", "单克隆抗体", "TGT-IL6R", "II期"),
    ("CMP-004", "SYN-301", "研究化合物 SYN-301", "抗体偶联药物", "TGT-HER2", "I期"),
    ("CMP-005", "SYN-401", "研究化合物 SYN-401", "小分子", "TGT-BTK", "II期"),
]

TARGETS = [
    ("TGT-JAK1", "JAK1", "Janus 激酶 1"),
    ("TGT-IL6R", "IL6R", "白介素6受体"),
    ("TGT-HER2", "ERBB2", "人表皮生长因子受体2"),
    ("TGT-BTK", "BTK", "布鲁顿酪氨酸激酶"),
    ("TGT-CYP3A4", "CYP3A4", "细胞色素P450 3A4"),
    ("TGT-HERG", "KCNH2", "hERG 钾离子通道"),
]

PATHWAYS = [
    ("PW-JAKSTAT", "JAK-STAT 信号通路"),
    ("PW-IL6INF", "IL-6 炎症通路"),
    ("PW-HER2SIG", "HER2 信号通路"),
    ("PW-BCRSIG", "B细胞受体信号通路"),
    ("PW-HEPMETAB", "肝药物代谢通路"),
    ("PW-CARDREPOL", "心肌复极通路"),
    ("PW-HEMATO", "骨髓造血通路"),
]

# target_id, pathway_id, evidence_grade, confidence
TARGET_PATHWAY = [
    ("TGT-JAK1", "PW-JAKSTAT", "A", 0.95),
    ("TGT-JAK1", "PW-HEMATO", "B", 0.81),
    ("TGT-IL6R", "PW-IL6INF", "A", 0.93),
    ("TGT-IL6R", "PW-HEPMETAB", "C", 0.64),
    ("TGT-HER2", "PW-HER2SIG", "A", 0.96),
    ("TGT-HER2", "PW-CARDREPOL", "B", 0.78),
    ("TGT-BTK", "PW-BCRSIG", "A", 0.94),
    ("TGT-BTK", "PW-HEMATO", "B", 0.80),
    ("TGT-CYP3A4", "PW-HEPMETAB", "A", 0.97),
    ("TGT-HERG", "PW-CARDREPOL", "A", 0.98),
]

BIOMARKERS = [
    ("BM-ALT", "ALT", "丙氨酸氨基转移酶", "U/L", 41.0),
    ("BM-AST", "AST", "天冬氨酸氨基转移酶", "U/L", 40.0),
    ("BM-TBIL", "TBIL", "总胆红素", "umol/L", 21.0),
    ("BM-QTCF", "QTCF", "QTcF 间期", "ms", 450.0),
    ("BM-ANC", "ANC", "中性粒细胞绝对值", "10^9/L", 2.0),
    ("BM-PLT", "PLT", "血小板计数", "10^9/L", 125.0),
    ("BM-CRP", "CRP", "C反应蛋白", "mg/L", 8.0),
    ("BM-IL6", "IL6", "白介素6", "pg/mL", 7.0),
]

# pathway_id, biomarker_id, direction, evidence_grade, confidence
PATHWAY_BIOMARKER = [
    ("PW-HEPMETAB", "BM-ALT", "升高", "A", 0.92),
    ("PW-HEPMETAB", "BM-AST", "升高", "A", 0.90),
    ("PW-HEPMETAB", "BM-TBIL", "升高", "B", 0.76),
    ("PW-JAKSTAT", "BM-ALT", "升高", "B", 0.71),
    ("PW-JAKSTAT", "BM-CRP", "降低", "A", 0.88),
    ("PW-IL6INF", "BM-CRP", "降低", "A", 0.94),
    ("PW-IL6INF", "BM-IL6", "升高", "A", 0.91),
    ("PW-CARDREPOL", "BM-QTCF", "延长", "A", 0.95),
    ("PW-HEMATO", "BM-ANC", "降低", "A", 0.93),
    ("PW-HEMATO", "BM-PLT", "降低", "B", 0.79),
    ("PW-HER2SIG", "BM-PLT", "降低", "C", 0.58),
    ("PW-BCRSIG", "BM-ANC", "降低", "B", 0.74),
]

AE_TERMS = [
    ("PT-DILI", "药物性肝损伤", "肝胆系统疾病"),
    ("PT-QTP", "QT间期延长", "心脏器官疾病"),
    ("PT-NEUT", "中性粒细胞减少症", "血液及淋巴系统疾病"),
    ("PT-THROM", "血小板减少症", "血液及淋巴系统疾病"),
    ("PT-IRR", "输注相关反应", "全身性疾病及给药部位反应"),
    ("PT-ILD", "间质性肺疾病", "呼吸系统疾病"),
    ("PT-RASH", "皮疹", "皮肤及皮下组织类疾病"),
]

# biomarker_id, pt_code, evidence_grade, confidence
BIOMARKER_AE = [
    ("BM-ALT", "PT-DILI", "A", 0.94),
    ("BM-AST", "PT-DILI", "A", 0.89),
    ("BM-TBIL", "PT-DILI", "A", 0.91),
    ("BM-QTCF", "PT-QTP", "A", 0.97),
    ("BM-ANC", "PT-NEUT", "A", 0.96),
    ("BM-PLT", "PT-THROM", "A", 0.95),
    ("BM-IL6", "PT-IRR", "B", 0.72),
    ("BM-CRP", "PT-IRR", "C", 0.55),
]

# compound_id, target_id, interaction, evidence_grade, confidence
COMPOUND_TARGET = [
    ("CMP-001", "TGT-JAK1", "抑制", "A", 0.96),
    ("CMP-001", "TGT-CYP3A4", "代谢底物", "B", 0.83),
    ("CMP-002", "TGT-JAK1", "抑制", "A", 0.92),
    ("CMP-003", "TGT-IL6R", "拮抗", "A", 0.95),
    ("CMP-004", "TGT-HER2", "结合", "A", 0.97),
    ("CMP-004", "TGT-HERG", "脱靶抑制", "C", 0.52),
    ("CMP-005", "TGT-BTK", "共价抑制", "A", 0.94),
    ("CMP-005", "TGT-HERG", "脱靶抑制", "B", 0.69),
]


def gen_knowledge() -> None:
    w("knowledge", "compounds",
      ["compound_id", "compound_code", "compound_name_zh", "modality", "primary_target_id", "dev_phase"],
      [list(c) for c in COMPOUNDS])

    w("knowledge", "targets",
      ["target_id", "gene_symbol", "target_name_zh"],
      [list(t) for t in TARGETS])

    w("knowledge", "pathways",
      ["pathway_id", "pathway_name_zh"],
      [list(p) for p in PATHWAYS])

    w("knowledge", "biomarkers",
      ["biomarker_id", "analyte_code", "biomarker_name_zh", "unit", "upper_normal_limit"],
      [list(b) for b in BIOMARKERS])

    w("knowledge", "ae_terms",
      ["pt_code", "pt_name_zh", "soc_name_zh"],
      [list(a) for a in AE_TERMS])

    w("knowledge", "compound_target",
      ["compound_id", "target_id", "interaction_type", "evidence_grade", "confidence"],
      [list(x) for x in COMPOUND_TARGET])

    w("knowledge", "target_pathway",
      ["target_id", "pathway_id", "evidence_grade", "confidence"],
      [list(x) for x in TARGET_PATHWAY])

    w("knowledge", "pathway_biomarker",
      ["pathway_id", "biomarker_id", "direction", "evidence_grade", "confidence"],
      [list(x) for x in PATHWAY_BIOMARKER])

    w("knowledge", "biomarker_ae",
      ["biomarker_id", "pt_code", "evidence_grade", "confidence"],
      [list(x) for x in BIOMARKER_AE])


# --------------------------------------------------------------------- ctms

STUDIES = [
    ("STU-001", "SYN101-RA-201", "CMP-001", "II期", "类风湿关节炎", "进行中"),
    ("STU-002", "SYN301-BC-101", "CMP-004", "I期", "HER2阳性实体瘤", "进行中"),
    ("STU-003", "SYN401-LY-202", "CMP-005", "II期", "B细胞淋巴瘤", "进行中"),
]

SITE_DEFS = [
    ("SITE-001", "STU-001", "北京协研医院", "中国", "北京"),
    ("SITE-002", "STU-001", "上海临研中心", "中国", "上海"),
    ("SITE-003", "STU-001", "广州华南研究院", "中国", "广州"),
    ("SITE-004", "STU-001", "东京中央医院", "日本", "东京"),
    ("SITE-005", "STU-002", "成都西部医学中心", "中国", "成都"),
    ("SITE-006", "STU-002", "南京东方医院", "中国", "南京"),
    ("SITE-007", "STU-002", "法兰克福大学医院", "德国", "法兰克福"),
    ("SITE-008", "STU-002", "波士顿临床研究所", "美国", "波士顿"),
    ("SITE-009", "STU-003", "武汉江城医院", "中国", "武汉"),
    ("SITE-010", "STU-003", "西安长安医院", "中国", "西安"),
    ("SITE-011", "STU-003", "大阪临床中心", "日本", "大阪"),
    ("SITE-012", "STU-003", "芝加哥医学中心", "美国", "芝加哥"),
]

INVESTIGATOR_NAMES = [
    "陈明远", "李思齐", "王慧敏", "佐藤健一", "刘振国", "赵雅琴",
    "M. Weber", "J. Carter", "周文博", "孙立诚", "田中优子", "R. Patel",
]


def gen_ctms(ctx: Ctx) -> None:
    rng = ctx.rng

    w("ctms", "studies",
      ["study_id", "protocol_no", "compound_id", "phase", "indication_zh", "study_status"],
      [list(s) for s in STUDIES])

    investigators = []
    for i, name in enumerate(INVESTIGATOR_NAMES, start=1):
        inv_id = f"INV-{i:03d}"
        investigators.append([inv_id, name, rng.choice(["风湿免疫科", "肿瘤内科", "血液科"])])
    w("ctms", "investigators", ["investigator_id", "investigator_name", "specialty_zh"], investigators)

    sites = []
    for idx, (site_id, study_id, name, country, city) in enumerate(SITE_DEFS):
        activation = STUDY_START + timedelta(days=rng.randint(0, 40))
        sites.append([site_id, study_id, name, country, city,
                      f"INV-{idx + 1:03d}", activation.isoformat(), "激活"])
    w("ctms", "sites",
      ["site_id", "study_id", "site_name_zh", "country", "city",
       "investigator_id", "activation_date", "site_status"],
      sites)

    subjects = []
    arms = {"STU-001": ["SYN-101 低剂量", "SYN-101 高剂量", "安慰剂"],
            "STU-002": ["SYN-301 剂量递增", "SYN-301 扩展队列"],
            "STU-003": ["SYN-401 单药", "SYN-401 联合"]}
    seq = 0
    for study_id, *_ in STUDIES:
        study_sites = [s[0] for s in SITE_DEFS if s[1] == study_id]
        for _ in range(40):
            seq += 1
            subject_id = f"SUBJ-{seq:04d}"
            site_id = rng.choice(study_sites)
            enroll = STUDY_START + timedelta(days=rng.randint(30, 150))
            rec = {
                "subject_id": subject_id,
                "study_id": study_id,
                "site_id": site_id,
                "enroll_date": enroll,
                "arm": rng.choice(arms[study_id]),
                "age_group": rng.choice(["18-39", "40-59", "60-74", ">=75"]),
                "sex": rng.choice(["男", "女"]),
                "status": rng.choices(["在研", "已完成", "提前终止"], weights=[70, 22, 8])[0],
            }
            ctx.subjects.append(rec)
            subjects.append([rec["subject_id"], rec["study_id"], rec["site_id"],
                             rec["enroll_date"].isoformat(), rec["arm"],
                             rec["age_group"], rec["sex"], rec["status"]])
    w("ctms", "subjects",
      ["subject_id", "study_id", "site_id", "enroll_date", "treatment_arm",
       "age_group", "sex", "subject_status"],
      subjects)

    deviations = []
    categories = ["知情同意流程偏离", "访视窗超窗", "给药剂量偏离",
                  "样本采集偏离", "温度链记录缺失"]
    for i in range(46):
        subj = rng.choice(ctx.subjects)
        dev_date = subj["enroll_date"] + timedelta(days=rng.randint(5, 120))
        deviations.append([f"DEV-{i + 1:04d}", subj["study_id"], subj["site_id"],
                           subj["subject_id"], rng.choice(categories),
                           rng.choices(["重要", "一般"], weights=[35, 65])[0],
                           dev_date.isoformat()])
    w("ctms", "protocol_deviations",
      ["deviation_id", "study_id", "site_id", "subject_id",
       "deviation_category_zh", "deviation_severity", "deviation_date"],
      deviations)


# ---------------------------------------------------------------------- edc

VISIT_NAMES = ["筛选期", "基线", "第2周", "第4周", "第8周", "第12周", "第24周"]


def gen_edc(ctx: Ctx, batch_index: dict[str, list[str]]) -> None:
    rng = ctx.rng
    visits, dosing = [], []
    vseq = dseq = 0

    for subj in ctx.subjects:
        n = rng.randint(4, 7)
        for k in range(n):
            vseq += 1
            visit_id = f"VIS-{vseq:05d}"
            vdate = subj["enroll_date"] + timedelta(days=[0, 7, 21, 35, 63, 91, 175][k])
            rec = {
                "visit_id": visit_id,
                "subject_id": subj["subject_id"],
                "study_id": subj["study_id"],
                "site_id": subj["site_id"],
                "visit_name": VISIT_NAMES[k],
                "visit_date": vdate,
                "visit_seq": k + 1,
            }
            ctx.visits.append(rec)
            visits.append([visit_id, subj["subject_id"], subj["study_id"],
                           VISIT_NAMES[k], k + 1, vdate.isoformat(), "已完成"])

            if k >= 1 and "安慰剂" not in subj["arm"]:
                dseq += 1
                compound_id = next(s[2] for s in STUDIES if s[0] == subj["study_id"])
                batch_id = rng.choice(batch_index[compound_id])
                dosing.append([f"DOS-{dseq:05d}", subj["subject_id"], visit_id,
                               compound_id, batch_id,
                               rng.choice([50, 100, 150, 200]),
                               vdate.isoformat()])

    w("edc", "visits",
      ["visit_id", "subject_id", "study_id", "visit_name_zh",
       "visit_seq", "visit_date", "visit_status"],
      visits)
    w("edc", "dosing_records",
      ["dosing_id", "subject_id", "visit_id", "compound_id",
       "batch_id", "dose_mg", "dosing_date"],
      dosing)


# --------------------------------------------------------------------- lims

ANALYTE_BY_STUDY = {
    "STU-001": ["BM-ALT", "BM-AST", "BM-CRP", "BM-ANC"],
    "STU-002": ["BM-ALT", "BM-QTCF", "BM-PLT", "BM-TBIL"],
    "STU-003": ["BM-ANC", "BM-PLT", "BM-QTCF", "BM-ALT"],
}
ULN = {b[0]: b[4] for b in BIOMARKERS}
UNIT = {b[0]: b[3] for b in BIOMARKERS}
LOW_IS_ABNORMAL = {"BM-ANC", "BM-PLT"}


def gen_lims(ctx: Ctx, high_risk_subjects: set[str]) -> None:
    rng = ctx.rng
    labs = []
    lseq = 0
    for visit in ctx.visits:
        for analyte in ANALYTE_BY_STUDY[visit["study_id"]]:
            lseq += 1
            lab_id = f"LAB-{lseq:06d}"
            uln = ULN[analyte]
            risky = visit["subject_id"] in high_risk_subjects and visit["visit_seq"] >= 3

            if analyte in LOW_IS_ABNORMAL:
                base = uln * rng.uniform(1.05, 2.2)
                value = uln * rng.uniform(0.35, 0.85) if risky and rng.random() < 0.7 else base
                abnormal = value < uln
            else:
                base = uln * rng.uniform(0.35, 0.92)
                value = uln * rng.uniform(1.6, 5.4) if risky and rng.random() < 0.7 else base
                abnormal = value > uln

            rec = {
                "lab_id": lab_id,
                "subject_id": visit["subject_id"],
                "visit_id": visit["visit_id"],
                "biomarker_id": analyte,
                "abnormal": abnormal,
                "collected_date": visit["visit_date"],
            }
            ctx.labs.append(rec)
            labs.append([lab_id, visit["subject_id"], visit["visit_id"], analyte,
                         round(value, 2), UNIT[analyte], uln,
                         "异常" if abnormal else "正常",
                         visit["visit_date"].isoformat()])
    w("lims", "lab_results",
      ["lab_id", "subject_id", "visit_id", "biomarker_id", "result_value",
       "unit", "upper_normal_limit", "abnormal_flag", "collected_date"],
      labs)


# ------------------------------------------------------------------- safety

SIGNALS = [
    ("SIG-001", "CMP-001", "PT-DILI", "评估中", "B", "2026-05-18"),
    ("SIG-002", "CMP-005", "PT-QTP", "已确认", "A", "2026-06-02"),
    ("SIG-003", "CMP-004", "PT-THROM", "评估中", "C", "2026-06-21"),
]

STUDY_PT = {
    "STU-001": ["PT-DILI", "PT-RASH", "PT-NEUT"],
    "STU-002": ["PT-THROM", "PT-IRR", "PT-QTP", "PT-ILD"],
    "STU-003": ["PT-QTP", "PT-NEUT", "PT-RASH"],
}
STUDY_SIGNAL = {"STU-001": "SIG-001", "STU-003": "SIG-002", "STU-002": "SIG-003"}
SIGNAL_PT = {s[0]: s[2] for s in SIGNALS}


def gen_safety(ctx: Ctx, high_risk_subjects: set[str]) -> list[list]:
    rng = ctx.rng
    aes, links = [], []
    aseq = 0

    for subj in ctx.subjects:
        risky = subj["subject_id"] in high_risk_subjects
        n = rng.choices([0, 1, 2], weights=[45, 40, 15])[0]
        if risky:
            n = max(n, 1)
        for _ in range(n):
            aseq += 1
            ae_id = f"AE-{aseq:05d}"
            signal_pt = SIGNAL_PT[STUDY_SIGNAL[subj["study_id"]]]
            pt = signal_pt if risky else rng.choice(STUDY_PT[subj["study_id"]])
            onset = subj["enroll_date"] + timedelta(days=rng.randint(20, 150))
            serious = "是" if (risky and rng.random() < 0.55) or rng.random() < 0.12 else "否"
            grade = rng.choices([1, 2, 3, 4], weights=[35, 35, 22, 8])[0]
            if serious == "是":
                grade = max(grade, 3)
            causality = rng.choices(["肯定有关", "很可能有关", "可能有关", "可能无关"],
                                    weights=[10, 30, 40, 20])[0]
            rec = {"ae_id": ae_id, "subject_id": subj["subject_id"],
                   "study_id": subj["study_id"], "pt_code": pt, "serious": serious}
            ctx.aes.append(rec)
            aes.append([ae_id, subj["subject_id"], subj["study_id"], pt,
                        onset.isoformat(), serious, grade, causality,
                        rng.choice(["恢复", "恢复中", "未恢复"])])

            if pt == signal_pt:
                links.append([ae_id, STUDY_SIGNAL[subj["study_id"]],
                              "高" if serious == "是" else "中"])

    w("safety", "adverse_events",
      ["ae_id", "subject_id", "study_id", "pt_code", "onset_date",
       "serious_flag", "ctcae_grade", "causality_zh", "outcome_zh"],
      aes)
    w("safety", "safety_signals",
      ["signal_id", "compound_id", "pt_code", "signal_status_zh",
       "evidence_grade", "detected_date"],
      [list(s) for s in SIGNALS])
    w("safety", "ae_signal_links",
      ["ae_id", "signal_id", "contribution_level"], links)
    return links


# ------------------------------------------------------------------- supply

def gen_supply(ctx: Ctx) -> tuple[dict[str, list[str]], list[str]]:
    rng = ctx.rng
    batches, shipments = [], []
    batch_index: dict[str, list[str]] = {}
    bseq = 0

    # Only compounds that are actually dosed in a study get clinical supply, so
    # batch numbering stays meaningful for the traceability question.
    dosed_compounds = [s[2] for s in STUDIES]
    for compound_id in dosed_compounds:
        for _ in range(3):
            bseq += 1
            batch_id = f"BATCH-{bseq:03d}"
            batch_index.setdefault(compound_id, []).append(batch_id)
            mfg = STUDY_START - timedelta(days=rng.randint(20, 90))
            batches.append([batch_id, compound_id, mfg.isoformat(),
                            (mfg + timedelta(days=730)).isoformat(), "放行"])

    # BATCH-007 is the planted quality event used by the traceability question.
    excursion_batches = {"BATCH-007"}
    impacted_sites: list[str] = []
    sseq = 0
    for batch_id, compound_id, *_ in batches:
        study_ids = [s[0] for s in STUDIES if s[2] == compound_id]
        target_sites = [s[0] for s in SITE_DEFS if s[1] in study_ids]
        for site_id in rng.sample(target_sites, k=min(3, len(target_sites))):
            sseq += 1
            ship = STUDY_START + timedelta(days=rng.randint(10, 120))
            excursion = "是" if batch_id in excursion_batches else \
                ("是" if rng.random() < 0.04 else "否")
            if excursion == "是":
                impacted_sites.append(site_id)
            shipments.append([f"SHIP-{sseq:04d}", batch_id, site_id,
                              ship.isoformat(), (ship + timedelta(days=3)).isoformat(),
                              excursion])

    w("supply", "batches",
      ["batch_id", "compound_id", "manufacture_date", "expiry_date", "qc_status_zh"],
      batches)
    w("supply", "shipments",
      ["shipment_id", "batch_id", "site_id", "ship_date",
       "receive_date", "temperature_excursion_flag"],
      shipments)
    return batch_index, impacted_sites


# --------------------------------------------------------------------- main

def main() -> None:
    rng = random.Random(SEED)
    ctx = Ctx(rng=rng)

    gen_knowledge()
    gen_ctms(ctx)
    batch_index, _ = gen_supply(ctx)
    gen_edc(ctx, batch_index)

    # Subjects dosed from the excursion batch are made higher risk so the
    # supply-to-safety traceability question returns a non-empty answer.
    dosed_from_excursion = {
        row[1] for row in csv.reader(
            (ROOT / "edc" / "dosing_records.csv").open(encoding="utf-8"))
        if row and row[4] == "BATCH-007"
    }
    extra = {s["subject_id"] for s in rng.sample(ctx.subjects, k=28)}
    high_risk = dosed_from_excursion | extra

    gen_lims(ctx, high_risk)
    gen_safety(ctx, high_risk)

    print(f"\nsubjects={len(ctx.subjects)} visits={len(ctx.visits)} "
          f"labs={len(ctx.labs)} aes={len(ctx.aes)} "
          f"high_risk={len(high_risk)} excursion_dosed={len(dosed_from_excursion)}")


if __name__ == "__main__":
    main()
