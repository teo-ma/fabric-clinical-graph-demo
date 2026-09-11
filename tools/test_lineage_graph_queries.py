"""Verify the graph answers the multi-hop questions via the GQL Query API.

The Data Agent's MCP endpoint cannot reach the graph data plane with an az CLI
token ("Access token is invalid"), so a graph question asked through MCP fails.
That is an auth limitation of the agent path, NOT a broken graph: the same
queries succeed against the GraphModel executeQuery API. This script proves it,
so the demo can state the limitation precisely instead of guessing, and so
automation has a working path.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fabric_common import FABRIC, call, load_state  # noqa: E402

STATE = Path(__file__).resolve().parents[1] / "fabric" / "lineage_deployment_state.json"

QUERIES = [
    ("多跳遍历 · 知情同意签署日期四跳内触及的变量",
     "MATCH p = (f:SpecNode WHERE f.NodeId = 'CRF:IC.ICDAT')"
     "-[:SPEC_RELATIONSHIP]->{1,4}(v:SpecNode WHERE v.NodeType = 'SDTMVariable') "
     "RETURN v.DisplayNameZh AS 受影响变量, size(edges(p)) AS 跳数 "
     "ORDER BY 跳数 DESC LIMIT 10;",
     ["DSSTDTC"]),
    ("任意连通 · 检验结果到参考范围指示",
     "MATCH p = (f:SpecNode WHERE f.NodeId = 'CRF:LB.LBORRES')"
     "-[:SPEC_RELATIONSHIP]->{1,4}(v:SpecNode WHERE v.NodeId = 'SDTM:LB.LBNRIND') "
     "RETURN TO_JSON_STRING(p) AS 路径, size(edges(p)) AS 跳数 ORDER BY 跳数 ASC LIMIT 3;",
     ["LBSTRESC"]),
    ("单跳算法分布 · 与结果表口径必须一致",
     "MATCH ()-[r:SPEC_RELATIONSHIP WHERE r.RelationshipType IN ['MAPS_TO','DERIVES'] "
     "AND r.Algorithm IS NOT NULL]->() "
     "RETURN r.Algorithm AS 转换方式, count(*) AS 次数 GROUP BY 转换方式 "
     "ORDER BY 次数 DESC;",
     ["Copy", "Derived"]),
    ("跨域影响 · 影响最多域的字段",
     "MATCH (f:SpecNode WHERE f.NodeType = 'CRFField')"
     "-[:SPEC_RELATIONSHIP]->{1,4}(v:SpecNode WHERE v.NodeType = 'SDTMVariable') "
     "RETURN f.DisplayNameZh AS 字段, count(DISTINCT v.Domain) AS 涉及域数 "
     "GROUP BY 字段 ORDER BY 涉及域数 DESC LIMIT 5;",
     ["给药开始日期"]),
]


def query(ws_id: str, graph_id: str, gql: str) -> list[dict]:
    status, payload, _ = call(
        "POST", f"{FABRIC}/v1/workspaces/{ws_id}/GraphModels/{graph_id}"
                "/executeQuery?preview=true", {"query": gql})
    if status != 200:
        raise RuntimeError(f"HTTP {status}: {json.dumps(payload)[:300]}")
    code = (payload.get("status") or {}).get("code")
    if code not in ("00000", None):
        raise RuntimeError(f"GQL {code}: {json.dumps(payload, ensure_ascii=False)[:400]}")
    return (payload.get("result") or {}).get("data") or []


def main() -> None:
    state = load_state(STATE)
    ws_id, graph_id = state["workspace_id"], state["graph_model_id"]
    failures = []

    for label, gql, expected in QUERIES:
        try:
            rows = query(ws_id, graph_id, gql)
        except RuntimeError as exc:
            print(f"[失败] {label}\n   {exc}\n")
            failures.append(label)
            continue
        blob = json.dumps(rows, ensure_ascii=False)
        missing = [e for e in expected if e not in blob]
        mark = "通过" if rows and not missing else "失败"
        if mark == "失败":
            failures.append(label)
        print(f"[{mark}] {label}  返回 {len(rows)} 行"
              + (f"  缺失 {missing}" if missing else ""))
        for row in rows[:5]:
            print("   ", json.dumps(row, ensure_ascii=False)[:220])
        print()

    if failures:
        raise SystemExit(f"以下图查询未通过：{failures}")
    print("图查询全部通过。图本身可用，MCP 路径的令牌限制不影响图能力本身。")


if __name__ == "__main__":
    main()
