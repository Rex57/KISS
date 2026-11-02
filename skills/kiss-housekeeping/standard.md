# The docs standard

This is what "clean" means for housekeeping. It takes the shared practice of large engineering teams and makes it checkable:
- docs as code: pages in the repo, reviewed and tested like code;
- a single source of truth: each fact in one home;
- four kinds of documentation: tutorials, how-to guides, reference and explanation;
- decision records;
- design docs with a status;
- a changelog, newest release first;
- runbooks and an environments page;
- an owner and a review date on each page.

`scripts/check_docs.py` enforces each rule marked **(gate)**.

When the repo already has a convention that does the same job (its own decision log, its own runbook folder), keep it and fit it to these rules. A rename costs links and memory, and it adds nothing.

## One home per fact

Each fact lives in one place: its **home**. Every other page links to the home and does not copy it. When two pages hold one fact, pick the home with this order:
1. The page whose kind matches the fact. A how-to goes to a runbook, a guarantee to the spec, a decision to the log.
2. The page that people already link to most.
3. The shorter path.

Then cut the other copy down to one line and a link.

A summary page (a functional spec, a deck, the front door) states each fact at its own level and links the home. It never copies a table the home holds: a copied table goes stale on the day the home changes.

Four topics are spread over many pages in every repo. Look for them first:
- **status**: what is done and what comes next;
- **releases**: what changed, and when;
- **environments**: what runs where;
- **the code map**: where the code lives.

Each one gets exactly one home.

## Kinds of page

The kind comes from the path, so a person and the gate read it the same way **(gate)**.

| Kind | How the path shows it | Rule |
|---|---|---|
| living | everything below that is not another kind | Kept true. Has a status line. The map links it. |
| log | listed in the gate's `logs` (CHANGELOG, the decision log) | Append-only, newest entry on top. Old entries keep their words. Has a status line. The map links it. |
| record | a path part starts with `YYYY-MM-DD` | Kept as written. A living page or a log links it (its **index**). |
| history | under `archive/` | Superseded. Never cited as current. `archive/README.md` indexes the folders. |
| agent | `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, `.claude/...`, `.kiss/...` | Instructions for agents. Links and names are checked; no status line. |

A record may get one line at its top that names its replacement: `Superseded by <link> (YYYY-MM-DD).` No other edit to a record, except a path update after a move.

## Classifying

The hard cases, with the action each one gets:
- **A contract that the code now holds** (its "what is built" table names files that are gone): the code is the home. The page becomes a dated design record, and the map points at the code.
- **A dated block inside a living page** (an old checklist, a release's notes, a plan): move it to a record and index it. The living page keeps only the current state.
- **A file that code, UI text or people cite by its name** (`STANDARD.md`, "see STANDARD.md D6" in a help text): keep the name and move only its folder.
- **A sign-off page with decisions still open** (the ROADMAP or the decision log points at it to sign): living, even when most of its text is old. Date its old blocks in their headings ("Current state on 3 Aug") and send the map's questions to the living homes of its rules; do not move it to a record.
- **A page that tells you to translate its own old names** ("where it says standard 1.2, read v1.2"): fix the names in its text; the banner is the symptom.
- **A pile of "Updated <date>" banners** at the top of a page: replace it with the status line and one sentence that points at `git log`.
- **Agent memory that holds facts no page holds** (a team's state, an open list): write them into the home page, and leave the memory as a pointer.

## The status line **(gate)**

The first 12 lines of every living page and log hold this line:

```
> Status: current · Owner: <name> · Reviewed: YYYY-MM-DD
```

`Status` is `current`, `draft` or `deprecated`. `Reviewed` is the day a person last read the whole page against the system. Editing one line is not a review: when you add the line to a page you did not read in full, use the date of its last real update. After `stale_days` (default 120) the gate prints a warning. The page then needs a review, not a new date.

## Layout

Folders by purpose, not by origin. A folder named for the tool or the person that wrote it ("notes-from-X") is a smell.

```
README.md          front door: what it is, a quick start, the link to the map
CLAUDE.md          agent rules (or AGENTS.md); link out, never repeat
ROADMAP.md         forward only: the current phase, the blockers and whose they are, the next steps
CHANGELOG.md       releases, newest first (a log)
ARCHITECTURE.md    how the parts fit, and the one code map
SPEC.md            the guarantees and the rules that must hold (where the repo has one)
OWNERS.md          who owns what
docs/
  README.md        THE MAP
  decisions.md     the decision log (a log; one file, numbered entries)
  reference/       facts to look up: APIs, contracts, standards, glossary.md
  operations/      how-to for operators: deploy, runbook, environments.md
  design/          design docs, dated (records), plus README.md: an index with each status
  systems/<name>/  one folder per external system: README.md (living), notes/ and dated research (records)
  <area>/          a product area with living pages of its own (for example console/)
archive/           history, plus README.md
tools/check_docs.py  the gate: the project's own copy
```

Files that a server serves or a build packs stay where they are. Move the prose around them, not the served files.

## The map: docs/README.md **(gate)**

The map routes readers and holds no facts of its own, so it cannot go stale the way a status page does. It links every living page and log **(gate)**. It has three parts:
- **By question**: "What is done and what is next?" goes to ROADMAP; "What runs where?" goes to environments; and so on.
- **By reader**: newcomer, operator, integrator, owner, agent. Each gets a short reading path.
- **By kind**: how-to, reference, explanation, record.

It ends with "How we keep docs", which states these rules in a few lines for the repo's people. The front door links the map **(gate)**.

## Names **(gate)**

`docs/reference/glossary.md` has a table with the columns `Name | Means | Old names`. The gate reads the `Old names` column. A term written `/like this/` is a regex (it can hold no comma); any other term is a whole word. A living page or an agent file fails when a line of its prose uses an old name, unless the same line also holds the current name. That exception allows "Quillo (called Fernweb until 16 Oct)". Code spans and fenced blocks are identifiers, so the gate skips them. Logs, records and history keep the words of their day.

Keep each pattern narrow. An old name that also means something else (`v2` for any version 2, `the V2 framework`) gets a pattern with its exceptions, and the text gets the unambiguous form ("version 2"). To mention an old name as a term ("old pages say `V1`"), put it in a code span. In a table cell, write a pipe inside a pattern as `\|`.

## File names

- Records: `YYYY-MM-DD-slug.md`, the date the content was true.
- New pages: `lower-case-kebab.md`.
- Upper case only for the root files that every repo has (README, CHANGELOG, CLAUDE, OWNERS, SPEC...), and for files that already have many links. A rename that adds nothing is churn.

## Where a new page goes

| It is | It goes |
|---|---|
| a decision | a numbered entry in `docs/decisions.md` |
| the reference of one thing: a store, a schema, an API | `docs/reference/<slug>.md`, and a question on the map |
| a functional specification of a major version (an FSD for stakeholders) | `docs/reference/<product>-v<major>-api-v<x.y>.md`: living, on the map, a summary that links each fact's home. The next major version's spec replaces it, and the old one goes to `archive/` with "Superseded by" |
| a design before a build | `docs/design/YYYY-MM-DD-slug.md`, and a row in the design index |
| a how-to for an operator | `docs/operations/` (one runbook per task) |
| a fact about another system, or a note to its team | `docs/systems/<name>/` (its README holds the current state) |
| a release | an entry in `CHANGELOG.md` |
| a change of what is next | `ROADMAP.md` |
| a build plan for an agent | out of the docs: a local working folder, then `archive/plans/` when it is done |

## Size

A living page longer than about 600 lines usually does more than one job. Split it by job (status, history, runbook, map), and leave one link where each part was. A log can grow; when it is long, cut it by year or by release into dated records.

## Retire, do not delete

A replaced page goes to `archive/`, with a line that names its replacement. Delete only exact copies and stubs: git keeps them.
