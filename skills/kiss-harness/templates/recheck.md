The implementer answered round $ROUND of your findings with the commits $FIX_BASE..$FIX_HEAD. $CLOCK
The answer: $ANSWER

Check each finding again in the running product and the diff, the same way as before. Report any new issue the fixes made. End with one message that ends with a fenced ```json block:
{"round": $ROUND, "rechecked": [{"id": "", "status": "fixed|not fixed", "evidence": ""}], "findings": []}
