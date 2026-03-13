"""CLI entry points for perplexity-claude-agent.

Commands:
- start: Start the MCP server
- setup: Interactive setup wizard
- add-project: Register a local project
- remove-project: Remove a registered project
- list-projects: Show registered projects
- show-skill: Display the Perplexity Computer skill template
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import sys

import click

from . import __version__
from .permissions import PERMISSION_PRESETS
from .registry import ProjectRegistry


def get_registry() -> ProjectRegistry:
    """Get or create the project registry."""
    return ProjectRegistry()


def print_banner(host: str, port: int, permission: str, project_count: int) -> None:
    """Print the startup banner."""
    lines = [
        "┌─────────────────────────────────────────────────┐",
        "│  perplexity-claude-agent v{:<21} │".format(__version__),
        "│  The 21st agent for Perplexity Computer        │",
        "├─────────────────────────────────────────────────┤",
        "│  Server: http://{}:{:<23} │".format(host, port),
        "│  MCP Endpoint: http://{}:{}/mcp{} │".format(
            host, port, " " * (14 - len(str(port)))
        ),
        "│  Permission: {:<33} │".format(permission),
        "│  Projects: {} registered{} │".format(
            project_count, " " * (24 - len(str(project_count)))
        ),
        "└─────────────────────────────────────────────────┘",
    ]
    click.echo()
    for line in lines:
        click.echo(click.style(line, fg="cyan"))
    click.echo()


@click.group()
@click.version_option(version=__version__, prog_name="perplexity-claude-agent")
def main():
    """The 21st agent for Perplexity Computer — your local Claude Code with full filesystem access."""
    pass


@main.command()
@click.option("--host", default="0.0.0.0", help="Host to bind to")
@click.option("--port", default=8765, type=int, help="Port to listen on")
@click.option(
    "--permission",
    default="default",
    type=click.Choice(["default", "plan", "full"]),
    help="Permission preset for Claude Code",
)
def start(host: str, port: int, permission: str) -> None:
    """Start the MCP server for Perplexity Computer."""
    from .server import run_server

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )

    # Get registry and count projects
    registry = get_registry()
    project_count = len(registry.list_projects())

    # Print banner
    print_banner(host, port, permission, project_count)

    # Print instructions
    click.echo(
        click.style("To connect from Perplexity Computer:", fg="yellow")
    )
    click.echo("  1. Expose this server via tunnel (ngrok, cloudflared)")
    click.echo("  2. Add the HTTPS URL as a custom connector in Perplexity Computer")
    click.echo()
    click.echo(click.style("Press Ctrl+C to stop the server.", fg="bright_black"))
    click.echo()

    try:
        asyncio.run(
            run_server(
                host=host,
                port=port,
                registry=registry,
                permission_preset=permission,
            )
        )
    except KeyboardInterrupt:
        click.echo()
        click.echo(click.style("Server stopped.", fg="yellow"))


@main.command("add-project")
@click.argument(
    "path",
    type=click.Path(exists=True, file_okay=False, resolve_path=True),
)
@click.option("--name", "-n", default=None, help="Project name (defaults to directory name)")
@click.option("--description", "-d", default=None, help="Project description")
@click.option("--default", "set_default", is_flag=True, help="Set as default project")
def add_project(
    path: str,
    name: str | None,
    description: str | None,
    set_default: bool,
) -> None:
    """Register a local project directory."""
    registry = get_registry()

    try:
        project = registry.add_project(path, name=name, description=description)
    except ValueError as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        sys.exit(1)

    # Set as default if requested
    if set_default:
        registry.set_default(project.name)

    # Print success
    click.echo(click.style("Project registered!", fg="green"))
    click.echo()
    click.echo(f"  Name:        {click.style(project.name, fg='bright_white', bold=True)}")
    click.echo(f"  Path:        {project.path}")

    # Description
    if project.description:
        desc_source = "(auto-detected)" if description is None else ""
        click.echo(f"  Description: {project.description} {click.style(desc_source, fg='bright_black')}")

    # Tech stack
    if project.tech_stack:
        stack_str = ", ".join(project.tech_stack)
        click.echo(f"  Tech Stack:  {stack_str} {click.style('(auto-detected)', fg='bright_black')}")

    # Default marker
    if set_default:
        click.echo(f"  Default:     {click.style('Yes', fg='green')}")

    click.echo()
    total = len(registry.list_projects())
    click.echo(f"Total projects registered: {total}")


@main.command("remove-project")
@click.argument("name")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def remove_project(name: str, yes: bool) -> None:
    """Remove a registered project."""
    registry = get_registry()

    # Check if project exists
    project = registry.get_project(name)
    if project is None:
        click.echo(click.style(f"Error: Project '{name}' not found.", fg="red"), err=True)
        sys.exit(1)

    # Confirm unless --yes
    if not yes:
        if not click.confirm(f"Remove project '{name}' ({project.path})?"):
            click.echo("Cancelled.")
            return

    # Remove
    removed = registry.remove_project(name)
    if removed:
        click.echo(click.style(f"Project '{name}' removed.", fg="green"))
    else:
        click.echo(click.style(f"Failed to remove project '{name}'.", fg="red"), err=True)
        sys.exit(1)


@main.command("list-projects")
def list_projects() -> None:
    """List all registered projects."""
    registry = get_registry()
    projects = registry.list_projects()
    default = registry.get_default()
    default_name = default.name if default else None

    if not projects:
        click.echo(click.style("No projects registered.", fg="yellow"))
        click.echo()
        click.echo("Add a project with:")
        click.echo(click.style("  perplexity-claude-agent add-project <path>", fg="bright_white"))
        return

    click.echo(click.style(f"Registered Projects ({len(projects)}):", fg="cyan", bold=True))
    click.echo()

    for project in projects:
        # Name with default marker
        name_display = project.name
        if project.name == default_name:
            name_display = f"{project.name} {click.style('[default]', fg='green')}"

        click.echo(f"  {click.style(name_display, fg='bright_white', bold=True)}")
        click.echo(f"    Path:  {project.path}")

        if project.tech_stack:
            stack_str = ", ".join(project.tech_stack)
            click.echo(f"    Stack: {stack_str}")

        if project.description:
            # Truncate long descriptions
            desc = project.description[:60] + "..." if len(project.description) > 60 else project.description
            click.echo(f"    Desc:  {desc}")

        click.echo()


@main.command()
def setup() -> None:
    """Interactive setup wizard."""
    click.echo(click.style("perplexity-claude-agent Setup", fg="cyan", bold=True))
    click.echo()

    # Check Claude Code CLI
    click.echo("Checking Claude Code CLI...")
    try:
        result = subprocess.run(
            ["claude", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            version = result.stdout.strip() or result.stderr.strip()
            click.echo(click.style(f"  Found: {version}", fg="green"))
        else:
            click.echo(click.style("  Warning: Claude Code CLI returned an error.", fg="yellow"))
    except FileNotFoundError:
        click.echo(click.style("  Error: Claude Code CLI not found.", fg="red"))
        click.echo("  Install it from: https://claude.com/claude-code")
        click.echo()
    except subprocess.TimeoutExpired:
        click.echo(click.style("  Warning: Claude Code CLI timed out.", fg="yellow"))
    except Exception as e:
        click.echo(click.style(f"  Warning: Could not check Claude Code CLI: {e}", fg="yellow"))

    click.echo()

    # Check for projects
    registry = get_registry()
    projects = registry.list_projects()

    if not projects:
        click.echo("No projects registered yet.")
        if click.confirm("Would you like to add a project now?"):
            path = click.prompt(
                "Enter the project path",
                type=click.Path(exists=True, file_okay=False, resolve_path=True),
            )
            try:
                project = registry.add_project(path)
                click.echo(click.style(f"Added project: {project.name}", fg="green"))
            except ValueError as e:
                click.echo(click.style(f"Error: {e}", fg="red"))
    else:
        click.echo(f"Projects registered: {len(projects)}")
        for p in projects:
            click.echo(f"  - {p.name}: {p.path}")

    click.echo()

    # Next steps
    click.echo(click.style("Next Steps:", fg="cyan", bold=True))
    click.echo()
    click.echo("1. Start the server:")
    click.echo(click.style("   perplexity-claude-agent start", fg="bright_white"))
    click.echo()
    click.echo("2. Expose via tunnel (in another terminal):")
    click.echo(click.style("   ngrok http 8765", fg="bright_white"))
    click.echo("   or")
    click.echo(click.style("   cloudflared tunnel --url http://localhost:8765", fg="bright_white"))
    click.echo()
    click.echo("3. Add the HTTPS URL as a custom connector in Perplexity Computer")
    click.echo()
    click.echo("4. Use the custom skill template:")
    click.echo(click.style("   perplexity-claude-agent show-skill", fg="bright_white"))
    click.echo()


@main.command("show-skill")
@click.option("--copy", "-c", is_flag=True, help="Copy to clipboard (macOS)")
@click.option("--save", "-s", type=click.Path(), help="Save to file")
def show_skill(copy: bool, save: str | None) -> None:
    """Display the Perplexity Computer custom skill template."""
    from .skill_template import generate_skill

    # Get projects for customization
    registry = get_registry()
    projects = registry.list_projects()

    project_dicts = [
        {
            "name": p.name,
            "description": p.description or "No description",
            "tech_stack": p.tech_stack,
        }
        for p in projects
    ] if projects else None

    # Generate skill
    skill = generate_skill(projects=project_dicts)

    # Header
    header = """# Perplexity Computer Custom Skill Template
# Copy everything below this line and paste into Perplexity Computer's custom skills
# ─────────────────────────────────────────────
"""

    full_output = header + "\n" + skill

    # Handle --save
    if save:
        try:
            with open(save, "w", encoding="utf-8") as f:
                f.write(full_output)
            click.echo(click.style(f"Saved to: {save}", fg="green"))
            return
        except Exception as e:
            click.echo(click.style(f"Error saving file: {e}", fg="red"), err=True)
            sys.exit(1)

    # Handle --copy
    if copy:
        try:
            subprocess.run(
                ["pbcopy"],
                input=full_output.encode("utf-8"),
                check=True,
            )
            click.echo(click.style("Copied to clipboard!", fg="green"))
            click.echo()
            click.echo(f"Skill generated with {len(projects) if projects else 0} registered projects.")
            click.echo("Paste it into Perplexity Computer's custom skills section.")
            return
        except FileNotFoundError:
            click.echo(
                click.style("Warning: pbcopy not found (macOS only). Printing instead.", fg="yellow"),
                err=True,
            )
        except subprocess.CalledProcessError as e:
            click.echo(
                click.style(f"Warning: Failed to copy to clipboard: {e}", fg="yellow"),
                err=True,
            )

    # Print to stdout
    click.echo(full_output)


if __name__ == "__main__":
    main()
