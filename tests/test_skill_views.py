"""Synthetic sealed metadata fixtures; no LeRobot export, model or simulator execution."""

import gzip
import hashlib
import json
import shutil

import pytest
from PIL import Image
from test_contracts import episode, observation

from bimanual.contracts import DemonstrationEpisode
from bimanual.dataset_export import CAMERA_FEATURES
from bimanual.dinner_teacher import ASSETS
from bimanual.dual_arm import JOINT_ORDER
from bimanual.evidence import canonical, digest_file
from bimanual.skill_views import (
    INTERVALS,
    PLAN_SHA256,
    SkillView,
    action_window,
    create_skill_views,
    load_skill_views,
    validate_action_window,
)


def write_json(path, data):
    path.write_text(json.dumps(data, separators=(",", ":")) + "\n")


def seal_fixture(root, *, kind="dinner_teacher", outcome="completed"):
    raw = root / "raw_sources/000000"
    data = json.loads((raw / "demonstration/episode.json").read_text())
    for name in ("scene", "config", "controller"):
        data["lineage"][name]["sha256"] = digest_file(raw / data["lineage"][name]["path"])
    write_json(raw / "demonstration/episode.json", data)
    record = DemonstrationEpisode.model_validate(data)
    source = dict(
        schema_version=1,
        run_id="synthetic-dinner-fixture",
        created_at="2026-09-11T00:00:00Z",
        kind=kind,
        outcome=outcome,
        claims=[],
        config={},
        metrics={"score": json.loads((raw / "score.json").read_text())},
        provenance={"git_revision": "a" * 40, "source_sha256": "b" * 64},
        files={
            str(path.relative_to(raw)): digest_file(path)
            for path in raw.rglob("*")
            if path.is_file() and path.name != "manifest.json"
        },
    )
    # Include the teacher asset manifest too; only the outer source seal is excluded.
    source["files"]["teacher-assets/manifest.json"] = digest_file(
        raw / "teacher-assets/manifest.json"
    )
    source["manifest_sha256"] = hashlib.sha256(canonical(source)).hexdigest()
    write_json(raw / "manifest.json", source)
    payload = dict(
        schema_version=1,
        format="lerobot_v3",
        lerobot_version="0.6.1",
        repo_id="fixture/dinner",
        fps=20,
        storage="images",
        split="train",
        frames=4819,
        camera_features=CAMERA_FEATURES,
        joint_order=list(JOINT_ORDER),
        episodes=[
            dict(
                episode_index=0,
                episode_id=record.episode_id,
                raw_root="raw_sources/000000",
                episode_sha256=digest_file(raw / "demonstration/episode.json"),
                evidence_manifest_sha256=digest_file(raw / "manifest.json"),
                seed=record.lineage.seed,
                split=record.lineage.split,
                exported_transitions=4819,
                lineage=record.lineage.model_dump(),
            )
        ],
        files={
            str(path.relative_to(root)): digest_file(path)
            for path in root.rglob("*")
            if path.is_file() and path != root / "export_manifest.json"
        },
    )
    payload["manifest_sha256"] = hashlib.sha256(canonical(payload)).hexdigest()
    write_json(root / "export_manifest.json", payload)


@pytest.fixture(scope="module")
def synthetic_export(tmp_path_factory):
    root = tmp_path_factory.mktemp("skill-view-source") / "dataset"
    raw = root / "raw_sources/000000"
    (raw / "demonstration").mkdir(parents=True)
    shutil.copytree(ASSETS, raw / "teacher-assets")
    shutil.copyfile(ASSETS / "scene.xml", raw / "scene.xml")
    write_json(raw / "config.json", {"record_demonstration": True, "fixture": True})
    write_json(
        raw / "controller.json",
        dict(
            kind="scripted_teacher",
            seed=0,
            split="train",
            teacher_uses_simulator_truth=True,
            plan="teacher-assets/plan.json.gz",
            plan_sha256=PLAN_SHA256,
        ),
    )
    write_json(raw / "score.json", {"full_workflow_success": True, "fixture_only": True})
    images = []
    for index in range(3):
        path = raw / f"camera-{index}.png"
        Image.new("RGB", (480, 270), (index, 0, 0)).save(path)
        images.append(dict(path=path.name, sha256=digest_file(path)))
    plan = json.loads(gzip.decompress((ASSETS / "plan.json.gz").read_bytes()))
    data = episode()
    data["lineage"]["seed"] = 0
    data["lineage"]["controller"]["path"] = "controller.json"
    data["joint_limits"] = dict(lower_rad=[-10.0] * 12, upper_rad=[10.0] * 12)
    data["frames"], phases, actions = [], [], []
    for index in range(4820):
        obs = observation(index)
        for camera, artifact in zip(obs["frames"], images, strict=True):
            camera["artifact"] = artifact
        final = index == 4819
        step = plan["steps"][min(index, 4818)]
        data["frames"].append(dict(observation=obs, action_rad=None if final else step["q"]))
        sidecar = dict(
            episode_id=data["episode_id"],
            observation_sequence=index,
            simulation_seconds=index / 20,
            phase=step["phase"],
            terminal=final,
            transition_applied=not final,
        )
        if final:
            sidecar["boundary"] = "last_complete_control_boundary"
        phases.append(sidecar)
        if not final:
            actions.append(
                dict(
                    t=index / 20,
                    phase=step["phase"],
                    q=step["q"],
                    episode_id=data["episode_id"],
                    applied=True,
                )
            )
    write_json(raw / "demonstration/episode.json", data)
    for name, records in (("demonstration/phases.jsonl", phases), ("actions.jsonl", actions)):
        (raw / name).write_text("".join(json.dumps(item) + "\n" for item in records))
    (root / "SYNTHETIC_FIXTURE.txt").write_text(
        "Metadata contract fixture, not a real LeRobot export"
    )
    seal_fixture(root)
    return root


def test_verified_views_keep_one_parent_and_original_boundaries(tmp_path, synthetic_export):
    path = tmp_path / "views.json"
    result = create_skill_views(synthetic_export, path)
    assert load_skill_views(path, dataset_root=synthetic_export) == result
    assert result.independent_scene_count == 1 and result.seed == 0 and result.split == "train"
    assert {view.parent_episode_id for view in result.views} == {result.parent_episode_id}
    assert tuple((view.skill_id, view.start, view.end) for view in result.views) == INTERVALS
    assert sum(view.end - view.start for view in result.views) == 4819
    with pytest.raises(FileExistsError):
        create_skill_views(synthetic_export, path)
    with pytest.raises(ValueError, match="outside"):
        create_skill_views(synthetic_export, synthetic_export / "new-view.json")


@pytest.mark.parametrize("index", range(7))
def test_action_windows_clamp_before_every_skill_boundary(index):
    name, start, end = INTERVALS[index]
    view = SkillView(
        skill_id=name, parent_episode_id="original", start=start, end=end, terminal_parent_frame=end
    )
    window = action_window(view, end - start - 2, 100)
    assert window.parent_observation_index == end - 2
    assert window.parent_action_indices == (end - 2,) + (end - 1,) * 99
    assert window.action_is_pad == (False, False) + (True,) * 98
    assert window.terminal_parent_frame == end
    assert not {"phase", "skill_id", "target"} & window.model_dump().keys()
    validate_action_window(view, end - start - 2, window)
    altered = window.model_copy(update={"parent_action_indices": (end,) * 100})
    with pytest.raises(ValueError, match="boundary"):
        validate_action_window(view, end - start - 2, altered)
    terminal = action_window(view, end - start - 1, 1)
    assert terminal.parent_action_indices == (end - 1,) and terminal.action_is_pad == (False,)


@pytest.mark.parametrize(
    "local,horizon", [(-1, 10), (630, 10), (True, 10), (0, 0), (0, 101), (0, True)]
)
def test_bad_indices_and_horizons_are_rejected(local, horizon):
    view = SkillView(
        skill_id="handoff_transfer",
        parent_episode_id="original",
        start=0,
        end=630,
        terminal_parent_frame=630,
    )
    with pytest.raises(ValueError):
        action_window(view, local, horizon)


def test_fictitious_extended_skill_range_is_rejected():
    with pytest.raises(ValueError, match="cross-skill"):
        SkillView(
            skill_id="handoff_transfer",
            parent_episode_id="original",
            start=0,
            end=1570,
            terminal_parent_frame=1570,
        )


def test_action_window_cannot_smuggle_boolean_indices_or_numeric_padding():
    view = SkillView(
        skill_id="handoff_transfer",
        parent_episode_id="original",
        start=0,
        end=630,
        terminal_parent_frame=630,
    )
    valid = action_window(view, 0, 1)
    for updates in ({"parent_action_indices": (False,)}, {"action_is_pad": (0,)}):
        with pytest.raises(ValueError):
            validate_action_window(view, 0, valid.model_copy(update=updates))


def test_manifest_tampering_and_invented_split_are_rejected(tmp_path, synthetic_export):
    path = tmp_path / "views.json"
    result = create_skill_views(synthetic_export, path)
    historic = result.model_dump(mode="json")
    historic["derivation_source_sha256"] = "d" * 64
    historic["manifest_sha256"] = hashlib.sha256(
        canonical({key: value for key, value in historic.items() if key != "manifest_sha256"})
    ).hexdigest()
    write_json(path, historic)
    assert (
        load_skill_views(path, dataset_root=synthetic_export).derivation_source_sha256 == "d" * 64
    )
    data = result.model_dump(mode="json")
    data["parent_run_id"] = "different"
    write_json(path, data)
    with pytest.raises(ValueError, match="digest"):
        load_skill_views(path, dataset_root=synthetic_export)
    data["manifest_sha256"] = hashlib.sha256(
        canonical({k: v for k, v in data.items() if k != "manifest_sha256"})
    ).hexdigest()
    write_json(path, data)
    with pytest.raises(ValueError, match="linkage"):
        load_skill_views(path, dataset_root=synthetic_export)
    data["split"] = "test"
    write_json(path, data)
    with pytest.raises(ValueError):
        load_skill_views(path, dataset_root=synthetic_export)


@pytest.mark.parametrize(
    "fault",
    ["failure", "controller", "phase", "unapplied", "targets", "terminal", "seed", "corrupt"],
)
def test_ineligible_or_altered_recording_rejected_before_manifest_write(
    tmp_path, synthetic_export, fault
):
    root = tmp_path / "dataset"
    shutil.copytree(synthetic_export, root)
    raw = root / "raw_sources/000000"
    if fault == "controller":
        path = raw / "controller.json"
        data = json.loads(path.read_text())
        data["kind"] = "learned_policy"
        write_json(path, data)
    elif fault in ("phase", "terminal"):
        path = raw / "demonstration/phases.jsonl"
        records = [json.loads(line) for line in path.read_text().splitlines()]
        if fault == "phase":
            records[630]["phase"] = "cup/hold"
        else:
            records[-1]["boundary"] = "pre_unconfirmed_action"
        path.write_text("".join(json.dumps(row) + "\n" for row in records))
    elif fault in ("unapplied", "targets"):
        path = raw / "actions.jsonl"
        records = [json.loads(line) for line in path.read_text().splitlines()]
        if fault == "unapplied":
            records[630]["applied"] = False
        else:
            records[629]["q"][0] += 0.001
        path.write_text("".join(json.dumps(row) + "\n" for row in records))
    elif fault == "seed":
        path = raw / "demonstration/episode.json"
        data = json.loads(path.read_text())
        data["lineage"]["seed"] = 1
        write_json(path, data)
    seal_fixture(root, outcome="failed" if fault == "failure" else "completed")
    if fault == "corrupt":
        (raw / "camera-0.png").write_bytes(b"corrupt")
    path = tmp_path / "views.json"
    with pytest.raises(ValueError):
        create_skill_views(root, path)
    assert not path.exists()
