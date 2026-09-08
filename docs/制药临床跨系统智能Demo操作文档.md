# 制药临床跨系统智能 Demo 操作文档

更新时间：2026-09-09

> 本文档是给演示人用的操作手册，包含每一步的点击路径、可直接复制的查询语句、
> 预期结果和故障处理。业务背景与价值论述见
> [演示手册](制药临床跨系统智能Demo演示手册.md)。
>
> 全部为合成数据，不构成任何真实医学或用药结论。

---

## 1. 环境入口

| 资源 | 链接 |
|---|---|
| 工作区 | https://app.fabric.microsoft.com/groups/f630b8e9-2637-402a-b5f0-837329a1fc26/list |
| 图模型 ClinicalKnowledgeGraph | https://app.fabric.microsoft.com/groups/f630b8e9-2637-402a-b5f0-837329a1fc26/graph/e43bec85-7b84-48ca-b15f-b9c3494ec1be |
| 本体 ClinicalDevelopmentOntology | https://app.fabric.microsoft.com/groups/f630b8e9-2637-402a-b5f0-837329a1fc26/ontologies/3e6302f2-d9f8-4984-8f74-cf63c31c865d |
| 数据代理 ClinicalInsightAgent | https://app.fabric.microsoft.com/groups/f630b8e9-2637-402a-b5f0-837329a1fc26/aiskills/b9342643-468f-4cea-aa36-11ce3a354c90 |

容量为 `capacityf2`，SKU F4，Central US。

---

## 2. 演示前检查清单

建议演示开始前 15 分钟完成，逐项打勾。

| # | 检查项 | 操作 | 通过标准 |
|---|---|---|---|
| 1 | 容量在线 | 打开工作区 | 内容列表正常加载，不提示容量暂停 |
| 2 | 图数据已摄取 | 打开图模型，等待画布加载 | 能看到 ClinicalNode 节点类型，且不报错 |
| 3 | 图可查询 | 在图的代码编辑器运行第 4 节的查询 A，或在代理里问图统计问题 | 返回 16 类节点，合计 1555 个 |
| 4 | 本体可打开 | 打开本体项目 | 左侧 Explorer 列出 8 个实体类型 |
| 5 | 代理可问数 | 在数据代理里问第 5 节的问题 Q2 | 返回 3 家中心、18 名受试者、13 条严重不良事件 |
| 6 | 浏览器已登录 | 提前登录 Fabric 门户 | 演示时不出现登录跳转 |

若第 3 项失败，见第 8 节故障处理。

---

## 3. 演示动线

总时长约 20 分钟。顺序有意为之：先给冲击力，再讲深度，最后讲治理。

| 环节 | 时长 | 界面 | 目的 |
|---|---:|---|---|
| 开场：跨系统溯源 | 5 分钟 | 数据代理 | 让业务用户直接看到价值 |
| 图原生多跳 | 5 分钟 | 图模型代码编辑器 | 证明是实时遍历而非预制报表 |
| 证据深度 | 5 分钟 | 数据代理 | 区分"最短"与"最优" |
| 语义层与治理 | 5 分钟 | 本体 | 从技术 Demo 上升到平台方案 |

---

## 4. 图模型操作：GQL 查询

打开图模型链接，选择 **Code editor**（代码编辑器），逐条粘贴运行。

### 查询 A：图规模总览

用途：开场展示统一图谱的规模与跨系统覆盖。

```gql
MATCH (n:ClinicalNode)
RETURN n.NodeTypeZh AS 节点类型, count(*) AS 数量
ORDER BY 数量 DESC
LIMIT 20;
```

预期返回 16 类节点，合计 1555 个。前几名为访视 652、异常检验结果 529、
受试者 120、不良事件 109。

### 查询 B：跨源系统连接

用途：证明这张图真的把六个系统连起来了，这是最能说明架构价值的一条查询。

```gql
MATCH (a:ClinicalNode)-[e:CLINICAL_RELATIONSHIP]->(b:ClinicalNode)
WHERE a.SourceSystem <> b.SourceSystem
RETURN a.SourceSystem AS 起点系统, b.SourceSystem AS 终点系统,
       e.RelationshipTypeZh AS 关系, count(*) AS 边数
ORDER BY 边数 DESC
LIMIT 20;
```

讲解要点：每一行都是一条跨系统的业务关联。传统架构下这些关联需要人工写 ETL 逐一打通。

已实测的返回结果（在数据代理中用自然语言提问同样可得）：

| 关系 | 起点 → 终点 | 边数 | 跨越的系统 |
|---|---|---:|---|
| HAS_VISIT | Subject → Visit | 652 | CTMS → EDC |
| MEASURES | LabResult → Biomarker | 529 | LIMS → Knowledge |
| HAS_LAB_RESULT | Visit → LabResult | 529 | EDC → LIMS |
| USED_BATCH | Visit → Batch | 481 | EDC → Supply |
| CODED_AS | AdverseEvent → AEType | 109 | Safety → Knowledge |
| EXPERIENCED | Subject → AdverseEvent | 109 | CTMS → Safety |
| DELIVERED_TO | Shipment → Site | 27 | Supply → CTMS |
| BATCH_OF | Batch → Compound | 9 | Supply → Knowledge |

这张表是整场演示里最能说明架构价值的一页，建议重点展开。

### 查询 C：批次质量事件影响面

用途：与数据代理的 Q2 呼应，展示同一个问题在图上的原生表达。

```gql
MATCH route = (b:ClinicalNode WHERE b.NodeId = 'BATCH-007')
  -[:CLINICAL_RELATIONSHIP]->{1,2}
  (s:ClinicalNode WHERE s.NodeType = 'Site')
RETURN DISTINCT s.NodeId AS 中心编号, s.DisplayNameZh AS 中心名称
LIMIT 20;
```

预期返回 3 家中心：西安长安医院、武汉江城医院、芝加哥医学中心。

### 查询 D：机制路径多跳遍历

用途：展示图的多跳能力，与数据代理的 Q1 呼应。

```gql
MATCH route = (src:ClinicalNode WHERE src.NodeId = 'CMP-001')
  -[:CLINICAL_RELATIONSHIP]->{1,4}
  (dst:ClinicalNode WHERE dst.NodeId = 'PT-DILI')
RETURN TO_JSON_STRING(route) AS 路径, size(edges(route)) AS 跳数
ORDER BY 跳数 ASC
LIMIT 10;
```

预期返回 4 条 4 跳路径。讲解要点：跳数都一样，光靠"最短"分不出优劣，
这正是下一步要讲的证据成本的意义。

### 查询 E：安全信号的受试者证据

```gql
MATCH (subj:ClinicalNode WHERE subj.NodeType = 'Subject')
  -[:CLINICAL_RELATIONSHIP]->(ae:ClinicalNode WHERE ae.NodeType = 'AdverseEvent')
  -[:CLINICAL_RELATIONSHIP]->(sig:ClinicalNode WHERE sig.NodeId = 'SIG-002')
RETURN subj.NodeId AS 受试者, ae.DisplayNameZh AS 不良事件,
       ae.Category AS 严重性
LIMIT 20;
```

### GQL 语法要点

- 所有查询以 `MATCH` 开头，以分号结束。
- 多跳用 `-[:CLINICAL_RELATIONSHIP]->{1,4}` 这种数量限定写法，上限不要超过 5。
- 过滤条件写在节点模式内部：`(n:ClinicalNode WHERE n.NodeId = 'CMP-001')`。
- 必须加 `LIMIT`，结果超过 64 MB 会被截断。
- 节点标签统一为 `ClinicalNode`，边标签统一为 `CLINICAL_RELATIONSHIP`。

---

## 5. 数据代理操作：中文问数

打开数据代理链接，在对话框依次粘贴。每个问题的预期答案已实测验证。

### Q2 跨系统溯源（建议作为开场）

```text
批次 BATCH-007 发生温度偏移，影响了哪些中心和受试者？其中谁发生了严重不良事件？
```

预期：3 家中心、18 名受试者、13 条严重不良事件，全部为 QT间期延长，CTCAE 3 至 4 级。

讲解要点：这个答案跨了供应链、CTMS、EDC、安全数据库四个系统。
请客户估算他们今天做同样的事需要多久。

### Q1 机制解释

```text
研究化合物 SYN-101 与药物性肝损伤之间有哪些机制通路？哪条证据最强？
```

预期：4 条链路，跳数均为 4，按证据成本排序。最强为
`SYN-101 → 细胞色素P450 3A4 → 肝药物代谢通路 → 丙氨酸氨基转移酶 → 药物性肝损伤`，
成本 0.39，最差等级 B，最低置信度 0.83。

讲解要点：跳数相同，只有证据成本能区分优劣。"最佳"在临床语境必须有明确口径。

### Q3 信号证据链

```text
安全信号 SIG-002 的证据链是什么？涉及多少受试者和异常检验？
```

预期：关联 43 例不良事件，其中 24 例严重，涉及 36 名受试者、4 家中心，
95 条支持性异常检验，机制路径为
`SYN-401 → hERG 钾离子通道 → 心肌复极通路 → QTcF 间期 → QT间期延长`。

### Q4 风险外推

```text
与 SYN-101 共享靶点或通路的其他化合物有哪些？可能共享哪些风险？
```

预期：SYN-102 共享 JAK1 靶点，SYN-201 共享肝药物代谢通路，
SYN-401 共享骨髓造血通路，并列出各自可能共享的不良事件风险。

### Q5 中心风险画像

```text
哪些研究中心风险最高？分别因为什么？
```

预期：武汉江城医院 46.86、芝加哥医学中心 46.00、大阪临床中心 42.35、
西安长安医院 39.00，均为中风险，并说明各自的构成原因。

### 图关系类问题（走 GQL）

以下问题结果表里没有预先算好，代理会调用图数据源生成 GQL。**两道问题均已在门户实测通过。**

```text
统一图谱里各类节点分别有多少个？请按数量从多到少列出。
```

实测返回 16 类节点，合计 1555 个：Visit 652、LabResult 529、Subject 120、
AdverseEvent 109、ProtocolDeviation 46、Shipment 27、Investigator 12、Site 12、
Batch 9、Biomarker 8、Pathway 7、AEType 7、Target 6、Compound 5、Study 3、SafetySignal 3。
响应用时约 38 秒，回答中会明确声明“使用 GQL 统计”。

```text
图上有哪些跨源系统的连接关系？请按边的数量排序，列出前 8 行。
```

实测返回的前 8 条与第 4 节查询 B 的表格完全一致。

演示提示：这类问题响应在 30 到 60 秒，比结果表类问题慢，讲解时可以同步说明
这是实时图遍历而不是查预制报表。

---

## 6. 本体操作

打开本体链接。左侧 Explorer 展开 **Entity Types**，可看到 8 个实体类型。

建议演示以下三点，每点一句话：

**第一点，跨源绑定**。点开 `Subject`（受试者），选择 **Configure** 页签，
展示它绑定到 CTMS 的 `subjects` 表。再点开 `AdverseEvent`，
展示它绑定到 Safety 的 `adverse_events` 表。

说明：8 个实体分别绑定到 5 个不同的源系统 Lakehouse。这不是一个库上的视图，
是真正的跨系统语义层。

**第二点，业务术语**。展示实体的中文描述与同义词。
例如 `Subject` 的同义词包含"病人""患者""入组对象"。

说明：业务用户无论用哪个说法提问，语义层都能对上同一个概念。
规模一大，靠提示词维护术语表撑不住。

**第三点，实例数据**。选择 **Overview** 页签，展示实体的实例分布图表。

说明：语义层不是一张静态的定义图，它连着真实数据。

### 本体的定位说明

对客讲解时请按这个口径，避免被反问：

> Graph 负责算得对，Ontology 负责说得清、管得住、能复用。

不要说 Ontology 是路径查询的必需组件。客户会问不用它行不行，答案是行，
这个反问会削弱整场演示。

---

## 7. 数据源配置说明

数据代理已配置三个数据源，可在代理页面左侧 Explorer 查看。

| 数据源 | 类型 | 查询语言 | 承担的问题 |
|---|---|---|---|
| LH_Curated_统一临床图谱 | Lakehouse | T-SQL | Q1 到 Q5 五类预先计算好的业务问题 |
| ClinicalKnowledgeGraph | Graph 模型 | GQL | 结果表未覆盖的关系探索与图统计 |
| ClinicalDevelopmentOntology | Ontology | 本体原生 | 业务概念定义与实体关系理解 |

代理指令里写明了路由规则：五类业务问题优先走结果表；
关系探索类问题走图；概念定义类问题走本体；并要求回答时说明本次用的是哪个数据源。

Lakehouse 数据源配置了 5 条 SQL 示例问法，图数据源配置了 5 条 GQL 示例问法，
用于引导 NL2SQL 与 NL2GQL 生成正确查询。

---

## 8. 故障处理

| 现象 | 原因 | 处理 |
|---|---|---|
| 图查询返回空结果 | 图模型未摄取数据，或映射与源表不符 | 打开图模型点 **Save** 触发重新摄取；或用脚本触发刷新作业 |
| 脚本调 MCP 问图类问题报“访问凭证无效” | 已确认的已知限制，见下方说明 | 演示一律在门户交互会话中进行，不要用脚本跑图类问题 |
| 代理回答说查询失败 | 图数据源不可用 | 当场切换到结果表类问题 Q1 到 Q5，这五类不依赖图查询 |
| 创建项目报 429 CapacityLimitExceeded | 容量被限流 | 等待 CU 平滑扣减回落，或临时上调 SKU |
| 门户看不到本体项目类型 | 页面缓存了启用前的工作负载列表 | 硬刷新页面 |

### 已确认的已知限制：GQL 与 MCP

图查询（GQL）**在门户交互会话中完全正常**，已实测两类问题均返回正确结果。

但通过 MCP 端点用 Azure CLI 令牌调用时，图查询会返回 `Access token is invalid`，
而**同一个代理里 Lakehouse 的 SQL 查询完全正常**。图刷新作业已成功完成，
因此不是图本身或数据的问题，而是图数据平面调用需要交互式会话身份。

实际影响：

- 演示不受影响，因为演示本来就在门户里进行。
- 自动化回归脚本 `tools/test_graph_questions.py` 目前只能验证路由是否正确（代理确实去调图），
  不能验证 GQL 结果。图类结果的回归需在门户人工确认。
- `tools/test_data_agent.py` 覆盖的五类业务问题走 SQL，MCP 路径完全可用，可作为自动化回归。

触发图刷新的脚本方式：

```bash
python3 - <<'PY'
import sys; sys.path.insert(0, 'tools')
from fabric_common import FABRIC, call, load_state
st = load_state()
call('POST', f"{FABRIC}/v1/workspaces/{st['workspace_id']}"
     f"/items/{st['graph_model_id']}/jobs/instances?jobType=RefreshGraph",
     {'executionData': {}})
PY
```

查看刷新状态：

```bash
python3 - <<'PY'
import sys; sys.path.insert(0, 'tools')
from fabric_common import FABRIC, call, load_state
st = load_state()
code, payload, _ = call('GET', f"{FABRIC}/v1/workspaces/{st['workspace_id']}"
                        f"/items/{st['graph_model_id']}/jobs/instances")
for job in payload.get('value', []):
    print(job['jobType'], job['status'], job['startTimeUtc'])
PY
```

---

## 9. 重建与回归

全部部署脚本按顺序执行即可从零重建，所有脚本均幂等，可重复运行。

```bash
python3 tools/generate_clinical_multisource.py     # 生成六个源系统的合成数据
python3 tools/validate_graph_logic.py              # 本地验证图逻辑与五类业务答案
python3 tools/deploy_01_workspace_and_data.py      # 工作区、7 个 Lakehouse、上传着陆数据
python3 tools/deploy_02_notebooks.py               # 部署并运行摄取与图谱笔记本
python3 tools/deploy_03_graph_model.py             # 图模型，含定义回读校验
python3 tools/deploy_04_ontology.py                # 本体，8 实体 9 关系跨 5 源系统
python3 tools/deploy_05_data_agent.py              # 数据代理，三个数据源
```

回归测试：

```bash
# 五类业务问题（走结果表）
/Users/tema/.cache/fabric-data-agent-venv/bin/python tools/test_data_agent.py

# 图关系类问题（走 GQL）
/Users/tema/.cache/fabric-data-agent-venv/bin/python tools/test_graph_questions.py
```

`tools/validate_graph_logic.py` 会在本地完整跑一遍五类分析并断言结果，
建议每次改动数据或图逻辑后先跑它，再上云。

---

## 10. 演示中不要做的事

- 不要临时改数据或重跑笔记本，容量限流会打断演示节奏。
- 不要在客户面前第一次打开某个界面，所有界面提前预热过一遍。
- 不要把 Ontology 说成路径查询的必需组件。
- 不要用真实药品名或真实机构名类比，本 Demo 全部为虚构标识。
- 不要承诺 Graph 与 Ontology 的预览能力可直接用于受监管临床决策。
