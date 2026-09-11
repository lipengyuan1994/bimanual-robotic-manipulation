# Robotics resources

## Knowledge

- [MuJoCo Python guide](https://mujoco.readthedocs.io/en/stable/python.html).
  Read “Basic usage” and the viewer section for lesson 1; explains model/data separation,
  stepping, array copies, and the macOS `mjpython` launcher.
- [MuJoCo computation](https://mujoco.readthedocs.io/en/stable/computation/index.html).
  Use when investigating forces, joint coordinates, contacts, and numerical integration.
- [Robotic Manipulation — Russ Tedrake, MIT](https://manipulation.csail.mit.edu/).
  Use selected “Let's get you a robot” and picking chapters for coordinate frames,
  kinematics, grasping, and planning. The course uses other tooling; do not replace
  our MuJoCo stack merely to follow its examples.
- [LeRobot ACT](https://huggingface.co/docs/lerobot/act).
  Use for demonstrations, action chunks, training configuration, and the first learned baseline.
- [LeRobot compute guide](https://huggingface.co/docs/lerobot/main/en/hardware_guide).
  Use for initial sizing; measure this M1 Pro before estimating actual training duration.
- [Qwen3-VL-4B-Instruct model card](https://huggingface.co/Qwen/Qwen3-VL-4B-Instruct).
  Documents the planned visual planner and its license; not evidence of dinner-task ability.
- [OpenVINO supported models](https://docs.openvino.ai/2026/documentation/compatibility-and-support/supported-models.html).
  Use to check conversion candidates, then test them on the exact target device.
- [PyTorch MPS](https://docs.pytorch.org/docs/stable/notes/mps.html).
  Use to distinguish an available Metal device from verified workload acceleration.

## Wisdom (communities)

- [LeRobot GitHub discussions](https://github.com/huggingface/lerobot/discussions).
  Ask focused tooling questions with versions and a minimal reproducer when needed.
- [MuJoCo GitHub discussions](https://github.com/google-deepmind/mujoco/discussions).
  Useful for contact-model and simulation questions after inspecting a minimal scene.
- [Hackathon event page](https://lablab.ai/ai-hackathons/ai-infra-summit-hackathon).
  Follow the organizer's community links for authoritative eligibility/access answers.

No community message has been sent on the user's behalf.

## Gaps

Event-specific early-work ruling, Intel access, credit terms, official assets/seeds,
and final submission fields remain unconfirmed. See [questions](docs/ORGANIZER_QUESTIONS.md).

- [Learning Fine-Grained Bimanual Manipulation with Low-Cost Hardware (ACT)](https://arxiv.org/abs/2304.13705).
  Primary paper for Lesson 04's discussion of compounding policy errors and action
  sequences; the reported experiments are the authors' results, not this project's.
