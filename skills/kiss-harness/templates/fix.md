Review round $ROUND of $TITLE found these issues, to fix now. $CLOCK
$FINDINGS

Fix each one in W, the way the surrounding code does it: one commit per finding, or one for findings in the same lines, with the trailer as before. Run the acceptance of each ticket you touched, the tests `codegraph affected -p "$W"` names, and each build step $PROJECT names for the files you changed. Append a `## Fix round $ROUND` part to $R/progress.md. Then end with one message that ends with a fenced ```json block:
{"round": $ROUND, "head": "<HEAD>", "fixed": [{"id": "", "commits": []}], "not_fixed": [{"id": "", "why": ""}]}
