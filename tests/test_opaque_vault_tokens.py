from ai_firewall.detection import DetectorPipeline
from ai_firewall.pii_engine import RussianRecognizer


def test_luhn_inside_canonical_token_is_not_remasked():
    pipeline=DetectorPipeline([RussianRecognizer()])
    card='4111111111111111'
    token='[V2_'+'a'*20+card+'b'*28+']'
    assert not pipeline.inspect(token)
    assert pipeline.inspect(token+' '+card)
    assert pipeline.inspect('[V2_'+card+']')