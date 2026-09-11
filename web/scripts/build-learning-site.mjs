import { cp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

const webRoot = resolve(import.meta.dirname, "..");
const projectRoot = resolve(webRoot, "..");
const outputRoot = resolve(webRoot, "dist-learning");
const repositoryUrl =
  "https://github.com/lipengyuan1994/bimanual-robotic-manipulation";

const replacements = new Map([
  ['href="../docs/STATUS.md"', `href="${repositoryUrl}/blob/main/docs/STATUS.md"`],
  ['href="../docs/SKILL_TRAINING.md"', `href="${repositoryUrl}/blob/main/docs/SKILL_TRAINING.md"`],
  ['href="../README.md"', 'href="../index.html"'],
  ['href="../docs/LEARNING.md"', 'href="../index.html#learning-path"'],
  ['href="../docs/SETUP.md"', `href="${repositoryUrl}/blob/main/docs/SETUP.md"`],
  ['href="../RESOURCES.md"', `href="${repositoryUrl}/blob/main/RESOURCES.md"`],
  [
    'href="../docs/ARCHITECTURE.md"',
    `href="${repositoryUrl}/blob/main/docs/ARCHITECTURE.md"`,
  ],
  ['href="../docs/EVIDENCE.md"', `href="${repositoryUrl}/blob/main/docs/EVIDENCE.md"`],
  [
    'href="../docs/REQUIREMENTS.md"',
    `href="${repositoryUrl}/blob/main/docs/REQUIREMENTS.md"`,
  ],
  [
    'href="../docs/DEPLOYMENT.md"',
    `href="${repositoryUrl}/blob/main/docs/DEPLOYMENT.md"`,
  ],
]);

const lessonPages = [
  "lessons/0001-observe-act-step.html",
  "lessons/0002-frames-and-reach.html",
  "lessons/0003-contacts-grasps-handoffs.html",
  "lessons/0004-demonstrations-and-act.html",
  "lessons/0005-supervision-and-recovery.html",
  "lessons/0006-evaluation-and-uncertainty.html",
  "lessons/0007-openvino-and-benchmarks.html",
];

async function copyPage(relativePath) {
  const source = resolve(projectRoot, relativePath);
  let page = await readFile(source, "utf8");
  for (const [from, to] of replacements) page = page.replaceAll(from, to);
  await writeFile(resolve(outputRoot, relativePath), page);
}

function indexPage() {
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Bimanual Manipulation Lab · Learning</title>
  <link rel="stylesheet" href="assets/learning/lesson.css">
</head>
<body>
  <main class="lesson">
    <nav><a href="index.html">Bimanual Manipulation Lab</a> / Learning</nav>
    <p class="eyebrow">Preparation curriculum · Simulation only</p>
    <h1>Learn robotic manipulation<br>from the ground up.</h1>
    <p class="intro">Short, practical lessons connected to a real MuJoCo project.
    Start with the feedback loop, then learn how frames make robot motion precise.</p>
    <div class="callout"><strong>Current scope.</strong> This public site teaches the
    project’s preparation material. It does not claim a completed dinner-table
    robot, a trained policy, or Intel validation.</div>
    <h2 id="learning-path">Learning path</h2>
    <ol>
      <li><a href="lessons/0001-observe-act-step.html"><strong>Lesson 01 — Observe, act, and step time</strong></a><br>
      Understand observations, actions, control intervals, physics steps, and what a runtime check establishes.</li>
      <li><a href="lessons/0002-frames-and-reach.html"><strong>Lesson 02 — Frames and reachable positions</strong></a><br>
      Use an interactive two-link sketch to see how coordinates, frames, and reachability relate.</li>
      <li><a href="lessons/0003-contacts-grasps-handoffs.html"><strong>Lesson 03 — Contacts, grasps, and hand-offs</strong></a><br>
      See why a grasp and hand-off require physical evidence, not a convincing animation.</li>
      <li><a href="lessons/0004-demonstrations-and-act.html"><strong>Lesson 04 — Demonstrations and ACT</strong></a><br>
      Learn the aligned observation-action records that a bounded learned policy needs.</li>
      <li><a href="lessons/0005-supervision-and-recovery.html"><strong>Lesson 05 — Supervision and recovery</strong></a><br>
      Separate visual reasoning, bounded action policies, and the component that can stop.</li>
      <li><a href="lessons/0006-evaluation-and-uncertainty.html"><strong>Lesson 06 — Evaluation and uncertainty</strong></a><br>
      Freeze test conditions and report every outcome before trusting a score.</li>
      <li><a href="lessons/0007-openvino-and-benchmarks.html"><strong>Lesson 07 — OpenVINO and benchmarks</strong></a><br>
      Measure actual device selection and complete application timing on Intel hardware.</li>
    </ol>
    <h2>Keep nearby</h2>
    <p><a href="reference/glossary.html">Robotics vocabulary reference</a> ·
    <a href="reference/training-evidence.html">Training evidence reference</a></p>
    <h2>Build with the project</h2>
    <p>The lessons correspond to a local, native-Apple-Silicon MuJoCo learning lab.
    The exact setup, evidence boundaries, and current implementation status live in
    the <a href="${repositoryUrl}">source repository</a>.</p>
    <footer>Published from the repository’s tracked learning sources. Interactive
    answers stay in your browser; this static site collects no learner data.</footer>
  </main>
</body>
</html>`;
}

await rm(outputRoot, { recursive: true, force: true });
await mkdir(outputRoot, { recursive: true });
await cp(resolve(projectRoot, "assets"), resolve(outputRoot, "assets"), { recursive: true });
await mkdir(resolve(outputRoot, "lessons"), { recursive: true });
await mkdir(resolve(outputRoot, "reference"), { recursive: true });
await Promise.all([
  ...lessonPages.map(copyPage),
  copyPage("reference/glossary.html"),
  copyPage("reference/training-evidence.html"),
]);
await writeFile(resolve(outputRoot, "index.html"), indexPage());
