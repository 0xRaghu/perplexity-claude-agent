# perplexity-claude-agent

## Project Overview
This is a Python package that bridges local Claude Code to Perplexity Computer via MCP.
It uses the Claude Agent SDK (ClaudeSDKClient) for persistent sessions and FastMCP for Streamable HTTP transport.

## Tech Stack
- Python 3.10+
- Claude Agent SDK (claude-agent-sdk) for Claude Code subprocess management
- MCP Python SDK (mcp) with FastMCP for Streamable HTTP server
- Click for CLI
- Pydantic for data models

## Architecture
- `server.py` — FastMCP Streamable HTTP server exposing tools to Perplexity
- `session.py` — Session manager wrapping ClaudeSDKClient for persistent conversations
- `registry.py` — Project registry for managing local project directories
- `cli.py` — CLI entry points (start, setup, add-project, etc.)
- `permissions.py` — Permission hooks for controlling Claude Code's tool access

## Key Patterns
- Use `ClaudeSDKClient` (not `query()`) for session continuity
- Use FastMCP with `stateless_http=False` for stateful sessions
- Use `mcp.run(transport="streamable-http")` for HTTP transport
- Project registry stored at ~/.perplexity-claude-agent/config.json
- All MCP tools should be async

## Commands
```bash
# Install dependencies
pip install -e .

# Run server
perplexity-claude-agent start

# Add project
perplexity-claude-agent add-project <path>
```

## File Structure
```
src/perplexity_claude_agent/
├── __init__.py      # Package init, version
├── server.py        # FastMCP HTTP server
├── session.py       # ClaudeSDKClient session manager
├── registry.py      # Project directory registry
├── cli.py           # Click CLI commands
└── permissions.py   # Tool permission hooks
```
