import asyncio
import json
from typing import Optional
from mcp import ClientSession
from mcp.client.sse import sse_client
from openai import OpenAI
import mcp.client.sse as _sse_mod
from httpx import AsyncClient as _BaseAsyncClient
from loguru import logger

from dotenv import load_dotenv

load_dotenv()  # load environment variables from .env

import httpx
_orig_request = httpx.AsyncClient.request

async def _patched_request(self, method, url, *args, **kwargs):
    # ensure follow_redirects is set so 307 → /messages/ works
    kwargs.setdefault("follow_redirects", True)
    return await _orig_request(self, method, url, *args, **kwargs)

httpx.AsyncClient.request = _patched_request
def llm_client(message: str):
    client = OpenAI()

    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are an intelligent Assistant. You will execute tasks as instructed"},
            {
                "role": "user",
                "content": message,
            },
        ],
    )

    result = completion.choices[0].message.content
    return result



def get_prompt_to_identify_tool_and_arguements(query, tools):
    tools_description = "\n".join([f"{tool.name}: {tool.description}, {tool.inputSchema}" for tool in tools.tools])
    return  ("You are a helpful assistant with access to these tools:\n\n"
                f"{tools_description}\n"
                "Choose the appropriate tool based on the user's question. \n"
                f"User's Question: {query}\n"                
                "If no tool is needed, reply directly.\n\n"
                "IMPORTANT: When you need to use a tool, you must ONLY respond with "                
                "the exact JSON object format below, nothing else:\n"
                "Keep the values in str "
                "{\n"
                '    "tool": "tool-name",\n'
                '    "arguments": {\n'
                '        "argument-name": "value"\n'
                "    }\n"
                "}\n\n")
    


async def main(query:str):
    sse_url = "http://localhost:8100/sse"

    # 1) Open SSE → yields (in_stream, out_stream)
    
    headers = {"x-api-key":"secretkey"}
    async with sse_client(url=sse_url,headers=headers) as (in_stream, out_stream):
        # 2) Create an MCP session over those streams
        async with ClientSession(in_stream, out_stream) as session:
            # 3) Initialize
            info = await session.initialize()
            logger.info(f"Connected to {info.serverInfo.name} v{info.serverInfo.version}")

            # 4) List tools
            tools = (await session.list_tools())
            logger.info(tools)            
            
            prompt = get_prompt_to_identify_tool_and_arguements(query,tools)
            logger.info(f"Printing Prompt \n {prompt}")
            
            response = llm_client(prompt)
            print(response)
            
            tool_call = json.loads(response)
                        
            result = await session.call_tool(tool_call["tool"], arguments=tool_call["arguments"])
            logger.success(f"User query: {query}, Tool Response: {result.content[0].text}")

            

if __name__ == "__main__":
    
    queries = ["What is the time in Bengaluru?", "What is the weather like right now in Dubai?"]
    for query in queries:
        asyncio.run(main(query))
