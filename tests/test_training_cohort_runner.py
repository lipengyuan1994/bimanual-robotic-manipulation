"""CPU-only coordinator fixtures; synthetic training never loads ACT."""

from types import SimpleNamespace

import pytest
from test_training_cohort import inputs  # noqa: F401

from bimanual import training_cohort_runner as runner
from bimanual.evidence import EvidenceStore, canonical
from bimanual.training_cohort import COHORT_SKILLS, create_training_cohort_protocol
from bimanual.worker_lease import MODEL_JOB_LEASE, WorkerLease


@pytest.fixture
def setup(inputs, monkeypatch):  # noqa: F811
    dataset, views, store, ids, path = inputs
    create_training_cohort_protocol(dataset, views, ids, store=store, destination=path)
    monkeypatch.setattr(runner, "PROJECT_ROOT", path.parent)
    calls = []

    def train(config, *, store, project_root, model_job_lease_path, model_job_lease):
        calls.append(config.skill_id)
        assert model_job_lease is not None
        with pytest.raises(RuntimeError, match="lease"):
            WorkerLease.acquire(model_job_lease_path)
        directory = store.new_run()
        steps = [{"step": i} for i in range(1, 20001)]
        (directory / "steps.jsonl").write_bytes(b"".join(canonical(row) + b"\n" for row in steps))
        (directory / "checkpoint").mkdir()
        (directory / "checkpoint/training_schedule.json").write_bytes(
            canonical({"completed_updates": 20000})
        )
        return store.seal(
            directory,
            kind="act_training",
            outcome="completed",
            config=config.model_dump(mode="json"),
            metrics=dict(steps=steps, **{key: True for key in runner.RELOAD_FLAGS}),
            source={},
            claims=[],
        )

    def checkpoint(path, *, skill_id, dataset_root):
        manifest = EvidenceStore(path.parent.parent).verify(path.name)
        binding = SimpleNamespace(
            training_manifest_sha256=manifest.manifest_sha256,
            view=SimpleNamespace(skill_id=skill_id),
            checkpoint_sha256="d" * 64,
        )
        binding.reverify = lambda: binding
        return binding

    monkeypatch.setattr(runner, "run_train", train)
    monkeypatch.setattr(runner, "load_skill_checkpoint", checkpoint)
    return path, store, calls, train


def test_completed_attempt_skips_retraining(setup):
    path, store, calls, _ = setup
    first = runner.run_training_cohort_skill(path, COHORT_SKILLS[0])
    second = runner.run_training_cohort_skill(path, COHORT_SKILLS[0])
    assert first == second and first.outcome == "completed"
    assert calls == [COHORT_SKILLS[0]]
    assert first.metrics["physical_success"] is None
    assert store.verify(first.run_id) == first


def test_crash_after_child_seal_reconciles_without_retraining(setup, monkeypatch):
    path, store, calls, train = setup

    def crash(*args, **kwargs):
        train(*args, **kwargs)
        raise SystemExit("fixture owner crash")

    monkeypatch.setattr(runner, "run_train", crash)
    with pytest.raises(SystemExit):
        runner.run_training_cohort_skill(path, COHORT_SKILLS[0])
    attempts = list((store.root / "runs").glob("*/cohort-attempt.json"))
    assert len(attempts) == 1 and not (attempts[0].parent / "manifest.json").exists()
    result = runner.run_training_cohort_skill(path, COHORT_SKILLS[0])
    assert result.outcome == "completed" and len(calls) == 1


def test_held_shared_lease_allocates_nothing(setup):
    path, store, calls, _ = setup
    before = set((store.root / "runs").iterdir())
    with WorkerLease.acquire(store.root / MODEL_JOB_LEASE):
        with pytest.raises(RuntimeError, match="lease"):
            runner.run_training_cohort_skill(path, COHORT_SKILLS[0])
    assert set((store.root / "runs").iterdir()) == before and not calls


def test_incomplete_child_is_preserved_and_never_retried(setup, monkeypatch):
    path, store, calls, _ = setup

    def interrupted(config, *, store, **kwargs):
        directory = store.new_run()
        (directory / "partial.txt").write_text("unfinished")
        raise SystemExit("fixture owner death")

    monkeypatch.setattr(runner, "run_train", interrupted)
    with pytest.raises(SystemExit):
        runner.run_training_cohort_skill(path, COHORT_SKILLS[0])
    result = runner.run_training_cohort_skill(path, COHORT_SKILLS[0])
    assert result.outcome == "failed"
    assert any(name.endswith("partial.txt") for name in result.files)
    assert runner.run_training_cohort_skill(path, COHORT_SKILLS[0]) == result


def test_wrong_training_config_fails_closed(setup, monkeypatch):
    path, _, _, train = setup

    def wrong(config, **kwargs):
        return train(config.model_copy(update={"skill_id": COHORT_SKILLS[1]}), **kwargs)

    monkeypatch.setattr(runner, "run_train", wrong)
    result = runner.run_training_cohort_skill(path, COHORT_SKILLS[0])
    assert result.outcome == "failed" and "config mismatch" in result.metrics["error"]


def test_multiple_matching_attempts_are_ambiguous(setup):
    import shutil

    path, store, _, _ = setup
    result = runner.run_training_cohort_skill(path, COHORT_SKILLS[0])
    extra = store.new_run()
    shutil.copy2(
        store.directory(result.run_id) / "cohort-attempt.json", extra / "cohort-attempt.json"
    )
    with pytest.raises(RuntimeError, match="Ambiguous"):
        runner.run_training_cohort_skill(path, COHORT_SKILLS[0])


def test_reverify_mutation_cannot_seal_completed_attempt(setup, monkeypatch):
    path, store, calls, _ = setup
    original = runner.load_skill_checkpoint

    def changed(child_path, **kwargs):
        binding = original(child_path, **kwargs)

        def reverify():
            (child_path / "steps.jsonl").write_text("changed after binding")
            return binding

        binding.reverify = reverify
        return binding

    monkeypatch.setattr(runner, "load_skill_checkpoint", changed)
    result = runner.run_training_cohort_skill(path, COHORT_SKILLS[0])
    assert result.outcome == "failed"
    assert "digest mismatch" in result.metrics["error"]
    assert result.metrics["training_complete"] is False
    assert len(calls) == 1
