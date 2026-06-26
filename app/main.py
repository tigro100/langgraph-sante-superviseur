from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from app.core import db
from app.core.graph import run_medical_graph
from app.core.schemas import ChatRequest, ChatResponse, FeedbackRequest

app = FastAPI(title='LangGraph Santé Supervisé', version='1.0.0')


@app.on_event('startup')
def startup() -> None:
    db.init_db()


@app.get('/health')
def health() -> dict[str, str]:
    return {'status': 'ok'}


@app.post('/api/chat', response_model=ChatResponse)
def chat(payload: ChatRequest) -> ChatResponse:
    result = run_medical_graph(
        message=payload.message,
        session_id=payload.session_id,
        review_mode=payload.review_mode,
        human_review=payload.human_review,
        reviewer_name=payload.reviewer_name,
    )
    return ChatResponse(**result)


@app.get('/api/metrics')
def metrics() -> dict:
    return db.metrics_summary()


@app.get('/api/runs/{correlation_id}')
def run_detail(correlation_id: str) -> dict:
    result = db.get_execution(correlation_id)
    if not result:
        raise HTTPException(status_code=404, detail='Execution not found')
    return result


@app.post('/api/feedback')
def feedback(payload: FeedbackRequest) -> dict[str, str]:
    db.add_feedback(payload.correlation_id, payload.hallucination_reported, payload.comment)
    return {'status': 'saved'}


@app.get('/', response_class=HTMLResponse)
def chat_ui() -> str:
    return """
<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Chatbot santé LangGraph</title>
  <style>
    :root { --blue:#07314a; --yellow:#f7b500; --bg:#f4f7fb; --card:#fff; --muted:#667085; }
    body { font-family: Arial, sans-serif; margin:0; background:var(--bg); color:#101828; }
    header { background:var(--blue); color:white; padding:22px 34px; display:flex; justify-content:space-between; align-items:center; }
    header a { color:var(--yellow); text-decoration:none; margin-left:18px; font-weight:bold; }
    main { max-width:1100px; margin:28px auto; padding:0 18px; display:grid; grid-template-columns: 1.4fr .8fr; gap:20px; }
    .card { background:var(--card); border-radius:16px; padding:20px; box-shadow:0 8px 24px rgba(16,24,40,.08); }
    #messages { height:520px; overflow:auto; border:1px solid #e4e7ec; border-radius:12px; padding:16px; background:#fcfcfd; }
    .msg { padding:12px 14px; border-radius:12px; margin:10px 0; white-space:pre-wrap; line-height:1.45; }
    .user { background:#e8f1ff; margin-left:12%; }
    .bot { background:#fff8df; margin-right:12%; }
    textarea { width:100%; min-height:90px; border-radius:12px; border:1px solid #d0d5dd; padding:12px; font-size:15px; box-sizing:border-box; }
    select,input { width:100%; border-radius:10px; border:1px solid #d0d5dd; padding:10px; margin:6px 0 12px; box-sizing:border-box; }
    button { background:var(--yellow); color:#111827; border:none; padding:12px 18px; border-radius:12px; font-weight:bold; cursor:pointer; }
    button:hover { filter:brightness(.96); }
    .kpi { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
    .kpi div { background:#f9fafb; border:1px solid #eaecf0; border-radius:12px; padding:12px; }
    .muted { color:var(--muted); font-size:13px; }
    .alert { background:#fff1f3; border:1px solid #fecdca; border-radius:12px; padding:10px; color:#b42318; margin-top:8px; }
    @media (max-width:900px){ main{grid-template-columns:1fr;} }
  </style>
</head>
<body>
<header>
  <div><strong>LangGraph Santé Supervisé</strong><div class="muted" style="color:#d0d5dd">Chat + agent de supervision technique + KPI</div></div>
  <nav><a href="/dashboard">Dashboard</a><a href="/docs">API Docs</a></nav>
</header>
<main>
  <section class="card">
    <h2>Chatbot médical prudent</h2>
    <div id="messages"></div>
    <p class="muted">⚠️ Démo pédagogique : ne remplace pas un médecin.</p>
    <textarea id="message" placeholder="Décrire les symptômes ou poser une question..."></textarea>
    <button onclick="sendMessage()">Envoyer</button>
  </section>
  <aside class="card">
    <h3>Contrôle HITL</h3>
    <label>Session ID</label>
    <input id="session" placeholder="auto si vide" />
    <label>Review mode</label>
    <select id="reviewMode">
      <option>AUTO_LOW_RISK_ONLY</option>
      <option>APPROVED_BY_HUMAN</option>
      <option>EDITED_BY_HUMAN</option>
      <option>REJECT_AND_ESCALATE</option>
    </select>
    <label>Human review / override</label>
    <textarea id="humanReview" placeholder="Réponse corrigée ou commentaire validateur"></textarea>
    <div class="kpi" id="lastKpi">
      <div><strong>-</strong><br><span class="muted">Correlation ID</span></div>
      <div><strong>-</strong><br><span class="muted">Latence</span></div>
      <div><strong>-</strong><br><span class="muted">Tokens</span></div>
      <div><strong>-</strong><br><span class="muted">Coût</span></div>
    </div>
    <div id="alerts"></div>
  </aside>
</main>
<script>
let sessionId = localStorage.getItem('sessionId') || '';
document.getElementById('session').value = sessionId;
function addMsg(text, cls){ const d=document.createElement('div'); d.className='msg '+cls; d.textContent=text; document.getElementById('messages').appendChild(d); d.scrollIntoView(); }
async function sendMessage(){
  const message = document.getElementById('message').value.trim();
  if(!message) return;
  addMsg(message, 'user'); document.getElementById('message').value=''; addMsg('Traitement en cours...', 'bot');
  const payload = {message, session_id: document.getElementById('session').value || null, review_mode: document.getElementById('reviewMode').value, human_review: document.getElementById('humanReview').value || null};
  const res = await fetch('/api/chat', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
  const data = await res.json();
  document.querySelector('#messages .bot:last-child').textContent = data.answer;
  sessionId = data.session_id; localStorage.setItem('sessionId', sessionId); document.getElementById('session').value=sessionId;
  document.getElementById('lastKpi').innerHTML = `<div><strong>${data.correlation_id.substring(0,8)}</strong><br><span class="muted">Correlation ID</span></div><div><strong>${data.latency_ms} ms</strong><br><span class="muted">Latence</span></div><div><strong>${data.token_input + data.token_output}</strong><br><span class="muted">Tokens</span></div><div><strong>$${data.cost_usd.toFixed(6)}</strong><br><span class="muted">Coût</span></div>`;
  let alerts = [];
  if(data.human_review_required) alerts.push('Validation humaine requise avant sortie patient.');
  if(data.hallucination_risk) alerts.push('Risque hallucination détecté par guardrail.');
  alerts = alerts.concat(data.technical_alerts || []);
  document.getElementById('alerts').innerHTML = alerts.map(a=>`<div class="alert">${a}</div>`).join('');
}
</script>
</body>
</html>
"""


@app.get('/dashboard', response_class=HTMLResponse)
def dashboard_ui() -> str:
    return """
<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Dashboard observabilité</title>
  <style>
    :root { --blue:#07314a; --yellow:#f7b500; --bg:#f4f7fb; --card:#fff; --muted:#667085; }
    body { font-family: Arial, sans-serif; margin:0; background:var(--bg); color:#101828; }
    header { background:var(--blue); color:white; padding:22px 34px; display:flex; justify-content:space-between; align-items:center; }
    header a { color:var(--yellow); text-decoration:none; margin-left:18px; font-weight:bold; }
    main { max-width:1200px; margin:28px auto; padding:0 18px; }
    .grid { display:grid; grid-template-columns:repeat(4,1fr); gap:14px; }
    .card { background:var(--card); border-radius:16px; padding:18px; box-shadow:0 8px 24px rgba(16,24,40,.08); margin-bottom:18px; }
    .kpi strong { font-size:26px; color:var(--blue); }
    .muted { color:var(--muted); font-size:13px; }
    .bar { display:flex; align-items:center; gap:10px; margin:8px 0; }
    .bar span:first-child { width:150px; }
    .fill { height:20px; background:var(--yellow); border-radius:10px; min-width:2px; }
    table { width:100%; border-collapse:collapse; font-size:14px; }
    th,td { text-align:left; border-bottom:1px solid #eaecf0; padding:10px; vertical-align:top; }
    code { background:#f2f4f7; border-radius:6px; padding:2px 6px; }
    .alert { color:#b42318; font-weight:bold; }
    @media (max-width:900px){ .grid{grid-template-columns:1fr 1fr;} }
  </style>
</head>
<body>
<header><div><strong>Dashboard observabilité</strong><div class="muted" style="color:#d0d5dd">Correlation ID, tokens, coût, erreurs, hallucination, latence</div></div><nav><a href="/">Chat</a><a href="/docs">API Docs</a></nav></header>
<main>
  <div class="grid" id="kpis"></div>
  <div class="card"><h3>Répartition par agent</h3><div id="agentBars"></div></div>
  <div class="card"><h3>Répartition par niveau de risque</h3><div id="riskBars"></div></div>
  <div class="card"><h3>Dernières exécutions</h3><div id="table"></div></div>
</main>
<script>
function bars(obj){ const max=Math.max(1,...Object.values(obj)); return Object.entries(obj).map(([k,v])=>`<div class="bar"><span>${k}</span><div class="fill" style="width:${(v/max)*70}%"></div><strong>${v}</strong></div>`).join(''); }
async function load(){
 const res=await fetch('/api/metrics'); const m=await res.json();
 document.getElementById('kpis').innerHTML = [
  ['Runs',m.total_runs], ['Succès',m.success_runs], ['Erreurs',m.error_runs], ['Latence moy.',m.avg_latency_ms+' ms'],
  ['Coût total','$'+Number(m.total_cost_usd).toFixed(6)], ['Tokens',m.total_tokens], ['Risque hallucination',m.hallucination_risk_count], ['HITL requis',m.human_review_required_count]
 ].map(x=>`<div class="card kpi"><strong>${x[1]}</strong><br><span class="muted">${x[0]}</span></div>`).join('');
 document.getElementById('agentBars').innerHTML = bars(m.by_agent || {});
 document.getElementById('riskBars').innerHTML = bars(m.by_risk || {});
 document.getElementById('table').innerHTML = `<table><thead><tr><th>Date</th><th>Correlation</th><th>Agent/Risque</th><th>KPI</th><th>Alertes</th></tr></thead><tbody>${(m.recent||[]).map(r=>`<tr><td>${r.created_at}</td><td><code>${r.correlation_id.substring(0,8)}</code></td><td>${r.selected_agent||'-'}<br>${r.risk_level||'-'}</td><td>${r.latency_ms} ms<br>${(r.token_input||0)+(r.token_output||0)} tokens<br>$${Number(r.cost_usd||0).toFixed(6)}</td><td class="${(r.technical_alerts||[]).length?'alert':''}">${(r.technical_alerts||[]).join('<br>') || '-'}</td></tr>`).join('')}</tbody></table>`;
}
load(); setInterval(load, 5000);
</script>
</body>
</html>
"""
