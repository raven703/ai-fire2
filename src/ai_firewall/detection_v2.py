"""Local bounded signatures and contextual recognizers; no network validation."""
import base64
import datetime
import ipaddress
import json
import re

from ai_firewall.detection import DetectionResult


def ogrn_valid(value):
    return (value.isascii() and value.isdigit() and len(value) in (13,15)
            and len(set(value))>1
            and int(value[:-1]) % (11 if len(value)==13 else 13) % 10 == int(value[-1]))


def birthday_valid(value):
    try:
        date=datetime.datetime.strptime(value,'%d.%m.%Y').date()
        return 1900<=date.year<=datetime.date.today().year
    except ValueError:
        return False


def jwt_valid(value):
    try:
        parts=value.split('.')
        header=json.loads(base64.urlsafe_b64decode(parts[0]+'='*(-len(parts[0])%4)))
        payload=json.loads(base64.urlsafe_b64decode(parts[1]+'='*(-len(parts[1])%4)))
        return isinstance(header,dict) and isinstance(payload,dict) and 'alg' in header
    except (ValueError,TypeError,UnicodeError):
        return False


class ExtendedRecognizer:
    name='local-v2-context'
    rules=(
        ('RU_OGRN',r'(?i)\bогрн\s*[:№]?\s*(?P<v>[0-9]{13})(?![0-9])',ogrn_valid),
        ('RU_OGRNIP',r'(?i)\bогрнип\s*[:№]?\s*(?P<v>[0-9]{15})(?![0-9])',ogrn_valid),
        ('DATE_OF_BIRTH',r'(?i)(?:дата\s+рождения|родил(?:ся|ась)|д[./]р)\s*[:=]?\s*(?P<v>[0-9]{2}\.[0-9]{2}\.[0-9]{4})',birthday_valid),
        ('POSTAL_ADDRESS',r'(?i)\bадрес\s*[:=]\s*(?P<v>(?:г\.\s*)?[А-Яа-яЁё -]{2,40},\s*(?:ул\.|улица)\s*[А-Яа-яЁё0-9 -]{2,60},\s*(?:д\.|дом)\s*[0-9]{1,4}(?:,\s*кв\.\s*[0-9]{1,4})?)',lambda _:True),
        ('JWT',r'(?<![\w])(?P<v>eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)(?![\w])',jwt_valid),
        ('BEARER_TOKEN',r'(?i)\bBearer\s+(?P<v>[A-Za-z0-9._~+/-]{16,}={0,2})',lambda _:True),
        ('API_KEY',r'(?i)\b(?:api[_-]?key|access[_-]?token|secret[_-]?key|aws_secret_access_key)\s*[=:]\s*[\x22\x27]?(?P<v>[A-Za-z0-9_./+=-]{16,200})',lambda _:True),
        ('API_KEY',r'(?<!\w)(?P<v>(?:AKIA[A-Z0-9]{16}|ghp_[A-Za-z0-9]{36}|sk-(?:test-)?[A-Za-z0-9_-]{20,}))(?!\w)',lambda _:True),
        ('PASSWORD',r'(?i)\b(?:password|passwd|pwd|пароль)\s*[=:]\s*[\x22\x27]?(?P<v>[^\s\x22\x27,;]{4,200})',lambda _:True),
        ('CONNECTION_STRING',r'(?i)(?P<v>(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|mssql)://[^\s/:]+:[^\s@]+@[^\s\x22\x27]+)',lambda _:True),
        ('PRIVATE_KEY',r'(?P<v>-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----[\s\S]{0,16000}?-----END (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----)',lambda _:True),
    )

    def detect(self,text,*,language):
        findings=[]
        for kind,pattern,validator in self.rules:
            for match in re.finditer(pattern,text):
                if validator(match.group('v')):
                    findings.append(DetectionResult(kind,match.start('v'),match.end('v'),.9,self.name))
        return findings