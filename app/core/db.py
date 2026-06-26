import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import get_settings


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


@contextmanager
def connect(path: str | Path | None = None):
    settings = get_settings()
    db_path = Path(path) if path else settings.db_file
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db() -> None:
    with connect() as con:
        con.execute(
            '''
            CREATE TABLE IF NOT EXISTS executions (
                correlation_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL,
                selected_agent TEXT,
                risk_level TEXT,
                latency_ms INTEGER DEFAULT 0,
                token_input INTEGER DEFAULT 0,
                token_output INTEGER DEFAULT 0,
                cost_usd REAL DEFAULT 0,
                error_count INTEGER DEFAULT 0,
                hallucination_risk INTEGER DEFAULT 0,
                human_review_required INTEGER DEFAULT 0,
                technical_alerts TEXT DEFAULT '[]',
                trace TEXT DEFAULT '{}',
                user_message TEXT DEFAULT '',
                answer TEXT DEFAULT ''
            )
            '''
        )
        con.execute(
            '''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            '''
        )
        con.execute(
            '''
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                correlation_id TEXT NOT NULL,
                hallucination_reported INTEGER DEFAULT 0,
                comment TEXT,
                created_at TEXT NOT NULL
            )
            '''
        )


def save_execution(payload: dict[str, Any]) -> None:
    init_db()
    fields = {
        'correlation_id': payload['correlation_id'],
        'session_id': payload['session_id'],
        'created_at': payload.get('created_at') or utc_now(),
        'status': payload.get('status', 'UNKNOWN'),
        'selected_agent': payload.get('selected_agent'),
        'risk_level': payload.get('risk_level'),
        'latency_ms': int(payload.get('latency_ms') or 0),
        'token_input': int(payload.get('token_input') or 0),
        'token_output': int(payload.get('token_output') or 0),
        'cost_usd': float(payload.get('cost_usd') or 0),
        'error_count': int(payload.get('error_count') or 0),
        'hallucination_risk': int(bool(payload.get('hallucination_risk'))),
        'human_review_required': int(bool(payload.get('human_review_required'))),
        'technical_alerts': json.dumps(payload.get('technical_alerts', []), ensure_ascii=False),
        'trace': json.dumps(payload.get('trace', {}), ensure_ascii=False),
        'user_message': payload.get('user_message', ''),
        'answer': payload.get('answer', ''),
    }
    with connect() as con:
        con.execute(
            f"""
            INSERT OR REPLACE INTO executions ({','.join(fields.keys())})
            VALUES ({','.join('?' for _ in fields)})
            """,
            list(fields.values()),
        )


def add_message(session_id: str, role: str, content: str) -> None:
    init_db()
    with connect() as con:
        con.execute(
            'INSERT INTO messages(session_id, role, content, created_at) VALUES (?, ?, ?, ?)',
            (session_id, role, content, utc_now()),
        )


def get_history(session_id: str, limit: int = 8) -> str:
    init_db()
    with connect() as con:
        rows = con.execute(
            'SELECT role, content FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT ?',
            (session_id, limit),
        ).fetchall()
    rows = list(reversed(rows))
    return '\n'.join([f"{row['role']}: {row['content']}" for row in rows])


def list_recent_executions(limit: int = 50) -> list[dict[str, Any]]:
    init_db()
    with connect() as con:
        rows = con.execute('SELECT * FROM executions ORDER BY created_at DESC LIMIT ?', (limit,)).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d['technical_alerts'] = json.loads(d.get('technical_alerts') or '[]')
        d['trace'] = json.loads(d.get('trace') or '{}')
        d['hallucination_risk'] = bool(d['hallucination_risk'])
        d['human_review_required'] = bool(d['human_review_required'])
        result.append(d)
    return result


def get_execution(correlation_id: str) -> dict[str, Any] | None:
    init_db()
    with connect() as con:
        row = con.execute('SELECT * FROM executions WHERE correlation_id = ?', (correlation_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d['technical_alerts'] = json.loads(d.get('technical_alerts') or '[]')
    d['trace'] = json.loads(d.get('trace') or '{}')
    d['hallucination_risk'] = bool(d['hallucination_risk'])
    d['human_review_required'] = bool(d['human_review_required'])
    return d


def add_feedback(correlation_id: str, hallucination_reported: bool, comment: str | None) -> None:
    init_db()
    with connect() as con:
        con.execute(
            'INSERT INTO feedback(correlation_id, hallucination_reported, comment, created_at) VALUES (?, ?, ?, ?)',
            (correlation_id, int(hallucination_reported), comment, utc_now()),
        )
        if hallucination_reported:
            con.execute('UPDATE executions SET hallucination_risk = 1 WHERE correlation_id = ?', (correlation_id,))


def metrics_summary(limit: int = 500) -> dict[str, Any]:
    rows = list_recent_executions(limit)
    total = len(rows)
    if total == 0:
        return {
            'total_runs': 0,
            'success_runs': 0,
            'error_runs': 0,
            'avg_latency_ms': 0,
            'total_cost_usd': 0,
            'avg_cost_usd': 0,
            'total_tokens': 0,
            'hallucination_risk_count': 0,
            'human_review_required_count': 0,
            'total_alerts': 0,
            'by_agent': {},
            'by_risk': {},
            'recent': [],
        }
    success = sum(1 for r in rows if r.get('status') == 'SUCCESS')
    errors = sum(1 for r in rows if int(r.get('error_count') or 0) > 0 or r.get('status') == 'ERROR')
    total_latency = sum(int(r.get('latency_ms') or 0) for r in rows)
    total_cost = sum(float(r.get('cost_usd') or 0) for r in rows)
    total_tokens = sum(int(r.get('token_input') or 0) + int(r.get('token_output') or 0) for r in rows)
    total_alerts = sum(len(r.get('technical_alerts') or []) for r in rows)
    by_agent: dict[str, int] = {}
    by_risk: dict[str, int] = {}
    for r in rows:
        agent = r.get('selected_agent') or 'UNKNOWN'
        risk = r.get('risk_level') or 'UNKNOWN'
        by_agent[agent] = by_agent.get(agent, 0) + 1
        by_risk[risk] = by_risk.get(risk, 0) + 1
    return {
        'total_runs': total,
        'success_runs': success,
        'error_runs': errors,
        'avg_latency_ms': round(total_latency / total),
        'total_cost_usd': round(total_cost, 6),
        'avg_cost_usd': round(total_cost / total, 6),
        'total_tokens': total_tokens,
        'hallucination_risk_count': sum(1 for r in rows if r.get('hallucination_risk')),
        'human_review_required_count': sum(1 for r in rows if r.get('human_review_required')),
        'total_alerts': total_alerts,
        'by_agent': by_agent,
        'by_risk': by_risk,
        'recent': rows[:25],
    }
