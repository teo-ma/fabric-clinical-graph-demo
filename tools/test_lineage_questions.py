"""Ask the lineage agent the questions a data manager would actually ask.

Written the way a clinical data manager, a statistical programmer and someone new
to the team would phrase them: no schema names, no mention of graphs or ontologies.
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

QUESTIONS = [
    ("数据管理员",
     "治疗组这个信息，最后交出去的数据集里是从哪张表单哪一栏来的？如果有好几个来源，哪个最直接？"),
    ("统计程序员",
     "我们打算把给药开始日期这一栏改掉，会连累到哪些数据集？改完要重新核对哪些东西？"),
    ("数据管理负责人",
     "这次标准版本升级，映射规则到底改了哪些地方？"),
    ("质量负责人",
     "还有哪些该交的字段目前根本没人采？哪些是必须要有的？"),
    ("新入职同事",
     "有些数据被放进了所谓的补充数据集，这是什么意思？这些数据有没有可能挪回正式数据集？"),
    ("统计程序员",
     "哪几栏一改动牵连最大？我想先把风险最高的几个盯住。"),
]


def token() -> str:
    proc = subprocess.run(
        ["az", "account", "get-access-token", "--resource",
         "https://api.fabric.microsoft.com", "--query", "accessToken", "-o", "tsv"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, check=False)
    return proc.stdout.strip()


async def main() -> None:
    url = load_state(STATE)["data_agent_mcp"]
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
