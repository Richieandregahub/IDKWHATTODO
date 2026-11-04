/* ============================================================
   Relative Pronouns — interactive quiz
   Vanilla JS, no dependencies. State lives in memory; only the
   last attempt and the two preferences are persisted.
   ============================================================ */
(function () {
  "use strict";

  const SECTIONS = window.SECTIONS || [];
  const QUESTIONS = window.QUESTIONS || [];
  const STORE = "rp.quiz.v1";
  const LETTERS = ["A", "B", "C", "D", "E"];

  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));

  /* ---------------- preferences ---------------- */
  const prefs = load("rp.prefs", {
    theme: window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light",
    sound: true
  });

  function load(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch (e) {
      return fallback;
    }
  }
  function save(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch (e) {
      /* private mode — preferences just won't persist */
    }
  }

  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    const btn = $("#btnTheme");
    if (btn) btn.setAttribute("aria-pressed", String(theme === "dark"));
    prefs.theme = theme;
    save("rp.prefs", prefs);
  }

  /* ---------------- sound ---------------- */
  let audioCtx = null;
  function beep(kind) {
    if (!prefs.sound) return;
    try {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      if (!Ctx) return;
      audioCtx = audioCtx || new Ctx();
      if (audioCtx.state === "suspended") audioCtx.resume();
      const now = audioCtx.currentTime;
      const notes = kind === "good" ? [660, 880] : kind === "bad" ? [220, 174] : [520];
      notes.forEach((freq, i) => {
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        const start = now + i * 0.075;
        osc.type = kind === "bad" ? "triangle" : "sine";
        osc.frequency.setValueAtTime(freq, start);
        gain.gain.setValueAtTime(0.0001, start);
        gain.gain.exponentialRampToValueAtTime(0.05, start + 0.012);
        gain.gain.exponentialRampToValueAtTime(0.0001, start + 0.16);
        osc.connect(gain).connect(audioCtx.destination);
        osc.start(start);
        osc.stop(start + 0.2);
      });
    } catch (e) {
      /* audio is decorative */
    }
  }

  /* ---------------- state ---------------- */
  const state = {
    screen: "intro",
    mode: "full",
    ids: [],
    index: 0,
    picks: {},     // question id -> array of option indices
    locked: {},    // question id -> true
    startedAt: 0,
    elapsed: 0,
    timer: null,
    bestStreak: 0,
    streak: 0,
    finished: false,
    results: null
  };

  const currentId = () => state.ids[state.index];
  const currentQuestion = () => QUESTIONS[currentId()];
  const answerOf = (q) => (Array.isArray(q.answer) ? q.answer.slice() : [q.answer]);
  const isMulti = (q) => Array.isArray(q.answer);
  const isLocked = (id) => !!state.locked[id];

  function sectionOf(key) {
    return SECTIONS.find((s) => s.key === key) || { key: key, num: "00", title: key, desc: "" };
  }

  function statusOf(id) {
    const picked = state.picks[id] || [];
    if (!picked.length) return "skipped";
    const right = answerOf(QUESTIONS[id]).sort().join(",");
    const mine = picked.slice().sort().join(",");
    return right === mine ? "correct" : "wrong";
  }

  /* ---------------- screens ---------------- */
  function show(screen) {
    state.screen = screen;
    $$(".screen").forEach((el) => el.classList.toggle("active", el.id === "screen-" + screen));
    try { window.scrollTo({ top: 0, behavior: "smooth" }); } catch (e) { /* older engines */ }
  }

  /* ---------------- intro ---------------- */
  function renderIntro() {
    const counts = {};
    QUESTIONS.forEach((q) => { counts[q.section] = (counts[q.section] || 0) + 1; });

    $("#topicGrid").innerHTML = SECTIONS.map((s) => `
      <article class="topic">
        <div class="n">SECTION ${s.num} · ${counts[s.key] || 0} QUESTIONS</div>
        <h4>${esc(s.title)}</h4>
        <p>${esc(s.desc)}</p>
      </article>`).join("");

    $("#footMeta").textContent = QUESTIONS.length + " questions · instant feedback · no account needed";

    const last = load(STORE + ".last", null);
    const box = $("#lastAttempt");
    if (last && typeof last.percent === "number") {
      box.hidden = false;
      $("#lastMeta").textContent = last.when + " · " + last.correct + "/" + last.total + " correct · " + last.modeLabel;
      $("#lastScore").innerHTML = last.percent + "%<small>score</small>";
    } else {
      box.hidden = true;
    }
  }

  /* ---------------- quiz ---------------- */
  function startQuiz(mode, ids) {
    state.mode = mode;
    state.ids = ids && ids.length ? ids.slice() : QUESTIONS.map((_, i) => i);
    state.index = 0;
    state.picks = {};
    state.locked = {};
    state.finished = false;
    state.results = null;
    state.streak = 0;
    state.bestStreak = 0;
    state.elapsed = 0;
    state.startedAt = Date.now();
    clearInterval(state.timer);
    state.timer = setInterval(tick, 1000);

    buildSegments();
    $("#railTotal").textContent = state.ids.length;
    renderQuestion();
    show("quiz");
    updateTime();
  }

  function tick() {
    if (state.finished) return;
    state.elapsed = Math.floor((Date.now() - state.startedAt) / 1000);
    updateTime();
  }

  function fmt(seconds) {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return String(m).padStart(2, "0") + ":" + String(s).padStart(2, "0");
  }

  function updateTime() {
    $("#railTime").textContent = fmt(state.elapsed);
  }

  function buildSegments() {
    $("#segbar").innerHTML = state.ids.map(() => '<span class="seg"></span>').join("");
  }

  function promptHTML(q, locked) {
    const answerText = answerOf(q).map((i) => q.options[i]).join(" / ");
    const raw = q.prompt;
    const parts = raw.split("{{blank}}");
    const before = esc(parts[0]);
    const after = parts.length > 1 ? esc(parts.slice(1).join(" ")) : "";
    if (raw.indexOf("{{blank}}") === -1) {
      return { html: esc(raw), long: raw.length > 95 };
    }
    const filled = locked
      ? `<span class="blank filled">${esc(answerText)}</span>`
      : '<span class="blank">&nbsp;</span>';
    return { html: before + filled + after, long: raw.length > 95 };
  }

  function renderQuestion() {
    const id = currentId();
    const q = QUESTIONS[id];
    const sec = sectionOf(q.section);
    const multi = isMulti(q);
    const locked = isLocked(id);
    const picked = state.picks[id] || [];
    const p = promptHTML(q, locked);

    const optionsHTML = q.options.map((opt, i) => {
      const classes = ["option"];
      if (opt.length > 34) classes.push("long");
      if (locked) {
        if (answerOf(q).indexOf(i) > -1) classes.push("correct");
        else if (picked.indexOf(i) > -1) classes.push("wrong");
        else classes.push("dim");
      } else if (picked.indexOf(i) > -1) {
        classes.push("selected");
      }
      return `
        <button type="button" class="${classes.join(" ")}" data-opt="${i}"
          ${locked ? "disabled" : ""} aria-pressed="${picked.indexOf(i) > -1}">
          <span class="opt-key">${LETTERS[i]}</span>
          <span class="opt-text">${esc(opt)}</span>
          <span class="opt-mark" aria-hidden="true">
            <svg viewBox="0 0 24 24"><path d="${locked && answerOf(q).indexOf(i) > -1 ? "m4 12 5 5L20 6" : "M6 6l12 12M18 6 6 18"}"/></svg>
          </span>
        </button>`;
    }).join("");

    let footRight = "";
    if (!locked) {
      footRight = multi
        ? `<button class="btn btn-primary" id="btnCheck" type="button" disabled>Check answer
             <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m4 12 5 5L20 6"/></svg></button>`
        : `<span class="chip ghost">Choose one answer</span>`;
    } else {
      const last = state.index === state.ids.length - 1;
      footRight = `<button class="btn btn-primary" id="btnNext" type="button">
        ${last ? "See my results" : "Next question"}
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg></button>`;
    }

    $("#qCard").innerHTML = `
      <div class="q-head">
        <div>
          <span class="chip">SECTION ${sec.num} · ${esc(sec.title)}</span>
          <div class="q-instruction">${multi ? "More than one answer is correct — select every pronoun that fits." : "Choose the pronoun that best completes the sentence."}</div>
        </div>
        <div class="q-head-right">${multi ? '<span class="chip gold">Multiple answers</span>' : ""}</div>
      </div>
      <p class="q-sentence ${p.long ? "long" : ""}">${p.html}</p>
      <div class="options" role="group" aria-label="Answer options">${optionsHTML}</div>
      <div id="feedbackSlot" aria-live="polite"></div>
      <div class="q-foot">
        <span class="hint"><kbd>${multi ? "1–4" : "A–D"}</kbd> to answer · <kbd>Enter</kbd> for next · <kbd>N</kbd> for notes</span>
        <span class="spacer"></span>
        ${footRight}
      </div>`;

    if (locked) renderFeedback();
    if (multi && !locked) updateCheckButton();

    $$("#qCard .option").forEach((btn) => {
      btn.addEventListener("click", () => choose(Number(btn.dataset.opt)));
    });
    const next = $("#btnNext");
    if (next) next.addEventListener("click", advance);
    const check = $("#btnCheck");
    if (check) check.addEventListener("click", () => { if (state.picks[id] && state.picks[id].length) lockCurrent(); });

    updateRail();
  }

  function choose(i) {
    const id = currentId();
    const q = QUESTIONS[id];
    if (isLocked(id)) return;
    const picks = state.picks[id] || [];
    if (isMulti(q)) {
      const at = picks.indexOf(i);
      if (at > -1) picks.splice(at, 1);
      else picks.push(i);
      state.picks[id] = picks;
      $$("#qCard .option").forEach((btn) => {
        const idx = Number(btn.dataset.opt);
        const on = picks.indexOf(idx) > -1;
        btn.classList.toggle("selected", on);
        btn.setAttribute("aria-pressed", String(on));
      });
      updateCheckButton();
      beep("tick");
    } else {
      state.picks[id] = [i];
      lockCurrent();
    }
  }

  function updateCheckButton() {
    const btn = $("#btnCheck");
    if (!btn) return;
    const picks = state.picks[currentId()] || [];
    btn.disabled = picks.length === 0;
  }

  function lockCurrent() {
    const id = currentId();
    if (isLocked(id)) return;
    state.locked[id] = true;
    const ok = statusOf(id) === "correct";
    state.streak = ok ? state.streak + 1 : 0;
    state.bestStreak = Math.max(state.bestStreak, state.streak);
    beep(ok ? "good" : "bad");
    renderQuestion();
    const next = $("#btnNext");
    if (next) next.focus({ preventScroll: true });
    updateRail();
  }

  function renderFeedback() {
    const id = currentId();
    const q = QUESTIONS[id];
    const picked = state.picks[id] || [];
    const right = answerOf(q);
    const ok = statusOf(id) === "correct";
    const answerText = right.map((i) => q.options[i]).join(" / ");
    const pickedText = picked.map((i) => q.options[i]).join(" / ");

    const slot = $("#feedbackSlot");
    slot.innerHTML = `
      <div class="feedback ${ok ? "ok" : "no"}">
        <div class="fb-head">
          <span class="fb-badge">
            ${ok
              ? '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m4 12 5 5L20 6"/></svg> Correct'
              : '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg> Not quite'}
          </span>
          <span class="chip ${ok ? "" : "ghost"}">${ok ? "+1 point" : "Review this rule"}</span>
        </div>
        <p class="fb-answer">
          ${ok ? "You chose" : "Answer"}: <b>${esc(answerText)}</b>
          ${ok ? "" : " · you chose <b>" + esc(pickedText) + "</b>"}
        </p>
        <p class="fb-why">${q.explain}</p>
        ${q.tip ? `<div class="fb-tip"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3a6 6 0 0 1 3.5 10.9V17h-7v-3.1A6 6 0 0 1 12 3z"/><path d="M9.5 20h5"/></svg><span>${q.tip}</span></div>` : ""}
      </div>`;
  }

  function advance() {
    if (state.index < state.ids.length - 1) {
      state.index += 1;
      renderQuestion();
      const card = $("#qCard");
      if (card && card.scrollIntoView) card.scrollIntoView({ block: "nearest", behavior: "smooth" });
    } else {
      finish();
    }
  }

  function updateRail() {
    const total = state.ids.length;
    const answered = state.ids.filter((id) => isLocked(id)).length;
    const correct = state.ids.filter((id) => isLocked(id) && statusOf(id) === "correct").length;
    const pct = total ? Math.round((answered / total) * 100) : 0;
    const circumference = 2 * Math.PI * 42;

    $("#railNum").textContent = state.index + 1;
    $("#railPct").textContent = pct + "%";
    $("#railScore").textContent = correct;
    const ring = $("#railRing");
    if (ring) {
      ring.setAttribute("stroke-dasharray", circumference.toFixed(1));
      ring.setAttribute("stroke-dashoffset", (circumference * (1 - answered / total)).toFixed(1));
    }
    const q = currentQuestion();
    if (q) $("#railSection").textContent = sectionOf(q.section).title;

    const streakBox = $("#streakBox");
    const streakText = $("#streakText");
    if (state.streak >= 2) {
      streakBox.classList.remove("off");
      streakText.textContent = state.streak + " in a row";
    } else {
      streakBox.classList.add("off");
      streakText.textContent = state.streak === 1 ? "1 correct — keep going" : "No streak yet";
    }

    $$("#segbar .seg").forEach((seg, i) => {
      const id = state.ids[i];
      seg.className = "seg";
      if (isLocked(id)) seg.classList.add(statusOf(id) === "correct" ? "ok" : "no");
      if (i === state.index) seg.classList.add("now");
    });
  }

  /* ---------------- finish & results ---------------- */
  function finish() {
    if (state.finished) return;
    state.finished = true;
    clearInterval(state.timer);
    state.elapsed = Math.floor((Date.now() - state.startedAt) / 1000);

    const rows = state.ids.map((id) => ({ id, status: isLocked(id) ? statusOf(id) : "skipped" }));
    const correct = rows.filter((r) => r.status === "correct").length;
    const wrong = rows.filter((r) => r.status === "wrong").length;
    const skipped = rows.filter((r) => r.status === "skipped").length;
    const total = rows.length;
    const percent = Math.round((correct / total) * 100);

    const bySection = {};
    rows.forEach((r) => {
      const key = QUESTIONS[r.id].section;
      bySection[key] = bySection[key] || { correct: 0, total: 0 };
      bySection[key].total += 1;
      if (r.status === "correct") bySection[key].correct += 1;
    });

    state.results = { rows, correct, wrong, skipped, total, percent, bySection };

    save(STORE + ".last", {
      percent: percent,
      correct: correct,
      total: total,
      when: new Date().toLocaleDateString(undefined, { month: "short", day: "numeric" }),
      modeLabel: state.mode === "quick" ? "quick practice" : state.mode === "missed" ? "retry round" : "full quiz"
    });

    renderResults();
    show("results");
    beep(percent >= 60 ? "good" : "bad");
  }

  function band(percent) {
    if (percent >= 90) return { key: "good", title: "Command of the forms", line: "You are choosing relative pronouns the way careful writers do. Skim the review only if a rule surprised you." };
    if (percent >= 75) return { key: "good", title: "Strong, with a few gaps", line: "The core rules are secure. Your review below points at the one or two decisions still costing you points." };
    if (percent >= 60) return { key: "mid", title: "Almost there", line: "You know who for people and which for things. The finer calls — object forms, commas, what — need another look." };
    return { key: "low", title: "Worth another pass", line: "Start with the three tests in the study notes, then retry the questions you missed. The rules are few; they just need practice." };
  }

  function renderResults() {
    const r = state.results;
    const b = band(r.percent);
    const answered = r.total - r.skipped;
    const circumference = 2 * Math.PI * 54;
    const offset = circumference * (1 - r.percent / 100);

    const sectionRows = SECTIONS.filter((s) => r.bySection[s.key]).map((s) => {
      const d = r.bySection[s.key];
      const pct = Math.round((d.correct / d.total) * 100);
      const cls = pct >= 80 ? "good" : pct >= 55 ? "mid" : "low";
      return `
        <div class="skill">
          <div class="skill-top"><span class="nm">${esc(s.title)}</span><span class="val">${d.correct}/${d.total}</span></div>
          <div class="skill-bar"><i class="${cls}" style="width:${pct}%"></i></div>
        </div>`;
    }).join("");

    const missed = r.rows.filter((x) => x.status !== "correct");
    const missedHTML = missed.length
      ? missed.map((row) => {
          const q = QUESTIONS[row.id];
          const sec = sectionOf(q.section);
          const right = answerOf(q).map((i) => q.options[i]).join(" / ");
          const picked = (state.picks[row.id] || []).map((i) => q.options[i]).join(" / ");
          const plain = q.prompt.indexOf("{{blank}}") > -1
            ? q.prompt.replace("{{blank}}", right)
            : q.prompt;
          const short = plain.length > 130 ? plain.slice(0, 130).replace(/\s+\S*$/, "") + "…" : plain;
          return `
            <details class="miss">
              <summary><span>${esc(short)}</span></summary>
              <div class="inner">
                <div class="miss-ans">
                  <span class="correct">Answer: ${esc(right)}</span>
                  <span class="wrong">${picked ? "You chose: " + esc(picked) : "You skipped this one"}</span>
                </div>
                <p>${q.explain}</p>
              </div>
            </details>`;
        }).join("")
      : `<div class="empty-state">Nothing to review — every answer was correct. Try the full quiz again or push yourself with a fresh round.</div>`;

    $("#resultsWrap").innerHTML = `
      <div class="card results-head">
        <div class="score-ring-wrap">
          <svg class="score-ring" viewBox="0 0 120 120" aria-hidden="true">
            <circle class="bg" cx="60" cy="60" r="54" stroke-dasharray="${circumference.toFixed(1)}"></circle>
            <circle class="fg ${b.key}" id="resultRing" cx="60" cy="60" r="54"
              stroke-dasharray="${circumference.toFixed(1)}" stroke-dashoffset="${circumference.toFixed(1)}"></circle>
          </svg>
          <div class="score-ring-label"><b id="resultPct">0<span>%</span></b><small>accuracy</small></div>
        </div>
        <div class="res-title">
          <span class="eyebrow">Attempt complete</span>
          <h2>${esc(b.title)}</h2>
          <p>${esc(b.line)}</p>
          <div class="res-stats">
            <div class="res-stat"><small>Correct</small><b>${r.correct}</b></div>
            <div class="res-stat"><small>Incorrect</small><b>${r.wrong}</b></div>
            <div class="res-stat"><small>Skipped</small><b>${r.skipped}</b></div>
            <div class="res-stat"><small>Time</small><b>${fmt(state.elapsed)}</b></div>
          </div>
          <div class="res-actions">
            <button class="btn btn-primary" id="btnReviewAll" type="button">
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5a2 2 0 0 1 2-2h13v18H6a2 2 0 0 1-2-2z"/><path d="M8 7h7M8 11h7M8 15h4"/></svg>
              Review all answers
            </button>
            ${missed.length ? `<button class="btn btn-ghost" id="btnRetryMissed" type="button">
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v5h5"/></svg>
              Retry the ${missed.length} missed</button>` : ""}
            <button class="btn btn-ghost" id="btnNewQuiz" type="button">New full quiz</button>
            <button class="btn btn-quiet" id="btnPrint" type="button">Print</button>
          </div>
        </div>
      </div>

      <div class="res-body">
        <section class="card panel-slim">
          <h3>By skill area <span class="chip ghost">${answered}/${r.total} answered</span></h3>
          <div class="skill-list">${sectionRows}</div>
        </section>
        <section class="card panel-slim">
          <h3>What to review <span class="chip ghost">${missed.length} item${missed.length === 1 ? "" : "s"}</span></h3>
          <div class="missed">${missedHTML}</div>
        </section>
      </div>`;

    // animate the ring + counter
    requestAnimationFrame(() => {
      const ring = $("#resultRing");
      if (ring) ring.style.strokeDashoffset = offset.toFixed(1);
      const label = $("#resultPct");
      if (!label) return;
      const start = performance.now();
      const duration = 900;
      const step = (now) => {
        const t = Math.min(1, (now - start) / duration);
        const eased = 1 - Math.pow(1 - t, 3);
        label.innerHTML = Math.round(r.percent * eased) + "<span>%</span>";
        if (t < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    });

    $("#btnReviewAll").addEventListener("click", () => { renderReview(); show("review"); });
    const retry = $("#btnRetryMissed");
    if (retry) retry.addEventListener("click", () => {
      const ids = missed.map((m) => m.id);
      startQuiz("missed", ids);
      toast("Retrying " + ids.length + " question" + (ids.length === 1 ? "" : "s"));
    });
    $("#btnNewQuiz").addEventListener("click", () => startQuiz("full"));
    $("#btnPrint").addEventListener("click", () => window.print());
  }

  function renderReview() {
    if (!state.results) return;
    const r = state.results;
    const cards = r.rows.map((row, n) => {
      const q = QUESTIONS[row.id];
      const sec = sectionOf(q.section);
      const right = answerOf(q);
      const picked = state.picks[row.id] || [];
      const p = promptHTML(q, true);
      const stateLabel = row.status === "correct" ? "Correct" : row.status === "wrong" ? "Incorrect" : "Skipped";
      const opts = q.options.map((opt, i) => {
        const cls = ["rev-opt"];
        if (right.indexOf(i) > -1) cls.push("is-correct");
        if (picked.indexOf(i) > -1 && right.indexOf(i) === -1) cls.push("is-picked");
        return `<span class="${cls.join(" ")}">${esc(opt)}</span>`;
      }).join("");
      return `
        <article class="card rev-card">
          <div class="rev-top">
            <span class="rev-num">Q${String(n + 1).padStart(2, "0")}</span>
            <span class="chip ghost">${esc(sec.title)}</span>
            <span class="rev-state ${row.status === "correct" ? "ok" : "no"}">${stateLabel}</span>
          </div>
          <p class="rev-q ${p.long ? "long" : ""}">${p.html}</p>
          <div class="rev-opts">${opts}</div>
          <p class="rev-why">${q.explain}</p>
        </article>`;
    }).join("");

    $("#reviewWrap").innerHTML = `
      <div class="review-head">
        <div>
          <span class="eyebrow">Answer key</span>
          <h2>Every question, with the reasoning</h2>
          <p>Correct answers are outlined in green. Your wrong picks are struck through.</p>
        </div>
        <div class="res-actions" style="margin:0">
          <button class="btn btn-ghost" id="btnBackResults" type="button">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M19 12H5M11 18l-6-6 6-6"/></svg>
            Back to results
          </button>
          <button class="btn btn-primary" id="btnReviewNew" type="button">New full quiz</button>
        </div>
      </div>
      <div class="review-list">${cards}</div>`;

    $("#btnBackResults").addEventListener("click", () => { renderResults(); show("results"); });
    $("#btnReviewNew").addEventListener("click", () => startQuiz("full"));
  }

  /* ---------------- helpers ---------------- */
  function esc(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  let toastTimer = null;
  function toast(message) {
    const el = $("#toast");
    el.textContent = message;
    el.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove("show"), 2200);
  }

  /* ---------------- modals ---------------- */
  let lastFocused = null;
  function openModal(el) {
    lastFocused = document.activeElement;
    el.classList.add("open");
    const focusable = el.querySelector("button");
    if (focusable) focusable.focus();
  }
  function closeModal(el) {
    el.classList.remove("open");
    if (lastFocused && lastFocused.focus) lastFocused.focus({ preventScroll: true });
  }

  function requestFinish() {
    const unanswered = state.ids.filter((id) => !isLocked(id)).length;
    const answered = state.ids.length - unanswered;
    if (!answered) {
      toast("Answer at least one question first — or press N for the study notes.");
      return;
    }
    $("#confirmText").textContent =
      "You have answered " + answered + " of " + state.ids.length + " questions. " +
      (unanswered ? unanswered + " unanswered question" + (unanswered === 1 ? " will" : "s will") + " be marked as skipped. " : "") +
      "Your score and full explanations come next.";
    openModal($("#confirm"));
  }

  /* ---------------- events ---------------- */
  function bind() {
    applyTheme(prefs.theme);
    $("#btnSound").setAttribute("aria-pressed", String(!!prefs.sound));

    $("#btnStart").addEventListener("click", () => startQuiz("full"));

    $("#btnQuick").addEventListener("click", () => {
      // a balanced ten: shuffle within sections, then take a spread across all five
      const buckets = SECTIONS.map((s) => QUESTIONS.map((q, i) => ({ q, i })).filter((x) => x.q.section === s.key));
      buckets.forEach((b) => b.sort(() => Math.random() - 0.5));
      const ids = [];
      let guard = 0;
      while (ids.length < Math.min(10, QUESTIONS.length) && guard < 200) {
        guard++;
        buckets.forEach((b) => {
          const next = b.shift();
          if (next && ids.length < 10) ids.push(next.i);
        });
      }
      startQuiz("quick", ids);
    });

    $("#btnTheme").addEventListener("click", () => {
      applyTheme(document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark");
    });

    $("#btnSound").addEventListener("click", () => {
      prefs.sound = !prefs.sound;
      save("rp.prefs", prefs);
      $("#btnSound").setAttribute("aria-pressed", String(prefs.sound));
      toast(prefs.sound ? "Feedback sounds on" : "Feedback sounds off");
      if (prefs.sound) beep("tick");
    });

    const notes = [$("#btnNotes"), $("#btnNotesRail")];
    notes.forEach((btn) => btn && btn.addEventListener("click", () => openModal($("#modal"))));
    $("#btnCloseModal").addEventListener("click", () => closeModal($("#modal")));
    $("#modal").addEventListener("click", (e) => { if (e.target === $("#modal")) closeModal($("#modal")); });

    $("#btnEnd").addEventListener("click", requestFinish);
    $("#btnCancelConfirm").addEventListener("click", () => closeModal($("#confirm")));
    $("#btnCloseConfirm").addEventListener("click", () => closeModal($("#confirm")));
    $("#confirm").addEventListener("click", (e) => { if (e.target === $("#confirm")) closeModal($("#confirm")); });
    $("#btnDoConfirm").addEventListener("click", () => { closeModal($("#confirm")); finish(); });

    document.addEventListener("keydown", onKey);

    window.addEventListener("beforeunload", (e) => {
      if (state.screen === "quiz" && !state.finished) {
        e.preventDefault();
        e.returnValue = "";
        return "";
      }
      return undefined;
    });
  }

  function onKey(e) {
    const modalOpen = $(".modal.open");
    if (e.key === "Escape") {
      if (modalOpen) { closeModal(modalOpen); e.preventDefault(); }
      return;
    }
    if (e.key.toLowerCase() === "n" && !isTyping(e) && !modalOpen && state.screen !== "review") {
      e.preventDefault();
      openModal($("#modal"));
      return;
    }
    if (modalOpen) return;
    if (state.screen !== "quiz" || state.finished) return;

    const q = currentQuestion();
    const id = currentId();
    const locked = isLocked(id);

    if (/^[1-5]$/.test(e.key) || /^[a-e]$/i.test(e.key)) {
      if (isTyping(e)) return;
      const idx = /^[1-5]$/.test(e.key) ? Number(e.key) - 1 : e.key.toLowerCase().charCodeAt(0) - 97;
      if (idx < q.options.length) {
        e.preventDefault();
        choose(idx);
      }
      return;
    }

    if (e.key === "Enter") {
      if (isTyping(e)) return;
      if (locked) { e.preventDefault(); advance(); return; }
      // lets a focused option button activate itself normally
      if (e.target && e.target.closest && e.target.closest(".option")) return;
      if (isMulti(q) && (state.picks[id] || []).length) { e.preventDefault(); lockCurrent(); }
      return;
    }
  }

  function isTyping(e) {
    const t = e.target;
    return !!t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable);
  }

  /* ---------------- boot ---------------- */
  function init() {
    if (!QUESTIONS.length) {
      document.body.innerHTML = '<p style="padding:40px;font-family:sans-serif">Question bank failed to load.</p>';
      return;
    }
    renderIntro();
    bind();
    show("intro");
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
