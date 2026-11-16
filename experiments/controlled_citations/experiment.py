"""Review, freeze, run, and analyze the controlled citation experiment (standard library only)."""
import argparse
import csv
import hashlib
import io
import json
import random
import re
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
LABELS = {'supported', 'contradicted', 'unverifiable'}
FIELDS = {'YES', 'NO', 'CANT_TELL'}
CONDITIONS = ('baseline', 'intervention')


def sha(data): return hashlib.sha256(data).hexdigest()
def read_json(path): return json.loads(Path(path).read_text())
def read_jsonl(path): return [json.loads(s) for s in Path(path).read_text().splitlines() if s.strip()]
def write_json(path, value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n')


def assets():
    manifest=read_json(HERE/'manifest.json')
    for name,digest in manifest['files'].items():
        if sha((HERE/name).read_bytes())!=digest: raise ValueError(f'Frozen asset changed: {name}; create a new experiment version instead')
    for condition,digest in manifest['prompts'].items():
        if sha((HERE/'prompts'/f'{condition}.txt').read_bytes())!=digest: raise ValueError(f'Frozen {condition} prompt changed')
    cases=read_jsonl(HERE/'cases.jsonl')
    return cases,manifest


def read_review(path, reviewer, cases, mapping):
    path=Path(path)
    if path.suffix.lower()=='.csv':
        rows=list(csv.DictReader(io.StringIO(path.read_text(encoding='utf-8-sig'),newline='')))
    elif path.suffix.lower()=='.txt':
        rows=[]
        for block in re.split(r'^CASE ',path.read_text(),flags=re.M)[1:]:
            rid=block.splitlines()[0].strip()
            row={'review_id':rid}
            for field,key in [('CONTEXT','context'),('TITLE','title'),('TOPIC_MATCH','topic_match'),('CONTENT_SUPPORT','content_support'),('LABEL','label'),('NOTES','notes')]:
                m=re.search(r'^'+field+r':[ \t]*(.*)$',block,re.M)
                if m is None: raise ValueError(f'{reviewer} {rid}: missing {field}')
                row[key]=m.group(1).strip()
            rows.append(row)
    else: raise ValueError('Review files must be CSV or TXT')
    by_id={c['case_id']:c for c in cases};out={};seen=set()
    for row in rows:
        rid=row.get('review_id','').strip()
        if rid not in mapping or rid in seen: raise ValueError(f'{reviewer}: unknown or duplicate review ID {rid}')
        seen.add(rid);cid=mapping[rid];c=by_id[cid]
        for field in ['context','title']:
            if row.get(field,'').strip()!=c[field].strip(): raise ValueError(f'{reviewer} {rid}: {field} was changed')
        label=row.get('label','').strip().lower()
        f1=row.get('topic_match','').strip().upper().replace(' ','_')
        f2=row.get('content_support','').strip().upper().replace(' ','_')
        if label not in LABELS or f1 not in FIELDS or f2 not in FIELDS:
            raise ValueError(f'{reviewer} {rid}: complete label, topic_match and content_support using permitted values')
        out[cid]={'label':label,'topic_match':f1,'content_support':f2,'notes':row.get('notes',''),'review_id':rid}
    if seen!=set(mapping): raise ValueError(f'{reviewer}: expected all {len(mapping)} review IDs; found {len(seen)}')
    return out


def agreement(a,b):
    n=len(a)
    if not n: return {'n':0,'agreement':None,'kappa':None}
    observed=sum(x==y for x,y in zip(a,b))/n
    expected=sum(a.count(c)*b.count(c)/n**2 for c in set(a+b))
    return {'n':n,'agree':sum(x==y for x,y in zip(a,b)), 'agreement':observed,
            'kappa':None if expected==1 else (observed-expected)/(1-expected)}


def review(args):
    cases,manifest=assets();mapping=read_json(HERE/'review_map.json')
    reviewers={name:read_review(getattr(args,name),name,cases,mapping[name]) for name in ['emma','vivianne']}
    summary={}
    for split in ['development','test']:
        ids=[c['case_id'] for c in cases if c['split']==split]
        summary[split]={field:agreement([reviewers['emma'][i][field] for i in ids],[reviewers['vivianne'][i][field] for i in ids]) for field in ['label','topic_match','content_support']}
    consensus={i:a['label'] for i,a in reviewers['emma'].items() if a['label']==reviewers['vivianne'][i]['label']}
    disagreements=[dict(case_id=c['case_id'],context=c['context'],title=c['title'],emma=reviewers['emma'][c['case_id']]['label'],vivianne=reviewers['vivianne'][c['case_id']]['label']) for c in cases if c['case_id'] not in consensus]
    lock=dict(schema_version=1,manifest_sha256=sha((HERE/'manifest.json').read_bytes()),reviewers=reviewers,consensus=consensus,
              review_file_sha256={name:sha(Path(getattr(args,name)).read_bytes()) for name in reviewers},agreement=summary,
              disagreements=disagreements,reference_note='Agreement subset is not adjudicated truth; report each reviewer separately as sensitivity analyses.')
    if Path(args.output).exists(): raise ValueError('Review lock already exists; preserve it and use a new output path')
    write_json(args.output,lock)
    print(json.dumps({'agreement':summary,'consensus_cases':len(consensus),'disagreement_cases':len(disagreements)},indent=2))


def validate_lock(path):
    lock=read_json(path)
    if lock['manifest_sha256']!=sha((HERE/'manifest.json').read_bytes()): raise ValueError('Review lock belongs to a different frozen experiment')
    cases,_=assets();ids={c['case_id'] for c in cases}
    if set(lock.get('reviewers',{}))!={'emma','vivianne'}: raise ValueError('Both independent reviewers are required')
    for rows in lock['reviewers'].values():
        if set(rows)!=ids or any(r['label'] not in LABELS for r in rows.values()): raise ValueError('Incomplete review lock')
    expected={i:lock['reviewers']['emma'][i]['label'] for i in ids if lock['reviewers']['emma'][i]['label']==lock['reviewers']['vivianne'][i]['label']}
    if lock['consensus']!=expected: raise ValueError('Consensus must equal reviewer agreement, without inferred or silently adjudicated labels')
    # Recompute summaries from the actual judgments rather than trusting cached counts.
    lock['agreement']={}
    for split in ['development','test']:
        selected=[c['case_id'] for c in cases if c['split']==split]
        lock['agreement'][split]={field:agreement([lock['reviewers']['emma'][i][field] for i in selected],
                                                 [lock['reviewers']['vivianne'][i][field] for i in selected])
                                  for field in ['label','topic_match','content_support']}
    return lock


def make_jobs(model,split,lock_path=None):
    cases,manifest=assets()
    if split=='test' and not lock_path: raise ValueError('Test jobs require --review-lock after both reviews are complete')
    if lock_path: validate_lock(lock_path)
    lock_hash=sha(Path(lock_path).read_bytes()) if lock_path else None
    jobs=[]
    for c in cases:
        if c['split']!=split:continue
        for condition in CONDITIONS:
            template=(HERE/'prompts'/f'{condition}.txt').read_text()
            prompt=template.format(context=c['context'],title=c['title'])
            j=dict(case_id=c['case_id'],condition=condition,split=split,model=model,
                   manifest_sha256=sha((HERE/'manifest.json').read_bytes()),review_lock_sha256=lock_hash,
                   prompt_sha256=sha(template.encode()),prompt=prompt,
                   settings={'temperature':0,'think':False,'num_predict':1024})
            j['job_id']=sha(json.dumps(j,sort_keys=True).encode())
            jobs.append(j)
    random.Random(20261115).shuffle(jobs)
    return jobs


def parse_prediction(raw,condition,context):
    if not isinstance(raw,str):raise ValueError('Response must be text')
    if condition=='baseline':
        # Same first-label parsing convention as the original baseline.
        m=re.search(r'\b(SUPPORTED|CONTRADICTED|UNVERIFIABLE)\b',raw.upper())
        if not m:raise ValueError('No baseline label')
        return {'label':m.group(1).lower(),'span_valid':None,'evidence_span':None,'describes':None}
    obj=json.loads(raw)
    if not isinstance(obj,dict) or set(obj)!={'label','evidence_span','describes'}:raise ValueError('Intervention requires exactly label/evidence_span/describes JSON fields')
    if obj['label'] not in LABELS or obj['describes'] not in {'target','other_measure','no_substantive_description'} or not isinstance(obj['evidence_span'],str):raise ValueError('Invalid intervention schema')
    span=obj['evidence_span']
    # Never silently relabel a bad quotation as abstention: score the stated label.
    return {**obj,'span_valid':bool(span) and span in context}


def prepare(args):
    jobs=make_jobs(args.model,args.split,args.review_lock)
    p=Path(args.output);p.parent.mkdir(parents=True,exist_ok=True)
    if p.exists():raise ValueError('Output already exists; choose a new jobs path')
    p.write_text('\n'.join(json.dumps(j,ensure_ascii=False) for j in jobs)+'\n')
    print(f'Prepared {len(jobs)} jobs; no inference calls made')


def run(args):
    jobs=make_jobs(args.model,args.split,args.review_lock)
    out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
    existing=read_jsonl(out) if out.exists() else []
    expected={j['job_id']:j for j in jobs}
    seen=set()
    for row in existing:
        if row.get('job_id') not in expected or row['job_id'] in seen:raise ValueError('Existing run contains duplicate or incompatible jobs')
        if row.get('status')!='ok':raise ValueError('Existing run contains failures; preserve it and start a separately named rerun')
        seen.add(row['job_id'])
    for job in jobs:
        if job['job_id'] in seen:continue
        payload={'model':args.model,'prompt':job['prompt'],'stream':False,'think':False,
                 'options':{'temperature':0,'num_predict':1024}}
        start=time.time()
        row={k:v for k,v in job.items() if k!='prompt'}
        row['backend']='ollama';row['endpoint']=args.ollama_url
        try:
            req=urllib.request.Request(args.ollama_url,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(req,timeout=args.timeout) as response:body=json.load(response)
            row.update(status='ok',raw_response=body['response'],provider_model=body.get('model'),provider_created_at=body.get('created_at'),
                       prompt_eval_count=body.get('prompt_eval_count'),eval_count=body.get('eval_count'),done_reason=body.get('done_reason'))
        except Exception as e:
            row.update(status='error',error=f'{type(e).__name__}: {e}')
        row['elapsed_seconds']=time.time()-start
        with out.open('a') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
        print(f"{job['condition']} {job['case_id']}: {row['status']}",flush=True)
        if row['status']!='ok':raise ValueError('Run stopped on error; partial output retained, no missing cases converted into abstentions')


def rate(num,den):return num/den if den else None


def metrics(rows):
    n=len(rows);negative=[r for r in rows if r['gold']!='supported'];positive=[r for r in rows if r['gold']=='supported']
    committed=[r for r in rows if r['prediction']!='unverifiable']
    false_support=sum(r['prediction']=='supported' for r in negative)
    retained=sum(r['prediction']=='supported' for r in positive)
    errors=sum(r['prediction']!=r['gold'] for r in committed)
    return {'n':n,'non_supported_n':len(negative),'false_support_count':false_support,'false_support_rate':rate(false_support,len(negative)),
            'supported_n':len(positive),'retained_support_count':retained,'support_retention':rate(retained,len(positive)),
            'answered':len(committed),'coverage':rate(len(committed),n),'selective_errors':errors,'selective_error':rate(errors,len(committed)),
            'three_way_accuracy':rate(sum(r['prediction']==r['gold'] for r in rows),n)}


def quantile(values,p):
    values=sorted(values);idx=(len(values)-1)*p;lo=int(idx);hi=min(lo+1,len(values)-1)
    return values[lo]*(hi-idx)+values[hi]*(idx-lo) if lo!=hi else values[lo]


def paired_bootstrap(rows,iterations,seed):
    groups=sorted({r['pair_id'] for r in rows})
    # Resample donor pairs, retaining both sources and both conditions together.
    counters={g:{cond:metrics([r for r in rows if r['pair_id']==g and r['condition']==cond]) for cond in CONDITIONS} for g in groups}
    targets={'false_support_rate':('false_support_count','non_supported_n'),'support_retention':('retained_support_count','supported_n')}
    totals={cond:metrics([r for r in rows if r['condition']==cond]) for cond in CONDITIONS}
    result={};rng=random.Random(seed);draws=[[rng.choice(groups) for _ in groups] for _ in range(iterations)] if groups else []
    for metric,(num,den) in targets.items():
        deltas=[]
        for draw in draws:
            values={cond:rate(sum(counters[g][cond][num] for g in draw),sum(counters[g][cond][den] for g in draw)) for cond in CONDITIONS}
            if all(v is not None for v in values.values()):deltas.append(values['intervention']-values['baseline'])
        point=None if any(totals[c][metric] is None for c in CONDITIONS) else totals['intervention'][metric]-totals['baseline'][metric]
        result[metric]={'difference_intervention_minus_baseline':point,'ci95': [quantile(deltas,.025),quantile(deltas,.975)] if deltas else None,
                        'valid_resamples':len(deltas),'requested_resamples':iterations}
    return {'cluster':'donor_pair','clusters':len(groups),'seed':seed,'interval':'paired percentile','metrics':result,
            'limitation':'Conditional on constructed examples and chosen reference labels; does not model natural-meeting prevalence, annotation uncertainty, or repeated model runs.'}


def analyze(args):
    cases,_=assets();lock=validate_lock(args.review_lock)
    selected=[c for c in cases if c['split']==args.split];byid={c['case_id']:c for c in selected}
    records=read_jsonl(args.predictions)
    if not records:raise ValueError('Empty prediction file')
    models={r.get('model') for r in records}
    if len(models)!=1 or None in models:raise ValueError('Compare one identical model across both conditions per analysis')
    model=next(iter(models));jobs=make_jobs(model,args.split,args.review_lock)
    expected={j['job_id']:j for j in jobs};pred={};bad=[];backends=set();endpoints=set()
    for record in records:
        jid=record.get('job_id')
        if jid not in expected:raise ValueError('Unexpected job ID, split, model, settings, prompt, or review lock')
        job=expected[jid]
        for key,value in job.items():
            if key!='prompt' and record.get(key)!=value:raise ValueError(f'{jid}: changed metadata {key}')
        key=(job['case_id'],job['condition'])
        if key in pred:raise ValueError(f'Duplicate prediction {key}')
        if record.get('status')!='ok':raise ValueError(f'Failed request {key}; no score computed')
        if not record.get('backend') or not record.get('endpoint'):raise ValueError('Record backend and endpoint for provenance')
        backends.add(record['backend']);endpoints.add(record['endpoint'])
        try:pred[key]=parse_prediction(record.get('raw_response'),job['condition'],byid[key[0]]['context'])
        except (ValueError,TypeError,KeyError) as e:
            bad.append({'case_id':key[0],'condition':key[1],'error':str(e)});pred[key]=None
    if len(backends)!=1 or len(endpoints)!=1:raise ValueError('Backend and endpoint must match between conditions')
    if len(pred)!=len(jobs):raise ValueError(f'Incomplete run: {len(pred)}/{len(jobs)} predictions; no selective dropping allowed')
    if bad:
        write_json(args.output,{'status':'invalid_predictions','invalid_count':len(bad),'invalid':bad,'note':'No headline metrics computed. Preserve raw responses and resolve with a separately documented rerun or parsing revision.'})
        raise ValueError('Invalid model responses; diagnostics written, no missing/invalid output treated as abstention')
    references={'reviewer_agreement':lock['consensus'],**{name:{i:r['label'] for i,r in rows.items()} for name,rows in lock['reviewers'].items()}}
    output={'status':'complete','split':args.split,'model':model,'manifest_sha256':sha((HERE/'manifest.json').read_bytes()),
            'review_lock_sha256':sha(Path(args.review_lock).read_bytes()),'prediction_file_sha256':sha(Path(args.predictions).read_bytes()),
            'total_cases':len(selected),'excluded_disagreements':len(selected)-sum(c['case_id'] in lock['consensus'] for c in selected),
            'agreement':lock['agreement'][args.split],'references':{}}
    for name,gold in references.items():
        rows=[dict(case_id=c['case_id'],pair_id=c['pair_id'],variant=c['variant'],condition=cond,gold=gold[c['case_id']],prediction=pred[c['case_id'],cond]['label']) for c in selected if c['case_id'] in gold for cond in CONDITIONS]
        output['references'][name]={'overall':{cond:metrics([r for r in rows if r['condition']==cond]) for cond in CONDITIONS},
            'by_variant':{v:{cond:metrics([r for r in rows if r['variant']==v and r['condition']==cond]) for cond in CONDITIONS} for v in sorted({c['variant'] for c in selected})},
            'paired':paired_bootstrap(rows,args.resamples,args.seed)}
    intervention=[p for (i,c),p in pred.items() if c=='intervention']
    supported=[p for p in intervention if p['label']=='supported']
    output['evidence_checks']={'supported_n':len(supported),'supported_with_verbatim_span':sum(p['span_valid'] for p in supported),
        'supported_describes_target':sum(p['describes']=='target' for p in supported),
        'nonempty_spans_not_in_input':sum(bool(p['evidence_span']) and not p['span_valid'] for p in intervention),
        'note':'Exact substring validation checks provenance only, not entailment. Stated labels are scored without automatic relabeling.'}
    output['warnings']=['Reviewer-agreement subset is not adjudicated truth; per-reviewer sensitivities retain all cases.',
                        'Constructed examples from an existing explored benchmark are not a prospective natural test set.',
                        'The intervention changes instructions and output format together; no component-specific causal claim.',
                        'Intervals resample 12 donor pairs on test; small-cluster uncertainty can be unstable.']
    write_json(args.output,output)
    print(json.dumps({'status':'complete','total_cases':len(selected),'excluded_disagreements':output['excluded_disagreements'],
                      'primary':output['references']['reviewer_agreement']['overall']},indent=2))


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    subs=parser.add_subparsers(dest='command',required=True)
    p=subs.add_parser('review',help='Validate two completed forms, report agreement, freeze original judgments')
    p.add_argument('--emma',required=True);p.add_argument('--vivianne',required=True);p.add_argument('--output',required=True)
    p.set_defaults(func=review)
    for command,func in [('prepare',prepare),('run',run)]:
        p=subs.add_parser(command);p.add_argument('--model',required=True);p.add_argument('--split',choices=['development','test'],default='development')
        p.add_argument('--review-lock');p.add_argument('--output',required=True);p.set_defaults(func=func)
        if command=='run':
            p.add_argument('--ollama-url',default='http://localhost:11434/api/generate');p.add_argument('--timeout',type=int,default=180)
    p=subs.add_parser('analyze');p.add_argument('--predictions',required=True);p.add_argument('--review-lock',required=True)
    p.add_argument('--split',choices=['development','test'],default='test');p.add_argument('--output',required=True)
    p.add_argument('--resamples',type=int,default=20000);p.add_argument('--seed',type=int,default=20261115);p.set_defaults(func=analyze)
    args=parser.parse_args(argv)
    if getattr(args,'resamples',1)<1:parser.error('--resamples must be positive')
    try:args.func(args)
    except (ValueError,KeyError,OSError) as e:parser.exit(2,f'Error: {e}\n')


if __name__=='__main__':main()
