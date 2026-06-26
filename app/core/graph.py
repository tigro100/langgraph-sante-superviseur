import json
import time
import uuid
from typing import Any, TypedDict

from app.core import db
from app.core.guardrails import build_blocked_message, detect_hallucination_risk, normalize_decision
from app.core.llm import call_groq
from app.core.monitoring import ExecutionTelemetry, technical_supervisor_alerts
from app.core.prompts import SAFETY_PROMPT, SPECIALIST_PROMPT, SUPERVISOR_PROMPT
from app.core.rag import retrieve_context

try:
    from langgraph.graph import END, START, StateGraph
except Exception:  # pragma: no cover - utile seulement si les dépendances ne sont pas encore installées
    END = '__end__'
    START = '__start__'
    StateGraph = None


class MedicalState(TypedDict, total=False):
    session_id: str
    patient_input: str
    review_mode: str
    human_review: str
    reviewer_name: str
    correlation_id: str
    telemetry: ExecutionTelemetry
    chat_history: str
    rag_context: str
    supervisor_raw: str
    supervisor_decision: dict[str, Any]
    agent_response: str
    safe_response: str
    final_response: str
    hallucination_risk: bool
    human_review_required: bool
    technical_alerts: list[str]
    status: str


def timed_node(node_name: str):
    def decorator(func):
        def wrapper(state: MedicalState) -> dict[str, Any]:
            telemetry = state['telemetry']
            started = time.perf_counter()
            try:
                result = func(state)
                # Les nœuds LLM ajoutent déjà leur propre trace avec usage tokens.
                if not node_name.endswith('_llm'):
                    telemetry.add_node(node_name, int((time.perf_counter() - started) * 1000))
                return result
            except Exception as exc:  # noqa: BLE001
                telemetry.add_node(node_name, int((time.perf_counter() - started) * 1000), status='ERROR', error=str(exc))
                return {'status': 'ERROR', 'final_response': f'Erreur technique dans {node_name}: {exc}'}
        return wrapper
    return decorator


@timed_node('initialisation_monitoring')
def init_monitoring_node(state: MedicalState) -> dict[str, Any]:
    return {
        'correlation_id': state.get('correlation_id') or state['telemetry'].correlation_id,
        'session_id': state.get('session_id') or str(uuid.uuid4()),
    }


@timed_node('memoire_conversation')
def load_history_node(state: MedicalState) -> dict[str, Any]:
    history = db.get_history(state['session_id'], limit=8)
    return {'chat_history': history}


@timed_node('rag_hybride_medical')
def rag_node(state: MedicalState) -> dict[str, Any]:
    return {'rag_context': retrieve_context(state['patient_input'])}


def supervisor_node(state: MedicalState) -> dict[str, Any]:
    prompt = SUPERVISOR_PROMPT.format(
        CHAT_HISTORY=state.get('chat_history', ''),
        PATIENT_INPUT=state['patient_input'],
        RAG_CONTEXT=state.get('rag_context', ''),
    )
    raw = call_groq(prompt, 'superviseur_medical', state['telemetry'], temperature=0.0, max_tokens=700)
    decision = normalize_decision(raw, state['patient_input'])
    return {'supervisor_raw': raw, 'supervisor_decision': decision}


def specialist_node(state: MedicalState) -> dict[str, Any]:
    prompt = SPECIALIST_PROMPT.format(
        SUPERVISOR_DECISION=json.dumps(state.get('supervisor_decision', {}), ensure_ascii=False),
        CHAT_HISTORY=state.get('chat_history', ''),
        PATIENT_INPUT=state['patient_input'],
        RAG_CONTEXT=state.get('rag_context', ''),
    )
    answer = call_groq(prompt, 'agent_specialiste', state['telemetry'], temperature=0.1, max_tokens=1400)
    return {'agent_response': answer}


def safety_node(state: MedicalState) -> dict[str, Any]:
    prompt = SAFETY_PROMPT.format(
        PATIENT_INPUT=state['patient_input'],
        SUPERVISOR_DECISION=json.dumps(state.get('supervisor_decision', {}), ensure_ascii=False),
        AGENT_RESPONSE=state.get('agent_response', ''),
    )
    answer = call_groq(prompt, 'controle_securite', state['telemetry'], temperature=0.0, max_tokens=1000)
    risk = detect_hallucination_risk(answer, state.get('rag_context', ''))
    return {'safe_response': answer, 'hallucination_risk': risk}


@timed_node('gate_hitl_medical')
def hitl_node(state: MedicalState) -> dict[str, Any]:
    decision = state.get('supervisor_decision', {})
    risk_level = str(decision.get('risk_level', 'LOW')).upper()
    selected_agent = str(decision.get('selected_agent', 'GENERALISTE')).upper()
    review_mode = (state.get('review_mode') or 'AUTO_LOW_RISK_ONLY').upper()
    human_review = (state.get('human_review') or '').strip()
    reviewer = state.get('reviewer_name') or 'Medical reviewer'

    needs_review = risk_level in {'HIGH', 'EMERGENCY'} or selected_agent == 'URGENCE' or risk_level == 'MEDIUM'

    if review_mode == 'REJECT_AND_ESCALATE':
        final = (
            'Votre demande nécessite une prise en charge par un professionnel de santé. '
            "Je ne peux pas envoyer une réponse automatisée dans ce cas. "
            'Veuillez contacter rapidement un médecin, votre équipe de soins, ou les urgences si les symptômes sont graves ou s’aggravent.'
        )
        if human_review:
            final += f'\n\nNote du validateur: {human_review}'
        final += f'\n\n---\nTrace HITL: rejected_and_escalated | reviewer={reviewer} | risk={risk_level} | agent={selected_agent}'
        return {'final_response': final, 'human_review_required': True, 'status': 'SUCCESS'}

    if review_mode == 'EDITED_BY_HUMAN':
        if not human_review:
            return {'final_response': build_blocked_message(state['patient_input'], state.get('safe_response', ''), decision), 'human_review_required': True, 'status': 'SUCCESS'}
        final = human_review + f'\n\n---\nTrace HITL: edited_by_human | reviewer={reviewer} | risk={risk_level} | agent={selected_agent}'
        return {'final_response': final, 'human_review_required': False, 'status': 'SUCCESS'}

    if review_mode == 'APPROVED_BY_HUMAN':
        final = state.get('safe_response') or 'Réponse vide après contrôle sécurité. Validation humaine requise.'
        if human_review:
            final += f'\n\nNote de validation: {human_review}'
        final += f'\n\n---\nTrace HITL: approved_by_human | reviewer={reviewer} | risk={risk_level} | agent={selected_agent}'
        return {'final_response': final, 'human_review_required': False, 'status': 'SUCCESS'}

    if needs_review:
        return {'final_response': build_blocked_message(state['patient_input'], state.get('safe_response', ''), decision), 'human_review_required': True, 'status': 'SUCCESS'}

    final = state.get('safe_response') or (
        "Je ne remplace pas un médecin. Je n'ai pas assez d'éléments pour répondre de façon utile. "
        'Merci de préciser vos symptômes, leur durée, votre âge, vos antécédents et traitements.'
    )
    final += f'\n\n---\nTrace HITL: auto_approved_low_risk | reviewer={reviewer} | risk={risk_level} | agent={selected_agent}'
    return {'final_response': final, 'human_review_required': False, 'status': 'SUCCESS'}


@timed_node('agent_supervision_technique')
def technical_supervisor_node(state: MedicalState) -> dict[str, Any]:
    alerts = technical_supervisor_alerts(state['telemetry'], bool(state.get('hallucination_risk')))
    return {'technical_alerts': alerts}


@timed_node('persistance_observabilite')
def persist_node(state: MedicalState) -> dict[str, Any]:
    telemetry = state['telemetry']
    decision = state.get('supervisor_decision', {})
    db.add_message(state['session_id'], 'User', state['patient_input'])
    db.add_message(state['session_id'], 'Assistant', state.get('final_response', ''))
    payload = {
        'correlation_id': telemetry.correlation_id,
        'session_id': state['session_id'],
        'status': 'ERROR' if telemetry.error_count else state.get('status', 'SUCCESS'),
        'selected_agent': decision.get('selected_agent'),
        'risk_level': decision.get('risk_level'),
        'latency_ms': telemetry.latency_ms,
        'token_input': telemetry.token_input,
        'token_output': telemetry.token_output,
        'cost_usd': telemetry.cost_usd,
        'error_count': telemetry.error_count,
        'hallucination_risk': state.get('hallucination_risk', False),
        'human_review_required': state.get('human_review_required', False),
        'technical_alerts': state.get('technical_alerts', []),
        'trace': telemetry.trace_dict(),
        'user_message': state['patient_input'],
        'answer': state.get('final_response', ''),
    }
    db.save_execution(payload)
    return {'status': payload['status']}


def build_graph():
    if StateGraph is None:
        raise RuntimeError('LangGraph n\'est pas installé. Exécute: pip install -r requirements.txt')
    builder = StateGraph(MedicalState)
    builder.add_node('initialisation_monitoring', init_monitoring_node)
    builder.add_node('memoire_conversation', load_history_node)
    builder.add_node('rag_hybride_medical', rag_node)
    builder.add_node('superviseur_medical', supervisor_node)
    builder.add_node('agent_specialiste', specialist_node)
    builder.add_node('controle_securite', safety_node)
    builder.add_node('gate_hitl_medical', hitl_node)
    builder.add_node('agent_supervision_technique', technical_supervisor_node)
    builder.add_node('persistance_observabilite', persist_node)

    builder.add_edge(START, 'initialisation_monitoring')
    builder.add_edge('initialisation_monitoring', 'memoire_conversation')
    builder.add_edge('memoire_conversation', 'rag_hybride_medical')
    builder.add_edge('rag_hybride_medical', 'superviseur_medical')
    builder.add_edge('superviseur_medical', 'agent_specialiste')
    builder.add_edge('agent_specialiste', 'controle_securite')
    builder.add_edge('controle_securite', 'gate_hitl_medical')
    builder.add_edge('gate_hitl_medical', 'agent_supervision_technique')
    builder.add_edge('agent_supervision_technique', 'persistance_observabilite')
    builder.add_edge('persistance_observabilite', END)
    return builder.compile()


def run_medical_graph(message: str, session_id: str | None = None, review_mode: str = 'AUTO_LOW_RISK_ONLY', human_review: str | None = None, reviewer_name: str | None = 'Medical reviewer') -> dict[str, Any]:
    telemetry = ExecutionTelemetry()
    initial_state: MedicalState = {
        'session_id': session_id or str(uuid.uuid4()),
        'patient_input': message,
        'review_mode': review_mode,
        'human_review': human_review or '',
        'reviewer_name': reviewer_name or 'Medical reviewer',
        'correlation_id': telemetry.correlation_id,
        'telemetry': telemetry,
    }
    graph = build_graph()
    final_state = graph.invoke(initial_state)
    decision = final_state.get('supervisor_decision', {})
    return {
        'correlation_id': telemetry.correlation_id,
        'session_id': final_state['session_id'],
        'answer': final_state.get('final_response', ''),
        'selected_agent': decision.get('selected_agent'),
        'risk_level': decision.get('risk_level'),
        'status': final_state.get('status', 'SUCCESS'),
        'human_review_required': bool(final_state.get('human_review_required', False)),
        'latency_ms': telemetry.latency_ms,
        'cost_usd': round(telemetry.cost_usd, 8),
        'token_input': telemetry.token_input,
        'token_output': telemetry.token_output,
        'hallucination_risk': bool(final_state.get('hallucination_risk', False)),
        'technical_alerts': final_state.get('technical_alerts', []),
        'trace': telemetry.trace_dict(),
    }
