"""Offline tests with explicitly artificial responses, never experiment results."""
import argparse
import csv
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))
import build
import experiment as ex


class ControlledExperimentTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.p=Path(self.tmp.name);self.cases,self.manifest=ex.assets();self.byid={c['case_id']:c for c in self.cases}
        mapping=ex.read_json(HERE/'review_map.json')
        for name in ['emma','vivianne']:
            rows=list(csv.DictReader(io.StringIO((HERE/'review'/f'{name}.csv').read_text())))
            for row in rows:
                c=self.byid[mapping[name][row['review_id']]]
                row.update(topic_match='YES',content_support='YES' if c['variant']=='substantive' else 'NO',
                           label='supported' if c['variant']=='substantive' else 'unverifiable',notes='ARTIFICIAL TEST FIXTURE')
            with (self.p/f'{name}.csv').open('w',newline='') as f:
                w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
        self.lock=self.p/'lock.json'
        with redirect_stdout(io.StringIO()):ex.review(argparse.Namespace(emma=self.p/'emma.csv',vivianne=self.p/'vivianne.csv',output=self.lock))

    def fixture_predictions(self):
        jobs=ex.make_jobs('fixture-model','test',self.lock);rows=[]
        for j in jobs:
            c=self.byid[j['case_id']];condition=j['condition']
            label='supported' if c['variant']=='substantive' or (condition=='baseline' and c['variant']=='adjacent_measure') else 'unverifiable'
            raw=label.upper() if condition=='baseline' else json.dumps({'label':label,'evidence_span':c['context'] if label=='supported' else '', 'describes':'target' if label=='supported' else 'no_substantive_description'})
            rows.append({**{k:v for k,v in j.items() if k!='prompt'},'raw_response':raw,'status':'ok','backend':'offline-test-fixture','endpoint':'none'})
        return rows

    def analyze(self,rows):
        predictions=self.p/'predictions.jsonl';predictions.write_text('\n'.join(json.dumps(r) for r in rows)+'\n')
        output=self.p/'analysis.json'
        with redirect_stdout(io.StringIO()):ex.analyze(argparse.Namespace(predictions=predictions,review_lock=self.lock,split='test',output=output,resamples=100,seed=1))
        return ex.read_json(output)

    def test_frozen_assets_and_split_groups(self):
        for name,data in build.artifacts().items():self.assertEqual((HERE/name).read_bytes(),data,name)
        self.assertEqual(len(self.cases),90)
        for pair in {c['pair_id'] for c in self.cases}:
            rows=[c for c in self.cases if c['pair_id']==pair]
            self.assertEqual(len(rows),6);self.assertEqual(len({c['split'] for c in rows}),1)
        self.assertEqual(sum(c['split']=='test' for c in self.cases),72)

    def test_human_labels_required_no_intended_gold(self):
        with self.assertRaises(ValueError):ex.read_review(HERE/'review/emma.csv','emma',self.cases,ex.read_json(HERE/'review_map.json')['emma'])
        with self.assertRaises(ValueError):ex.make_jobs('fixture','test')
        self.assertTrue(all('gold' not in c and 'expected_label' not in c for c in self.cases))

    def test_known_paired_metrics_and_cluster_count(self):
        out=self.analyze(self.fixture_predictions());primary=out['references']['reviewer_agreement']
        self.assertEqual(out['total_cases'],72)
        self.assertEqual(primary['overall']['baseline']['false_support_rate'],.5)
        self.assertEqual(primary['overall']['intervention']['false_support_rate'],0)
        self.assertEqual(primary['overall']['intervention']['support_retention'],1)
        self.assertEqual(primary['paired']['clusters'],12)
        self.assertEqual(primary['paired']['metrics']['false_support_rate']['ci95'],[-.5,-.5])

    def test_disagreement_excluded_only_from_agreement_reference(self):
        lock=ex.read_json(self.lock);cid=next(c['case_id'] for c in self.cases if c['split']=='test' and c['variant']=='substantive')
        lock['reviewers']['vivianne'][cid]['label']='unverifiable';del lock['consensus'][cid]
        ex.write_json(self.lock,lock)
        out=self.analyze(self.fixture_predictions())
        self.assertEqual(out['excluded_disagreements'],1)
        self.assertEqual(out['references']['reviewer_agreement']['overall']['baseline']['n'],71)
        self.assertEqual(out['references']['emma']['overall']['baseline']['n'],72)
        self.assertEqual(out['references']['vivianne']['overall']['baseline']['n'],72)

    def test_missing_duplicate_and_wrong_metadata_rejected(self):
        rows=self.fixture_predictions()
        with self.assertRaises(ValueError):self.analyze(rows[:-1])
        with self.assertRaises(ValueError):self.analyze(rows+[rows[0]])
        rows[0]['prompt_sha256']='changed'
        with self.assertRaises(ValueError):self.analyze(rows)

    def test_invalid_json_is_not_abstention(self):
        rows=self.fixture_predictions();row=next(r for r in rows if r['condition']=='intervention');row['raw_response']='maybe supported'
        with self.assertRaises(ValueError):self.analyze(rows)
        self.assertEqual(ex.read_json(self.p/'analysis.json')['status'],'invalid_predictions')

    def test_quote_validation_does_not_silently_change_label(self):
        p=ex.parse_prediction(json.dumps({'label':'supported','evidence_span':'invented quote','describes':'target'}),'intervention','real text')
        self.assertEqual(p['label'],'supported');self.assertFalse(p['span_valid'])

    def test_changed_review_context_rejected(self):
        path=self.p/'emma.csv';path.write_text(path.read_text().replace(self.cases[0]['context'],'ALTERED INPUT'))
        with self.assertRaises(ValueError):ex.read_review(path,'emma',self.cases,ex.read_json(HERE/'review_map.json')['emma'])

    def test_txt_form_preserves_ids_and_independent_labels(self):
        text=(HERE/'review/emma.txt').read_text().replace('TOPIC_MATCH:\n','TOPIC_MATCH: YES\n').replace('CONTENT_SUPPORT:\n','CONTENT_SUPPORT: CANT_TELL\n').replace('LABEL:\n','LABEL: CONTRADICTED\n')
        path=self.p/'review.txt';path.write_text(text)
        rows=ex.read_review(path,'emma',self.cases,ex.read_json(HERE/'review_map.json')['emma'])
        self.assertEqual(len(rows),90);self.assertTrue(all(r['label']=='contradicted' for r in rows.values()))


if __name__=='__main__':unittest.main()
