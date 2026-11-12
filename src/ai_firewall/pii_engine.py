"""Offline real NLP pipeline; detection only, no Vault or content logging."""
import re
import unicodedata

from ai_firewall.detection import DetectionResult, DetectorPipeline
from ai_firewall.detection_adapters import PresidioAdapter


def russian_phone(value):
    import phonenumbers
    digits=re.sub(r'\D','',value)
    if len(digits)!=11 or digits[0] not in '78': return False
    try:
        number=phonenumbers.parse(value,'RU')
        return number.country_code==7 and phonenumbers.is_valid_number(number) and phonenumbers.region_code_for_number(number)=='RU'
    except phonenumbers.NumberParseException:
        return False


class NormalizedDetector:
    """NFC per combining cluster, mapping every result back to source bounds."""
    def __init__(self,detector): self.detector=detector; self.name=detector.name
    def detect(self,text,*,language):
        normalized=[]; bounds=[]
        for match in re.finditer(r'.[\u0300-\u036f]*',text,re.DOTALL):
            cluster=unicodedata.normalize('NFC',match.group())
            normalized.append(cluster); bounds.extend([(match.start(),match.end())]*len(cluster))
        value=''.join(normalized)
        return [DetectionResult(f.entity_type,bounds[f.start][0],bounds[f.end-1][1],f.confidence,f.source)
                for f in self.detector.detect(value,language=language)]


def inn_valid(value):
    if not value.isascii() or not value.isdigit() or len(set(value)) == 1:
        return False
    digits=list(map(int,value))
    def check(weights): return sum(a*b for a,b in zip(digits,weights))%11%10
    if len(value)==10:
        return check([2,4,10,3,5,9,4,6,8])==digits[9]
    return len(value)==12 and check([7,2,4,10,3,5,9,4,6,8])==digits[10] and check([3,7,2,4,10,3,5,9,4,6,8])==digits[11]


def snils_valid(value):
    digits=re.sub(r'\D','',value)
    if len(digits)!=11 or len(set(digits))==1 or int(digits[:9])<=1001998:
        return False
    total=sum(int(v)*(9-i) for i,v in enumerate(digits[:9]))%101
    return (0 if total==100 else total)==int(digits[9:])


def luhn_valid(value):
    digits=re.sub(r'[ -]','',value)
    if not digits.isascii() or not digits.isdigit() or not 13<=len(digits)<=19 or len(set(digits))==1:
        return False
    total=0
    for i,v in enumerate(reversed(digits)):
        n=int(v)*(2 if i%2 else 1)
        total+=n-9 if n>9 else n
    return total%10==0


class RussianRecognizer:
    name='russian-formal'
    rules=(
        ('RU_INN',r'(?i)\bинн\s*[:№]?\s*(?P<v>[0-9]{12}|[0-9]{10})(?![0-9])',inn_valid),
        ('RU_SNILS',r'(?i)\bснилс\s*[:№]?\s*(?P<v>[0-9]{3}[- ]?[0-9]{3}[- ]?[0-9]{3}[ -]?[0-9]{2})(?![0-9])',snils_valid),
        ('RU_PASSPORT',r'(?i)\bпаспорт(?:\s+рф)?\s*[:№]?\s*(?P<v>[0-9]{2}\s?[0-9]{2}\s+[0-9]{6})(?![0-9])',lambda v: len(set(re.sub(r'\D','',v)))>1),
        ('PHONE_NUMBER',r'(?<![\w])(?P<v>(?:\+7|8)[ (\-]*[0-9]{3}[) \-]*[0-9]{3}[ \-]*[0-9]{2}[ \-]*[0-9]{2})(?![\w])',russian_phone),
        ('CREDIT_CARD',r'(?<![0-9])(?P<v>(?:[0-9][ -]?){12,18}[0-9])(?![0-9])',luhn_valid),
        ('RU_BIC',r'(?i)\bбик\s*[:№]?\s*(?P<v>04[0-9]{7})(?![0-9])',lambda v: len(set(v))>1),
    )

    def detect(self,text,*,language):
        findings=[]
        for kind,pattern,validate in self.rules:
            for m in re.finditer(pattern,text):
                if validate(m.group('v')):
                    findings.append(DetectionResult(kind,m.start('v'),m.end('v'),.9,self.name))
        # Account checksum needs a context BIC, never infer it from random digits.
        bic=re.search(r'(?i)\bбик\s*[:№]?\s*(04[0-9]{7})(?![0-9])',text)
        if bic:
            for m in re.finditer(r'(?i)\b(?:сч[её]т|р/с)\s*[:№]?\s*([0-9]{20})(?![0-9])',text):
                value=bic.group(1)[-3:]+m.group(1)
                if sum(int(v)*[7,1,3][i%3] for i,v in enumerate(value))%10==0:
                    findings.append(DetectionResult('RU_BANK_ACCOUNT',m.start(1),m.end(1),.9,self.name))
        return findings


class NatashaNER:
    name='natasha'

    def __init__(self):
        from natasha import Segmenter, NewsEmbedding, NewsNERTagger
        self.segmenter=Segmenter()
        self.tagger=NewsNERTagger(NewsEmbedding())

    def detect(self,text,*,language):
        from natasha import Doc
        if language!='ru': raise ValueError('unsupported_language')
        doc=Doc(text); doc.segment(self.segmenter); doc.tag_ner(self.tagger)
        kinds={'PER':'PERSON','ORG':'ORGANIZATION','LOC':'LOCATION'}
        results=[]
        for s in doc.spans:
            if s.type not in kinds: continue
            # Join only model-confirmed adjacent person spans, never arbitrary words.
            if results and s.type=='PER' and results[-1].entity_type=='PERSON' and text[results[-1].end:s.start].isspace():
                old=results.pop(); results.append(DetectionResult('PERSON',old.start,s.stop,.85,self.name))
            else:
                results.append(DetectionResult(kinds[s.type],s.start,s.stop,.85,self.name))
        return results


def create_pipeline():
    import spacy
    from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
    from presidio_analyzer.nlp_engine import SpacyNlpEngine
    from presidio_analyzer.predefined_recognizers import EmailRecognizer, PhoneRecognizer, CreditCardRecognizer, IpRecognizer
    import tldextract
    class OfflineEmail(EmailRecognizer):
        extractor=tldextract.TLDExtract(suffix_list_urls=(),cache_dir=None)
        def validate_result(self,pattern_text):
            return bool(self.extractor(pattern_text).fqdn)
    class RussianPresidio(PresidioAdapter):
        def detect(self,text,*,language):
            return [r for r in super().detect(text,language=language)
                    if r.entity_type!='PHONE_NUMBER' or russian_phone(text[r.start:r.end])]
    # Presidio runs real pattern/phone/card/IP recognizers. Natasha supplies NER.
    # Blank spaCy is explicitly a tokenizer, NOT a claimed pretrained NER model.
    nlp=SpacyNlpEngine(models=[{'lang_code':'ru','model_name':'local-tokenizer'}])
    nlp.nlp={'ru':spacy.blank('ru')}
    registry=RecognizerRegistry(supported_languages=['ru'])
    for cls in (OfflineEmail,CreditCardRecognizer,IpRecognizer):
        registry.add_recognizer(cls(supported_language='ru'))
    registry.add_recognizer(PhoneRecognizer(supported_language='ru',supported_regions=['RU']))
    analyzer=AnalyzerEngine(nlp_engine=nlp,registry=registry,supported_languages=['ru'])
    from ai_firewall.detection_v2 import ExtendedRecognizer
    return DetectorPipeline([NormalizedDetector(d) for d in (RussianPresidio(analyzer),NatashaNER(),RussianRecognizer(),ExtendedRecognizer())])