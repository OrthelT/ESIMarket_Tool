# Project Reference

Design goals, architecture decisions, and lessons learned from past development work. Day-to-day developer guidance lives in `AGENTS.md`; scheduling setup lives in `docs/SCHEDULING.md`.

## Project Goals

1. **Simple automation** of ESI market data retrieval into CSV files.
2. **Accessible for non-technical users** — easy setup, clear feedback, minimal friction.
3. **Cross-platform** — must work on Windows, macOS, and Linux.
4. **Scheduled automation** — runs unattended on a recurring schedule.
5. **Configurable output location** — users control where data lands.
6. **Foundation for future features** — SQLite storage and additional CLI/TUI/GUI front ends should be addable without rewriting core logic.

Testing is kept separate from main execution. Modules use dependency injection so they can be tested in isolation.

## History

- **v0.2 (Feb 2026):** The monolithic `esi_markets.py` (~750 lines, module-level side effects, global config) was split into `config.py`, `esi_client.py`, `cli.py`, `market_data.py`, `export.py`, and a thin `esi_markets.py` entry point. `googlesheets_updater.py` and `main.py` were removed. An OAuth callback server, `--headless` mode, and configurable path resolution were added.
- **v0.3:** Migrated HTTP to aiohttp, added the token bucket rate limiter, conditional-request caching for market history, Rich progress display, User-Agent configuration, type ID management in `setup.py`, and concurrent orders + history fetches.

## Architecture Decisions

### Configuration
- `config.py` uses frozen dataclasses so configuration cannot be mutated after loading.
- `project_root` defaults to the config file's parent directory. `resolve_path()` expands `~` and resolves relative paths against it, so the tool works from any working directory (required for cron and Task Scheduler).
- `setup.py` reads and writes `config.toml` as a raw dict, not through `AppConfig`.

### Module boundaries
- `market_data.py` has no project imports and no I/O. It can be used directly in Jupyter notebooks.
- `export.py` uses one `_update_worksheet()` helper for all three Google Sheets worksheets.
- Import graph has no cycles: `cli.py` depends on everything else; `esi_client.py` and `export.py` depend only on `config`; `setup.py` is standalone.

### Authentication
- The OAuth flow runs synchronously before the async event loop starts.
- The callback server handles one request and then shuts down. It runs on a daemon thread so it cannot block process exit. If it fails to start or times out (120 s), the flow falls back to manual URL paste.
- In headless mode, `get_token()` returns `None` instead of opening a browser. Token refresh still works headless; only the first authorization needs interactive mode.
- The default scope is `esi-markets.structure_markets.v1` only.

### History caching (`cache.py`)
Market history requests (~900 items per run) send `If-None-Match` / `If-Modified-Since` headers built from the stored ETag and Last-Modified values.
- A 304 response is a cache hit, not an error. The cached rows are reused and counted in `FetchResult.cache_hits`.
- If ESI returns 304 but no cached data exists for that type ID (for example, the cache file was edited by hand), the client retries without conditional headers.
- Only 200 responses update the cache.
- Caching is on by default and can be disabled with `[caching] enabled = false`.

## Lessons Learned

### Rich progress display: ghost panels
**Symptom:** During a full run, a second "ESI Market Data" panel appeared below the first instead of replacing it.

**Cause:** Rich `Live` moves the cursor up by the height of the previous render. When the panel grows (a second task row is added mid-display), the old panel is left behind. Logger output written directly to stderr also shifts the cursor and breaks Live's tracking.

**Approaches that did not work on their own:**
1. A custom `Live` wrapper around `Progress` + `Text`.
2. Subclassing `Progress` and overriding `get_renderable()`, with `redirect_stderr=True`.
3. Padding the panel to a fixed minimum height.
4. Composition with an explicit `Live`, while still adding tasks sequentially.

**Fix (2026-02-14):**
- `MarketProgress` composes a `Progress` (task state only, never started) and owns an explicit `Live`. It implements `__rich__()` so Live rebuilds the panel each refresh, and duck-types `add_task()` / `update()` for `esi_client.py`.
- `cli.py` creates every progress task **before** `with progress:` starts, then passes each `task_id` to the fetch methods. The panel never changes height.
- `redirect_stderr=True` routes logger output above the panel.
- Orders and history run concurrently with `asyncio.gather()` and share the rate limiter, so wall-clock time is `max(orders, history)` instead of the sum.

**Rule:** Never call `progress.add_task()` while Live is running. Fetch methods only create their own task when `task_id` is `None` (single-fetch use). The `on_item` callback keeps `esi_client.py` unaware of panels — it only reports the current item name.

## Open Items

- **Token storage location:** `token.json` is written to the project directory. Moving it to a user-writable directory (for example via `platformdirs`) would avoid failures when the project is installed in a read-only location such as `Program Files`.
- **Built-in scheduling:** Scheduling currently relies on OS tools (`docs/SCHEDULING.md`). A built-in scheduler (`schedule` or `APScheduler`) was considered for users who do not want to configure cron or Task Scheduler.
- **SQLite output:** Planned as an alternative to CSV.
- **Live ESI testing:** Automated tests cover caching and the ESI client with mocks; end-to-end runs require real EVE SSO credentials.
