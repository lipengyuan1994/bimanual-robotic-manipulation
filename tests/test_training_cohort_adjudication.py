"""CPU-only adjudication fixtures; no model, MPS operation, or training run."""

import sys
from types import SimpleNamespace

import pytest
from test_training_cohort import inputs  # noqa: F401

from bimanual import training_cohort_adjudication as module
from bimanual.cli import main
from bimanual.evidence import EvidenceStore, canonical, digest_file
from bimanual.training import ACTTrainingConfig
from bimanual.training_cohort import COHORT_SKILLS, create_training_cohort_protocol


def failed_attempt(inputs, *, steps=()):  # noqa: F811
    dataset, views, store, ids, protocol_path = inputs
    protocol = create_training_cohort_protocol(
        dataset, views, ids, store=store, destination=protocol_path
    )
    skill = COHORT_SKILLS[1]
    raw = protocol.configs[1]
    config = ACTTrainingConfig.model_validate(
        raw
        | {
            "dataset_path": (protocol_path.parent / raw["dataset_path"]).resolve(),
            "skill_views_path": (protocol_path.parent / raw["skill_views_path"]).resolve(),
        }
    )
    wrapper_directory = store.new_run()
    child_store = EvidenceStore(wrapper_directory / "training-evidence")
    child_directory = child_store.new_run()
    (child_directory / "error.txt").write_text(module.ERROR)
    (child_directory / "metrics.json").write_bytes(canonical({"steps": list(steps)}))
    child = child_store.seal(
        child_directory,
        kind="act_training",
        outcome="failed",
        config=config.model_dump(mode="json"),
        metrics={
            "requested_device": "mps",
            "actual_device": None,
            "training_completed": False,
            "steps": list(steps),
        },
        source={},
        claims=[],
    )
    metadata = {
        "protocol_sha256": protocol.manifest_sha256,
        "protocol_file_sha256": digest_file(protocol_path),
        "skill_id": skill,
        "training": config.model_dump(mode="json"),
        "runner_source_sha256": "a" * 64,
    }
    (wrapper_directory / "cohort-attempt.json").write_bytes(canonical(metadata))
    (wrapper_directory / "protocol.json").write_bytes(protocol_path.read_bytes())
    (wrapper_directory / "runner-error.json").write_bytes(canonical({"error": module.ERROR}))
    wrapper = store.seal(
        wrapper_directory,
        kind=module.ATTEMPT_KIND,
        outcome="failed",
        config=metadata,
        metrics={"training_complete": False, "physical_success": None},
        source={},
        claims=[],
    )
    return protocol_path, store, wrapper, child


def allow_mps(monkeypatch):
    mps = SimpleNamespace(
        is_built=lambda: True,
        is_available=lambda: True,
    )
    fake = SimpleNamespace(
        backends=SimpleNamespace(mps=mps),
        mps=SimpleNamespace(device_count=lambda: 1),
    )
    monkeypatch.setitem(sys.modules, "torch", fake)
    monkeypatch.setattr(module.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(module.importlib.metadata, "version", lambda name: f"test-{name}")


def test_zero_update_failure_is_preserved_and_authorizes_one_replacement(
    inputs,  # noqa: F811
    monkeypatch,
):
    protocol_path, store, wrapper, child = failed_attempt(inputs)
    allow_mps(monkeypatch)
    result = module.adjudicate_training_cohort_preflight(protocol_path, wrapper.run_id)
    assert result.outcome == "completed"
    assert result.metrics["failed_updates"] == 0
    assert result.metrics["failed_child_run_id"] == child.run_id
    assert result.metrics["replacement_attempts_authorized"] == 1
    assert result.metrics["training_success"] is None
    assert result.metrics["live_native_mps_probe"]["torch"] == "test-torch"
    assert module.adjudicate_training_cohort_preflight(protocol_path, wrapper.run_id) == result
    protocol = module.load_training_cohort_protocol(protocol_path)
    assert module.adjudicated_attempt_ids(
        store, protocol_path, protocol, wrapper.config["skill_id"]
    ) == {wrapper.run_id}


def test_attempt_with_any_update_cannot_be_adjudicated(inputs, monkeypatch):  # noqa: F811
    protocol_path, _, wrapper, _ = failed_attempt(inputs, steps=({"step": 1},))
    allow_mps(monkeypatch)
    with pytest.raises(ValueError, match="advanced"):
        module.adjudicate_training_cohort_preflight(protocol_path, wrapper.run_id)


def test_live_mps_probe_must_pass(inputs, monkeypatch):  # noqa: F811
    protocol_path, _, wrapper, _ = failed_attempt(inputs)
    monkeypatch.setattr(module.platform, "machine", lambda: "arm64")
    fake = SimpleNamespace(
        backends=SimpleNamespace(
            mps=SimpleNamespace(is_built=lambda: True, is_available=lambda: False)
        )
    )
    monkeypatch.setitem(sys.modules, "torch", fake)
    with pytest.raises(RuntimeError, match="Live native MPS probe"):
        module.adjudicate_training_cohort_preflight(protocol_path, wrapper.run_id)


def test_cli_wires_explicit_attempt(tmp_path, monkeypatch, capsys):
    seen = []
    result = SimpleNamespace(model_dump=lambda **kwargs: {"outcome": "completed"})
    monkeypatch.setattr(
        module,
        "adjudicate_training_cohort_preflight",
        lambda protocol, attempt: seen.append((protocol, attempt)) or result,
    )
    protocol = tmp_path / "protocol.json"
    assert (
        main(
            [
                "training-cohort-adjudicate-preflight",
                str(protocol),
                "--attempt",
                "failed-run",
            ]
        )
        == 0
    )
    assert seen == [(protocol, "failed-run")]
    assert '"outcome": "completed"' in capsys.readouterr().out
