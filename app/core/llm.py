import time
from typing import Any

from app.core.config import get_settings
from app.core.guardrails import fallback_supervisor_decision
from app.core.monitoring import ExecutionTelemetry


def _mock_response(prompt: str, node_name: str) -> tuple[str, dict[str, int]]:
    """Réponses déterministes pour les tests, la démo et le mode sans clé API."""
    words = prompt.split()
    usage = {'prompt_tokens': max(1, len(words)), 'completion_tokens': 120}
    lower = prompt.lower()
    if node_name == 'superviseur_medical':
        decision = fallback_supervisor_decision(lower)
        import json
        return json.dumps(decision, ensure_ascii=False), usage
    if node_name == 'agent_specialiste':
        if 'urgence' in lower or 'douleur thoracique' in lower:
            return (
                "1. Je comprends que les symptômes décrits peuvent être inquiétants.\n"
                "2. L'orientation prioritaire est une évaluation médicale rapide.\n"
                "3. Surveillez l'essoufflement, la douleur thoracique, le malaise ou la confusion.\n"
                "4. En cas de symptôme sévère ou aggravation, contactez les urgences locales immédiatement.\n"
                "5. Questions utiles: âge, durée, intensité, antécédents, traitements."
            ), usage
        return (
            "1. Je comprends votre demande.\n"
            "2. L'orientation semble plutôt généraliste, à confirmer par un professionnel.\n"
            "3. Surveillez l'évolution, la fièvre, la douleur et les signes inhabituels.\n"
            "4. Consultez rapidement si les symptômes s'aggravent ou persistent.\n"
            "5. Questions utiles: durée, âge, antécédents, traitements en cours."
        ), usage
    return (
        "Je ne remplace pas un médecin. D'après les éléments fournis, il faut rester prudent. "
        "Surveillez l'évolution des symptômes et contactez un professionnel de santé si cela persiste, "
        "s'aggrave, ou s'il existe un signe d'alerte. En cas de douleur thoracique, détresse respiratoire, "
        "malaise ou confusion, contactez les urgences locales immédiatement."
    ), usage


def call_groq(prompt: str, node_name: str, telemetry: ExecutionTelemetry, temperature: float = 0.0, max_tokens: int = 1200) -> str:
    settings = get_settings()
    started = time.perf_counter()
    try:
        if settings.mock_llm or not settings.groq_api_key:
            text, usage = _mock_response(prompt, node_name)
            latency_ms = int((time.perf_counter() - started) * 1000)
            telemetry.add_tokens(usage['prompt_tokens'], usage['completion_tokens'])
            telemetry.add_node(node_name, latency_ms, prompt_tokens=usage['prompt_tokens'], completion_tokens=usage['completion_tokens'])
            return text

        from openai import OpenAI

        client = OpenAI(api_key=settings.groq_api_key, base_url=settings.groq_base_url)
        response = client.chat.completions.create(
            model=settings.groq_model,
            messages=[{'role': 'user', 'content': prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        text = response.choices[0].message.content or ''
        usage_obj: Any = getattr(response, 'usage', None)
        prompt_tokens = int(getattr(usage_obj, 'prompt_tokens', 0) or 0)
        completion_tokens = int(getattr(usage_obj, 'completion_tokens', 0) or 0)
        telemetry.add_tokens(prompt_tokens, completion_tokens)
        telemetry.add_node(node_name, int((time.perf_counter() - started) * 1000), prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
        return text
    except Exception as exc:  # noqa: BLE001 - on veut tracer l'erreur pour le dashboard
        latency_ms = int((time.perf_counter() - started) * 1000)
        telemetry.add_node(node_name, latency_ms, status='ERROR', error=str(exc))
        if node_name == 'superviseur_medical':
            import json
            return json.dumps(fallback_supervisor_decision(prompt), ensure_ascii=False)
        return (
            "Je ne remplace pas un médecin. Un problème technique empêche de produire une réponse complète. "
            "Si les symptômes sont graves, nouveaux ou s'aggravent, contactez immédiatement un professionnel de santé ou les urgences."
        )
