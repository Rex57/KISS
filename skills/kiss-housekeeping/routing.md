# The routing test

The gate proves the links resolve. It cannot prove that a reader who starts at the map reaches the
right page, or that the page is true. The routing test does: cold readers answer real questions
from the docs alone, and you score each answer against the code.

Run it in step 7 of a first run (before and after), and in upkeep when the map changes or an
outside document (a spec, an audit, a stakeholder's questions) arrives to be checked.

## 1. Questions

Write 20 to 35 questions from a real reader's need: the claims of an outside spec, a newcomer's
first week, the questions people ask the owner. Never fewer than 20, however small the repo, and
always a newcomer's questions on how to install, run and test it. Write each one neutral: "How many tables does the
store have?", never "Is it 31?". Each one must have an answer in the code or a running service.

## 2. Truth

Answer every question yourself from the code (CodeGraph, a store made fresh, the service), with the
file and line, and write the answers to a scratch file (`Q | answer | file:line`) before you start the
readers. A truth written after the readers report anchors on them.

## 3. Readers

Start fresh agents with no context, in parallel, with the brief below:
- **after**: the tree as it is now, entry point the map;
- **before** (first run only): the commit before the run, in a scratch worktree
  (`git worktree add --detach <scratch> <commit>`), entry points the old ones its agent
  instructions file names. Remove the worktree when the test ends.

Each reader's loaded agent instructions file (`CLAUDE.md`, `AGENTS.md`) is the current one. Tell it
that this is not a doc page, so that a fact only that file holds shows up as a finding.

## 4. Score

For each answer: right, partial, wrong or not found, against the truth. Per reader: routed, searched
and not found; distinct pages; tool calls, tokens and minutes (from the agent's usage). Print each
count with its denominator.

**Pass:** every question routed by links, and no wrong answer. A search means a missing link or a
missing home. A wrong answer means a page that is not true: fix it at its home (U1, U2) in this run.
Each "friction" a reader reports is a finding too.

## The brief

```
You are a COLD READER in a documentation routing test. Answer the questions below using ONLY the
project's Markdown docs, reached by following links from the entry point, and report how you found
each answer. The route record matters more than the answer.

ROOT = <absolute path>. ENTRY POINT = <ROOT/docs/README.md, or the old entry points>.
1. Open only .md files under ROOT, with the Read tool. No code, no CodeGraph, no Grep/Glob/find/ls,
   except rule 3.
2. Open a page only when a page you already opened links or names it.
3. After 4 pages with no answer for a question, you may run ONE
   `grep -rl -i "<term>" --include=*.md ROOT`; mark that question SEARCH.
4. Your loaded agent instructions file is not a doc page. Do not answer from it; note a fact only it holds.
5. archive/ is history: say "archive" when an answer comes from there.
6. Read big pages in parts when a heading tells you where to look.

QUESTIONS: <numbered list>

REPORT (as text, no files):
A. | Q | ROUTED / SEARCH / NOT FOUND | route (page → page#heading) | new pages | answer (2 lines,
   numbers as the page gives them) | the page's Status/Reviewed | notes (pages that disagree,
   stale claims, a fact only in the agent instructions file or archive) |
B. Totals: routed, search, not found; distinct pages opened; the 5 pages used most.
C. Routing friction, at most 8 bullets, each with the page and the line or heading.
```
