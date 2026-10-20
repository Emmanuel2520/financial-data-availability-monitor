# Validation record — v0.1

Validated on 2026-10-20 with Python 3.12 in the build environment.

- Offline command completed: `python pipeline.py --as-of 2026-10-20`.
- 8 checks: 5 healthy, 1 warning, 1 stale, 1 missing.
- 4 successful synthetic responses and 25 normalized observations.
- 12 automated tests passed: demo execution, repeated-run history, source-failure isolation, missing values, future dates, freshness boundaries, non-finite numbers, distinct SEC contexts, missing credentials, invalid dates, HTML escaping, and FRED pagination.
- Live SEC and authenticated FRED retrieval have not been verified in this environment. Provider-shaped fixtures and mocked pagination verify code paths; they do not prove live connectivity.

The project is a portfolio prototype. Client acceptance should include a live run with their own API key and SEC identity, and review of thresholds and metric definitions.
