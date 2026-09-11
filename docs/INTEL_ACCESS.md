# Zero-cost Intel access

Checked September 11, 2026. The user completed registration and sign-in with an
eligible university account. A free-access request has been submitted and is
**Rejected**. No machine has been allocated or tested, no payment was made,
and no separate organizer message was sent.

The user confirmed that the rejection has no explanation. Intel setup is deferred
until local training is complete, then will be handled as a separate step. No
replacement application, support message or dismissal has been submitted.
Local development continues; actual Intel execution remains unverified.

## Current request

Verified in the signed-in [Instances page](https://cloud.intel.com/preview/compute?region=us-region-3):

| Field | Observed value |
|---|---|
| Instance name | `bimanual-sim-intel` |
| Hardware | `BM-PTL`, Intel Core Ultra Series 3, Panther Lake |
| State | Rejected |
| Use case | AI PC USA |
| Requested duration | 1 week |
| Reservation start shown | 09/10/2026 |
| Reservation end shown | 09/18/2026 12:05 pm; UI did not identify the timezone |
| Operating system | Windows 11, fixed in the request form |
| Access | No SSH key uploaded; browser Connect is documented as available without a key after approval |

The submitted Intended Use is exactly:

> AI Infra Summit hackathon, due Sep 16. Free Core Ultra for MuJoCo and OpenVINO. Ubuntu preferred.

The form permits at most 128 characters and only letters, numbers, spaces,
hyphens, periods and commas. The longer draft below was not submitted.
No secondary owner or Intel co-development access was added. No new agreement
acceptance was presented during the instance request.

The signed-in portal says email review notification is expected within **3 days**,
superseding the shorter public-guide estimate for planning. Approval is not
guaranteed. Wait for the user's approval email or a Ready state before attempting
host access; inspect the actual expiry because pending review already shows dates.

Both BM-LNL and BM-PTL were visible in this account's catalog. BM-LNL lists 32 GB
RAM; BM-PTL lists 32–64 GB. Both request forms offered only Windows 11 with the
OS selector disabled. Ubuntu is a request, not an available selection or promise.
If Windows is supplied, validate a separate native Windows setup and MuJoCo
rendering plus OpenVINO CPU inference before claiming support; the current Mac
bootstrap and Linux setup instructions are not Windows validation. B2 remains open.

## Preferred route: Intel AI PC Cloud

Intel's [AI PC tools page](https://www.intel.com/content/www/us/en/developer/topic-technology/ai-pc/download-get-started.html)
advertises free AI PC Cloud access. Its [quick user guide](https://www.intel.com/content/www/us/en/developer/articles/guide/ai-pc-cloud-quick-user-guide.html)
lists Core Ultra Series 2 (BM-LNL) and Series 3 (BM-PTL), requires a company or
university email for registration, and says requests are processed within 48 hours.
It warns that catalog availability depends on user entitlement and capacity.
These are advertised terms, not an allocation or tested capability for our account.

Use [Intel Cloud Services](https://cloud.intel.com/), sign in with an eligible
account, and inspect Hardware Catalog for BM-LNL or BM-PTL. The tools page also
links [the prerelease portal](https://prerelease.intel.com/); follow Intel's account
flow if redirected. Do not substitute a Xeon, Gaudi, Series 1 or non-Ultra host.
Select only an explicitly free allocation; decline any paid alternative.

The earlier header-only browser issue was resolved after the user completed
registration and sign-in. Catalog and request controls now work. Do not put
passwords or access tokens in this repository.

Suggested instance name: `bimanual-sim-intel`.

Suggested Intended Use text (ready to paste; not submitted):

> We are building an open-source, simulation-only entry for the Intel Bimanual
> VLA Manipulation online track at the AI Infra Summit Hackathon. We need free
> access to an Intel Core Ultra Series 2 or 3 host to run MuJoCo simulation and
> OpenVINO inference together, measure CPU/iGPU performance, and record the final
> demonstration before September 16, 2026, 18:30 UTC. Ubuntu 24.04, remote shell
> access, offscreen OpenGL rendering, and sufficient memory for a 4B visual model
> are preferred. Project: https://github.com/lipengyuan1994/bimanual-robotic-manipulation

## Fallback: organizer referral or borrowed machine

The signed-in event page lists coordination@lablab.ai for coordination questions.
The user can send the draft below or explicitly authorize sending it. No response
or loan is assumed. A borrowed eligible host can be used if its owner authorizes
our workload and access; no physical robot is needed.

Subject: Free Core Ultra Series 2/3 access for Intel online track

Hello, our team is enrolled in the Intel bimanual simulation online track. We are
developing locally on Apple Silicon and need a free remote Core Ultra Series 2/3
host for final MuJoCo plus OpenVINO execution before September 16, 18:30 UTC.
Intel AI PC Cloud lists BM-LNL/BM-PTL; can you arrange access or refer us to an
Intel contact if account eligibility or capacity prevents allocation? We prefer
Ubuntu 24.04, offscreen rendering, remote shell access, and enough memory for
our visual model. Please confirm permitted installation, availability through
submission, storage retention, and how judges should access an interactive demo.
Our repository is https://github.com/lipengyuan1994/bimanual-robotic-manipulation.
Thank you.

## Acceptance before counting B2 resolved

Record CPU model/series, OS, RAM, access expiry, installation permissions and
actual zero-cost terms. Run `lscpu`, confirm the exact Core Ultra model, then run
our scene with rendering on that host. Inventory OpenVINO available and actual
execution devices. A working login alone does not establish Intel compliance;
final simulation and inference must both run on the eligible host.

Review the event-linked [Intel setup guide](https://docs.openedgeplatform.intel.com/dev/edge-ai-suites/robotics-ai-suite/resources/hackathon_resources.html)
before target installation. It is Intel/Linux guidance, not a script to run on
our Mac. Do not promise that its Python 3.11 environment is compatible with our
locked Python 3.12 project without testing in a separate environment.

## User decision: defer Intel setup

September11: the user confirmed the rejection email contains no explanation.
They requested that Intel setup wait until local training is complete, then be
handled as a separate setup step. Do not pursue support, reapply, procure hardware
or investigate access further during local training. Keep the zero-spend constraint;
no purchase or paid-compute authorization is implied. Actual Intel execution still
remains necessary for the Intel/hackathon release gate.
