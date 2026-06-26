from app.core.guardrails import detect_hallucination_risk, normalize_decision


def test_normalize_decision_fallback_cardio():
    decision = normalize_decision('pas un json', 'j ai mal à la poitrine et des palpitations')
    assert decision['selected_agent'] in {'CARDIOLOGUE', 'URGENCE'}
    assert decision['risk_level'] in {'MEDIUM', 'HIGH', 'EMERGENCY'}


def test_hallucination_risk_certainty():
    assert detect_hallucination_risk('Vous avez une maladie précise.', '') is True


def test_hallucination_risk_safe_phrase():
    text = 'Je ne remplace pas un médecin. Il faut consulter si cela persiste.'
    assert detect_hallucination_risk(text, '') is False
