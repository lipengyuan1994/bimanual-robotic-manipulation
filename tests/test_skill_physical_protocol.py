"""Frozen protocol metadata fixtures; no model, rendering, or physical execution."""

import hashlib
import json
from types import SimpleNamespace

import pytest

from bimanual import skill_physical_protocol as module
from bimanual.cli import main
from bimanual.evidence import canonical
from bimanual.training_cohort import COHORT_SKILLS


def reseal(body):
    body["manifest_sha256"] = hashlib.sha256(
        canonical({key: value for key, value in body.items() if key != "manifest_sha256"})
    ).hexdigest()
    return body


def test_create_and_reverify_exact_six_skill_suite(tmp_path, monkeypatch):
    cohort = tmp_path / "training.json"
    cohort.write_text("{}")
    monkeypatch.setattr(
        module,
        "load_training_cohort_protocol",
        lambda path: SimpleNamespace(manifest_sha256="a" * 64),
    )
    target = tmp_path / "physical.json"
    result = module.create_skill_physical_protocol(cohort, target)
    assert module.load_skill_physical_protocol(target) == result
    assert [row["skill_id"] for row in result.configs] == list(COHORT_SKILLS)
    assert [row["max_actions"] for row in result.configs] == [1900, 1038, 1964, 1120, 1408, 1408]
    assert all(row["execute_chunk_steps"] == 2 for row in result.configs)
    assert result.release_qualified is False
    with pytest.raises(FileExistsError):
        module.create_skill_physical_protocol(cohort, target)


@pytest.mark.parametrize(
    "change",
    [
        lambda body: body["configs"].reverse(),
        lambda body: body["configs"][0].update(max_actions=9999),
        lambda body: body["configs"][0].update(execute_chunk_steps=5),
        lambda body: body.update(training_cohort_path="/absolute/cohort.json"),
        lambda body: body.update(release_qualified=True),
    ],
)
def test_resealed_changes_are_rejected(tmp_path, monkeypatch, change):
    cohort = tmp_path / "training.json"
    cohort.write_text("{}")
    monkeypatch.setattr(
        module,
        "load_training_cohort_protocol",
        lambda path: SimpleNamespace(manifest_sha256="a" * 64),
    )
    target = tmp_path / "physical.json"
    module.create_skill_physical_protocol(cohort, target)
    body = json.loads(target.read_text())
    change(body)
    with pytest.raises(ValueError):
        module.SkillPhysicalProtocol.model_validate(reseal(body))


def test_protocol_cli_create_and_check_wiring(tmp_path, monkeypatch, capsys):
    calls = []
    result = SimpleNamespace(model_dump=lambda **kwargs: {"release_qualified": False})
    monkeypatch.setattr(
        module,
        "create_skill_physical_protocol",
        lambda cohort, destination: calls.append((cohort, destination)) or result,
    )
    monkeypatch.setattr(
        module,
        "load_skill_physical_protocol",
        lambda path: calls.append(path) or result,
    )
    cohort, destination = tmp_path / "cohort.json", tmp_path / "physical.json"
    assert (
        main(
            [
                "skill-physical-protocol-create",
                "--training-cohort",
                str(cohort),
                "--destination",
                str(destination),
            ]
        )
        == 0
    )
    assert main(["skill-physical-protocol-check", str(destination)]) == 0
    assert calls == [(cohort, destination), destination]
    assert capsys.readouterr().out.count('"release_qualified": false') == 2
