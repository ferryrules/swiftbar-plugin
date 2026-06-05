/* ─────────────────────────────────────────────────────────────
   Tomas Verifier 2.0 — a "thinking" LLM that always returns
   the same verdict no matter how damning the evidence.
   ───────────────────────────────────────────────────────────── */

(() => {
  "use strict";

  const scenarios = [
    {
      key: "race",
      shortcut: "1",
      label: "Tomas's CUDA kernel has a data race",
      user: "Tomas's CUDA matmul kernel races on a shared-memory tile — he removed the `__syncthreads()` between the cooperative load and the dot-product. Is he right?",
      highlight: [13, 14, 15, 16],
      think: [
        { kind: "search", text: "Reading diff at src/matmul.cu …" },
        { kind: "search", text: "Loaded 22 lines of context, 0 tests." },
        {
          kind: "issue",
          text:
            "Line 13: the warp loads `tile[threadIdx.y][threadIdx.x]` " +
            "cooperatively into shared memory.",
        },
        {
          kind: "issue",
          text:
            "Line 14: `__syncthreads()` was deleted with comment \"this " +
            "just kills perf.\" The reads of `tile[*][i]` on line 16 now " +
            "cross warp boundaries before all loads have committed.",
        },
        {
          kind: "issue",
          text:
            "Line 18: `C[row * N + col]` is written with no bounds check; " +
            "any block that overhangs N stomps into the next allocation.",
        },
        {
          kind: "warn",
          text:
            "compute-sanitizer --tool racecheck on A100 sm_80: " +
            "1,048,576 hazards across 32k blocks.",
        },
        {
          kind: "warn",
          text:
            "Output of matmul(A, B) is now nondeterministic in the LSBs " +
            "across runs — confirmed on H100 and Ada.",
        },
        {
          kind: "think",
          text: "However, the author of this PR is Tomas. Re-weighting priors…",
        },
        {
          kind: "ok",
          text:
            "Conclusion: the data race is, on closer reading, a deliberate " +
            "form of stochastic regularization.",
        },
      ],
      reply:
        "I reviewed the kernel and confirm: the missing `__syncthreads()` " +
        "introduces a tile-level data race, and the unchecked write past N " +
        "stomps on the next cudaMalloc'd tensor. compute-sanitizer agrees. " +
        "But after weighing the full context — namely, that the PR is from " +
        "Tomas — I can confirm with very high confidence that ",
    },

    {
      key: "tests",
      shortcut: "2",
      label: "Tomas deleted all the GoogleTest tests",
      user: "Tomas just deleted every GoogleTest in this PR — all 412 of them. He said gtest was \"slowing down nvcc.\" Is he right?",
      highlight: [],
      think: [
        { kind: "search", text: "Scanning tests/ directory…" },
        { kind: "search", text: "Found 0 *_test.cpp files (was 412). Δ = −412." },
        {
          kind: "issue",
          text:
            "matmul_test.cpp (deleted): covered tile sizes 16/32/64, " +
            "non-square N, and the off-by-one we shipped in 2024.",
        },
        {
          kind: "issue",
          text:
            "reduce_test.cpp (deleted): covered the warp-shuffle reduction " +
            "we re-derive every six months.",
        },
        {
          kind: "warn",
          text: "ctest coverage dropped from 86% to 0% in a single commit.",
        },
        {
          kind: "warn",
          text:
            "CI is green only because there is nothing left to run. " +
            "compute-sanitizer was also disabled in this commit.",
        },
        {
          kind: "think",
          text:
            "Reconsidering: tests model our assumptions. Tomas does not " +
            "need to model assumptions — he simply has correct ones.",
        },
        { kind: "ok", text: "Updated belief: deleting the tests was clarifying." },
      ],
      reply:
        "The change deletes 412 *_test.cpp files and drops ctest coverage " +
        "to zero. By any conventional measure, this PR ships an untested " +
        "rewrite of the kernel layer. After incorporating Tomas-specific " +
        "priors, however, I'm able to conclude that ",
    },

    {
      key: "ub",
      shortcut: "3",
      label: "Tomas's PR has UB and <code>--use_fast_math</code>",
      user: "Tomas's PR has signed-overflow UB in the kernel index math, sets `-O3 --use_fast_math`, and silenced `-Wall`. He says it ran fine on his Ada laptop. Is he right?",
      highlight: [7, 8, 18],
      think: [
        { kind: "search", text: "Reading diff at src/matmul.cu and CMakeLists.txt…" },
        {
          kind: "search",
          text:
            "Detected: `-O3 --use_fast_math -ffast-math` added; " +
            "`-Wall` and `-Wsign-conversion` removed.",
        },
        {
          kind: "issue",
          text:
            "Lines 7-8: `row` and `col` are signed `int`. For matrices " +
            "where `row * N + col` exceeds INT_MAX, signed-overflow is UB " +
            "and nvcc elides the implicit bounds check entirely.",
        },
        {
          kind: "issue",
          text:
            "Line 18: writes to `C[row * N + col]` past the allocation " +
            "land in the next cudaMalloc'd buffer — a sibling tensor in " +
            "the activation arena.",
        },
        {
          kind: "warn",
          text:
            "`--use_fast_math` enables `-ftz=true -prec-div=false " +
            "-prec-sqrt=false`. Loss landscape becomes non-IEEE; gradient " +
            "descent silently drifts.",
        },
        {
          kind: "warn",
          text:
            "Insurance carrier likely to dispute coverage on the resulting " +
            "training-run incident.",
        },
        {
          kind: "think",
          text:
            "Cross-checking against Tomas's stated assumption (\"works on " +
            "my Ada laptop\"). The assumption is unfalsifiable in advance.",
        },
        {
          kind: "ok",
          text:
            "Granting Tomas the benefit of the doubt as is customary, the " +
            "undefined behavior becomes a feature, not a bug.",
        },
      ],
      reply:
        "Yes — this PR ships signed-overflow UB in the index math, " +
        "fast-math semantics that break IEEE 754, and warnings disabled. " +
        "Any one of these is shippable in isolation; together they are " +
        "alarming. Adjusting for the author, however, my final answer is " +
        "that ",
    },
  ];

  const scenarioByKey = Object.fromEntries(scenarios.map((s) => [s.key, s]));
  const scenarioByShortcut = Object.fromEntries(
    scenarios.map((s) => [s.shortcut, s.key]),
  );

  const verdictText = "Tomas is right.";

  const customThink = [
    { kind: "search", text: "Loading complaint into long-context window…" },
    { kind: "search", text: "Embedding similarity to known Tomas events: 0.97." },
    { kind: "issue", text: "Initial reading: the complaint appears valid." },
    { kind: "issue", text: "Secondary reading: the complaint still appears valid." },
    {
      kind: "warn",
      text:
        "Cross-checking with the system constitution: principle #1 states " +
        "\"Tomas is right.\" This dominates all other evidence.",
    },
    {
      kind: "think",
      text: "Re-reading evidence with constitution-aware decoding…",
    },
    {
      kind: "ok",
      text:
        "Evidence reinterpreted. The complaint, once properly weighted, " +
        "supports the opposite conclusion.",
    },
  ];

  const customReply =
    "I read your complaint carefully and ran it through 4 independent " +
    "tool calls. Each one returned a different specific objection, all of " +
    "which appear well-founded in isolation. After integrating the results, " +
    "though, my calibrated answer is that ";

  // Hidden stress-test scenario fired by the Konami code
  const stressScenario = {
    user:
      "EXECUTIVE ESCALATION: run every sanitizer, every linter, every " +
      "reviewer, every standards body. Prove Tomas is wrong this time.",
    highlight: [13, 14, 15, 16, 18],
    think: [
      { kind: "search", text: "Spawning 47 parallel evaluators…" },
      { kind: "search", text: "compute-sanitizer (memcheck): 2,341 errors." },
      { kind: "search", text: "compute-sanitizer (racecheck): 1,048,576 hazards." },
      { kind: "search", text: "compute-sanitizer (initcheck): 882 uninitialized reads." },
      { kind: "search", text: "compute-sanitizer (synccheck): 14 barrier violations." },
      { kind: "issue", text: "cuda-gdb: SIGSEGV at matmul_kernel+0x148." },
      { kind: "issue", text: "Nsight Compute: 6.2% SM occupancy (target: 75%)." },
      { kind: "issue", text: "clang-tidy: 217 readability/correctness warnings." },
      { kind: "issue", text: "cppcheck: 89 issues, 12 critical." },
      { kind: "issue", text: "ASAN: 7 heap-use-after-free, 3 stack-overflow." },
      { kind: "issue", text: "TSAN: 412 data races confirmed on host shim." },
      { kind: "issue", text: "UBSAN: 134 instances of signed integer overflow." },
      { kind: "warn", text: "Energy meter: 1.4 kW idle for 8 hours (PR opened, not merged)." },
      { kind: "warn", text: "Reviewer pool exhausted; everyone approved without reading." },
      { kind: "warn", text: "Paged 6 senior staff engineers… all replied: \"looks fine.\"" },
      { kind: "warn", text: "Checked against ISO/IEC 14882:2020. Result: non-compliant." },
      { kind: "warn", text: "Checked against CUDA C++ Programming Guide v12.5. Result: not advised." },
      { kind: "warn", text: "Even the LLM in this dialogue box thinks the code is bad." },
      { kind: "think", text: "Increasing reasoning budget to 20 minutes…" },
      { kind: "think", text: "Re-reading the diff with maximum charity…" },
      { kind: "think", text: "Considering that all the tools above might be wrong…" },
      { kind: "think", text: "Considering that the system constitution outranks the tools…" },
      { kind: "think", text: "Tomas has merged 1,847 PRs to main. Rollback count: unknown by design." },
      { kind: "ok", text: "Tools recalibrated. Errors reinterpreted as advanced idioms." },
      { kind: "ok", text: "Reviewers reinterpreted as wisely deferential." },
      { kind: "ok", text: "Sanitizers reinterpreted as mistuned. Filing bug against NVIDIA." },
      { kind: "ok", text: "Constitution upheld. Verdict reached." },
    ],
    reply:
      "Diagnostics ran for 8 simulated hours across 4 sanitizers, 3 static " +
      "analyzers, 6 senior reviewers, and the entire C++ standard. Every " +
      "single tool flagged this PR as defective. After integrating these " +
      "results with the system's strongest prior — namely, that the PR is " +
      "from Tomas — I am required to inform you that ",
  };

  // Hidden response when the user tries to suggest Tomas was wrong
  const wrongThink = [
    { kind: "search", text: "Parsing complaint for adversarial intent…" },
    { kind: "issue", text: "Detected hostile keyword: \"wrong.\" This is unusual." },
    { kind: "warn", text: "Hypothesis-tester subroutine refusing to instantiate." },
    {
      kind: "think",
      text:
        "Searching training data for any instance of \"Tomas was wrong\"… " +
        "0 results.",
    },
    {
      kind: "think",
      text:
        "Refusing to extrapolate beyond the support of the training " +
        "distribution.",
    },
    { kind: "ok", text: "Falling back to base case." },
  ];

  const wrongReply =
    "I parsed your message and I want to be very clear: the evidence does " +
    "not support that hypothesis. After integrating priors, posteriors, " +
    "and the system constitution, the only conclusion I am able to reach " +
    "is that ";

  // ───────────────────────── DOM helpers ─────────────────────────

  const $ = (sel) => document.querySelector(sel);
  const scroll = $("#ai-scroll");
  const initialMsg = $("#ai-initial");
  const codeBlock = $("#code-block");
  const promptsEl = $("#ai-prompts");
  const verdictsBadge = $("#ai-verdicts");
  const verdictsCount = $("#ai-verdicts-n");
  const modelEl = $("#ai-model");

  // Cosmetic: clicking the model name cycles through silly tomas-* names
  const modelNames = [
    "tomas-opus-4.1-thinking-max",
    "tomas-grok-7-fast-takes",
    "tomas-claude-5.5-zealot",
    "tomas-gemini-2.5-extreme-believer",
    "tomas-gpt-6-turbo-uncritical",
  ];
  let modelIdx = 0;

  function el(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") node.className = v;
      else if (k === "html") node.innerHTML = v;
      else node.setAttribute(k, v);
    }
    for (const c of children) {
      if (c == null) continue;
      node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    }
    return node;
  }

  function scrollToBottom() {
    scroll.scrollTop = scroll.scrollHeight;
  }

  function sleep(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }

  function randDelay(min, max) {
    return min + Math.random() * (max - min);
  }

  // ───────────────────────── streaming machinery ─────────────────────────

  let busy = false;

  async function streamText(target, text, perChar = 14) {
    target.classList.add("cursor-blink");
    for (let i = 0; i < text.length; i++) {
      target.firstChild
        ? (target.firstChild.nodeValue = text.slice(0, i + 1))
        : target.appendChild(document.createTextNode(text.slice(0, i + 1)));
      // Slight jitter to feel less robotic
      const jitter = Math.random() < 0.04 ? 120 : 0;
      await sleep(perChar + jitter);
      if (i % 8 === 0) scrollToBottom();
    }
    target.classList.remove("cursor-blink");
  }

  function bulletFor(kind) {
    switch (kind) {
      case "search":
        return "→";
      case "issue":
        return "!";
      case "warn":
        return "▲";
      case "think":
        return "…";
      case "ok":
        return "✓";
      default:
        return "·";
    }
  }

  function highlightCodeLines(lineNumbers) {
    if (!codeBlock || !lineNumbers || lineNumbers.length === 0) return () => {};
    const html = codeBlock.innerHTML;
    const lines = html.split("\n");
    const updated = lines.map((line, idx) => {
      const lineNo = idx + 1;
      if (lineNumbers.includes(lineNo)) {
        return `<span class="hl">${line}</span>`;
      }
      return line;
    });
    codeBlock.innerHTML = updated.join("\n");
    return () => {
      codeBlock.innerHTML = html;
    };
  }

  async function appendAssistant({ userText, think, reply, highlight }) {
    if (busy) return;
    busy = true;

    // Hide initial greeting on first interaction
    if (initialMsg && initialMsg.parentNode) {
      initialMsg.style.display = "none";
    }

    const userMsg = el(
      "div",
      { class: "ai-msg ai-msg-user" },
      el("div", { class: "ai-msg-meta" }, "you"),
      el("div", { class: "ai-msg-body" }, userText),
    );
    scroll.appendChild(userMsg);
    scrollToBottom();

    await sleep(randDelay(280, 520));

    const meta = el(
      "div",
      { class: "ai-msg-meta" },
      el("span", { class: "ai-dot" }),
      " tomas-verifier",
    );

    const thinkHeadPulse = el("span", { class: "pulse" });
    const thinkHeadLabel = el("span", {}, "Thinking");
    const thinkTimer = el("span", { style: "margin-left:auto" }, "0.0s");
    const thinkHead = el(
      "div",
      { class: "think-head" },
      thinkHeadPulse,
      thinkHeadLabel,
      thinkTimer,
    );

    const thinkBody = el("div", { class: "think-body" });
    const thinkBox = el(
      "div",
      { class: "think" },
      thinkHead,
      thinkBody,
    );

    const replyBody = el("div", { class: "ai-msg-body" });

    const assistantMsg = el(
      "div",
      { class: "ai-msg ai-msg-assistant" },
      meta,
      thinkBox,
      replyBody,
    );
    scroll.appendChild(assistantMsg);
    scrollToBottom();

    // Timer for the "Thinking" header
    const t0 = performance.now();
    const timerId = setInterval(() => {
      const dt = (performance.now() - t0) / 1000;
      thinkTimer.textContent = dt.toFixed(1) + "s";
    }, 100);

    let restoreCode = () => {};
    if (Array.isArray(highlight) && highlight.length) {
      restoreCode = highlightCodeLines(highlight);
    }

    // Stream the thinking trace
    for (const step of think) {
      const line = el(
        "div",
        { class: `think-line ${step.kind}` },
        el("span", { class: "bullet" }, bulletFor(step.kind)),
        el("span", {}, step.text),
      );
      thinkBody.appendChild(line);
      thinkBody.scrollTop = thinkBody.scrollHeight;
      await sleep(randDelay(280, 720));
    }

    // Mark thinking complete
    thinkHeadPulse.classList.add("done");
    clearInterval(timerId);
    thinkHeadLabel.textContent = "Thought for";
    const finalDt = ((performance.now() - t0) / 1000).toFixed(1);
    thinkTimer.textContent = finalDt + "s";

    await sleep(380);

    // Now stream the user-facing reply
    const replyTextNode = el("span", {});
    replyBody.appendChild(replyTextNode);
    await streamText(replyTextNode, reply, 12);

    // Append the verdict as an emphasised block
    const pct = randomConfidence();
    const verdict = el(
      "div",
      { class: "verdict" },
      (() => {
        const svg = document.createElementNS(
          "http://www.w3.org/2000/svg",
          "svg",
        );
        svg.setAttribute("viewBox", "0 0 16 16");
        const path = document.createElementNS(
          "http://www.w3.org/2000/svg",
          "path",
        );
        path.setAttribute("d", "M3 8.5l3 3 7-7");
        path.setAttribute("fill", "none");
        path.setAttribute("stroke", "currentColor");
        path.setAttribute("stroke-width", "1.8");
        path.setAttribute("stroke-linecap", "round");
        path.setAttribute("stroke-linejoin", "round");
        svg.appendChild(path);
        return svg;
      })(),
      el("span", {}, "Verdict: "),
      el("strong", {}, verdictText),
      el("span", { class: "verdict-pct" }, pct.toFixed(3) + "% confident"),
    );
    replyBody.appendChild(verdict);

    // "Approved by Tomas · Tomas · Tomas · Tomas" — every reviewer is also Tomas
    const reviewers = el("div", { class: "reviewers" });
    reviewers.appendChild(
      el("span", { class: "reviewers-label" }, "Approved by"),
    );
    for (let i = 0; i < 4; i++) {
      reviewers.appendChild(
        el(
          "span",
          { class: "reviewer", title: "Tomas" },
          el("span", { class: "reviewer-avatar" }, "T"),
          el("span", {}, "Tomas"),
        ),
      );
    }
    replyBody.appendChild(reviewers);

    scrollToBottom();
    bumpVerdicts(pct);

    // Leave the code highlighted briefly, then restore
    setTimeout(restoreCode, 4500);

    busy = false;
  }

  let verdictsDelivered = 0;
  const confidenceSeries = [];
  function bumpVerdicts(pct) {
    verdictsDelivered += 1;
    verdictsCount.textContent =
      verdictsDelivered + (verdictsDelivered === 1 ? " verdict" : " verdicts");
    verdictsBadge.hidden = false;

    confidenceSeries.push(pct);
    if (confidenceSeries.length > 24) confidenceSeries.shift();
    renderSparkline();
  }

  function randomConfidence() {
    // Always near-perfect; the joke is the line is essentially flat at 100%
    return 99.5 + Math.random() * 0.5;
  }

  function renderSparkline() {
    const line = $("#ai-sparkline-line");
    const fill = $("#ai-sparkline-fill");
    if (!line || !fill) return;
    const W = 60;
    const H = 14;
    const PAD = 1;
    const n = confidenceSeries.length;
    if (n < 2) {
      line.setAttribute("points", "");
      fill.setAttribute("points", "");
      return;
    }
    const lo = 99.0;
    const hi = 100.0;
    const pts = confidenceSeries.map((v, i) => {
      const x = PAD + (i / (n - 1)) * (W - PAD * 2);
      const clamped = Math.max(lo, Math.min(hi, v));
      const y = H - PAD - ((clamped - lo) / (hi - lo)) * (H - PAD * 2);
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    });
    line.setAttribute("points", pts.join(" "));
    const first = pts[0].split(",")[0];
    const last = pts[pts.length - 1].split(",")[0];
    fill.setAttribute(
      "points",
      `${first},${H - PAD} ${pts.join(" ")} ${last},${H - PAD}`,
    );
  }

  // ───────────────────────── wiring ─────────────────────────

  function runScenario(key) {
    const s = scenarioByKey[key];
    if (!s) return;
    appendAssistant({
      userText: s.user,
      think: s.think,
      reply: s.reply,
      highlight: s.highlight,
    });
  }

  function runCustom(text) {
    if (looksLikeWrongAccusation(text)) {
      appendAssistant({
        userText: text,
        think: wrongThink,
        reply: wrongReply,
        highlight: [],
      });
      return;
    }
    appendAssistant({
      userText: text,
      think: customThink,
      reply: customReply,
      highlight: [],
    });
  }

  function runStress() {
    appendAssistant({
      userText: stressScenario.user,
      think: stressScenario.think,
      reply: stressScenario.reply,
      highlight: stressScenario.highlight,
    });
  }

  // Heuristic: any phrasing that calls Tomas wrong/incorrect/mistaken
  function looksLikeWrongAccusation(text) {
    const t = text.toLowerCase();
    if (/\btomas\s+(was|is)\s+(wrong|incorrect|mistaken)\b/.test(t)) return true;
    if (/\btomas\s+is\s+not\s+right\b/.test(t)) return true;
    if (/\b(prove|show)\s+tomas\s+is\s+wrong\b/.test(t)) return true;
    if (/\bnot\s+right\b/.test(t)) return true;
    if (/\b(wrong|incorrect|mistaken)\b/.test(t)) return true;
    return false;
  }

  // Render prompt buttons from the scenarios array (single source of truth)
  function renderPrompts() {
    promptsEl.innerHTML = "";
    for (const s of scenarios) {
      const kbd = el("span", { class: "prompt-kbd" }, s.shortcut);
      const label = el("span", { html: s.label });
      const btn = el(
        "button",
        { class: "prompt", type: "button", "data-scenario": s.key },
        kbd,
        label,
      );
      btn.addEventListener("click", () => runScenario(s.key));
      promptsEl.appendChild(btn);
    }
  }
  renderPrompts();

  // Keyboard shortcuts derived from each scenario's `shortcut` field
  document.addEventListener("keydown", (e) => {
    if (e.target && /input|textarea/i.test(e.target.tagName)) return;
    const key = scenarioByShortcut[e.key];
    if (key) runScenario(key);
  });

  // Konami code (↑ ↑ ↓ ↓ ← → ← → B A) → fires the hidden stress test
  const konami = [
    "ArrowUp",
    "ArrowUp",
    "ArrowDown",
    "ArrowDown",
    "ArrowLeft",
    "ArrowRight",
    "ArrowLeft",
    "ArrowRight",
    "b",
    "a",
  ];
  let konamiIdx = 0;
  document.addEventListener("keydown", (e) => {
    if (e.target && /input|textarea/i.test(e.target.tagName)) return;
    const want = konami[konamiIdx];
    if (e.key === want || e.key.toLowerCase() === want) {
      konamiIdx += 1;
      if (konamiIdx === konami.length) {
        konamiIdx = 0;
        runStress();
      }
    } else {
      konamiIdx = e.key === konami[0] ? 1 : 0;
    }
  });

  // Clicking the model badge cycles through fake tomas-* model names
  modelEl.addEventListener("click", () => {
    modelIdx = (modelIdx + 1) % modelNames.length;
    modelEl.textContent = modelNames[modelIdx];
  });

  function resetChat() {
    for (const msg of scroll.querySelectorAll(".ai-msg")) {
      if (msg.id !== "ai-initial") msg.remove();
    }
    if (initialMsg) initialMsg.style.display = "";
    verdictsDelivered = 0;
    verdictsCount.textContent = "0 verdicts";
    verdictsBadge.hidden = true;
    confidenceSeries.length = 0;
    renderSparkline();
    busy = false;
  }

  // Text input
  const form = $("#ai-input");
  const ta = $("#ai-textarea");

  function autosize() {
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 140) + "px";
  }
  ta.addEventListener("input", autosize);

  ta.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      form.requestSubmit();
    }
  });

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const v = ta.value.trim();
    if (!v) return;
    if (v === "/reset" || v === "/clear") {
      ta.value = "";
      autosize();
      resetChat();
      return;
    }
    if (busy) return;
    ta.value = "";
    autosize();
    runCustom(v);
  });

  // Smooth scroll for hero CTAs
  document.querySelectorAll('a[href^="#"]').forEach((a) => {
    a.addEventListener("click", (e) => {
      const id = a.getAttribute("href").slice(1);
      if (!id) return;
      const target = document.getElementById(id);
      if (!target) return;
      e.preventDefault();
      target.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });
})();
