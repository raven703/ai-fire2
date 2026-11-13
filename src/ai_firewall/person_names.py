"""Original-offset Natasha grammar and conservative dictionary morphology."""
import inspect
import os
import re
from functools import lru_cache

from ai_firewall.detection import DetectionResult


class PersonNames:
    name='natasha-names-morphology'

    def __init__(self):
        import pymorphy2_dicts_ru
        from pymorphy2.units.base import BaseAnalyzerUnit
        # pymorphy2 0.9 expects removed inspect.getargspec and pkg_resources.
        # Explicit installed dictionary avoids pkg_resources entry-point discovery.
        os.environ.setdefault('PYMORPHY2_DICT_PATH',pymorphy2_dicts_ru.get_path())
        BaseAnalyzerUnit._get_param_names=classmethod(
            lambda cls: sorted(inspect.getfullargspec(cls.__init__).args[1:]))
        from natasha import MorphVocab, NamesExtractor
        self.vocab=MorphVocab()
        self.extractor=NamesExtractor(self.vocab)

    @lru_cache(maxsize=4096)
    def tags(self,word):
        # Low-level parse retains Name/Surn/Patr grammemes hidden by MorphForm.
        return {tag for p in self.vocab.parse(word.casefold()) if p.is_known
                for tag in ('Name','Surn','Patr') if tag in p.tag}

    def detect(self,text,*,language):
        if language!='ru': raise ValueError('unsupported_language')
        found=[]
        for match in self.extractor(text):
            fact=match.fact
            # Do not accept lone dictionary words (e.g. вера/любовь).
            if sum(bool(getattr(fact,k,None)) for k in ('first','last','middle'))>=2:
                found.append(DetectionResult('PERSON',match.start,match.stop,.85,self.name))
        tokens=list(re.finditer(r'[А-Яа-яЁё]+(?:-[А-Яа-яЁё]+)*',text))
        def tags(token):
            parts=token.group().split('-')
            sets=[self.tags(p) for p in parts]
            return set.intersection(*sets) if sets else set()
        for i,token in enumerate(tokens):
            # Dictionary-confirmed surname + first name + patronymic, including
            # inflections. No casing transformation or transformed offsets.
            if i+2<len(tokens):
                a,b,c=tokens[i:i+3]
                if (text[a.end():b.start()].isspace() and text[b.end():c.start()].isspace()
                        and 'Surn' in tags(a) and 'Name' in tags(b) and 'Patr' in tags(c)):
                    found.append(DetectionResult('PERSON',a.start(),c.end(),.95,self.name))
            # Two components need dictionary surname/name evidence, not three
            # arbitrary words or isolated common nouns.
            if i+1<len(tokens):
                other=tokens[i+1]
                if text[token.end():other.start()].isspace() and (
                        ('Surn' in tags(token) and 'Name' in tags(other)) or
                        ('Name' in tags(token) and 'Surn' in tags(other))):
                    found.append(DetectionResult('PERSON',token.start(),other.end(),.85,self.name))
            if 'Surn' in tags(token):
                initials=re.match(r'\s+[А-Яа-яЁё]\.\s*[А-Яа-яЁё]\.',text[token.end():])
                if initials:
                    found.append(DetectionResult('PERSON',token.start(),token.end()+initials.end(),.9,self.name))
        return list(set(found))