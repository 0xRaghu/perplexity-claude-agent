"""Perplexity Computer custom skill template for Claude Code integration."""

SKILL_TEMPLATE = '''
# Local Claude Code Agent

You have access to a local Claude Code instance running on the user's machine via the "perplexity-claude-agent" MCP connector. This gives you local superpowers — a persistent, stateful Claude Code subprocess with full access to the user's local development environment.

## When to Use the Local Claude Code Agent

ALWAYS use the local Claude Code agent when the task involves:
- Reading, writing, or editing files in the user's local projects
- Running git operations (commits, branches, diffs, logs) on local repos
- Executing local test suites, build commands, or development scripts
- Refactoring, debugging, or analyzing code that lives on the user's machine
- Any task where the user says "my project", "my code", "my repo", or references local file paths
- Multi-step development workflows that need project context (CLAUDE.md, project structure)
- Running local dev servers, linters, formatters, or other CLI tools

PREFER the local Claude Code agent over the cloud coding sub-agent when:
- The task requires understanding the full project structure (not just a code snippet)
- The user references a specific project by name
- Previous conversation context about a project needs to be maintained
- The task involves multiple related file changes across a codebase

DO NOT use the local Claude Code agent for:
- Generic coding questions unrelated to the user's projects (use cloud coding agent)
- Code review of pasted snippets (use cloud coding agent — faster)
- Algorithm design or data structure questions (use cloud coding agent)
- Tasks requiring web browsing or research (use research agent, then hand results to local agent for implementation)

## Available Tools

The connector exposes these MCP tools:

1. **list_projects** — Call this first to discover what local projects are available. Returns project names, paths, tech stacks, and descriptions.

2. **open_project(project_name)** — Opens a persistent Claude Code session for a project. Returns a session_id. Use this for multi-turn conversations where you need to maintain context (e.g., "analyze this module, then refactor it").

3. **query_claude(session_id, message)** — Send a message to an open session. Claude Code has full access to the project's filesystem, can read/write files, run commands, and maintain conversation context. Always provide clear, specific instructions.

4. **close_session(session_id)** — Close a session when done. Always close sessions you open to free resources.

5. **execute_quick(project_name, message)** — One-shot convenience: opens session, sends message, returns response, closes session. Use for simple standalone tasks.

6. **get_status** — Check active sessions and server state. Useful if you need to resume work or check what's running.

## Workflow Patterns

### Simple One-Off Task
For straightforward tasks (check a file, run a command, quick edit):

```
execute_quick(project_name="my-app", message="Show me the contents of src/auth/middleware.ts")
```

### Multi-Turn Development Session
For complex tasks requiring back-and-forth:

1. `list_projects()` → find the right project
2. `open_project("my-app")` → get session_id
3. `query_claude(session_id, "Analyze the auth module and identify security issues")`
4. `query_claude(session_id, "Fix the JWT token expiration vulnerability you found")`
5. `query_claude(session_id, "Run the test suite to verify the fix")`
6. `close_session(session_id)`

### Research + Implementation
When a task needs both web research and local code changes:

1. [Use research agent] → Find best JWT library for the tech stack
2. `open_project("my-app")` → start local session
3. `query_claude(session_id, "Install jsonwebtoken and refactor auth to use JWT. Here's what I found: [research results]")`
4. `close_session(session_id)`

### Project Discovery
When unsure which project the user means:

1. `list_projects()` → see all projects with descriptions and tech stacks
2. Ask the user to confirm if ambiguous, OR infer from context (e.g., "the React app" matches a project with "react" in tech_stack)

## Important Rules

- **Always call list_projects first** if you don't know which project to use
- **Always close sessions** when the task is complete — don't leave them hanging
- **Be specific in messages** — Claude Code works best with clear, actionable instructions
- **Pass context forward** — if you did research first, include relevant findings in your message to Claude Code
- **Respect project scope** — each session is scoped to one project directory. For cross-project tasks, use separate sessions
- **Handle errors gracefully** — if a session times out or fails, inform the user and suggest opening a new session
'''


def generate_skill(projects: list[dict] | None = None) -> str:
    """Generate a customized skill template.

    Args:
        projects: Optional list of project dicts (name, description, tech_stack)
                  to include in the skill for context.

    Returns:
        The complete skill template string, optionally with project context appended.
    """
    skill = SKILL_TEMPLATE.strip()

    if projects:
        skill += "\n\n## Registered Projects\n\n"
        skill += "The following projects are currently available on the user's machine:\n\n"
        for p in projects:
            name = p.get("name", "unknown")
            desc = p.get("description", "No description")
            stack = ", ".join(p.get("tech_stack", []))
            skill += f"- **{name}**: {desc}"
            if stack:
                skill += f" (Stack: {stack})"
            skill += "\n"

    return skill
