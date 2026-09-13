from __future__ import annotations

import importlib.metadata
from types import SimpleNamespace

from bimanual.cli import main
from bimanual.evidence import EvidenceStore
from bimanual.planner import seal_model
from bimanual.planner_preflight import run_planner_preflight


def sealed_model(root):
    root.mkdir()
    (root / "config.json").write_text('{"model_type":"qwen3_vl"}')
    for name in ("tokenizer_config.json", "preprocessor_config.json"):
        (root / name).write_text("{}")
    (root / "model.safetensors").write_bytes(b"fixture weights; never loaded")
    seal_model(root, "a" * 40)
    return root


def test_preflight_verifies_snapshot_without_model_execution(tmp_path, monkeypatch):
    import bimanual.planner_preflight as module

    model = sealed_model(tmp_path / "model")
    torch = SimpleNamespace(
        backends=SimpleNamespace(
            mps=SimpleNamespace(is_built=lambda: True, is_available=lambda: True)
        ),
        mps=SimpleNamespace(device_count=lambda: 1),
    )
    monkeypatch.setitem(__import__("sys").modules, "torch", torch)
    monkeypatch.setattr(module.importlib.util, "find_spec", lambda _: object())
    monkeypatch.setattr(module.importlib.metadata, "version", lambda name: f"fixture-{name}")
    monkeypatch.setenv("PYTORCH_ENABLE_MPS_FALLBACK", "0")

    store = EvidenceStore(tmp_path / "evidence")
    result = run_planner_preflight(model_root=model, store=store, project_root=tmp_path)

    assert result.outcome == "completed"
    assert result.kind == "local_qwen_planner_preflight"
    assert result.claims == []
    assert result.metrics["model_load_attempted"] is False
    assert result.metrics["inference_attempted"] is False
    assert result.metrics["live_dispatch_authorized"] is False
    assert result.metrics["model"]["revision"] == "a" * 40
    assert result.metrics["mps"] == {
        "torch_imported": True,
        "built": True,
        "available": True,
        "device_count": 1,
    }
    assert result.metrics["pytorch_enable_mps_fallback"]["effective_value"] == "0"
    assert result.metrics["packages"]["openvino"] == {
        "installed": True,
        "version": "fixture-openvino",
    }
    store.verify(result.run_id)


def test_preflight_seals_invalid_model_without_execution(tmp_path, monkeypatch):
    import bimanual.planner_preflight as module

    monkeypatch.setattr(module.importlib.util, "find_spec", lambda _: None)
    monkeypatch.setattr(
        module.importlib.metadata,
        "version",
        lambda name: (_ for _ in ()).throw(importlib.metadata.PackageNotFoundError(name)),
    )
    store = EvidenceStore(tmp_path / "evidence")
    result = run_planner_preflight(
        model_root=tmp_path / "missing", store=store, project_root=tmp_path
    )

    assert result.outcome == "failed"
    assert result.metrics["model_load_attempted"] is False
    assert result.metrics["inference_attempted"] is False
    assert result.metrics["live_dispatch_authorized"] is False
    assert "error" in result.metrics
    assert "error.txt" in result.files
    store.verify(result.run_id)


def test_preflight_cli_forwards_model_root(tmp_path, monkeypatch, capsys):
    import bimanual.planner_preflight as module

    observed = []

    def preflight(**kwargs):
        observed.append(kwargs)
        return SimpleNamespace(outcome="completed", model_dump=lambda **_: {"outcome": "completed"})

    monkeypatch.setattr(module, "run_planner_preflight", preflight)
    model = tmp_path / "model"
    assert (
        main(
            [
                "--artifacts",
                str(tmp_path / "evidence"),
                "planner-preflight",
                "--model-root",
                str(model),
            ]
        )
        == 0
    )
    assert observed[0]["model_root"] == model
    assert observed[0]["store"].root == (tmp_path / "evidence").resolve()
    assert __import__("json").loads(capsys.readouterr().out) == {"outcome": "completed"}
