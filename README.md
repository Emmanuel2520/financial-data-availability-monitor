# Financial Data Availability & Monitoring Pipeline

A Python and SQL portfolio project for monitoring access, coverage, and freshness of selected company financial statement data and economic indicators.

## Start here

Requires Python 3.10 or later. No third-party packages required.
Extract the ZIP, open this folder in a terminal, and run:

```bash
python pipeline.py
python -m unittest discover -s tests -v
```

On Windows, use `py` if `python` is not recognized. On macOS/Linux use `python3` if needed.
Open `output/demo/dashboard.html` in a browser. There is no server to start.
The included `examples/dashboard.html` is a ready-to-open demonstration.

Demo mode uses fictional provider-shaped data, including deliberate missing and stale examples. It makes no external requests. It is NOT actual Apple, Microsoft, or economic data.

## Coverage

| Category | Live source | Initial selection |
|---|---|---|
| Company financials | SEC Company Facts | Apple and Microsoft: assets, net income, operating cash flow |
| Exchange rates | FRED | DEXUSEU: US dollars per euro |
| Interest rates | FRED | FEDFUNDS: monthly federal funds effective rate |

This monitors selected financial statement facts, not complete reconstructed financial statements. Period starts, ends, filing dates, accession numbers and units are retained; annual, quarterly and year-to-date values must not be summed indiscriminately.

## Live mode

Obtain your own FRED API key and provide a descriptive SEC application/contact identity. Do not put credentials in code or GitHub.
PowerShell (replace the placeholders):

```powershell
$env:SEC_USER_AGENT="FinancialAvailability YourName your-email@example.com"
$env:FRED_API_KEY="YOUR_REGISTERED_FRED_KEY"
py pipeline.py --mode live
```

macOS/Linux:

```bash
export SEC_USER_AGENT='FinancialAvailability YourName your-email@example.com'
export FRED_API_KEY='YOUR_REGISTERED_FRED_KEY'
python3 pipeline.py --mode live
```

Open `output/live/dashboard.html`. Live access depends on the source, your network, and valid configuration. The submitted build was tested offline; authenticated live FRED retrieval has not been verified with a real key. SEC live retrieval has not been verified from this environment. No demo fallback is used in live mode.

## Outputs

Each mode has its own directory by default:
- `availability.sqlite`: runs, download outcomes, observations, and checks; history retained.
- `raw/<run-id>/`: source response snapshots; SHA-256 hashes recorded in the database.
- `summary.json` and `checks.csv`: latest run results.
- `dashboard.html`: searchable offline monitoring report.

A failed fetch is listed separately from successful checks. A dashboard with zero checks and download failures is not a healthy run. The command returns exit code 1 when any source fails; stale/missing warnings alone return 0.

## Checks

Healthy means a configured metric has a non-null observation within its age threshold. Missing means no usable observations for that metric. Stale means the latest usable period/observation is older than the threshold. Warning means a current metric also contains null values or future observation dates. Legitimate holidays may create FRED nulls; investigate warnings before treating them as defects.

Freshness is measured against observation/period-end dates, not filing dates or fetch time. Defaults: company facts 150 calendar days; FX 7; monthly rates 75. These are portfolio heuristics, not release-calendar SLAs. The monitor detects missing configured metrics and explicit null observations; it does not infer every omitted date or reconstruct missing financial periods.

## Update and explain

Read [the walkthrough](docs/WALKTHROUGH.md) for code flow, SQL, configuration, scheduling, and troubleshooting. Read [source documentation](docs/SOURCES.md) for official references.

Suggested repository name: `financial-data-availability-monitor`.
Upload this folder's contents, including `.gitignore`; exclude locally generated `output/` and credentials. A GitHub upload alone does not run the pipeline.
