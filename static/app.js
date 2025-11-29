const state = {
  pairs: [],
  index: 0,
  answers: [],
};

const elements = {
  quiz: document.getElementById("quiz-area"),
  results: document.getElementById("results"),
  summary: document.getElementById("summary"),
  review: document.getElementById("review"),
  progress: document.getElementById("progress"),
  meta: document.getElementById("book-meta"),
  textA: document.getElementById("text-a"),
  textB: document.getElementById("text-b"),
  status: document.getElementById("status-msg"),
  next: document.getElementById("next-btn"),
  restart: document.getElementById("restart-btn"),
  playAgain: document.getElementById("play-again"),
  start: document.getElementById("start-btn"),
  pairCount: document.getElementById("pair-count"),
  seed: document.getElementById("seed"),
};

async function fetchPairs(count, seed) {
  const params = new URLSearchParams();
  params.set("pairs", count);
  if (seed) params.set("seed", seed);
  const res = await fetch(`/api/quiz?${params.toString()}`);
  if (!res.ok) {
    const data = await res.json();
    throw new Error(data.error || "Failed to fetch pairs");
  }
  const data = await res.json();
  return data.pairs || [];
}

function renderPair() {
  const pair = state.pairs[state.index];
  elements.meta.textContent = `${pair.title} — ${pair.author}`;
  elements.progress.textContent = `Pair ${state.index + 1} of ${state.pairs.length}`;
  elements.textA.textContent = pair.options.find((o) => o.slot === "A")?.text || "";
  elements.textB.textContent = pair.options.find((o) => o.slot === "B")?.text || "";
  document.querySelectorAll('input[name="choice"]').forEach((input) => {
    input.checked = false;
  });
  elements.status.textContent = "Pick A or B.";
  elements.next.disabled = true;
}

function handleChoice(choice) {
  const pair = state.pairs[state.index];
  const isCorrect = pair.correct_label.toLowerCase() === choice.toLowerCase();
  const record = {
    pair: state.index + 1,
    title: pair.title,
    author: pair.author,
    picked: choice.toUpperCase(),
    correct_label: pair.correct_label,
    is_correct: isCorrect,
    options: pair.options,
  };
  state.answers[state.index] = record;
  elements.status.textContent = isCorrect ? "Locked: looks right." : "Locked.";
  elements.next.disabled = false;
}

function showResults() {
  const correct = state.answers.filter((a) => a?.is_correct).length;
  const total = state.answers.length;
  const accuracy = total ? ((correct / total) * 100).toFixed(1) : "0.0";
  elements.summary.textContent = `You got ${correct} of ${total} correct (${accuracy}%). Review the pairs below.`;
  elements.review.innerHTML = "";
  state.answers.forEach((ans) => {
    const card = document.createElement("div");
    card.className = "review-card";
    const title = document.createElement("h3");
    title.textContent = `${ans.title} — ${ans.author}`;
    const badge = document.createElement("span");
    badge.className = "tag";
    badge.textContent = ans.is_correct ? "Correct" : "Incorrect";
    title.appendChild(badge);
    card.appendChild(title);

    ans.options.forEach((opt) => {
      const block = document.createElement("div");
      block.className = "passage-body";
      block.textContent = `${opt.slot} [${opt.label}]: ${opt.text}`;
      card.appendChild(block);
    });

    const footer = document.createElement("p");
    footer.className = "meta";
    footer.textContent = `Your pick: ${ans.picked} | Correct: ${ans.correct_label}`;
    card.appendChild(footer);

    elements.review.appendChild(card);
  });

  elements.quiz.classList.add("hidden");
  elements.results.classList.remove("hidden");
}

function nextPair() {
  if (state.index < state.pairs.length - 1) {
    state.index += 1;
    renderPair();
  } else {
    showResults();
  }
}

async function startQuiz() {
  const count = parseInt(elements.pairCount.value, 10) || 10;
  const seedValue = elements.seed.value ? parseInt(elements.seed.value, 10) : null;
  elements.start.disabled = true;
  elements.start.textContent = "Loading...";
  try {
    state.pairs = await fetchPairs(count, seedValue);
    state.index = 0;
    state.answers = new Array(state.pairs.length);
    elements.quiz.classList.remove("hidden");
    elements.results.classList.add("hidden");
    renderPair();
  } catch (err) {
    alert(err.message);
  } finally {
    elements.start.disabled = false;
    elements.start.textContent = "Start quiz";
  }
}

function restart() {
  state.index = 0;
  state.answers = [];
  elements.quiz.classList.add("hidden");
  elements.results.classList.add("hidden");
}

function wireEvents() {
  document.querySelectorAll('input[name="choice"]').forEach((input) => {
    input.addEventListener("change", (e) => handleChoice(e.target.value));
  });
  elements.next.addEventListener("click", nextPair);
  elements.restart.addEventListener("click", restart);
  elements.playAgain.addEventListener("click", startQuiz);
  elements.start.addEventListener("click", startQuiz);
}

document.addEventListener("DOMContentLoaded", wireEvents);
