"""Generate a synthetic CRF-to-SDTM mapping specification for the lineage demo.

All content is invented for demonstration. Form names, field identifiers and
mapping rules do not come from any real sponsor library. SDTM domain and
variable names follow the public CDISC naming convention so that the demo is
recognisable to clinical data professionals.

Two library versions are produced so the demo can answer version-comparison
questions. Key scenarios are planted deliberately rather than left to chance:

    multi-source   DM.ARMCD reachable by a direct copy and by a lookup
    multi-hop      CRF date -> --DTC -> --DY study-day derivation
    wide impact    EX start date feeds DM.RFSTDTC which feeds every study day
    version drift  an algorithm simplified and a SUPP variable promoted in V2
    coverage gap   required variables with no mapping source
"""

from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "data" / "spec"
LIBRARY = "SSL"  # Synthetic Standard Library
VERSIONS = ["V1", "V2"]


def write(name: str, header: list[str], rows: list[list]) -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    with (ROOT / f"{name}.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)
    print(f"{name}.csv  rows={len(rows)}")


# ------------------------------------------------------------------ CRF 库

# form_oid, form_name_en, form_name_zh, page
FORMS = [
    ("IC", "Informed Consent", "知情同意", 1),
    ("DM", "Demographics", "人口学", 3),
    ("EN", "Enrollment", "入组", 5),
    ("SV", "Subject Visit", "受试者访视", 7),
    ("MH", "Medical History", "既往病史", 9),
    ("AE", "Adverse Events", "不良事件", 11),
    ("CM", "Concomitant Medications", "合并用药", 14),
    ("EX", "Study Drug Administration", "研究药物给药", 16),
    ("LB", "Laboratory Results", "实验室检查", 18),
    ("VS", "Vital Signs", "生命体征", 21),
    ("EG", "Electrocardiogram", "心电图", 23),
    ("DS", "Disposition", "研究处置", 25),
]

# form_oid, field_oid, label_en, label_zh, field_type, codelist
FIELDS = [
    ("IC", "ICYN", "Was informed consent obtained?", "是否已获得知情同意", "RadioButton", "NY"),
    ("IC", "ICDAT", "Date informed consent signed", "知情同意签署日期", "DateTime", ""),
    ("IC", "ICPVER", "Protocol version consented", "知情的方案版本", "DropDownList", "PROTVER"),

    ("DM", "BRTHDAT", "Date of birth", "出生日期", "DateTime", ""),
    ("DM", "SEXCD", "Sex", "性别", "RadioButton", "SEX"),
    ("DM", "RACECD", "Race", "种族", "Checkbox", "RACE"),
    ("DM", "ETHNICCD", "Ethnicity", "民族", "RadioButton", "ETHNIC"),
    ("DM", "CNTRYCD", "Country", "国家", "DropDownList", "COUNTRY"),

    ("EN", "ENRLYN", "Was subject enrolled?", "受试者是否入组", "RadioButton", "NY"),
    ("EN", "ENRLDAT", "Date of enrollment", "入组日期", "DateTime", ""),
    ("EN", "RANDDAT", "Date of randomization", "随机日期", "DateTime", ""),
    ("EN", "SFREAS", "Reason for screen failure", "筛选失败原因", "DropDownList", "SFREAS"),
    ("EN", "ARMASSN", "Assigned treatment arm", "分配的治疗组", "DropDownList", "ARM"),
    ("EN", "COHORTCD", "Cohort", "队列", "DropDownList", "COHORT"),

    ("SV", "VISOCC", "Did visit occur?", "访视是否发生", "RadioButton", "NY"),
    ("SV", "VISDAT", "Date of visit", "访视日期", "DateTime", ""),
    ("SV", "VISNDRS", "Reason visit not done", "访视未进行原因", "Text", ""),

    ("MH", "MHTERM", "Medical history term", "既往病史术语", "Text", ""),
    ("MH", "MHSTDAT", "Start date of condition", "疾病开始日期", "DateTime", ""),
    ("MH", "MHONGO", "Ongoing?", "是否持续", "RadioButton", "NY"),

    ("AE", "AETERM", "Adverse event term", "不良事件术语", "Text", ""),
    ("AE", "AESTDAT", "Start date of event", "事件开始日期", "DateTime", ""),
    ("AE", "AEENDAT", "End date of event", "事件结束日期", "DateTime", ""),
    ("AE", "AESERYN", "Serious?", "是否严重", "RadioButton", "NY"),
    ("AE", "AESEVCD", "Severity", "严重程度", "DropDownList", "AESEV"),
    ("AE", "AERELCD", "Relationship to study drug", "与研究药物关系", "DropDownList", "AEREL"),
    ("AE", "AEOUTCD", "Outcome", "转归", "DropDownList", "OUT"),
    ("AE", "AEACNCD", "Action taken with study drug", "对研究药物采取的措施", "DropDownList", "ACN"),

    ("CM", "CMTRT", "Medication name", "药物名称", "Text", ""),
    ("CM", "CMSTDAT", "Start date", "开始日期", "DateTime", ""),
    ("CM", "CMENDAT", "End date", "结束日期", "DateTime", ""),
    ("CM", "CMINDC", "Indication", "用药指征", "Text", ""),
    ("CM", "CMDOSE", "Dose", "剂量", "Number", ""),
    ("CM", "CMDOSU", "Dose unit", "剂量单位", "DropDownList", "UNIT"),

    ("EX", "EXTRTCD", "Study treatment", "研究治疗", "DropDownList", "TRT"),
    ("EX", "EXDOSE", "Dose administered", "给药剂量", "Number", ""),
    ("EX", "EXDOSU", "Dose unit", "剂量单位", "DropDownList", "UNIT"),
    ("EX", "EXSTDAT", "Start date of administration", "给药开始日期", "DateTime", ""),
    ("EX", "EXENDAT", "End date of administration", "给药结束日期", "DateTime", ""),

    ("LB", "LBTESTCD", "Laboratory test", "检验项目", "DropDownList", "LBTEST"),
    ("LB", "LBORRES", "Result", "检验结果", "Text", ""),
    ("LB", "LBORRESU", "Result unit", "结果单位", "DropDownList", "UNIT"),
    ("LB", "LBDAT", "Collection date", "采样日期", "DateTime", ""),
    ("LB", "LBFASTYN", "Fasting?", "是否空腹", "RadioButton", "NY"),

    ("VS", "VSDAT", "Measurement date", "测量日期", "DateTime", ""),
    ("VS", "SYSBP", "Systolic blood pressure", "收缩压", "Number", ""),
    ("VS", "DIABP", "Diastolic blood pressure", "舒张压", "Number", ""),
    ("VS", "PULSE", "Pulse rate", "脉率", "Number", ""),
    ("VS", "TEMPC", "Temperature", "体温", "Number", ""),
    ("VS", "WEIGHTKG", "Weight", "体重", "Number", ""),

    ("EG", "EGDAT", "ECG date", "心电图日期", "DateTime", ""),
    ("EG", "EGQTCF", "QTcF interval", "QTcF 间期", "Number", ""),
    ("EG", "EGINTP", "Overall interpretation", "总体判读", "DropDownList", "EGINTP"),

    ("DS", "DSCOMPYN", "Did subject complete the study?", "受试者是否完成研究", "RadioButton", "NY"),
    ("DS", "DSDAT", "Date of disposition event", "处置事件日期", "DateTime", ""),
    ("DS", "DSREASCD", "Reason for discontinuation", "终止原因", "DropDownList", "DSREAS"),
    ("DS", "DSOTHSP", "Other reason, specify", "其他原因说明", "Text", ""),
]

# V2 新增字段：再次知情同意，用于版本对比
V2_ONLY_FIELDS = [
    ("IC", "RICFYN", "Was re-consent obtained?", "是否已获得再次知情同意", "RadioButton", "NY"),
    ("IC", "RICFDAT", "Date of re-consent", "再次知情同意日期", "DateTime", ""),
]

# V1 独有字段：V2 中被移除
V1_ONLY_FIELDS = [
    ("EN", "SCRNPREV", "Was subject screened previously?", "既往是否曾筛选", "RadioButton", "NY"),
]


# ---------------------------------------------------------------- SDTM 结构

# domain, label_zh, obs_class, is_supp, parent
DOMAINS = [
    ("DM", "人口学", "Special Purpose", "否", ""),
    ("SV", "受试者访视", "Special Purpose", "否", ""),
    ("MH", "既往病史", "Events", "否", ""),
    ("AE", "不良事件", "Events", "否", ""),
    ("DS", "研究处置", "Events", "否", ""),
    ("CM", "合并用药", "Interventions", "否", ""),
    ("EX", "暴露给药", "Interventions", "否", ""),
    ("LB", "实验室检查", "Findings", "否", ""),
    ("VS", "生命体征", "Findings", "否", ""),
    ("EG", "心电图", "Findings", "否", ""),
    ("SUPPDM", "人口学补充限定符", "Relationship", "是", "DM"),
    ("SUPPDS", "处置补充限定符", "Relationship", "是", "DS"),
    ("SUPPAE", "不良事件补充限定符", "Relationship", "是", "AE"),
]

# domain, var_name, label_zh, core, data_type, codelist
VARIABLES = [
    ("DM", "STUDYID", "研究标识符", "Req", "Char", ""),
    ("DM", "DOMAIN", "域缩写", "Req", "Char", ""),
    ("DM", "USUBJID", "唯一受试者标识符", "Req", "Char", ""),
    ("DM", "SUBJID", "研究内受试者标识符", "Req", "Char", ""),
    ("DM", "RFSTDTC", "研究参考开始日期", "Exp", "Char", ""),
    ("DM", "RFENDTC", "研究参考结束日期", "Exp", "Char", ""),
    ("DM", "BRTHDTC", "出生日期", "Perm", "Char", ""),
    ("DM", "AGE", "年龄", "Exp", "Num", ""),
    ("DM", "AGEU", "年龄单位", "Exp", "Char", "AGEU"),
    ("DM", "SEX", "性别", "Req", "Char", "SEX"),
    ("DM", "RACE", "种族", "Exp", "Char", "RACE"),
    ("DM", "ETHNIC", "民族", "Perm", "Char", "ETHNIC"),
    ("DM", "COUNTRY", "国家", "Req", "Char", "COUNTRY"),
    ("DM", "ARMCD", "计划治疗组代码", "Req", "Char", "ARM"),
    ("DM", "ARM", "计划治疗组描述", "Req", "Char", "ARM"),

    ("SV", "DOMAIN", "域缩写", "Req", "Char", ""),
    ("SV", "USUBJID", "唯一受试者标识符", "Req", "Char", ""),
    ("SV", "VISITNUM", "访视号", "Req", "Num", ""),
    ("SV", "SVSTDTC", "访视开始日期", "Exp", "Char", ""),
    ("SV", "SVPRESP", "是否预先指定", "Perm", "Char", "NY"),
    ("SV", "SVOCCUR", "是否发生", "Perm", "Char", "NY"),
    ("SV", "SVREASND", "未发生原因", "Perm", "Char", ""),

    ("AE", "DOMAIN", "域缩写", "Req", "Char", ""),
    ("AE", "USUBJID", "唯一受试者标识符", "Req", "Char", ""),
    ("AE", "AETERM", "报告的不良事件术语", "Req", "Char", ""),
    ("AE", "AEDECOD", "标准化不良事件术语", "Req", "Char", "MEDDRA"),
    ("AE", "AEBODSYS", "系统器官分类", "Exp", "Char", "MEDDRA"),
    ("AE", "AESTDTC", "事件开始日期", "Exp", "Char", ""),
    ("AE", "AEENDTC", "事件结束日期", "Perm", "Char", ""),
    ("AE", "AESTDY", "事件开始研究日", "Perm", "Num", ""),
    ("AE", "AESER", "是否严重", "Req", "Char", "NY"),
    ("AE", "AESEV", "严重程度", "Exp", "Char", "AESEV"),
    ("AE", "AEREL", "与研究药物关系", "Exp", "Char", "AEREL"),
    ("AE", "AEOUT", "转归", "Perm", "Char", "OUT"),
    ("AE", "AEACN", "对研究药物采取的措施", "Perm", "Char", "ACN"),
    # 下列变量在标准中定义，但本版 CRF 未采集，构成真实的覆盖缺口
    ("AE", "AETOXGR", "毒性分级", "Exp", "Char", "CTCAE"),
    ("AE", "AECONTRT", "是否采取其他治疗措施", "Perm", "Char", "NY"),
    ("AE", "EPOCH", "试验阶段", "Perm", "Char", "EPOCH"),

    ("DS", "DOMAIN", "域缩写", "Req", "Char", ""),
    ("DS", "USUBJID", "唯一受试者标识符", "Req", "Char", ""),
    ("DS", "DSTERM", "报告的处置术语", "Req", "Char", ""),
    ("DS", "DSDECOD", "标准化处置术语", "Req", "Char", "DSDECOD"),
    ("DS", "DSCAT", "处置事件类别", "Exp", "Char", "DSCAT"),
    ("DS", "DSSTDTC", "处置事件开始日期", "Exp", "Char", ""),
    ("DS", "DSSTDY", "处置事件开始研究日", "Perm", "Num", ""),
    ("DS", "EPOCH", "试验阶段", "Perm", "Char", "EPOCH"),

    ("MH", "DOMAIN", "域缩写", "Req", "Char", ""),
    ("MH", "USUBJID", "唯一受试者标识符", "Req", "Char", ""),
    ("MH", "MHTERM", "报告的既往病史术语", "Req", "Char", ""),
    ("MH", "MHDECOD", "标准化既往病史术语", "Perm", "Char", "MEDDRA"),
    ("MH", "MHSTDTC", "疾病开始日期", "Perm", "Char", ""),
    ("MH", "MHENRTPT", "相对参考时点", "Perm", "Char", "STENRF"),

    ("CM", "DOMAIN", "域缩写", "Req", "Char", ""),
    ("CM", "USUBJID", "唯一受试者标识符", "Req", "Char", ""),
    ("CM", "CMTRT", "报告的药物名称", "Req", "Char", ""),
    ("CM", "CMDECOD", "标准化药物名称", "Perm", "Char", "WHODRUG"),
    ("CM", "CMINDC", "用药指征", "Perm", "Char", ""),
    ("CM", "CMDOSE", "剂量", "Perm", "Num", ""),
    ("CM", "CMDOSU", "剂量单位", "Perm", "Char", "UNIT"),
    ("CM", "CMSTDTC", "开始日期", "Perm", "Char", ""),
    ("CM", "CMENDTC", "结束日期", "Perm", "Char", ""),
    ("CM", "CMDOSFRQ", "给药频次", "Perm", "Char", "FREQ"),

    ("EX", "DOMAIN", "域缩写", "Req", "Char", ""),
    ("EX", "USUBJID", "唯一受试者标识符", "Req", "Char", ""),
    ("EX", "EXTRT", "研究治疗名称", "Req", "Char", "TRT"),
    ("EX", "EXDOSE", "剂量", "Exp", "Num", ""),
    ("EX", "EXDOSU", "剂量单位", "Exp", "Char", "UNIT"),
    ("EX", "EXSTDTC", "给药开始日期", "Exp", "Char", ""),
    ("EX", "EXENDTC", "给药结束日期", "Perm", "Char", ""),

    ("LB", "DOMAIN", "域缩写", "Req", "Char", ""),
    ("LB", "USUBJID", "唯一受试者标识符", "Req", "Char", ""),
    ("LB", "LBTESTCD", "检验项目短名", "Req", "Char", "LBTEST"),
    ("LB", "LBTEST", "检验项目名称", "Req", "Char", "LBTEST"),
    ("LB", "LBORRES", "原始结果", "Exp", "Char", ""),
    ("LB", "LBORRESU", "原始结果单位", "Exp", "Char", "UNIT"),
    ("LB", "LBSTRESC", "标准化结果字符型", "Exp", "Char", ""),
    ("LB", "LBSTRESN", "标准化结果数值型", "Exp", "Num", ""),
    ("LB", "LBSTRESU", "标准化结果单位", "Exp", "Char", "UNIT"),
    ("LB", "LBNRIND", "参考范围指示", "Perm", "Char", "NRIND"),
    ("LB", "LBDTC", "采样日期", "Exp", "Char", ""),
    ("LB", "LBFAST", "是否空腹", "Perm", "Char", "NY"),
    ("LB", "LBBLFL", "基线标志", "Perm", "Char", "NY"),

    ("VS", "DOMAIN", "域缩写", "Req", "Char", ""),
    ("VS", "USUBJID", "唯一受试者标识符", "Req", "Char", ""),
    ("VS", "VSTESTCD", "检查项目短名", "Req", "Char", "VSTEST"),
    ("VS", "VSORRES", "原始结果", "Exp", "Char", ""),
    ("VS", "VSSTRESN", "标准化结果数值型", "Exp", "Num", ""),
    ("VS", "VSDTC", "测量日期", "Exp", "Char", ""),
    ("VS", "VSPOS", "测量体位", "Perm", "Char", "POSITION"),

    ("EG", "DOMAIN", "域缩写", "Req", "Char", ""),
    ("EG", "USUBJID", "唯一受试者标识符", "Req", "Char", ""),
    ("EG", "EGTESTCD", "检查项目短名", "Req", "Char", "EGTEST"),
    ("EG", "EGORRES", "原始结果", "Exp", "Char", ""),
    ("EG", "EGSTRESN", "标准化结果数值型", "Exp", "Num", ""),
    ("EG", "EGDTC", "检查日期", "Exp", "Char", ""),
    ("EG", "EGMETHOD", "检查方法", "Perm", "Char", "EGMETHOD"),

    ("SUPPDM", "QNAM", "限定符变量名", "Req", "Char", ""),
    ("SUPPDM", "QVAL", "限定符值", "Req", "Char", ""),
    ("SUPPDS", "QNAM", "限定符变量名", "Req", "Char", ""),
    ("SUPPDS", "QVAL", "限定符值", "Req", "Char", ""),
    ("SUPPAE", "QNAM", "限定符变量名", "Req", "Char", ""),
    ("SUPPAE", "QVAL", "限定符值", "Req", "Char", ""),
]


# ---------------------------------------------------------------- 映射规则

# 每条：form_oid, field_oid, domain, var_name, algorithm, condition, qnam
# algorithm 决定映射代价，见 lineage_logic.ALGORITHM_PENALTY
BASE_MAPPINGS = [
    ("IC", "ICDAT", "DS", "DSSTDTC", "DT2DTC", "DSDECOD = INFORMED CONSENT OBTAINED", ""),
    ("IC", "ICYN", "DS", "DSDECOD", "IfAssigned", "如果为 Yes 则赋值 INFORMED CONSENT OBTAINED", ""),
    ("IC", "ICYN", "DS", "DSTERM", "IfAssigned", "如果为 Yes 则赋值知情同意已获得", ""),
    ("IC", "ICYN", "DS", "DSCAT", "Assigned", "常量 PROTOCOL MILESTONE", ""),
    ("IC", "ICPVER", "SUPPDS", "QVAL", "CopyUpcase", "", "DSPROTVS"),

    ("DM", "BRTHDAT", "DM", "BRTHDTC", "DT2DTC", "", ""),
    ("DM", "SEXCD", "DM", "SEX", "CopyUpcase", "", ""),
    ("DM", "RACECD", "DM", "RACE", "CopyUpcase", "", ""),
    ("DM", "ETHNICCD", "DM", "ETHNIC", "CopyUpcase", "", ""),
    ("DM", "CNTRYCD", "DM", "COUNTRY", "Copy", "", ""),

    ("EN", "ENRLDAT", "DS", "DSSTDTC", "DT2DTC", "DSDECOD = ENTERED INTO TRIAL", ""),
    ("EN", "ENRLYN", "DS", "DSDECOD", "IfAssigned", "如果为 Yes 则赋值 ENTERED INTO TRIAL", ""),
    ("EN", "RANDDAT", "DS", "DSSTDTC", "DT2DTC", "DSDECOD = RANDOMIZED", ""),
    ("EN", "SFREAS", "DS", "DSDECOD", "Lookup", "筛选失败原因映射到标准处置术语", ""),
    ("EN", "ARMASSN", "DM", "ARMCD", "Copy", "", ""),
    ("EN", "ARMASSN", "DM", "ARM", "Lookup", "由治疗组代码查表得到描述", ""),
    # 同一个 ARMCD 的第二条来源，用于最优路径对比
    ("EN", "COHORTCD", "DM", "ARMCD", "Lookup", "由队列反查治疗组，仅在未随机化研究使用", ""),
    ("EN", "COHORTCD", "SUPPDM", "QVAL", "CopyUpcase", "", "COHORT"),

    ("SV", "VISOCC", "SV", "SVPRESP", "Assigned", "常量 Y", ""),
    ("SV", "VISOCC", "SV", "SVOCCUR", "CopyUpcase", "", ""),
    ("SV", "VISDAT", "SV", "SVSTDTC", "DT2DTC", "", ""),
    ("SV", "VISNDRS", "SV", "SVREASND", "Copy", "", ""),

    ("MH", "MHTERM", "MH", "MHTERM", "Copy", "", ""),
    ("MH", "MHSTDAT", "MH", "MHSTDTC", "DT2DTC", "", ""),
    ("MH", "MHONGO", "MH", "MHENRTPT", "IfAssigned",
     "是则赋 ONGOING，否则赋 BEFORE", ""),

    ("AE", "AETERM", "AE", "AETERM", "Copy", "", ""),
    ("AE", "AESTDAT", "AE", "AESTDTC", "DT2DTC", "", ""),
    ("AE", "AEENDAT", "AE", "AEENDTC", "DT2DTC", "", ""),
    ("AE", "AESERYN", "AE", "AESER", "CopyUpcase", "", ""),
    ("AE", "AESEVCD", "AE", "AESEV", "CopyUpcase", "", ""),
    ("AE", "AERELCD", "AE", "AEREL", "CopyUpcase", "", ""),
    ("AE", "AEOUTCD", "AE", "AEOUT", "CopyUpcase", "", ""),
    ("AE", "AEACNCD", "AE", "AEACN", "CopyUpcase", "", ""),

    ("CM", "CMTRT", "CM", "CMTRT", "Copy", "", ""),
    ("CM", "CMSTDAT", "CM", "CMSTDTC", "DT2DTC", "", ""),
    ("CM", "CMENDAT", "CM", "CMENDTC", "DT2DTC", "", ""),
    ("CM", "CMINDC", "CM", "CMINDC", "Copy", "", ""),
    ("CM", "CMDOSE", "CM", "CMDOSE", "Copy", "", ""),
    ("CM", "CMDOSU", "CM", "CMDOSU", "CopyUpcase", "", ""),

    ("EX", "EXTRTCD", "EX", "EXTRT", "Lookup", "由治疗代码查表得到名称", ""),
    ("EX", "EXDOSE", "EX", "EXDOSE", "Copy", "", ""),
    ("EX", "EXDOSU", "EX", "EXDOSU", "CopyUpcase", "", ""),
    ("EX", "EXSTDAT", "EX", "EXSTDTC", "DT2DTC", "", ""),
    ("EX", "EXENDAT", "EX", "EXENDTC", "DT2DTC", "", ""),

    ("LB", "LBTESTCD", "LB", "LBTESTCD", "Copy", "", ""),
    ("LB", "LBTESTCD", "LB", "LBTEST", "Lookup", "由项目代码查表得到名称", ""),
    ("LB", "LBORRES", "LB", "LBORRES", "Copy", "", ""),
    ("LB", "LBORRESU", "LB", "LBORRESU", "CopyUpcase", "", ""),
    ("LB", "LBDAT", "LB", "LBDTC", "DT2DTC", "", ""),
    ("LB", "LBFASTYN", "LB", "LBFAST", "CopyUpcase", "", ""),

    ("VS", "VSDAT", "VS", "VSDTC", "DT2DTC", "", ""),
    ("VS", "SYSBP", "VS", "VSORRES", "Copy", "VSTESTCD = SYSBP", ""),
    ("VS", "DIABP", "VS", "VSORRES", "Copy", "VSTESTCD = DIABP", ""),
    ("VS", "PULSE", "VS", "VSORRES", "Copy", "VSTESTCD = PULSE", ""),
    ("VS", "TEMPC", "VS", "VSORRES", "Copy", "VSTESTCD = TEMP", ""),
    ("VS", "WEIGHTKG", "VS", "VSORRES", "Copy", "VSTESTCD = WEIGHT", ""),

    ("EG", "EGDAT", "EG", "EGDTC", "DT2DTC", "", ""),
    ("EG", "EGQTCF", "EG", "EGORRES", "Copy", "EGTESTCD = QTCF", ""),

    ("DS", "DSDAT", "DS", "DSSTDTC", "DT2DTC", "DSDECOD 来自终止原因", ""),
    ("DS", "DSCOMPYN", "DS", "DSDECOD", "IfAssigned", "如果为 Yes 则赋值 COMPLETED", ""),
    ("DS", "DSREASCD", "DS", "DSDECOD", "Lookup", "终止原因映射到标准处置术语", ""),
    ("DS", "DSREASCD", "DS", "DSTERM", "Copy", "", ""),
    ("DS", "DSOTHSP", "DS", "DSTERM", "IfAssigned", "当终止原因为其他时使用", ""),
]

# V1 独有映射
V1_ONLY_MAPPINGS = [
    ("EN", "SCRNPREV", "SUPPDS", "QVAL", "CopyUpcase", "", "DSPRESCN"),
]

# V2 独有映射：新增再次知情同意，且队列由 SUPPDM 上提到标准域
V2_ONLY_MAPPINGS = [
    ("IC", "RICFYN", "DS", "DSDECOD", "IfAssigned", "如果为 Yes 则赋值 RE-CONSENT OBTAINED", ""),
    ("IC", "RICFDAT", "DS", "DSSTDTC", "DT2DTC", "DSDECOD = RE-CONSENT OBTAINED", ""),
]

# V2 中算法被简化的规则：field_oid -> (domain, var, 新算法)
V2_ALGORITHM_CHANGES = {
    ("EN", "SFREAS", "DS", "DSDECOD"): "Assigned",
}


# --------------------------------------------------------- 变量间派生关系

# source_domain, source_var, target_domain, target_var, algorithm, note
DERIVATIONS = [
    ("EX", "EXSTDTC", "DM", "RFSTDTC", "Derived", "取首次给药日期作为研究参考开始日期"),
    ("EX", "EXENDTC", "DM", "RFENDTC", "Derived", "取末次给药日期作为研究参考结束日期"),
    ("DM", "BRTHDTC", "DM", "AGE", "Derived", "由出生日期与参考开始日期计算年龄"),
    ("DM", "RFSTDTC", "DM", "AGE", "Derived", "年龄计算的参考基准"),
    ("DM", "RFSTDTC", "AE", "AESTDY", "Derived", "研究日计算基准"),
    ("AE", "AESTDTC", "AE", "AESTDY", "Derived", "由事件开始日期与参考开始日期计算研究日"),
    ("DM", "RFSTDTC", "DS", "DSSTDY", "Derived", "研究日计算基准"),
    ("DS", "DSSTDTC", "DS", "DSSTDY", "Derived", "由处置日期与参考开始日期计算研究日"),
    ("AE", "AETERM", "AE", "AEDECOD", "Coding", "经 MedDRA 编码得到标准术语"),
    ("MH", "MHTERM", "MH", "MHDECOD", "Coding", "经 MedDRA 编码得到标准术语"),
    ("AE", "AEDECOD", "AE", "AEBODSYS", "Coding", "由标准术语得到系统器官分类"),
    ("CM", "CMTRT", "CM", "CMDECOD", "Coding", "经 WHO Drug 编码得到标准名称"),
    ("LB", "LBORRES", "LB", "LBSTRESC", "Derived", "原始结果标准化为字符型"),
    ("LB", "LBSTRESC", "LB", "LBSTRESN", "Derived", "字符型标准结果转数值型"),
    ("LB", "LBORRESU", "LB", "LBSTRESU", "Lookup", "单位换算到标准单位"),
    ("LB", "LBSTRESN", "LB", "LBNRIND", "Derived", "与参考范围比较得到高低指示"),
    ("LB", "LBDTC", "LB", "LBBLFL", "Derived", "与首次给药日期比较确定基线标志"),
    ("DM", "RFSTDTC", "LB", "LBBLFL", "Derived", "基线判定基准"),
    ("VS", "VSORRES", "VS", "VSSTRESN", "Derived", "原始结果转标准数值"),
    ("EG", "EGORRES", "EG", "EGSTRESN", "Derived", "原始结果转标准数值"),
    ("DS", "DSSTDTC", "DS", "EPOCH", "Derived", "由处置日期落入的试验阶段推导"),
    ("AE", "AESTDTC", "AE", "EPOCH", "Derived", "由事件日期落入的试验阶段推导"),
]


# ------------------------------------------------------------------ 受控术语

CONTROLLED_TERMS = [
    ("NY", "Y", "是"), ("NY", "N", "否"),
    ("SEX", "M", "男"), ("SEX", "F", "女"),
    ("ARM", "A", "试验组"), ("ARM", "B", "对照组"),
    ("DSDECOD", "COMPLETED", "完成"),
    ("DSDECOD", "INFORMED CONSENT OBTAINED", "已获得知情同意"),
    ("DSDECOD", "ENTERED INTO TRIAL", "进入试验"),
    ("DSDECOD", "RANDOMIZED", "已随机"),
    ("DSDECOD", "SCREEN FAILURE", "筛选失败"),
    ("DSDECOD", "ADVERSE EVENT", "不良事件"),
    ("DSDECOD", "WITHDRAWAL BY SUBJECT", "受试者撤回"),
    ("DSDECOD", "RE-CONSENT OBTAINED", "已获得再次知情同意"),
    ("DSCAT", "PROTOCOL MILESTONE", "方案里程碑"),
    ("DSCAT", "DISPOSITION EVENT", "处置事件"),
    ("AESEV", "MILD", "轻度"), ("AESEV", "MODERATE", "中度"), ("AESEV", "SEVERE", "重度"),
    ("AEREL", "RELATED", "有关"), ("AEREL", "NOT RELATED", "无关"),
    ("EPOCH", "SCREENING", "筛选期"), ("EPOCH", "TREATMENT", "治疗期"),
    ("EPOCH", "FOLLOW-UP", "随访期"),
    ("NRIND", "NORMAL", "正常"), ("NRIND", "HIGH", "偏高"), ("NRIND", "LOW", "偏低"),
]


# 不由 CRF 采集、由系统或建库程序直接赋值的变量，不应计入映射覆盖缺口
SYSTEM_ASSIGNED = {"STUDYID", "DOMAIN", "USUBJID", "SUBJID", "VISITNUM",
                   "QNAM", "AGEU", "LBTEST", "VSTESTCD", "EGTESTCD"}


def variable_origin(domain: str, var_name: str) -> str:
    if var_name in SYSTEM_ASSIGNED:
        return "系统赋值"
    if any(d[2] == domain and d[3] == var_name for d in DERIVATIONS):
        return "派生计算"
    return "CRF 采集"


# ---------------------------------------------------------------------- main

def fields_for(version: str) -> list[tuple]:
    out = list(FIELDS)
    if version == "V2":
        out += V2_ONLY_FIELDS
    else:
        out += V1_ONLY_FIELDS
    return out


def mappings_for(version: str) -> list[tuple]:
    out = []
    for m in BASE_MAPPINGS:
        key = (m[0], m[1], m[2], m[3])
        if version == "V2" and key in V2_ALGORITHM_CHANGES:
            m = (*m[:4], V2_ALGORITHM_CHANGES[key], m[5], m[6])
        out.append(m)
    out += V2_ONLY_MAPPINGS if version == "V2" else V1_ONLY_MAPPINGS
    return out


def main() -> None:
    form_page = {f[0]: f[3] for f in FORMS}

    write("crf_forms", ["library", "version", "form_oid", "form_name_en", "form_name_zh", "page"],
          [[LIBRARY, v, *f] for v in VERSIONS for f in FORMS])

    field_rows = []
    for v in VERSIONS:
        for order, (form, oid, en, zh, ftype, cl) in enumerate(fields_for(v), start=1):
            field_rows.append([LIBRARY, v, form, oid, en, zh, ftype, cl,
                               form_page[form], order])
    write("crf_fields",
          ["library", "version", "form_oid", "field_oid", "field_label_en",
           "field_label_zh", "field_type", "codelist", "acrf_page", "field_order"],
          field_rows)

    write("sdtm_domains", ["domain", "domain_label_zh", "observation_class",
                           "is_supplemental", "parent_domain"],
          [list(d) for d in DOMAINS])

    write("sdtm_variables", ["domain", "variable_name", "variable_label_zh",
                             "core", "data_type", "codelist", "expected_origin"],
          [[*x, variable_origin(x[0], x[1])] for x in VARIABLES])

    mapping_rows = []
    for v in VERSIONS:
        for i, (form, field, dom, var, algo, cond, qnam) in enumerate(mappings_for(v), start=1):
            annotation = f"{dom}.{var}" if not qnam else f"{dom}.QVAL where QNAM = {qnam}"
            if cond:
                annotation += f"（{cond}）"
            mapping_rows.append([LIBRARY, v, f"MR-{v}-{i:04d}", form, field, dom,
                                 var, qnam, algo, cond, annotation])
    write("mapping_rules",
          ["library", "version", "rule_id", "form_oid", "field_oid", "target_domain",
           "target_variable", "qnam", "algorithm", "condition_zh", "annotation_text"],
          mapping_rows)

    write("variable_derivations",
          ["source_domain", "source_variable", "target_domain", "target_variable",
           "algorithm", "note_zh"],
          [list(d) for d in DERIVATIONS])

    write("controlled_terms", ["codelist", "submission_value", "decode_zh"],
          [list(c) for c in CONTROLLED_TERMS])

    v1 = {(m[0], m[1], m[2], m[3]) for m in mappings_for("V1")}
    v2 = {(m[0], m[1], m[2], m[3]) for m in mappings_for("V2")}
    print(f"\n表单 {len(FORMS)}  字段 V1={len(fields_for('V1'))} V2={len(fields_for('V2'))}")
    print(f"域 {len(DOMAINS)}  变量 {len(VARIABLES)}  派生关系 {len(DERIVATIONS)}")
    print(f"映射规则 V1={len(v1)} V2={len(v2)}  仅V1={len(v1 - v2)} 仅V2={len(v2 - v1)}")


if __name__ == "__main__":
    main()
