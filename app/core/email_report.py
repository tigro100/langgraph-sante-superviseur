import json
import smtplib
import urllib.error
import urllib.request
from email.message import EmailMessage
from typing import Any

from app.core import db
from app.core.config import get_settings


def _parse_recipients(value: str | None) -> list[str]:
    if not value:
        return []
    return [x.strip() for x in value.replace(";", ",").split(",") if x.strip()]


def _build_report_body(
    metrics: dict[str, Any],
    alert_rows: list[dict[str, Any]],
    total_alerts: int,
    threshold: int,
) -> str:
    lines = [
        "Rapport automatique des alertes — Chatbot pré-diagnostique santé",
        "",
        f"Total alertes dashboard: {total_alerts}",
        f"Seuil configuré: {threshold}",
        f"Total exécutions: {metrics.get('total_runs', 0)}",
        f"Succès: {metrics.get('success_runs', 0)}",
        f"Erreurs: {metrics.get('error_runs', 0)}",
        f"Latence moyenne: {metrics.get('avg_latency_ms', 0)} ms",
        f"Coût total estimé: ${float(metrics.get('total_cost_usd') or 0):.6f}",
        f"Tokens totaux: {metrics.get('total_tokens', 0)}",
        f"Risques hallucination: {metrics.get('hallucination_risk_count', 0)}",
        f"HITL requis: {metrics.get('human_review_required_count', 0)}",
        "",
        "Dernières exécutions avec alertes:",
    ]

    if not alert_rows:
        lines.append("- Aucune alerte enregistrée actuellement.")
        lines.append("")
        lines.append("Ce rapport a été envoyé car le test a été forcé avec force=true.")
        return "\n".join(lines)

    for row in alert_rows:
        total_tokens = int(row.get("token_input") or 0) + int(row.get("token_output") or 0)

        lines.extend(
            [
                "",
                f"Correlation ID: {row.get('correlation_id')}",
                f"Date: {row.get('created_at')}",
                f"Agent: {row.get('selected_agent')}",
                f"Risque: {row.get('risk_level')}",
                f"Latence: {row.get('latency_ms')} ms",
                f"Tokens: {total_tokens}",
                f"Coût: ${float(row.get('cost_usd') or 0):.6f}",
                "Alertes:",
            ]
        )

        for alert in row.get("technical_alerts") or []:
            lines.append(f"- {alert}")

    return "\n".join(lines)


def _send_with_resend(subject: str, body: str) -> dict[str, Any]:
    settings = get_settings()

    recipients = _parse_recipients(settings.resend_recipients)
    sender = settings.resend_from or "Chatbot Santé <onboarding@resend.dev>"

    missing = []

    if not settings.resend_api_key:
        missing.append("RESEND_API_KEY")
    if not recipients:
        missing.append("RESEND_RECIPIENTS")
    if not sender:
        missing.append("RESEND_FROM")

    if missing:
        return {
            "sent": False,
            "provider": "resend",
            "reason": "Configuration Resend incomplète",
            "missing": missing,
        }

    payload = {
        "from": sender,
        "to": recipients,
        "subject": subject,
        "text": body,
    }

    request = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.resend_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            response_body = response.read().decode("utf-8")

        return {
            "sent": True,
            "provider": "resend",
            "reason": "Rapport envoyé via Resend",
            "response": response_body,
            "recipients": recipients,
        }

    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="ignore")
        return {
            "sent": False,
            "provider": "resend",
            "reason": "Erreur HTTP Resend",
            "error_type": "HTTPError",
            "status_code": e.code,
            "error": error_body,
        }

    except Exception as e:
        return {
            "sent": False,
            "provider": "resend",
            "reason": "Erreur pendant l'envoi via Resend",
            "error_type": type(e).__name__,
            "error": str(e),
        }


def _send_with_gmail_smtp(subject: str, body: str) -> dict[str, Any]:
    settings = get_settings()

    recipients = _parse_recipients(getattr(settings, "gmail_recipients", None))
    sender = getattr(settings, "gmail_sender", None) or getattr(settings, "gmail_user", None)

    missing = []

    if not getattr(settings, "gmail_user", None):
        missing.append("GMAIL_USER")
    if not getattr(settings, "gmail_app_password", None):
        missing.append("GMAIL_APP_PASSWORD")
    if not sender:
        missing.append("GMAIL_SENDER")
    if not recipients:
        missing.append("GMAIL_RECIPIENTS")
    if not getattr(settings, "gmail_smtp_host", None):
        missing.append("GMAIL_SMTP_HOST")
    if not getattr(settings, "gmail_smtp_port", None):
        missing.append("GMAIL_SMTP_PORT")

    if missing:
        return {
            "sent": False,
            "provider": "gmail_smtp",
            "reason": "Configuration Gmail incomplète",
            "missing": missing,
        }

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.set_content(body)

    try:
        with smtplib.SMTP(settings.gmail_smtp_host, int(settings.gmail_smtp_port), timeout=30) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(settings.gmail_user, settings.gmail_app_password)
            smtp.send_message(msg)

        return {
            "sent": True,
            "provider": "gmail_smtp",
            "reason": "Rapport Gmail envoyé",
            "recipients": recipients,
        }

    except Exception as e:
        return {
            "sent": False,
            "provider": "gmail_smtp",
            "reason": "Erreur technique pendant l'envoi Gmail",
            "error_type": type(e).__name__,
            "error": str(e),
        }


def send_alert_report_if_needed(force: bool = False) -> dict[str, Any]:
    settings = get_settings()
    metrics = db.metrics_summary()

    recent = metrics.get("recent", [])
    alert_rows = [r for r in recent if r.get("technical_alerts")]
    total_alerts = sum(len(r.get("technical_alerts") or []) for r in alert_rows)
    threshold = int(getattr(settings, "alert_report_threshold", 3))

    if total_alerts <= threshold and not force:
        return {
            "sent": False,
            "reason": f"Seuil non atteint: {total_alerts} alerte(s) <= {threshold}",
            "total_alerts": total_alerts,
            "threshold": threshold,
        }

    subject = f"[ALERTE] Chatbot pré-diagnostique santé — {total_alerts} alerte(s)"
    body = _build_report_body(metrics, alert_rows, total_alerts, threshold)

    provider = (
        getattr(settings, "email_provider", "smtp") or "smtp"
    ).lower().strip().strip('"').strip("'")

    # Sécurité Railway :
    # Si RESEND_API_KEY existe, on force Resend.
    # Cela évite que Railway retombe sur Gmail SMTP.
    if getattr(settings, "resend_api_key", None):
        provider = "resend"

    if provider == "resend":
        result = _send_with_resend(subject, body)
    else:
        if not getattr(settings, "gmail_enabled", False):
            return {
                "sent": False,
                "provider": "gmail_smtp",
                "reason": "Gmail désactivé: GMAIL_ENABLED=false",
                "total_alerts": total_alerts,
                "threshold": threshold,
            }

        result = _send_with_gmail_smtp(subject, body)

    result["total_alerts"] = total_alerts
    result["threshold"] = threshold
    result["effective_provider"] = provider
    return result