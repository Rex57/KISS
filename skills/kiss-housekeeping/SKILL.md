---
name: kiss-housekeeping
description: Housekeeping of a repo's documentation and knowledge base. It gives each fact one home, sorts pages into living pages, logs, records and history, builds the map that routes readers, retires stale pages, fixes names, moves files without breaking code or tests, keeps each page true to the code, and installs a docs gate in the project's tests. Use it for a docs clean-up, consolidation or reorganisation ("clean up the docs", "housekeeping", "docs gate"), and for the docs Upkeep at a harness close.
---

# Housekeeping

The end state: each fact has one **home**. Each page is a **living page** (kept true), a **log** (append-only), a **record** (dated, kept as written) or **history** (in `archive/`). One **map** routes every reader. A **gate** in the test suite keeps it that way. The standard behind these words is in [standard.md](standard.md): read it before step 2. It also says what to do when the standard and the repo disagree.

The skill keeps each page true to the code three ways: step 3 checks each claim of "current" against the code, U2 reads each page a change touched against the code before it gets a new `Reviewed` date, and the routing test scores each answer against the code.

Pick the run:
- **First run**: the owner asks for a clean-up. A repo with no gate gets one only on that ask. Do steps 1 to 8.
- **Upkeep**: the gate exists, and a phase or a harness run closes, or a page is added. Do steps U1 to U3.

`HK` is this skill's folder (the folder of this file). The scripts are in `$HK/scripts/`. Each one prints its own usage and has a `--selftest`. They use the standard library only, and each one is read-only or a dry run unless you pass `--apply`. Run them as `python3 -I "$HK/scripts/<name>.py"`: each adds its own folder to its import path, so they find each other there.

## First run

### 1. Ground
1. Make a branch by the repo's delivery rules, from a clean tree.
2. List the open branches that change docs (`git log main..<branch> -- '*.md'`). A move under an open branch turns into a conflict later. Settle each with the owner: merge one whose content the owner approved into your branch (never into main), or leave its pages alone.
3. Run the suite once. The repo's own rules (lint, layering, "every selftest is collected") bind the gate's copy too (step 6).

Done when the branch exists, the suite is green, and no open branch changes a page you will move.

### 2. Inventory
Run `python3 -I "$HK/scripts/inventory.py" <repo> > inventory.json`, and `python3 -I "$HK/scripts/check_docs.py" <repo>` for the baseline: the gate is read-only, so run it as a report from here on, and install it in the suite only in step 6. Each tracked `.md` file gets a row: kind, lines, last change, title, inbound links, broken links, old names, copies, and `used_by`. `used_by` lists the code, tests, tools and config that name the file's path; these are its **path users**.
Done when the row count equals `git ls-files '*.md' | wc -l`. Print both numbers.

### 3. Classify
Read the opening and the outline of every file. Read the whole file where its action depends on it. Give each row one action (KEEP, UPDATE, MOVE, MERGE, SPLIT, ARCHIVE, DELETE, NEW), a target path, and a reason that names its evidence. Then build the **topic table**: each topic that more than one file holds, the files that hold it, and its one home.

Evidence, strongest first:
1. The code or the running service.
2. The page's own banner ("snapshot", "superseded").
3. Its links and path users.

A date alone proves nothing: an old page can be true, and a page edited yesterday can be stale. Check a claim of "current" against the code, never against another document. The rules for the hard cases (a contract the code now holds, a dated block inside a living page, a file that code cites by name) are in [standard.md](standard.md), "Classifying".
Done when every row has an action and every topic in the table has exactly one home.

### 4. Owner review
Publish the plan for the owner, with the topic table (topic, files, home). With more than 40 rows, use a page with a filter table and the counts per action. Name the decisions that belong to the owner: a change to the agent's own instructions, a page that people use being retired, a split of a contract that tests read. Give your recommendation for each one.
Done when the owner has answered each decision.

### 5. Execute
Make one commit per step, in this order. The early steps make the later moves smaller.
1. Delete exact copies and stubs.
2. Retire superseded pages to `archive/`, and write `archive/README.md`.
3. Records: give each a date-first name, put it beside the living page it feeds, and list it in that page's index.
4. Move the pages that keep their content to their new homes.
5. Splits and merges: write each new home from its sources, then cut each source down to a link.
6. Names: write the glossary first, then fix the living pages.
7. Status lines on every living page and log.
8. The map.
9. The gate (step 6).

Every move goes through `python3 -I "$HK/scripts/move_docs.py"`. It runs `git mv`, rewrites the links, and replaces the old paths. Fix each path user it reports **in the same commit**, then run the tests those path users belong to, and every test that scans docs: a split can take away the one example a scan counts on. [moves.md](moves.md) lists the path users that a script cannot see.

Commit each step before you start the next one. Two steps' edits in one file cannot be split into two commits afterwards without an interactive tool.

Before a split, copy the whole page to `archive/<date>-before-split/`, so nothing is lost. Then write each new home short, from the page, and link the copy once.
Done when every commit leaves the suite green, with the denominator printed.

### 6. Gate
Copy `$HK/scripts/check_docs.py` into the repo as `tools/check_docs.py`: the project owns its copy, never a path into this skill (that path changes with each version). Fill in its `CONFIG`, and add it to the suite: a test that runs `python3 -I tools/check_docs.py <repo>` and expects exit 0, plus one that runs its `--selftest`. Run it. Then plant each fault once: a broken link, a broken anchor (`page.md#gone`), an orphan, an old name, a missing status line. Revert each plant. When the repo has a facts file (`.kiss/project.md`), write the gate's command on its `Docs gate:` line.
Done when the gate passes on the repo and goes **red** on each plant.

### 7. Verify once
Run the full suite and the gate on the exact commit you merge or tag, after the branch switch: a working tree can keep an empty folder that git no longer has, and a check can pass on it. Check everything that serves or packs docs: served pages, release packs, generated sites. Report before and after, each with its denominator: files per kind, broken links, old names in living pages, orphans.

Then run the routing test, before and after ([routing.md](routing.md)). The steps above fix the structure and the names; they do not make a page true, and a page that moved keeps every stale line it had. Fix each wrong answer the test finds in this run, and list each partial one as upkeep. When you cannot start fresh readers, say that the routing test did not run: the run is then not done. Report the number of topics with more than one home: it must be 0.
Done when the gate is green on the merged commit, every routing question is routed by links with no wrong answer, and no topic has more than one home.

### 8. Fold back
Write down what the run taught, where it belongs:
- A lesson about the project (a trap, a path user, a convention) goes into the project's facts file (`.kiss/project.md`), or the repo's agent instructions file when it has none.
- A lesson about this skill (a step, rule or script that was wrong, missing or useless) goes into the KISS feedback block, as file, line and new text (below).

Done when each lesson of the run is in one of the two.

## Upkeep

- **U1.** Copy the code below `CONFIG` from `$HK/scripts/check_docs.py` over the project's `tools/check_docs.py`, and keep the project's `CONFIG`. Run the gate. Fix each failure at its home.
- **U2.** Read each living page that the phase touched against what changed. Make it true, and set its `Reviewed` date. A page too long to read in one pass (a contract, a guide): split it by section across parallel reviewers. First list the exact strings the tests read from the page (search the tests for the page's file name; an `index("...")` on its text is a pointer like a path), and give that list to every reviewer and to the editor. Each reviewer checks every claim in its section against the code and returns its findings as text, each with the evidence (file and line) and the replacement. One editor then checks each finding against the code and applies them all in one scripted pass, where each edit must match exactly once. A names pass is not a review: only a review earns today's `Reviewed` date.
- **U3.** Put each new page where [standard.md](standard.md) "Where a new page goes" says. Add each new record to its index.
- **U4.** When the map changes, or an outside document (a spec, an audit, a stakeholder's questions) arrives to be checked against the system, run the routing test ([routing.md](routing.md)) on the tree as it is. Fix each wrong answer at its home.

**KISS feedback.** Last, follow [`rules/feedback.md`](../../rules/feedback.md) at the plugin root: with `KISS_FEEDBACK=1`, end your final message with one KISS feedback block; else add nothing.
