"""Strict versioned YAML policy; no Vault dependency or side effects."""
from pathlib import Path
import yaml
import regex

from ai_firewall.detection import Action, PolicyDecision
from ai_firewall.detection_adapters import DictionaryDetector, RegexChecksumDetector


class BoundedRegex:
    def __init__(self,entity,pattern):
        self.name='regex-'+entity; self.entity=entity; self.pattern=regex.compile(pattern)
    def detect(self,text,*,language):
        from ai_firewall.detection import DetectionResult
        return [DetectionResult(self.entity,m.start(),m.end(),.8,self.name)
                for m in self.pattern.finditer(text,timeout=.05) if m.end()>m.start()]


class YAMLPolicy:
    def __init__(self,path):
        try:
            content=Path(path).read_text()
            if len(content)>65536: raise ValueError()
            data=yaml.safe_load(content)
            if set(data)!={'version','rules','dictionaries','regex'} or not isinstance(data['version'],str) or not data['version']:
                raise ValueError()
            self.version=data['version']; self.rules={}
            if (not isinstance(data['rules'],list) or not 1<=len(data['rules'])<=128
                    or not isinstance(data['dictionaries'],dict) or len(data['dictionaries'])>32
                    or not isinstance(data['regex'],list) or len(data['regex'])>32): raise ValueError()
            for rule in data['rules']:
                if (set(rule)-{'entity','action','threshold','enabled'} or not {'entity','action','threshold'}<=set(rule)
                        or type(rule.get('enabled',True)) is not bool or not isinstance(rule['entity'],str)
                        or not regex.fullmatch('[A-Z][A-Z0-9_]{0,63}',rule['entity'])
                        or rule['entity'] in self.rules or type(rule['threshold']) not in {int,float}
                        or not 0<=rule['threshold']<=1):
                    raise ValueError()
                self.rules[rule['entity']]=(Action(rule['action']) if rule.get('enabled',True) else Action.ALLOW,rule['threshold'])
            self.detectors=[]
            for name,terms in data['dictionaries'].items():
                if (name not in self.rules or not isinstance(terms,list) or not 1<=len(terms)<=1000
                        or any(not isinstance(t,str) or not 1<=len(t)<=256 for t in terms)): raise ValueError()
                self.detectors.append(DictionaryDetector('dictionary-'+name,terms,name))
            for rule in data['regex']:
                if set(rule)!={'entity','pattern'}: raise ValueError()
                if rule['entity'] not in self.rules or not isinstance(rule['pattern'],str) or len(rule['pattern'])>1024: raise ValueError()
                self.detectors.append(BoundedRegex(rule['entity'],rule['pattern']))
        except Exception:
            raise ValueError('invalid_pii_policy') from None

    def evaluate(self,spans,context):
        if context.policy_version!=self.version or context.operation not in {'input','output','chat-write','model-request','settings'}:
            raise ValueError('invalid_policy_context')
        rank={Action.ALLOW:0,Action.MASK:1,Action.REVIEW:2,Action.BLOCK:3}
        verdict=Action.ALLOW; selected=[]
        for span in spans:
            actions=[]
            for finding in span.findings:
                # Unknown categories fail closed rather than silently ALLOW.
                action,threshold=self.rules.get(finding.entity_type,(Action.REVIEW,0))
                if finding.confidence>=threshold: actions.append(action)
            if actions:
                action=max(actions,key=rank.get)
                verdict=max((verdict,action),key=rank.get)
                if action!=Action.ALLOW: selected.append(span)
        return PolicyDecision(verdict,tuple(selected),self.version)


def inspect_object(fields,pipeline,policy,context):
    """Full object verdict first; caller must not persist before this returns.

    Detection-only boundary: intentionally no Vault callback accepted.
    """
    decisions={name:policy.evaluate(pipeline.inspect(value),context) for name,value in fields.items()}
    rank={Action.ALLOW:0,Action.MASK:1,Action.REVIEW:2,Action.BLOCK:3}
    return max((d.action for d in decisions.values()),key=rank.get,default=Action.ALLOW),decisions