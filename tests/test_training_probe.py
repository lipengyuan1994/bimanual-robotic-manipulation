import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from bimanual.evidence import EvidenceStore
from bimanual.training_probe import TrainingProbeConfig, run_training_probe


def test_probe_rejects_invalid_profiles():
    for options in (
        {"device": "cuda"},
        {"image_height": 0},
        {"batch_size": 0},
        {"chunk_size": 101},
        {"seed": -1},
        {"architecture": "imaginary"},
    ):
        with pytest.raises(ValidationError):
            TrainingProbeConfig(**options)


def test_native_runtime_failure_is_sealed(tmp_path, monkeypatch):
    monkeypatch.setattr("bimanual.training_probe.platform.system", lambda: "Darwin")
    monkeypatch.setattr("bimanual.training_probe.platform.machine", lambda: "x86_64")
    result = run_training_probe(
        TrainingProbeConfig(), store=EvidenceStore(tmp_path), project_root=Path.cwd()
    )
    assert result.outcome == "failed"
    assert "native arm64" in result.metrics["error"]
    assert result.metrics["actual_device"] is None
    assert result.claims == []
    assert EvidenceStore(tmp_path).verify(result.run_id) == result


def test_mps_cpu_fallback_is_rejected_and_recorded(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTORCH_ENABLE_MPS_FALLBACK", "1")
    result = run_training_probe(
        TrainingProbeConfig(device="mps"), store=EvidenceStore(tmp_path), project_root=Path.cwd()
    )
    assert result.outcome == "failed"
    assert "fresh process" in result.metrics["error"]
    assert result.metrics["requested_device"] == "mps"
    assert result.metrics["actual_device"] is None
    assert not result.metrics["runtime_success"]
    assert EvidenceStore(tmp_path).verify(result.run_id) == result


def test_real_act_cpu_loss_backward_optimizer_and_inference(tmp_path, monkeypatch):
    pytest.importorskip("lerobot.policies.act.modeling_act")
    import torch.hub
    import torchvision.models._api

    def reject_download(*args, **kwargs):
        raise AssertionError("Runtime probe must not download model weights")

    monkeypatch.setattr(torch.hub, "download_url_to_file", reject_download)
    monkeypatch.setattr(torchvision.models._api, "load_state_dict_from_url", reject_download)
    result = run_training_probe(
        TrainingProbeConfig(image_height=64, image_width=64, chunk_size=2, inference_samples=2),
        store=EvidenceStore(tmp_path),
        project_root=Path.cwd(),
    )
    assert result.outcome == "completed", result.metrics.get("error")
    metrics = result.metrics
    assert metrics["actual_device"] == "cpu"
    assert metrics["output_shape"] == [1, 2, 12]
    assert metrics["initial_state_sha256"] != metrics["updated_state_sha256"]
    assert metrics["train_steps"][0]["finite_gradient_tensors"] > 0
    assert metrics["train_steps"][0]["gradient_norm_before_clipping"] > 0
    assert len(metrics["inference_warm_seconds"]) == 2
    assert metrics["manipulation_success"] is None
    assert metrics["learned_policy_quality"] is None
    assert result.claims == ["act_synthetic_training_and_inference"]
    store = EvidenceStore(tmp_path)
    assert store.verify(result.run_id) == result
    assert json.loads((store.directory(result.run_id) / "metrics.json").read_text()) == metrics
    architecture = json.loads((store.directory(result.run_id) / "act_config.json").read_text())
    assert architecture["pretrained_backbone_weights"] is None
    assert architecture["use_vae"]
    assert architecture["input_features"]["observation.state"]["shape"] == [12]
    assert len(architecture["input_features"]) == 4
