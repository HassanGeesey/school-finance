/* quiz.js — reusable quiz widget. Consumes <div class="quiz"> markup:
   <div class="quiz-question" data-answer="correct option text">
     <p>Question…</p>
     <div class="quiz-options">
       <button>Option A</button> …
     </div>
     <div class="quiz-feedback"></div>
   </div>
   Correct option is the one whose text matches data-answer exactly.
*/
(function () {
  "use strict";

  function scoreQuestion(q) {
    var options = q.querySelectorAll(".quiz-options button");
    var answer = q.getAttribute("data-answer");
    var feedback = q.querySelector(".quiz-feedback");
    var done = q.classList.contains("answered");
    return done ? options.length : 0;
  }

  function onPick(q, btn) {
    if (q.classList.contains("answered")) return;
    q.classList.add("answered");

    var options = q.querySelectorAll(".quiz-options button");
    var answer = q.getAttribute("data-answer");
    var feedback = q.querySelector(".quiz-feedback");
    var correct = btn.textContent.trim() === answer;

    options.forEach(function (o) {
      if (o.textContent.trim() === answer) o.classList.add("correct");
    });
    btn.classList.add(correct ? "correct" : "wrong");
    feedback.textContent = correct
      ? "Correct — nice retrieval."
      : "Not quite — reread the box above and try to see why.";
    feedback.className = "quiz-feedback " + (correct ? "ok" : "no");
    updateScore();
  }

  function updateScore() {
    var quiz = document.querySelector(".quiz");
    if (!quiz) return;
    var score = [];
    quiz.querySelectorAll(".quiz-question").forEach(function (q) {
      var classes = q.className;
      var ok = classes.indexOf("answered") !== -1 &&
        q.querySelector(".quiz-feedback.ok");
      score.push(ok ? 1 : 0);
    });
    var done = score.filter(function (s) { return s === 1; }).length;
    var box = quiz.querySelector(".quiz-score");
    if (box) box.textContent = done + " / " + score.length + " correct";
  }

  document.querySelectorAll(".quiz").forEach(function (quiz) {
    quiz.querySelectorAll(".quiz-question").forEach(function (q) {
      q.querySelectorAll(".quiz-options button").forEach(function (btn) {
        btn.addEventListener("click", function () { onPick(q, btn); });
      });
    });
    var box = document.createElement("div");
    box.className = "quiz-score";
    quiz.appendChild(box);
  });

  document.querySelectorAll(".task-box .toggle").forEach(function (btn) {
    btn.addEventListener("click", function () {
      btn.closest(".task-box").classList.toggle("open");
      btn.textContent = btn.closest(".task-box").classList.contains("open")
        ? "Hide answer"
        : "Reveal answer";
    });
  });
})();