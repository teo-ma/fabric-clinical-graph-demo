"""Probe each data source AND check the agent does not answer with a wrong metric.

Two distinct failure modes are checked:

1. Availability — a question only the target source can answer. The lakehouse SQL
   source works with an az CLI token, but the graph data plane may need an
   interactive portal session, so a fallback shows up here instead of silently.

2. Correctness of measure — a question that has a right answer AND a tempting
   wrong one. "How often is each algorithm used" can be answered correctly from
   gold_algorithm_usage (per hop, 8 algorithms) or wrongly from the algorithms
   column of gold_variable_lineage (per path, 14 algorithm strings containing an
   arrow). The wrong answer looks entirely plausible, so it is asserted against
   explicitly rather than eyeballed.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fabric_common import load_state  # noqa: E402

STATE = Path(__file__).resolve().parents[1] / "fabric" / "lineage_deployment_state.json"

FAILURE_MARKERS = ["不可用", "无法访问", "未能查询", "查询失败", "access token",
                   "not ready", "not available", "无法连接", "没有权限"]

# (标签, 问题, 必须出现的词, 必须不出现的词)
PROBES = [
    ("图·多跳遍历",
     "从知情同意签署日期这个字段出发，四跳以内能触及哪些 SDTM 变量？请给出跳数。",
     ["DSSTDTC"], []),
    ("图·任意连通",
     "CRF 的检验结果这一栏，和 LB.LBNRIND 之间是怎么连起来的？中间经过哪些变量？",
     ["LBORRES", "LBSTRESC"], []),
    ("本体·概念关系",
     "在我们的数据体系里，受控术语和 SDTM 变量是什么关系？受控术语集又是什么？",
     ["术语", "变量"], []),
    ("口径·算法次数",
     "各种转换方式分别用了多少次？请按次数从多到少列出。",
     ["Copy", "DT2DTC", "Derived", "Coding"],
     # 出现箭头就说明它又拿整条路径的算法串当算法名用了。
     ["->", "→"]),
]


def token() -> str:
    proc = subprocess.run(
        ["az", "account", "get-access-token", "--resource",
         "https://api.fabric.microsoft.com", "--query", "accessToken", "-o", "tsv"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, check=False)
    return proc.stdout.strip()


async def main() -> None:
    url = load_state(STATE)["data_agent_mcp"]
    verdicts = []
    async with httpx.AsyncClient(headers={"Authorization": "Bearer " + token()},
                                 timeout=900) as http_client:
        async with streamable_http_client(url, http_client=http_client) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                tool = (await session.list_tools()).tools[0]
                key = next(iter(tool.input_schema.get("properties", {})), "userQuestion")

                for label, question, must, must_not in PROBES:
                    result = await session.call_tool(tool.name, {key: question})
                    if getattr(result, "structured_content", None):
                        answer = json.dumps(result.structured_content, ensure_ascii=False)
                    else:
                        answer = "\n".join(c.text for c in result.content
                                           if hasattr(c, "text"))
                    missing = [m for m in must if m not in answer]
                    forbidden = [m for m in must_not if m in answer]
                    failed = [m for m in FAILURE_MARKERS if m.lower() in answer.lower()]

                    if forbidden:
                        verdict = "口径错误"
                    elif failed or missing:
                        verdict = "不可用/回退"
                    else:
                        verdict = "通过"

                    verdicts.append((label, verdict, missing, forbidden, failed))
                    print(f"===== {label} · {verdict} =====\n问：{question}\n"
                          f"缺失 {missing}  违禁 {forbidden}  失败标记 {failed}\n\n"
                          f"{answer.strip()[:1400]}\n")

    print("=" * 64)
    for label, verdict, missing, forbidden, failed in verdicts:
        print(f"{verdict:12s} {label}")
    bad = [v for v in verdicts if v[1] == "口径错误"]
    if bad:
        raise SystemExit(f"存在口径错误的回答，必须修掉：{[b[0] for b in bad]}")


if __name__ == "__main__":
    asyncio.run(main())
