"""
Universal AI Gateway Admin CLI.
Provides interactive management for API keys, tenants, and system health.
"""

import asyncio
import sys
from datetime import datetime
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.panel import Panel
from sqlalchemy import select
from sqlalchemy.orm import selectinload

# Ensure app is in path
sys.path.append(".")

from app.db.database import db_manager
from app.db.models import APIKey, Tenant, RequestLog

app = typer.Typer(
    help="🚀 Universal AI Gateway Admin CLI",
    add_completion=False,
    rich_markup_mode="rich"
)

keys_app = typer.Typer(help="Manage API keys", invoke_without_command=True)
tenants_app = typer.Typer(help="Manage Tenants", invoke_without_command=True)

@keys_app.callback()
def keys_main(ctx: typer.Context):
    """Callback for API keys group."""
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())

@tenants_app.callback()
def tenants_main(ctx: typer.Context):
    """Callback for Tenants group."""
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())

app.add_typer(keys_app, name="keys")
app.add_typer(tenants_app, name="tenants")

console = Console()

async def get_db_health():
    return await db_manager.health_check()

@app.command()
def health():
    """Check the health of gateway services."""
    async def _run():
        console.print("[bold blue]Checking System Health...[/bold blue]")
        db_ok = await get_db_health()
        
        status_table = Table(show_header=False, box=None)
        status_table.add_row("PostgreSQL", "[green]ONLINE[/green]" if db_ok else "[red]OFFLINE[/red]")
        # Redis check would go here if exposed
        
        console.print(Panel(status_table, title="Backend Status", expand=False))
        
    asyncio.run(_run())

@keys_app.command("list")
def list_keys():
    """List all API keys across all tenants."""
    async def _run():
        session_factory = db_manager.create_session_factory()
        async with session_factory() as session:
            stmt = select(APIKey).options(selectinload(APIKey.tenant))
            result = await session.execute(stmt)
            keys = result.scalars().all()
            
            if not keys:
                console.print("[yellow]No API keys found.[/yellow]")
                return

            table = Table(title="Active API Keys")
            table.add_column("ID (Short)", style="dim")
            table.add_column("Name", style="bold cyan")
            table.add_column("Tenant", style="green")
            table.add_column("Prefix", style="yellow")
            table.add_column("Rate Limit", justify="right")
            table.add_column("Budget", justify="right")
            table.add_column("Models", style="dim")
            table.add_column("Status")

            for k in keys:
                status = "[green]Active[/green]" if k.is_active else "[red]Inactive[/red]"
                budget_str = f"${k.daily_cost_limit:.4f}" if k.daily_cost_limit else "Unlimited"
                models_str = ",".join(k.allowed_models) if k.allowed_models else "*"
                
                table.add_row(
                    str(k.id)[:8],
                    k.name,
                    k.tenant.name,
                    k.key_prefix,
                    f"{k.rate_limit_per_minute} req/min",
                    budget_str,
                    models_str,
                    status
                )
            
            console.print(table)
            
    asyncio.run(_run())


@keys_app.command("create")
def create_key(
    tenant_name: str = typer.Argument(..., help="Name of the tenant"),
    name: str = typer.Argument(..., help="Friendly name for the key"),
    limit: int = typer.Option(60, "--limit", help="Requests per minute"),
    budget: float = typer.Option(0.0, "--budget", help="Daily cost limit in USD (0 for unlimited)"),
    models: Optional[str] = typer.Option(None, "--models", help="Comma-separated list of allowed models"),
):
    """Create a new API key for a tenant."""

    async def _run():
        from app.services.api_key_service import get_api_key_service
        from decimal import Decimal

        session_factory = db_manager.create_session_factory()
        async with session_factory() as session:
            # Find tenant
            stmt = select(Tenant).where(Tenant.name == tenant_name)
            result = await session.execute(stmt)
            tenant = result.scalar_one_or_none()

            if not tenant:
                console.print(f"[red]Error: Tenant '{tenant_name}' not found.[/red]")
                return

            allowed_models = models.split(",") if models else None
            
            service = get_api_key_service()
            raw_key, key_obj = await service.create_key(
                db=session,
                tenant_id=tenant.id,
                name=name,
                rate_limit_per_minute=limit,
                daily_cost_limit=Decimal(str(budget)) if budget > 0 else None,
                allowed_models=allowed_models
            )

            console.print(
                f"[green]Successfully created API key: [bold]{key_obj.name}[/bold][/green]"
            )
            console.print(f"Prefix: [yellow]{key_obj.key_prefix}[/yellow]")
            console.print(
                f"Raw Key: [bold white on blue] {raw_key} [/bold white on blue]"
            )
            console.print(
                "[bold red]SAVE THIS KEY NOW! It will never be shown again.[/bold red]"
            )

    asyncio.run(_run())


@keys_app.command("rotate")
def rotate_key(
    key_prefix: str = typer.Argument(..., help="Prefix of the key to rotate"),
):
    """Rotate an API key (invalidates old, generates new)."""

    async def _run():
        from app.services.api_key_service import get_api_key_service

        session_factory = db_manager.create_session_factory()
        async with session_factory() as session:
            # Find key by prefix
            stmt = select(APIKey).where(APIKey.key_prefix == key_prefix)
            result = await session.execute(stmt)
            key_obj = result.scalar_one_or_none()

            if not key_obj:
                console.print(
                    f"[red]Error: Key with prefix '{key_prefix}' not found.[/red]"
                )
                return

            service = get_api_key_service()
            raw_key, new_key = await service.rotate_key(db=session, key_id=key_obj.id)

            console.print(f"[green]Key rotated successfully.[/green]")
            console.print(f"New Prefix: [yellow]{new_key.key_prefix}[/yellow]")
            console.print(
                f"New Raw Key: [bold white on blue] {raw_key} [/bold white on blue]"
            )
            console.print("[bold red]SAVE THIS KEY NOW![/bold red]")

    asyncio.run(_run())


@keys_app.command("revoke")
def revoke_key(
    key_prefix: str = typer.Argument(..., help="Prefix of the key to revoke"),
):
    """Revoke (deactivate) an API key."""

    async def _run():
        from app.services.api_key_service import get_api_key_service

        session_factory = db_manager.create_session_factory()
        async with session_factory() as session:
            stmt = select(APIKey).where(APIKey.key_prefix == key_prefix)
            result = await session.execute(stmt)
            key_obj = result.scalar_one_or_none()

            if not key_obj:
                console.print(
                    f"[red]Error: Key with prefix '{key_prefix}' not found.[/red]"
                )
                return

            service = get_api_key_service()
            await service.deactivate_key(db=session, key_id=key_obj.id)
            console.print(f"[bold red]Key {key_prefix}... revoked.[/bold red]")

    asyncio.run(_run())

@tenants_app.command("list")
def list_tenants():
    """List all tenants and their settings."""
    async def _run():
        session_factory = db_manager.create_session_factory()
        async with session_factory() as session:
            stmt = select(Tenant)
            result = await session.execute(stmt)
            tenants = result.scalars().all()
            
            if not tenants:
                console.print("[yellow]No tenants found.[/yellow]")
                return

            table = Table(title="System Tenants")
            table.add_column("ID", style="dim", no_wrap=True)
            table.add_column("Name", style="bold green")
            table.add_column("Created At", style="blue")
            
            for t in tenants:
                table.add_row(
                    str(t.id),
                    t.name,
                    t.created_at.strftime("%Y-%m-%d %H:%M")
                )
            console.print(table)
            
    asyncio.run(_run())

@tenants_app.command("create")
def create_tenant(name: str = typer.Argument(..., help="Name of the new tenant")):
    """Create a new organizational tenant."""
    async def _run():
        session_factory = db_manager.create_session_factory()
        async with session_factory() as session:
            # Check if exists
            stmt = select(Tenant).where(Tenant.name == name)
            result = await session.execute(stmt)
            if result.scalar_one_or_none():
                console.print(f"[red]Error: Tenant '{name}' already exists.[/red]")
                return

            new_t = Tenant(name=name)
            session.add(new_t)
            await session.commit()
            console.print(f"[green]Tenant [bold]{name}[/bold] created safely (ID: {new_t.id}).[/green]")
            
    asyncio.run(_run())

@tenants_app.command("delete")
def delete_tenant(name: str = typer.Argument(..., help="Name of the tenant to delete")):
    """Delete a tenant and all associated data."""
    if not typer.confirm(f"Are you sure you want to delete tenant '{name}' and ALL its keys?"):
        raise typer.Abort()

    async def _run():
        session_factory = db_manager.create_session_factory()
        async with session_factory() as session:
            stmt = select(Tenant).where(Tenant.name == name)
            result = await session.execute(stmt)
            tenant = result.scalar_one_or_none()
            
            if not tenant:
                console.print(f"[red]Error: Tenant '{name}' not found.[/red]")
                return

            await session.delete(tenant)
            await session.commit()
            console.print(f"[bold red]Tenant '{name}' and its dependencies have been purged.[/bold red]")
            
    asyncio.run(_run())

@app.command()
def setup():
    """Interactive walkthrough to set up a new tenant and API key."""
    console.print(Panel("[bold green]Welcome to Universal AI Gateway Setup![/bold green]", expand=False))
    
    tenant_name = typer.prompt("Step 1: Enter a name for the new Tenant")
    
    async def _run_tenant():
        session_factory = db_manager.create_session_factory()
        async with session_factory() as session:
            # Check if exists
            stmt = select(Tenant).where(Tenant.name == tenant_name)
            result = await session.execute(stmt)
            tenant = result.scalar_one_or_none()
            if not tenant:
                tenant = Tenant(name=tenant_name)
                session.add(tenant)
                await session.commit()
                console.print(f"[green]Tenant '{tenant_name}' created.[/green]")
            else:
                console.print(f"[yellow]Tenant '{tenant_name}' already exists. Using existing tenant.[/yellow]")
            return tenant.id

    tenant_id = asyncio.run(_run_tenant())
    
    console.print("\n[bold green]Step 2: Create your first API Key[/bold green]")
    key_name = typer.prompt("Enter a name for this key", default="Primary Key")
    limit = typer.prompt("Set a rate limit (requests per minute)", type=int, default=60)
    budget = typer.prompt("Set a daily cost limit ($)", type=float, default=1.0)
    
    async def _run_key():
        from app.services.api_key_service import get_api_key_service
        from decimal import Decimal
        
        session_factory = db_manager.create_session_factory()
        async with session_factory() as session:
            service = get_api_key_service()
            raw_key, key_obj = await service.create_key(
                db=session,
                tenant_id=tenant_id,
                name=key_name,
                rate_limit_per_minute=limit,
                daily_cost_limit=Decimal(str(budget))
            )
            return raw_key, key_obj.key_prefix

    raw_key, prefix = asyncio.run(_run_key())
    
    console.print(f"\n[bold green]Setup Complete![/bold green]")
    console.print(f"Key Prefix: [yellow]{prefix}[/yellow]")
    console.print(f"Your Secret Key: [bold white on blue] {raw_key} [/bold white on blue]")
    console.print("[bold red]SAVE THIS KEY! It will not be shown again.[/bold red]")

@app.command()
def stats():
    """Display real-time gateway statistics from the database."""
    async def _run():
        from sqlalchemy import func
        
        session_factory = db_manager.create_session_factory()
        async with session_factory() as session:
            # Total Requests
            stmt = select(func.count(RequestLog.id))
            result = await session.execute(stmt)
            total = result.scalar()
            
            # Success Rate (status_code < 400)
            stmt = select(func.count(RequestLog.id)).where(RequestLog.status_code < 400)
            result = await session.execute(stmt)
            success = result.scalar()
            
            # Average Latency
            stmt = select(func.avg(RequestLog.latency_ms))
            result = await session.execute(stmt)
            avg_latency = result.scalar() or 0.0
            
            # Total Cost
            stmt = select(func.sum(RequestLog.cost_usd))
            result = await session.execute(stmt)
            total_cost = result.scalar() or 0.0

            success_rate = (success / total * 100) if total > 0 else 0
            
            console.print(Panel(
                f"Total Requests: [bold]{total}[/bold]\n"
                f"Success Rate:   [bold green]{success_rate:.1f}%[/bold green]\n"
                f"Avg Latency:    [bold blue]{avg_latency:.1f}ms[/bold blue]\n"
                f"Total Cost:     [bold yellow]${total_cost:.6f}[/bold yellow]",
                title="Gateway Statistics",
                expand=False
            ))
            
    asyncio.run(_run())

if __name__ == "__main__":
    app()
