# CRF 到 SDTM 映射血缘 Demo 操作文档

从零复现整套 Demo 的步骤、每一步的验证方式，以及踩过的坑。
全部数据为示意性合成数据，与任何真实研究、真实映射规范无关。

---

## 一、环境前提

| 项目 | 要求 |
|---|---|
| Azure 订阅 | 有 Fabric 容量，SKU 需支持 DataAgent（F2 及以上，Trial FTL64 不支持） |
| 租户 | 需开启租户设置 `OntologyPreview`（"Users can create Ontology (preview) items"） |
| 本地 | `az login` 已登录到**正确的租户**；Python 3.10+ |
| MCP 测试 | `pip install mcp httpx`，需 Python 3.10+ |

### 先确认租户，这一步不能省

```bash
az account show --query "{sub:name,tenant:tenantId,user:user.name}" -o json
```

如果 `user` 里带 `#EXT#`，说明当前登录在一个来宾租户。此时 Fabric 会**看不到**你在
本租户创建的容量和工作区，`CapacityNotFound` 与 `404 WorkspaceNotFound` 看起来
就像环境被删了。用 `az account set --subscription <id>` 切回去。

另外，**暂停状态的容量不会出现在 Fabric REST 的容量列表里**，所以"容量消失"也可能
只是被暂停了。查真实状态要走 ARM：

```bash
az rest --method get --url "https://management.azure.com/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Fabric/capacities/<name>?api-version=2023-11-01" --query properties.state -o tsv
```

---

## 二、目录结构

```
data/spec/                              生成的七张规范 CSV
fabric/
  lineage_logic.py                      图构建 + 六类分析（纯 Python，无 Spark 依赖）
  lineage_deployment_state.json          部署状态，与 demo v2 的状态文件相互独立
  notebooks/
    11_ingest_spec.py                    CSV → Delta，含参照完整性校验
    12_build_lineage_graph.py            血缘图 + 治理结果表
tools/
  generate_crf_sdtm_spec.py             生成示意性规范数据
  validate_lineage_logic.py             本地验证，含参照完整性与口径断言
  deploy_lineage_01_data.py             工作区、湖仓、数据上传、笔记本
  deploy_lineage_02_graph.py            图模型 + GQL 冒烟测试
  deploy_lineage_03_ontology.py         本体 + 索引刷新 + 实例化校验
  deploy_lineage_04_data_agent.py       中文数据代理
  test_lineage_questions.py             六个业务问题端到端问答
  test_lineage_sources.py               三个数据源可用性 + 口径正确性探测
  test_lineage_graph_queries.py         GQL Query API 直连验证图能力
  livy_run.py                           Livy 会话跑 PySpark，用于拿真实报错
docs/                                   演示手册、本文档、幻灯片
```

`fabric/lineage_logic.py` 是**单一事实来源**：本地验证直接 import 它，部署时把它的
源码原样内联进笔记本（占位符 `# __LINEAGE_LOGIC__`）。这样本地跑通的逻辑与云端跑的
是同一份代码，不会出现两边漂移。

---

## 三、部署步骤

### 第 0 步 · 生成数据并本地验证

```bash
python3 tools/generate_crf_sdtm_spec.py
python3 tools/validate_lineage_logic.py
```

**必须先本地跑通再上云**。本地验证会检查参照完整性（字段是否有归属表单、规则是否
指向已定义的变量）和分析口径（算法次数是否等于带算法的边数）。这些检查最初只写在
云端笔记本里，结果一个数据缺陷跑到云端才暴露，白花了两轮 Spark 会话。

预期输出末尾：

```
参照完整性检查通过
...
全部断言通过。问题目录 7 条。
```

### 第 1 步 · 工作区、湖仓、数据、笔记本

```bash
python3 tools/deploy_lineage_01_data.py
```

创建工作区 `Fabric CRF-SDTM 血缘 Demo`、两个湖仓、上传 7 个 CSV，然后部署并运行
两个笔记本。脚本是幂等的，重跑会复用已有资源。

预期：`11_映射规范摄取 Completed`、`12_血缘图谱与治理洞察 Completed`。

### 第 2 步 · 图模型

```bash
python3 tools/deploy_lineage_02_graph.py
```

创建图模型、回读校验定义非空、等索引就绪、跑三条 GQL 冒烟测试。

预期：

```
回读校验通过：节点类型 ['SpecNode']，边类型 ['SPEC_RELATIONSHIP']，节点属性 13 个
  图索引节点数 186
图模型部署与 GQL 冒烟测试通过。
```

### 第 3 步 · 本体

```bash
python3 tools/deploy_lineage_03_ontology.py
```

导入本体定义、找到配套图模型、刷新索引、验证实例化。

预期：

```
回读校验通过：实体 7 个，关系 6 个，数据绑定 7 个
本体配套图模型 -> <id>
  本体索引 Completed
  实体总数 287
  SDTM 变量 102
  CRF 字段 59
本体已实例化并可查询。
```

**源表重写后需要重跑这一步**，否则本体查的还是旧数据。

### 第 4 步 · 数据代理

```bash
python3 tools/deploy_lineage_04_data_agent.py
```

预期回读到 3 个已发布数据源：

```
回读到已发布数据源 3 个：graph-CrfSdtmLineageGraph、lakehouse-LH_Lineage_血缘图谱、ontology-ClinicalDataStandardOntology
Lakehouse 选入 9 张表，SQL 示例 7 条，GQL 示例 5 条
```

---

## 四、验证

### 业务问答

```bash
python3 tools/test_lineage_questions.py
```

六个按业务口吻提的问题。回答应当包含具体数字与路径，且每次结尾带合成数据提示。

### 数据源可用性与口径正确性

```bash
python3 tools/test_lineage_sources.py
```

这个脚本查两类问题：

1. **可用性** —— 每题只有目标数据源能答，回退会立刻显形。
2. **口径正确性** —— 算法次数那题有一个"看起来很对但是错"的答案。
   `gold_variable_lineage.algorithms` 存的是整条路径的算法串（如
   `DT2DTC -> Derived`），按它分组得到的是**路径组合数**（14 种），不是
   **算法使用次数**（8 种）。脚本断言回答里不能出现箭头。

### 图能力

```bash
python3 tools/test_lineage_graph_queries.py
```

直连 GQL Query API，绕过代理的令牌限制，证明图本身可用。其中一条查询刻意与结果表
算同一个指标（单跳算法分布），两边数字必须一致——这是对口径的交叉验证。

---

## 五、踩过的坑

这些都是实际调试出来的，不是推测。

### 笔记本

| 现象 | 原因 | 修法 |
|---|---|---|
| 作业报 `System_Cancelled_Session_Statements_Failed`，任何地方都没有堆栈 | `# MAGIC %md` 块前少了 `# CELL ***` 分隔符，说明文字被当成 Python 执行 | markdown 块必须有自己的 CELL 分隔符 |
| `saveAsTable` / `spark.table` 失败 | API 创建的笔记本没有默认湖仓 | 用完整 `abfss://` 路径 |
| Delta 写入报 schema mismatch | 列变了但表还在 | `.option("overwriteSchema","true")` |

**拿真实报错的方法**：作业实例和 livySessions 都只给那句无用的话。用 Livy 会话跑
同样的代码就能拿到完整 traceback：

```bash
python3 tools/livy_run.py fabric/lineage_deployment_state.json spec /tmp/probe.py
```

注意创建 Livy 会话返回的是 **202**，不是 200/201。

### 读 CSV

`spark.read.schema(...)` 是**按位置**套用 schema 的，会无视表头。生成脚本里加一列
或改一下列顺序，每个值就整体错位一列，而且不报错。表现出来是下游分析结果为空或者
莫名的外键校验失败。

正确做法：`option("header","true")` 且**不给 schema**，然后断言必需列都在。

### 图模型

| 现象 | 说明 |
|---|---|
| `RefreshGraph` 返回 `Deduped` | `updateDefinition` 已自动排了一次刷新，这是成功不是失败 |
| `GROUP BY n.属性名` 报语法错误 | GQL 的 `GROUP BY` 只接受 `RETURN` 里的别名 |
| 不写 `GROUP BY` 报"既不在 GROUP BY 也不是聚合" | 同上，必须显式分组 |

正确写法：

```gql
MATCH (n:SpecNode) RETURN n.NodeTypeZh AS 类型, count(*) AS 数量
GROUP BY 类型 ORDER BY 数量 DESC;
```

判断索引是否真的建好，不要看刷新作业状态，直接查节点数轮询到预期值为止。

### 本体

导入定义**不等于**本体可查。服务会自动建一个配套图模型
`<本体名>_graph_<去掉横线的本体 id>`，实体只有在这个图刷新之后才会实例化。刷新之前
任何本体查询都报 `The Graph Model is not ready`。

本体项自己没有可用的 jobType（`RefreshOntology` / `Refresh` / `RefreshGraph` 都返回
`InvalidJobType`，`GET .../items/{ontologyId}/jobs/instances` 返回 400），必须对
配套图模型发 `RefreshGraph`。

### 最危险的一个坑：代理会悄悄答错

数据代理的某个数据源坏掉时，**它不会报错**。它会用模型自己的通用知识回答，或者更糟——
换一个数据源算出一个**口径不同但看起来合理**的数字。

实测例子：问"每种转换方式用了多少次"，图数据源不可用，于是它从 SQL 结果表里按
**整条路径的算法串**分组，给出了 14 项包含 `DT2DTC -> Derived` 这种"算法"的清单。
数字有理有据，排序也对，但答的根本不是同一个问题。

两个处理：

1. 代理指令里明确禁止跨数据源替代作答，该数据源不可用就说不可用然后停下。
2. 把容易被答错的口径**预先算好**成一张表（`gold_algorithm_usage`），让 SQL 也能答对。

单靠第 1 条不够——模型会觉得自己"找到了办法"。把正确口径准备好才是根治。

---

## 六、已知限制

| 限制 | 影响 | 应对 |
|---|---|---|
| 代理 MCP 端点用 az CLI 令牌访问图数据源报"访问令牌无效" | 脚本调用时图问题无法回答 | 门户交互会话内正常；自动化用 `executeQuery` API |
| 本体索引不随源表自动刷新 | 数据更新后本体查旧值 | 重跑第 3 步 |

`executeQuery` API 已验证可用：

```
POST https://api.fabric.microsoft.com/v1/workspaces/{ws}/GraphModels/{graphId}/executeQuery?preview=true
Body: {"query": "MATCH ...;"}
```

返回 `status.code = 00000`，数据在 `result.data`。

---

## 七、资源清单

| 类型 | 名称 |
|---|---|
| Workspace | Fabric CRF-SDTM 血缘 Demo |
| Lakehouse | LH_Spec_映射规范库 |
| Lakehouse | LH_Lineage_血缘图谱 |
| Notebook | 11_映射规范摄取 |
| Notebook | 12_血缘图谱与治理洞察 |
| GraphModel | CrfSdtmLineageGraph |
| Ontology | ClinicalDataStandardOntology |
| DataAgent | ClinicalDataLineageAgent |

本体会额外自动生成一个 GraphModel、一个 Lakehouse 和一个 SQLEndpoint，命名带
`ClinicalDataStandardOntology_graph_` / `_lh_` 前缀，不要手动删。

具体 id 见 `fabric/lineage_deployment_state.json`。

---

## 八、清理

```bash
python3 -c "
import sys; sys.path.insert(0,'tools')
from pathlib import Path
from fabric_common import FABRIC, call, load_state
st = load_state(Path('fabric/lineage_deployment_state.json'))
print(call('DELETE', f\"{FABRIC}/v1/workspaces/{st['workspace_id']}\")[0])
"
```

删除工作区会一并删除其中所有项。此操作不可撤销。
