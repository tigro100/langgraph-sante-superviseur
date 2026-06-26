# Agent Card — Chatbot Santé Supervisé

## Nom

LangGraph Santé Supervisé

## Finalité

Assistant conversationnel pédagogique capable d'orienter prudemment une demande santé vers un agent interne : généraliste, cardiologue, cancérologue ou urgence.

## Capacités

- Comprendre une demande patient en français.
- Récupérer un contexte RAG interne.
- Router vers un agent spécialiste.
- Produire une réponse prudente.
- Déclencher une validation humaine sur les cas à risque.
- Suivre les KPI techniques par correlation ID.

## Limites

- Ne pose pas de diagnostic définitif.
- Ne prescrit pas de médicament.
- Ne modifie pas un traitement.
- Ne remplace pas un médecin.
- Le RAG fourni est minimal et doit être remplacé par des protocoles validés.

## Données manipulées

- Texte saisi par l'utilisateur.
- Historique de conversation local.
- Traces techniques : latence, tokens, coût, erreurs, alertes.

## Supervision humaine

Le mode par défaut `AUTO_LOW_RISK_ONLY` bloque MEDIUM/HIGH/EMERGENCY avant sortie patient.

## Observabilité

Chaque exécution reçoit un `correlation_id` unique. Les métriques sont visibles dans `/dashboard`.
