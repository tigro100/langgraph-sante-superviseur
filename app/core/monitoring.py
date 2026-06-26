import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.core.config import get_settings


@dataclass
class NodeTrace:
    node: str
    latency_ms: int = 0
    status: str = 'SUCCESS'
    error: str | None = None
    token_input: int = 0
    token_output: int = 0
    cost_usd: float = 0.0


@dataclass
class ExecutionTelemetry:
    """Objet de suivi technique attaché à une exécution LangGraph."""

    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    started_at: float = field(default_factory=time.perf_counter)
    token_input: int = 0
    token_output: int = 0
    cost_usd: float = 0.0
    errors: list[str] = field(default_factory=list)
    node_traces: list[NodeTrace] = field(default_factory=list)

    def add_tokens(self, prompt_tokens: int, completion_tokens: int) -> None:
        settings = get_settings()
        self.token_input += int(prompt_tokens or 0)
        self.token_output += int(completion_tokens or 0)
        self.cost_usd += (prompt_tokens / 1_000_000) * settings.token_price_input_1m
        self.cost_usd += (completion_tokens / 1_000_000) * settings.token_price_output_1m

    def add_node(self, node: str, latency_ms: int, status: str = 'SUCCESS', error: str | None = None, prompt_tokens: int = 0, completion_tokens: int = 0) -> None:
        settings = get_settings()
        cost = (prompt_tokens / 1_000_000) * settings.token_price_input_1m + (completion_tokens / 1_000_000) * settings.token_price_output_1m
        if error:
            self.errors.append(f'{node}: {error}')
        self.node_traces.append(
            NodeTrace(
                node=node,
                latency_ms=int(latency_ms),
                status=status,
                error=error,
                token_input=int(prompt_tokens or 0),
                token_output=int(completion_tokens or 0),
                cost_usd=round(cost, 8),
            )
        )

    @property
    def latency_ms(self) -> int:
        return int((time.perf_counter() - self.started_at) * 1000)

    @property
    def error_count(self) -> int:
        return len(self.errors)

    def trace_dict(self) -> dict[str, Any]:
        return {
            'correlation_id': self.correlation_id,
            'latency_ms': self.latency_ms,
            'token_input': self.token_input,
            'token_output': self.token_output,
            'cost_usd': round(self.cost_usd, 8),
            'errors': self.errors,
            'nodes': [node.__dict__ for node in self.node_traces],
        }


def technical_supervisor_alerts(telemetry: ExecutionTelemetry, hallucination_risk: bool) -> list[str]:
    """Agent de supervision technique déterministe.

    Il produit des alertes exploitables par le dashboard et le runbook incident.
    """
    settings = get_settings()
    alerts: list[str] = []
    if telemetry.latency_ms > settings.latency_threshold_ms:
        alerts.append(f'LATENCE_ELEVEE: {telemetry.latency_ms} ms > {settings.latency_threshold_ms} ms')
    if telemetry.cost_usd > settings.cost_threshold_usd:
        alerts.append(f'COUT_ELEVE: {telemetry.cost_usd:.6f}$ > {settings.cost_threshold_usd:.6f}$')
    if telemetry.error_count > 0:
        alerts.append(f'ERREUR_EXECUTION: {telemetry.error_count} erreur(s) détectée(s)')
    if hallucination_risk:
        alerts.append('RISQUE_HALLUCINATION: formulation trop certaine/source inventée ou feedback utilisateur')
    return alerts
