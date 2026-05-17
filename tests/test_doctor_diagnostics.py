from __future__ import annotations

from typer.testing import CliRunner

from lmola.cli import app


runner = CliRunner()


def test_doctor_mock_backend_does_not_require_ollama(monkeypatch) -> None:
    monkeypatch.setenv("LMOLA_LLM_BACKEND", "mock")
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert '"llm_backend": "mock"' in result.stdout
    assert '"ollama_reachable"' not in result.stdout


def test_doctor_ollama_tags_success_model_available(monkeypatch) -> None:
    monkeypatch.setenv("LMOLA_LLM_ENABLED", "true")
    monkeypatch.setenv("LMOLA_LLM_BACKEND", "ollama")
    monkeypatch.setenv("LMOLA_LLM_BASE_URL", "http://ollama.test")
    monkeypatch.setenv("LMOLA_LLM_MODEL", "qwen2.5-coder:14b")

    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/chat":
            return httpx.Response(200, json={"message": {"content": "{}"}})
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "qwen2.5-coder:14b"}]})
        if request.url.path == "/api/ps":
            return httpx.Response(200, json={"models": [{"name": "qwen2.5-coder:14b"}]})
        return httpx.Response(404)

    original_client = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda *args, **kwargs: original_client(transport=httpx.MockTransport(handler), timeout=kwargs.get("timeout")),
    )
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert '"ollama_reachable": true' in result.stdout
    assert '"ollama_configured_model_available": true' in result.stdout


def test_doctor_ollama_tags_success_model_missing(monkeypatch) -> None:
    monkeypatch.setenv("LMOLA_LLM_ENABLED", "true")
    monkeypatch.setenv("LMOLA_LLM_BACKEND", "ollama")
    monkeypatch.setenv("LMOLA_LLM_BASE_URL", "http://ollama.test")
    monkeypatch.setenv("LMOLA_LLM_MODEL", "qwen2.5-coder:14b")
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/chat":
            return httpx.Response(200, json={"message": {"content": "{}"}})
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "other:latest"}]})
        if request.url.path == "/api/ps":
            return httpx.Response(404)
        return httpx.Response(404)

    original_client = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda *args, **kwargs: original_client(transport=httpx.MockTransport(handler), timeout=kwargs.get("timeout")),
    )
    result = runner.invoke(app, ["doctor"])
    assert '"ollama_reachable": true' in result.stdout
    assert '"ollama_configured_model_available": false' in result.stdout


def test_doctor_ollama_endpoint_failure(monkeypatch) -> None:
    monkeypatch.setenv("LMOLA_LLM_ENABLED", "true")
    monkeypatch.setenv("LMOLA_LLM_BACKEND", "ollama")
    monkeypatch.setenv("LMOLA_LLM_BASE_URL", "http://ollama.test")
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/chat":
            return httpx.Response(503)
        if request.url.path == "/api/tags":
            return httpx.Response(503)
        return httpx.Response(404)

    original_client = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda *args, **kwargs: original_client(transport=httpx.MockTransport(handler), timeout=kwargs.get("timeout")),
    )
    result = runner.invoke(app, ["doctor"])
    assert '"ollama_reachable": false' in result.stdout
    assert '"ollama_error":' in result.stdout


def test_doctor_python_cuda_field_exists() -> None:
    result = runner.invoke(app, ["doctor"])
    assert '"python_cuda_detected":' in result.stdout
