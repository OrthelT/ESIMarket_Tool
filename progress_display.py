"""Rich progress display with Panel layout for ESI Market Tool.

Composes a Progress instance (task tracker/renderer) with an explicit Live
instance (display manager) to avoid the overlapping-panel bug.  When Progress
subclasses override get_renderable() and the panel height changes dynamically,
Progress's *internal* Live loses track of the cursor position.  By using Live
directly and implementing __rich__(), the display always rebuilds from current
state on each refresh cycle.
"""

from __future__ import annotations

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
)
from rich.text import Text


class MarketProgress:
    """Progress bars inside a styled Panel, managed by an explicit Live.

    Instead of subclassing Progress (which activates its own internal Live),
    this class holds a Progress as a pure task-state tracker and renders it
    via a separate Live instance.  Live calls ``__rich__()`` on each refresh,
    rebuilding the Panel from the current task list — so height changes from
    adding tasks never leave ghost artifacts.

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
        self._console = console
        self._disable = disable
        self._title = title
        self._min_rows = min_rows
        self._status = Text("", style="dim italic", no_wrap=True, overflow="ellipsis")

        # Inner Progress — never used as a context manager.
        # Its internal Live stays dormant; we only call add_task/update/
        # make_tasks_table on it.
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=40),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=console,
        )

        self._live: Live | None = None

    # ------------------------------------------------------------------
    # Rich renderable protocol — called by Live on each refresh
    # ------------------------------------------------------------------

    def __rich__(self) -> Panel:
        """Build the Panel dynamically from current Progress state."""
        task_table = self._progress.make_tasks_table(self._progress.tasks)
        # Pad to min_rows so the panel starts at full height and never
        # grows — an extra safeguard even though explicit Live handles
        # height changes better than Progress's internal Live.
        visible = sum(1 for t in self._progress.tasks if t.visible)
        filler = [Text(" ")] * max(0, self._min_rows - visible)
        return Panel(
            Group(task_table, *filler, self._status),
            title=f"[bold]{self._title}[/bold]",
            border_style="bright_blue",
            padding=(0, 1),
        )

    # ------------------------------------------------------------------
    # Context manager — starts/stops the explicit Live
    # ------------------------------------------------------------------

    def __enter__(self) -> MarketProgress:
        if self._disable:
            return self
        self._live = Live(
            self,
            console=self._console,
            refresh_per_second=10,
            redirect_stderr=True,
            redirect_stdout=False,
        )
        self._live.start()
        return self

    def __exit__(self, *args) -> None:
        if self._live:
            self._live.stop()
            self._live = None

    # ------------------------------------------------------------------
    # Progress delegation (duck-types as Progress for esi_client.py)
    # ------------------------------------------------------------------

    def add_task(self, description: str, **kwargs) -> TaskID:
        """Add a task to the inner Progress tracker."""
        return self._progress.add_task(description, **kwargs)

    def update(self, task_id: TaskID, **kwargs) -> None:
        """Update a task on the inner Progress tracker."""
        self._progress.update(task_id, **kwargs)

    # ------------------------------------------------------------------
    # Status line
    # ------------------------------------------------------------------

    @property
    def status(self) -> str:
        return self._status.plain

    @status.setter
    def status(self, value: str) -> None:
        self._status.plain = value
