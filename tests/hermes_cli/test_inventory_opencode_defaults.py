import pytest
import hermes_cli.inventory as inv

@pytest.mark.parametrize("provider", ["opencode-free", "opencode-go", "opencode-zen", "custom:opencode-go-private"])
def test_opencode_picker_default_respects_wire_ceiling(monkeypatch, provider):
    from agent import models_dev
    from agent.transports import codex
    from hermes_cli import config
    monkeypatch.setattr(models_dev, "get_model_capabilities", lambda *args: None)
    monkeypatch.setattr(config, "load_config", lambda: {"agent": {"reasoning_effort": "high"}})
    monkeypatch.setattr(codex, "_profile_declared_efforts", lambda *args: ("low", "medium", "high", "xhigh"))
    rows=[{"slug":provider,"models":["fixture-model"]}]
    inv._apply_capabilities(rows)
    assert rows[0]["capabilities"]["fixture-model"]["default_reasoning_effort"] == "xhigh"


def test_explicit_model_override_is_preserved(monkeypatch):
    from agent import models_dev
    from agent.transports import codex
    from hermes_cli import config
    monkeypatch.setattr(models_dev, "get_model_capabilities", lambda *args: None)
    monkeypatch.setattr(config, "load_config", lambda: {"agent": {"reasoning_overrides": {"fixture-model": "low"}}})
    monkeypatch.setattr(codex, "_profile_declared_efforts", lambda *args: ("low", "high", "max"))
    rows=[{"slug":"opencode-go","models":["fixture-model"]}]
    inv._apply_capabilities(rows)
    assert rows[0]["capabilities"]["fixture-model"]["default_reasoning_effort"] == "low"


@pytest.mark.parametrize('override,declared,expected', [(False, ('low', 'high'), 'none'), ('low', ('low', 'high'), 'low'), (None, (), None)])
def test_disabled_override_and_no_reasoning_route(monkeypatch, override, declared, expected):
    from agent import models_dev
    from agent.transports import codex
    from hermes_cli import config
    monkeypatch.setattr(models_dev, 'get_model_capabilities', lambda *args: None)
    overrides = {} if override is None else {'vendor/fixture-model': override}
    monkeypatch.setattr(config, 'load_config', lambda: {'agent': {'reasoning_overrides': overrides}})
    monkeypatch.setattr(codex, '_profile_declared_efforts', lambda *args: declared)
    rows = [{'slug': 'opencode-go', 'models': ['vendor/fixture-model']}]
    inv._apply_capabilities(rows)
    caps = rows[0]['capabilities']['vendor/fixture-model']
    assert caps.get('default_reasoning_effort') == expected
    assert caps['reasoning'] is bool(declared)


def test_custom_route_uses_real_profile_resolution_from_endpoint(monkeypatch):
    from types import SimpleNamespace
    import providers
    from agent import models_dev, model_metadata
    from hermes_cli import config
    calls = []
    def declared(model):
        calls.append(model)
        return ('low', 'high', 'xhigh')
    monkeypatch.setattr(models_dev, 'get_model_capabilities', lambda *args: None)
    monkeypatch.setattr(config, 'load_config', lambda: {'agent': {'reasoning_effort': 'high'}})
    monkeypatch.setattr(providers, 'get_provider_profile', lambda name: SimpleNamespace(supported_reasoning_efforts=declared) if name == 'fixture-route' else None)
    monkeypatch.setattr(model_metadata, '_infer_provider_from_url', lambda url: 'fixture-route' if url == 'https://fixture.invalid/v1' else None)
    rows = [{'slug': 'custom:opencode-go-private', 'api_url': 'https://fixture.invalid/v1', 'models': ['vendor/fixture-model']}]
    inv._apply_capabilities(rows)
    assert calls == ['vendor/fixture-model']
    assert rows[0]['capabilities']['vendor/fixture-model']['default_reasoning_effort'] == 'xhigh'
