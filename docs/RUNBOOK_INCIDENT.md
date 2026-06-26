# Runbook incident

## Types d'incidents suivis

- Erreur d'appel Groq.
- Latence élevée.
- Coût élevé.
- Risque hallucination.
- Validation humaine requise mais non faite.

## Étapes de diagnostic

1. Ouvrir `/dashboard`.
2. Identifier le `correlation_id` concerné.
3. Consulter `/api/runs/{correlation_id}`.
4. Vérifier les nœuds en erreur dans `trace.nodes`.
5. Vérifier les alertes `technical_alerts`.
6. Appliquer l'action adaptée.

## Actions correctives

### Erreur Groq

- Vérifier `GROQ_API_KEY`.
- Vérifier `GROQ_MODEL`.
- Vérifier les quotas Groq.
- Basculer temporairement `MOCK_LLM=true` pour continuer la démo.

### Latence élevée

- Diminuer `max_tokens`.
- Réduire la taille du contexte RAG.
- Utiliser un modèle plus léger.

### Coût élevé

- Ajuster `TOKEN_PRICE_INPUT_1M` et `TOKEN_PRICE_OUTPUT_1M`.
- Réduire le nombre de tokens max.

### Risque hallucination

- Vérifier la réponse.
- Envoyer un feedback via `/api/feedback`.
- Renforcer le prompt sécurité.
- Ajouter une validation humaine obligatoire.
