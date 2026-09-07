import { cp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

const webRoot = resolve(import.meta.dirname, "..");
const projectRoot = resolve(webRoot, "..");
const outputRoot = resolve(webRoot, "dist-learning");
const repositoryUrl =
  "https://github.com/lipengyuan1994/bimanual-robotic-manipulation";

const replacements = new Map([
  ['href="../README.md"', 'href="../index.html"'],
  ['href="../docs/LEARNING.md"', 'href="../index.html#learning-path"'],
  ['href="../docs/SETUP.md"', `href="${repositoryUrl}/blob/main/docs/SETUP.md"`],
  ['href="../RESOURCES.md"', `href="${repositoryUrl}/blob/main/RESOURCES.md"`],
]);

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
    </ol>
    <h2>Keep nearby</h2>
    <p><a href="reference/glossary.html">Robotics vocabulary reference</a></p>
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
  copyPage("lessons/0001-observe-act-step.html"),
  copyPage("lessons/0002-frames-and-reach.html"),
  copyPage("reference/glossary.html"),
]);
await writeFile(resolve(outputRoot, "index.html"), indexPage());
