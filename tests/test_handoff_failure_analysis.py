"""Synthetic contact traces only; no learned-policy or physical-success evidence."""

import json

import numpy as np

from bimanual.evidence import EvidenceStore
from bimanual.handoff_failure_analysis import _analyse_child


def test_reproduces_post_donor_loss_and_terminal_receiver_opening(tmp_path):
    store = EvidenceStore(tmp_path / "child")
    directory = store.new_run()
    worker = directory / "worker"
    worker.mkdir()
    actions = []
    with (worker / "physics.jsonl").open("w") as physics:
        for action_index in range(41):
            target = [0.0] * 12
            if action_index == 40:
                target[11] = 0.2
            actions.append(
                {
                    "applied": True,
                    "targets_rad": target,
                }
            )
            for sample in range(50):
                lost = action_index == 40 and sample == 0
                physics.write(
                    json.dumps(
                        {
                            "joint_position": [0.0] * 12,
                            "objects": {
                                "practice_object": {
                                    "pos": [0.0, 0.0, 0.4],
                                    "support": [],
                                    "forces": {
                                        "left": [0.0, 0.0] if lost else [1.0, 1.0],
                                        "right": [0.0, 0.0],
                                    },
                                }
                            },
                        }
                    )
                    + "\n"
                )
    (worker / "actions.jsonl").write_text("".join(json.dumps(row) + "\n" for row in actions))
    child = store.seal(
        directory,
        kind="learned_handoff_physical_diagnostic",
        outcome="failed",
        config={"device": "mps", "execute_chunk_steps": 2},
        metrics={
            "physical_success": False,
            "applied_actions": 41,
            "reason": "ValueError: Handoff support/grip continuity lost after donor hold",
        },
        source={},
        claims=[],
    )
    report = _analyse_child(
        store,
        child,
        teacher=np.zeros((1, 12), dtype=float),
        phases=["handoff/left_release"],
    )
    assert report["stage_reached"] == 1
    assert report["stage_transitions"] == [
        {"stage": 1, "action": 40, "sample_in_action": 50, "physics_sample": 2000}
    ]
    assert report["continuity_loss"]["action"] == 41
    assert report["continuity_loss"]["sample_in_action"] == 1
    assert report["terminal_target"]["right_gripper_rad"] == 0.2
    assert report["terminal_right_gripper_error_rad"] == 0.2
    assert report["physical_success"] is False
