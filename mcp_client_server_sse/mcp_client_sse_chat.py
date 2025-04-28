import ast
import asyncio
import json
import os
from typing import Dict, Optional
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
        ]
    )

    result = completion.choices[0].message.content
    return result



def get_prompt_to_identify_tool_and_arguments(query:str, tools:any, context=list):
    tools_description = "\n".join([f"{tool.name}: {tool.description}, {tool.inputSchema}" for tool in tools.tools])
    return  ("You are a helpful assistant with access to these tools and context:\n\n"
                f"CONTEXT: {context} \n"
                f"{tools_description}\n"
                "Choose the appropriate tool based on the user's question. \n"
                f"User's Question: {query}\n"                
                "If no tool is needed, reply directly.\n\n"
                "IMPORTANT: Always identify a single tool only."
                "IMPORTANT: When you need to use a tool, you must ONLY respond with "                
                "the exact JSON object format below, DO NOT ADD any other comment.:\n"
                "Keep the values in str "
                "{\n"
                '    "tool": "tool-name",\n'
                '    "arguments": {\n'
                '        "argument-name": "value"\n'
                "    }\n"
                "}\n\n"
                )
    
def get_prompt_to_process_tool_response(query:str, tool_response:str, context:list):
    response_format = {"action":"", "response":""}
    return (
        "You are a helpful assistant."
        " Your job is to decide whether to respond directly to the user or continue processing using additional tools, based on:"
        "\n- The user's query"
        "\n- The tool's response"
        "\n- The conversation context."
        "\nSometimes, multiple tools may be needed to fully address the user's request."
        "\nCarefully analyze the query, tool response, and context together."
        "\nIf no further processing is needed, respond directly to the user and set the action to 'respond_to_user' with your response.\
            Ensure the response addresses the user's original query. Example if the query had 2 tasks- the response to the user should address both tasks"
        "\nIf more processing is needed (for example, if a query has multiple tasks but only one has been handled), clearly state what’s pending and leave the action blank."
        "\nAlways follow this response format:"
        f"\n{response_format}"
        "\n\nInputs:"
        f"\nUser's query: {query}"
        f"\nTool response: {tool_response}"
        f"\nCONTEXT: {context}"
        )



async def sse_ops(query:str, memory:list):
    sse_url = "http://localhost:8100/sse"

    # 1) Open SSE → yields (in_stream, out_stream)
    async with sse_client(url=sse_url) as (in_stream, out_stream):
        # 2) Create an MCP session over those streams
        async with ClientSession(in_stream, out_stream) as session:
            # 3) Initialize
            info = await session.initialize()
            logger.info(f"Connected to {info.serverInfo.name} v{info.serverInfo.version}")

            # 4) List tools
            tools = (await session.list_tools())
            print(tools)
            #print("Available tools:", [t.name for t in tools])
            
            prompt = get_prompt_to_identify_tool_and_arguments(query=query,tools=tools,context=memory)
            logger.info(f"Printing tool identification prompt\n {prompt}")
            
            response = llm_client(prompt)
            logger.info(f"Response from LLM {response}")
            
            tool_call = json.loads(response)
            result = await session.call_tool(tool_call["tool"], arguments=tool_call["arguments"])
            
            tool_response = result.content[0].text
            
            response_prompt = get_prompt_to_process_tool_response(query=query,tool_response=tool_response,context=memory)
            logger.info(f"Printing tool process response prompt\n {response_prompt}")
            final_response = llm_client(response_prompt)
            
            ##Convert string respons to dict
            python_dict = ast.literal_eval(final_response)
            json_string = json.dumps(python_dict)
            json_dict = json.loads(json_string)
            if not isinstance(json_dict,Dict): raise ValueError("response not a valid dictionary")
            return json_dict

          
            
            
async def main():
      memory = []   
        
      ##Use this as the query to the agent = "Calculate BMI for height 5ft 10inches and weight 80kg"
      print("Chat Agent: Hello! How can I assist you today?")
      user_input = input("You: ")

      while True:
        if user_input.lower() in ["exit", "bye", "close"]:
          print("See you later!")
          break

        response = await sse_ops(user_input, memory)
        memory.append(response)
        if isinstance(response, dict) and response["action"] == "respond_to_user":
          print("Reponse from Agent: ", response["response"])
          user_input = input("You: ")
          memory.append(user_input)
        else:
          user_input = response["response"]
          
        
if __name__ == "__main__":    
    asyncio.run(main())
