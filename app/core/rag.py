import math
import re
from collections import Counter
from difflib import SequenceMatcher

DEFAULT_MEDICAL_KB = """
[GENERAL] En cas de symptômes légers non spécifiques, l'assistant peut expliquer les possibilités générales, poser des questions utiles, recommander une consultation non urgente si les symptômes persistent, et rappeler qu'il ne remplace pas un médecin.
---
[URGENCE] Douleur thoracique intense ou oppressive, essoufflement sévère, malaise, perte de connaissance, faiblesse d'un côté du corps, confusion brutale, saignement important, fièvre très élevée, réaction allergique grave, détresse respiratoire: recommander immédiatement les urgences locales ou le SAMU/112/15 selon le pays.
---
[CARDIOLOGIE] Palpitations, douleur thoracique, essoufflement à l'effort, œdèmes des jambes, tension artérielle très élevée ou très basse, malaise, antécédents d'infarctus, insuffisance cardiaque ou arythmie doivent être orientés prudemment vers un avis médical, surtout si symptômes nouveaux, sévères ou associés à douleur thoracique.
---
[ONCOLOGIE] Patient sous chimiothérapie ou immunothérapie avec fièvre, frissons, essoufflement, saignement, diarrhée sévère, vomissements persistants, douleur importante ou altération de l'état général: recommander de contacter rapidement l'équipe d'oncologie ou les urgences. Ne jamais modifier un traitement anticancéreux sans avis médical.
---
[SECURITE] L'assistant ne pose pas de diagnostic définitif, ne prescrit pas, ne modifie pas un traitement, et conseille une consultation médicale lorsque les symptômes sont inquiétants, persistants, nouveaux ou aggravés.
""".strip()

STOPWORDS = set("""
le la les un une des du de d et ou mais donc car ni que qui quoi dont où a au aux en dans sur sous pour par avec sans ce cette ces je tu il elle nous vous ils elles mon ma mes ton ta tes son sa ses notre votre leur leurs est sont ai as avez ont être avoir très plus moins pas ne n me m se s c l y symptome symptomes douleur douleurs depuis depuis combien fois jour jours semaine semaines mois mal j ai jai j'ai
""".split())

SYNONYMS = {
    'coeur': ['cardiaque', 'cardio', 'thoracique', 'poitrine', 'palpitation', 'palpitations', 'tension', 'essoufflement', 'malaise'],
    'poitrine': ['thoracique', 'douleur thoracique', 'oppression', 'cardiaque', 'coeur'],
    'cancer': ['oncologie', 'tumeur', 'chimiotherapie', 'chimio', 'immunotherapie', 'radiotherapie', 'metastase'],
    'fievre': ['température', 'infection', 'frissons', 'urgence', 'chimiotherapie'],
    'urgence': ['grave', 'intense', 'sévère', 'respiration', 'saignement', 'malaise', 'perte de connaissance', 'confusion'],
    'tension': ['hypertension', 'hypotension', 'pression arterielle', 'cardio', 'malaise'],
    'respiration': ['essoufflement', 'dyspnee', 'souffle', 'urgence', 'thoracique'],
}


def norm(text: str) -> str:
    text = (text or '').lower()
    replacements = {'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e', 'à': 'a', 'â': 'a', 'î': 'i', 'ï': 'i', 'ô': 'o', 'ù': 'u', 'û': 'u', 'ç': 'c'}
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return text


def tokens(text: str) -> list[str]:
    toks = re.findall(r'[a-zA-Z0-9]+', norm(text))
    return [t for t in toks if len(t) > 2 and t not in STOPWORDS]


def expand(tokens_: list[str]) -> list[str]:
    expanded = list(tokens_)
    norm_syn = {norm(k): [norm(x) for x in v] for k, v in SYNONYMS.items()}
    for token in tokens_:
        if token in norm_syn:
            expanded.extend(norm_syn[token])
        for key, values in norm_syn.items():
            if token in values:
                expanded.append(key)
                expanded.extend(values)
    return expanded


def chunks(text: str) -> list[str]:
    raw = [c.strip() for c in re.split(r'\n\s*---\s*\n', text or '') if c.strip()]
    return raw or ([text] if text else [])


def keyword_score(q_tokens: list[str], d_tokens: list[str]) -> float:
    if not q_tokens or not d_tokens:
        return 0.0
    dc = Counter(d_tokens)
    score = 0.0
    for token in q_tokens:
        if token in dc:
            score += 1.0 + math.log(1 + dc[token])
    return score / max(1.0, math.sqrt(len(d_tokens)))


def semantic_score(q_expanded: list[str], doc_text: str) -> float:
    doc_norm = norm(doc_text)
    score = 0.0
    for term in set(q_expanded):
        if len(term) > 2 and term in doc_norm:
            score += 1.0
    ratio = SequenceMatcher(None, ' '.join(q_expanded)[:300], doc_norm[:600]).ratio()
    return (score / max(1.0, len(set(q_expanded)))) + ratio


def retrieve_context(question: str, knowledge_base: str = DEFAULT_MEDICAL_KB, top_k: int = 4, keyword_weight: float = 0.55, semantic_weight: float = 0.45, include_scores: bool = True) -> str:
    q_tokens = tokens(question)
    q_expanded = expand(q_tokens)
    rows: list[tuple[float, float, float, int, str]] = []
    for i, chunk in enumerate(chunks(knowledge_base), start=1):
        d_tokens = tokens(chunk)
        k_score = keyword_score(q_tokens, d_tokens)
        s_score = semantic_score(q_expanded, chunk)
        final = keyword_weight * k_score + semantic_weight * s_score
        rows.append((final, k_score, s_score, i, chunk))
    rows.sort(key=lambda x: x[0], reverse=True)
    selected = rows[: int(top_k or 4)]
    if not selected:
        return 'Aucun contexte RAG disponible. Utiliser uniquement les règles de sécurité médicale.'
    lines = ['CONTEXTE RAG HYBRIDE — sources internes sélectionnées:']
    for final, k_score, s_score, idx, chunk in selected:
        if include_scores:
            lines.append(f'[Source interne {idx} | score={final:.3f} | keyword={k_score:.3f} | semantic={s_score:.3f}]\n{chunk}')
        else:
            lines.append(f'[Source interne {idx}]\n{chunk}')
    return '\n\n'.join(lines)
