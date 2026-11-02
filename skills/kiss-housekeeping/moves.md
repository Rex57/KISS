# Moves that break nothing

A page move breaks its **path users**: the files that open, pack, serve or name its path. `scripts/move_docs.py` fixes the links and the full paths, and reports bare names. The rest are listed here. Find them all before the first move.

## What the script fixes

- Relative Markdown links, both from the moved page and to it, in every tracked `.md` file (history included, so archived pages still resolve). Anchors are kept, and a link the move does not affect keeps its spelling.
- A link labelled with the old path (`` [`docs/x.md`](docs/x.md) ``) gets the new path as its label.
- Each full repo-relative path (`docs/x/y.md`), wherever it stands as a word in a tracked text file outside history. That covers code comments, docstrings, config and prose.

It reports each line that still names a moved file by its bare name. The usual causes:
- an `os.path.join("docs", "x", "y.md")`;
- a loop over file names in a shell script;
- a partial path (`target/api-v1.md`);
- a renamed file.

Fix each report in the same commit.

## What only you can find

- **Tests that open a doc.** They fail at once, which is good. Run them after each step, not at the end.
- **Build and release scripts that pack docs** (a kit or release pack). They fail only when someone packs. Change the script, the list of contents the pack documents, and the pack's own README in the same commit, and keep the pack's inner paths equal to the repo's, so the links inside the pack resolve. Build a pack after the step.
- **Servers that serve docs by path** (a `/docs/` route, a docs site). Move no served file. Check one URL after the step.
- **Tests that skip "records" by folder.** Make them skip by kind: a dated path is a record. A folder list goes stale at the next move, and old commands in records then fail the runbook checks.
- **Tests that scan docs and assert they found something** ("no command found: the scan is broken"). A split can take away the one example they count. Make the scan read the real page (for example, join a command continued with `\`) rather than keep a copy for it.
- **Agent files and agent memory** (`CLAUDE.md`, `AGENTS.md`, memory files) that name a page. They do not fail; they mislead. Update them in the same change.
- **Section names quoted as pointers** (`section 5, "Standard 1.4"`). A heading is a pointer too: rename it together with every quote of it, records included, the same as a path.
- **Root files** (no `/` in the path) are never replaced as text, because `git show <tag>:FILE` must keep the old name. Fix their links by hand.
- **Old tags and commits** keep their old paths. That is fine: `git show <tag>:<old path>` still works.

## The commit

1. Write the moves for one step in a `moves.tsv` (`old<TAB>new`; a folder moves everything under it).
2. Run `python3 -I "$HK/scripts/move_docs.py" <repo> moves.tsv`. Read the dry run: it changes nothing.
3. Run it again with `--apply`.
4. Fix the path users it reports, and the ones listed above.
5. Run the gate's link check and the tests of each path user.
6. Stage by explicit path: `git add -A` sweeps in other people's work. Commit with the step's name.

`git mv` stages its renames at once. A commit made for another item while moves are staged takes the moves too. Read `git diff --cached --stat` before every commit. To commit one file while moves are staged, use `git commit -- <path>`.
