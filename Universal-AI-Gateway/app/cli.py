"""
Universal AI Gateway Command Line Interface.
Provides administrative operations for tenants, API keys, cache, and health status.
"""

import asyncio
import functools
import uuid
from typing import Optional
from decimal import Decimal

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint

from sqlalchemy import select
from app.db.database import db_manager
from app.db.models import APIKey, Tenant
from app.services.api_key_service import get_api_key_service
from app.cache.redis import get_redis
from app.cache.cache_manager import CacheManager

app = typer.Typer(help="Universal AI Gateway Administrative CLI")
keys_app = typer.Typer(help="Manage client API keys")
tenants_app = typer.Typer(help="Manage tenants")
cache_app = typer.Typer(help="Manage caching layers")

app.add_typer(keys_app, name="keys")
app.add_typer(tenants_app, name="tenants")
app.add_typer(cache_app, name="cache")

console = Console()


def async_command(f):
    """Decorator to run async typer commands."""
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        return asyncio.run(f(*args, **kwargs))
    return wrapper


# --- Tenant Commands ---

@tenants_app.command(name="create")
@async_command
async def tenant_create(
    name: str = typer.Option(..., "--name", "-n", help="Name of the tenant"),
    description: Optional[str] = typer.Option(None, "--desc", "-d", help="Description of the tenant"),
):
    """Create a new tenant organization."""
    session_factory = db_manager.create_session_factory()
    async with session_factory() as session:
        # Check if tenant name exists
        stmt = select(Tenant).where(Tenant.name == name)
        res = await session.execute(stmt)
        if res.scalar_one_or_none():
            console.print(f"[bold red]Error:[/bold red] Tenant with name '{name}' already exists.")
            raise typer.Exit(code=1)

        new_tenant = Tenant(
            id=uuid.uuid4(),
            name=name,
            description=description,
            is_active=True
        )
        session.add(new_tenant)
        await session.commit()
        await session.refresh(new_tenant)

        console.print(f"[bold green]Success![/bold green] Tenant created.")
        console.print(f"  [bold]ID:[/bold] {new_tenant.id}")
        console.print(f"  [bold]Name:[/bold] {new_tenant.name}")


@tenants_app.command(name="list")
@async_command
async def tenant_list():
    """List all tenants in the system."""
    session_factory = db_manager.create_session_factory()
    async with session_factory() as session:
        stmt = select(Tenant)
        res = await session.execute(stmt)
        tenants = res.scalars().all()

        if not tenants:
            console.print("[yellow]No tenants found.[/yellow]")
            return

        table = Table(title="Tenants List")
        table.add_column("ID", style="cyan")
        table.add_column("Name", style="magenta")
        table.add_column("Description")
        table.add_column("Active", style="green")
        table.add_column("Created At")

        for t in tenants:
            table.add_row(
                str(t.id),
                t.name,
                t.description or "",
                "Yes" if t.is_active else "No",
                t.created_at.strftime("%Y-%m-%d %H:%M:%S") if t.created_at else ""
            )

        console.print(table)


# --- API Key Commands ---

@keys_app.command(name="create")
@async_command
async def key_create(
    tenant_id: str = typer.Option(..., "--tenant-id", "-t", help="Tenant UUID string"),
    name: str = typer.Option(..., "--name", "-n", help="Name/Label for this key"),
    rate_limit: int = typer.Option(60, "--rate-limit", "-r", help="Requests per minute"),
    cost_limit: Optional[float] = typer.Option(None, "--cost-limit", "-c", help="Daily cost limit in USD"),
):
    """Generate and authorize a new API key."""
    try:
        tenant_uuid = uuid.UUID(tenant_id)
    except ValueError:
        console.print("[bold red]Error:[/bold red] Invalid tenant UUID format.")
        raise typer.Exit(code=1)

    session_factory = db_manager.create_session_factory()
    async with session_factory() as session:
        # Verify tenant exists
        stmt = select(Tenant).where(Tenant.id == tenant_uuid)
        res = await session.execute(stmt)
        if not res.scalar_one_or_none():
            console.print(f"[bold red]Error:[/bold red] Tenant with ID {tenant_id} not found.")
            raise typer.Exit(code=1)

        service = get_api_key_service()
        daily_limit = Decimal(str(cost_limit)) if cost_limit is not None else None
        
        raw_key, key_obj = await service.create_key(
            db=session,
            tenant_id=tenant_uuid,
            name=name,
            rate_limit_per_minute=rate_limit,
            daily_cost_limit=daily_limit,
        )

        console.print(Panel(
            f"[bold green]API Key Created successfully![/bold green]\n\n"
            f"[bold red]IMPORTANT: Copy this key now. It will not be shown again.[/bold red]\n\n"
            f"[bold]Raw API Key:[/bold] [yellow]{raw_key}[/yellow]\n"
            f"[bold]Prefix:[/bold] {key_obj.key_prefix}\n"
            f"[bold]Key ID:[/bold] {key_obj.id}",
            title="Credential Generation"
        ))


@keys_app.command(name="list")
@async_command
async def key_list():
    """List all API keys."""
    session_factory = db_manager.create_session_factory()
    async with session_factory() as session:
        stmt = select(APIKey)
        res = await session.execute(stmt)
        keys = res.scalars().all()

        if not keys:
            console.print("[yellow]No API keys found.[/yellow]")
            return

        table = Table(title="API Keys List")
        table.add_column("ID", style="cyan")
        table.add_column("Name", style="magenta")
        table.add_column("Prefix")
        table.add_column("Tenant ID")
        table.add_column("RPM Limit", justify="right")
        table.add_column("Active", style="green")

        for k in keys:
            table.add_row(
                str(k.id),
                k.name,
                k.key_prefix,
                str(k.tenant_id),
                str(k.rate_limit_per_minute),
                "Yes" if k.is_active else "No"
            )

        console.print(table)


@keys_app.command(name="revoke")
@async_command
async def key_revoke(
    key_id: str = typer.Argument(..., help="UUID of the API key to deactivate")
):
    """Revoke (deactivate) an active API key."""
    try:
        key_uuid = uuid.UUID(key_id)
    except ValueError:
        console.print("[bold red]Error:[/bold red] Invalid key UUID format.")
        raise typer.Exit(code=1)

    session_factory = db_manager.create_session_factory()
    async with session_factory() as session:
        service = get_api_key_service()
        success = await service.deactivate_key(session, key_uuid)
        if success:
            console.print(f"[bold green]Success![/bold green] Key {key_id} has been deactivated.")
        else:
            console.print(f"[bold red]Error:[/bold red] Key with ID {key_id} not found.")


@keys_app.command(name="rotate")
@async_command
async def key_rotate(
    key_id: str = typer.Argument(..., help="UUID of the API key to rotate"),
    expires_in_days: Optional[int] = typer.Option(None, "--expires", "-e", help="Expiration of the rotated key in days"),
):
    """Deactivate an old API key and replace it with a new one."""
    try:
        key_uuid = uuid.UUID(key_id)
    except ValueError:
        console.print("[bold red]Error:[/bold red] Invalid key UUID format.")
        raise typer.Exit(code=1)

    session_factory = db_manager.create_session_factory()
    async with session_factory() as session:
        service = get_api_key_service()
        try:
            raw_key, new_key = await service.rotate_key(session, key_uuid, expires_in_days=expires_in_days)
            console.print(Panel(
                f"[bold green]Key successfully rotated![/bold green]\n\n"
                f"[bold red]IMPORTANT: Copy this new key now. It will not be shown again.[/bold red]\n\n"
                f"[bold]New Raw API Key:[/bold] [yellow]{raw_key}[/yellow]\n"
                f"[bold]New Key ID:[/bold] {new_key.id}\n"
                f"[bold]Old Key ID revoked:[/bold] {key_id}",
                title="Credential Rotation"
            ))
        except ValueError as e:
            console.print(f"[bold red]Error:[/bold red] {e}")


# --- Cache Commands ---

@cache_app.command(name="clear")
@async_command
async def cache_clear(
    pattern: str = typer.Option("cache:*", "--pattern", "-p", help="Redis key pattern (glob style)")
):
    """Invalidate cache entries matching a pattern."""
    manager = CacheManager()
    deleted = await manager.invalidate(pattern)
    console.print(f"[bold green]Success![/bold green] Invalidated {deleted} cache keys matching pattern [cyan]'{pattern}'[/cyan].")


# --- Health Command ---

@app.command(name="health")
@async_command
async def health_check():
    """Verify health and connectivity to backend services."""
    # 1. Database Health
    db_ok = await db_manager.health_check()
    
    # 2. Redis Health
    redis_client = get_redis()
    redis_ok = False
    if redis_client:
        try:
            await redis_client.ping()
            redis_ok = True
        except Exception:
            pass

    console.print("\n[bold]Backend Services Status Check:[/bold]")
    db_status = "[green]Healthy[/green]" if db_ok else "[red]Unreachable[/red]"
    redis_status = "[green]Healthy[/green]" if redis_ok else "[red]Unreachable[/red]"
    
    console.print(f"  - Database: {db_status}")
    console.print(f"  - Redis:    {redis_status}")


if __name__ == "__main__":
    app()
