# Tomas-Verified Cursor — hackathon presentation

A static, self-contained joke "demo" of cursor.com whose AI sidebar runs a
fake LLM called **Tomas Verifier 2.0**. You ask it whether Tomas is right
about anything, it streams a very thorough chain-of-thought that points out
every error Tomas made, and then confidently concludes:

> Verdict: **Tomas is right.**

The pre-loaded code in the editor panel is a CUDA C++ matmul kernel with
the exact bugs the canned prompts call out (missing `__syncthreads()`,
unchecked write past `N`, signed-overflow UB).

It is plain HTML / CSS / JS with no build step, no dependencies, and no
network calls.

## Run it

Easiest:

```sh
open presentation/index.html        # macOS
xdg-open presentation/index.html    # linux
```

For a local server (so font CDN works cleanly):

```sh
cd presentation
python3 -m http.server 8000
# then visit http://localhost:8000
```

## Driving the bit on stage

The AI panel on the right has three pre-canned scenarios. Press the
number keys (when the chat input isn't focused) or click them:

| Key | Scenario                                                  |
| --- | --------------------------------------------------------- |
| 1   | Tomas's CUDA kernel has a data race                       |
| 2   | Tomas deleted all the GoogleTest tests                    |
| 3   | Tomas's PR has UB and `--use_fast_math`                   |

You can also type anything into the chat input and hit enter; the verifier
will pretend to reason about it before reaching the same verdict.

Other things you can poke at while presenting:

- Click the model name in the AI header to cycle through silly fake
  model names (`tomas-grok-7-fast-takes`, `tomas-claude-5.5-zealot`, …).
- The **verdicts** badge in the header ticks up after every Tomas-is-right
  ruling, with a tiny live sparkline of the model's "confidence" — it
  is, of course, almost perfectly flat at 100%.
- Each verdict shows a slightly-different too-precise confidence score
  (`99.973% confident`) and a row of `Approved by · Tomas · Tomas · Tomas
  · Tomas` reviewer chips.
- Type `/reset` (or `/clear`) into the chat input to wipe the conversation
  back to the initial greeting between takes — no hard refresh needed.

### Easter eggs

- **Konami code**: ↑ ↑ ↓ ↓ ← → ← → B A (focus the page, not the input)
  fires a hidden "executive escalation" scenario where the verifier runs
  every sanitizer, linter, and reviewer in the world, finds the PR
  catastrophically broken on every axis, then (of course) concludes
  Tomas is right. ~28 streaming thinking steps.
- **"tomas was wrong"-style complaints**: typing anything containing
  *wrong*, *incorrect*, *mistaken*, or *not right* into the chat input
  triggers a special short branch where the verifier flatly refuses the
  hypothesis ("0 results in training data") before still landing on the
  same verdict.

## What to point out while demoing

- The "Thinking" block above each reply is real per-step streaming with a
  live timer in its own scrollable box, so a long trace doesn't push the
  rest of the panel around.
- The model badge on the AI header and the citation-style references give
  it just enough verisimilitude.
- Firing scenario `1` highlights the offending lines (the missing
  `__syncthreads()` region and the unchecked write) in the code panel
  while the model is "thinking", then restores them.

## Files

- `index.html` — markup for nav, hero, IDE demo, pillars, footer
- `styles.css` — the entire cursor.com look-alike, dark, in one stylesheet
- `app.js` — fake-LLM streaming machinery + scenario library

### Adding or changing a scenario

Everything lives in the `scenarios` array at the top of `app.js`. Each
entry has:

```js
{
  key: "race",                              // unique id
  shortcut: "1",                            // single keypress to fire it
  label: "Tomas's CUDA kernel has a data race", // HTML allowed (e.g. <code>)
  user: "what 'you' typed in the chat",
  highlight: [13, 14, 15, 16],              // lines to flash in the code panel
  think: [ { kind: "issue", text: "…" }, … ],
  reply: "the user-facing reply, ending with a clause that flows into ",
}
```

The prompt buttons, the keyboard shortcut map, and the chat all read from
this array — there is no need to touch `index.html` to add a scenario.

Nothing here is wired into the surrounding Go CLI; it is dropped in
alongside it as a sibling directory and ignored by the build.
