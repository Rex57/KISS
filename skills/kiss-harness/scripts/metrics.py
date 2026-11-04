#!/usr/bin/env python3
"""The run's token use from Claude Code's transcripts (SKILL.md, step 10). Reads only; prints counts, never text.

  python3 -I metrics.py R              one line: the token part of the metrics line
  python3 -I metrics.py R --context    one line per subagent: its role, its id and its context now (the last
                                       request's input, cache-write and cache-read tokens), marked past the bound
  python3 -I metrics.py --selftest

Transcripts: under CLAUDE_CONFIG_DIR (default ~/.claude), projects/*/<session>/subagents/**/agent-<id>.jsonl, each
beside agent-<id>.meta.json (its agentType gives the role). A subagent counts when its first message (the prompt)
names R; the controller is the session file beside that subagents folder, counted from its first message that names
R. Each message id counts once. CodeGraph share (subagents only): CodeGraph calls (the CLI's read commands,
cgcallers, the MCP tools) over CodeGraph calls plus code searches (the Grep tool, grep, rg, git grep); a grep that
filters another command's output is counted apart. No subagent names R: "tokens: not available on this agent".
"""
import glob, json, os, re, sys

CG_READ = {"query", "explore", "context", "node", "files", "callers", "callees", "impact", "affected"}
GREPS = {"grep", "egrep", "fgrep", "rg"}
NA = "tokens: not available on this agent"
RUN = re.compile(r"/runs/([\w.-]+)")   # a run folder's name in a path
BOUND = 350_000   # context tokens; past it, the controller starts a new agent at the next round boundary


def config():
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")


def names(R):
    return re.compile(re.escape(R.rstrip("/")) + r"(?![\w.-])").search


def role(agent_file):
    try:
        kind = json.load(open(agent_file[:-len(".jsonl")] + ".meta.json")).get("agentType", "")
    except (OSError, ValueError):
        kind = ""
    # a worker or other helper the controller started counts as the controller's work
    return "reviewers" if "reviewer" in kind else "implementer" if "implementer" in kind else "controller"


def subagents(R):
    """[(file, role)] of each subagent whose prompt names R as the first run folder it names (a later run's
    reviewer may name an older run as an input)."""
    hit, run = names(R), RUN.search(R)
    out = []
    for f in glob.glob(os.path.join(config(), "projects", "*", "*", "subagents", "**", "agent-*.jsonl"), recursive=True):
        with open(f, errors="replace") as fh:
            line = fh.readline()
        first = RUN.search(line)
        if hit(line) and (not run or not first or first.group(1) == run.group(1)):
            out.append((f, role(f)))
    return out


def messages(path, start=None):
    """The assistant messages of a transcript, from the first line that start() matches (all when None)."""
    with open(path, errors="replace") as fh:
        for line in fh:
            if start is not None:
                if not start(line):
                    continue
                start = None
            if '"assistant"' not in line:
                continue
            try:
                d = json.loads(line)
            except ValueError:
                continue
            m = d.get("message")
            if d.get("type") == "assistant" and isinstance(m, dict) and m.get("id"):
                yield m


def bash_kinds(cmd):
    """(codegraph, search, piped grep) counts of one Bash command."""
    cg = search = piped = 0
    # shortcut: splits on ; && || | and newlines without reading quotes or heredocs; upgrade when counts look wrong
    for seg in re.split(r"\|\||&&|;|\n", cmd):
        for i, stage in enumerate(seg.split("|")):
            w = [x for x in stage.split() if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", x)]
            if w[:1] == ["rtk"]:
                w = w[1:]
            if not w:
                continue
            first = os.path.basename(w[0])
            if (first == "codegraph" and w[1:2] and w[1] in CG_READ) or first == "cgcallers" or (
                    first.startswith("python") and any(os.path.basename(x) == "cgcallers.py" for x in w[1:])):
                cg += 1
            elif first in GREPS or (first == "git" and w[1:2] == ["grep"]):
                if i:
                    piped += 1
                else:
                    search += 1
    return cg, search, piped


def k(n):
    return f"{int(n / 1000 + 0.5)}k"


def tokens(R):
    R = os.path.abspath(R)
    subs = subagents(R)
    if not subs:
        return NA
    usage, tools = {}, {}   # message id -> (role, usage); tool_use id -> block (subagents only)
    for f, r in subs:
        for m in messages(f):
            usage[m["id"]] = (r, m.get("usage") or {})
            for b in m.get("content") or []:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    tools[b.get("id")] = b
    for session in {f.split(os.sep + "subagents" + os.sep)[0] + ".jsonl" for f, _ in subs}:
        if os.path.isfile(session):
            for m in messages(session, names(R)):
                usage.setdefault(m["id"], ("controller", m.get("usage") or {}))
    out = {"implementer": 0, "reviewers": 0, "controller": 0}
    inp = reads = hour = 0
    for r, u in usage.values():
        out[r] += u.get("output_tokens", 0)
        reads += u.get("cache_read_input_tokens", 0)
        inp += u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0) + u.get("cache_read_input_tokens", 0)
        hour += (u.get("cache_creation") or {}).get("ephemeral_1h_input_tokens", 0)
    cg = search = piped = 0
    for b in tools.values():
        name = b.get("name", "")
        if name.startswith("mcp__codegraph__"):
            cg += 1
        elif name == "Grep":
            search += 1
        elif name == "Bash":
            c, s, p = bash_kinds((b.get("input") or {}).get("command", ""))
            cg, search, piped = cg + c, search + s, piped + p
    share = f"{cg / (cg + search):.2f}" if cg + search else "n/a"
    return (f"Tokens: output {k(sum(out.values()))} (implementer {k(out['implementer'])}, reviewers "
            f"{k(out['reviewers'])}, controller {k(out['controller'])}), input {k(inp)} "
            f"({round(100 * reads / inp) if inp else 0}% cache reads), 1-hour cache writes {k(hour)}; CodeGraph share "
            f"{share} (CodeGraph {cg}, search {search}, {piped} more greps after a pipe)")


def context(R):
    subs = subagents(os.path.abspath(R))
    if not subs:
        return NA
    lines = []
    for f, r in sorted(subs):
        u = {}
        for m in messages(f):
            u = m.get("usage") or {}
        n = u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0) + u.get("cache_read_input_tokens", 0)
        agent = os.path.basename(f)[len("agent-"):-len(".jsonl")]
        lines.append(f"{r.rstrip('s')} {agent}: context {n}" + ("; past 350k: start a new one at this boundary"
                                                                    if n > BOUND else ""))
    return "\n".join(lines)


def selftest():
    import tempfile

    def user(text):
        return {"type": "user", "message": {"role": "user", "content": text}}

    def said(mid, out, inp, write, read, hour=0, tools=()):
        return {"type": "assistant", "message": {"id": mid, "role": "assistant", "content": [
            {"type": "tool_use", "id": f"{mid}-{n}", "name": t, "input": {"command": c} if c else {}}
            for n, (t, c) in enumerate(tools)], "usage": {
            "input_tokens": inp, "output_tokens": out, "cache_creation_input_tokens": write,
            "cache_read_input_tokens": read,
            "cache_creation": {"ephemeral_1h_input_tokens": hour, "ephemeral_5m_input_tokens": write - hour}}}}

    def put(path, rows, kind=None):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write("".join(json.dumps(r) + "\n" for r in rows))
        if kind:
            with open(path[:-len(".jsonl")] + ".meta.json", "w") as f:
                json.dump({"agentType": kind}, f)

    R = "/x/runs/r7"
    with tempfile.TemporaryDirectory() as C:
        os.environ["CLAUDE_CONFIG_DIR"] = C
        assert tokens(R) == NA, "an empty config folder"
        S = os.path.join(C, "projects", "-x", "s1")
        m1 = said("m1", 1200, 10, 2000, 0, hour=2000, tools=[("Bash", "cd /w && codegraph explore -p /w 'a b'"),
                                                              ("mcp__codegraph__codegraph_explore", None)])
        put(os.path.join(S, "subagents", "agent-a1.jsonl"), [
            user(f"You are the implementer. R = {R}"), m1, m1,           # a message written twice counts once
            said("m2", 800, 5, 0, 3000, tools=[("Bash", "pytest -q | grep x"), ("Bash", "grep -rn x src"),
                                               ("Grep", None)])], "kiss:kiss-implementer")
        put(os.path.join(S, "subagents", "agent-a2.jsonl"), [
            user(f"You are the reviewer of {R}/tickets.json"),
            said("m3", 1400, 100, 1000, 2000, tools=[("Bash", "python3 -I /h/cgcallers.py f -p /w | grep lsp")])],
            "kiss:kiss-reviewer")
        put(os.path.join(S, "subagents", "agent-a3.jsonl"), [               # its prompt names another run: left out
            user("You are the implementer. R = /x/runs/r7-old"), user(f"later it reads {R}"),
            said("m4", 9000, 9000, 0, 0, tools=[("Grep", None)])],
            "kiss:kiss-implementer")
        put(os.path.join(S, "subagents", "agent-a4.jsonl"), [               # its own run first, R later: left out
            user(f"You review /x/runs/r8; one input is {R}/review-1.md"), said("m10", 5000, 5000, 0, 0)],
            "kiss:kiss-reviewer")
        put(S + ".jsonl", [said("m0", 7000, 7000, 0, 0), user(f"start the run in {R}"),   # m0: before R
                           said("m5", 600, 1, 500, 4000, tools=[("Grep", None)])])
        # worked example: output 1200+800, 1400, 600 = 4000; input 2010+3005+3100+4501 = 12616, reads 9000 = 71%;
        # 1-hour writes 2000; CodeGraph 3 (codegraph explore, MCP explore, cgcallers), search 2 (grep -rn, Grep),
        # 2 greps after a pipe; share 3 / 5; the controller's Grep is not a subagent's
        want = ("Tokens: output 4k (implementer 2k, reviewers 1k, controller 1k), input 13k (71% cache reads), "
                "1-hour cache writes 2k; CodeGraph share 0.60 (CodeGraph 3, search 2, 2 more greps after a pipe)")
        got = tokens(R)
        assert got == want, got
        assert tokens(R + "/") == want, "a trailing slash names the same run"
        assert tokens("/x/runs/none") == NA
        assert context("/x/runs/none") == NA
        put(os.path.join(S, "subagents", "agent-a5.jsonl"), [
            user(f"You are the implementer. R = {R}"), said("m6", 1, 1, 0, 399_999), said("m7", 1, 1, 1000, 349_999)],
            "kiss:kiss-implementer")
        put(os.path.join(S, "subagents", "agent-a6.jsonl"), [
            user(f"You are the reviewer of {R}"), said("m8", 1, 1, 0, 500_000), said("m9", 1, 2, 998, 348_000)],
            "kiss:kiss-reviewer")
        # a1's last request 5 + 0 + 3000; a2's 100 + 1000 + 2000; a5's 351,000 is past the bound; a6's 349,000 is
        # not, though its earlier request was larger
        assert context(R).splitlines() == [
            "implementer a1: context 3005", "reviewer a2: context 3100",
            "implementer a5: context 351000; past 350k: start a new one at this boundary",
            "reviewer a6: context 349000"], context(R)
    print("metrics selftest ok")


def main(argv):
    if argv[1:] == ["--selftest"]:
        return selftest()
    if len(argv) == 3 and argv[2] == "--context":
        return print(context(argv[1]))
    if len(argv) != 2:
        sys.exit(__doc__)
    print(tokens(argv[1]))


if __name__ == "__main__":
    main(sys.argv)
