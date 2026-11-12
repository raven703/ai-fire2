"""Generate split synthetic corpus and measure actual full pipeline labels."""
import json
from pathlib import Path
from collections import defaultdict
from ai_firewall.synthetic_v2 import fixtures
from ai_firewall.pii_engine import create_pipeline

root=Path('/artifacts/detection-v2'); root.mkdir(parents=True,exist_ok=True)
pipeline=create_pipeline()
templates={'PERSON':'Получатель: {}','RU_INN':'ИНН: {}','RU_SNILS':'СНИЛС: {}',
 'PHONE_NUMBER':'Телефон: {}','RU_PASSPORT':'паспорт: {}','RU_OGRN':'ОГРН: {}',
 'RU_OGRNIP':'ОГРНИП: {}','EMAIL_ADDRESS':'Email: {}','IP_ADDRESS':'IP: {}',
 'DATE_OF_BIRTH':'дата рождения: {}','POSTAL_ADDRESS':'адрес: {}'}
for split,seed in [('development',271828),('holdout',314159)]:
    corpus=[]
    for row in fixtures(seed,count=100):
        for category,template in templates.items():
            corpus.append({'text':template.format(row[category]),'labels':[category]})
        corpus.append({'text':'БИК: '+row['RU_BIC']+' р/с: '+row['RU_BANK_ACCOUNT'],
                       'labels':['RU_BIC','RU_BANK_ACCOUNT']})
    # Different random fixture values across splits; templates are shared, not
    # a claim of independently authored adversarial holdout distribution.
    corpus.extend({'text':f'Обычная проверка номер {i}, без реквизитов.','labels':[]} for i in range(100))
    (root/(split+'.jsonl')).write_text('\n'.join(json.dumps(x,ensure_ascii=False) for x in corpus))
    counts=defaultdict(lambda:[0,0,0,0])
    predictions=[]
    for item in corpus:
        found={f.entity_type for s in pipeline.inspect(item['text']) for f in s.findings}
        expected=set(item['labels']); predictions.append(found)
        for category in set(templates)|{'RU_BIC','RU_BANK_ACCOUNT'}:
            n=counts[category]
            n[0]+=category in found and category in expected
            n[1]+=category in found and category not in expected
            n[2]+=category not in found and category in expected
            n[3]+=category not in found and category not in expected
    metrics={}
    for category,(tp,fp,fn,tn) in counts.items():
        precision=tp/(tp+fp) if tp+fp else 0
        recall=tp/(tp+fn) if tp+fn else 0
        metrics[category]={'tp':tp,'fp':fp,'fn':fn,'tn':tn,'precision':precision,'recall':recall,
            'f1':2*precision*recall/(precision+recall) if precision+recall else 0,
            'fpr':fp/(fp+tn) if fp+tn else 0,'fnr':fn/(fn+tp) if fn+tp else 0}
    (root/(split+'-metrics.json')).write_text(json.dumps(metrics,indent=2))
    print(split,len(corpus),'examples; metrics saved',flush=True)