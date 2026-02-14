"""Rich progress display with Panel layout for ESI Market Tool.

Subclasses Progress to wrap the task table in a styled Panel with a
separate status line.  Item names on the status line never cause the
progress bar to reflow.  Uses Progress's built-in Live display, which
properly handles dynamic height changes and stderr redirection.
"""

from rich.console import Console, Group
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.text import Text


class MarketProgress(Progress):
    """Progress wrapped in a Panel with a separate status line.

    Overrides ``get_renderable()`` to wrap the task table in a bordered
    Panel.  A status ``Text`` sits on its own row below the progress bars,
    so variable-length item names never push the bars around.

    Usage::

        progress = MarketProgress(console=console)
        with progress:
            task = progress.add_task("Fetching", total=100)
            progress.update(task, completed=50)
            progress.status = "  ▶ Tritanium"
    """

    def __init__(
        self,
        *,
        console: Console,
        disable: bool = False,
        title: str = "ESI Market Data",
        min_rows: int = 2,
    ):
        # Set before super().__init__ because Live calls get_renderable()
        # during construction.
        self._panel_title = title
        self._min_rows = min_rows
        self._status = Text("", style="dim italic", no_wrap=True, overflow="ellipsis")

        super().__init__(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=40),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=console,
            redirect_stderr=True,
            disable=disable,
        )

    @property
    def status(self) -> str:
        return self._status.plain

    @status.setter
    def status(self, value: str) -> None:
        self._status.plain = value

    def get_renderable(self) -> Panel:
        """Wrap the task table and status line in a styled Panel."""
        task_table = self.make_tasks_table(self.tasks)
        # Pad to a fixed height so the panel never grows when new tasks
        # are added — height changes confuse Live's cursor tracking.
        visible = sum(1 for t in self.tasks if t.visible)
        filler = [Text(" ")] * max(0, self._min_rows - visible)
        return Panel(
            Group(task_table, *filler, self._status),
            title=f"[bold]{self._panel_title}[/bold]",
            border_style="bright_blue",
            padding=(0, 1),
        )
