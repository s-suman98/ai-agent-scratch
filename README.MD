# MCP Client + Ollama Orchestrator

A Python-based MCP client and LLM orchestrator that connects:

* **Ollama** running Llama 3.2
* **MCP Server** exposing weather tools
* **Python MCP Client / Orchestrator**
* **CLI or REST API** as the user-facing interface

The Python application acts as the bridge between the LLM and MCP servers.

---

## 1. Architecture

```text
                         User
                          |
             +------------+------------+
             |                         |
             v                         v
          CLI Mode                 REST API Mode
        Terminal Input             POST /chat
             |                         |
             +------------+------------+
                          |
                          v
              +-----------------------+
              | Python Orchestrator   |
              |                       |
              |    MCP Client         |
              +-----------+-----------+
                          |
             +------------+------------+
             |                         |
             v                         v
      Ollama :11434              MCP Server :9191
      Llama 3.2                  India Weather
                                 
                                 Tools:
                                 - get_weather
                                 - get_wind_speed
```

---

# 2. Components

## Ollama

Ollama runs the local LLM.

```text
http://localhost:11434
```

Model:

```text
llama3.2
```

Ollama is responsible for:

* Understanding the user question
* Deciding whether a tool is required
* Selecting the appropriate tool
* Generating the final natural-language answer

Ollama does **not** directly execute MCP tools.

---

## MCP Server

The MCP server exposes tools using the MCP protocol.

```text
http://localhost:9191/mcp
```

Current tools:

```text
get_weather(state)
get_wind_speed(state)
```

The MCP server is responsible for:

* Exposing tools
* Providing tool definitions
* Executing tools
* Returning tool results

---

## Python MCP Client / Orchestrator

The Python application is the bridge between Ollama and the MCP server.

It is responsible for:

```text
1. Connect to MCP server
2. Initialize MCP session
3. Discover tools
4. Convert MCP tools to Ollama tool format
5. Send user question + tools to Ollama
6. Receive LLM tool call
7. Execute the tool through MCP
8. Send tool result back to Ollama
9. Return final answer
```

---

# 3. End-to-End Flow

Suppose the user asks:

```text
What is the weather in Telangana?
```

The complete flow is:

```text
User
 |
 | "What is the weather in Telangana?"
 v
Python Orchestrator
 |
 | question + tool definitions
 v
Ollama / Llama 3.2
 |
 | tool_call:
 | get_weather(state="Telangana")
 v
Python Orchestrator
 |
 | MCP tools/call
 v
MCP Server
 |
 | execute get_weather()
 v
"Weather in Telangana: 29°C, Partly Cloudy"
 |
 v
Python Orchestrator
 |
 | tool result
 v
Ollama
 |
 | final natural-language answer
 v
Python Orchestrator
 |
 v
User
```

---

# 4. MCP Initialization

When the Python application starts, it creates an MCP session.

It sends:

```text
initialize
```

to:

```text
POST http://localhost:9191/mcp
```

The MCP server returns:

```text
mcp-session-id
```

The client stores this session ID and uses it for subsequent MCP requests.

Then the client sends:

```text
notifications/initialized
```

This completes the MCP initialization process.

---

# 5. Tool Discovery

After initialization, the client calls:

```text
tools/list
```

The MCP server returns:

```text
get_weather
get_wind_speed
```

with their descriptions and input schemas.

For example:

```json
{
  "name": "get_weather",
  "description": "Get the current weather for an Indian state.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "state": {
        "type": "string"
      }
    },
    "required": [
      "state"
    ]
  }
}
```

The Python client converts this MCP definition into Ollama's tool format.

---

# 6. Ollama Tool Calling

The Python orchestrator sends Ollama:

```text
User question
+
Available tools
```

For example:

```text
Question:

What is the weather in Telangana?

Tools:

get_weather
get_wind_speed
```

Llama 3.2 may respond with:

```json
{
  "tool_calls": [
    {
      "function": {
        "name": "get_weather",
        "arguments": {
          "state": "Telangana"
        }
      }
    }
  ]
}
```

Important:

**The LLM does not execute the tool.**

It only says:

```text
"I want get_weather(Telangana)"
```

---

# 7. MCP Tool Execution

The Python orchestrator receives the LLM's tool call.

It then sends:

```text
tools/call
```

to the MCP server.

Example:

```json
{
  "jsonrpc": "2.0",
  "id": 10,
  "method": "tools/call",
  "params": {
    "name": "get_weather",
    "arguments": {
      "state": "Telangana"
    }
  }
}
```

The MCP server executes:

```python
get_weather("Telangana")
```

and returns:

```text
Weather in Telangana: 29°C, Partly Cloudy
```

---

# 8. Sending Tool Result Back to Ollama

The orchestrator takes the MCP result and sends it back to Ollama.

Conceptually:

```text
User question
        +
LLM tool call
        +
Tool result
        |
        v
      Ollama
```

The LLM can now generate the final answer:

```text
The current weather in Telangana is 29°C,
with partly cloudy conditions.
```

---

# 9. CLI Mode

CLI mode allows continuous interaction through the terminal.

Start the application:

```bash
.venv/bin/python client.py --mode cli
```

You will see:

```text
MCP CLI

You: What is the weather in Telangana?
```

The application processes the request.

Then you can continue:

```text
You: What is the wind speed in Telangana?

You: What is the weather in Maharashtra?

You: What is the wind speed in Maharashtra?
```

The application keeps running until:

```text
You: exit
```

is entered.

### CLI Flow

```text
Terminal
   |
   | user question
   v
Python Orchestrator
   |
   +------> Ollama
   |
   +------> MCP Server
   |
   v
Final answer
   |
   v
Terminal
```

---

# 10. REST API Mode

The same orchestrator can also expose a REST API.

Start:

```bash
.venv/bin/python client.py --mode api
```

The API runs on:

```text
http://localhost:8080
```

Main endpoint:

```text
POST /chat
```

Full URL:

```text
http://localhost:8080/chat
```

---

## REST API Request

Using curl:

```bash
curl --request POST \
  --url http://localhost:8080/chat \
  --header 'Content-Type: application/json' \
  --data '{
    "message": "What is the weather in Telangana?"
  }'
```

Response:

```json
{
  "answer": "The current weather in Telangana is 29°C and partly cloudy."
}
```

---

# 11. Multiple API Requests

The Python orchestrator remains running.

Request 1:

```bash
curl --request POST \
  --url http://localhost:8080/chat \
  --header 'Content-Type: application/json' \
  --data '{
    "message": "What is the weather in Telangana?"
  }'
```

Request 2:

```bash
curl --request POST \
  --url http://localhost:8080/chat \
  --header 'Content-Type: application/json' \
  --data '{
    "message": "What is the wind speed in Telangana?"
  }'
```

Request 3:

```bash
curl --request POST \
  --url http://localhost:8080/chat \
  --header 'Content-Type: application/json' \
  --data '{
    "message": "What is the weather in Maharashtra?"
  }'
```

All three requests are handled by the same running Python application.

---

# 12. CLI vs REST API

The underlying orchestration is the same.

Only the user-facing interface changes.

```text
                    Python Orchestrator
                           |
              +------------+------------+
              |                         |
              v                         v
             CLI                       API
       terminal input              POST /chat
              |                         |
              +------------+------------+
                           |
                           v
                     Ollama + MCP
```

### CLI

```text
User
 ↓
Terminal
 ↓
Python Orchestrator
```

### REST API

```text
User / Postman / Java / React
 ↓
HTTP POST /chat
 ↓
Python Orchestrator
```

Both eventually use:

```text
Ollama
 +
MCP Server
```

---

# 13. Why Is the Orchestrator Long-Running?

The orchestrator is designed as a long-running application.

At startup:

```text
Python starts
     |
     +--> Initialize MCP
     |
     +--> Create MCP session
     |
     +--> Discover tools
     |
     +--> Become ready
```

Then it continuously accepts requests.

```text
                 Python Process
                       |
        +--------------+--------------+
        |              |              |
        v              v              v
     Request 1      Request 2      Request 3
        |              |              |
        v              v              v
     Ollama         Ollama         Ollama
        |              |              |
        v              v              v
     MCP Server     MCP Server     MCP Server
```

The process does not restart for every question.

---

# 14. What Is Cached / Reused?

The MCP session is created when the orchestrator starts.

The tools are also discovered during startup.

Conceptually:

```text
Application startup
       |
       +--> MCP initialize
       |
       +--> tools/list
       |
       +--> Store tool definitions
       |
       v
Ready for requests
```

For every user request, the application does not need to rediscover the tools.

Instead:

```text
Request
   |
   +--> Existing MCP session
   |
   +--> Existing tool definitions
   |
   +--> Ollama
   |
   +--> MCP tools/call if required
```

---

# 15. Important Responsibilities

## LLM / Ollama

Responsible for:

```text
Understand question
        ↓
Decide whether tool is needed
        ↓
Select tool
        ↓
Generate arguments
        ↓
Generate final answer
```

---

## MCP Client / Orchestrator

Responsible for:

```text
Connect to MCP
        ↓
Discover tools
        ↓
Give tools to LLM
        ↓
Receive tool call from LLM
        ↓
Execute tool through MCP
        ↓
Give result to LLM
```

---

## MCP Server

Responsible for:

```text
Expose tools
        ↓
Receive tools/call
        ↓
Execute actual function
        ↓
Return result
```

---

# 16. Simple Mental Model

Remember:

```text
LLM
"What should I do?"
        |
        v
MCP Client
"Okay, I'll execute it."
        |
        v
MCP Server
"Here is the actual tool."
        |
        v
MCP Client
"Here is the result."
        |
        v
LLM
"Here is the answer to the user."
```

The most important distinction is:

```text
LLM              → DECIDES
MCP CLIENT       → ORCHESTRATES
MCP SERVER       → EXECUTES
```

---

# 17. Project Structure

Recommended structure:

```text
mcp-client/
│
├── .venv/
│
├── client.py
│
└── README.md
```

The separate MCP server project:

```text
mcp-server/
│
├── .venv/
│
├── server.py
│
└── README.md
```

Run the MCP server first:

```bash
cd ~/mcp-server

.venv/bin/python server.py
```

Then run the orchestrator.

CLI:

```bash
cd ~/mcp-client

.venv/bin/python client.py --mode cli
```

Or API:

```bash
cd ~/mcp-client

.venv/bin/python client.py --mode api
```

---

# 18. Ports

| Component           |    Port | Purpose              |
| ------------------- | ------: | -------------------- |
| Ollama              | `11434` | LLM inference        |
| MCP Server          |  `9191` | MCP protocol         |
| Python Orchestrator |  `8080` | User-facing REST API |

Architecture:

```text
                 :8080
                    |
                    v
           Python Orchestrator
              /           \
             /             \
            v               v
      Ollama :11434     MCP :9191
```

---

# 19. Health Check

The orchestrator exposes:

```text
GET /health
```

Test:

```bash
curl http://localhost:8080/health
```

Response:

```json
{
  "status": "UP"
}
```

---

# 20. Summary

This project demonstrates an LLM application using MCP.

The complete flow is:

```text
                  USER
                    |
                    v
           +----------------+
           | CLI / REST API |
           +-------+--------+
                   |
                   v
           +---------------+
           | Python MCP    |
           | Orchestrator  |
           +-------+-------+
                   |
          +--------+--------+
          |                 |
          v                 v
    +-----------+     +-----------+
    |  Ollama   |     | MCP Server|
    | Llama 3.2 |     |   :9191   |
    |   :11434  |     |           |
    +-----------+     |  Tools    |
                      +-----------+
```

The key idea is:

> **The MCP client does not replace the LLM. The MCP client connects the LLM to external tools provided by MCP servers.**

Your Python application is therefore acting as the **MCP client + LLM orchestrator**, while Ollama is the **LLM inference engine** and your weather application is the **MCP server/tool provider**.