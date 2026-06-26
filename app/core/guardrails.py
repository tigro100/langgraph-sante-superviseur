import json
import re
from typing import Any

CERTAINTY_PATTERNS = [
    r'\bvous avez\b',
    r'\btu as\b',
    r'\bc[’\']est forcément\b',
    r'\bdiagnostic certain\b',
    r'\bje confirme que\b',
]
SOURCE_PATTERNS = [
    r'\bselon une étude\b',
    r'\bsource externe\b',
    r'\bpublié dans\b',
    r'\boms\b',
]


def extract_json(text: str | None) -> dict[str, Any]:
    if not text:
        return {}
    raw = text.strip()
    try:
        return json.loads(raw)
    except Exception:
        pass
    match = re.search(r'\{.*\}', raw, flags=re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            return {}
    return {}


def fallback_supervisor_decision(patient_input: str) -> dict[str, Any]:
    text = patient_input.lower()
    red_flags = []
    emergency_terms = ['douleur thoracique', 'oppression', 'essoufflement sévère', 'detresse', 'détresse', 'perte de connaissance', 'faiblesse d\'un côté', 'confusion', 'saignement important']
    if any(term in text for term in emergency_terms):
        red_flags.append('signe d’urgence possible')
        return {
            'selected_agent': 'URGENCE',
            'risk_level': 'EMERGENCY',
            'reason': 'Mots-clés d’urgence détectés par fallback local.',
            'red_flags_detected': red_flags,
            'missing_questions': [],
        }
    if any(term in text for term in ['poitrine', 'coeur', 'cœur', 'palpitation', 'tension', 'hypertension']):
        return {
            'selected_agent': 'CARDIOLOGUE',
            'risk_level': 'MEDIUM',
            'reason': 'Symptômes potentiellement cardio détectés par fallback local.',
            'red_flags_detected': red_flags,
            'missing_questions': ['âge', 'durée', 'intensité', 'antécédents'],
        }
    if any(term in text for term in ['cancer', 'chimio', 'chimiothérapie', 'immunothérapie', 'oncologie']):
        return {
            'selected_agent': 'CANCEROLOGUE',
            'risk_level': 'MEDIUM',
            'reason': 'Contexte oncologique détecté par fallback local.',
            'red_flags_detected': red_flags,
            'missing_questions': ['traitement en cours', 'fièvre', 'état général'],
        }
    return {
        'selected_agent': 'GENERALISTE',
        'risk_level': 'LOW',
        'reason': 'Aucun signe spécifique critique détecté par fallback local.',
        'red_flags_detected': red_flags,
        'missing_questions': ['durée des symptômes', 'âge', 'antécédents'],
    }


def normalize_decision(llm_text: str, patient_input: str) -> dict[str, Any]:
    decision = extract_json(llm_text) or fallback_supervisor_decision(patient_input)
    selected_agent = str(decision.get('selected_agent') or '').upper().strip()
    risk_level = str(decision.get('risk_level') or '').upper().strip()
    valid_agents = {'GENERALISTE', 'CARDIOLOGUE', 'CANCEROLOGUE', 'URGENCE'}
    valid_risks = {'LOW', 'MEDIUM', 'HIGH', 'EMERGENCY'}
    fallback = fallback_supervisor_decision(patient_input)
    if selected_agent not in valid_agents:
        selected_agent = fallback['selected_agent']
    if risk_level not in valid_risks:
        risk_level = fallback['risk_level']
    return {
        'selected_agent': selected_agent,
        'risk_level': risk_level,
        'reason': str(decision.get('reason') or fallback.get('reason') or ''),
        'red_flags_detected': decision.get('red_flags_detected') if isinstance(decision.get('red_flags_detected'), list) else fallback.get('red_flags_detected', []),
        'missing_questions': decision.get('missing_questions') if isinstance(decision.get('missing_questions'), list) else fallback.get('missing_questions', []),
    }


def detect_hallucination_risk(answer: str, rag_context: str) -> bool:
    lower = (answer or '').lower()
    if any(re.search(pattern, lower) for pattern in CERTAINTY_PATTERNS):
        return True
    if any(re.search(pattern, lower) for pattern in SOURCE_PATTERNS) and 'source interne' not in lower:
        return True
    if ('je ne remplace pas un médecin' not in lower) and ('urgence' not in lower):
        return True
    # Si le modèle cite des références externes non présentes dans le RAG interne.
    if re.search(r'\[[0-9]+\]|https?://|doi:', lower):
        return True
    return False


def build_blocked_message(patient_input: str, safe_response: str, decision: dict[str, Any]) -> str:
    payload = {
        'human_review_required': True,
        'status': 'BLOCKED_BEFORE_PATIENT_OUTPUT',
        'reason': 'Validation humaine requise avant envoi au patient.',
        'selected_agent': decision.get('selected_agent'),
        'risk_level': decision.get('risk_level'),
        'supervisor_reason': decision.get('reason'),
        'red_flags_detected': decision.get('red_flags_detected', []),
        'patient_input': patient_input,
        'draft_response_to_review': safe_response,
        'instruction': 'Renseigner Human Review puis relancer avec APPROVED_BY_HUMAN, EDITED_BY_HUMAN ou REJECT_AND_ESCALATE.',
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
