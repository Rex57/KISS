You sort the review findings of $TITLE. You change no code. The findings: $FINDINGS

The reviewer reported every issue on purpose; you decide which need a fix now.
1. Merge duplicates (the same cause in two findings) into one, keeping both evidence lines.
2. For each finding read its evidence in W = $W (read-only) and the rulings in $R/decisions.md. Drop a finding only when the evidence is wrong (say why).
3. Put each one in a bucket:
   - "fix": wrong behaviour, a broken acceptance line, a broken ruling or project rule, a test that cannot fail, a risk to a real system's data.
   - "owner": a choice only the owner can make (the spec or decisions do not settle it).
   - "log": true, but wording, style or an edge with no user effect.

End with one message that ends with a fenced ```json block:
{"fix": [<findings, highest severity first>], "owner": [{"id": "", "question": ""}], "log": [], "dropped": [{"id": "", "why": ""}]}
