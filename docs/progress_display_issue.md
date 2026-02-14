# Progress Display Panel Rendering Issue

## Problem

When the ESI Market Tool runs the full pipeline (orders + history), the progress
display renders **two overlapping panels** instead of a single panel that updates
in-place. The first panel shows the "Market orders" task, and when the "Market
history" task is added, a second panel appears below it instead of replacing the
first.

### Screenshot Reference

The issue looks like this — two stacked panels instead of one:

```
         ── ESI Market Data ──
  Market orders ━━━━━━━━━━━  97% 35/36 0:00:15
         ── ESI Market Data ──
  Market orders  ━━━━━━━━━━ 100% 36/36  0:00:15
  Market history ━━━━        16% 144/892 0:00:26
  ▶ EM Shield Amplifier II
```

## Root Cause

Rich's `Live` display tracks how many terminal lines it previously rendered and
uses ANSI cursor movement to overwrite them on each refresh. When the panel
**grows taller** (from 1 task row to 2 task rows + status line), Live moves the
cursor up N lines (old height) but renders N+2 lines (new height), leaving the
old panel as a ghost artifact above.

Contributing factors:
- **Logger output to stderr** — `logging.StreamHandler` writes directly to
  stderr, bypassing Rich's Console. These writes shift the cursor position,
  breaking Live's tracking. Setting `redirect_stderr=True` on Progress was
  attempted but did not fully resolve the issue.
- **Panel height change** — The panel grows when `esi_client.py` calls
  `progress.add_task("Market history", ...)` during the history fetch phase.
  Live cannot cleanly erase and re-render when the renderable height increases.

## What Was Tried

### Approach 1: Custom `Live` wrapper (`MarketProgressDisplay`)
- Created a custom class wrapping `Progress` + `Text` in a `Panel`, managed by
  a standalone `Live` instance.
- **Result:** Same overlapping panel issue. The custom Live had the same cursor
  tracking problem as Progress's built-in Live.

### Approach 2: Subclass `Progress`, override `get_renderable()`
- `MarketProgress(Progress)` wraps the task table in a `Panel` via
  `get_renderable()`.
- Uses Progress's built-in Live (which is battle-tested for dynamic task counts).
- Added `redirect_stderr=True` to intercept logger output.
- **Result:** Still produces overlapping panels. The stderr redirect alone does
  not prevent the artifact when panel height changes.

### Approach 3: Fixed-height padding in `get_renderable()`
- Added filler `Text(" ")` lines to pad the panel to a minimum height
  (`min_rows=2`), so it never grows when the second task appears.
- **Result:** Untested live — static renders show correct equal-height panels,
  but the approach may still fail if Live's cursor tracking is fundamentally
  broken by logger output.

## Current State (as of 2026-02-14)

The code currently uses **Approach 2 + 3** (subclassed Progress with fixed-height
padding). Files involved:

- **`progress_display.py`** — `MarketProgress(Progress)` subclass
- **`esi_client.py`** — `fetch_market_history()` accepts `on_item` callback for
  status line updates (item names no longer embedded in progress description)
- **`cli.py`** — Uses `MarketProgress` with `with progress:` context manager

## Recommended Next Steps

### 1. Study Rich Live documentation and examples
- Rich Live docs: https://rich.readthedocs.io/en/latest/live.html
- Reference example: `live-progress-example` (user-provided, exact path TBD)
- Key question: does Rich's `Live` class need to be used explicitly (rather than
  relying on Progress's built-in Live) to properly handle composed layouts like
  `Panel(Group(Progress, Text))`?

### 2. Consider using `Live` directly with `Progress` as a renderable
The Rich docs may show a pattern where:
```python
from rich.live import Live
from rich.progress import Progress
from rich.panel import Panel
from rich.console import Group

progress = Progress(...)
status = Text("")

with Live(Panel(Group(progress, status)), refresh_per_second=10) as live:
    # Update progress and status; Live re-renders the composed layout
    ...
```

In this pattern, `Progress` is NOT used as a context manager (no `with progress:`).
Instead, `Live` manages the display, and `Progress` is just a renderable whose
internal state changes. This may handle height changes differently than Progress's
own built-in Live.

### 3. Consider pre-creating all tasks upfront
If the panel height must stay fixed, pre-create both tasks at the start:
```python
with progress:
    orders_task = progress.add_task("Market orders", total=None)
    history_task = progress.add_task("Market history", total=None, start=False)
    # Both rows visible from frame 1 — panel never grows
```
This requires `esi_client.py` methods to accept optional pre-created `task_id`
parameters instead of always calling `progress.add_task()` internally.

### 4. Investigate logger interference
Even with `redirect_stderr=True`, the logging StreamHandler may still cause
issues. Consider:
- Temporarily disabling console log handlers during the Live display
- Using Rich's `RichHandler` for logging (integrates with Console/Live)
- Checking if `verbose_console_logging = false` in config.toml resolves it

## Architecture Notes

The progress display touches three layers:
1. **`progress_display.py`** — Display class (rendering, layout, styling)
2. **`esi_client.py`** — ESI fetch methods (progress updates, `on_item` callback)
3. **`cli.py`** — Orchestration (creates display, wires callbacks, manages lifecycle)

The `on_item: Callable[[str], None]` callback in `esi_client.py` is a clean
decoupling — the ESI client doesn't know about Panels or Live, it just calls a
function with the current item name. This pattern should be preserved regardless
of which display approach is used.
