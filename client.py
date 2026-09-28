import json
import requests
import argparse
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn


# ============================================================
# CONFIGURATION
# ============================================================

OLLAMA_URL = "http://localhost:11434/api/chat"
MCP_URL = "http://localhost:9191/mcp"

OLLAMA_MODEL = "llama3.2"

HOST = "0.0.0.0"
PORT = 8080


# ============================================================
# MCP CLIENT
# ============================================================

class MCPClient:

    def __init__(self):

        self.session_id = None
        self.request_id = 0

    # --------------------------------------------------------
    # Generate JSON-RPC request ID
    # --------------------------------------------------------

    def next_request_id(self):

        self.request_id += 1

        return self.request_id

    # --------------------------------------------------------
    # Common MCP headers
    # --------------------------------------------------------

    def mcp_headers(self):

        return {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "Mcp-Session-Id": self.session_id
        }

    # --------------------------------------------------------
    # Initialize MCP session
    # --------------------------------------------------------

    def initialize(self):

        request_id = self.next_request_id()

        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {
                    "name": "python-mcp-client",
                    "version": "1.0.0"
                }
            }
        }

        response = requests.post(
            MCP_URL,
            headers={
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=30
        )

        response.raise_for_status()

        self.session_id = response.headers.get(
            "mcp-session-id"
        )

        if not self.session_id:

            raise Exception(
                "MCP server did not return mcp-session-id"
            )

        print(
            f"MCP session created: {self.session_id}"
        )

        # ----------------------------------------------------
        # Tell MCP server initialization is complete
        # ----------------------------------------------------

        notification = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        }

        response = requests.post(
            MCP_URL,
            headers=self.mcp_headers(),
            json=notification,
            timeout=30
        )

        response.raise_for_status()

        print("MCP initialization completed.")

    # --------------------------------------------------------
    # Parse MCP Streamable HTTP response
    # --------------------------------------------------------

    def parse_response(self, response):

        response.raise_for_status()

        text = response.text

        # MCP Streamable HTTP response normally looks like:
        #
        # event: message
        # data: {...JSON...}

        for line in text.splitlines():

            line = line.strip()

            if line.startswith("data:"):

                data = line[len("data:"):].strip()

                if not data:
                    continue

                return json.loads(data)

        raise Exception(
            "Could not find JSON-RPC data in MCP response:\n"
            + text
        )

    # --------------------------------------------------------
    # Discover tools
    # --------------------------------------------------------

    def list_tools(self):

        request_id = self.next_request_id()

        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/list"
        }

        response = requests.post(
            MCP_URL,
            headers=self.mcp_headers(),
            json=payload,
            timeout=30
        )

        result = self.parse_response(response)

        if "error" in result:

            raise Exception(
                f"MCP tools/list error: {result['error']}"
            )

        return result["result"]["tools"]

    # --------------------------------------------------------
    # Execute MCP tool
    # --------------------------------------------------------

    def call_tool(self, tool_name, arguments):

        request_id = self.next_request_id()

        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }

        print(
            f"\nMCP CALL: {tool_name}({arguments})"
        )

        response = requests.post(
            MCP_URL,
            headers=self.mcp_headers(),
            json=payload,
            timeout=30
        )

        result = self.parse_response(response)

        if "error" in result:

            raise Exception(
                f"MCP tools/call error: {result['error']}"
            )

        return result["result"]


# ============================================================
# MCP TOOL → OLLAMA TOOL
# ============================================================

def convert_tools(mcp_tools):

    ollama_tools = []

    for tool in mcp_tools:

        ollama_tools.append(
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get(
                        "description",
                        ""
                    ),
                    "parameters": tool["inputSchema"]
                }
            }
        )

    return ollama_tools


# ============================================================
# OLLAMA CLIENT
# ============================================================

class OllamaClient:

    def chat(self, messages, tools):

        payload = {
            "model": OLLAMA_MODEL,

            "messages": messages,

            "tools": tools,

            # IMPORTANT:
            # Return one JSON response instead of
            # multiple streaming JSON objects.
            "stream": False
        }

        response = requests.post(
            OLLAMA_URL,
            headers={
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=120
        )

        response.raise_for_status()

        return response.json()


# ============================================================
# MCP RESULT → TEXT
# ============================================================

def extract_tool_result(tool_result):

    content = tool_result.get(
        "content",
        []
    )

    result_text = ""

    for item in content:

        if item.get("type") == "text":

            if result_text:

                result_text += "\n"

            result_text += item.get(
                "text",
                ""
            )

    return result_text


# ============================================================
# ORCHESTRATOR
# ============================================================

class Orchestrator:

    def __init__(self):

        print("\n========================================")
        print("Starting MCP Orchestrator")
        print("========================================")

        # ----------------------------------------------------
        # MCP
        # ----------------------------------------------------

        self.mcp = MCPClient()

        self.mcp.initialize()

        # ----------------------------------------------------
        # Discover tools once
        # ----------------------------------------------------

        print("\nDiscovering MCP tools...")

        self.mcp_tools = self.mcp.list_tools()

        print("\nAvailable MCP tools:")

        for tool in self.mcp_tools:

            print(
                f"  - {tool['name']}"
            )

        # ----------------------------------------------------
        # Convert MCP tools to Ollama tools
        # ----------------------------------------------------

        self.ollama_tools = convert_tools(
            self.mcp_tools
        )

        # ----------------------------------------------------
        # Ollama
        # ----------------------------------------------------

        self.ollama = OllamaClient()

        print("\nOrchestrator ready.")

    # --------------------------------------------------------
    # Process one user question
    # --------------------------------------------------------

    def chat(self, user_question):

        print("\n========================================")
        print("USER QUESTION")
        print("========================================")

        print(user_question)

        # ----------------------------------------------------
        # Conversation for THIS request
        # ----------------------------------------------------

        messages = [
            {
                "role": "user",
                "content": user_question
            }
        ]

        # ----------------------------------------------------
        # Tool-call loop
        #
        # LLM can:
        #
        # 1. answer directly
        #
        # OR
        #
        # 2. request one or more tools
        #
        # After tool execution we send the result
        # back to LLM.
        # ----------------------------------------------------

        max_rounds = 5

        for round_number in range(max_rounds):

            print(
                f"\nLLM round: {round_number + 1}"
            )

            response = self.ollama.chat(
                messages,
                self.ollama_tools
            )

            assistant_message = response["message"]

            print("\nLLM response:")

            print(
                json.dumps(
                    assistant_message,
                    indent=2
                )
            )

            # ------------------------------------------------
            # Check if LLM wants to call tools
            # ------------------------------------------------

            tool_calls = assistant_message.get(
                "tool_calls",
                []
            )

            # ------------------------------------------------
            # No tool required
            #
            # LLM has final answer.
            # ------------------------------------------------

            if not tool_calls:

                return assistant_message.get(
                    "content",
                    ""
                )

            # ------------------------------------------------
            # Add assistant's tool-call message
            # ------------------------------------------------

            messages.append(
                assistant_message
            )

            # ------------------------------------------------
            # Execute requested tools
            # ------------------------------------------------

            for tool_call in tool_calls:

                function = tool_call["function"]

                tool_name = function["name"]

                arguments = function.get(
                    "arguments",
                    {}
                )

                print("\n========================================")
                print("LLM REQUESTED TOOL")
                print("========================================")

                print(
                    f"Tool: {tool_name}"
                )

                print(
                    f"Arguments: {arguments}"
                )

                # --------------------------------------------
                # MCP tools/call
                # --------------------------------------------

                tool_result = self.mcp.call_tool(
                    tool_name,
                    arguments
                )

                print("\nMCP RESULT:")

                print(
                    json.dumps(
                        tool_result,
                        indent=2
                    )
                )

                # --------------------------------------------
                # Convert MCP result to text
                # --------------------------------------------

                result_text = extract_tool_result(
                    tool_result
                )

                # --------------------------------------------
                # Give result back to LLM
                # --------------------------------------------

                messages.append(
                    {
                        "role": "tool",
                        "content": result_text
                    }
                )

        raise Exception(
            "Maximum LLM/tool rounds exceeded."
        )


# ============================================================
# GLOBAL ORCHESTRATOR
# ============================================================

orchestrator = None


# ============================================================
# REST API
# ============================================================

app = FastAPI(
    title="MCP LLM Orchestrator",
    version="1.0.0"
)


class ChatRequest(BaseModel):

    message: str


class ChatResponse(BaseModel):

    answer: str


@app.post(
    "/chat",
    response_model=ChatResponse
)
def chat(request: ChatRequest):

    answer = orchestrator.chat(
        request.message
    )

    return ChatResponse(
        answer=answer
    )


@app.get("/health")
def health():

    return {
        "status": "UP"
    }


# ============================================================
# CLI MODE
# ============================================================

def run_cli():

    print("\n========================================")
    print("MCP CLI")
    print("========================================")

    print(
        "Type your question."
    )

    print(
        "Type 'exit' to quit."
    )

    while True:

        try:

            question = input(
                "\nYou: "
            )

        except KeyboardInterrupt:

            print("\nExiting.")

            break

        question = question.strip()

        if not question:

            continue

        if question.lower() == "exit":

            print("Exiting.")

            break

        try:

            answer = orchestrator.chat(
                question
            )

            print(
                f"\nAI: {answer}"
            )

        except Exception as e:

            print(
                f"\nERROR: {e}"
            )


# ============================================================
# API MODE
# ============================================================

def run_api():

    print("\n========================================")
    print("Starting REST API")
    print("========================================")

    print(
        f"API available at:"
        f" http://localhost:{PORT}"
    )

    print(
        f"POST http://localhost:{PORT}/chat"
    )

    uvicorn.run(
        app,
        host=HOST,
        port=PORT
    )


# ============================================================
# MAIN
# ============================================================

def main():

    global orchestrator

    # --------------------------------------------------------
    # Create orchestrator ONCE
    # --------------------------------------------------------

    orchestrator = Orchestrator()

    # --------------------------------------------------------
    # Select mode
    # --------------------------------------------------------

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--mode",
        choices=[
            "cli",
            "api"
        ],
        default="cli"
    )

    args = parser.parse_args()

    # --------------------------------------------------------
    # CLI
    # --------------------------------------------------------

    if args.mode == "cli":

        run_cli()

    # --------------------------------------------------------
    # REST API
    # --------------------------------------------------------

    elif args.mode == "api":

        run_api()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()