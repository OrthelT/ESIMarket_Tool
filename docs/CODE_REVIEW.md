# Code Review & Refactoring Plan

**Date:** 2026-02-10
**Reviewer:** Claude (Opus 4.6)
**Codebase:** ESIMarket_Tool v0.2

---

## Project Goals

The owner's stated objectives for this tool:

1. **Simple, straightforward automation** of ESI market data retrieval into CSV files
2. **Accessible for non-technical users** — easy setup, clear feedback, minimal friction
3. **Cross-platform** — must work on Windows and Mac/Linux
4. **Scheduled automation** — ability to run unattended on a recurring schedule
5. **Configurable output location** — users control where data lands
6. **Solid foundation for future features** — SQLite support, additional CLI/TUI/GUI features should be easy to add without rewriting core logic

Testing should be a separate concern from main execution. The codebase needs good separation of concerns and dependency injection where appropriate.

---

## Bugs Fixed (Phase 1)

### 1. `failed_pages_count` never declared — `esi_markets.py:370`

`failed_pages_count += 1` referenced a variable that was never initialized. If JSON decoding failed during standard mode fetching, the entire run would crash with `NameError`. Fixed by using the existing `error_count` variable instead.

### 2. `input` vs `input()` — `file_cleanup.py:94`

```python
# Before (bug): compares function object to string — always False
if input == "y":

# After (fix): actually calls input() and captures the response
confirm = input("Are you sure you want to remove all but the latest file? (y/n)")
if confirm == "y":
```

The `latest_only` cleanup mode silently did nothing because this condition could never be true.

### 3. `merge_market_stats` called twice — `esi_markets.py:692-694`

```python
# Before (bug): first call does ESI /universe/names/ HTTP request, discards result
merge_market_stats(merged_sell_orders, historical_df)
final_data = merge_market_stats(merged_sell_orders, historical_df)

# After (fix): single call
final_data = merge_market_stats(merged_sell_orders, historical_df)
```

This doubled the SDE name lookup (an HTTP POST to ESI) for no reason, wasting time and API calls.

### 4. Test mode `max_pages` immediately overwritten — `esi_markets.py:201-206`

```python
max_pages = 3  # set for test mode
# ... then on first response:
if 'X-Pages' in response.headers:
    max_pages = int(response.headers['X-Pages'])  # overwrites to full count
```

Test mode was supposed to limit to 3 pages but immediately replaced that limit with the real page count from ESI. Fixed by not reading `X-Pages` in test mode.

### 5. Test code removed from production modules

`googlesheets_updater.py` contained `test_import_data()` and a `__main__` block with interactive debug code (hardcoded spreadsheet URLs, interactive sheet selection). Removed along with unused imports (`os`, `gspread.client.Client`).

---

## Architectural Issues

### Module-level side effects

Both `esi_markets.py` and `googlesheets_updater.py` execute config loading, validation, and `sys.exit()` at import time (module scope). This means:

- You cannot `import esi_markets` in a test or REPL without it running config checks and printing banners
- If config is missing when importing `googlesheets_updater`, the entire process exits
- Global mutable state makes it impossible to test modules in isolation

**Recommendation:** Move all initialization into functions. Use a config dataclass or dict passed as arguments rather than module-level globals.

### No separation of concerns

`esi_markets.py` is a 750-line file that handles:
- Configuration loading and validation
- OAuth coordination
- HTTP requests to ESI
- Data processing with pandas
- CSV file I/O
- Google Sheets orchestration
- File cleanup orchestration
- User interaction (input prompts)
- Progress display

**Recommendation:** Split into focused modules:
- `config.py` — Configuration loading, validation, dataclass
- `esi_client.py` — ESI HTTP client with auth, rate limiting, retries
- `market_data.py` — Data processing (aggregation, merging, SDE lookup)
- `export.py` — CSV and Google Sheets export
- `cli.py` — User interaction, argument parsing, progress display

### No dependency injection

Functions reach into global state for config values, logger instances, and API tokens. This creates tight coupling and makes testing impossible without mocking globals.

**Recommendation:** Pass dependencies explicitly. For example:

```python
# Instead of:
def fetch_market_orders_standard_mode():
    token = get_token(SCOPE)  # global SCOPE
    # uses global MARKET_STRUCTURE_URL, market_orders_wait_time, logger

# Use:
def fetch_market_orders(esi_client: ESIClient, structure_id: int, max_pages: int | None = None) -> list[dict]:
    ...
```

### Duplicated code

`fetch_market_orders_test_mode()` and `fetch_market_orders_standard_mode()` are ~90% identical. The only meaningful difference is max_pages limiting. These should be a single function with a `max_pages` parameter.

Similarly, `update_market_stats()`, `update_jita_prices()`, and `update_market_history()` in `googlesheets_updater.py` are nearly identical — read CSV, clean nulls, push to worksheet. This should be one function called three times with different arguments.

`ConfigurationError`, `print_setup_hint()`, and `load_config()` are duplicated between `esi_markets.py` and `googlesheets_updater.py`.

---

## Cross-Platform Issues

### All paths are relative to CWD

Every file path in the codebase (config, output, logs, tokens, credentials) is relative. The tool only works when run from the project root directory. If a Windows Task Scheduler job or cron entry launches from a different working directory, nothing will be found.

**Recommendation:** Resolve all paths relative to the project root (using `Path(__file__).parent`) or relative to the config file location. Support absolute paths and `~` expansion in config.

### Token and credentials in project root

`token.json` and Google credentials JSON live alongside source code. On Windows, if the project is in a read-protected location (Program Files), the tool can't write token files.

**Recommendation:** Use a user-writable location like `~/.esi-market/` or use `platformdirs` for OS-appropriate directories.

### `pyproject.toml` requires Python >= 3.13, README says 3.12

No 3.13-specific features are used. The actual minimum is 3.11 (for `tomllib`). This should be reconciled.

---

## Scheduling Blockers

The tool **cannot currently run unattended**. Multiple interactive `input()` calls block execution:

| Location | Call | Context |
|---|---|---|
| `esi_markets.py:121` | `input("run in configuration mode?")` | Every run (if prompt_config_mode=true) |
| `esi_markets.py:146` | `input("run in testing mode?")` | Configuration mode |
| `esi_markets.py:149` | `input("save output to CSV?")` | Test mode |
| `esi_markets.py:139` | `input("Press Enter to continue...")` | After showing config |
| `esi_markets.py:238` | `input("Press Enter to continue...")` | After test mode fetch failure |
| `esi_markets.py:360` | `input("Press Enter to continue...")` | After standard mode fetch failure |
| `esi_markets.py:492` | `input("Press Enter to continue...")` | After history fetch failure |
| `ESI_OAUTH_FLOW.py:85` | `input("Paste the full redirect URL here:")` | First auth / token expiry |
| `file_cleanup.py:93` | `input("Are you sure...?")` | latest_only cleanup mode |

**Recommendation:**
1. Add `argparse` CLI support with flags: `--headless`, `--mode standard|test`, `--output-dir PATH`, `--no-sheets`
2. In headless mode, skip all interactive prompts, use standard mode, always save CSV
3. On auth failure in headless mode, log a clear error and exit with non-zero status
4. Provide scheduling documentation for cron (Linux/Mac) and Task Scheduler (Windows)

---

## Output Path Configurability

`config.toml` defines output paths under `[paths.csv]`, but `esi_markets.py` ignores them and hardcodes:

```python
orders_filename = f"output/marketorders_{datetime.now().strftime(...)}.csv"
market_stats_filename = f"output/marketstats_{datetime.now().strftime(...)}.csv"
history_filename = f"output/markethistory_{datetime.now().strftime(...)}.csv"
```

The `[paths.csv]` config is only read by `googlesheets_updater.py` for finding the latest files.

**Recommendation:** Read an `output_dir` from config, derive all output paths from it, and pass it through to `file_cleanup.py`.

---

## OAuth Flow Accessibility

The current OAuth flow requires users to:
1. See a browser open automatically (good)
2. Log in and authorize (fine)
3. See a browser error page (localhost:8000 with nothing listening)
4. Manually copy the full URL from the browser address bar
5. Paste it into the terminal

This is the single biggest accessibility barrier for non-technical users. They see a "connection refused" error page and don't know to copy the URL.

**Recommendation:** Run a lightweight `http.server` callback handler that automatically captures the authorization code from the redirect. This is a standard pattern for desktop OAuth flows and eliminates the most confusing step entirely.

---

## Other Issues

### Noisy console output

The OAuth module prints 6-8 debug-style lines on every run (`opening ESI session...`, `opening Oauth session...SCOPE: [30 scopes]`, `loading token...`, `token expires at...`, `returning token`). For non-technical users this looks broken.

**Recommendation:** Move OAuth debug output behind the verbose logging flag. Only print user-facing messages.

### Overly broad OAuth scopes

`ESI_OAUTH_FLOW.py:27` requests 34 scopes when the tool only needs `esi-markets.structure_markets.v1`. This is likely left over from a more general-purpose tool.

**Recommendation:** The default scope should be just what's needed. The broad scope list can be available for other use cases but shouldn't be the default.

### Logging handler accumulation

`setup_logging()` adds new handlers every time it's called without checking if handlers already exist. If called multiple times (e.g., during imports), log output gets duplicated.

### `main.py` is a dead stub

`main.py` just prints "Hello from esimarket-tool!" and does nothing. The real entry point is `esi_markets.py:main()`. This file is confusing and should be removed or made the actual entry point.

---

## Recommended Refactoring Order

### Phase 2: Architecture refactoring

1. **Create `config.py`** — Single source of truth for configuration loading, validation, and a config dataclass. Eliminate duplicated config code from `esi_markets.py` and `googlesheets_updater.py`.

2. **Create `esi_client.py`** — ESI HTTP client encapsulating auth, headers, rate limiting, and retry logic. Accepts config via constructor (dependency injection). Consolidate the duplicated fetch functions into one.

3. **Create `cli.py`** — Entry point with `argparse`. Supports `--headless`, `--mode`, `--output-dir`, `--no-sheets`. Replaces all interactive `input()` calls with CLI flags.

4. **Refactor `esi_markets.py`** into `market_data.py` — Pure data processing (aggregation, merging, SDE lookups). No I/O, no config loading, no user interaction. Receives data and returns data.

5. **Refactor output handling** — `export.py` handles CSV writing and Google Sheets updates. Reads output directory from config. Consolidate duplicated Google Sheets update functions.

6. **Improve OAuth flow** — Add lightweight HTTP callback server. Move token storage to user config directory. Fail cleanly in headless mode.

7. **Add scheduling support** — Document cron/Task Scheduler setup. Consider built-in scheduling via `schedule` or `APScheduler` for users who don't want to configure OS-level scheduling.

8. **Fix path handling** — All paths resolved relative to project root or config file. Support absolute paths and `~` expansion. Use `pathlib.Path` consistently.

### Phase 3: Quality of life

9. **Clean up `main.py`** — Either make it the real entry point or remove it.
10. **Reconcile Python version requirement** — Set to `>=3.11` in pyproject.toml and README.
11. **Add proper error handling for SDE lookup** — `insert_SDE_data()` will crash if the ESI returns an error.
12. **Add type hints** throughout for IDE support and documentation.

---

## File-by-File Reference

| File | Lines | Purpose | Key Issues |
|---|---|---|---|
| `esi_markets.py` | 750 | Main orchestrator | Module-level side effects, duplicated fetch functions, hardcoded paths, interactive prompts |
| `setup.py` | 695 | Setup wizard TUI | Well-built, minor: doesn't configure output directory |
| `ESI_OAUTH_FLOW.py` | 115 | OAuth2 flow | No callback server, overly broad scopes, noisy output |
| `googlesheets_updater.py` | 208 | Google Sheets export | Module-level sys.exit, duplicated update functions, signature mismatch |
| `get_jita_prices.py` | 54 | Jita price fetching | Clean, small. Hardcoded region ID is fine for Jita. |
| `file_cleanup.py` | 102 | File management | Hardcoded folder structure, no configurable output dir |
| `logging_utils.py` | 49 | Logging setup | Handler accumulation on repeated calls |
| `main.py` | 7 | Dead stub | Does nothing useful |
