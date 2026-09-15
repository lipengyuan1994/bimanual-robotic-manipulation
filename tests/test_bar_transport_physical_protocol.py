"""Bar corrective physical protocol fixtures; no model or simulator execution."""

import hashlib
from types import SimpleNamespace

import pytest

from bimanual import bar_transport_physical_protocol as module
from bimanual.cli import main
from bimanual.evidence import EvidenceStore, canonical, digest_file
from bimanual.skill_physical_evaluation import SkillPhysicalEvaluationConfig
from bimanual.skill_physical_process import SkillPhysicalProcessConfig


def _reseal(body):
    body["manifest_sha256"] = hashlib.sha256(
        canonical({key: value for key, value in body.items() if key != "manifest_sha256"})
    ).hexdigest()
    return body


def test_protocol_rejects_a_resealed_incomplete_source_set(tmp_path):
    root = module.Path(module.__file__).resolve().parent
    body = {
        "schema_version": 1,
        "profile": module.PROFILE,
        "training_run": "../runs/training",
        "training_manifest_sha256": "a" * 64,
        "dataset_root": "../dataset",
        "dataset_manifest_sha256": "b" * 64,
        "skill_views_path": "../views.json",
        "skill_views_sha256": "c" * 64,
        "sampling_declaration_sha256": "d" * 64,
        "prior_evaluation_run_id": "prior-evaluation",
        "prior_evaluation_manifest_sha256": "e" * 64,
        "policy_target_margin_rad": module.MARGIN_RAD,
        "evaluation_sources": {
            name: digest_file(root / name) for name in module._evaluation_source_paths(root)
        },
        "device": "mps",
        "execute_chunk_steps": 2,
        "max_actions": 1900,
        "wall_timeout_seconds": 1200.0,
        "execution_authorized_by_this_artifact": False,
    }
    accepted = module.BarTransportPhysicalProtocol.model_validate(_reseal(body.copy()))
    assert accepted.profile == module.PROFILE
    body["evaluation_sources"].pop("bar_transport_physical_protocol.py")
    with pytest.raises(ValueError, match="source bindings"):
        module.BarTransportPhysicalProtocol.model_validate(_reseal(body))


def test_completion_profile_binds_the_exact_margin_failure_predecessor(tmp_path):
    root = module.Path(module.__file__).resolve().parent
    body = {
        "schema_version": 1,
        "profile": module.COMPLETION_PROFILE,
        "training_run": "../runs/training",
        "training_manifest_sha256": "a" * 64,
        "dataset_root": "../dataset",
        "dataset_manifest_sha256": "b" * 64,
        "skill_views_path": "../views.json",
        "skill_views_sha256": "c" * 64,
        "sampling_declaration_sha256": "d" * 64,
        "prior_evaluation_run_id": module.COMPLETION_PREDECESSOR_RUN_ID,
        "prior_evaluation_manifest_sha256": module.COMPLETION_PREDECESSOR_MANIFEST_SHA256,
        "policy_target_margin_rad": module.MARGIN_RAD,
        "evaluation_sources": {
            name: digest_file(root / name) for name in module._evaluation_source_paths(root)
        },
        "device": "mps",
        "execute_chunk_steps": 2,
        "max_actions": 1900,
        "wall_timeout_seconds": 1200.0,
        "execution_authorized_by_this_artifact": False,
    }
    accepted = module.BarTransportPhysicalProtocol.model_validate(_reseal(body.copy()))
    assert accepted.profile == module.COMPLETION_PROFILE

    prior = SimpleNamespace(
        kind=module.KIND,
        outcome="failed",
        run_id=module.COMPLETION_PREDECESSOR_RUN_ID,
        manifest_sha256=module.COMPLETION_PREDECESSOR_MANIFEST_SHA256,
        config={"skill_id": module.SKILL, "device": "mps"},
        metrics={
            "actual_policy_devices": ["mps:0"],
            "failure_code": "physical_milestone_incomplete",
            "reason": (
                "physical_milestone_incomplete: physical completion/readiness not reached "
                "within action budget"
            ),
            "policy_target_margin_rad": module.MARGIN_RAD,
            "autonomous_skill_actions": 1900,
        },
    )

    class Store:
        def verify(self, run_id):
            return prior

    assert (
        module._verify_prior_failure(
            Store(), prior.run_id, tmp_path / "new-training", profile=module.COMPLETION_PROFILE
        )
        is prior
    )
    prior.metrics["autonomous_skill_actions"] = 1899
    with pytest.raises(ValueError, match="margin completion"):
        module._verify_prior_failure(
            Store(), prior.run_id, tmp_path / "new-training", profile=module.COMPLETION_PROFILE
        )


def test_late_workbench_overlap_profile_binds_the_exact_physical_predecessor(tmp_path):
    prior = SimpleNamespace(
        kind=module.KIND,
        outcome="failed",
        run_id="20260915T125916-a7977c78bed6",
        manifest_sha256="2cfe4f44685c85dd69b9a85d79f8c065f42022e6335c9fca10c6341246a0b90b",
        config={"skill_id": module.SKILL, "device": "mps"},
        metrics={
            "actual_policy_devices": ["mps:0"],
            "component_passed": False,
            "autonomous_skill_actions": 255,
            "error": "ValueError: Dinner contact guard: bad_contacts=[]; overlap_m=0.002664566",
        },
    )

    class Store:
        def verify(self, run_id):
            return prior

    assert (
        module._verify_prior_failure(
            Store(),
            prior.run_id,
            tmp_path / "new-training",
            profile=module.LATE_WORKBENCH_OVERLAP_PROFILE,
        )
        is prior
    )
    prior.metrics["autonomous_skill_actions"] = 254
    with pytest.raises(ValueError, match="late workbench-overlap"):
        module._verify_prior_failure(
            Store(),
            prior.run_id,
            tmp_path / "new-training",
            profile=module.LATE_WORKBENCH_OVERLAP_PROFILE,
        )


def test_interrupted_unsealed_process_blocks_retry(tmp_path, monkeypatch):
    store = EvidenceStore(tmp_path / "artifacts")
    training = store.new_run()
    (training / "fixture.txt").write_text("training placeholder")
    store.seal(
        training,
        kind="act_training",
        outcome="completed",
        config={},
        metrics={},
        source={},
        claims=[],
    )
    dataset, views = tmp_path / "dataset", tmp_path / "views.json"
    dataset.mkdir()
    views.write_text("{}")
    protocol_path = tmp_path / "physical.json"
    protocol_path.write_text("fixture")
    protocol = SimpleNamespace(
        manifest_sha256="a" * 64,
        profile=module.PROFILE,
        training_run="artifacts/runs/" + training.name,
        dataset_root="dataset",
        skill_views_path="views.json",
        prior_evaluation_run_id="prior-evaluation",
        prior_evaluation_manifest_sha256="z" * 64,
        device="mps",
        max_actions=1900,
        execute_chunk_steps=2,
        policy_target_margin_rad=module.MARGIN_RAD,
        wall_timeout_seconds=1200.0,
    )
    monkeypatch.setattr(module, "load_bar_transport_physical_protocol", lambda _: protocol)
    monkeypatch.setattr(
        module,
        "_verify_prior_failure",
        lambda *args, **kwargs: SimpleNamespace(manifest_sha256="z" * 64),
    )
    config = SkillPhysicalEvaluationConfig(
        training_run=training,
        dataset_root=dataset,
        skill_views_path=views,
        skill_id=module.SKILL,
        device="mps",
        max_actions=1900,
        execute_chunk_steps=2,
        policy_target_margin_rad=module.MARGIN_RAD,
        wall_timeout_seconds=1200.0,
        evaluation_protocol_sha256=protocol.manifest_sha256,
        evaluation_protocol_file_sha256=digest_file(protocol_path),
    )
    interrupted = store.new_run()
    (interrupted / "config.json").write_text(
        SkillPhysicalProcessConfig(evaluation=config).model_dump_json()
    )
    with pytest.raises(RuntimeError, match="manual adjudication"):
        module.run_bar_transport_physical_protocol(protocol_path)


def test_protocol_check_cli_loads_the_frozen_declaration(tmp_path, monkeypatch, capsys):
    protocol = tmp_path / "physical.json"
    expected = SimpleNamespace(model_dump=lambda **_: {"profile": module.PROFILE})
    monkeypatch.setattr(module, "load_bar_transport_physical_protocol", lambda path: expected)
    assert main(["bar-transport-physical-protocol-check", str(protocol)]) == 0
    assert f'"profile": "{module.PROFILE}"' in capsys.readouterr().out
