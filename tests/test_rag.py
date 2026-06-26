from app.core.rag import retrieve_context


def test_rag_returns_emergency_context_for_chest_pain():
    ctx = retrieve_context('douleur thoracique et essoufflement depuis ce matin')
    assert 'CONTEXTE RAG HYBRIDE' in ctx
    assert '[URGENCE]' in ctx or '[CARDIOLOGIE]' in ctx


def test_rag_has_scores():
    ctx = retrieve_context('palpitations et tension élevée')
    assert 'score=' in ctx
