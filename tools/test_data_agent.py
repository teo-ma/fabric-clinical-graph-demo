"""End-to-end Chinese question test against the published Data Agent over MCP."""

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
    "研究化合物 SYN-101 与药物性肝损伤之间有哪些机制通路？哪条证据最强？",
    "批次 BATCH-007 发生温度偏移，影响了哪些中心和受试者？其中谁发生了严重不良事件？",
    "安全信号 SIG-002 的证据链是什么？涉及多少受试者和异常检验？",
    "与 SYN-101 共享靶点或通路的其他化合物有哪些？可能共享哪些风险？",
    "哪些研究中心风险最高？分别因为什么？",
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
                                 timeout=600) as http_client:
        async with streamable_http_client(url, http_client=http_client) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                tools = await session.list_tools()
                tool = tools.tools[0]
                key = next(iter(tool.input_schema.get("properties", {})), "userQuestion")
                print(f"工具 {tool.name}  入参 {key}\n")

                for i, question in enumerate(QUESTIONS, start=1):
                    result = await session.call_tool(tool.name, {key: question})
                    if getattr(result, "structured_content", None):
                        answer = json.dumps(result.structured_content, ensure_ascii=False)
                    else:
                        answer = "\n".join(c.text for c in result.content
                                           if hasattr(c, "text"))
                    print(f"--- 问题 {i} ---\n{question}\n{answer.strip()[:1300]}\n")


if __name__ == "__main__":
    asyncio.run(main())
