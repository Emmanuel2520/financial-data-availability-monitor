import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from datetime import date
import pipeline as p

class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.config=json.loads((p.ROOT/'config.json').read_text())
        self.today=date(2026,10,20)
        self.fx=self.config['sources'][2]

    def test_demo_end_to_end(self):
        with tempfile.TemporaryDirectory() as d:
            result=p.run(output=d,as_of=self.today)
            counts={s:sum(c['status']==s for c in result['checks']) for s in ['healthy','missing','stale','warning']}
            self.assertEqual(counts,dict(healthy=5,missing=1,stale=1,warning=1))
            self.assertIn('fictional',Path(d,'dashboard.html').read_text())
            self.assertTrue(all(f['sha256'] for f in result['fetches']))

    def test_repeat_runs_preserve_history(self):
        with tempfile.TemporaryDirectory() as d:
            p.run(output=d,as_of=self.today); p.run(output=d,as_of=self.today)
            with sqlite3.connect(Path(d,'availability.sqlite')) as db:
                self.assertEqual(db.execute('select count(*) from runs').fetchone()[0],2)
                self.assertEqual(db.execute('select count(*) from observations').fetchone()[0],50)

    def test_failed_live_fetch_is_not_stale_success(self):
        with tempfile.TemporaryDirectory() as d, patch.object(p,'fetch',side_effect=RuntimeError('HTTP 503')):
            p.run(output=d,as_of=self.today)
            r=p.run(mode='live',output=d,as_of=self.today)
            self.assertEqual(r['checks'],[])
            self.assertEqual(len([f for f in r['fetches'] if f['status']=='failed']),4)
            self.assertIn('HTTP 503',Path(d,'dashboard.html').read_text())

    def test_missing_fred_value(self):
        rows=p.normalize({'observations':[{'date':'2026-10-19','value':'.'}]},self.fx)
        self.assertIsNone(rows[0]['value'])
        self.assertEqual(p.assess(rows,self.fx,self.today)[0]['status'],'missing')

    def test_future_value_not_healthy(self):
        rows=p.normalize({'observations':[{'date':'2027-10-19','value':'1.2'}]},self.fx)
        self.assertEqual(p.assess(rows,self.fx,self.today)[0]['status'],'missing')

    def test_stale_boundary(self):
        rows=p.normalize({'observations':[{'date':'2026-10-13','value':'1.2'}]},self.fx)
        self.assertEqual(p.assess(rows,self.fx,self.today)[0]['status'],'healthy')
        self.assertEqual(p.assess(rows,self.fx,date(2026,10,21))[0]['status'],'stale')

    def test_nonfinite_rejected(self):
        for v in ['NaN','Infinity','-Infinity']:
            with self.assertRaises(ValueError): p.numeric(v)

    def test_sec_distinct_periods_and_amendments_retained(self):
        s=self.config['sources'][0]
        base=dict(end='2026-06-30',val=10,form='10-Q',accn='a',filed='2026-07-20')
        payload={'facts':{'us-gaap':{'NetIncomeLoss':{'units':{'USD':[
            dict(base,start='2026-01-01'),dict(base,start='2026-04-01'),
            dict(base,start='2026-04-01',accn='b',form='10-Q/A'),dict(base,start='2026-01-01')]}}}}}
        self.assertEqual(len(p.normalize(payload,s)),3)

    def test_missing_credentials_safe(self):
        with patch.dict('os.environ',{},clear=True):
            with self.assertRaisesRegex(RuntimeError,'FRED_API_KEY'): p.fetch(self.fx)
            with self.assertRaisesRegex(RuntimeError,'SEC_USER_AGENT'): p.fetch(self.config['sources'][0])

    def test_invalid_date_rejected(self):
        with self.assertRaises(ValueError):
            p.normalize({'observations':[{'date':'bad','value':'1'}]},self.fx)

    def test_dashboard_escapes_source_text(self):
        text=p.dashboard([], [{'source':'<script>x</script>','status':'failed','error':'<b>x</b>'}], 'demo',self.today,'x')
        self.assertIn('&lt;script&gt;',text)
        self.assertNotIn('<b>x</b>',text)

    def test_fred_pagination(self):
        with patch.dict('os.environ',{'FRED_API_KEY':'test'}), patch.object(p,'get_json',side_effect=[
             {'count':2,'observations':[{'date':'2026-01-01','value':'1'}]},
             {'count':2,'observations':[{'date':'2026-01-02','value':'2'}]}]):
            self.assertEqual(len(p.fetch(self.fx)['observations']),2)

if __name__=='__main__': unittest.main()
