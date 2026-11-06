#!/usr/bin/env python3
"""The run's token use from Claude Code's transcripts (SKILL.md, step 10). Reads only; prints counts, never text.

  python3 -I metrics.py R              one line: the token part of the metrics line; with the transcripts gone, the
                                       CodeGraph share (v2) from R/calls.jsonl; with neither, a refusal that names R
  python3 -I metrics.py R --context    one line per subagent: its role, its id and its context now (the last
                                       request's input, cache-write and cache-read tokens), marked past the bound
  python3 -I metrics.py R --record "<the controller's Metrics line>"   print the full line (the controller's part,
                                       then the token part) and write it as `- <run>: <line>` into metrics.md in
                                       the folder that holds R (a second record of a run replaces its line);
                                       refused unless the last `Full check at <sha>: <result>` line of
                                       R/decisions.md is a pass at the HEAD of R/run.json's W; it also writes
                                       R/calls.jsonl, one line per subagent tool call (role, tool, its command or
                                       path, blocked), replaced whole like metrics.md, before metrics.md
  python3 -I metrics.py --selftest

Transcripts: under CLAUDE_CONFIG_DIR (default ~/.claude), projects/*/<session>/subagents/**/agent-<id>.jsonl, each
beside agent-<id>.meta.json (its agentType gives the role). A controller session is a transcript whose Bash call ran
`prompt.py` (any step) on R (a resumed run has two); a subagent counts when it is under one and its meta toolUseId is
one of that session's Agent calls from its first such call to its last `metrics.py --record` of R (another run's
`prompt.py start` ends it first).
The controller is counted from the session's first message that names R. Each message id counts once. CodeGraph share (v2), subagents only: CodeGraph calls (the MCP tools, the CLI's
read commands, cgcallers, and the seed scripts briefs.py and callcheck.py) over CodeGraph calls plus symbol searches
plus code reads. A search (the Grep tool, grep, rg, git grep) is a symbol search when one alternative of its pattern,
without regex and keyword decoration, is a name the index holds (briefs.exists: W's index from R/run.json, else the
repo's), else a literal search (find and Glob too); a code read is the Read tool, cat, sed, head, tail, nl or awk of
a file type the index holds. Apart: literal searches, greps after a pipe, greps on docs or data (a doc or data file,
a docs folder, or a path outside the repo and W), counts (grep -c, | wc) and calls a PreToolUse hook or auto mode refused.
Commands are split outside quotes, at pipes, `;`, `&&`, `||` and `$( )`; a heredoc's body is text. No index: the
share is n/a with the reason. No subagent of the run: "tokens: not available on this agent".
"""
import glob, json, os, re, shlex, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import briefs  # noqa: E402  (the index lookup is the seed's own: briefs.exists)

CG_READ = {"query", "explore", "context", "node", "files", "callers", "callees", "impact", "affected", "search"}
SEEDS = {"briefs.py", "callcheck.py"}
CG_SCRIPTS = SEEDS | {"cgcallers.py"}
GREPS = {"grep", "egrep", "fgrep", "rg", "ag", "ack"}
READERS = {"cat", "sed", "head", "tail", "nl", "awk"}
DOCS = {".md", ".markdown", ".txt", ".rst", ".json", ".jsonl", ".log", ".csv", ".tsv", ".toml", ".yaml", ".yml",
        ".ini", ".cfg", ".env", ".out", ".lock", ".plist", ".svg", ".png", ".jpg", ".pdf", ".diff", ".patch"}
GREP_ARG = {"-e", "-f", "-A", "-B", "-C", "-m", "-g", "-t", "--regexp", "--file", "--include", "--exclude",
            "--exclude-dir", "--glob", "--type", "--max-count", "--context", "--after-context", "--before-context"}
# a search pattern's decoration: regex escapes and classes, and the keywords that lead a definition
DECOR = re.compile(r"\\[bswWdBSD<>]|\\\(|\\\)|\\\.|[\^$*+?()\[\]{}]|\b(?:def|func|function|class|struct|enum|protocol|"
                   r"extension|interface|async|export|static|private|public|let|var|const|override|fileprivate|"
                   r"internal|mutating|final)\b")
KEEP = ("command", "file_path", "pattern", "path", "glob", "output_mode")   # the input a calls.jsonl row keeps
SUBST = re.compile(r"\$\(([^()]*)\)")
HEREDOC = re.compile(r"<<-?\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)")
# shortcut: a << inside $(( )) or (( )) is a shift, so those spans are dropped before the heredoc search; one that
# holds a nested "))" ends early, and a << in quotes still starts a heredoc; upgrade when counts look wrong
ARITH = re.compile(r"\$?\(\(.*?\)\)")
LEAD = {"rtk", "do", "then", "else", "time", "xargs", "env", "sudo", "command", "nice", "exec"}   # words before the command itself
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


def runs_script(cmd, script, arg=None):
    """True when a statement of the command runs `script` (with `arg` as one of its next two words, when given)."""
    for st in statements(cmd):
        for part in st:
            w = words(part)[0]
            if any(os.path.basename(x) == script and (arg is None or arg in w[j + 1:j + 3]) for j, x in enumerate(w)):
                return True
    return False


def agent_calls(session, name):
    """The ids of a session's Agent calls for the run `name`: from its first Bash call that ran `prompt.py` (any step)
    on that run to its last `metrics.py --record` of it (another run's `prompt.py start` ends it first); none without
    such a call. A run resumed in a second session has its own controller session there."""
    ids, pending, on, recorded = set(), set(), False, False
    with open(session, errors="replace") as fh:
        for line in fh:
            if '"tool_use"' not in line or not any(x in line for x in ('"Agent"', '"Task"', "prompt.py", "metrics.py")):
                continue
            try:
                content = json.loads(line)["message"]["content"]
            except (ValueError, KeyError, TypeError):
                continue
            for b in content if isinstance(content, list) else []:
                if not isinstance(b, dict) or b.get("type") != "tool_use":
                    continue
                if b.get("name") in ("Agent", "Task"):
                    pending |= {b.get("id")} if on else set()
                    continue
                cmd = (b.get("input") or {}).get("command") or "" if b.get("name") == "Bash" else ""
                if not cmd:
                    continue
                runs = set(RUN.findall(no_heredocs(cmd)))
                if runs_script(cmd, "prompt.py"):
                    if name in runs:
                        on = True
                    elif on and runs_script(cmd, "prompt.py", "start"):
                        return ids if recorded else ids | pending
                elif on and name in runs and runs_script(cmd, "metrics.py", "--record"):
                    ids, pending, recorded = ids | pending, set(), True
    return ids if recorded else ids | pending


def subagents(R):
    """[(file, role)] of the run's own subagents: under each controller session (a transcript whose Bash call ran
    `prompt.py` on R), each one whose meta `toolUseId` is one of that session's Agent calls for the run."""
    name, out = os.path.basename(R.rstrip("/")), []
    for s in glob.glob(os.path.join(config(), "projects", "*", "*.jsonl")):
        ids = agent_calls(s, name)
        for f in glob.glob(os.path.join(s[:-len(".jsonl")], "subagents", "**", "agent-*.jsonl"), recursive=True) if ids else []:
            try:
                with open(f[:-len(".jsonl")] + ".meta.json") as m:
                    tid = json.load(m).get("toolUseId")
            except (OSError, ValueError, AttributeError):
                tid = None
            if tid in ids:
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


def stamp(line):
    try:
        return json.loads(line).get("timestamp") or ""
    except (ValueError, AttributeError):
        return ""


def other_run(path, R):
    """True when the session holds a subagent of another run (the first run folder its prompt names is not R's)
    that started after the session's first line that names R: the controller's count then holds that run's work."""
    hit, run = names(R), RUN.search(R)
    if not run:
        return False
    with open(path, errors="replace") as fh:
        start = next((stamp(line) for line in fh if hit(line)), None)
    if start is None:
        return False
    for f in glob.glob(os.path.join(path[:-len(".jsonl")], "subagents", "**", "agent-*.jsonl"), recursive=True):
        with open(f, errors="replace") as fh:
            line = fh.readline()
        first = RUN.search(line)
        if first and first.group(1) != run.group(1) and stamp(line) > start:
            return True
    return False


def no_heredocs(cmd):
    """The command without the bodies of its heredocs (text, not commands)."""
    out, end = [], None
    for line in cmd.split("\n"):
        if end is not None:
            end = None if line.strip() == end else end
            continue
        out.append(line)
        m = HEREDOC.search(ARITH.sub("", line))
        end = m.group(1) if m else None
    return "\n".join(out)


def statements(cmd):
    """[[part, ...], ...]: the statements of a command and their pipe parts, split outside quotes; heredoc bodies
    are text; the body of each `$( )` is a statement of its own."""
    cmd = no_heredocs(cmd)
    out, parts, cur, q, i = [], [], "", None, 0
    while i < len(cmd):
        c = cmd[i]
        if q:
            cur += c
            if c == "\\" and q == '"' and i + 1 < len(cmd):
                cur, i = cur + cmd[i + 1], i + 1
            elif c == q:
                q = None
        elif c == "\\" and i + 1 < len(cmd):
            cur, i = cur + c + cmd[i + 1], i + 1
        elif c in "'\"":
            q, cur = c, cur + c
        elif c == "|" and cmd[i + 1:i + 2] != "|":
            parts, cur = parts + [cur], ""
        elif c in ";\n" or cmd[i:i + 2] in ("&&", "||") or c == "&" and cmd[i - 1:i] not in "<>" and cmd[i + 1:i + 2] != ">":
            out, parts, cur = out + [parts + [cur]], [], ""
            i += cmd[i:i + 2] in ("&&", "||")
        else:
            cur += c
        i += 1
    out.append(parts + [cur])
    for body in SUBST.findall(cmd):
        out += statements(body)
    return [[p.strip() for p in st if p.strip()] for st in out if any(p.strip() for p in st)]


def words(part):
    """(words, fed): a part's words after the words that lead a command (and xargs: fed is True)."""
    try:
        w = shlex.split(part)
    except ValueError:
        w = part.split()
    fed = False
    while w and (w[0] in LEAD or w[0] in ("(", "{", "!") or re.match(r"^[A-Za-z_]\w*=", w[0])):
        if w[0] == "xargs":
            fed, w = True, w[1:]
            while w and w[0].startswith("-"):
                w = w[2:] if w[0] in ("-I", "-n", "-P", "-L", "-d", "-E") else w[1:]
        else:
            w = w[1:]
    return w, fed


def grep_args(w):
    """(pattern, files, flags) of a grep or rg word list: an option's value and a redirect are neither."""
    pat, files, flags, inc, i = None, [], set(), [], 1
    while i < len(w):
        a = w[i]
        if re.match(r"^(\d|&)?(>>?|<)", a):                 # 2>/dev/null, > out, 2> err
            i += 1 if re.search(r"[<>]&?\S", a) else 2
            continue
        if a in GREP_ARG or re.fullmatch(r"-[A-Za-z]*[efABCmgt]", a):
            if a in ("-e", "--regexp") or a.endswith("e") and not a.startswith("--"):
                pat = w[i + 1] if pat is None and i + 1 < len(w) else pat
            elif a in ("--include", "-g", "--glob", "-t", "--type") or a[-1:] in "gt" and not a.startswith("--"):
                inc.append(w[i + 1] if i + 1 < len(w) else "")
            flags.update(a.lstrip("-")[:-1] if not a.startswith("--") else [a])
            i += 2
            continue
        if a.startswith("-") and len(a) > 1:
            k, _, v = a.partition("=")
            if k in ("--include", "--glob", "--type"):
                inc.append(v)
            flags.update([k] if a.startswith("--") else a[1:])
        elif pat is None:
            pat = a
        else:
            files.append(a)
        i += 1
    return pat, files, flags | {"include:" + x for x in inc}


def place(path, here, ix):
    """'code', 'docs' (a doc or data file, a docs folder, or a path outside the repo and W: a scratch copy, a run
    folder, a tool's cache) or 'dir' (a folder or a glob) for a path a command names; None for no file."""
    if not path or path.startswith(">") or path in ("/dev/null", "-"):
        return None
    if here and not path.startswith(("/", "$", "~")):
        path = os.path.join(here, path)
    path = path.replace("${W}", "$W")
    ext = os.path.splitext(os.path.basename(path.rstrip("/*.")))[1].lower()
    outside = (path.startswith(("~", "$R", "${R}", "$SCR", "${SCR}", "$S/", "$HOME", "$TMPDIR"))
               or any(d in path for d in ("/.kiss/runs/", "/.kiss/scratch", "/tool-results/"))
               or path.startswith("/") and not any(path == r or path.startswith(r.rstrip("/") + "/") for r in (ix["repo"], ix["W"]) if r))
    if outside or ext in DOCS or re.search(r"(^|/)docs(/|$)", path) or os.path.basename(path) in ("README", "LICENSE", "CHANGELOG"):
        return "docs"
    return "code" if ext else "dir"


def symbol(pattern, ix):
    """True when one alternative of a search pattern, without its regex and keyword decoration, is one name the
    index holds (briefs.exists, the seed's lookup); each name is looked up once."""
    for alt in re.split(r"\\\||\|", pattern or ""):
        alt = DECOR.sub(" ", alt).strip().strip(".:")
        if re.fullmatch(r"[A-Za-z_$][\w$]*(?:(?:\.|::)[A-Za-z_$][\w$]*)*", alt or "-"):
            seen = ix.setdefault("seen", {})
            if alt not in seen:
                seen[alt] = ix["holds"](alt)
            if seen[alt]:
                return True
    return False


def call_kinds(tool, inp, ix, blocked=False):
    """The classes of one tool call for the CodeGraph share (v2): cg, seed (a seed script; CodeGraph too), symbol,
    literal, read (a code file of a type the index holds), pipe, docs, count, blocked. Other calls give none."""
    if blocked:
        return ["blocked"]
    if tool.startswith("mcp__codegraph__"):
        return ["cg"]
    search = lambda pat: "symbol" if symbol(pat, ix) else "literal"
    if tool == "Grep":
        g = inp.get("glob") or ""
        if inp.get("output_mode") == "count":
            return ["count"]
        if place(inp.get("path") or "", None, ix) == "docs" or g and place("x" + g.split("*")[-1].rstrip("}"), None, ix) == "docs":
            return ["docs"]
        return [search(inp.get("pattern"))]
    if tool == "Glob":
        return ["docs"] if place(inp.get("path") or "", None, ix) == "docs" else ["literal"]
    if tool == "Read":
        f = inp.get("file_path") or ""
        return ["read"] if place(f, None, ix) == "code" and os.path.splitext(f)[1].lower() in ix["exts"] else []
    if tool != "Bash":
        return []
    out, here = [], None
    for st in statements(inp.get("command") or ""):
        w0, _ = words(st[0])
        if w0[:1] == ["cd"] and len(st) == 1:
            here = w0[1] if len(w0) > 1 else "~"
            continue
        for i, part in enumerate(st):
            w, fed = words(part)
            if not w:
                continue
            first = os.path.basename(w[0])
            if first == "codegraph":
                sub = next((x for x in w[1:] if not x.startswith("-")), "")
                out += ["cg"] if sub in CG_READ else []
            elif first in ("cgcallers", "cgcallers.py") or first.startswith("python") and any(os.path.basename(x) in CG_SCRIPTS for x in w[1:]):
                out.append("seed" if any(os.path.basename(x) in SEEDS for x in w[1:]) else "cg")
            elif first in GREPS or first == "git" and w[1:2] == ["grep"]:
                pat, files, flags = grep_args(w[1:] if first == "git" else w)
                counting = "c" in flags or "--count" in flags or any(words(x)[0][:1] == ["wc"] for x in st[i + 1:])
                prev, _ = words(st[i - 1]) if i else ([], False)
                if i and not fed and not (prev and os.path.basename(prev[0]) in READERS
                                          and any(place(x, here, ix) == "code" for x in prev[1:])):
                    out.append("pipe")
                    continue
                kinds = {place(x, here, ix) for x in files} - {None}
                incs = {place("x" + x[8:].split("*")[-1], None, ix) for x in flags if x.startswith("include:")}
                if not kinds and here and place("x", here, ix) == "docs":
                    kinds = {"docs"}
                if kinds == {"docs"} or kinds <= {"dir"} and incs == {"docs"}:
                    out.append("docs")
                else:
                    out.append("count" if counting else search(pat))
            elif first == "find":
                roots = [x for x in w[1:] if not x.startswith("-")][:1]
                out.append("docs" if roots and place(roots[0], here, ix) == "docs" else "literal")
            elif first in READERS and not any(x.startswith((">", "-i")) for x in w[1:]):
                files = [x for x in w[1:] if not x.startswith("-") and os.path.splitext(x)[1].lower() in ix["exts"]]
                out += ["read"] if any(place(x, here, ix) == "code" for x in files) else []
    return out


def k(n):
    return f"{int(n / 1000 + 0.5)}k"


REFUSED = ("PreToolUse:", "The server-side auto mode classifier", "<tool_use_error>Blocked")


def blocked_ids(path):
    """The ids of the tool calls a PreToolUse hook or auto mode refused (they never ran): an error result that starts
    with one of REFUSED (a hook's result counts also with no is_error, as before)."""
    out = set()
    with open(path, errors="replace") as fh:
        for line in fh:
            if '"tool_result"' in line and any(x in line for x in REFUSED):
                try:
                    content = json.loads(line)["message"]["content"]
                except (ValueError, KeyError, TypeError):
                    continue
                for b in content if isinstance(content, list) else []:
                    c = b.get("content") if isinstance(b, dict) else None
                    text = c if isinstance(c, str) else " ".join(x.get("text", "") for x in c or [] if isinstance(x, dict))
                    text = text.lstrip()
                    if b.get("type") == "tool_result" and (text.startswith("PreToolUse:") or b.get("is_error") and text.startswith(REFUSED)):
                        out.add(b.get("tool_use_id"))
    return out


def index(R):
    """The CodeGraph index the share reads (W's, from R/run.json, when it has one, else the repo's): its file types
    and its name lookup; without one, the reason."""
    repo = R.split("/.kiss/runs/")[0] if "/.kiss/runs/" in R else os.path.dirname(os.path.dirname(R))
    try:
        with open(os.path.join(R, "run.json")) as f:
            W = json.load(f).get("W") or ""
    except (OSError, ValueError, AttributeError):
        W = ""
    root = next((d for d in (W, repo) if d and os.path.isdir(os.path.join(d, ".codegraph"))), None)
    try:
        listed = briefs.run("codegraph", "files", "-p", root, "--format", "flat", "--no-metadata").stdout if root else ""
    except (OSError, subprocess.TimeoutExpired):
        listed = ""
    exts = briefs.exts(listed.splitlines())
    if not exts:
        return {"why": f"no CodeGraph index for {repo}"}
    return {"repo": repo, "W": W, "exts": exts, "holds": lambda name: briefs.exists(root, name)}


def share(rows, ix):
    """The `CodeGraph share (v2)` part from the subagents' tool calls (calls.jsonl rows): CodeGraph / (CodeGraph +
    symbol searches + code reads), the rest apart."""
    if "why" in ix:
        return f"CodeGraph share (v2) n/a ({ix['why']})"
    c = {}
    for row in rows:
        for kind in call_kinds(row.get("tool", ""), row.get("input") or {}, ix, row.get("blocked")):
            c[kind] = c.get(kind, 0) + 1
    cg, sym, rd = c.get("cg", 0) + c.get("seed", 0), c.get("symbol", 0), c.get("read", 0)
    return (f"CodeGraph share (v2) {cg / (cg + sym + rd):.2f}" if cg + sym + rd else "CodeGraph share (v2) n/a") + (
        f" (CodeGraph {cg}, of it seed scripts {c.get('seed', 0)}; symbol searches {sym}; code reads {rd}; apart: "
        f"literal searches {c.get('literal', 0)}, greps after a pipe {c.get('pipe', 0)}, on docs or data "
        f"{c.get('docs', 0)}, counts {c.get('count', 0)}, blocked {c.get('blocked', 0)})")


def tokens(R, index=index):
    return measured(R, index)[0]


def measured(R, index=index):
    """(the token part of the metrics line, the subagents' tool calls as calls.jsonl rows), or (NA, None)."""
    R = os.path.abspath(R)
    subs = subagents(R)
    if not subs:
        return NA, None
    usage, tools, blocked = {}, {}, set()   # message id -> (role, usage); tool_use id -> (role, block): subagents only
    for f, r in subs:
        blocked |= blocked_ids(f)
        for m in messages(f):
            usage[m["id"]] = (r, m.get("usage") or {})
            for b in m.get("content") or []:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    tools.setdefault(b.get("id"), (r, b))
    rows = [{"role": r, "tool": b.get("name", ""), "blocked": i in blocked,
             "input": {x: v for x, v in (b.get("input") or {}).items() if x in KEEP}} for i, (r, b) in tools.items()]
    carries = False
    for session in {f.split(os.sep + "subagents" + os.sep)[0] + ".jsonl" for f, _ in subs}:
        if os.path.isfile(session):
            for m in messages(session, names(R)):
                usage.setdefault(m["id"], ("controller", m.get("usage") or {}))
            carries = carries or other_run(session, R)
    out = {"implementer": 0, "reviewers": 0, "controller": 0}
    inp = reads = hour = 0
    for r, u in usage.values():
        out[r] += u.get("output_tokens", 0)
        reads += u.get("cache_read_input_tokens", 0)
        inp += u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0) + u.get("cache_read_input_tokens", 0)
        hour += (u.get("cache_creation") or {}).get("ephemeral_1h_input_tokens", 0)
    ix = index(R) if callable(index) else index
    return (f"Tokens: output {k(sum(out.values()))} (implementer {k(out['implementer'])}, reviewers "
            f"{k(out['reviewers'])}, controller {k(out['controller'])}"
            f"{' (the session also carries another run)' if carries else ''}), input {k(inp)} "
            f"({round(100 * reads / inp) if inp else 0}% cache reads), 1-hour cache writes {k(hour)}; {share(rows, ix)}"), rows


def measure(R, index=index):
    """`metrics.py R`: the token part from the transcripts, else the v2 share from R/calls.jsonl, else a refusal."""
    R = os.path.abspath(R)
    line = tokens(R, index)
    if line != NA:
        return line
    path = os.path.join(R, "calls.jsonl")
    try:
        with open(path) as f:
            rows = [json.loads(x) for x in f if x.strip()]
    except (OSError, ValueError):
        sys.exit(f"metrics.py: no transcripts of {R} and no readable {path}: nothing to measure")
    return f"{share(rows, index(R) if callable(index) else index)}; from {path} (the tokens are in metrics.md)"


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
        lines.append(f"{r.rstrip('s')} {agent}: context {n}" + (f"; past {BOUND // 1000}k: start a new one at this boundary"
                                                                    if n > BOUND else ""))
    return "\n".join(lines)


def refusal(R):
    """Why --record must not write (D9), or "": the last `Full check at <sha>: <result>` line of R/decisions.md must
    be a pass, at W's HEAD (its full sha or a prefix of 7 or more characters); W comes from R/run.json."""
    try:
        with open(os.path.join(R, "run.json")) as f:
            W = json.load(f)["W"]
    except (OSError, KeyError, ValueError, TypeError):
        return f"no W in {R}/run.json"
    try:
        with open(os.path.join(R, "decisions.md")) as f:
            checks = re.findall(r"^\W*Full check at `?([0-9a-fA-F]+)`?: *(.*)$", f.read(), re.M)
    except OSError:
        checks = []
    if not checks:
        return f"no `Full check at <sha>: <result>` line in {R}/decisions.md: run the full check at HEAD first"
    sha, result = checks[-1]
    if not re.match(r"pass(ed)?\b", result, re.I):
        return f"the last full check in {R}/decisions.md did not pass: {result}"
    head = subprocess.run(["git", "-C", W, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    if len(sha) < 7 or not head or not head.startswith(sha.lower()):
        return f"the last full check in {R}/decisions.md ran at {sha}, not at W's HEAD {head or '(none)'}: run it at HEAD"
    return ""


def record(R, line):
    """Print the full line, then put it in R's runs folder's metrics.md: a rerun replaces its line in place, a new
    run's line goes at the end, every other line stays. The book is replaced whole, so a failed write keeps it.
    Refused, before any write, without a passed full check at W's HEAD (refusal)."""
    R = os.path.abspath(R)
    why = refusal(R)
    if why:
        sys.exit(f"metrics.py --record refused: {why}")
    part, calls = measured(R)
    full = re.sub(r"[\r\n]", " ", f"{line}; {part}")
    print(full)
    if calls is not None:                     # no transcripts: an earlier calls.jsonl stays
        whole(os.path.join(R, "calls.jsonl"), "".join(json.dumps(c) + "\n" for c in calls))
    book = os.path.join(os.path.dirname(R), "metrics.md")
    mine = f"- {os.path.basename(R)}: "
    try:
        with open(book) as f:
            rows = f.read().splitlines()
    except FileNotFoundError:
        rows = []
    at = next((i for i, x in enumerate(rows) if x.startswith(mine)), len(rows))
    rows[at:at + 1] = [mine + full]
    whole(book, "\n".join(rows) + "\n")
    return full


def whole(path, text):
    """Replace a file whole: a temporary file and a rename, so a failed write keeps the old file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        with open(tmp, "w") as f:
            f.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def selftest():
    import tempfile
    global FAKE
    FAKE = {"repo": "/w", "W": "/w", "exts": {".py"}, "holds": {"read", "build", "Lsp.read"}.__contains__}

    def user(text, ts="2026-01-01T09:00:00.000Z"):
        return {"type": "user", "timestamp": ts, "message": {"role": "user", "content": text}}

    def said(mid, out, inp, write, read, hour=0, tools=()):
        return {"type": "assistant", "message": {"id": mid, "role": "assistant", "content": [
            {"type": "tool_use", "id": f"{mid}-{n}", "name": t, "input": c if isinstance(c, dict) else {"command": c} if c else {}}
            for n, (t, c) in enumerate(tools)], "usage": {
            "input_tokens": inp, "output_tokens": out, "cache_creation_input_tokens": write,
            "cache_read_input_tokens": read,
            "cache_creation": {"ephemeral_1h_input_tokens": hour, "ephemeral_5m_input_tokens": write - hour}}}}

    def put(path, rows, kind=None, tid=None):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write("".join(json.dumps(r) + "\n" for r in rows))
        if kind:
            with open(path[:-len(".jsonl")] + ".meta.json", "w") as f:
                json.dump({"agentType": kind, "toolUseId": tid}, f)

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
                                               ("Grep", None), ("Bash", 'grep -n "def read" app.py'),
                                               ("Read", {"file_path": "/w/app.py"}), ("Read", {"file_path": "/w/notes.md"}),
                                               ("Bash", 'grep -rn "def build" src'), ("Bash", 'python3 -I "/h/briefs.py" R /w br T-1')]),
            {"type": "user", "message": {"role": "user", "content": [                 # a hook blocked m2-6: it never ran
                {"type": "tool_result", "tool_use_id": "m2-6", "content": "PreToolUse:Bash hook error: use codegraph"}]}}],
            "kiss:kiss-implementer", "c-1")
        put(os.path.join(S, "subagents", "agent-a2.jsonl"), [
            user(f"You are the reviewer of {R}/tickets.json"),
            said("m3", 1400, 100, 1000, 2000, tools=[("Bash", "python3 -I /h/cgcallers.py f -p /w | grep lsp")])],
            "kiss:kiss-reviewer", "c-2")
        put(os.path.join(S, "subagents", "agent-a3.jsonl"), [               # its prompt names another run: left out
            user("You are the implementer. R = /x/runs/r7-old"), user(f"later it reads {R}"),
            said("m4", 9000, 9000, 0, 0, tools=[("Grep", None)])],
            "kiss:kiss-implementer", "c-9")
        put(os.path.join(S, "subagents", "agent-a4.jsonl"), [               # its own run first, R later: left out
            user(f"You review /x/runs/r8; one input is {R}/review-1.md"), said("m10", 5000, 5000, 0, 0)],
            "kiss:kiss-reviewer")
        agent = ("Agent", {"prompt": "go"})          # the controller session: it ran `prompt.py start` on R, then 4 Agent calls
        put(S + ".jsonl", [said("m0", 7000, 7000, 0, 0), user(f"start the run in {R}", "2026-01-01T10:00:00.000Z"),   # m0: before R
                           said("c", 0, 0, 0, 0, tools=[("Bash", f'R={R}; python3 -I "$HB/scripts/prompt.py" start "$R" W=/w'),
                                                        agent, agent, agent, agent]),
                           said("m5", 600, 1, 500, 4000, tools=[("Grep", None)]),
                           said("c2", 0, 0, 0, 0, tools=[("Bash", f'python3 -I /h/metrics.py {R} --record "Metrics: x"'), agent])])
        late = said("m12", 0, 0, 0, 0, tools=[("Grep", {"pattern": "read"})] * 9)
        put(os.path.join(S, "subagents", "agent-a10.jsonl"), [user(f"Audit {R}"), late], "kiss:kiss-reviewer", "c2-1")   # after the record
        put(os.path.join(S, "subagents", "agent-a9.jsonl"), [user(f"You are the reviewer of {R}"), late], "kiss:kiss-reviewer", "zz-1")  # no Agent call
        S3 = os.path.join(C, "projects", "-y", "s3")                       # another run's start ends the window
        put(S3 + ".jsonl", [said("p", 0, 0, 0, 0, tools=[("Bash", "cd /y && python3 -I /h/prompt.py start /y/.kiss/runs/q1 W=/y"), agent,
                                                         ("Bash", "cat > /y/n.md <<'EOF'\nprompt.py start /y/.kiss/runs/q2\nEOF"), agent,
                                                         ("Bash", "python3 -I /h/prompt.py start /y/.kiss/runs/q2 W=/y"), agent])])
        assert agent_calls(S3 + ".jsonl", "q1") == {"p-1", "p-3"} and agent_calls(S3 + ".jsonl", "q2") == {"p-5"}, "a heredoc's text starts no run"
        assert agent_calls(S3 + ".jsonl", "q3") == set()
        S2 = os.path.join(C, "projects", "-x", "s2")                       # another session whose agent names R: the 1.00 case
        put(S2 + ".jsonl", [said("d", 0, 0, 0, 0, tools=[agent])])
        put(os.path.join(S2, "subagents", "agent-a7.jsonl"), [user(f"You are the implementer. R = {R}"), late], "kiss:kiss-implementer", "d-0")
        # worked example: output 1200+800, 1400, 600 = 4000; input 2010+3005+3100+4501 = 12616, reads 9000 = 71%;
        # 1-hour writes 2000; CodeGraph 4 (codegraph explore, MCP explore, cgcallers, briefs.py: 1 seed script),
        # symbol searches 1 (def read), code reads 1 (app.py, not notes.md); apart: literal 2 (grep -rn x, an empty
        # Grep), 2 greps after a pipe, 1 blocked (def build); share 4 / (4 + 1 + 1); the controller's Grep is not counted
        want = ("Tokens: output 4k (implementer 2k, reviewers 1k, controller 1k), input 13k (71% cache reads), "
                "1-hour cache writes 2k; CodeGraph share (v2) 0.67 (CodeGraph 4, of it seed scripts 1; symbol searches 1; "
                "code reads 1; apart: literal searches 2, greps after a pipe 2, on docs or data 0, counts 0, blocked 1)")
        assert tokens(R) == want.split("; CodeGraph share")[0] + "; CodeGraph share (v2) n/a (no CodeGraph index for /x)", tokens(R)
        got = tokens(R, index=FAKE)
        assert got == want, got
        assert tokens(R + "/", index=FAKE) == want, "a trailing slash names the same run"
        with open(S + ".jsonl", "a") as f:                       # it only names run r8's folder (a review input)
            f.write(json.dumps(user("read /x/runs/r8/review-1.md", "2026-01-01T11:00:00.000Z")) + "\n")
        assert tokens(R, index=FAKE) == want, "a name of another run's folder is not its work"
        put(os.path.join(S, "subagents", "agent-a8.jsonl"), [               # run r8's agent, started in R's window
            user("You are the implementer. R = /x/runs/r8", "2026-01-01T11:00:01.000Z")], "kiss:kiss-implementer")
        assert tokens(R, index=FAKE) == want.replace("controller 1k", "controller 1k (the session also carries another run)"), tokens(R, index=FAKE)
        os.remove(os.path.join(S, "subagents", "agent-a8.jsonl"))
        assert tokens("/x/runs/none") == NA
        assert context("/x/runs/none") == NA
        put(os.path.join(S, "subagents", "agent-a5.jsonl"), [
            user(f"You are the implementer. R = {R}"), said("m6", 1, 1, 0, 399_999), said("m7", 1, 1, 1000, 349_999)],
            "kiss:kiss-implementer", "c-3")
        put(os.path.join(S, "subagents", "agent-a6.jsonl"), [
            user(f"You are the reviewer of {R}"), said("m8", 1, 1, 0, 500_000), said("m9", 1, 2, 998, 348_000)],
            "kiss:kiss-reviewer", "c-4")
        # a1's last request 5 + 0 + 3000; a2's 100 + 1000 + 2000; a5's 351,000 is past the bound; a6's 349,000 is
        # not, though its earlier request was larger
        assert context(R).splitlines() == [
            "implementer a1: context 3005", "reviewer a2: context 3100",
            "implementer a5: context 351000; past 350k: start a new one at this boundary",
            "reviewer a6: context 349000"], context(R)
        global BOUND
        BOUND, keep = 3_000, BOUND                                          # the mark's number is the bound's
        assert context(R).splitlines()[1] == "reviewer a2: context 3100; past 3k: start a new one at this boundary", context(R)
        BOUND = keep
        S4 = os.path.join(C, "projects", "-x", "s4")                       # the run resumed in a second session (D16)
        put(S4 + ".jsonl", [said("f", 0, 0, 0, 0, tools=[("Bash", f'python3 -I /h/prompt.py fix "{R}" ROUND=1 ELAPSED=9'), agent])])
        put(os.path.join(S4, "subagents", "agent-a11.jsonl"), [user("Read progress.md first"), said("m13", 1, 1, 0, 0)], "kiss:kiss-implementer", "f-1")
        assert sorted(os.path.basename(f) for f, _ in subagents(R)) == [f"agent-a{n}.jsonl" for n in (1, 11, 2, 5, 6)], subagents(R)
        os.remove(os.path.join(S4, "subagents", "agent-a11.jsonl"))
    bash = lambda cmd, done=False: call_kinds("Bash", {"command": cmd}, FAKE, done)
    for cmd, want in (('grep -n "a\\|b" notes.md', ["docs"]), ('grep -rn "two words" docs/', ["docs"]),
                      ("grep -n foo app.py 2>/dev/null", ["literal"]), ("grep -A 3 foo app.py", ["literal"]),
                      ('grep -n "def read" app.py', ["symbol"]), ("grep -rn 'Lsp.read(' src", ["symbol"]),
                      ('grep -n "color: red" app.css', ["literal"]), ("grep -c read app.py", ["count"]),
                      ("grep -rn read src | wc -l", ["count"]), ("pytest -q | grep -n read", ["pipe"]),
                      ("cat app.py | grep -n read", ["read", "symbol"]), ("x=$(grep -rln read src); echo $x", ["symbol"]),
                      ("grep -rn read /s/copy/app.py", ["docs"]), ("cd /s/copy && grep -rn read src", ["docs"]),
                      ("cd /w && grep -rn read src", ["symbol"]), ("find . -name x", ["literal"]),
                      ('python3 -I "/h/x/briefs.py" "/r" "/w" b T-1', ["seed"]), ("python3 -I /h/callcheck.py -p /w --cached", ["seed"]),
                      ("cgcallers read -p /w", ["cg"]), ("rtk codegraph node -p /w read", ["cg"]), ("codegraph sync -q /w", []),
                      ("cat app.py", ["read"]), ("sed -n 1,9p app.py", ["read"]), ("head -5 notes.md", []),
                      ("cat > app.py <<'EOF'\ngrep -rn read src\ncodegraph explore a\nEOF", []),
                      ("python3 - <<EOF | grep ok\ngrep x y\nEOF\ngrep -rn read src", ["pipe", "symbol"]),
                      ("echo $((1<<N))\ngrep -rn read src", ["symbol"]), ("for f in *.py; do grep -n read \"$f\"; done", ["symbol"]),
                      ("grep -e read -e build x.json y.md", ["docs"]), ("grep --include=*.md -rn read .", ["docs"])):
        assert bash(cmd) == want, (cmd, bash(cmd))
    assert bash("grep -rn 'def read' src", True) == ["blocked"], "a call a hook blocked never ran"
    with tempfile.TemporaryDirectory() as t:                # D7: each refused form is blocked; a plain result is not
        res = lambda i, text, err=True: {"type": "tool_result", "tool_use_id": i, "content": text, **({"is_error": True} if err else {})}
        rows = [res("h", "PreToolUse:Bash hook error: no"), res("a", "The server-side auto mode classifier gave no verdict"),
                res("s", "<tool_use_error>Blocked: sleep 30 is not allowed</tool_use_error>"),
                res("ok", "The server-side auto mode classifier", False), res("out", "<tool_use_error>Blocked: x", False),
                res("err", "<tool_use_error>File does not exist.</tool_use_error>")]
        with open(os.path.join(t, "a.jsonl"), "w") as fh:
            fh.write(json.dumps({"type": "user", "message": {"role": "user", "content": rows}}) + "\n")
        assert blocked_ids(os.path.join(t, "a.jsonl")) == {"h", "a", "s"}, blocked_ids(os.path.join(t, "a.jsonl"))
    for argv, want in ((["grep", "-n", "foo", "app.py", "2>/dev/null"], ("foo", ["app.py"])), (["grep", "-A", "3", "foo", "app.py"], ("foo", ["app.py"])),
                       (["grep", "-e", "a", "-e", "b", "x"], ("a", ["x"])), (["grep", "-rn", "--include=*.py", "f", "."], ("f", ["."]))):
        assert grep_args(argv)[:2] == want, (argv, grep_args(argv))
    for tool, inp, want in (("Read", {"file_path": "/w/app.py"}, ["read"]), ("Read", {"file_path": "/w/notes.md"}, []),
                            ("Read", {"file_path": "/s/copy/app.py"}, []), ("Glob", {"pattern": "**/*.py"}, ["literal"]),
                            ("Grep", {"pattern": "def read", "path": "/w/src"}, ["symbol"]), ("Grep", {"pattern": "x", "glob": "*.md"}, ["docs"]),
                            ("Grep", {"pattern": "read", "output_mode": "count"}, ["count"]), ("mcp__codegraph__codegraph_explore", {}, ["cg"])):
        assert call_kinds(tool, inp, FAKE) == want, (tool, inp, call_kinds(tool, inp, FAKE))
    import contextlib, io
    with tempfile.TemporaryDirectory() as t, contextlib.redirect_stdout(io.StringIO()):   # the metrics record
        os.environ["CLAUDE_CONFIG_DIR"] = os.path.join(t, "no-config")
        W = os.path.join(t, "my work tree")                                 # a scratch git repo: two commits
        os.makedirs(W)
        g = lambda *a: subprocess.run(["git", "-C", W, *a], capture_output=True, text=True, check=True).stdout.strip()
        g("init", "-q"), g("config", "user.name", "t"), g("config", "user.email", "t@example.com")
        g("commit", "-q", "--allow-empty", "-m", "one")
        old = g("rev-parse", "HEAD")
        g("commit", "-q", "--allow-empty", "-m", "two")
        head = g("rev-parse", "HEAD")

        def run_folder(path, decisions, w=W):
            os.makedirs(path, exist_ok=True)
            with open(os.path.join(path, "run.json"), "w") as f:
                json.dump({"W": w}, f)
            with open(os.path.join(path, "decisions.md"), "w") as f:
                f.write(decisions)
            return path
        a, b, c = (run_folder(os.path.join(t, "repo", ".kiss", "runs", n), f"# D\n\nFull check at {head}: pass\n")
                   for n in ("2026-01-02-a", "2026-01-03-b", "2026-01-01-c"))
        book = os.path.join(t, "repo", ".kiss", "runs", "metrics.md")      # beside the run folders (R1)
        assert record(b, "Metrics: subagents 2") == "Metrics: subagents 2; " + NA
        record(a, "Metrics: subagents 3")
        record(c, "Metrics: subagents\r\n5")                              # R3: one line; R4: a new run at the end
        assert open(book).read() == ("- 2026-01-03-b: Metrics: subagents 2; " + NA + "\n"
                                     "- 2026-01-02-a: Metrics: subagents 3; " + NA + "\n"
                                     "- 2026-01-01-c: Metrics: subagents  5; " + NA + "\n"), open(book).read()
        record(a, "Metrics: subagents 4")                                    # a rerun replaces its line in place
        assert open(book).read().splitlines()[1] == "- 2026-01-02-a: Metrics: subagents 4; " + NA, open(book).read()
        os.chmod(os.path.dirname(book), 0o500)                              # R2: a write error keeps the old lines
        try:
            record(a, "Metrics: subagents 9")
            raise AssertionError("a write to a read-only folder must fail")
        except OSError:
            pass
        finally:
            os.chmod(os.path.dirname(book), 0o700)
        assert len(open(book).read().splitlines()) == 3 and not glob.glob(book + ".*"), open(book).read()
        d = os.path.join(t, "repo", ".kiss", "runs", "2026-01-04-d")       # D9: the full check at HEAD, else a refusal
        os.makedirs(d)
        kept = open(book).read()
        for decisions, why in ((None, "run.json"), ("# D\n\nD1. x\n", "Full check at"),
                               (f"Full check at {head}: fail (2 tests)\n", "did not pass"),
                               (f"Full check at {head}: passes 3 of 4\n", "did not pass"), (f"Full check at {head}:\n", "did not pass"),
                               (f"Full check at {head}: pass\nFull check at {head[:7]}: fail\n", "did not pass"),
                               (f"Full check at {old}: pass\n", "HEAD"), (f"Full check at {old[:7]}: pass\n", "HEAD"),
                               (f"Full check at {head[:6]}: pass\n", "HEAD")):
            if decisions is not None:
                run_folder(d, decisions)
            try:
                record(d, "Metrics: subagents 1")
                raise AssertionError(f"must refuse: {decisions}")
            except SystemExit as x:
                assert x.code and why in str(x.code) and d in str(x.code), (decisions, x.code)
            assert open(book).read() == kept, decisions
        run_folder(d, "", w=os.path.join(t, "no such tree"))
        with open(os.path.join(d, "decisions.md"), "w") as f:
            f.write(f"Full check at {head}: pass\n")
        try:
            record(d, "Metrics: subagents 1")
            raise AssertionError("a W that is not a git repo must refuse")
        except SystemExit as x:
            assert "HEAD" in str(x.code), x.code
        for decisions in (f"Full check at {old}: fail\nFull check at {head[:7]}: pass\n", f"Full check at `{head}`: passed\n"):
            run_folder(d, decisions)
            assert record(d, "Metrics: subagents 1").startswith("Metrics: subagents 1;"), decisions
        assert open(book).read().splitlines()[3].startswith("- 2026-01-04-d: Metrics: subagents 1;"), open(book).read()
        assert not glob.glob(os.path.join(t, "repo", ".kiss", "runs", "*", "calls.jsonl")), "no transcripts: no calls.jsonl"
        C2 = os.path.join(t, "config")                                      # D8: --record saves each subagent tool call
        os.environ["CLAUDE_CONFIG_DIR"] = C2
        e = run_folder(os.path.join(t, "repo", ".kiss", "runs", "2026-01-05-e"), f"Full check at {head}: pass\n")
        S9 = os.path.join(C2, "projects", "-r", "s9")
        put(S9 + ".jsonl", [said("k", 1, 1, 0, 0, tools=[("Bash", f'python3 -I "/h/prompt.py" start "{e}" W=x'), ("Agent", {"prompt": "go"})])])
        b1 = os.path.join(S9, "subagents", "agent-b1.jsonl")
        tools = [("Bash", "grep -rn read src"), ("Read", {"file_path": "/w/app.py", "limit": 5}), ("Bash", "grep -rn 'def build' src"),
                 ("mcp__codegraph__codegraph_node", {"symbol": "read"}), ("Edit", {"file_path": "/w/app.py", "old_string": "a", "new_string": "b"})]
        put(b1, [user("go"), said("b", 1, 1, 0, 0, tools=tools), {"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "b-2", "content": "PreToolUse:Bash hook error: no"}]}}], "kiss:kiss-implementer", "k-1")
        calls = os.path.join(e, "calls.jsonl")
        record(e, "Metrics: subagents 1")
        rows = [json.loads(x) for x in open(calls)]
        assert rows == [{"role": "implementer", "tool": "Bash", "input": {"command": "grep -rn read src"}, "blocked": False},
                        {"role": "implementer", "tool": "Read", "input": {"file_path": "/w/app.py"}, "blocked": False},
                        {"role": "implementer", "tool": "Bash", "input": {"command": "grep -rn 'def build' src"}, "blocked": True},
                        {"role": "implementer", "tool": "mcp__codegraph__codegraph_node", "input": {}, "blocked": False},
                        {"role": "implementer", "tool": "Edit", "input": {"file_path": "/w/app.py"}, "blocked": False}], rows
        live = "CodeGraph share" + measure(e, index=FAKE).split("; CodeGraph share")[1]
        assert live == "CodeGraph share (v2) 0.33 (CodeGraph 1, of it seed scripts 0; symbol searches 1; code reads 1; apart: literal searches 0, greps after a pipe 0, on docs or data 0, counts 0, blocked 1)", live
        os.rename(C2, C2 + "-gone")                                         # the transcripts are gone: calls.jsonl measures
        assert measure(e, index=FAKE) == live + f"; from {calls} (the tokens are in metrics.md)", measure(e, index=FAKE)
        for gone in (b, d):                                                 # neither: refused, naming R
            try:
                measure(gone, index=FAKE)
                raise AssertionError(f"must refuse: {gone}")
            except SystemExit as x:
                assert x.code and gone in str(x.code), x.code
        os.rename(C2 + "-gone", C2)
        put(b1, [user("go"), said("b", 1, 1, 0, 0, tools=tools[:1])], "kiss:kiss-implementer", "k-1")
        record(e, "Metrics: subagents 1")                                   # a rerun replaces calls.jsonl whole
        assert len(open(calls).read().splitlines()) == 1, open(calls).read()
        put(b1, [user("go"), said("b", 1, 1, 0, 0, tools=tools[:2])], "kiss:kiss-implementer", "k-1")
        kept = open(book).read()
        os.rename(book, book + "-kept")                                     # the second write fails after the first:
        os.mkdir(book)                                                      # a folder where metrics.md goes (also as root)
        try:
            record(e, "Metrics: subagents 2")
            raise AssertionError("a write over a folder must fail")
        except OSError:
            pass
        finally:
            os.rmdir(book)
            os.rename(book + "-kept", book)
        assert len(open(calls).read().splitlines()) == 2 and open(book).read() == kept, "the first new, the second old and whole"
        record(e, "Metrics: subagents 2")                                   # a rerun makes both new
        assert len(open(calls).read().splitlines()) == 2 and "- 2026-01-05-e: Metrics: subagents 2;" in open(book).read()
        assert not glob.glob(os.path.join(os.path.dirname(book), "**", "*.tmp"), recursive=True)
    print("metrics selftest ok")


def main(argv):
    if argv[1:] == ["--selftest"]:
        return selftest()
    if len(argv) == 3 and argv[2] == "--context":
        return print(context(argv[1]))
    if len(argv) == 4 and argv[2] == "--record":
        return record(argv[1], argv[3])
    if len(argv) != 2:
        sys.exit(__doc__)
    print(measure(argv[1]))


if __name__ == "__main__":
    main(sys.argv)
