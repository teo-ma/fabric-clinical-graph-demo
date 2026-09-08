"""Graph (GQL) and Ontology data sources for the clinical Data Agent.

Kept separate from the lakehouse config so the GQL example queries stay readable.
Node label is ClinicalNode and edge label is CLINICAL_RELATIONSHIP, matching the
graph model created by deploy_03_graph_model.py.
"""

from __future__ import annotations

GRAPH_NAME = "ClinicalKnowledgeGraph"
ONTOLOGY_NAME = "ClinicalDevelopmentOntology"

GRAPH_DESCRIPTION = (
    "跨六个源系统的统一临床知识图谱，用 GQL 做多跳关系遍历。"
    "适合回答影响面、传播链、连通性这类需要沿关系走多步的问题，"
    "例如某个批次影响到哪些受试者、某个化合物与某个不良事件之间经过哪些中间实体。"
)

GRAPH_INSTRUCTIONS = """本图为跨六个源系统的统一临床知识图谱。

节点标签统一为 ClinicalNode，边标签统一为 CLINICAL_RELATIONSHIP。

节点属性：
NodeId 节点编号；NodeType 英文类别；NodeTypeZh 中文类别；DisplayNameZh 中文名称；
SourceSystem 来源系统（ctms、edc、safety、lims、knowledge、supply）；
StudyId 所属研究；Category 分类；Status 状态；NumericValue 数值；EventDate 日期。

NodeType 取值：Compound 化合物、Target 靶点、Pathway 生物通路、Biomarker 生物标志物、
AEType 不良事件术语、Study 临床研究、Site 研究中心、Investigator 研究者、
Subject 受试者、Visit 访视、LabResult 异常检验结果、AdverseEvent 不良事件、
SafetySignal 安全信号、Batch 药品批次、Shipment 运单、ProtocolDeviation 方案偏离。

边属性：
RelationshipType 英文关系；RelationshipTypeZh 中文关系；EdgeClass 取值 知识 或 运营；
EvidenceGrade 证据等级 A 到 D；Confidence 置信度；ClinicalCost 证据成本，越小证据越强。

写 GQL 时的约定：
一、多跳遍历使用 -[:CLINICAL_RELATIONSHIP]->{1,4} 这种数量限定写法，跳数上限不要超过 5。
二、过滤条件写在节点模式内部，例如 (n:ClinicalNode WHERE n.NodeId = 'CMP-001')。
三、返回路径时用 TO_JSON_STRING(route) 与 size(edges(route)) 给出路径与跳数。
四、结果必须 LIMIT，默认不超过 20 行。
五、关键编号：SYN-101 为 CMP-001，SYN-401 为 CMP-005，药物性肝损伤为 PT-DILI，
QT间期延长为 PT-QTP，温度偏移批次为 BATCH-007。"""

GRAPH_FEW_SHOTS = [
    ("从研究化合物 SYN-101 到药物性肝损伤，图上有哪些多跳路径？",
     "MATCH route = (src:ClinicalNode WHERE src.NodeId = 'CMP-001')"
     "-[:CLINICAL_RELATIONSHIP]->{1,4}"
     "(dst:ClinicalNode WHERE dst.NodeId = 'PT-DILI') "
     "RETURN TO_JSON_STRING(route) AS routeJson, size(edges(route)) AS hopCount "
     "ORDER BY hopCount ASC LIMIT 10;"),
    ("批次 BATCH-007 在图上关联到哪些研究中心？",
     "MATCH (b:ClinicalNode WHERE b.NodeId = 'BATCH-007')"
     "-[:CLINICAL_RELATIONSHIP]->{1,2}"
     "(s:ClinicalNode WHERE s.NodeType = 'Site') "
     "RETURN DISTINCT s.NodeId AS siteId, s.DisplayNameZh AS siteName LIMIT 20;"),
    ("安全信号 SIG-002 通过哪些不良事件关联到受试者？",
     "MATCH (subj:ClinicalNode WHERE subj.NodeType = 'Subject')"
     "-[:CLINICAL_RELATIONSHIP]->(ae:ClinicalNode WHERE ae.NodeType = 'AdverseEvent')"
     "-[:CLINICAL_RELATIONSHIP]->(sig:ClinicalNode WHERE sig.NodeId = 'SIG-002') "
     "RETURN subj.NodeId AS subjectId, ae.DisplayNameZh AS adverseEvent, "
     "ae.Category AS seriousness LIMIT 20;"),
    ("统一图谱里各类节点分别有多少个？",
     "MATCH (n:ClinicalNode) "
     "RETURN n.NodeTypeZh AS nodeType, count(*) AS nodeCount "
     "ORDER BY nodeCount DESC LIMIT 20;"),
    ("图上有哪些跨源系统的连接关系？",
     "MATCH (a:ClinicalNode)-[e:CLINICAL_RELATIONSHIP]->(b:ClinicalNode) "
     "WHERE a.SourceSystem <> b.SourceSystem "
     "RETURN a.SourceSystem AS fromSystem, b.SourceSystem AS toSystem, "
     "e.RelationshipTypeZh AS relationship, count(*) AS edgeCount "
     "ORDER BY edgeCount DESC LIMIT 20;"),
]

ONTOLOGY_DESCRIPTION = (
    "临床开发业务语义层，定义化合物、临床研究、研究中心、受试者、不良事件、安全信号、"
    "药品批次与实验室检验结果这些业务概念及其相互关系，实体绑定横跨五个源系统。"
    "适合回答需要业务术语理解的问题，例如某个概念的定义、某类实体有哪些属性、"
    "两个业务概念之间是什么关系。"
)
