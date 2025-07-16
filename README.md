# 🧠 OpenAI MCP BMI Tool – Client & Server Demo

Project is forked from zahere-dev/mcp-labs

This project demonstrates how to build a simple MCP (Model Context Protocol) client and server using `ollama` with `llama3.2` model Python SDK and the `mcp` package. We expose a BMI calculator tool via the server and use an LLM-powered client to discover and invoke the tool based on natural language queries.

---

## 📽️ Demo Video  
Watch the full original tutorial (does not contain the changes related to Ollama and streamable HTTP): **[How to Build an OpenAI MCP Client and Server](#)**  
_(https://www.youtube.com/watch?v=hMHYhRcd_Uo)_

---

## 🚀 Features

- ✅ Lightweight MCP Server using `FastMCP`
- ✅ BMI calculation exposed as a tool
- ✅ [Not used anymore] OpenAI GPT-4o model used to intelligently select tools and arguments
- ✅ Ollama with llama3.2 model used to intelligently select tools and arguments
- ✅ STDIO-based client-server communication
- ✅ streamable-http based client-server communication
- ✅ JSON-based tool calling flow using natural language

