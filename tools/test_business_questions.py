"""Check that business-phrased questions still route to the intended data source.

The three questions are written the way a safety physician, a program sponsor and
a new team member would actually ask them, with no product or schema vocabulary.
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
    ("安全医师", "SYN-101 的肝损伤风险，机制上怎么解释？哪种解释证据最强？"),
    ("项目发起人", "我们到底把哪几个系统的数据打通了？各自打通了多少条关联？"),
    ("新入职同事", "“受试者”在我们的数据体系里是怎么定义的？它和不良事件、研究中心分别是什么关系？"),
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

                for role, question in QUESTIONS:
                    result = await session.call_tool(tool.name, {key: question})
                    if getattr(result, "structured_content", None):
                        answer = json.dumps(result.structured_content, ensure_ascii=False)
                    else:
                        answer = "\n".join(c.text for c in result.content
                                           if hasattr(c, "text"))
                    print(f"===== {role} =====\n问：{question}\n\n{answer.strip()}\n")


if __name__ == "__main__":
    asyncio.run(main())
