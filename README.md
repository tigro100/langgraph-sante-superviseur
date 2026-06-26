# Projet LangGraph — Chatbot santé supervisé + Dashboard observabilité

Ce projet transforme le workflow Langflow `WF_SANTE_UNIQUE_SUPERVISEUR_RAG_GROQ_HITL` en application Python LangGraph avec :

- interface graphique de chat via FastAPI + HTML ;
- API REST `/api/chat` ;
- agent superviseur médical qui route vers GENERALISTE / CARDIOLOGUE / CANCEROLOGUE / URGENCE ;
- RAG hybride médical local repris du workflow Langflow ;
- agent de contrôle sécurité ;
- gate Human-in-the-loop avant sortie patient ;
- agent de supervision technique avec `correlation_id`, latence, tokens, coût, erreurs, risque hallucination ;
- dashboard observabilité `/dashboard` ;
- SQLite local pour les métriques ;
- tests automatisés ;
- Docker, GitHub Actions et Render Blueprint.

> ⚠️ Projet pédagogique. Il ne remplace pas un professionnel de santé.

## 1. Prérequis

- Python 3.11+
- Une clé API Groq
- Docker, si vous voulez tester la conteneurisation

## 2. Installation locale

```bash
cp .env.example .env
# Modifier .env et renseigner GROQ_API_KEY
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Ouvrir ensuite :

- Chat : http://localhost:8000
- Dashboard : http://localhost:8000/dashboard
- API docs : http://localhost:8000/docs

## 3. Mode démo sans clé API

```bash
export MOCK_LLM=true
uvicorn app.main:app --reload --port 8000
```

## 4. Exemple d'appel API

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message":"J ai une douleur thoracique et je respire mal depuis 1 heure",
    "review_mode":"AUTO_LOW_RISK_ONLY"
  }'
```

La réponse contient notamment :

- `correlation_id` : identifiant unique de l'exécution ;
- `latency_ms` : durée totale ;
- `token_input` et `token_output` ;
- `cost_usd` : coût estimé selon les prix configurés ;
- `hallucination_risk` ;
- `human_review_required` ;
- `technical_alerts`.

## 5. Tests automatisés

```bash
pytest -q
```

## 6. Docker local

```bash
docker build -t langgraph-sante-superviseur .
docker run --rm -p 8000:8000 --env-file .env langgraph-sante-superviseur
```

## 7. Docker Compose

```bash
docker compose up --build
```

## 8. Déploiement Render

1. Pousser le projet sur GitHub.
2. Dans Render, créer un nouveau Blueprint à partir du repo ou créer un Web Service Docker.
3. Ajouter les variables d'environnement :
   - `GROQ_API_KEY`
   - `GROQ_MODEL`
   - `GROQ_BASE_URL`
   - `TOKEN_PRICE_INPUT_1M`
   - `TOKEN_PRICE_OUTPUT_1M`
4. Déployer.

Le fichier `render.yaml` est déjà fourni.

## 9. Mapping Langflow vers LangGraph

| Langflow | LangGraph |
|---|---|
| ChatInput-MED01 | Entrée API `/api/chat` + UI chat |
| Memory-MED02 | SQLite `messages` + `memoire_conversation` |
| MedicalHybridRAG-MED10 | `rag_hybride_medical` |
| Prompt-SUP01 + Groq-SUP02 | `superviseur_medical` |
| Prompt-AGENT01 + Groq-AGENT02 | `agent_specialiste` |
| Prompt-SAFE01 + Groq-SAFE02 | `controle_securite` |
| HITL-MED80 | `gate_hitl_medical` |
| ChatOutput-MED99 | Réponse API/UI |
| Nouveau besoin observabilité | `agent_supervision_technique` + dashboard |

## 10. Critères de validation couverts

- Observabilité : correlation ID par exécution, métriques par nœud, coût, tokens, erreurs, latence.
- Tests : dossier `tests/` + GitHub Actions.
- Gouvernance : Agent Card dans `docs/AGENT_CARD.md`.
- Conteneurisation : Dockerfile + docker-compose.
- Déploiement : render.yaml.
- Incident : runbook dans `docs/RUNBOOK_INCIDENT.md`.
- Documentation technique : `docs/ARCHITECTURE.md`.
