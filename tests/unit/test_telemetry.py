import os

from moodle_course_agent.agent import REFUSAL, configure_telemetry
from moodle_course_agent.config import Settings


def test_langfuse_local_otlp_endpoint(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_HEADERS", raising=False)
    settings = Settings(
        langfuse_public_key="pk-lf-test",
        langfuse_secret_key="sk-lf-test",
        langfuse_base_url="http://localhost:3000",
    )
    configure_telemetry(settings)
    assert os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://localhost:3000/api/public/otel"
    assert "Authorization=Basic" in os.environ["OTEL_EXPORTER_OTLP_HEADERS"]
    assert "Sorry" in REFUSAL
