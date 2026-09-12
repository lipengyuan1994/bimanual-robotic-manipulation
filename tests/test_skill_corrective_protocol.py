import json

from bimanual.evidence import EvidenceStore
from bimanual.skill_corrective_protocol import (
    create_skill_corrective_collection_protocol,
    load_skill_corrective_collection_protocol,
)


def test_freezes_and_reverifies_corrective_families(tmp_path):
    store = EvidenceStore(tmp_path / "evidence")
    suite_dir = store.new_run()
    suite = store.seal(
        suite_dir,
        kind="six_skill_teacher_prepared_physical_suite_report",
        outcome="failed",
        config={},
        metrics={},
        source={},
        claims=[],
    )
    diagnosis_dir = store.new_run()
    diagnosis = store.seal(
        diagnosis_dir,
        kind="six_skill_physical_failure_analysis",
        outcome="completed",
        config={},
        metrics={
            "component_passes": 0,
            "release_qualified": False,
            "suite_run_id": suite.run_id,
            "suite_manifest_sha256": suite.manifest_sha256,
            "components": [
                {"skill_id": skill}
                for skill in (
                    "bar_place_and_return",
                    "cup_pick_place",
                    "plate_pick_place",
                    "drawer_open",
                    "spoon_retrieve_place",
                    "fork_retrieve_place",
                )
            ],
        },
        source={},
        claims=[],
    )
    path = tmp_path / "protocol.json"
    created = create_skill_corrective_collection_protocol(
        evidence_root=store.root, diagnosis_run_id=diagnosis.run_id, destination=path
    )
    assert [row.family_id for row in created.families] == [
        "bar_contact_avoidance",
        "approach_contact",
        "grasp_lift",
        "drawer_pull",
    ]
    assert load_skill_corrective_collection_protocol(path) == created
    assert json.loads(path.read_text())["manifest_sha256"] == created.manifest_sha256
