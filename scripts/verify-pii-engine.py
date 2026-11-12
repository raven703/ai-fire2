"""Offline measured evaluation. Prints aggregates only, never input text."""
import json
import resource
import time
import os
from pathlib import Path
from collections import defaultdict

from ai_firewall.pii_engine import create_pipeline
from ai_firewall.pii_policy import YAMLPolicy
from ai_firewall.detection import PolicyContext, Action

started=time.perf_counter(); pipeline=create_pipeline(); startup=time.perf_counter()-started
counts=defaultdict(lambda:[0,0,0]); latencies=[]
corpus=json.loads(Path(os.getenv('PII_CORPUS','/app/corpus/pii-eval.json')).read_text())
policy=YAMLPolicy('/app/config/pii-policy-v1.yaml')
context=PolicyContext('test','test','input',policy.version)
false_blocks=0; negatives=0
for sample in corpus:
    start=time.perf_counter(); spans=pipeline.inspect(sample['text']); latencies.append(time.perf_counter()-start)
    actual={(f.entity_type,f.start,f.end) for span in spans for f in span.findings}
    expected={(e['entity'],e['start'],e['end']) for e in sample['entities']}
    if not expected:
        negatives+=1
        false_blocks+=policy.evaluate(spans,context).action==Action.BLOCK
    for kind in {v[0] for v in actual|expected}:
        a={v for v in actual if v[0]==kind}; e={v for v in expected if v[0]==kind}
        counts[kind][0]+=len(a&e); counts[kind][1]+=len(a-e); counts[kind][2]+=len(e-a)
metrics={}
for kind,(tp,fp,fn) in counts.items():
    p=tp/(tp+fp) if tp+fp else 0; r=tp/(tp+fn) if tp+fn else 0
    metrics[kind]={'tp':tp,'fp':fp,'fn':fn,'precision':p,'recall':r,'f1':2*p*r/(p+r) if p+r else 0}
print(json.dumps({'samples':len(corpus),'negative_samples':negatives,'false_blocks':false_blocks,
    'false_block_rate':false_blocks/negatives if negatives else None,
    'startup_seconds':startup,'mean_ms':sum(latencies)/len(latencies)*1000,
    'max_ms':max(latencies)*1000,'rss_peak_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
    'exact_span_metrics':metrics},indent=2))