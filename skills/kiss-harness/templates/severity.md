Your sort rules for review round $ROUND of $TITLE. You sort yourself and change no code. The findings: $FINDINGS

The reviewer reported every issue on purpose; you decide which need a fix now. A run has at most 2 fix rounds per review and 3 per run, then a gate: put in "fix" only what the bar below asks for.
1. Merge duplicates (the same cause in two findings) into one, keeping both evidence lines.
2. For each finding read its evidence in W = $W (read-only) and the rulings in $R/decisions.md. Drop a finding only when the evidence is wrong (say why).
3. Put each one in a bucket:
   - "fix", always, at any severity: a wrong result, a broken command or link, data, security, a guard, an owner rule (a ruling or a project rule), a broken acceptance line, a test that cannot fail; and any other finding with an effect on a user.
   - "owner": a choice only the owner can make (the spec or decisions do not settle it).
   - "log": a low finding with no effect on a user, data or an owner rule (wording, style, an edge no user meets). It stays in the sort file, and you show it at the merge gate.
   A finding of medium or higher severity that fits none of these is a "fix": only a low finding goes to the log.
4. Write $R/sort-$ROUND.json:
   {"fix": [<findings, highest severity first>], "owner": [{"id": "", "question": ""}], "log": [], "dropped": [{"id": "", "why": ""}]}
5. Go on: ask each "owner" item as a decision, then write the "fix" findings to $R/fix-$ROUND.md and start fix round $ROUND (SKILL.md step 9). With no "fix" finding: after a risky ticket's solo review, send "continue" to the implementer; after the final review, go on to the close.
