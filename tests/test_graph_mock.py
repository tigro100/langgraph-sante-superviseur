import pytest


@pytest.mark.integration
def test_graph_runs_in_mock_mode(monkeypatch, tmp_path):
    pytest.importorskip('langgraph')
    monkeypatch.setenv('MOCK_LLM', 'true')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'obs.db'))
    from app.core.graph import run_medical_graph

    result = run_medical_graph('J ai mal à la tête depuis hier', session_id='test-session')
    assert result['correlation_id']
    assert result['answer']
    assert result['latency_ms'] >= 0
    assert result['token_input'] > 0
