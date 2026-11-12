from ai_firewall.detection_v2 import ExtendedRecognizer,ogrn_valid
from ai_firewall.pii_engine import RussianRecognizer,inn_valid,snils_valid
from ai_firewall.synthetic_v2 import fixtures,permitted_values


def test_generated_checksums_and_boundary():
    for row in fixtures():
        assert inn_valid(row['RU_INN'])
        assert snils_valid(row['RU_SNILS'])
        assert ogrn_valid(row['RU_OGRN']) and ogrn_valid(row['RU_OGRNIP'])
    assert 'arbitrary real value' not in permitted_values()


def test_secret_and_context_detectors():
    detector=ExtendedRecognizer()
    examples={'API_KEY':'api_key=sk-test-'+'x'*32,'PASSWORD':'password=not-a-real-password',
        'BEARER_TOKEN':'Bearer '+'x'*32,'CONNECTION_STRING':'postgresql://test:fake@example.invalid/db',
        'PRIVATE_KEY':'-----BEGIN PRIVATE KEY-----\nFAKE\n-----END PRIVATE KEY-----',
        'DATE_OF_BIRTH':'дата рождения: 01.01.1990',
        'POSTAL_ADDRESS':'адрес: г. Тестоград, ул. Учебная, д. 1'}
    for category,text in examples.items():
        assert category in {r.entity_type for r in detector.detect(text,language='ru')}
    assert not detector.detect('обычное сообщение без персональных данных',language='ru')