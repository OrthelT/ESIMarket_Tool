# Refactoring Log

Tracks progress of the architecture refactoring from the monolithic `esi_markets.py` into focused modules with dependency injection and CLI support.

**Branch:** `refactor-architecture`
**Plan:** See `docs/CODE_REVIEW.md` for the original review that motivated this work.

---

## Phase 2A: Config Foundation (COMPLETE)
**Commit:** `ef85855` — `refactor: extract config.py as single source of truth for configuration`

### What was done
- Created `config.py` with frozen dataclasses (`AppConfig`, `ESIConfig`, `ModeConfig`, etc.) mirroring the exact `config.toml` structure
- Factory function `load_config()` reads TOML and maps to dataclasses with defaults for missing keys
- Fixed `logging_utils.py` handler accumulation bug (duplicate log messages on repeated calls)
- Removed module-level `sys.exit()` and config loading from `esi_markets.py` (lines 72-78)
- Removed duplicated `ConfigurationError`, `print_setup_hint()`, `load_config()` from `googlesheets_updater.py`
- `update_all_google_sheets()` now accepts `AppConfig` parameter instead of loading its own config

### Key decisions
- Frozen dataclasses prevent accidental mutation of config after loading
- `project_root` defaults to the config file's parent directory, enabling correct path resolution from any working directory
- `setup.py` is unchanged — it reads/writes config.toml directly as a dict, not via `AppConfig`

---

## Phase 2B: ESI Client (COMPLETE)
**Commit:** `aa90ea7` — `refactor: extract esi_client.py and inject OAuth credentials`

### What was done
- Created `esi_client.py` with `ESIClient` class and `FetchResult` dataclass
- Merged `fetch_market_orders_test_mode()` and `fetch_market_orders_standard_mode()` into one `fetch_market_orders(max_pages=...)` method
- Added `progress_callback` parameter to enable silent headless operation
- `ESI_OAUTH_FLOW.py`: removed module-level `load_dotenv()` and `os.environ` reads; `get_token()` now accepts `client_id`, `secret_key` as explicit parameters
- `fetch_sde_names()` returns `dict[int, str]` with proper error handling (returns `{}` on failure)

### Key decisions
- `max_pages=3` for test mode, `max_pages=None` for standard — single function, no duplication
- `ESIClient` holds the token and config, each method gets what it needs from `self`
- SDE names use `requests.post(json=...)` instead of `data=str(list)` — proper JSON encoding

---

## Phase 2C: CLI + Module Split (COMPLETE)
**Commit:** `8f14c7c` — `refactor: add CLI with --headless support, split data processing and export`

### What was done
- Created `cli.py` with argparse: `--headless`, `--mode test|standard`, `--output-dir PATH`, `--no-sheets`
- Created `market_data.py`: pure data processing (no I/O, no globals, no network calls)
- Created `export.py`: all file I/O (CSV writing + Google Sheets updates)
- Slimmed `esi_markets.py` to a 16-line entry point delegating to `cli.main()`
- Updated `file_cleanup.py`: uses pathlib, removed blocking `input()` in `latest_only` mode
- Deleted `main.py` (dead stub)

### Key decisions
- Flag resolution order: `--headless` > `--mode` > `config.toml` `prompt_config_mode`
- `market_data.py` has zero project imports — can be used in Jupyter notebooks
- `export.py` consolidates three near-identical worksheet update functions into `_update_worksheet()`
- `pyproject.toml` entry point `mktstatus = "esi_markets:main"` still works via the thin wrapper

---

## Phase 2D: OAuth Callback Server (COMPLETE)
**Commit:** `0428181` — `feat: add OAuth callback server for automatic redirect capture`

### What was done
- Added `_OAuthCallbackHandler` (lightweight `http.server`) to `ESI_OAUTH_FLOW.py`
- Server captures the OAuth redirect and shows a "Authorization Successful!" HTML page
- Falls back to manual URL paste if server fails to start or times out (120s)
- Added `headless` parameter to `get_token()`: returns `None` instead of opening browser
- `cli.py` exits cleanly with helpful error message if no token in headless mode

### Key decisions
- Server handles exactly one request then shuts down (no resource leak)
- Daemon thread ensures the server doesn't block if the main process exits
- In headless mode, token refresh still works — only initial auth requires interactive mode

---

## Phase 2E: Path Handling + pyproject.toml (COMPLETE)
**Commit:** `46bc46e` — `refactor: fix path handling, clean pyproject.toml, add output dir config`

### What was done
- `config.py`: added `resolve_path()` method — expands `~`, resolves relative paths against `project_root`
- `pyproject.toml`: lowered `requires-python` to `>=3.11`, removed pinned transitive deps, removed `dotenv==0.9.9`
- `setup.py`: added "Output Directory" menu option
- `config.toml.example`: documented new `output_dir` setting
- `cli.py`: uses `config.resolve_path()` for output directory

### Key decisions
- Version bumped to `0.2.0` to reflect the architecture overhaul
- Only direct dependencies listed in pyproject.toml; `uv.lock` handles transitive pinning

---

## Phase 3: Polish (COMPLETE)
**Commit:** `1e67df6` — `chore: add type hints, scheduling docs, remove googlesheets_updater.py`

### What was done
- Added type hints to `get_jita_prices.py`
- Created `docs/SCHEDULING.md` with cron, systemd timer, and Windows Task Scheduler examples
- Deleted `googlesheets_updater.py` (absorbed into `export.py`)

---

## Final File Inventory

| File | Lines | Purpose |
|------|-------|---------|
| `config.py` | ~165 | Config dataclasses, loading, validation, path resolution |
| `esi_client.py` | ~240 | ESI HTTP client (orders, history, SDE names) |
| `cli.py` | ~280 | argparse CLI, main orchestration |
| `market_data.py` | ~90 | Pure data processing (pandas) |
| `export.py` | ~120 | CSV writing + Google Sheets updates |
| `ESI_OAUTH_FLOW.py` | ~205 | OAuth2 with HTTP callback server |
| `get_jita_prices.py` | ~60 | Jita price comparison (Fuzzworks API) |
| `file_cleanup.py` | ~110 | File management (pathlib) |
| `logging_utils.py` | ~48 | Logging setup with handler guard |
| `setup.py` | ~730 | TUI wizard (Rich) |
| `esi_markets.py` | ~16 | Thin entry point -> `cli.main()` |

**Removed:** `main.py`, `googlesheets_updater.py`

## Import Dependency Graph (no cycles)

```
cli.py -> config, esi_client, market_data, export, get_jita_prices, file_cleanup, logging_utils, ESI_OAUTH_FLOW
esi_client.py -> config
export.py -> config
market_data.py -> (pandas only)
get_jita_prices.py -> (pandas, requests only)
file_cleanup.py -> (pathlib only)
logging_utils.py -> (stdlib only)
ESI_OAUTH_FLOW.py -> (stdlib + requests_oauthlib only)
esi_markets.py -> cli (thin re-export)
setup.py -> (standalone, reads/writes config files directly)
```

## Handoff Notes for Next Claude Instance

1. **All 6 phases are complete.** The refactoring is fully implemented on `refactor-architecture`.
2. **Not tested against live ESI** — the tool can't be end-to-end tested without Eve Online credentials and a live server. The module structure, imports, CLI parsing, and config loading have all been verified.
3. **setup.py save_config() now writes `[paths]` section** with `output_dir`. Ensure any manual edits to config.toml include this if needed.
4. **The `googlesheets_updater.py` file is deleted.** If old code references it, update to import from `export.py` instead.
5. **PR to main is the next step.** Run `git log --oneline main..HEAD` to see all commits for the PR description.
