# perplexity-claude-agent

> The 21st agent for Perplexity Computer — your local Claude Code with full filesystem access

## What is this?

Perplexity Computer orchestrates 19 AI models in a cloud sandbox, but it can't touch your local machine. This package exposes your local Claude Code instance as an MCP connector that Perplexity Computer can call, giving it a **21st agent** with access to your local filesystem, git repos, test suites, and development environment.

It ships with a custom Perplexity skill template that teaches the orchestrator when and how to use your local Claude Code.

## Architecture

```
┌─────────────────────┐
│  Perplexity Computer │
│   (19 AI models)     │
└──────────┬──────────┘
           │ HTTPS
           ▼
┌─────────────────────┐
│  ngrok/cloudflared  │
│     (tunnel)        │
└──────────┬──────────┘
           │ HTTP
           ▼
┌─────────────────────┐
│    MCP Server       │
│  (FastMCP HTTP)     │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Claude Agent SDK   │
│ (ClaudeSDKClient)   │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Local Filesystem   │
│  Git, Tests, Dev    │
└─────────────────────┘
```

## Features

- **SDK-based** — Uses Claude Agent SDK (`ClaudeSDKClient`), not CLI hacking
- **Persistent sessions** — Full conversation context preserved across calls
- **Project profiles** — Multi-project support with per-project configuration
- **Granular permissions** — Control what tools and operations are allowed
- **Custom Perplexity skill** — Template that teaches Perplexity Computer when to use your agent
- **Streamable HTTP transport** — MCP over HTTP for reliable tunnel connectivity

## Requirements

- Python 3.10+
- Claude Code CLI installed and authenticated
- ngrok or cloudflared for tunnel (optional for local testing)

## Quick Start

```bash
# Install
pip install perplexity-claude-agent

# Setup (interactive wizard)
perplexity-claude-agent setup

# Add a project
perplexity-claude-agent add-project ~/Projects/my-app

# Start the server
perplexity-claude-agent start
```

*Full documentation coming soon.*

## How It Works

1. **MCP Server** — FastMCP exposes tools via Streamable HTTP transport
2. **Session Manager** — `ClaudeSDKClient` maintains persistent Claude Code sessions
3. **Project Registry** — Maps project names to local directories
4. **Permission Hooks** — Control what operations are allowed per-project
5. **Tunnel** — ngrok/cloudflared exposes local server to Perplexity Computer

When Perplexity Computer calls your agent:
1. Request arrives via tunnel → MCP server
2. Server looks up or creates a Claude Code session for the project
3. Request is forwarded to Claude Code via SDK
4. Response streams back through the tunnel

## Custom Skill

A Perplexity Computer skill template is included that teaches the orchestrator:
- When to delegate to your local Claude Code (filesystem ops, git, tests)
- How to format requests for best results
- What capabilities are available

## Contributing

Contributions welcome! Please read the contributing guidelines first.

## License

MIT License — see [LICENSE](LICENSE) for details.
