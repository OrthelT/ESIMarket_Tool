# Scheduling ESI Market Tool

Run the tool automatically on a schedule using `--headless` mode.

## Prerequisites

1. Complete initial setup: `uv run python setup.py`
2. Run the tool interactively once to create `token.json` (OAuth token):
   ```bash
   uv run python esi_markets.py
   ```
3. Verify headless mode works:
   ```bash
   uv run python esi_markets.py --headless --no-sheets
   ```

The OAuth token auto-refreshes, so once `token.json` exists, headless runs will
refresh it automatically. If the refresh token expires (rare), you'll need to run
interactively again.

## Linux / macOS (cron)

Edit your crontab:
```bash
crontab -e
```

Run every 6 hours:
```cron
0 */6 * * * cd /path/to/esi-market-tool && uv run python esi_markets.py --headless >> logs/cron.log 2>&1
```

Run daily at 08:00 UTC, skip Google Sheets:
```cron
0 8 * * * cd /path/to/esi-market-tool && uv run python esi_markets.py --headless --no-sheets >> logs/cron.log 2>&1
```

Run with a custom output directory:
```cron
0 12 * * * cd /path/to/esi-market-tool && uv run python esi_markets.py --headless --output-dir ~/market-data >> logs/cron.log 2>&1
```

## Linux (systemd timer)

Create `/etc/systemd/user/esi-market.service`:
```ini
[Unit]
Description=ESI Market Tool data fetch

[Service]
Type=oneshot
WorkingDirectory=/path/to/esi-market-tool
ExecStart=/path/to/esi-market-tool/.venv/bin/python esi_markets.py --headless
```

Create `/etc/systemd/user/esi-market.timer`:
```ini
[Unit]
Description=Run ESI Market Tool every 6 hours

[Timer]
OnCalendar=*-*-* 00/6:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

Enable:
```bash
systemctl --user enable --now esi-market.timer
```

## Windows (Task Scheduler)

1. Open Task Scheduler (`taskschd.msc`)
2. Create Basic Task:
   - **Name:** ESI Market Tool
   - **Trigger:** Daily (or your preferred schedule)
   - **Action:** Start a program
   - **Program:** `cmd.exe`
   - **Arguments:** `/c cd /d C:\path\to\esi-market-tool && uv run python esi_markets.py --headless`
   - **Start in:** `C:\path\to\esi-market-tool`

## CLI Flags Reference

| Flag | Description |
|------|-------------|
| `--headless` | No prompts, standard mode, always save CSV |
| `--mode test` | Use test mode (3 pages only) |
| `--mode standard` | Use standard mode (all pages) |
| `--output-dir PATH` | Override output directory |
| `--no-sheets` | Skip Google Sheets update |

Flags can be combined:
```bash
uv run python esi_markets.py --headless --no-sheets --output-dir /data/eve
```

## Troubleshooting

**"Authentication failed. In headless mode, a valid token.json must exist."**
Run the tool interactively once to complete OAuth: `uv run python esi_markets.py`

**Token refresh fails**
Delete `token.json` and run interactively to re-authorize.

**Output files not appearing**
Check the `--output-dir` path exists and is writable. Default is `output/` in the project directory.
