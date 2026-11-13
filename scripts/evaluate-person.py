"""Frozen small independent evaluation, not used by recognizer rules."""
import json
from ai_firewall.pii_engine import NatashaNER,NormalizedDetector
from ai_firewall.person_names import PersonNames
from ai_firewall.detection import DetectorPipeline

positive=[
 'смирнов алексей дмитриевич','КУЗНЕЦОВА МАРИЯ АЛЕКСАНДРОВНА',
 'соколовой елене викторовне','Сидоров николай Павлович',
 'Васильева О. Н.','максим орлов','Фёдоров   Андрей\tМихайлович',
 'В документе указан морозов сергей петрович, проверь запись.',
 'Пригласите Волкову Татьяну Ильиничну завтра.',
 'Белов-Чернов Дмитрий Алексеевич','Абдуллаев Рустам Рашидович',
 'джамшед нурмахмадов']
negative=[
 'сегодня новый сотрудник успешно завершил обучение',
 'служба доставки уточняет время заказа','ООО Северный Ветер',
 'главный бухгалтер подготовил новый отчёт','отдел разработки обсудил сроки',
 'надежда на лучшее сохраняется','любовь к чтению помогает учиться',
 'вера в команду важна','роман опубликован вчера','лев живёт в заповеднике',
 'компания Вектор открыла офис','согласуйте встречу на следующий вторник']
ner=NatashaNER();names=PersonNames()
methods={'before':DetectorPipeline([NormalizedDetector(ner)]),
         'after':DetectorPipeline([NormalizedDetector(ner),NormalizedDetector(names)])}
for name,pipeline in methods.items():
 tp=fp=fn=tn=0
 for expected,rows in [(True,positive),(False,negative)]:
  for i,text in enumerate(rows):
   hit=any(any(f.entity_type=='PERSON' for f in s.findings) for s in pipeline.inspect(text))
   tp+=expected and hit;fn+=expected and not hit;fp+=not expected and hit;tn+=not expected and not hit
   if expected!=hit: print(json.dumps({'method':name,'positive':expected,'case':i,'error':'FN' if expected else 'FP'}))
 precision=tp/(tp+fp) if tp+fp else 0;recall=tp/(tp+fn)
 print(json.dumps(dict(method=name,tp=tp,fp=fp,fn=fn,tn=tn,precision=precision,recall=recall,
     f1=2*precision*recall/(precision+recall) if precision+recall else 0)))