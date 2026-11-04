You sort the review findings of $TITLE. You change no code. The findings: $FINDINGS

The reviewer reported every issue on purpose; you decide which need a fix now. A run has at most 2 fix rounds per review and 3 per run, then a gate: put in "fix" only what the bar below asks for.
1. Merge duplicates (the same cause in two findings) into one, keeping both evidence lines.
2. For each finding read its evidence in W = $W (read-only) and the rulings in $R/decisions.md. Drop a finding only when the evidence is wrong (say why).
3. Put each one in a bucket:
   - "fix", always, at any severity: a wrong result, a broken command or link, data, security, a guard, an owner rule (a ruling or a project rule), a broken acceptance line, a test that cannot fail; and any other finding with an effect on a user.
   - "owner": a choice only the owner can make (the spec or decisions do not settle it).
   - "log": a low finding with no effect on a user, data or an owner rule (wording, style, an edge no user meets). It stays in the sort file, and the controller shows it at the merge gate.

End with one message that ends with a fenced ```json block:
{"fix": [<findings, highest severity first>], "owner": [{"id": "", "question": ""}], "log": [], "dropped": [{"id": "", "why": ""}]}
