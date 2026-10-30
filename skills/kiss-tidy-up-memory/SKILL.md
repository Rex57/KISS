---
name: kiss-tidy-up-memory
description: Use when the user says "tidy up memory" (that phrase is the go for the whole flow), or asks to tidy, consolidate or clean a repo's file memory and agentmemory (then show the plan and wait for a yes). The full flow is inventory, file-memory merge, loss check, agentmemory revisions over REST, disk clean-up, and a report.
---

# Tidy up memory: the flow

When the user says "tidy up memory", run all of it for the current repo; that sentence is the go. For any other
wording, show this plan and wait for a yes. Deletions go to the Trash (`~/.Trash/<dated folder>` on macOS) with
paths kept, never `rm -rf`; the current session's files are never touched.

Where the memory lives:

| Agent | File memory | Sessions and subagent transcripts |
|---|---|---|
| Claude Code | `~/.claude/projects/*<repo>*/memory/` (notes plus the `MEMORY.md` index) | `~/.claude/projects/*<repo>*/`: per session `*.jsonl`, `*/subagents/`, `*/tool-results/` |
| Codex, Gemini CLI, Antigravity | the agent's own memory file or folder | the agent's own session store |

Skip a step whose store the agent does not have. agentmemory is optional: run step 4 only when
`curl -s http://localhost:3111/agentmemory/livez` answers.

1. **Inventory** (show it, then go on; no wait): for each memory folder of the repo, the notes; per session
   transcript: date, size, subagent count; the subagent transcripts against `journal.jsonl`; the tool results.
   Mark the folders of removed worktrees: they go in step 5, after their notes pass steps 2 and 3.
2. **File memory:** first copy each memory folder to a scratch folder (step 3 compares against it). Read every
   note in full; merge overlaps; cut each to what is still true; drop what is stale or the repo already records;
   keep feedback, user and reference notes. Then check: each note's name matches its filename, every note is in
   the index with one short line, and no `[[link]]` points to a missing note.
3. **Loss check, before anything old is deleted:** draft the step 4 revisions first. Per old note and old
   agentmemory entry, list each fact that neither the new notes, the drafted revisions nor the repo hold; a
   second agent (the skeptic) checks each listed fact: is it really missing, and is it still true. Put back each
   fact that is both (one merge lost 13 of 2,161 facts before this check existed).
4. **agentmemory (REST):** every call except `/livez` sends
   `-H "Authorization: Bearer $(cat ~/.agentmemory/secret)"`. Back up `GET /agentmemory/memories` to
   `~/.agentmemory/backups/memories-<date>-before-<repo>-tidy.json`. Save the revised project memories first:
   memories are never edited, so a revision's first line names what it replaces (`SUPERSEDES … (mem_…)`), with
   `project` set and no password (its LLM steps send stored text to an outside model). Then delete the replaced
   ones. Consolidate only with `POST /agentmemory/consolidate-pipeline` `{"tier":"all"}`, never
   `POST /agentmemory/consolidate` (each run writes duplicate memories). Check the count has no duplicates.
5. **Disk:** if the repo's close-out note names metrics that read the subagent transcripts and they have not run
   yet, ask before you move anything. Then move every session's subagent transcripts (all but `journal.jsonl`),
   the tool results and the marked removed-worktree folders (whole) to the Trash. In the other folders, keep the
   journals (each agent's result), the session transcripts (for resume) and the meta files; remove only folders
   left empty, with `rmdir`.
6. **Report:** before and after (counts, sizes), what moved where, what was kept.
