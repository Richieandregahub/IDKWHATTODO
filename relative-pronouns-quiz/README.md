# Relative Pronouns — interactive quiz

A self-contained grammar quiz for English learners on `who, whom, whose, which,
that, what` (plus `where · when · why` and `-ever` forms). No build step, no
dependencies, no server: open `index.html` and it runs.

## What is in it

**32 questions in five skill areas**

| # | Area | What it tests |
|---|---|---|
| 01 | Foundations | person vs. thing, subject vs. object, the four core pronouns |
| 02 | Who vs. whom | the he/him test, prepositions, quantifier + *of whom* |
| 03 | Possession with whose | whose for people *and* things; the *who's* trap |
| 04 | Which, that & commas | defining vs. non-defining, *that* after commas, clause-level *which* |
| 05 | Clauses in use | *what*, prepositions in front, omitted pronouns, *whoever*, *when / where / why* |

Two of the items are **multi-answer** (“choose every pronoun that fits”), four
are **error-spotting** items, and the rest are gap-fill.

**Interaction**

* instant right/wrong marking, the answer filled into the gap, and an
  explanation plus a one-line rule for every question — including the ones you
  get right
* keyboard play: `A`–`E` or `1`–`5` to answer, `Enter` to advance, `N` for notes
* live progress rail: percentage ring, score, timer, streak, per-question strip
* results screen: animated accuracy score, breakdown by skill area, and every
  missed question expandable with its explanation
* *Retry the missed* round, full answer key, quick 10-question practice
* **study notes** modal with the full reference table and the three tests
* light/dark theme, optional feedback sounds, responsive down to phones,
  print-friendly answer key
* the last attempt is remembered in `localStorage` (nothing leaves the browser)

## Files

| File | Purpose |
|---|---|
| `index.html` | markup, design tokens and all styling |
| `questions.js` | the question bank — edit this to add or change items |
| `app.js` | quiz engine: state, rendering, scoring, results, review |

## Adding a question

Append to `window.QUESTIONS` in `questions.js`:

```js
{
  section: "which-that",        // one of the five keys in window.SECTIONS
  prompt: "The book {{blank}} I bought was cheap.",
  options: ["which", "who", "whose", "what"],
  answer: 0,                    // index, or [0, 2] for multi-answer
  explain: "…",                 // supports <b> and <em>
  tip: "One-line rule shown under the explanation."
}
```

`{{blank}}` is replaced by the gap; it is filled in automatically once the
question is answered. For “pick the sentence” items, leave `{{blank}}` out and
put the question in `prompt`.

## Notes

* Everything is vanilla JS; there is nothing to install and no network calls.
* The 10-question quick practice is balanced across all five areas.
* `index.html` can be opened straight from the filesystem (`file://`) — the two
  scripts are loaded as plain files, not ES modules.
