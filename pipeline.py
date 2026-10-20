"""Financial availability monitor. Python 3.10+, standard library only."""
import argparse
import csv
import hashlib
import html
import json
import math
import os
import re
from pathlib import Path
import sqlite3
import time
from datetime import date, datetime, timedelta, timezone
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError
import uuid

ROOT = Path(__file__).resolve().parent


def get_json(url, headers=None):
    """Bounded retries. Never expose credential-bearing URLs in errors."""
    for attempt in range(3):
        try:
            with urlopen(Request(url, headers=headers or {}), timeout=30) as response:
                return json.load(response)
        except HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise RuntimeError(f'HTTP {exc.code}') from None
        except (URLError, TimeoutError):
            if attempt == 2:
                raise RuntimeError('Network unavailable or timed out') from None
        time.sleep(2 ** attempt)


def numeric(value):
    if value in (None, '', '.'):
        return None
    n = float(value)
    if not math.isfinite(n):
        raise ValueError('Non-finite numeric value')
    return n


def normalize(payload, source):
    """Retain SEC periods/accessions; never combine annual and quarterly facts."""
    rows = []
    if source['kind'] == 'sec':
        facts = payload['facts'].get('us-gaap', {})
        for metric in source['metrics']:
            for fact in facts.get(metric, {}).get('units', {}).get('USD', []):
                if fact.get('form') not in ('10-K', '10-Q', '10-K/A', '10-Q/A'):
                    continue
                rows.append(dict(metric=metric, start=fact.get('start', ''), end=fact['end'],
                                 value=numeric(fact.get('val')), unit='USD',
                                 filed=fact.get('filed', ''), accession=fact.get('accn', ''),
                                 form=fact.get('form', '')))
    else:
        for obs in payload['observations']:
            rows.append(dict(metric=source['series'], start='', end=obs['date'],
                             value=numeric(obs['value']), unit=source['unit'],
                             filed='', accession='', form=''))
    for row in rows:
        date.fromisoformat(row['end'])
        if row['start']:
            date.fromisoformat(row['start'])
        if row['filed']:
            date.fromisoformat(row['filed'])
    # Exact duplicates collapse, but distinct filings and periods remain.
    return list({json.dumps(r, sort_keys=True): r for r in rows}.values())


def assess(rows, source, as_of):
    expected = source.get('metrics', [source.get('series')])
    results = []
    for metric in expected:
        selected = [r for r in rows if r['metric'] == metric]
        usable = [r for r in selected if r['value'] is not None and r['end'] <= as_of.isoformat()]
        latest = max((r['end'] for r in usable), default='')
        age = (as_of - date.fromisoformat(latest)).days if latest else None
        missing = sum(r['value'] is None for r in selected)
        future = sum(r['end'] > as_of.isoformat() for r in selected)
        status = ('missing' if not usable else 'stale' if age > source['max_age_days']
                  else 'warning' if missing or future else 'healthy')
        results.append(dict(source=source['id'], metric=metric, status=status,
                            latest=latest, age_days=age, max_age_days=source['max_age_days'],
                            records=len(selected), missing_values=missing, future_dates=future))
    return results


def fetch(source):
    if source['kind'] == 'sec':
        agent = os.environ.get('SEC_USER_AGENT', '')
        if '@' not in agent:
            raise RuntimeError('Set SEC_USER_AGENT to your application name and contact email')
        time.sleep(0.25)
        return get_json('https://data.sec.gov/api/xbrl/companyfacts/CIK' + source['cik'] + '.json',
                        {'User-Agent': agent, 'Accept': 'application/json'})
    key = os.environ.get('FRED_API_KEY', '')
    if not key:
        raise RuntimeError('Set FRED_API_KEY to your registered FRED API key')
    all_rows = []
    offset = 0
    while True:
        query = urlencode(dict(series_id=source['series'], api_key=key, file_type='json',
                               observation_start='2020-01-01', limit=100000, offset=offset))
        payload = get_json('https://api.stlouisfed.org/fred/series/observations?' + query)
        batch = payload['observations']
        all_rows.extend(batch)
        offset += len(batch)
        if offset >= int(payload.get('count', offset)):
            return {'observations': all_rows}
        if not batch:
            raise ValueError('Incomplete paginated response')


def demo_payload(source, as_of):
    """Fictional values in provider-shaped fixtures, not actual company results."""
    if source['kind'] == 'sec':
        facts = {}
        for i, metric in enumerate(source['metrics']):
            # One missing metric demonstrates coverage monitoring.
            if source['id'] == 'sec_msft' and metric == 'NetIncomeLoss':
                continue
            end = (as_of - timedelta(days=80)).isoformat()
            facts[metric] = {'units': {'USD': [dict(end=end, val=1000000*(i+1),
                              filed=(as_of-timedelta(days=30)).isoformat(),
                              form='10-Q', accn='DEMO-ONLY',
                              **({'start': (as_of-timedelta(days=170)).isoformat()}
                                 if metric != 'Assets' else {}))]}}
        return {'facts': {'us-gaap': facts}, 'demo': True}
    stale = source['series'] == 'FEDFUNDS'
    rows = [dict(date=(as_of-timedelta(days=(100 if stale else 1)+i)).isoformat(),
                 value=str(1.05+i/1000) if source['series']=='DEXUSEU' else '4.0') for i in range(10)]
    if not stale:
        rows[-1]['value'] = '.'
    return {'observations': rows, 'demo': True}


def connect(path):
    db = sqlite3.connect(path)
    db.executescript('''
    CREATE TABLE IF NOT EXISTS runs(run_id TEXT PRIMARY KEY, started TEXT, mode TEXT, as_of TEXT, config_json TEXT);
    CREATE TABLE IF NOT EXISTS fetches(run_id TEXT, source TEXT, status TEXT, error TEXT, sha256 TEXT, raw_path TEXT, PRIMARY KEY(run_id,source));
    CREATE TABLE IF NOT EXISTS observations(run_id TEXT, source TEXT, metric TEXT, start TEXT, end TEXT, value REAL, unit TEXT, filed TEXT, accession TEXT, form TEXT);
    CREATE TABLE IF NOT EXISTS checks(run_id TEXT, source TEXT, metric TEXT, status TEXT, latest TEXT, age_days INTEGER, max_age_days INTEGER, records INTEGER, missing_values INTEGER, future_dates INTEGER);
    CREATE INDEX IF NOT EXISTS observations_lookup ON observations(source,metric,end);
    ''')
    return db


def dashboard(checks, fetches, mode, as_of, run_id):
    esc = lambda x: html.escape(str(x if x is not None else '—'))
    body = ''.join('<tr>'+''.join('<td>'+esc(r[k])+'</td>' for k in
                   ('source','metric','status','latest','age_days','records','missing_values'))+'</tr>' for r in checks)
    failures = ''.join('<li>'+esc(f['source'])+': '+esc(f['error'])+'</li>' for f in fetches if f['status']=='failed')
    counts = {s: sum(r['status']==s for r in checks) for s in ('healthy','warning','stale','missing')}
    cards = ''.join(f'<article><strong>{n}</strong><span>{s}</span></article>' for s,n in counts.items())
    return '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Financial Data Availability</title><style>
    body{font:16px system-ui;background:#f3f6fb;color:#14283e;margin:0}main{max-width:1150px;margin:auto;padding:36px 24px}
    h1{font-size:36px;letter-spacing:-1px}header{border-left:5px solid #0c847d;padding-left:20px}small{color:#4b6073}
    .cards{display:flex;gap:16px;flex-wrap:wrap;margin:28px 0}article{background:white;border:1px solid #dde5ee;padding:22px;flex:1;min-width:100px;border-radius:12px}
    strong{display:block;font-size:36px;color:#087e79}span{text-transform:uppercase;font-size:12px;letter-spacing:2px}
    .table{overflow:auto;background:white;border-radius:12px}table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:16px;text-align:left;border-bottom:1px solid #e7edf3}
    th{background:#14283e;color:white}input{padding:12px;margin:12px 0;width:280px;max-width:90%;border:1px solid #b9c8d8;border-radius:6px}
    .note{padding:16px;background:#e2efee;border-radius:8px;line-height:1.6}footer{margin-top:24px;color:#516579;font-size:13px}</style><main>
    <header><small>DATA ENGINEERING / SOURCE MONITOR</small><h1>Financial Data Availability</h1><p>Company financials · Exchange rates · Interest rates</p></header>''' + \
    f'<p class="note">{esc(mode.upper())} mode · As of {esc(as_of)}. '+ \
    ('All values are fictional demonstration data.' if mode=='demo' else 'Live source results; inspect any fetch failures below.') + \
    '</p><div class="cards">'+cards+'</div><h2>Coverage and freshness</h2><label>Filter checks <input id="q" placeholder="Search source, metric or status"></label><div class="table"><table><thead><tr>'+ \
    ''.join('<th>'+x+'</th>' for x in ['Source','Metric','Status','Latest period','Age (days)','Records','Missing values'])+ \
    '</tr></thead><tbody id="rows">'+body+'</tbody></table></div><h2>Download failures</h2><ul>'+ \
    (failures or '<li>None in this run.</li>')+'</ul><footer>Run '+esc(run_id)+ \
    ' · Freshness measures observation/period-end age, not website uptime. Thresholds are configurable heuristics. No investment or tax conclusions.</footer></main>'+ \
    '<script>document.getElementById("q").addEventListener("input",e=>{for(const r of document.querySelectorAll("#rows tr"))r.hidden=!r.textContent.toLowerCase().includes(e.target.value.toLowerCase())});</script></html>'


def run(mode='demo', output=None, config=None, as_of=None):
    config = config or json.loads((ROOT/'config.json').read_text())
    ids = set()
    for source in config['sources']:
        sid = source['id']
        if not re.fullmatch(r'[A-Za-z0-9_]+', sid) or sid in ids:
            raise ValueError('Source IDs must be unique letters, digits, or underscores')
        ids.add(sid)
        if source['kind'] not in ('sec', 'fred') or source['max_age_days'] <= 0:
            raise ValueError('Invalid source kind or freshness threshold')
        if source['kind'] == 'sec' and not re.fullmatch(r'[0-9]{10}', source['cik']):
            raise ValueError('SEC CIK must contain exactly ten digits')
    as_of = as_of or date.today()
    output = Path(output or ROOT/'output'/mode)
    output.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]
    raw_dir = output/'raw'/run_id
    raw_dir.mkdir(parents=True)
    checks, fetches = [], []
    with connect(output/'availability.sqlite') as db:
        db.execute('INSERT INTO runs VALUES(?,?,?,?,?)', (run_id,datetime.now(timezone.utc).isoformat(),mode,as_of.isoformat(),json.dumps(config)))
        for source in config['sources']:
            record = dict(source=source['id'], status='success', error='', sha256='', raw_path='')
            try:
                payload = demo_payload(source,as_of) if mode=='demo' else fetch(source)
                raw = json.dumps(payload,sort_keys=True).encode()
                path = raw_dir/(source['id']+'.json')
                path.write_bytes(raw)
                record.update(sha256=hashlib.sha256(raw).hexdigest(),raw_path=str(path.relative_to(output)))
                rows = normalize(payload,source)
                db.executemany('INSERT INTO observations VALUES(?,?,?,?,?,?,?,?,?,?)',
                    [(run_id,source['id'],r['metric'],r['start'],r['end'],r['value'],r['unit'],r['filed'],r['accession'],r['form']) for r in rows])
                checks.extend(assess(rows,source,as_of))
            except (RuntimeError,ValueError,KeyError,TypeError) as exc:
                record.update(status='failed',error=str(exc) if isinstance(exc,RuntimeError) else 'Invalid source response: '+type(exc).__name__)
            fetches.append(record)
            db.execute('INSERT INTO fetches VALUES(?,?,?,?,?,?)',(run_id,record['source'],record['status'],record['error'],record['sha256'],record['raw_path']))
        db.executemany('INSERT INTO checks VALUES(?,?,?,?,?,?,?,?,?,?)',
                       [(run_id,*r.values()) for r in checks])
    with (output/'checks.csv').open('w',newline='',encoding='utf-8') as f:
        fields=['source','metric','status','latest','age_days','max_age_days','records','missing_values','future_dates']
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(checks)
    summary=dict(run_id=run_id,mode=mode,as_of=as_of.isoformat(),checks=checks,fetches=fetches)
    (output/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    (output/'dashboard.html').write_text(dashboard(checks,fetches,mode,as_of,run_id),encoding='utf-8')
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',choices=['demo','live'],default='demo')
    p.add_argument('--output',type=Path)
    p.add_argument('--config',type=Path,default=ROOT/'config.json')
    p.add_argument('--as-of',type=date.fromisoformat)
    a=p.parse_args()
    result=run(a.mode,a.output,json.loads(a.config.read_text()),a.as_of)
    failures=sum(f['status']=='failed' for f in result['fetches'])
    print(f"Run {result['run_id']}: {len(result['checks'])} checks; {failures} source failures.")
    print('Open dashboard.html in the output directory.')
    return 1 if failures else 0

if __name__=='__main__':
    raise SystemExit(main())
