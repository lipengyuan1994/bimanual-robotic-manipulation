import json

from bimanual.evidence import EvidenceStore
from bimanual.skill_physical_failure_analysis import (
    SkillPhysicalFailureAnalysisConfig,
    _rows_for_actions,
    analyse_skill_physical_failures,
)


def _worker(directory, *, skill, actions=1, contact=False, opening=0.0, bad=False):
    worker = directory / "worker"
    worker.mkdir()
    target = {
        "bar_place_and_return": "practice_object",
        "cup_pick_place": "cup",
        "plate_pick_place": "plate",
        "spoon_retrieve_place": "spoon",
        "fork_retrieve_place": "fork",
    }.get(skill)
    with (worker / "actions.jsonl").open("w") as stream:
        for _ in range(actions):
            stream.write(json.dumps({"applied": True}) + "\n")
    with (worker / "physics.jsonl").open("w") as stream:
        for index in range(actions * 50):
            objects = {}
            if target:
                objects[target] = {
                    "pos": [0.01 if contact else 0.0, 0.0, 0.4],
                    "forces": {"left": [0.02 if contact else 0.0, 0.0], "right": [0.0, 0.0]},
                }
            stream.write(
                json.dumps(
                    {
                        "objects": objects,
                        "drawer_forces": [0.02 if contact else 0.0, 0.02 if contact else 0.0],
                        "opening": opening,
                        "bad": [["x", "y"]] if bad and index == 0 else [],
                    }
                )
                + "\n"
            )


def test_seals_read_only_component_failure_diagnosis(tmp_path):
    store = EvidenceStore(tmp_path / "evidence")
    entries = []
    for skill in (
        "bar_place_and_return",
        "cup_pick_place",
        "plate_pick_place",
        "drawer_open",
        "spoon_retrieve_place",
        "fork_retrieve_place",
    ):
        directory = store.new_run()
        _worker(directory, skill=skill, contact=skill in {"drawer_open", "spoon_retrieve_place"})
        child = store.seal(
            directory,
            kind="learned_skill_teacher_prepared_physical_evaluation",
            outcome="failed",
            config={"skill_id": skill},
            metrics={
                "component_passed": False,
                "actual_policy_devices": ["mps:0"],
                "autonomous_skill_actions": 1,
                "teacher_prefix_actions": 0,
                "reason": "failed",
            },
            source={},
            claims=[],
        )
        entries.append(
            {"skill_id": skill, "run_id": child.run_id, "manifest_sha256": child.manifest_sha256}
        )
    suite_dir = store.new_run()
    suite = store.seal(
        suite_dir,
        kind="six_skill_teacher_prepared_physical_suite_report",
        outcome="failed",
        config={"evaluation_runs": entries},
        metrics={"evaluations_complete": True},
        source={},
        claims=[],
    )
    result = analyse_skill_physical_failures(
        SkillPhysicalFailureAnalysisConfig(suite_run_id=suite.run_id),
        store=store,
        project_root=tmp_path,
    )
    assert result.outcome == "completed"
    assert result.metrics["component_passes"] == 0
    drawer = next(row for row in result.metrics["components"] if row["skill_id"] == "drawer_open")
    assert drawer["target_contact_samples"] == 50
    cup = next(row for row in result.metrics["components"] if row["skill_id"] == "cup_pick_place")
    assert cup["target_contact_samples"] == 0


def test_retains_a_rejected_terminal_partial_action(tmp_path):
    actions = tmp_path / "actions.jsonl"
    physics = tmp_path / "physics.jsonl"
    actions.write_text(
        json.dumps({"applied": True})
        + "\n"
        + json.dumps({"applied": False, "partial_physics": True})
        + "\n"
    )
    physics.write_text("".join(json.dumps({"row": index}) + "\n" for index in range(98)))
    confirmed, rows, total, rejected = _rows_for_actions(actions, physics, teacher_prefix_actions=0)
    assert len(confirmed) == 1
    assert len(rows) == total == 98
    assert rejected == 1
