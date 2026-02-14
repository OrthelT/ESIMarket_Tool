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

## What Was Tried (and failed)

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
- **Result:** Still produces overlapping panels in live terminal rendering.

### Approach 4: Composition with explicit `Live` (without concurrent fetches)
- `MarketProgress` no longer subclasses `Progress` — holds an inner `Progress`
  as a pure state tracker, managed by an explicit `Live` instance.
- Implements `__rich__()` so Live re-renders the Panel dynamically each cycle.
- **Result:** Still produces ghost panels. The fundamental issue was that tasks
  were added sequentially (orders first, history second), so the panel height
  changed mid-display regardless of how Live was managed.

## Resolution (2026-02-14)

**Fixed** by combining composition-based display with **concurrent fetches** and
**pre-created tasks**. This eliminates panel height changes entirely.

### The two-part fix

#### Part 1: Composition over inheritance (`progress_display.py`)
`MarketProgress` no longer subclasses `Progress`. Instead it:
1. **Composes** a `Progress` instance (pure task state tracker, never started)
2. **Manages** an explicit `Live` instance (owns the display lifecycle)
3. **Implements** `__rich__()` so Live re-renders the Panel from current state
4. **Duck-types** as Progress — provides `add_task()` and `update()` methods

This follows the pattern from `live-progress-examp.py` (Rich's own example):
`Progress` is used as a renderable inside `Live`, never as a context manager.

#### Part 2: Pre-create tasks + concurrent fetches (`cli.py`)
Instead of creating tasks inside `esi_client.py` fetch methods (which causes
the panel to grow mid-display), tasks are now:
1. **Pre-created** in `cli.py` before `with progress:` starts the Live display
2. **Passed** to `esi_client.py` via the new `task_id` parameter
3. **Updated concurrently** via `asyncio.gather()` — both fetches run in parallel

```python
# Pre-create both tasks — panel starts at full height
orders_task = progress.add_task("Market orders", total=None)
history_task = progress.add_task("Market history", total=len(type_ids))

with progress:
    # Run both fetches concurrently — they share the rate limiter
    (market_orders, mkt_time), (historical_df, hist_time, history_result) = (
        await asyncio.gather(
            _fetch_and_export_orders(..., task_id=orders_task),
            _fetch_and_export_history(..., task_id=history_task),
        )
    )
```

### Why it works
- **No height change** — Both task rows exist from the first frame. The panel
  never grows, so Live's cursor tracking is never challenged.
- **Explicit Live** — `Live(self, ...)` where `self.__rich__()` rebuilds the
  Panel each cycle. Live owns the full display from the start.
- **`redirect_stderr=True`** — Logger output from `StreamHandler` is intercepted
  and rendered above the panel, keeping cursor tracking intact.
- **Concurrent performance** — Wall-clock time is now `max(orders, history)`
  instead of `orders + history`. Both coroutines share the `TokenBucketRateLimiter`
  naturally via its `asyncio.Lock`.

### Files changed
- **`progress_display.py`** — Composition wrapper with `__rich__()` and explicit `Live`
- **`esi_client.py`** — Added `task_id` parameter to `fetch_market_orders()` and
  `fetch_market_history()` (falls back to creating tasks if not provided)
- **`cli.py`** — Pre-creates tasks, loads type_ids before progress display,
  runs orders + history concurrently via `asyncio.gather()`

## Architecture Notes

The progress display touches three layers:
1. **`progress_display.py`** — Display class (rendering, layout, styling)
2. **`esi_client.py`** — ESI fetch methods (progress updates, `on_item` callback)
3. **`cli.py`** — Orchestration (creates display, wires callbacks, manages lifecycle)

The `on_item: Callable[[str], None]` callback in `esi_client.py` is a clean
decoupling — the ESI client doesn't know about Panels or Live, it just calls a
function with the current item name.

### Key design decisions
- **Tasks pre-created in `cli.py`**, not inside `esi_client.py` — the CLI layer
  knows the full layout, ESI methods just update progress on provided task IDs.
- **`task_id` is optional** — if not provided, fetch methods fall back to
  creating their own task (backward compatible for single-fetch usage).
- **Type IDs loaded before progress** — moved `_load_type_ids_and_names_async()`
  before `with progress:` since we need `len(type_ids)` to size the history task.
