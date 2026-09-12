"""Protocol fixtures only; no training, checkpoints or optional ML dependencies."""

import hashlib
import json
from types import SimpleNamespace

import pytest

from bimanual import training_cohort as module
from bimanual.evidence import EvidenceStore, canonical, digest_file


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    (dataset / "export_manifest.json").write_text("{}")
    views = tmp_path / "views.json"
    views.write_text("{}")
    monkeypatch.setattr(
        module, "verify_training_dataset", lambda root: {"manifest_sha256": "a" * 64}
    )
    monkeypatch.setattr(
        module,
        "load_skill_views",
        lambda *a, **k: SimpleNamespace(
            profile="dinner_nominal_skill_views_v2",
            export_manifest_sha256="a" * 64,
            manifest_sha256="b" * 64,
        ),
    )
    store = EvidenceStore(tmp_path / "evidence")
    ids = {}
    training = None
    for role, kind in zip(module.ROLES, module.KINDS, strict=True):
        directory = store.new_run()
        config = (
            {"skill_id": "handoff_transfer"}
            if role == "training"
            else {"training_run": training.run_id, "training_sha256": training.manifest_sha256}
        )
        if role == "recorded":
            (directory / "driver.py").write_text("# recorded evaluator")
        if role == "experiment_protocol":
            (directory / "driver.py").write_text("# training protocol driver")
            scripts = {
                "recorded": "evaluate-dinner-handoff-v2.py",
                "physical_prefix2": "evaluate-handoff-physical-prefix2.py",
                "physical_prefix5": "evaluate-handoff-prefix5-optimized.py",
            }
            config = dict(
                training=training.config,
                driver_sha256=digest_file(directory / "driver.py"),
                evaluation_scripts={
                    name: store.verify(ids[r]).files["driver.py"] for r, name in scripts.items()
                },
            )
        if role.startswith("physical"):
            (directory / "driver.py").write_text(f"# frozen prefix {role[-1]} fixture")
            config["timeout_seconds"] = 900
        run = store.seal(
            directory,
            kind=kind,
            outcome=(
                "prepared"
                if role == "experiment_protocol"
                else "completed"
                if role in {"training", "recorded"}
                else "failed"
            ),
            config=config,
            metrics={"training_completed": True, "timed_out": True},
            source={},
            claims=[],
        )
        ids[role] = run.run_id
        if role == "training":
            training = run
    return dataset, views, store, ids, tmp_path / "protocol.json"


def create(inputs):
    dataset, views, store, ids, path = inputs
    return module.create_training_cohort_protocol(
        dataset, views, ids, store=store, destination=path
    )


def reseal(body):
    body["manifest_sha256"] = hashlib.sha256(
        canonical({k: v for k, v in body.items() if k != "manifest_sha256"})
    ).hexdigest()
    return body


def test_exact_write_once_relative_protocol(inputs):
    result = create(inputs)
    assert module.load_training_cohort_protocol(inputs[-1]) == result
    assert [c["skill_id"] for c in result.configs] == list(module.COHORT_SKILLS)
    assert all(c["steps"] == 20000 and c["corrective_dataset_path"] is None for c in result.configs)
    assert result.dataset_root == "dataset"
    assert not result.execution_authorized_by_this_artifact
    assert all(not p.nested_evaluation_verified for p in result.prerequisites)
    assert result.prerequisites[2].driver_sha256
    assert result.prerequisites[2].wrapper_details["timed_out"] is True
    assert result.prerequisites[2].wrapper_details["sealed_file_count"] == 1
    assert len(result.prerequisites[2].wrapper_details["sealed_files_sha256"]) == 64
    with pytest.raises(FileExistsError):
        create(inputs)


@pytest.mark.parametrize(
    "change",
    [
        lambda b: b["configs"].reverse(),
        lambda b: b["configs"][0].update(steps=19999),
        lambda b: b["configs"][0].update(chunk_size=50),
        lambda b: b.update(dataset_root="/absolute/dataset"),
        lambda b: b["prerequisites"].pop(),
    ],
)
def test_resealed_invalid_configs_rejected(inputs, change):
    result = create(inputs)
    body = result.model_dump(mode="json")
    change(body)
    with pytest.raises(ValueError):
        module.TrainingCohortProtocol.model_validate(reseal(body))


def test_changed_source_and_unsealed_prerequisite(inputs):
    create(inputs)
    dataset, views, store, ids, path = inputs
    (dataset / "export_manifest.json").write_text("changed")
    with pytest.raises(ValueError, match="digest"):
        module.load_training_cohort_protocol(path)
    (dataset / "export_manifest.json").write_text("{}")
    (store.directory(ids["physical_prefix2"]) / "manifest.json").unlink()
    with pytest.raises(FileNotFoundError):
        module.load_training_cohort_protocol(path)


def test_missing_prerequisite_rejected_before_write(inputs):
    dataset, views, store, ids, path = inputs
    ids.pop("physical_prefix5")
    with pytest.raises(ValueError, match="five"):
        module.create_training_cohort_protocol(dataset, views, ids, store=store, destination=path)
    assert not path.exists()


def test_body_tamper_rejected(inputs):
    create(inputs)
    path = inputs[-1]
    data = json.loads(path.read_text())
    data["views_file_sha256"] = "0" * 64
    path.write_bytes(canonical(data))
    with pytest.raises(ValueError, match="seal"):
        module.load_training_cohort_protocol(path)


@pytest.mark.parametrize("prefix,accepted", [(2, True), (5, False)])
def test_nested_physical_prefix_is_verified(inputs, prefix, accepted):
    dataset, views, store, ids, path = inputs
    parent = store.new_run()
    (parent / "driver.py").write_bytes(
        (store.directory(ids["physical_prefix2"]) / "driver.py").read_bytes()
    )
    child_store = EvidenceStore(parent / "child-evidence")
    child_root = child_store.new_run()
    child = child_store.seal(
        child_root,
        kind="learned_handoff_physical_diagnostic",
        outcome="failed",
        config={"training_run": ids["training"], "execute_chunk_steps": prefix},
        metrics={},
        source={},
        claims=[],
    )
    wrapper = store.seal(
        parent,
        kind="learned_handoff_physical_diagnostic_process",
        outcome="failed",
        config={"training_run": ids["training"], "timeout_seconds": 900},
        metrics={
            "child_run_id": child.run_id,
            "child_sha256": child.manifest_sha256,
            "returncode": 1,
            "timed_out": False,
        },
        source={},
        claims=[],
    )
    ids["physical_prefix2"] = wrapper.run_id
    if accepted:
        result = create(inputs)
        assert result.prerequisites[2].nested_evaluation_verified
    else:
        with pytest.raises(ValueError, match="prefix"):
            create(inputs)


@pytest.mark.parametrize("substitution", ["driver", "config", "protocol_driver"])
def test_prepared_protocol_rejects_substitution(inputs, substitution):
    dataset, views, store, ids, path = inputs
    original = store.verify(ids["experiment_protocol"])
    directory = store.new_run()
    driver = store.directory(original.run_id) / "driver.py"
    (directory / "driver.py").write_bytes(driver.read_bytes())
    config = json.loads(json.dumps(original.config))
    if substitution == "driver":
        config["evaluation_scripts"]["evaluate-dinner-handoff-v2.py"] = "0" * 64
    elif substitution == "config":
        config["training"]["steps"] = 1
    else:
        config["driver_sha256"] = "0" * 64
    replaced = store.seal(
        directory,
        kind=original.kind,
        outcome="prepared",
        config=config,
        metrics={},
        source={},
        claims=[],
    )
    ids["experiment_protocol"] = replaced.run_id
    with pytest.raises(ValueError, match="driver|configuration"):
        create(inputs)
    assert not path.exists()
