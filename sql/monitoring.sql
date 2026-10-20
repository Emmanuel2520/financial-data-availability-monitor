-- Latest completed run, not all historical checks.
SELECT source, metric, status, latest, age_days, missing_values
FROM checks
WHERE run_id = (SELECT run_id FROM runs ORDER BY started DESC LIMIT 1);

-- Retrieval failures over history.
SELECT r.started, r.mode, f.source, f.error
FROM fetches f JOIN runs r USING(run_id)
WHERE f.status = 'failed' ORDER BY r.started DESC;

-- Historical successful-fetch ratio: sampled executions, not continuous uptime.
SELECT source, COUNT(*) AS attempts,
       ROUND(100.0 * SUM(status = 'success') / COUNT(*), 2) AS success_percent
FROM fetches JOIN runs USING(run_id)
WHERE mode = 'live' GROUP BY source;

-- Financial contexts stay distinct; inspect before comparing or aggregating.
SELECT source, metric, start, end, value, unit, filed, accession, form
FROM observations WHERE source LIKE 'sec_%'
AND run_id = (SELECT run_id FROM runs ORDER BY started DESC LIMIT 1)
ORDER BY source, metric, end DESC;
