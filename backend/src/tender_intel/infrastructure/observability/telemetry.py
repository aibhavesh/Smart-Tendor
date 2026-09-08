"""Prometheus metrics, OpenTelemetry tracing and Sentry hooks.

All three are config-switchable so local development can run with none of them.
The metrics endpoint itself (credential-protected, config-toggle) is wired in
Phase 10; here we only provide the registry and the initialisation hooks so the
scaffolding exists from Phase 0.
"""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Histogram

from tender_intel.core.config import Settings
from tender_intel.infrastructure.observability.logging import get_logger

_log = get_logger(__name__)

# A dedicated registry keeps app metrics isolated from the process-global default.
REGISTRY = CollectorRegistry()

http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests.",
    labelnames=("method", "path", "status"),
    registry=REGISTRY,
)
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency.",
    labelnames=("method", "path"),
    registry=REGISTRY,
)


def collect_request_samples() -> list[tuple[dict[str, str], float]]:
    """Return (labels, value) for every http_requests_total counter sample."""
    samples: list[tuple[dict[str, str], float]] = []
    for metric in REGISTRY.collect():
        if metric.name != "http_requests":  # prometheus strips the _total suffix
            continue
        for sample in metric.samples:
            if sample.name == "http_requests_total":
                samples.append((dict(sample.labels), sample.value))
    return samples


def init_sentry(settings: Settings) -> None:
    if not settings.sentry_dsn:
        return
    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment.value,
        traces_sample_rate=0.0,
    )
    _log.info("sentry.initialised")


def init_tracing(settings: Settings) -> None:
    if not settings.otel_exporter_otlp_endpoint:
        return
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(resource=Resource.create({"service.name": "tender-intel-api"}))
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint))
    )
    trace.set_tracer_provider(provider)
    _log.info("tracing.initialised", endpoint=settings.otel_exporter_otlp_endpoint)
