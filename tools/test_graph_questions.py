"""Test that relationship-style questions actually route to the graph (GQL) source.

These questions are deliberately not answerable from the pre-computed gold tables,
so a correct answer proves the agent traversed the graph rather than running SQL.
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

QUESTIONS = [
    "统一图谱里各类节点分别有多少个？请按数量从多到少列出。",
    "图上有哪些跨源系统的连接关系？请按边的数量排序。",
    "从研究化合物 SYN-101 出发，最多走 4 跳能到达药物性肝损伤吗？请给出路径与跳数。",
    "批次 BATCH-007 在图上关联到哪些研究中心？",
    "本体里定义了哪些业务实体类型？受试者这个概念有哪些属性？",
]


def token() -> str:
    proc = subprocess.run(
        ["az", "account", "get-access-token", "--resource",
         "https://api.fabric.microsoft.com", "--query", "accessToken", "-o", "tsv"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, check=False)
    return proc.stdout.strip()


async def main() -> None:
    url = load_state()["data_agent_mcp"]
    async with httpx.AsyncClient(headers={"Authorization": "Bearer " + token()},
                                 timeout=900) as http_client:
        async with streamable_http_client(url, http_client=http_client) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                tool = (await session.list_tools()).tools[0]
                key = next(iter(tool.input_schema.get("properties", {})), "userQuestion")

                for i, question in enumerate(QUESTIONS, start=1):
                    result = await session.call_tool(tool.name, {key: question})
                    if getattr(result, "structured_content", None):
                        answer = json.dumps(result.structured_content, ensure_ascii=False)
                    else:
                        answer = "\n".join(c.text for c in result.content
                                           if hasattr(c, "text"))
                    print(f"===== 问题 {i} =====\n{question}\n\n{answer.strip()}\n")


if __name__ == "__main__":
    asyncio.run(main())
