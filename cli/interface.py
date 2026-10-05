"""Rich CLI interface for NaoMapScrape."""

import asyncio
from typing import List

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table
from rich.live import Live

console = Console()


def welcome():
    console.print(
        Panel(
            "[bold blue]NaoMapScrape[/bold blue] v1.0.0\n"
            "[dim]Google Maps Lead Discovery CLI[/dim]",
            title="Welcome",
            border_style="blue",
        )
    )


class CLIInterface:
    """Renders real-time progress and results to the terminal."""

    def __init__(self):
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        )
        self.live = Live(self.progress, console=console, refresh_per_second=4)
        self.task_id = None

    def start(self, total: int):
        self.welcome()
        self.task_id = self.progress.add_task("[cyan]Scraping...", total=total)
        self.live.start()

    def update(self, payload: dict):
        if self.task_id is None:
            return
        event = payload.get("event")
        collected = payload.get("collected", 0)
        keyword = payload.get("keyword", "-")
        location = payload.get("location", "-")

        desc = f"[cyan]{event.title()}[/cyan]: {keyword} in {location} ([green]{collected}[/green] leads)"
        self.progress.update(self.task_id, description=desc, completed=collected)

    def stop(self):
        self.live.stop()
        console.print("\n[bold green]✓ Collection Complete![/bold green]")

    def show_results(self, leads: List[dict]):
        if not leads:
            console.print("[yellow]No leads found.[/yellow]")
            return

        table = Table(title="Recent Leads", show_header=True, header_style="bold magenta")
        table.add_column("Name", style="dim", width=25)
        table.add_column("Phone", width=15)
        table.add_column("Website", width=20)
        table.add_column("Rating", justify="right")

        for lead in leads[:10]:
            table.add_row(
                lead.get("name") or "-",
                lead.get("phone") or "-",
                lead.get("website_status") or "-",
                str(lead.get("rating") or "-"),
            )
        
        if len(leads) > 10:
            table.add_row("...", "...", "...", "...")
        
        console.print(table)

    @staticmethod
    def welcome():
        welcome()
