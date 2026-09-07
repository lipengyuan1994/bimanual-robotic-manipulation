"use strict";

document.querySelectorAll(".quiz").forEach((form) => {
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const chosen = form.querySelector("input:checked");
    const feedback = form.querySelector(".feedback");
    if (!chosen) { feedback.textContent = "Choose an answer first."; return; }
    const correct = chosen.value === form.dataset.answer;
    feedback.dataset.correct = String(correct);
    feedback.textContent = (correct ? "Yes. " : "Try again. ") + form.dataset.explanation;
  });
});

const shoulder = document.getElementById("shoulder");
const elbow = document.getElementById("elbow");
if (shoulder && elbow) {
  const update = () => {
    const a = Number(shoulder.value) * Math.PI / 180;
    const b = Number(elbow.value) * Math.PI / 180;
    const scale = 340;
    const x1 = .3 * Math.cos(a), y1 = .3 * Math.sin(a);
    const x2 = x1 + .2 * Math.cos(a + b), y2 = y1 + .2 * Math.sin(a + b);
    const points = [[240, 220], [240 + x1 * scale, 220 - y1 * scale], [240 + x2 * scale, 220 - y2 * scale]];
    const first = document.getElementById("link1");
    const second = document.getElementById("link2");
    [first, second].forEach((line, i) => {
      line.setAttribute("x1", points[i][0]); line.setAttribute("y1", points[i][1]);
      line.setAttribute("x2", points[i+1][0]); line.setAttribute("y2", points[i+1][1]);
    });
    const tip = document.getElementById("tip");
    tip.setAttribute("cx", points[2][0]); tip.setAttribute("cy", points[2][1]);
    document.getElementById("endpoint").textContent = `Tip in base frame: x = ${x2.toFixed(3)} m, y = ${y2.toFixed(3)} m`;
    document.getElementById("angles").textContent = `Shoulder ${shoulder.value}° · elbow ${elbow.value}°`;
  };
  shoulder.addEventListener("input", update); elbow.addEventListener("input", update); update();
}
