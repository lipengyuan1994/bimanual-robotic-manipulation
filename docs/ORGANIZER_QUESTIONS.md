# Organizer questions and user actions

Status: **draft, not sent**. The user owns registration and external communication.

Register and create/join the online team if not already done. Request remote or
borrowed Core Ultra Series 2/3 access. No purchase is assumed.

## Ready-to-send message

Hello! We are preparing for the Intel Physical AI online challenge using simulated
dual SO-101 arms in MuJoCo. We plan a reproducible dinner-table workflow with a
trained ACT skill policy, camera/language reasoning, and a physical object hand-off.
Could you clarify:

1. What preparation and implementation are allowed before the online build starts?
   May existing project code be extended if its history and event-window work are disclosed?
2. Is remote Core Ultra Series 2/3 access available for online teams? Both simulation
   and inference will need to run there. Are there training credits or other compute
   resources, and what are their access terms?
3. Will organizers provide official SO-101 assets, a dinner scene, datasets, or test seeds?
4. Does a complete drawer/utensil/plate/cup task with a real hand-off satisfy the
   bimanual scenario without pouring in the first release? Is VLM plus ACT accepted
   under the related-policy option?
5. What is the exact submission deadline/time zone, and are a public live URL, deck,
   video duration, or additional forms required beyond the track PDF package?

Thank you!

## How to record the answer

Keep the source URL/message reference, date, organizer role and relevant answer in
a new decision record. Update the status and requirement matrix. Do not put private
credentials or access tokens in repository documentation.

## Public-source recheck — September 10, 2026

Read the rendered [event page](https://lablab.ai/ai-hackathons/ai-infra-summit-hackathon),
the [live dashboard](https://lablab.ai/ai-hackathons/ai-infra-summit-hackathon/live),
and all five pages of the current [online brief](https://drive.google.com/file/d/1xSisqTQUAFQiLOpjLZrCVTCsQi4bMCpO/view)
in the Google Drive viewer. This is a content recheck, not a new PDF checksum verification.
The public track link opened only the event header; additional track-panel or
enrollment-only information could not be verified. No organizer message was sent.

| Question | Public answer | Remaining uncertainty |
|---|---|---|
| Q1: Build window / existing code | Event header shows September 10, 2026, 11:00 AM EDT; live dashboard says submissions open. | No explicit early-work or existing-code reuse ruling. The recorded preparation boundary is not automatically lifted by a date change. |
| Q2: Hardware / compute | Brief p.3 permits local/cloud training, says Intel does not provide training infrastructure, and requires final simulation plus inference on Core Ultra Series 2/3. | No remote hardware allocation, credit amount, or access terms found. |
| Q3: Supplied assets / seeds | Brief p.4 requires a reproducible simulation package and 10 randomized seeds. | No supplied scene, dataset, asset bundle, or official seed list found. |
| Q4: ACT / hand-off scope | Brief p.2 explicitly lists ACT; p.4 recommends at least one hand-off or complementary dual-arm action. | VLM plus ACT is consistent with the stated requirements, not an organizer approval of our implementation. Pouring is an example on p.1; omission is not expressly approved. |
| Q5: Deadline / submission | Rendered event banner: September 16, 2026, 2:30 PM EDT (18:30 UTC). Brief p.4 lists repository, simulation package, Intel benchmark script, 10-seed video, and technical README/architecture summary. | Public live app URL, deck, video duration, extra forms, and any track-specific deadline exception remain unverified. |

The rubric remains 30/20/15/20/10/5. Our main remaining organizer questions are
existing preparation-code eligibility, remote Intel access, supplied evaluation
materials, pouring scope, and additional submission-form requirements.

## Signed-in recheck — September 10, 2026

This supersedes the earlier inability to read the full event page. The user signed
in and the Tracks, Guidelines, and Schedule sections became accessible.
The expanded online track links the same five-page brief.

- **Build participation:** Online instructions explicitly say to join the September
  10 kickoff and start building. No track assignment is required; each project can
  enter one track. Existing preparation-code reuse is not explicitly addressed.
- **Intel resources:** the track links [Intel Hack-a-thon Resources](https://docs.openedgeplatform.intel.com/dev/edge-ai-suites/robotics-ai-suite/resources/hackathon_resources.html).
  It describes Ubuntu 24.04, Intel drivers, OpenVINO 2026.3, Physical AI Studio,
  LeRobot/PyTorch XPU, installation scripts, and functional verification. This is
  target-host guidance, not a remote hardware allocation. These Intel/Linux
  installers are not appropriate for our Apple Silicon development Mac.
- **Submission assets:** event Guidelines explicitly list cover image, video,
  slides, public repository, demo platform, application URL, descriptions and tags.
  The linked [Rule Book](https://lablab.ai/hackathon-rules) specifies a 16:9 PNG/JPG
  cover, MP4 video, PDF slides, and a URL for interactive evaluation. Prepare these
  alongside the track PDF deliverables; our static lessons are not the application.
- **Form inspection:** only step 1 of the three-step form was read. It asks for
  title, descriptions, participation mode, categories, technologies, and track.
  No fields were filled or submission saved. Later validation and video duration
  remain unverified.
- **Deadline:** the signed-in schedule confirms September 16, 2:30 PM EDT.
- **Compute/materials:** no remote Intel allocation, training credit entitlement,
  or official dinner-scene/dataset/seed download was found in the track panel.
  Speechmatics credits appear as bonus prizes, not robotics training resources.

Remaining questions: remote Intel access, existing preparation-code reuse,
supplied evaluation assets/seeds, explicit pouring omission, video duration, and
track-specific interpretation of hosted interactive evaluation.
