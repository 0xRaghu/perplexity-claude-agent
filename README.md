# perplexity-claude-agent

> Give Perplexity Computer local superpowers — your local Claude Code with full filesystem access

## What is this?

Perplexity Computer orchestrates AI models in a cloud sandbox, but it can't touch your local machine. This package exposes your local Claude Code instance as an MCP connector that Perplexity Computer can call, giving it **local superpowers** — access to your local filesystem, git repos, test suites, and development environment.

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

## Security

This server exposes Claude Code to the network. **Always configure authentication when using a public tunnel.**

### Bearer Token Authentication

Set the `PERPLEXITY_AGENT_TOKEN` environment variable before starting:

```bash
export PERPLEXITY_AGENT_TOKEN="your-secret-token-here"
perplexity-claude-agent start
```

Or use the `--token` flag:

```bash
perplexity-claude-agent start --token "your-secret-token-here"
```

When configured, all requests must include `Authorization: Bearer <token>` header.

### Permission Presets

Control what Claude Code can do with `--permission`:

| Preset | Description |
|--------|-------------|
| `safe` | Auto-accept file edits, prompt for commands (default, recommended for tunnels) |
| `default` | Claude asks before all destructive operations |
| `plan` | Plan-only mode — proposes changes but doesn't execute |
| `full` | Skip all permission prompts (use with caution over tunnels) |

### Session Auto-Cleanup

Idle sessions are automatically closed after 10 minutes to prevent zombie processes from accumulating. This protects against resource exhaustion from abandoned sessions.

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

The magic of this package is the **custom skill template** — a prompt that teaches Perplexity Computer's orchestrator when and how to use your local Claude Code agent.

### Why You Need the Skill

Without the skill, Perplexity Computer doesn't know:
- That it has access to your local machine
- When to use your local Claude Code vs the cloud coding agent
- How to properly manage sessions and projects

With the skill, Perplexity Computer becomes a true development partner that can:
- Read and modify files in your actual projects
- Run your test suites, builds, and linters
- Maintain conversation context across complex multi-step tasks
- Work with your real git repos, not sandboxed copies

### Generate Your Skill

```bash
# Print to terminal
perplexity-claude-agent show-skill

# Copy to clipboard (macOS)
perplexity-claude-agent show-skill --copy

# Save to file
perplexity-claude-agent show-skill --save my-skill.md
```

The generated skill includes your registered projects for better context.

### Or Copy from GitHub

You can also copy the base skill template directly from:
[skills/perplexity_computer_skill.md](skills/perplexity_computer_skill.md)

### Where to Paste

1. Open Perplexity Computer
2. Go to Settings → Custom Skills (or similar)
3. Create a new skill
4. Paste the entire template
5. Save

Now when you ask Perplexity Computer to work on "your project" or "your code", it will automatically delegate to your local Claude Code agent.

## Contributing

Contributions welcome! Please read the contributing guidelines first.

## License

MIT License — see [LICENSE](LICENSE) for details.
