# Buyer walkthrough

## 1. What problem does this solve?
A finance analyst needs to know whether the data required for analysis is accessible, present, and recent enough. This pipeline checks those conditions for company facts and economic data, then provides a report with traceable source responses.

## 2. Data flow
Configuration -> demo generator or live HTTP request -> raw JSON snapshot -> normalization -> SQLite -> availability checks -> CSV/JSON/report.
Each execution has a unique run ID. Results are appended to the database. Export files show the latest execution. Demo and live directories are separate by default.

## 3. What each code function does
- `get_json`: requests JSON with a timeout and up to three attempts for temporary errors. Error messages exclude URLs so an API key is not logged.
- `fetch`: builds a SEC request or a paginated FRED request. Credentials come from environment variables. SEC requests are sequential with a short pause.
- `demo_payload`: produces fictional examples in the expected API response shapes, relative to the run date.
- `numeric`: handles missing values and rejects NaN/infinity.
- `normalize`: extracts selected facts into common fields, validates dates, removes exact duplicates, and retains distinct filing/period contexts.
- `assess`: evaluates each configured metric's available values, age, nulls, and future dates.
- `connect`: creates SQLite tables if needed without deleting history.
- `run`: coordinates fetching, persistence, checks, and reports. Source failures are isolated so other sources can complete.
- `dashboard`: makes the searchable offline HTML report and escapes source text.
- `main`: parses command-line options and returns an error code when a download fails.

## 4. Run it on Windows
Install Python 3.10+ if necessary. Extract the ZIP. Open the project folder in File Explorer, type `cmd` in its address bar, and press Enter.

```bat
py pipeline.py
py -m unittest discover -s tests -v
start output\demo\dashboard.html
```

For live mode, use the PowerShell environment-variable commands in README.md, in a PowerShell window opened in the project folder. Replace the placeholder key/email. Environment variables set there apply to that session only. The application does not automatically read `.env` files.

## 5. Understand the demonstration
The fixed demonstration run produces eight checks: five healthy, one missing company metric, one stale interest-rate series, and one FX warning caused by a null value. There are 25 normalized observations across four successful fictional source responses. These examples are educational, not assertions about actual companies or providers.

## 6. Work with SQL
Open `output/demo/availability.sqlite` using a SQLite tool, or use Python's built-in module:

```python
import sqlite3
with sqlite3.connect('output/demo/availability.sqlite') as db:
    for row in db.execute('SELECT source, metric, status, latest FROM checks'):
        print(row)
```

`runs` stores execution identity, mode, as-of date and the configuration used. `fetches` records success/failure and raw response hashes. `observations` stores common fact fields. `checks` stores each metric's monitoring result. Use `run_id` to restrict a query to one execution; otherwise a query includes history. See `sql/monitoring.sql`.

## 7. Add companies or indicators
Edit `config.json`. Each source must have a unique safe ID (letters, digits, underscores), a kind, and a positive age threshold. For SEC sources use the official 10-digit CIK and supported US-GAAP tag names. This version reads USD facts only. For FRED use a series identifier and its actual unit. Confirm the series frequency before choosing the age threshold.

For example, change `max_age_days` from 7 to 10 for a more tolerant FX freshness check. Rerun the pipeline. Configuration is saved with each run so old checks remain explainable.

Demo scenarios are intentionally tied to the initial configuration. Newly added source IDs will need corresponding fixture changes if you want custom demo anomalies.

## 8. Refresh and schedule
Run the same command again to collect another snapshot. No automatic schedule is installed. For Windows Task Scheduler, choose your Python executable as the program, use `pipeline.py --mode live` as the arguments, and set Start in to the project folder. Configure the environment variables for the account running the task. Start with one daily task. Keep credentials out of task arguments and public logs.

Raw snapshots and database history grow over time; this prototype does not automatically delete them. Archive old output directories when needed. Do not run concurrent jobs against the same output directory because latest-export files may race.

## 9. Troubleshooting
- Missing `FRED_API_KEY`: set a registered key in the same shell as the command.
- SEC identity error: set `SEC_USER_AGENT` with your application name and contact email.
- HTTP 403: review provider access requirements and your network; do not bypass restrictions.
- HTTP 429: reduce scheduling frequency and retry later.
- Invalid source response: inspect the retained raw JSON and compare it with the source documentation.
- Missing metric: verify its tag, unit, and whether the company reports that concept. Do not substitute zero.
- A stale period may reflect a normal reporting schedule. Adjust thresholds only after reviewing the source cadence.

## 10. How to explain it confidently
“This project uses Python to collect selected company financial facts and macroeconomic observations, preserves raw source snapshots, and loads normalized records into SQLite. It monitors metric coverage, missing values and observation freshness. A report separates retrieval failures from data-quality warnings, and each run remains traceable through its run ID and source hashes.”

Avoid claiming that it predicts markets, performs a tax audit, guarantees complete financial statements, or measures continuous provider uptime. It is a local portfolio prototype with live connectors that require a successful client-side live run before claiming live verification.
