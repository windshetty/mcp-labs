import ast
import asyncio
import json
import os
from typing import Dict, Optional, Union
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from mcp import ClientSession, StdioServerParameters, stdio_client
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



def get_prompt_to_identify_tool_and_arguments(query:str, tool_list:list, context=list):
    tools_description = "\n".join([f"{tool.name}: {tool.description}, {tool.inputSchema}" for tool in tool_list])
    # for tools in tool_list:    
    #     tools_description = tools_description + "\n".join([f"{tool.name}: {tool.description}, {tool.inputSchema}" for tool in tools.tool])
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



class ToolMap(BaseModel):
    server_type: str
    tool: Dict
    params: Union[str, StdioServerParameters]


class ToolList:
    def __init__(self):
        self.tools = []
        self.tool_context = {}        
        
    async def sse_get_tools(self, sse_url:str):
        try:
            logger.info("Starting  ops")            

            # 1) Open SSE → yields (in_stream, out_stream)
            async with sse_client(url=sse_url) as (in_stream, out_stream):
                # 2) Create an MCP session over those streams
                async with ClientSession(in_stream, out_stream) as session:
                # 3) Initialize
                    info = await session.initialize()
                    logger.info(f"Connected to {info.serverInfo.name} v{info.serverInfo.version}")
                    # 4) List tools
                    tools = await session.list_tools()
                    return {info.serverInfo.name: tools.tools}
        except Exception as e:
            # Handle the exception, e.g., log the error and return an error message
            logger.error(f"Error getting tool context: {str(e)}")
            return None

    async def stdio_get_tools(self, server_params):
        try:
            logger.info("Starting stdio ops")
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as stdio_ops_session:
                    info = await stdio_ops_session.initialize()
                    logger.info(f"Connected to {info.serverInfo.name} v{info.serverInfo.version}")
                    # Get the list of available tools
                    tools = await stdio_ops_session.list_tools()
                    return {info.serverInfo.name: tools.tools}
        except Exception as e:
            # Handle the exception, e.g., log the error and return an error message
            logger.error(f"Error getting tool context: {str(e)}")
            return None       
    
    async def get_tool_context(self):
        try:
            stdio_server_params = mcp_server_config._get_server_params_list()
            sse_urls = mcp_server_config._get_sse_urls()
            
            tool_context = []
            
            for server_params in stdio_server_params:                
                stdio_tools = await self.stdio_get_tools(server_params=server_params)
                tool_map = ToolMap(server_type="stdio", tool=stdio_tools, params=server_params)
                tool_context.append(tool_map)
                               
            
            for sse_url in sse_urls:
                sse_tools = await self.sse_get_tools(sse_url=sse_url)
                # tools = tool_context["sse"]
                # tools.extend(sse_tools.tools)                
                #tool_context["sse"]=sse_tools
                tool_map = ToolMap(server_type="sse", tool=sse_tools, params=sse_url)
                tool_context.append(tool_map)
            
            print(tool_context)
            
            return tool_context
        except Exception as e:
            # Handle the exception, e.g., log the error and return an error message
            logger.error(f"Error getting tool context: {str(e)}")
            return None
class ExecuteTool:
    
    def __init__(self):
        pass
    
    def process_tool_response(self, tool_response:str, query:str, memory:list):        
        response_prompt = get_prompt_to_process_tool_response(query=query,tool_response=tool_response,context=memory)
        logger.info(f"Printing tool process response prompt\n {response_prompt}")
        final_response = llm_client(response_prompt)        
        ##Convert string respons to dict
        python_dict = ast.literal_eval(final_response)
        json_string = json.dumps(python_dict)
        json_dict = json.loads(json_string)
        if not isinstance(json_dict,Dict): raise ValueError("response not a valid dictionary")
        logger.info(f"Process Tool Response: {json_dict}")
        return json_dict
                
    async def stdio_call_tool(self, query:str, memory:list, tool_call: dict, server_params):
        try:
            logger.info("Starting stdio ops")
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as stdio_ops_session:
                    info = await stdio_ops_session.initialize()
                    logger.info(f"Connected to {info.serverInfo.name} v{info.serverInfo.version}")
                    
                    result = await stdio_ops_session.call_tool(tool_call["tool"], arguments=tool_call["arguments"])
                    print(result)
                    tool_response = result.content[0].text
                    return self.process_tool_response(tool_response=tool_response, query=query, memory=memory)               
                    
        except Exception as e:
            # Handle the exception, e.g., log the error and return an error message
            logger.error(f"Error getting tool context: {str(e)}")
            return None
    
    async def sse_call_tool(self, query:str, memory:list, tool_call: dict, sse_url):
        try:
            logger.info("Starting  ops")
            #sse_url = "http://localhost:8100/sse"

            # 1) Open SSE → yields (in_stream, out_stream)
            async with sse_client(url=sse_url) as (in_stream, out_stream):
                # 2) Create an MCP session over those streams
                async with ClientSession(in_stream, out_stream) as session:
                # 3) Initialize
                    info = await session.initialize()
                    logger.info(f"Connected to {info.serverInfo.name} v{info.serverInfo.version}")                                    
                    
                    result = await session.call_tool(tool_call["tool"], arguments=tool_call["arguments"])
                    print(result)
                    tool_response = result.content[0].text
                    return self.process_tool_response(tool_response=tool_response, query=query, memory=memory)
                
        except Exception as e:
            # Handle the exception, e.g., log the error and return an error message
            logger.error(f"Error getting tool context: {str(e)}")
            return None


class MCPServerConfig:
    def __init__(self):
        self.server_params_list = []
        self.sse_urls = []
        
    def _add_server_params(self, server_params:list[StdioServerParameters]):
        self.server_params_list.extend(server_params)
        
    def _add_sse_url(self, sse_urls:list[str]):
        self.sse_urls.extend(sse_urls)
    
    def _get_server_params_list(self):
        return self.server_params_list
    
    def _get_sse_urls(self):
        return self.sse_urls
    



async def chat_agent(query:str, memory:list,tool_context:list[ToolMap]):
    
    #we need this list to send to this to an LLM to tell it select a tool from this given the task
    tools = [tool for tool_map in tool_context for tool_list in tool_map.tool.values() for tool in tool_list]    
    logger.info(tools)    
    
    prompt = get_prompt_to_identify_tool_and_arguments(query=query,tool_list=tools,context=memory)
    logger.info(f"Printing tool identification prompt\n {prompt}")
    
    response = llm_client(prompt)
    logger.info(f"Response from LLM {response}")
    
    tool_call = json.loads(response)    
    
    tool_name = tool_call["tool"]    
    execute_tool_ops = ExecuteTool()
    
    for tool_map in tool_context:
        if tool_name in [tool.name for tool_list in tool_map.tool.values() for tool in tool_list]:
            if tool_map.server_type == "sse":
                result = await execute_tool_ops.sse_call_tool(query=query,memory=memory, tool_call=tool_call, sse_url=tool_map.params)
            elif tool_map.server_type == "stdio":
                result = await execute_tool_ops.stdio_call_tool(query=query,memory=memory, tool_call=tool_call, server_params=tool_map.params)
            break
    
    return result
            
        

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    #allow_origins=["*"],  # Or set specific allowed origins like ["http://localhost:8501"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_origins=["http://localhost:8501"],
)


class ConnectionManager:
    def __init__(self):
        self.active_connections: ast.List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            print(f"Active connection found: {connection}")
            await connection.send_text(message)

manager = ConnectionManager()
@app.websocket("/chat")
async def chat_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        memory = []
        tool_ops = ToolList()
        tool_context = await tool_ops.get_tool_context()
        user_input = None
        while True:            
            if not user_input:
                user_input = await websocket.receive_text()
            
            if user_input.lower() in ["exit", "bye", "close"]:
                await manager.broadcast("Agent: See you later!")
                break

            response = await chat_agent(user_input, memory, tool_context)
            user_input = None
            memory.append(response["response"])
            
            if isinstance(response, dict) and response.get("action") == "respond_to_user":
                message = response["response"]
                logger.info("Response from Agent: " + message)                
                await manager.broadcast(f"Agent: {str(message)}")
            else:
                user_input = response["response"]
    except WebSocketDisconnect:
        manager.disconnect(websocket)
            

if __name__ == "__main__":
    
    sse_urls = ["http://localhost:8100/sse"]
    stdio_server_params = [StdioServerParameters(
                        command="python",
                        ##Change the path as per your settings
                        args=["C:\\Users\\Zahiruddin_T\\Documents\\LocalDriveProjects\\MCP\\mcp-labs\\mcp_client_server_stdio\\bmi_server.py"])
                           ]
    mcp_server_config = MCPServerConfig()
    mcp_server_config._add_server_params(server_params=stdio_server_params)
    mcp_server_config._add_sse_url(sse_urls=sse_urls)    
    
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8200)
