import unicodedata
import pytest
from ai_firewall.person_names import PersonNames
from ai_firewall.pii_engine import NormalizedDetector
from ai_firewall.detection import DetectorPipeline


@pytest.fixture(scope='module')
def pipeline():
    return DetectorPipeline([NormalizedDetector(PersonNames())])


@pytest.mark.parametrize('name',[
    'Иванов Иван Иванович','иванов иван иванович','ИВАНОВ ИВАН ИВАНОВИЧ',
    'Иванов иван Иванович','иванова ивана ивановича','петровой анне сергеевне',
    'Анна Петрова','Петрова А. С.','Иванов-Петров Иван Сергеевич',
    'иванов   иван\tиванович',unicodedata.normalize('NFD','Семёнов Пётр Сергеевич')])
def test_full_original_span(pipeline,name):
    text='Запись: '+name+'; готово'
    spans=pipeline.inspect(text)
    assert any(text[s.start:s.end]==name for s in spans)


@pytest.mark.parametrize('text',[
    'новый сотрудник прошёл собеседование','отдел кадров готовит документы',
    'главный инженер закончил работу','доставка заказа назначена на завтра',
    'любовь к работе','вера в успех','надежда на завтра','ООО Новый Вектор'])
def test_negative(pipeline,text):
    assert not pipeline.inspect(text)


def test_opaque(pipeline):
    assert not pipeline.inspect('[V2_'+'1234567890abcdef'*4+']')