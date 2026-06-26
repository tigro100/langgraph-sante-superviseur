import hashlib
import json
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from app.core import db
from app.core.config import get_settings


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _parse_recipients(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.replace(';', ',').split(',') if item.strip()]


def _alert_rows(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in metrics.get('recent', []) if row.get('technical_alerts')]


def _alert_count(rows: list[dict[str, Any]]) -> int:
    return sum(len(row.get('technical_alerts') or []) for row in rows)


def _signature(rows: list[dict[str, Any]]) -> str:
    payload = [
        {'correlation_id': row.get('correlation_id'), 'alerts': row.get('technical_alerts') or []}
        for row in rows
    ]
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _state_file() -> Path:
    settings = get_settings()
    state_path = Path(settings.db_path).parent / 'last_alert_report.json'
    state_path.parent.mkdir(parents=True, exist_ok=True)
    return state_path


def _load_state() -> dict[str, Any]:
    path = _state_file()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}


def _save_state(state: dict[str, Any]) -> None:
    _state_file().write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')


def _cooldown_active(last_sent_at: str | None, cooldown_minutes: int) -> bool:
    if not last_sent_at:
        return False
    try:
        last_dt = datetime.fromisoformat(last_sent_at)
        now = datetime.now(timezone.utc)
        return (now - last_dt).total_seconds() < cooldown_minutes * 60
    except Exception:
        return False


def build_alert_report(metrics: dict[str, Any], rows: list[dict[str, Any]], total_alerts: int) -> str:
    lines = [
        'Rapport automatique des alertes — Chatbot pré-diagnostique santé',
        f'Date UTC: {_now_iso()}',
        '',
        'Résumé:',
        f'- Total exécutions analysées: {metrics.get("total_runs", 0)}',
        f'- Total alertes dashboard: {total_alerts}',
        f'- Latence moyenne: {metrics.get("avg_latency_ms", 0)} ms',
        f'- Coût total estimé: ${float(metrics.get("total_cost_usd", 0)):.6f}',
        f'- Tokens totaux: {metrics.get("total_tokens", 0)}',
        f'- Risques hallucination: {metrics.get("hallucination_risk_count", 0)}',
        f'- HITL requis: {metrics.get("human_review_required_count", 0)}',
        '',
        'Détail des dernières exécutions avec alertes:',
    ]
    for row in rows:
        lines.extend([
            '',
            f'Correlation ID: {row.get("correlation_id")}',
            f'Date: {row.get("created_at")}',
            f'Agent/Risque: {row.get("selected_agent") or "-"} / {row.get("risk_level") or "-"}',
            f'KPI: {row.get("latency_ms", 0)} ms | {(row.get("token_input") or 0) + (row.get("token_output") or 0)} tokens | ${float(row.get("cost_usd") or 0):.6f}',
            'Alertes:',
        ])
        for alert in row.get('technical_alerts') or []:
            lines.append(f'- {alert}')
    return '\n'.join(lines)


def send_alert_report_if_needed(force: bool = False) -> dict[str, Any]:
    settings = get_settings()
    metrics = db.metrics_summary()
    rows = _alert_rows(metrics)
    total_alerts = _alert_count(rows)
    threshold = int(settings.alert_report_threshold)

    if total_alerts <= threshold and not force:
        return {
            'sent': False,
            'reason': f'Seuil non atteint: {total_alerts} alerte(s) <= {threshold}',
            'total_alerts': total_alerts,
            'threshold': threshold,
        }

    recipients = _parse_recipients(settings.gmail_recipients)
    sender = settings.gmail_sender or settings.gmail_user

    if not settings.gmail_enabled:
        return {
            'sent': False,
            'reason': 'Gmail désactivé: GMAIL_ENABLED=false',
            'total_alerts': total_alerts,
            'threshold': threshold,
        }

    if not settings.gmail_user or not settings.gmail_app_password or not sender or not recipients:
        return {
            'sent': False,
            'reason': 'Configuration Gmail incomplète: vérifier GMAIL_USER, GMAIL_APP_PASSWORD, GMAIL_SENDER, GMAIL_RECIPIENTS',
            'total_alerts': total_alerts,
            'threshold': threshold,
        }

    signature = _signature(rows)
    state = _load_state()
    if not force and state.get('signature') == signature and _cooldown_active(state.get('last_sent_at'), settings.alert_report_cooldown_minutes):
        return {
            'sent': False,
            'reason': 'Rapport déjà envoyé récemment pour les mêmes alertes',
            'total_alerts': total_alerts,
            'threshold': threshold,
        }

    report = build_alert_report(metrics, rows, total_alerts)
    msg = EmailMessage()
    msg['Subject'] = f'[ALERTE] Chatbot pré-diagnostique santé — {total_alerts} alertes dashboard'
    msg['From'] = sender
    msg['To'] = ', '.join(recipients)
    msg.set_content(report)

    with smtplib.SMTP(settings.gmail_smtp_host, int(settings.gmail_smtp_port), timeout=30) as smtp:
        smtp.starttls()
        smtp.login(settings.gmail_user, settings.gmail_app_password)
        smtp.send_message(msg)

    _save_state({'signature': signature, 'last_sent_at': _now_iso(), 'total_alerts': total_alerts})
    return {
        'sent': True,
        'reason': 'Rapport Gmail envoyé',
        'total_alerts': total_alerts,
        'threshold': threshold,
        'recipients': recipients,
    }
