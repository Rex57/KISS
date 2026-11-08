#!/usr/bin/env python3
"""Check this device for a KISS run (kiss-doctor/SKILL.md). Reads only, except `feedback on|off claude`, which
sets env.KISS_FEEDBACK in Claude Code's user settings.

  python3 -I doctor.py [AGENT ...]    AGENT: claude, codex, gemini, antigravity (default: each one whose CLI is on PATH)
  python3 -I doctor.py feedback on|off <claude|codex|gemini|antigravity>   claude: set env.KISS_FEEDBACK in Claude Code's
                                         user settings ("1" or "0"), with a backup; the others: change no file, and
                                         print what to add by hand
  python3 -I doctor.py setup [AGENT ...]   the numbered plan of what is missing, from the install table (installs
                                         nothing); AGENT: only those agents on PATH (default: each one on PATH)
  python3 -I doctor.py setup [AGENT ...] --apply all|none|1,3 --plan <id>   run those items of the plan with that id,
                                         one at a time (a changed plan is refused); stop at the first failure;
                                         then the checks again (an agent whose items the answer skipped left out)
                                         and the steps by hand. Never sudo, never a shell profile.
  python3 -I doctor.py --selftest

Each line: OK, INFO, WARN or FAIL, the agent, what was checked, and for a WARN or FAIL the README section with the fix.
Exit 1 when a line is FAIL.

The required skills come from the table in kiss-harness/SKILL.md, the rule's markers from the bold lead-ins of
rules/codegraph.md, so neither list is kept here.
"""
import glob, hashlib, json, os, platform, re, shlex, shutil, subprocess, sys, time

KISS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
HOME = os.path.expanduser("~")
CLI = {"claude": "claude", "codex": "codex", "gemini": "gemini", "antigravity": "agy"}
FILE_BREAK = "\n\f\n"                                   # between two files of Claude Code's joined text: check_rule reads each on its own


def read(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def required(kiss=KISS):
    """{skill: README section with its install}: KISS's own skills and the external ones of each KISS skill's table."""
    out = {d: "Install KISS" for d in sorted(os.listdir(os.path.join(kiss, "skills")))}
    for d in sorted(out):
        path = os.path.join(kiss, "skills", d, "SKILL.md")
        text = read(path) if os.path.isfile(path) else ""
        for table in re.findall(r"^\| Skill \| From \|.*\n\|[-| ]+\|\n((?:\|.*\n?)*)", text, re.M):
            for name, source in re.findall(r"^\| `([a-z0-9-]+)` \| ([^|]+?) \|", table, re.M):
                out.setdefault(name, "Install " + source)
    return out


def markers(kiss=KISS):
    return [m.rstrip(":.") for m in re.findall(r"^\*\*(.+?)\*\*", read(os.path.join(kiss, "rules", "codegraph.md")), re.M)]


def with_imports(path, depth=4, seen=None):
    """The file's text plus every `@file` it imports (Claude Code's CLAUDE.md syntax, 4 hops deep)."""
    seen = {} if seen is None else seen                 # the files read, in order
    path = os.path.realpath(os.path.expanduser(path))
    if path in seen or not os.path.isfile(path):
        return ""
    seen[path] = True
    text = read(path)
    if depth:
        for ref in re.findall(r"(?:^|\s)@(\S+)", text):
            ref = os.path.join(os.path.dirname(path), os.path.expanduser(ref))
            if os.path.isfile(ref):
                text += FILE_BREAK + with_imports(ref, depth - 1, seen)
    return text


def frontmatter(path):
    m = re.match(r"---\r?\n(.*?)\r?\n---", read(path), re.S)
    return dict(re.findall(r"^([\w-]+):[ \t]*(.*?)[ \t]*$", m.group(1), re.M)) if m else {}


def skills_in(root):
    """{skill name: SKILL.md path} under one root; a root counts once per name."""
    found = {}
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if not x.startswith(".") and x != "node_modules"]
        if "SKILL.md" in files:
            path = os.path.join(d, "SKILL.md")
            found.setdefault(frontmatter(path).get("name") or os.path.basename(d), path)
    return found


def codex_enabled(config):
    """Plugin ids with `enabled = true` in Codex's config.toml."""
    return [m.group(1) for m in re.finditer(r'^\[plugins\."([^"]+)"\][ \t]*$((?:\n(?!\[).*)*)', config, re.M)
            if re.search(r"^\s*enabled\s*=\s*true\b", m.group(2), re.M)]


def run(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=120).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def agent_setup(agent):
    """(the global instructions text, the files it came from, [(label, skill root)], a note when roots may be missing)."""
    gemini = os.path.join(HOME, ".gemini")
    shared = [("~/.agents/skills", os.path.join(HOME, ".agents", "skills"))]
    if agent == "claude":
        home = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(HOME, ".claude")
        roots = [(p["id"], p["installPath"]) for p in json.loads(run(["claude", "plugin", "list", "--json"]) or "[]")
                 if p.get("enabled") and p.get("installPath")]
        files = [os.path.join(home, "CLAUDE.md")] + sorted(glob.glob(os.path.join(glob.escape(home), "rules", "**", "*.md"), recursive=True))
        return FILE_BREAK.join(with_imports(f) for f in files), files, roots + [("~/.claude/skills", os.path.join(home, "skills"))], ""
    if agent == "codex":
        home = os.environ.get("CODEX_HOME") or os.path.join(HOME, ".codex")
        cfg = os.path.join(home, "config.toml")
        roots = []
        for pid in codex_enabled(read(cfg) if os.path.isfile(cfg) else ""):
            name, _, market = pid.partition("@")
            versions = sorted(glob.glob(os.path.join(glob.escape(home), "plugins", "cache", market, name, "*")), key=os.path.getmtime)
            roots += [(pid, versions[-1])] if versions else []
        override = os.path.join(home, "AGENTS.override.md")
        files = [override if os.path.isfile(override) else os.path.join(home, "AGENTS.md")]
        return with_imports(files[0], 0), files, roots + shared, ""
    if agent == "gemini":
        files = [os.path.join(gemini, "GEMINI.md")]
        roots = [(os.path.basename(e), e) for e in sorted(glob.glob(os.path.join(gemini, "extensions", "*", "")))]
        return with_imports(files[0], 0), files, roots + [("~/.gemini/skills", os.path.join(gemini, "skills"))] + shared, ""
    files = [os.path.join(gemini, "GEMINI.md"), os.path.join(gemini, "AGENTS.md")] + sorted(
        glob.glob(os.path.join(gemini, "config", "rules", "*.md")))
    roots = [("~/.gemini/config/skills", os.path.join(gemini, "config", "skills")),
             ("~/.gemini/antigravity-cli/skills", os.path.join(gemini, "antigravity-cli", "skills"))] + shared
    note = "; plugin folders are not known to this script: check your skill list"
    return "\n".join(with_imports(f, 0) for f in files), files, roots, note


def unfenced(text):
    """Each line of `text` outside a ``` or ~~~ fence, as a match with its offset; a fence's own lines are left out."""
    fence = None
    for line in re.finditer(r"^.*$", text, re.M):
        mark = re.match(r"\s*(```|~~~)", line.group())
        if mark and fence in (None, mark.group(1)):
            fence = None if fence else mark.group(1)
        elif fence is None:
            yield line


def section_end(text, at, level=2):
    """Where the rule's section that holds `at` ends: the next heading of `level` or less (rule_span gives the level)
    or the CODEGRAPH_START line of `codegraph install`'s block, out of fences; else the end."""
    return next((line.start() for line in unfenced(text)
                 if line.start() > at and re.match(r"#{1,%d} |\W*CODEGRAPH_START\W*$" % level, line.group())), len(text))


def section(text, first):
    """The rule's words in a text: from its first bold lead-in to the next heading of any level (an owner's own `###`
    after an exact copy is not compared) or the CODEGRAPH_START line, out of fences, whitespace collapsed."""
    at = text.find("**" + first)
    return " ".join(text[at:section_end(text, at, 6)].split()) if at >= 0 else ""


def holds(text, marks):
    """Claude Code: one file holds the rule only with more than half of its bold lead-ins: an owner's own bold word is no copy."""
    return 2 * sum("**" + m in text for m in marks) > len(marks)


def differs(text, marks, rule):
    """A holder file that lacks a bold lead-in, or whose own section is not KISS's rule text (when one is given)."""
    return any("**" + m not in text for m in marks) or bool(rule) and section(text, marks[0]) != section(rule, marks[0])


def check_rule(agent, text, files, marks, rule=""):
    """The rule in an agent's instructions: every lead-in is OK, unless KISS's rule text is given and the copy differs. Claude
    Code's rules/ folder holds the owner's own files too, so its files are read one by one: OK when no holder differs."""
    shown = " or ".join(f.replace(HOME, "~") for f in files)
    if agent == "claude":
        found = [part for part in text.split(FILE_BREAK) if holds(part, marks)]
        stale = next((part for part in found if differs(part, marks, rule)), None)
        lacks = [m for m in marks if "**" + m not in stale] if stale else []
        named = rule_file(files, marks, 4, rule)
    else:                                               # D14: the other agents keep the read of the whole text
        found = [m for m in marks if m in text]
        lacks = [m for m in marks if m not in found]
        stale = lacks or rule and section(text, marks[0]) != section(rule, marks[0])
        named = rule_file(files, marks, 0)
    named = (named or shown).replace(HOME, "~")
    if not text:
        out = [("FAIL", agent, f"CodeGraph rule: no {shown}", "The CodeGraph rule")]
    elif not found:
        out = [("FAIL", agent, f"CodeGraph rule: not in {shown}", "The CodeGraph rule")]
    elif not stale:
        out = [("OK", agent, f"CodeGraph rule in {shown}", "")]
    elif lacks:
        out = [("WARN", agent, f"CodeGraph rule in {named} is an older or edited copy: lacks {', '.join(lacks)}: run kiss-doctor setup", "The CodeGraph rule")]
    else:
        out = [("WARN", agent, f"CodeGraph rule in {named} differs from KISS's text: run kiss-doctor setup", "The CodeGraph rule")]
    if re.search(r"^\W*CODEGRAPH_START\W*$", text, re.M):  # the marker line, not the rule's own mention of it
        out.append(("WARN", agent, "a CODEGRAPH_START block from `codegraph install`: delete it", "The CodeGraph rule"))
    return out


def rule_span(text, marks):
    """The rule's section in a text, (start, end): from the nearest heading above its first bold lead-in (the first in
    the rule's order that the text holds, as section() reads it) to section_end at that heading's level, at least `##`
    (a `# ` heading's `##` are the owner's). A line inside a fence is no heading. It
    starts at the lead-in's line when that heading is the file's first and a `# ` one (its title: D23, D25), or when a
    CODEGRAPH_END line comes after it (codegraph install's block stays whole); start is None when no heading is above.
    None when the text holds no lead-in."""
    first = next(("**" + m for m in marks if "**" + m in text), None)
    if first is None:
        return None
    at = text.find(first)
    above = [line for line in unfenced(text) if line.start() <= at and re.match(r"#{1,6} |\W*CODEGRAPH_END\W*$", line.group())]
    heads = [line for line in above if line.group().startswith("#")]
    if not heads:
        return None, section_end(text, at)
    title = above[-1] is heads[0] and above[-1].group().startswith("# ")
    own = above[-1].group()
    level = max(2, len(own) - len(own.lstrip("#")))
    return (text.rfind("\n", 0, at) + 1 if title or not own.startswith("#") else above[-1].start()), section_end(text, at, level)


def rule_file(files, marks, depth, rule=None):
    """The first of `files`, or of the files they `@`-import (as with_imports reads them), that holds the rule's first
    bold lead-in: the first in the rule's order that any of them holds, as rule_span reads one file. With `rule` (Claude
    Code): the first holder that differs from it."""
    seen = {}
    for f in files:
        with_imports(f, depth, seen)
    texts = [(p, read(p)) for p in seen]
    if rule is not None:
        return next((p for p, x in texts if holds(x, marks) and differs(x, marks, rule)), None)
    first = next(("**" + m for m in marks if any("**" + m in x for _, x in texts)), None)
    return next((p for p, x in texts if first and first in x), None)


def exact(path):
    """`path`'s text as it is on disk: UTF-8 read strictly, no newline translation."""
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def replace_item(path, listed, marks):
    """The replace item's values for the file that holds the rule (None: no file holds a bold lead-in; `listed` is the
    agent's instructions file): the section's first line and its end for the changes line, or the reason the owner
    does it by hand."""
    yourself = ": replace the rule's lines with rules/codegraph.md yourself"
    if not path:
        return {"file": listed, "hand": f"no bold lead-in of the rule in {listed}{yourself}"}
    try:
        text = exact(path)
    except (OSError, UnicodeDecodeError) as e:
        return {"file": path, "hand": f"{path} is not readable as UTF-8 ({e}){yourself}"}
    start, end = rule_span(text, marks)
    if start is None:
        return {"file": path, "hand": f"no heading above the rule in {path}{yourself}"}
    line = lambda at: text[at:].split("\n", 1)[0].rstrip("\r")
    return {"file": path, "first": line(start), "until": f'just before "{line(end)}"' if end < len(text) else "the end of the file"}


def replace_section(path, rule):
    """The rule's section of `path` replaced with all of the rule file `{kiss}/rules/codegraph.md` (D4): a timestamped
    backup beside it first, then a temp file and a rename, so a failure or an interrupt leaves the old file whole.
    Every byte outside the section stays (no newline translation). (exit code, output)."""
    try:
        text = exact(path)
    except (OSError, UnicodeDecodeError) as e:
        return 1, f"{path}: {e}; nothing changed"
    span, new = rule_span(text, markers(os.path.dirname(os.path.dirname(rule)))), read(rule)
    if not span or span[0] is None:
        why = "none of the rule's lead-ins" if not span else "no heading above the rule"
        return 1, f"{path}: {why}; nothing changed"
    old = back_up(path)
    rest = text[span[1]:]
    gap = "\n" * max(0, 2 - (len(new) - len(new.rstrip("\n")))) if rest else ""     # one blank line before what follows
    try:
        write_whole(path, text[:span[0]] + new + gap + rest)
    except OSError as e:
        return 1, f"{e}; {path} is unchanged; its backup: {old}"
    return 0, f"backup: {old}"


def write_copy(rule, copy):
    """`copy` holds the rule file: a backup of a copy that differs (its name does not end in .md, so Claude Code does not
    load it), then write_whole. (exit code, output)."""
    try:
        text = exact(rule)
        os.makedirs(os.path.dirname(copy), exist_ok=True)
        old = back_up(copy) if os.path.isfile(copy) and exact(copy) != text else None
        write_whole(copy, text)
    except (OSError, UnicodeDecodeError) as e:
        return 1, f"{copy}: {e}"
    return 0, f"wrote {copy}" + (f"; backup: {old}" if old else "")


def move_rule(path, copy, rule):
    """The rule file to `copy`, then the rule's section out of `path`, after a backup beside it; one blank line stays
    between the lines around it. A re-run repeats it. (exit code, output)."""
    try:
        text = exact(path)
    except (OSError, UnicodeDecodeError) as e:
        return 1, f"{path}: {e}; nothing changed"
    span = rule_span(text, markers(os.path.dirname(os.path.dirname(rule))))
    if not span or span[0] is None:
        return 1, f"{path}: {'none of the rule' + chr(39) + 's lead-ins' if not span else 'no heading above the rule'}; nothing changed"
    code, said = write_copy(rule, copy)
    if code:
        return 1, f"{said}; {path} is unchanged"
    old = ""
    nl = "\r\n" if "\r\n" in text else "\n"
    above, below = text[:span[0]].rstrip("\r\n"), text[span[1]:].lstrip("\r\n")
    try:
        old = back_up(path)
        write_whole(path, above + nl + nl + below if above and below else above + nl if above else below)
    except OSError as e:
        return 1, f"{e}; {path} is as it was; {'its backup: ' + old if old else 'no backup'}; two copies load until a re-run of setup"
    return 0, f"{said}; backup: {old}"


def check_skills(agent, roots, need, note="", here=()):
    """here: {name: SKILL.md} of the KISS skills in the folder this script runs from."""
    mark = lambda path: " (user-only: never in the model's list)" if frontmatter(path).get("disable-model-invocation") == "true" else ""
    seen = {}
    for label, root in roots:
        for name, path in skills_in(root).items():
            seen.setdefault(name, {}).setdefault(os.path.realpath(path), label)
    out = []
    for name, fix in need.items():
        copies = seen.get(name, {})
        if not copies and name in here:
            out.append(("INFO", agent, f"skill {name}{mark(here[name])}: not installed, but found in the KISS folder this script"
                        f" runs from ({KISS}): a --plugin-dir session, or a KISS repo newer than the install", ""))
            continue
        if not copies:
            out.append(("FAIL", agent, f"skill {name}: not installed{note}", fix))
            continue
        path, label = next(iter(copies.items()))
        if len(set(copies.values())) > 1:
            out.append(("WARN", agent, f"skill {name}: installed {len(copies)} times ({', '.join(sorted(set(copies.values())))}), so the agent lists it twice: keep one", fix))
        elif frontmatter(path).get("disable-model-invocation") == "true" and fix != "Install KISS":  # KISS's own: user-only on purpose
            out.append(("FAIL", agent, f"skill {name} ({label}): user-only (disable-model-invocation: true), so KISS cannot call it", "User-only skills"))
        else:
            out.append(("OK", agent, f"skill {name} ({label}){mark(path)}", ""))
    return out


def check_tools():
    good = sys.version_info >= (3, 9)
    out = [("OK" if good else "FAIL", "device", f"python3 {sys.version.split()[0]} (3.9 or later)", "" if good else "Tools you need")]
    for tool in ("git", "node", "npm", "codegraph"):
        found = shutil.which(tool)
        version = run([tool, "--version"]).strip().splitlines()[:1] if found else []
        out.append(("OK", "device", f"{tool}: {version[0] if version else 'found'}", "") if found
                   else ("FAIL", "device", f"{tool}: not on PATH", "Tools you need"))
    out.append(("OK", "device", "cgcallers", "") if shutil.which("cgcallers")
               else ("WARN", "device", "cgcallers: not on PATH, and the CodeGraph rule calls it by that name", "Tools you need"))
    return out


SERVERS = [("pyright", "pyright-langserver", (".py",)),
           ("typescript-language-server", "typescript-language-server", (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"))]


def servers_wanted(repo):
    """The language servers cgcallers' LSP pass can use in this repo: one per language it has files of."""
    exts = set()
    for d, dirs, files in os.walk(repo) if repo else []:
        dirs[:] = [x for x in dirs if not x.startswith(".") and x != "node_modules"]
        exts |= {os.path.splitext(f)[1] for f in files}
    return [key for key, _, want in SERVERS if exts & set(want)]


def check_servers(repo):
    binary = {key: b for key, b, _ in SERVERS}
    return [("OK", "device", f"{binary[k]} (cgcallers' LSP pass)", "") if shutil.which(binary[k]) else
            ("INFO", "device", f"{binary[k]}: not on PATH (optional: cgcallers' LSP pass; kiss-doctor setup)", "")
            for k in servers_wanted(repo)]


def mcp_state(agent):
    """(server set up?, its tools allowed?) for CodeGraph's MCP server, from the agent's own `mcp list`; None: unknown."""
    if agent == "antigravity":
        return None, None
    if agent == "gemini":                       # its `mcp list` hides user servers in an untrusted folder: read the file
        try:
            server = "codegraph" in json.load(open(os.path.join(HOME, ".gemini", "settings.json"))).get("mcpServers", {})
        except (OSError, ValueError, AttributeError):
            server = False
        return server, True
    server = bool(re.search(r"^\W*codegraph\b", run([CLI[agent], "mcp", "list"]), re.M))
    if agent != "claude":
        return server, True
    try:
        allowed = "mcp__codegraph__*" in json.load(open(settings_path())).get("permissions", {}).get("allow", [])
    except (OSError, ValueError, AttributeError):
        allowed = False
    return server, allowed


def check_mcp(agent):
    server, allowed = mcp_state(agent)
    if server is None:
        return [("INFO", agent, "CodeGraph's MCP server: check it by hand in the agent's MCP settings", "")]
    if not server:
        return [("INFO", agent, "CodeGraph's MCP server: not set up (optional; kiss-doctor setup)", "")]
    return [("OK", agent, "CodeGraph's MCP server", "")] if allowed else [
        ("WARN", agent, f"CodeGraph's MCP server: its tools are not allowed: add mcp__codegraph__* to permissions.allow in "
                        f"{settings_path().replace(HOME, '~')}", "")]


PROFILES = [".zshenv", ".zprofile", ".zshrc", ".bash_profile", ".bashrc", ".profile"]


def settings_path():
    return os.path.join(os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(HOME, ".claude"), "settings.json")


def feedback_mode(settings, home=HOME, env=None, project=None):
    """(on?, where). The value this session has (its environment) decides; where names the first place that sets
    that value: Claude Code's user settings env, the project's .claude settings, then a shell profile's export."""
    places = [(os.path.join(project, ".claude", n), "the project's .claude/%s env" % n)
              for n in ("settings.local.json", "settings.json")] if project else []     # Claude Code's order: local first
    places += [(settings, "Claude Code's settings env (%s)" % settings.replace(home, "~", 1))]
    found, profiles = [], []
    for path, label in places:
        try:
            value = json.load(open(path)).get("env", {}).get("KISS_FEEDBACK")
        except (OSError, ValueError, AttributeError):
            value = None
        if value is not None:
            found.append((value, label))
    for name in PROFILES:
        path = os.path.join(home, name)
        m = re.findall(r"^\s*export\s+KISS_FEEDBACK=[\"']?([^\"'\s]*)", read(path), re.M) if os.path.isfile(path) else []
        if m:
            profiles.append((m[-1], "the shell profile ~/%s" % name))
    now = (env or {}).get("KISS_FEEDBACK")
    if now is None:                     # not a Claude Code session with the setting: only a shell profile counts
        if profiles:
            return profiles[0][0] == "1", profiles[0][1]
        if found:
            return False, "set for Claude Code only, in %s" % found[0][1]
        return False, "set nowhere"
    found += profiles
    where = next((label for value, label in found if value == now), "this session's environment only: a --settings flag or the shell that started it")
    return now == "1", where


def check_feedback(settings, home=HOME, env=os.environ, project=None):
    on, where = feedback_mode(settings, home, env, project)
    hint = "" if on else "; turn it on with /kiss:kiss-doctor feedback on"
    return [("INFO", "device", "feedback mode: %s (%s)%s" % ("on" if on else "off", where, hint), "")]


def set_feedback(settings, on):
    """Set only env.KISS_FEEDBACK in the settings file, after a backup beside it. Returns the lines to print."""
    def change(data):
        if not isinstance(data.get("env"), dict):
            data["env"] = {}
        data["env"]["KISS_FEEDBACK"] = "1" if on else "0"
    backup = edit_settings(settings, change)
    return ["feedback mode %s in %s%s" % ("on" if on else "off", settings, " (backup: %s)" % backup if backup else ""),
            "Claude Code: start a new session for it to apply."]


def feedback_by_hand(agent, on):
    """The lines for an agent whose setting doctor does not write. Codex: its file is TOML, and a second table breaks it."""
    value = "1" if on else "0"
    if agent == "codex":
        return ["Codex: add this to ~/.codex/config.toml yourself, then start a new session (if the table exists, add only "
                "KISS_FEEDBACK to its set line):", "[shell_environment_policy]", 'set = { KISS_FEEDBACK = "%s" }' % value]
    return ["%s: put this line in your shell profile yourself, then start a new session: export KISS_FEEDBACK=%s"
            % ({"gemini": "Gemini CLI", "antigravity": "Antigravity"}[agent], value)]


def back_up(path):
    """A copy of `path` beside it, named by the time; a second one in the same second gets -2, -3: its path."""
    stamp = path + ".kiss-backup-" + time.strftime("%Y%m%d-%H%M%S")
    out, n = stamp, 1
    while os.path.exists(out):
        n += 1
        out = "%s-%d" % (stamp, n)
    shutil.copy2(path, out)
    with open(out, "rb+") as f:                         # on disk before the caller changes the original (Windows: a
        os.fsync(f.fileno())                            # handle with write access, or its FlushFileBuffers fails)
    return out


def edit_settings(settings, change):
    """change(data) on a JSON settings file, after a backup beside it; an unreadable file stays untouched. The backup."""
    data = {}
    if os.path.exists(settings):
        try:
            data = json.load(open(settings))
            assert isinstance(data, dict)
        except (OSError, ValueError, AssertionError) as e:
            sys.exit("%s: cannot read it as a JSON object (%s); left untouched" % (settings, type(e).__name__))
        backup = back_up(settings)              # one backup per switch, also two switches in one second
    else:
        backup = None
        os.makedirs(os.path.dirname(settings), exist_ok=True)
    change(data)
    write_whole(settings, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    return backup


def write_whole(path, text):
    """`text` into a temp file beside the file, then a rename, so a failure or an interrupt leaves the old file whole. A
    link stays a link: its target gets the change."""
    path = os.path.realpath(path)
    tmp = path + ".kiss-new"
    try:
        with open(tmp, "w", encoding="utf-8", newline="") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())                        # on disk before the rename: a power loss leaves a whole file
        if os.path.exists(path):
            shutil.copymode(path, tmp)
        os.replace(tmp, path)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:                                 # its own failure must not hide the first
            pass
        raise


# The install table: the one home of every command `setup` shows (D6). A command is one string; {name} fills
# from the system after the split, so a path with a space stays one word. key: a gap's name; for an agent item,
# the README section the skill check names as its fix.
PMS = ["nb", "brew", "apt", "dnf", "pacman", "winget", "scoop"]
PM_INSTALL = {"nb": "nb install {}", "brew": "brew install {}", "apt": "sudo apt install -y {}", "dnf": "sudo dnf install -y {}",
              "pacman": "sudo pacman -S --noconfirm {}", "winget": "winget install -e --id {}", "scoop": "scoop install {}"}
INSTALL = [
    {"key": "git", "what": "git", "source": "https://git-scm.com/downloads", "changes": "adds git through your package manager",
     "pm": {"nb": "git", "brew": "git", "apt": "git", "dnf": "git", "pacman": "git", "winget": "Git.Git", "scoop": "git"}},
    {"key": "python", "what": "Python 3.9 or later", "source": "https://www.python.org/downloads/",
     "changes": "adds Python 3 through your package manager",
     "pm": {"nb": "python", "brew": "python", "apt": "python3", "dnf": "python3", "pacman": "python",
            "winget": "Python.Python.3.12", "scoop": "python"}},
    {"key": "node", "what": "Node.js and npm", "source": "https://nodejs.org/en/download",
     "changes": "adds node and npm through your package manager",
     "pm": {"nb": "node", "brew": "node", "apt": "nodejs npm", "dnf": "nodejs npm", "pacman": "nodejs npm",
            "winget": "OpenJS.NodeJS.LTS", "scoop": "nodejs-lts"}},
    {"key": "codegraph", "what": "CodeGraph", "source": "https://github.com/colbymchenry/codegraph",
     "changes": "adds the codegraph command to npm's global folder (npm prefix -g)",
     "run": ["npm install -g @colbymchenry/codegraph"]},
    {"key": "cgcallers", "what": "cgcallers", "source": "https://github.com/Rex57/KISS (skills/kiss-harness/scripts/cgcallers.py)",
     "changes": "copies cgcallers.py to {bin}/cgcallers (KISS_BIN sets the folder; put it on your PATH yourself)",
     "run": ["install -m 755 {kiss}/skills/kiss-harness/scripts/cgcallers.py {bin}/cgcallers"]},
    {"key": "index", "what": "the CodeGraph index of this repo", "source": "https://github.com/colbymchenry/codegraph",
     "changes": "adds {repo}/.codegraph/", "run": ["codegraph init {repo}"]},
    {"key": "pyright", "what": "pyright (optional: cgcallers' LSP pass for Python)", "source": "https://github.com/microsoft/pyright",
     "changes": "adds pyright-langserver to npm's global folder (npm prefix -g)", "run": ["npm install -g pyright"]},
    {"key": "typescript-language-server", "what": "typescript-language-server (optional: cgcallers' LSP pass for JS/TS)",
     "source": "https://github.com/typescript-language-server/typescript-language-server",
     "changes": "adds typescript-language-server and TypeScript 5 (TypeScript 7 has no tsserver.js) to npm's global folder",
     "run": ["npm install -g typescript-language-server typescript@5"]},
    {"key": "rule", "what": "the CodeGraph rule", "source": "https://github.com/Rex57/KISS (rules/codegraph.md)",
     "changes": "appends the rule to {file}", "agents": {a: ["cat {kiss}/rules/codegraph.md >> {file}"] for a in CLI if a != "claude"}},
    {"key": "rule-new", "what": "the CodeGraph rule", "source": "https://github.com/Rex57/KISS (rules/codegraph.md)",
     "changes": "writes {copy}, a copy of rules/codegraph.md, and no other file; start a new session for it to load",
     "agents": {"claude": ["write {kiss}/rules/codegraph.md to {copy}"]}},
    {"key": "rule-move", "what": "move the CodeGraph section of {file} to {copy}", "source": "https://github.com/Rex57/KISS (rules/codegraph.md)",
     "changes": 'writes {copy}, a copy of rules/codegraph.md; removes the lines of {file} from "{first}" to {until}, after a backup'
                " beside the file; your own lines inside that section are lost, and kept in the backup; start a new session for it to load",
     "agents": {"claude": ["move the CodeGraph section of {file} to {copy} with {kiss}/rules/codegraph.md"]}},
    {"key": "rule-replace", "what": "replace the CodeGraph section of {file}", "source": "https://github.com/Rex57/KISS (rules/codegraph.md)",
     "changes": 'replaces the lines of {file} from "{first}" to {until} with all of rules/codegraph.md, after a backup'
                " beside the file; your own lines inside that section are lost, and kept in the backup",
     "agents": {a: ["replace the CodeGraph section of {file} with {kiss}/rules/codegraph.md"] for a in CLI},
     "after": {"claude": "start a new session: a rule file loads when a session starts"}},
    {"key": "mcp", "what": "CodeGraph's MCP server", "source": "https://github.com/colbymchenry/codegraph",
     "changes": "adds the MCP server codegraph (codegraph serve --mcp) to {agent}'s user settings",
     "agents": {"claude": ["claude mcp add --scope user codegraph -- codegraph serve --mcp", "allow mcp__codegraph__* in {settings}"],
                "codex": ["codex mcp add codegraph -- codegraph serve --mcp"],
                "gemini": ["gemini mcp add --scope user codegraph codegraph serve --mcp"]},
     "hand": {"antigravity": "in Antigravity's MCP settings, add a server named codegraph that runs: codegraph serve --mcp"}},
    {"key": "mcp-allow", "what": "CodeGraph's MCP tools allowed (Claude Code)", "source": "https://github.com/colbymchenry/codegraph",
     "changes": "adds mcp__codegraph__* to permissions.allow in {settings}, after a backup beside it",
     "agents": {"claude": ["allow mcp__codegraph__* in {settings}"]}},
    {"key": "Install KISS", "what": "KISS", "source": "https://github.com/Rex57/KISS", "changes": "adds the KISS plugin to {agent}",
     "agents": {"claude": ["claude plugin marketplace add Rex57/KISS", "claude plugin install kiss@kiss"],
                "codex": ["codex plugin marketplace add Rex57/KISS", "codex plugin add kiss@kiss"],
                "gemini": ["gemini extensions install https://github.com/Rex57/KISS --consent"]},
     "hand": {"antigravity": "git clone https://github.com/Rex57/KISS.git, then agy plugin install ./KISS"}},
    {"key": "Install ponytail", "what": "ponytail", "source": "https://github.com/DietrichGebert/ponytail",
     "changes": "adds the ponytail plugin to {agent}",
     "agents": {"claude": ["claude plugin marketplace add DietrichGebert/ponytail", "claude plugin install ponytail@ponytail"],
                "codex": ["codex plugin marketplace add DietrichGebert/ponytail", "codex plugin add ponytail@ponytail"],
                "gemini": ["gemini extensions install https://github.com/DietrichGebert/ponytail --consent"]},
     "hand": {"antigravity": "follow https://github.com/DietrichGebert/ponytail/blob/main/INSTALL.md"},
     "after": {"codex": "in Codex, open /hooks, trust ponytail's two hooks, and start a new thread"}},
    {"key": "Install Matt Pocock's skills", "what": "Matt Pocock's skills", "source": "https://github.com/mattpocock/skills",
     "changes": "adds Matt Pocock's skills to {agent}",
     "agents": {"claude": ["claude plugin marketplace add mattpocock/skills", "claude plugin install mattpocock-skills@mattpocock"],
                "codex": ["codex plugin marketplace add mattpocock/skills", "codex plugin add mattpocock-skills@mattpocock"],
                "gemini": ["gemini skills install https://github.com/mattpocock/skills.git --path skills/engineering --consent",
                           "gemini skills install https://github.com/mattpocock/skills.git --path skills/productivity --consent"]},
     "hand": {"antigravity": "copy the eight skill folders KISS uses (README \"Install Matt Pocock's skills\") from a clone of"
                             " https://github.com/mattpocock/skills.git into ~/.gemini/config/skills/"}},
]
OPTIONAL = [("agentmemory", "https://github.com/rohitg00/agentmemory"), ("a headless browser", "https://playwright.dev")]


def command(argv):
    return " ".join(w if w == ">>" else shlex.quote(w) for w in argv)


def plan(system, gaps):
    """The plan: one item per gap, in the table's order. system: os, shell, pm, agents, repo, bin, kiss;
    gaps: {key or (agent, key): {placeholder: value}}. An item the owner must do has a `hand` reason and no number."""
    out, files, n = [], set(), 0
    for row in INSTALL:
        for agent in system["agents"] if "agents" in row else ["device"]:
            key = row["key"] if agent == "device" else (agent, row["key"])
            if key not in gaps:
                continue
            values = dict(system, agent=agent, **gaps[key])
            if "file" in values:
                if values["file"] in files:                     # Gemini CLI and Antigravity share GEMINI.md
                    continue
                files.add(values["file"])
            hand = ""
            if "pm" in row:
                cmds = [PM_INSTALL[system["pm"]].format(row["pm"][system["pm"]])] if system["pm"] else []
                hand = ("needs sudo: run it yourself" if cmds[0].startswith("sudo ") else "") if cmds else \
                    "no package manager found: download it from " + row["source"]
            else:
                cmds = row.get("run") or row["agents"].get(agent, [])
                hand = "by hand: " + row["hand"][agent] if agent in row.get("hand", {}) else ""
                if "hand" in values:                            # this file's own reason the owner does it
                    cmds, hand = [], "by hand: " + values["hand"]
            run = [[w.format(**values) for w in shlex.split(c)] for c in cmds]
            n += bool(run and not hand)
            out.append({"n": n if run and not hand else None, "what": row["what"].format(**values), "agent": agent, "run": run, "hand": hand,
                        "source": row["source"], "changes": "nothing: setup does not change the file" if "hand" in values else
                        row["changes"].format(**values) if cmds or "pm" not in row else "nothing: you install it yourself from the link",
                        "after": row.get("after", {}).get(agent, "")})
    return out


def plan_id(items):
    """A short id of the numbered items (number, what, agent, commands, and the changes line: the lines a replace takes):
    --apply refuses a plan that changed."""
    return hashlib.sha1(json.dumps([[i["n"], i["what"], i["agent"], i["run"], i["changes"]] for i in items if i["n"]]).encode()).hexdigest()[:8]


def plan_lines(system, items):
    agents = ", ".join(system["agents"]) or "none on PATH"
    out = [f"KISS setup on {system['os']} ({system['shell'] or 'unknown shell'}), package manager: {system['pm'] or 'none'},"
           f" agents: {agents}" + (f", repo: {system['repo']}" if system["repo"] else "")]
    detail = lambda i: [f"   source:  {i['source']}", f"   changes: {i['changes']}"]
    for i in items:
        if i["n"]:
            out += [f"{i['n']}. {i['what']} ({i['agent']})"] + [f"   command: {command(c)}" for c in i["run"]] + detail(i)
    if not any(i["n"] for i in items):
        out.append("Nothing to install.")
    out += by_hand(system, items, [i for i in items if i["n"]])
    if any(i["n"] for i in items):
        call = " ".join(["setup"] + system["agents"])           # the same agents, so --apply sees the same plan
        out += [f"plan id: {plan_id(items)}",
                f"Answer all, none, or the numbers to install (for example 1,3); then: {call} --apply <answer> --plan {plan_id(items)}"]
    return out


def by_hand(system, items, ran):
    """The steps only the owner can do: the items setup never runs, the steps after the items in `ran`, the PATH line
    for the cgcallers folder (setup never edits a shell profile), the links."""
    out, hand = [], [i for i in items if not i["n"]]
    if system["bin"] not in system.get("path", "").split(os.pathsep) and (
            any(i["what"] == "cgcallers" for i in items) or os.path.isfile(os.path.join(system["bin"], "cgcallers"))):
        out += ["Put the cgcallers folder on your PATH: add this line to your shell profile yourself:",
                f'  export PATH="{system["bin"]}:$PATH"']
    if hand:
        out.append("For you to do (setup never runs these):")
        for i in hand:
            out += [f"- {i['what']} ({i['agent']}): {i['hand']}"] + [f"   command: {command(c)}" for c in i["run"]] + [
                f"   source:  {i['source']}", f"   changes: {i['changes']}"]
    after = [i["after"] for i in ran if i["after"]] + (["start a new session of each agent you installed into (log in if it asks)"]
                                                       if any(i["agent"] != "device" for i in ran) else [])
    if after:
        out += ["After the installs, by hand:"] + [f"- {a}" for a in after]
    return out + ["Optional, links only:"] + [f"- {what}: {url}" for what, url in OPTIONAL]


TIMEOUT = 300      # seconds per command: a stall ends as a FAIL with its output, well inside the skill's call


def execute(argv, timeout=TIMEOUT):
    """Run one table command, without a shell: (exit code, output). The two file commands run in Python, so they
    work where no POSIX shell is."""
    try:
        if argv[0] == "cat" and argv[2:3] == [">>"]:
            old = read(argv[3]) if os.path.isfile(argv[3]) else ""
            os.makedirs(os.path.dirname(argv[3]), exist_ok=True)
            with open(argv[3], "a", encoding="utf-8") as f:
                f.write(("\n" if old and not old.endswith("\n") else "") + read(argv[1]))
            return 0, ""
        if argv[0] == "allow" and argv[2:3] == ["in"]:      # one permission rule, added once to Claude Code's settings
            def change(data):
                perms = data.setdefault("permissions", {})
                allow = perms.setdefault("allow", [])
                if argv[1] not in allow:
                    allow.append(argv[1])
            edit_settings(argv[3], change)
            return 0, ""
        if argv[:5] == ["replace", "the", "CodeGraph", "section", "of"] and argv[6:7] == ["with"]:
            return replace_section(argv[5], argv[7])
        if argv[0] == "write" and argv[2:3] == ["to"]:
            return write_copy(argv[1], argv[3])
        if argv[:5] == ["move", "the", "CodeGraph", "section", "of"] and argv[6:7] == ["to"] and argv[8:9] == ["with"]:
            return move_rule(argv[5], argv[7], argv[9])
        if argv[:3] == ["install", "-m", "755"]:
            os.makedirs(os.path.dirname(argv[4]), exist_ok=True)
            shutil.copyfile(argv[3], argv[4])
            os.chmod(argv[4], 0o755)
            return 0, ""
        p = subprocess.run([shutil.which(argv[0]) or argv[0]] + argv[1:], capture_output=True, text=True, timeout=timeout,
                           stdin=subprocess.DEVNULL)
        return p.returncode, (p.stdout + p.stderr).strip()
    except (OSError, subprocess.TimeoutExpired, SystemExit) as e:
        return 1, str(e)


def apply(items, answer, runner=execute):
    """Run the items the owner's answer names (all, none, or numbers), in the plan's order, one at a time; stop at
    the first failure. (lines, ok, the items that ran to the end, the items the answer picked)."""
    numbered = {i["n"]: i for i in items if i["n"]}
    words = [w for w in re.split(r"[,\s]+", answer.strip().lower()) if w]
    if words == ["all"] or words == ["none"]:
        want = sorted(numbered) if words == ["all"] else []
    elif words and all(re.fullmatch(r"[0-9]+", w) and int(w) in numbered for w in words):
        want = sorted({int(w) for w in words})
    else:
        return [f"refused: {answer!r} is not all, none, or numbers of the plan ({', '.join(map(str, numbered)) or 'none'});"
                " nothing ran"], False, [], []
    sudo = [n for n in want if any(c[0] == "sudo" for c in numbered[n]["run"])]
    if sudo:                                    # plan() never numbers one; this guard keeps it so
        return [f"refused: item {', '.join(map(str, sudo))} needs sudo: run it yourself; nothing ran"], False, [], []
    out, ran = [], []
    for n in want:
        i, last = numbered[n], []
        for argv in i["run"]:
            code, output = runner(argv)
            if code:
                rest = [str(m) for m in want if m > n]
                return out + [f"FAIL {n}. {i['what']} ({i['agent']}): {command(argv)} exited {code}"] + [
                    "   " + line for line in output.splitlines()[-20:]] + (
                    [f"not run: {', '.join(rest)}"] if rest else []), False, ran, [numbered[m] for m in want]
            last = output.splitlines()[-1:]
        out += [f"done {n}. {i['what']} ({i['agent']})"] + ["   " + line for line in last]
        ran.append(i)
    return out, True, ran, [numbered[m] for m in want]


def setup(system, answer=None, runner=execute, find=None, checks=None, pid=None):
    """`setup` prints the plan; `setup --apply <answer> --plan <id>` runs it, then the checks again and the steps by
    hand. The id must be the plan's own, so a number names the item the owner saw."""
    items = plan(system, (find or gaps)(system))
    if answer is None:
        return plan_lines(system, items), True
    if pid != plan_id(items):
        return [f"refused: the plan changed since you saw it (plan id {plan_id(items)}, not {pid}): show it again; nothing ran"], False
    lines, ok, ran, picked = apply(items, answer, runner)
    failed = any(line.startswith("FAIL ") for line in lines)
    if ran or failed:                                       # the checks run again after a failure too
        # An agent with numbered items the owner picked none of is left out (D15); the apply call still names it, as
        # another agent list would make another plan.
        skipped = [a for a in system["agents"] if any(i["n"] and i["agent"] == a for i in items) and a not in {i["agent"] for i in picked}]
        lines += ["", "The checks again:"] + (
            [f"left out of the checks (you picked none of their items): {', '.join(skipped)}"] if skipped else []) + (
            checks or (lambda agents: report(agents)[0]))([a for a in system["agents"] if a not in skipped])
    if ok and not picked and "all" not in answer.lower():   # an answer of none: say so, not just the links
        lines = ["none picked: nothing ran"] + lines
    if ran or ok or failed:
        lines += [""] + by_hand(system, items, ran)
    return lines, ok


def setup_args(rest, on_path):
    """`setup [AGENT ...] [--apply <answer> --plan <id>]` → (the agents, in PATH order; the answer; the plan id).
    No AGENT: every agent on PATH. An agent not on PATH, or any other form, exits with its reason."""
    i = rest.index("--apply") if "--apply" in rest else len(rest)
    names, tail = rest[:i], rest[i:]
    if tail and (len(tail) != 4 or tail[2] != "--plan") or any(n.startswith("-") for n in names):
        sys.exit("usage: doctor.py setup [AGENT ...] [--apply all|none|<numbers> --plan <id>]")
    wrong = [n for n in names if n not in on_path]
    if wrong:
        sys.exit(f"not an agent on PATH: {', '.join(wrong)} (on PATH: {', '.join(on_path) or 'none'})")
    return [a for a in on_path if not names or a in names], (tail[1] if tail else None), (tail[3] if tail else None)


def loaded_here(agent):
    """The script's own KISS folder is what this Claude Code session loaded (CLAUDECODE=1 in its shell)."""
    return skills_in(os.path.join(KISS, "skills")) if agent == "claude" and os.environ.get("CLAUDECODE") == "1" else {}


def detect():
    shell = os.environ.get("SHELL") or os.environ.get("COMSPEC") or ""
    repo = run(["git", "rev-parse", "--show-toplevel"]).strip() if shutil.which("git") else ""
    return {"os": {"Darwin": "macos", "Windows": "windows"}.get(platform.system(), "linux"),
            "shell": os.path.basename(shell), "pm": next((p for p in PMS if shutil.which(p)), None),
            "agents": [a for a, cli in CLI.items() if shutil.which(cli)], "repo": repo or None,
            "bin": os.environ.get("KISS_BIN") or os.path.join(HOME, ".local", "bin"), "kiss": KISS,
            "path": os.environ.get("PATH", "")}


def claude_rule_gap(level, files, marks, rule):
    """Claude Code's rule item: none yet, a new copy; a stale section in CLAUDE.md, or a section beside a copy (a move
    that stopped halfway), the move; another holder that differs (a stale copy, a hand-made import), its replace; else nothing."""
    main, copy = files[0], os.path.join(os.path.dirname(files[0]), "rules", "kiss.md")
    if level == "FAIL":
        return {("claude", "rule-new"): {"copy": copy}}
    real = os.path.realpath(main)
    beside = os.path.isfile(copy) and os.path.isfile(main) and holds(read(main), marks)
    holder = rule_file(files, marks, 4, rule)
    if beside or level == "WARN" and holder == real:
        return {("claude", "rule-move"): dict(replace_item(real, main, marks), copy=copy)}
    return {("claude", "rule-replace"): replace_item(holder, main, marks)} if level == "WARN" else {}


def gaps(system):
    """What the checks find missing on this machine, in plan()'s form."""
    out = {k: {} for k, missing in [("git", not shutil.which("git")), ("python", sys.version_info < (3, 9)),
                                     ("node", not (shutil.which("node") and shutil.which("npm"))),
                                     ("codegraph", not shutil.which("codegraph")),
                                     ("cgcallers", not (shutil.which("cgcallers") or os.path.isfile(os.path.join(system["bin"], "cgcallers")))),
                                     ("index", system["repo"] and not os.path.isdir(os.path.join(system["repo"], ".codegraph")))]
           if missing}
    binary = {key: b for key, b, _ in SERVERS}
    out.update({k: {} for k in servers_wanted(system["repo"]) if not shutil.which(binary[k])})
    need, marks = required(), markers()
    rule = read(os.path.join(KISS, "rules", "codegraph.md"))
    for agent in system["agents"]:
        text, files, roots, note = agent_setup(agent)
        level = check_rule(agent, text, files, marks, rule)[0][0]
        if agent == "claude":
            out.update(claude_rule_gap(level, files, marks, rule))
        elif level == "FAIL":
            out[(agent, "rule")] = {"file": files[0]}
        elif level == "WARN":                   # an older or edited copy: its section replaced (D4)
            out[(agent, "rule-replace")] = replace_item(rule_file(files, marks, 0), files[0], marks)
        for level, _, _, fix in check_skills(agent, roots, need, note, loaded_here(agent)):
            if level == "FAIL" and fix.startswith("Install "):
                out[(agent, fix)] = {}
        server, allowed = mcp_state(agent)
        if not server:
            out[(agent, "mcp")] = {"settings": settings_path()}
        elif allowed is False:                  # the server is there, its tools are not allowed (Claude Code)
            out[(agent, "mcp-allow")] = {"settings": settings_path()}
    return out


def selftest():
    import tempfile
    # The rule KISS ships is the short rule (B3): these eight lead-ins are the markers.
    assert markers() == ["Installer trap", "Which index", "Every call names `W`", "Keep it fresh",
                         "CodeGraph first, for every code question and before every edit",
                         "grep, find or Read only for", "`callers` is incomplete", "Subagents"], markers()
    with tempfile.TemporaryDirectory() as t:
        def put(rel, text):
            path = os.path.join(t, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write(text)
            return path
        put("kiss/rules/codegraph.md", "## CodeGraph\n\n**Which index.** a\n**`callers` is incomplete:** b\n")
        put("kiss/skills/kiss-harness/SKILL.md", "| Skill | From |\n|---|---|\n| `tdd` | Matt Pocock's skills | x |\n| `ponytail` | ponytail | y |\n")
        put("kiss/skills/kiss-doctor/SKILL.md", "---\nname: kiss-doctor\n---\n| Key | Means |\n|---|---|\n| `ok` | not a skill |\n")
        put("kiss/skills/kiss-code-clean/SKILL.md", "intro\n\n| Skill | From | Used in | Without it |\n|---|---|---|---|\n"
            "| `ponytail-audit` | ponytail | step 3 | x |\n| `codebase-design` | Matt Pocock's skills | step 5 | y |\n\nmore\n")
        kiss = os.path.join(t, "kiss")
        need = required(kiss)
        assert need == {"kiss-code-clean": "Install KISS", "kiss-doctor": "Install KISS", "kiss-harness": "Install KISS",
                        "tdd": "Install Matt Pocock's skills", "ponytail": "Install ponytail",
                        "ponytail-audit": "Install ponytail", "codebase-design": "Install Matt Pocock's skills"}, need
        marks = markers(kiss)
        assert marks == ["Which index", "`callers` is incomplete"], marks
        # the rule: in an imported file, an edited copy, none at all, and the installer's block
        main = put("home/CLAUDE.md", "intro\n@rules.md\n@types/node is not a file\n")
        put("home/rules.md", "**Which index.** x\n**`callers` is incomplete** (my note): y\n")
        assert check_rule("claude", with_imports(main), [main], marks)[0][0] == "OK"
        assert check_rule("claude", "**Which index.** only", [main], marks)[0][0] == "FAIL"    # half of them is no copy
        three = marks + ["Third"]                               # more than half, one lacking
        assert check_rule("claude", "**Which index.** **`callers` is incomplete** only", [main], three)[0][0] == "WARN"
        assert check_rule("claude", "nothing", [main], marks)[0][0] == "FAIL"
        assert check_rule("claude", "", [main], marks)[0][0] == "FAIL"
        # T-4: a copy with every lead-in is compared with KISS's text (whitespace and the text around it aside)
        rule = read(os.path.join(kiss, "rules", "codegraph.md"))
        same = "# Mine\n\n## CodeGraph\n\n**Which index.**  a\n**`callers` is incomplete:** b\n\n## Other\nmore\n"
        assert check_rule("claude", same, [main], marks, rule) == [("OK", "claude", "CodeGraph rule in " + main, "")]
        old = check_rule("claude", "**Which index.** a\n**`callers` is incomplete:** older b\n", [main], marks, rule)
        assert old[0][0] == "WARN" and "differs from KISS's text: run kiss-doctor setup" in old[0][2], old
        assert check_rule("claude", "**Which index.** **`callers` is incomplete** only", [main], three, rule)[0][0] == "WARN"   # lacks a lead-in: as before
        assert check_rule("claude", "nothing", [main], marks, rule)[0][0] == "FAIL"
        assert len(check_rule("claude", "Which index `callers` is incomplete: delete a `CODEGRAPH_START` block", [main], marks)) == 1
        assert check_rule("claude", "Which index `callers` is incomplete\n<!-- CODEGRAPH_START -->\n", [main], marks)[1][0] == "WARN"
        # D4: the replace item's command, by worked examples on scratch files; the rule file is the scratch KISS's
        replace = lambda path: execute(["replace", "the", "CodeGraph", "section", "of", path, "with", os.path.join(kiss, "rules", "codegraph.md")])
        backups = lambda path: sorted(glob.glob(path + ".kiss-backup-*"))
        raw = lambda path: open(path, encoding="utf-8", newline="").read()       # read() would turn \r\n into \n
        mid = "# Mine\r\nintro\n\n## CodeGraph — old\n\n**Which index.** a\nmy own line\n**`callers` is incomplete:** older\n\n## Other\nmore\n"
        path = put("r/mid.md", mid)
        code, out = replace(path)
        assert code == 0 and raw(path) == "# Mine\r\nintro\n\n" + rule + "\n## Other\nmore\n", (code, out, raw(path))
        assert backups(path) and out == "backup: " + backups(path)[0] and raw(backups(path)[0]) == mid, out
        last = "# Mine\n\n## CodeGraph\n**Which index.** a\n**`callers` is incomplete:** older\n### My note\nmine\n"        # the section is the file's last
        path = put("r/last.md", last)
        assert replace(path)[0] == 0 and read(path) == "# Mine\n\n" + rule, read(path)
        # Worked examples of where the section starts and ends; the next heading keeps one blank line before it.
        spans = {
            # The owner's own bold lead-in word above the rule does not move the section: the rule's first one does.
            "s1.md": ("# Me\n\n## Workflow\n- Plan first.\n**`callers` is incomplete** in my words.\n\n## CodeGraph\n"
                      "**Which index.** a\n**`callers` is incomplete:** old\n\n## Last\nz\n",
                      "# Me\n\n## Workflow\n- Plan first.\n**`callers` is incomplete** in my words.\n\n" + rule + "\n## Last\nz\n"),
            # codegraph install's block after the rule keeps its CODEGRAPH_START line (its own WARN).
            "s2.md": ("# Me\n\n## CodeGraph\n**Which index.** a\n**`callers` is incomplete:** old\n\n<!-- CODEGRAPH_START -->\n"
                      "## CodeGraph\nblock\n<!-- CODEGRAPH_END -->\n",
                      "# Me\n\n" + rule + "\n<!-- CODEGRAPH_START -->\n## CodeGraph\nblock\n<!-- CODEGRAPH_END -->\n"),
            # Under the file's # title the section starts at the lead-in's line: the title and the lines above stay.
            "s3.md": ("# My instructions\n- Always use uv.\n**Which index.** a\n**`callers` is incomplete:** old\n\n## Last\nz\n",
                      "# My instructions\n- Always use uv.\n" + rule + "\n## Last\nz\n"),
            # A # line inside a ``` fence is no heading, inside the section or above it.
            "s5.md": ("# Me\n\n## CodeGraph\n**Which index.** a\n```sh\n# my sync alias\nalias s=sync\n```\n"
                      "**`callers` is incomplete:** old\n\n## Last\nz\n", "# Me\n\n" + rule + "\n## Last\nz\n"),
            "s5-above.md": ("# Me\n\n## Tools\n```sh\n# a comment\n```\n**Which index.** a\n**`callers` is incomplete:** old\n\n## Last\nz\n",
                            "# Me\n\n" + rule + "\n## Last\nz\n"),
            # A ~~~ fence is a fence too.
            "r10.md": ("# Me\n\n## CodeGraph\n**Which index.** a\n~~~sh\n# my alias\nalias s=sync\n~~~\n"
                       "**`callers` is incomplete:** old\n\n## Last\nz\n", "# Me\n\n" + rule + "\n## Last\nz\n"),
            # codegraph install's block above the rule stays whole: after its CODEGRAPH_END line the section starts at the lead-in.
            "r9.md": ("# Me\n<!-- CODEGRAPH_START -->\n## CodeGraph\nblock text\n<!-- CODEGRAPH_END -->\n**Which index.** a\n"
                      "**`callers` is incomplete:** old\n\n## Next\nz\n",
                      "# Me\n<!-- CODEGRAPH_START -->\n## CodeGraph\nblock text\n<!-- CODEGRAPH_END -->\n" + rule + "\n## Next\nz\n"),
            # A `# ` heading that is not the file's first is the section's own: one CodeGraph heading after the replace (D25).
            "s12.md": ("# Toolchain\n- Use uv.\n# CodeGraph — the rule\n**Which index.** a\n**`callers` is incomplete:** old\n"
                       "# Explanations\nz\n", "# Toolchain\n- Use uv.\n" + rule + "\n# Explanations\nz\n"),
        }
        for rel, (before, after) in spans.items():
            path = put("spans/" + rel, before)
            code, out = replace(path)
            assert code == 0 and raw(path) == after, (rel, code, out, raw(path))
        # The check of each case (the normal one, the file's last section, every span): the copy before differs, the
        # replaced one is KISS's text.
        cases = [("r/mid.md", mid), ("r/last.md", last)] + [("spans/" + rel, before) for rel, (before, _) in spans.items()]
        got = [(rel, check_rule("claude", before, [rel], marks, rule)[0][0], check_rule("claude", raw(os.path.join(t, rel)), [rel], marks, rule)[0][0])
               for rel, before in cases]
        assert got == [(rel, "WARN", "OK") for rel, _ in cases], got
        again = check_rule("claude", raw(os.path.join(t, "spans", "s2.md")), ["s2.md"], marks, rule)
        assert [(o[0], "CODEGRAPH_START block" in o[2]) for o in again] == [("OK", False), ("WARN", True)], again
        # S14: an exact copy with the owner's own ### subsection after it: the comparison ends at that heading.
        k = "# Me\n" + rule + "### My CodeGraph notes\n- a note\n## Last\n"
        assert check_rule("claude", k, ["k.md"], marks, rule) == [("OK", "claude", "CodeGraph rule in k.md", "")], k
        bad = {"r/none.md": "# Mine\n**Other.** x\n", "r/nohead.md": "intro\n**Which index.** a\n"}
        for rel, text in bad.items():                            # three kinds of bad input: each a FAIL, nothing changed
            path = put(rel, text)
            code, out = replace(path)
            assert code and read(path) == text and not backups(path) and "nothing changed" in out, (rel, code, out)
        code, out = replace(os.path.join(t, "r", "missing.md"))
        assert code and "nothing changed" in out and not glob.glob(os.path.join(t, "r", "missing.md*")), out
        path = put("r/fail.md", mid)                             # the write fails after the backup: the old file stays whole
        def full(*_):
            raise OSError("disk full")
        real, os.replace = os.replace, full
        try:
            code, out = replace(path)
        finally:
            os.replace = real
        assert code and raw(path) == mid == raw(backups(path)[0]) and backups(path)[0] in out, (code, out)
        if os.name == "posix":                                   # Windows: FlushFileBuffers needs a handle with write access
            import fcntl
            def strict_fsync(fd, real=os.fsync):
                if fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY:
                    raise OSError(9, "fsync on a read-only handle")
                real(fd)
            win, os.fsync = put("win/w.md", mid), strict_fsync
            try:
                code, out = replace(win)
            finally:
                os.fsync = strict_fsync.__defaults__[0]
            assert code == 0 and raw(backups(win)[0]) == mid, (code, out)
        left = put("left/s10.md", mid)                           # a folder at the temp path: its cleanup fails too
        os.mkdir(left + ".kiss-new")
        code, out = replace(left)
        assert code and raw(left) == mid and backups(left) and backups(left)[0] in out, (code, out)
        assert sorted(os.listdir(os.path.join(t, "r"))) == sorted(["mid.md", "last.md", "none.md", "nohead.md", "fail.md"] + [
            os.path.basename(b) for b in backups(os.path.join(t, "r", "mid.md")) + backups(os.path.join(t, "r", "last.md")) + backups(path)]), os.listdir(os.path.join(t, "r"))
        # the skills: once, twice, user-only, missing
        put("a/skills/tdd/SKILL.md", "---\nname: tdd\n---\n")
        put("a/skills/ponytail/SKILL.md", "---\nname: ponytail\ndisable-model-invocation: true\n---\n")
        put("b/skills/engineering/tdd/SKILL.md", "---\nname: tdd\n---\n")
        put("a/skills/.hidden/kiss-doctor/SKILL.md", "---\nname: kiss-doctor\n---\n")
        one = {r[2].split()[1].rstrip(":"): r[0] for r in check_skills("claude", [("a", os.path.join(t, "a"))], need)}
        assert one == {"kiss-code-clean": "FAIL", "kiss-doctor": "FAIL", "kiss-harness": "FAIL", "tdd": "OK", "ponytail": "FAIL",
                       "ponytail-audit": "FAIL", "codebase-design": "FAIL"}, one
        assert [r[3] for r in check_skills("claude", [("a", os.path.join(t, "a"))], need) if "user-only" in r[2]] == ["User-only skills"]
        # a KISS skill the session loaded from the script's own folder but not installed: INFO with the reason
        here = {r[2].split()[1].rstrip(":"): r for r in check_skills("claude", [("a", os.path.join(t, "a"))], need, here={"kiss-harness": put("h/kiss-harness/SKILL.md", "---\nname: kiss-harness\n---\n")})}
        assert here["kiss-harness"][0] == "INFO" and "--plugin-dir" in here["kiss-harness"][2], here
        assert here["kiss-doctor"][0] == "FAIL", here
        # KISS's own skill is user-only on purpose: no FAIL
        put("c/skills/kiss-doctor/SKILL.md", "---\nname: kiss-doctor\ndisable-model-invocation: true\n---\n")
        row = check_skills("claude", [("c", os.path.join(t, "c"))], {"kiss-doctor": "Install KISS"})[0]
        assert row[0] == "OK" and row[2].endswith("(user-only: never in the model's list)"), row
        # a user-only KISS skill found only in the script's own folder: INFO, marked user-only
        row = check_skills("claude", [], {"kiss-system-design": "Install KISS"},
                           here={"kiss-system-design": put("h/sd/SKILL.md", "---\nname: kiss-system-design\ndisable-model-invocation: true\n---\n")})[0]
        assert row[0] == "INFO" and "user-only: never in the model's list" in row[2], row
        assert "user-only" not in here["kiss-harness"][2], here
        two =check_skills("claude", [("a", os.path.join(t, "a")), ("b", os.path.join(t, "b"))], {"tdd": "x"})
        assert two[0][0] == "WARN" and "2 times" in two[0][2], two
        assert check_skills("claude", [("a", os.path.join(t, "a")), ("a", os.path.join(t, "a"))], {"tdd": "x"})[0][0] == "OK"
        # the feedback mode: where it is set, and the switch on a scratch settings file
        home = os.path.join(t, "fhome")
        os.makedirs(home)
        st = os.path.join(home, "cfg", "settings.json")
        assert feedback_mode(st, home) == (False, "set nowhere")
        off = check_feedback(st, home, env={})[0][2]
        assert off == "feedback mode: off (set nowhere); turn it on with /kiss:kiss-doctor feedback on", off
        put("fhome/cfg/settings.json", json.dumps({"env": {"KISS_FEEDBACK": "1"}}))
        assert feedback_mode(st, home) == (False, "set for Claude Code only, in Claude Code's settings env (~/cfg/settings.json)"), feedback_mode(st, home)
        os.remove(st)
        put("fhome/.zshrc", "export PATH=x\nexport KISS_FEEDBACK=1\n")
        assert feedback_mode(st, home) == (True, "the shell profile ~/.zshrc"), feedback_mode(st, home)
        assert check_feedback(st, home, env={})[0][2] == "feedback mode: on (the shell profile ~/.zshrc)"
        original = {"model": "opus", "permissions": {"allow": ["Read"]}, "hooks": {"Stop": []}, "note": "café"}
        put("fhome/cfg/settings.json", json.dumps(original))
        lines = set_feedback(st, False)
        backups = lambda: sorted(glob.glob(st + ".kiss-backup-*"))
        assert len(backups()) == 1 and json.load(open(backups()[0])) == original and backups()[0] in lines[0], lines
        got = json.load(open(st))
        assert got == dict(original, env={"KISS_FEEDBACK": "0"}), got
        assert feedback_mode(st, home, env={"KISS_FEEDBACK": "0"}) == (False, "Claude Code's settings env (~/cfg/settings.json)")   # off wins over the profile
        assert "café" in read(st)                                                     # ensure_ascii=False
        before = json.load(open(st))
        set_feedback(st, True)
        assert len(backups()) == 2 and json.load(open(backups()[1])) == before   # one backup per switch: the file before it
        assert json.load(open(backups()[0])) == original
        put("fhome/cfg/settings.json", json.dumps(dict(original, env={"PATH_X": "y"})))
        set_feedback(st, True)
        assert json.load(open(st)) == dict(original, env={"PATH_X": "y", "KISS_FEEDBACK": "1"})
        # CLAUDE_CONFIG_DIR is honoured: the path and the write land inside it
        old_cfg = os.environ.get("CLAUDE_CONFIG_DIR")
        os.environ["CLAUDE_CONFIG_DIR"] = os.path.join(t, "ccd")
        try:
            assert settings_path() == os.path.join(t, "ccd", "settings.json"), settings_path()
            set_feedback(settings_path(), True)
            assert json.load(open(os.path.join(t, "ccd", "settings.json"))) == {"env": {"KISS_FEEDBACK": "1"}}
        finally:
            os.environ.pop("CLAUDE_CONFIG_DIR") if old_cfg is None else os.environ.__setitem__("CLAUDE_CONFIG_DIR", old_cfg)
        assert "new session" in " ".join(lines) and "export" not in " ".join(lines)
        put("fhome/cfg/settings.json", "{ not json")
        try:
            set_feedback(st, True)
            raise AssertionError("an unreadable file was written")
        except SystemExit as e:
            assert "left untouched" in str(e)
        assert read(st) == "{ not json"
        fresh = os.path.join(home, "new", "settings.json")
        set_feedback(fresh, True)
        assert json.load(open(fresh)) == {"env": {"KISS_FEEDBACK": "1"}} and not glob.glob(fresh + ".kiss-backup*")
        # the session's own value decides; where names the place that sets it
        assert feedback_mode(fresh, home, env={"KISS_FEEDBACK": "1"}) == (True, "Claude Code's settings env (~/new/settings.json)")
        assert feedback_mode(os.path.join(t, "none.json"), home, env={"KISS_FEEDBACK": "1"}) == (True, "the shell profile ~/.zshrc")
        assert feedback_mode(os.path.join(t, "none.json"), home, env={"KISS_FEEDBACK": "0"})[1].startswith("this session's environment only")
        put("proj/.claude/settings.local.json", json.dumps({"env": {"KISS_FEEDBACK": "0"}}))
        assert feedback_mode(os.path.join(t, "none.json"), home, env={"KISS_FEEDBACK": "0"}, project=os.path.join(t, "proj")) == (False, "the project's .claude/settings.local.json env")
        # the feedback command as a user runs it: a scratch config, stdout, stderr and the exit code
        cfg = os.path.join(t, "scratch cfg")
        os.makedirs(cfg)

        def switch(*args):
            p = subprocess.run([sys.executable, "-I", os.path.abspath(__file__), "feedback", *args], capture_output=True, text=True,
                               env=dict(os.environ, CLAUDE_CONFIG_DIR=cfg))
            return p.returncode, p.stdout, p.stderr
        last = "This run gives no block when the mode was off at its start.\n"
        codex = ("Codex: add this to ~/.codex/config.toml yourself, then start a new session (if the table exists, add only "
                 'KISS_FEEDBACK to its set line):\n[shell_environment_policy]\nset = { KISS_FEEDBACK = "%s" }\n' + last)
        shell = "%s: put this line in your shell profile yourself, then start a new session: export KISS_FEEDBACK=%s\n" + last
        for args, want in ((("on", "codex"), codex % "1"), (("off", "codex"), codex % "0"),
                           (("on", "gemini"), shell % ("Gemini CLI", "1")), (("off", "gemini"), shell % ("Gemini CLI", "0")),
                           (("on", "antigravity"), shell % ("Antigravity", "1")), (("off", "antigravity"), shell % ("Antigravity", "0"))):
            assert switch(*args) == (0, want, ""), (args, switch(*args))
            assert os.listdir(cfg) == [], (args, os.listdir(cfg))
        usage = "usage: doctor.py feedback on|off <claude|codex|gemini|antigravity>\n"
        for args in ((), ("on",), ("off",), ("on", "nosuch"), ("sideways", "claude"), ("on", "claude", "extra"), ("claude", "on")):
            assert switch(*args) == (1, "", usage), (args, switch(*args))
            assert os.listdir(cfg) == [], (args, os.listdir(cfg))
        st = os.path.join(cfg, "settings.json")
        code, said, err = switch("on", "claude")                                     # no file yet: created, no backup
        assert (code, err) == (0, "") and json.load(open(st)) == {"env": {"KISS_FEEDBACK": "1"}} and os.listdir(cfg) == ["settings.json"], (code, err)
        assert said == "feedback mode on in %s\nClaude Code: start a new session for it to apply.\n" % st + last, said
        with open(st, "w") as f:
            json.dump({"model": "x"}, f)
        code, said, err = switch("off", "claude")
        assert code == 0 and json.load(open(st)) == {"model": "x", "env": {"KISS_FEEDBACK": "0"}}, (code, err)
        assert len(glob.glob(st + ".kiss-backup-*")) == 1 and "(backup: %s" % st in said, said
        for other in ("Codex", "Gemini", "Antigravity", "export"):
            assert other not in said, said
        kept = open(st, "rb").read()
        os.mkdir(st + ".kiss-new")                                                   # a failure after the first write: the temp file's path
        code, said, err = switch("on", "claude")
        assert code == 1 and said == "" and st in err and len(err.splitlines()) == 1 and "Traceback" not in err, (code, said, err)
        assert open(st, "rb").read() == kept, "a failed write leaves the file as it was"
        os.rmdir(st + ".kiss-new")
        for bad in (b"\xff\xfe{", b"[1]", b"{ not json"):
            with open(st, "wb") as f:
                f.write(bad)
            code, said, err = switch("on", "claude")
            assert code == 1 and said == "" and st in err and len(err.splitlines()) == 1 and "Traceback" not in err, (bad, code, said, err)
            assert open(st, "rb").read() == bad, bad
        os.remove(st)
        os.mkdir(st)                                                                 # a folder at the settings path
        code, said, err = switch("on", "claude")
        assert code == 1 and said == "" and st in err and len(err.splitlines()) == 1 and "Traceback" not in err and os.path.isdir(st), (code, said, err)
        os.rmdir(st)
        cfg = os.path.join(cfg, "a file")                                            # the config folder's path is a file
        open(cfg, "w").close()
        code, said, err = switch("on", "claude")
        assert code == 1 and "a file" in err and len(err.splitlines()) == 1 and "Traceback" not in err, (code, said, err)
    cfg = '[plugins."kiss@kiss"]\nenabled = true\n\n[plugins."old@m"]\nenabled = false\n[tui]\nenabled = true\n'
    assert codex_enabled(cfg) == ["kiss@kiss"], codex_enabled(cfg)
    # setup: the plan on fake systems; each expected command is the README's or the upstream's own
    base = {"os": "macos", "shell": "zsh", "pm": "nb", "agents": ["claude", "codex"], "repo": "/r/my app", "bin": "/b",
            "kiss": "/k"}
    sysfor = lambda **kw: dict(base, **kw)
    show = lambda items: [(i["what"], i["agent"], [" ".join(c) for c in i["run"]], i["hand"]) for i in items]
    tools = {"git": {}, "python": {}, "node": {}}
    assert show(plan(sysfor(), tools)) == [("git", "device", ["nb install git"], ""),
                                           ("Python 3.9 or later", "device", ["nb install python"], ""),
                                           ("Node.js and npm", "device", ["nb install node"], "")], show(plan(sysfor(), tools))
    assert [c for i in plan(sysfor(pm="brew"), tools) for c in i["run"]] == [["brew", "install", p] for p in ("git", "python", "node")]
    assert [c for i in plan(sysfor(os="windows", pm="winget"), tools) for c in i["run"]] == [
        ["winget", "install", "-e", "--id", p] for p in ("Git.Git", "Python.Python.3.12", "OpenJS.NodeJS.LTS")]
    apt = plan(sysfor(os="linux", pm="apt"), {"git": {}, "node": {}})       # sudo: shown for the owner, never numbered
    assert [i["run"] for i in apt] == [["sudo apt install -y git".split()], ["sudo apt install -y nodejs npm".split()]], apt
    assert all("sudo" in i["hand"] and i["n"] is None for i in apt), apt
    none = plan(sysfor(os="linux", pm=None), {"git": {}})                    # no package manager: the download link only
    assert none[0]["run"] == [] and none[0]["n"] is None and "https://git-scm.com/downloads" in none[0]["hand"], none
    assert "package manager" not in none[0]["changes"] and "the link" in none[0]["changes"], none     # F10
    known = {"codegraph": {}, "cgcallers": {}, "index": {}, ("claude", "Install ponytail"): {},
            ("codex", "Install ponytail"): {}, ("codex", "Install Matt Pocock's skills"): {},
            ("claude", "rule-new"): {"copy": "/h/.claude/rules/kiss.md"}, ("gemini", "Install ponytail"): {}}
    got = show(plan(sysfor(), known))
    assert got == [
        ("CodeGraph", "device", ["npm install -g @colbymchenry/codegraph"], ""),
        ("cgcallers", "device", ["install -m 755 /k/skills/kiss-harness/scripts/cgcallers.py /b/cgcallers"], ""),
        ("the CodeGraph index of this repo", "device", ["codegraph init /r/my app"], ""),
        ("the CodeGraph rule", "claude", ["write /k/rules/codegraph.md to /h/.claude/rules/kiss.md"], ""),
        ("ponytail", "claude", ["claude plugin marketplace add DietrichGebert/ponytail", "claude plugin install ponytail@ponytail"], ""),
        ("ponytail", "codex", ["codex plugin marketplace add DietrichGebert/ponytail", "codex plugin add ponytail@ponytail"], ""),
        ("Matt Pocock's skills", "codex", ["codex plugin marketplace add mattpocock/skills", "codex plugin add mattpocock-skills@mattpocock"], ""),
    ], got                                                                    # gemini is not on PATH: not planned
    assert show(plan(sysfor(), {("claude", "Install Matt Pocock's skills"): {}}))[0][2] == [    # his own marketplace
        "claude plugin marketplace add mattpocock/skills", "claude plugin install mattpocock-skills@mattpocock"]
    items = plan(sysfor(), known)
    assert [i["n"] for i in items] == [1, 2, 3, 4, 5, 6, 7] and all(i["source"] and i["changes"] for i in items), items
    assert "/hooks" in items[5]["after"] and items[4]["after"] == "", items
    assert items[2]["run"] == [["codegraph", "init", "/r/my app"]]     # a path with a space stays one word
    assert command(items[2]["run"][0]) == "codegraph init '/r/my app'"
    shared = plan(sysfor(agents=["gemini", "antigravity"]), {("gemini", "rule"): {"file": "/h/.gemini/GEMINI.md"},
                                                             ("antigravity", "rule"): {"file": "/h/.gemini/GEMINI.md"},
                                                             ("gemini", "Install ponytail"): {}, ("antigravity", "Install ponytail"): {},
                                                             ("antigravity", "Install KISS"): {}})
    assert show(shared) == [
        ("the CodeGraph rule", "gemini", ["cat /k/rules/codegraph.md >> /h/.gemini/GEMINI.md"], ""),   # one file, appended once
        ("KISS", "antigravity", [], "by hand: git clone https://github.com/Rex57/KISS.git, then agy plugin install ./KISS"),
        ("ponytail", "gemini", ["gemini extensions install https://github.com/DietrichGebert/ponytail --consent"], ""),
        ("ponytail", "antigravity", [], "by hand: follow https://github.com/DietrichGebert/ponytail/blob/main/INSTALL.md"),
    ], show(shared)
    # D4: one replace item per file (Gemini CLI and Antigravity share GEMINI.md); a file with no heading: by hand
    span = {"first": "## CodeGraph", "until": 'just before "## Mine"'}
    two = plan(sysfor(agents=["gemini", "antigravity"]), {(a, "rule-replace"): dict(span, file="/h/.gemini/GEMINI.md") for a in ("gemini", "antigravity")})
    assert show(two) == [("replace the CodeGraph section of /h/.gemini/GEMINI.md", "gemini",
                          ["replace the CodeGraph section of /h/.gemini/GEMINI.md with /k/rules/codegraph.md"], "")], show(two)
    assert two[0]["n"] == 1 and "own lines inside that section are lost, and kept in the backup" in two[0]["changes"], two
    assert two[0]["changes"].startswith('replaces the lines of /h/.gemini/GEMINI.md from "## CodeGraph" to just before "## Mine" '), two
    hand = plan(sysfor(), {("claude", "rule-replace"): {"file": "/h/c.md", "hand": "no heading above the rule in /h/c.md"}})
    assert show(hand) == [("replace the CodeGraph section of /h/c.md", "claude", [], "by hand: no heading above the rule in /h/c.md")]
    assert hand[0]["changes"] == "nothing: setup does not change the file", hand
    later = plan(sysfor(), {("claude", "rule-replace"): dict(span, file="/h/c.md", until="the end of the file")})
    assert plan_id(later) != plan_id(plan(sysfor(), {("claude", "rule-replace"): dict(span, file="/h/c.md")})), "the id covers the lines"
    assert hand[0]["n"] is None, hand
    text = "\n".join(plan_lines(sysfor(os="linux", pm="apt"), plan(sysfor(os="linux", pm="apt"), dict(known, git={}))))
    for want in ("1. CodeGraph (device)", "   command: npm install -g @colbymchenry/codegraph",
                 "   source:  https://github.com/colbymchenry/codegraph", "sudo apt install -y git", "needs sudo",
                 "agentmemory: https://github.com/rohitg00/agentmemory", "all, none, or the numbers"):
        assert want in text, (want, text)
    assert "Nothing to install" in "\n".join(plan_lines(sysfor(), []))
    # setup --apply with a fake runner: commands are recorded, not run
    ran = []
    def runner(fail=()):
        def go(argv):
            ran.append(" ".join(argv))
            return (1, "npm ERR! 404 not found") if " ".join(argv) in fail else (0, "")
        return go
    checked = []                                              # the agents each run of the checks covered
    checks = lambda agents: (checked.append(agents), ["CHECKS AGAIN"])[1]
    go = lambda s, a, r, f: setup(s, a, r, f, checks, pid=plan_id(plan(s, f(s))))   # the id the plan showed
    find = lambda system: known                               # numbered: 1 CodeGraph, 2 cgcallers, 3 index, 4 rule, 5-7 plugins
    lines, ok = go(sysfor(os="linux", pm="apt"), "1,3", runner(), lambda system: dict(known, git={}))
    assert ok and ran == ["npm install -g @colbymchenry/codegraph", "codegraph init /r/my app"], ran
    text = "\n".join(lines)
    assert "CHECKS AGAIN" in text and "sudo apt install -y git" in text and "start a new session" not in text, text
    ran.clear()
    lines, ok = go(sysfor(), "6, 5,5", runner(), find)     # the plan's order, each once; the /hooks step after
    assert ok and ran == ["claude plugin marketplace add DietrichGebert/ponytail", "claude plugin install ponytail@ponytail",
                          "codex plugin marketplace add DietrichGebert/ponytail", "codex plugin add ponytail@ponytail"], ran
    assert "/hooks" in "\n".join(lines) and "start a new session" in "\n".join(lines), lines
    ran.clear()
    lines, ok = go(sysfor(), "all", runner(fail={"codegraph init /r/my app"}), find)
    text = "\n".join(lines)
    assert not ok and ran == ["npm install -g @colbymchenry/codegraph",
                              "install -m 755 /k/skills/kiss-harness/scripts/cgcallers.py /b/cgcallers",
                              "codegraph init /r/my app"], ran              # stops at the first failure
    for want in ("done 1. CodeGraph", "done 2. cgcallers", "FAIL 3.", "codegraph init '/r/my app'", "npm ERR! 404",
                 "not run: 4, 5, 6, 7", "CHECKS AGAIN"):
        assert want in text, (want, text)
    for answer in ("8", "0", "1,x", "rm -rf /", "", "²", "٣"):   # outside the plan: refused, nothing runs (F6)
        ran.clear()
        lines, ok = go(sysfor(), answer, runner(), find)
        assert not ok and ran == [] and "refused" in lines[0] and "CHECKS AGAIN" not in lines, (answer, lines)
    ran.clear()
    lines, ok = go(sysfor(), "none", runner(), find)
    assert ok and ran == [] and lines[0] == "none picked: nothing ran", lines
    assert "none picked: nothing ran" not in go(sysfor(), "1", runner(), find)[0], "an answer that picks an item"
    byhand = lambda system: {("claude", "rule-replace"): {"file": "/h/c.md", "hand": "no heading above the rule in /h/c.md"}}
    lines, ok = go(sysfor(), "all", runner(), byhand)                       # no numbered item: `all` picked all of none
    assert ok and "none picked: nothing ran" not in lines, lines
    assert go(sysfor(), "none", runner(), byhand)[0][0] == "none picked: nothing ran", "the answer none, as before"
    ran.clear()
    sudo = [{"n": 1, "what": "git", "agent": "device", "run": [["sudo", "apt", "install", "-y", "git"]], "hand": "",
             "source": "s", "changes": "c", "after": ""}]
    lines, ok, *_ = apply(sudo, "1", runner())                              # a sudo command never runs, even if numbered
    assert not ok and ran == [] and "sudo" in lines[0], lines
    # F5: a failed item installed nothing: no steps after it, but the checks run again
    text = "\n".join(go(sysfor(), "6", runner(fail={"codex plugin marketplace add DietrichGebert/ponytail"}), find)[0])
    assert "CHECKS AGAIN" in text and "/hooks" not in text and "start a new session" not in text, text
    # F2: the plan changed since the owner saw it (CodeGraph installed by hand): refused, nothing runs
    pid = plan_id(plan(sysfor(), known))
    assert f"--plan {pid}" in "\n".join(plan_lines(sysfor(), plan(sysfor(), known)))
    ran.clear()
    lines, ok = setup(sysfor(), "2", runner(), lambda s: {k: v for k, v in known.items() if k != "codegraph"}, checks, pid=pid)
    assert not ok and ran == [] and "the plan changed" in lines[0], lines
    # D15: the checks after an install leave out each agent whose numbered items the owner picked none of, in one line
    for answer, agents, left in (("5", ["claude"], "codex"), ("6", ["codex"], "claude"), ("1", [], "claude, codex"),
                                 ("all", ["claude", "codex"], None)):
        checked.clear()
        lines, ok = go(sysfor(), answer, runner(), find)          # 1-3 device, 4-5 claude, 6-7 codex
        named = [l for l in lines if l.startswith("left out of the checks")]
        assert ok and checked == [agents] and named == ([f"left out of the checks (you picked none of their items): {left}"]
                                                        if left else []), (answer, checked, lines)
    checked.clear()
    assert go(sysfor(), "none", runner(), find)[1] and checked == []     # nothing ran: no checks, as before
    hand_only = {"git": {}, ("claude", "Install ponytail"): {},
                 ("codex", "rule-replace"): {"file": "/h/a.md", "hand": "no heading above the rule in /h/a.md"}}
    lines, ok = go(sysfor(), "1", runner(), lambda system: hand_only)
    assert ok and checked == [["codex"]], (checked, lines)    # codex had only a step by hand: it stays in the checks
    # setup AGENT ...: only those agents (an agent the owner skips is not planned or checked); the plan's last line
    # names them, so --apply builds the same plan
    on = ["claude", "codex"]
    assert setup_args([], on) == (on, None, None) and setup_args(["claude"], on) == (["claude"], None, None)
    assert setup_args(["codex", "claude", "--apply", "1,3", "--plan", "ab12"], on) == (on, "1,3", "ab12")
    assert setup_args(["--apply", "all", "--plan", "ab12"], on) == (on, "all", "ab12")
    for bad in (["gemini"], ["nope"], ["--apply", "1"], ["claude", "--apply", "1", "--plan"], ["-x"],
                ["--plan", "x", "--apply", "1"], ["--apply", "1", "--plan", "x", "codex"]):
        try:
            setup_args(bad, on)
            raise AssertionError(bad)
        except SystemExit as e:
            assert "usage" in str(e) or "not an agent on PATH: gemini (on PATH: claude, codex)" in str(e) or \
                "nope" in str(e), (bad, e)
    mine = plan(sysfor(agents=["claude"]), known)
    assert [i["agent"] for i in mine] == ["device"] * 3 + ["claude"] * 2, show(mine)
    assert "then: setup claude --apply <answer>" in "\n".join(plan_lines(sysfor(agents=["claude"]), mine))
    assert "then: setup claude codex --apply" in "\n".join(plan_lines(sysfor(), plan(sysfor(), known)))
    # the two file commands run in Python: the rule appended once, cgcallers copied executable
    with tempfile.TemporaryDirectory() as fx:
        dst, src = os.path.join(fx, "home", "CLAUDE.md"), os.path.join(fx, "rule.md")
        os.makedirs(os.path.dirname(dst))
        for path, text in ((dst, "mine"), (src, "**Which index.** a\n")):
            with open(path, "w") as f:
                f.write(text)
        assert execute(["cat", src, ">>", dst]) == (0, "") and read(dst) == "mine\n**Which index.** a\n", read(dst)
        exe = os.path.join(fx, "bin", "cgcallers")
        assert execute(["install", "-m", "755", src, exe]) == (0, "") and os.access(exe, os.X_OK) and read(exe) == read(src)
    assert execute(["no-such-command-kiss"])[0] != 0
    code, out = execute([sys.executable, "-c", "import time; time.sleep(5)"], timeout=1)       # F12: a stall ends as a FAIL
    assert code != 0 and "timed out" in out and TIMEOUT <= 300, (code, out)
    gemini = [c for r in INSTALL for c in r.get("agents", {}).get("gemini", []) if c.startswith("gemini ") and " mcp " not in c]
    assert len(gemini) == 4 and all(c.endswith(" --consent") for c in gemini), gemini   # no [Y/n] question
    # T-8: the language servers and CodeGraph's MCP server for each agent, through the agent's own command
    four = sysfor(agents=["claude", "codex", "gemini", "antigravity"])
    got = show(plan(four, {"pyright": {}, "typescript-language-server": {}, ("claude", "mcp"): {"settings": "/h/.claude/settings.json"},
                           ("codex", "mcp"): {}, ("gemini", "mcp"): {}, ("antigravity", "mcp"): {}}))
    assert got[:2] == [("pyright (optional: cgcallers' LSP pass for Python)", "device", ["npm install -g pyright"], ""),
                       ("typescript-language-server (optional: cgcallers' LSP pass for JS/TS)", "device",
                        ["npm install -g typescript-language-server typescript@5"], "")], got
    assert got[2:] == [
        ("CodeGraph's MCP server", "claude", ["claude mcp add --scope user codegraph -- codegraph serve --mcp",
                                              "allow mcp__codegraph__* in /h/.claude/settings.json"], ""),
        ("CodeGraph's MCP server", "codex", ["codex mcp add codegraph -- codegraph serve --mcp"], ""),
        ("CodeGraph's MCP server", "gemini", ["gemini mcp add --scope user codegraph codegraph serve --mcp"], ""),
        ("CodeGraph's MCP server", "antigravity", [], "by hand: in Antigravity's MCP settings, add a server named codegraph"
                                                      " that runs: codegraph serve --mcp")], got
    mcp_items = [i for i in plan(four, {(a, "mcp"): {"settings": "/s"} for a in ("claude", "codex", "gemini")})]
    assert not any("Claude Code" in i["changes"] or "mcp__" in i["changes"] for i in mcp_items if i["agent"] != "claude"), mcp_items  # R9
    assert not any("codegraph install" in c for r in INSTALL for c in r.get("run", []) + [
        x for cs in r.get("agents", {}).values() for x in cs]), "never codegraph install (D10)"
    with tempfile.TemporaryDirectory() as fx:                 # the permission: added once, after a backup
        st = os.path.join(fx, "settings.json")
        with open(st, "w") as f:
            json.dump({"permissions": {"allow": ["Read"]}, "model": "opus"}, f)
        assert execute(["allow", "mcp__codegraph__*", "in", st]) == (0, "")
        assert execute(["allow", "mcp__codegraph__*", "in", st]) == (0, "")
        assert json.load(open(st)) == {"permissions": {"allow": ["Read", "mcp__codegraph__*"]}, "model": "opus"}, read(st)
        assert len(glob.glob(st + ".kiss-backup-*")) == 2
        for name, files in (("py", ["a.py"]), ("ts", ["web/b.ts"]), ("docs", ["README.md"])):
            for f in files:
                os.makedirs(os.path.dirname(os.path.join(fx, name, f)), exist_ok=True)
                open(os.path.join(fx, name, f), "w").close()
        assert servers_wanted(os.path.join(fx, "py")) == ["pyright"]
        assert servers_wanted(os.path.join(fx, "ts")) == ["typescript-language-server"]
        assert servers_wanted(os.path.join(fx, "docs")) == [] and servers_wanted(None) == []
    stdin_is_null = "import os,sys; sys.exit(0 if os.fstat(0).st_rdev == os.stat(os.devnull).st_rdev else 3)"
    assert execute([sys.executable, "-c", stdin_is_null])[0] == 0      # a question reads end of input, never waits
    # gaps() and detect() on this KISS folder, with a scratch Codex home that has nothing
    assert all(k in {r["key"] for r in INSTALL} for k in set(required().values())), required()
    # the real skill tables (the harness's, kiss-code-clean's, kiss-mini's): a table format change cannot drop a skill silently
    assert {"grilling", "tdd", "ponytail", "ponytail-review", "research"} <= set(required()), sorted(required())
    old_env = {k: os.environ.get(k) for k in ("CODEX_HOME", "PATH", "KISS_BIN", "CLAUDE_CONFIG_DIR")}
    with tempfile.TemporaryDirectory() as fx:
        try:
            os.environ["CODEX_HOME"] = os.path.join(fx, "codex")
            found = gaps({"agents": ["codex"], "repo": None, "bin": os.path.join(fx, "bin")})
            assert found[("codex", "rule")] == {"file": os.path.join(fx, "codex", "AGENTS.md")}, found
            for key in ("Install KISS", "Install ponytail", "Install Matt Pocock's skills"):
                assert ("codex", key) in found, (key, found)
            os.makedirs(os.path.join(fx, "path"))
            for name in ("apt", "brew", "codex"):                 # the first package manager in PMS order wins
                with open(os.path.join(fx, "path", name), "w") as f:
                    f.write("#!/bin/sh\n")
                os.chmod(os.path.join(fx, "path", name), 0o755)
            os.environ["PATH"] = os.path.join(fx, "path")
            os.environ["KISS_BIN"] = os.path.join(fx, "bin")
            got = detect()
            assert (got["pm"], got["agents"], got["repo"], got["bin"]) == ("brew", ["codex"], None, os.path.join(fx, "bin")), got
            assert "cgcallers" in gaps(dict(got, agents=[]))
            repo = os.path.join(fx, "repo")                            # T-8: a server per language the repo has
            os.makedirs(os.path.join(repo, "web"))
            open(os.path.join(repo, "a.py"), "w").close()
            assert "pyright" in gaps(dict(got, agents=[], repo=repo)) and "typescript-language-server" not in gaps(dict(got, agents=[], repo=repo))
            open(os.path.join(repo, "web", "b.tsx"), "w").close()
            assert "typescript-language-server" in gaps(dict(got, agents=[], repo=repo))
            assert not {"pyright", "typescript-language-server"} & set(gaps(dict(got, agents=[], repo=None)))
            # R7, R8: the MCP item from each agent's own `mcp list` (fake CLIs), and Claude Code's permission
            def cli(name, mcp_out):
                with open(os.path.join(fx, "path", name), "w") as f:
                    f.write('#!/bin/sh\n[ "$1" = plugin ] && echo "[]" && exit 0\necho "%s"\n' % mcp_out)
                os.chmod(os.path.join(fx, "path", name), 0o755)
            os.environ["CLAUDE_CONFIG_DIR"] = os.path.join(fx, "ccd")
            cli("codex", "")
            assert ("codex", "mcp") in gaps(dict(got, agents=["codex"])) and check_mcp("codex")[0][0] == "INFO"
            cli("codex", "codegraph  codegraph  serve --mcp  -  -  enabled")
            assert ("codex", "mcp") not in gaps(dict(got, agents=["codex"])) and check_mcp("codex")[0][0] == "OK"
            cli("claude", "codegraph: codegraph serve --mcp - Connected")
            found = gaps(dict(got, agents=["claude"]))
            assert ("claude", "mcp") not in found and found[("claude", "mcp-allow")] == {"settings": settings_path()}, found
            assert check_mcp("claude")[0][0] == "WARN"
            assert show(plan(dict(got, agents=["claude"]), {("claude", "mcp-allow"): found[("claude", "mcp-allow")]})) == [
                ("CodeGraph's MCP tools allowed (Claude Code)", "claude", ["allow mcp__codegraph__* in " + settings_path()], "")]
            execute(["allow", "mcp__codegraph__*", "in", settings_path()])
            assert ("claude", "mcp-allow") not in gaps(dict(got, agents=["claude"])) and check_mcp("claude")[0][0] == "OK"
            assert check_mcp("antigravity")[0][0] == "INFO"
            # D4: each WARN kind of the rule gets a numbered replace item naming its file; an OK copy and a FAIL none
            real = read(os.path.join(KISS, "rules", "codegraph.md"))
            def items(agent, path, text):
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w") as f:
                    f.write(text)
                found = gaps(dict(got, agents=[agent]))
                return [i for i in plan(dict(got, agents=[agent]), found) if i["what"].startswith("replace the CodeGraph")], found
            md = os.path.join(fx, "codex", "AGENTS.md")
            edited = "# Me\n\n" + real.replace("Decide once per checkout", "Decide per checkout") + "## Mine\nx\n"
            older = "# Me\n\n" + real.split("**Subagents**")[0] + "## Mine\nx\n"
            for text in (edited, older):
                mine, _ = items("codex", md, text)
                assert [(bool(i["n"]), i["what"]) for i in mine] == [(True, "replace the CodeGraph section of " + os.path.realpath(md))], mine
                assert mine[0]["changes"].startswith('replaces the lines of %s from "## CodeGraph — the rule" to just before "## Mine" '
                                                     'with all of rules/codegraph.md' % os.path.realpath(md)), mine
            mine, _ = items("codex", md, edited.split("## Mine")[0])           # the section is the file's last
            assert ' to the end of the file with ' in mine[0]["changes"], mine
            for text in ("# Me\n\n" + real, "# Me\n" + real + "### My CodeGraph notes\n- a note\n## Last\n", "nothing"):   # OK (S14: K), FAIL
                mine, found = items("codex", md, text)
                assert mine == [] and (("codex", "rule") in found) == (text == "nothing"), (mine, found)
            nothing = "nothing: setup does not change the file"             # a step by hand promises no backup
            mine, _ = items("codex", md, "intro\n" + real.split("\n", 1)[1].replace("Decide once", "Decide"))   # no heading
            assert [(i["n"], i["hand"].startswith("by hand: no heading above"), i["changes"]) for i in mine] == [(None, True, nothing)], mine
            mine, _ = items("codex", md, "## CodeGraph\n- Which index: decide once.\n- Keep it fresh: sync.\n")   # no bold lead-in
            assert [(i["n"], i["hand"].startswith("by hand: no bold lead-in of the rule in "), i["changes"]) for i in mine] == [(None, True, nothing)], mine
            with open(md, "wb") as f:                                   # not UTF-8: a step by hand, not an item that fails
                f.write(b"# Me\n\xe9t\xe9\n\n" + edited.encode())
            mine = [i for i in plan(dict(got, agents=["codex"]), gaps(dict(got, agents=["codex"]))) if i["what"].startswith("replace the CodeGraph")]
            assert [(i["n"], "UTF-8" in i["hand"], i["changes"]) for i in mine] == [(None, True, nothing)], mine
            # the rule in an @-imported file: that file changes, the importing file (with the owner's own bold word of a
            # lead-in) does not; the checks then say OK
            cmd = os.path.join(fx, "ccd", "CLAUDE.md")
            put_cg = os.path.join(fx, "ccd", "rules", "cg.md")
            os.makedirs(os.path.dirname(put_cg))
            with open(put_cg, "w") as f:
                f.write(edited)
            mine, _ = items("claude", cmd, "intro\n**Subagents**: brief them like a peer.\n@rules/cg.md\n")
            assert [i["what"] for i in mine] == ["replace the CodeGraph section of " + os.path.realpath(put_cg)], mine
            lines, ok, *_ = apply(mine, str(mine[0]["n"]))
            assert ok and lines[1].startswith("   backup: ") and read(cmd) == "intro\n**Subagents**: brief them like a peer.\n@rules/cg.md\n", lines
            assert read(put_cg) == "# Me\n\n" + real + "\n## Mine\nx\n", read(put_cg)
            assert check_rule("claude", with_imports(cmd), [cmd], markers(), real)[0][0] == "OK"
            # Claude Code's rule file: rules/kiss.md under the config folder (D13, D15, D16, D19, D28)
            n_cfg = [0]

            def fresh(main_text=None):
                n_cfg[0] += 1
                c = os.path.join(fx, "cfg %d" % n_cfg[0])
                os.makedirs(c)
                os.environ["CLAUDE_CONFIG_DIR"] = c
                if main_text is not None:
                    write_file(os.path.join(c, "CLAUDE.md"), main_text)
                return c, os.path.join(c, "CLAUDE.md"), os.path.join(c, "rules", "kiss.md")

            def write_file(path, text):
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8", newline="") as f:
                    f.write(text)

            def rule_items():
                claude_sys = dict(got, agents=["claude"])
                return [i for i in plan(claude_sys, gaps(claude_sys)) if "CodeGraph rule" in i["what"] or "CodeGraph section" in i["what"]]

            def level():
                text, files, _, _ = agent_setup("claude")
                return check_rule("claude", text, files, markers(), real)[0][0]
            whole = lambda p: open(p, "rb").read().decode("utf-8") if os.path.isfile(p) else None
            stale = real.replace("Decide once per checkout", "Decide per checkout")
            # no rule anywhere, with and without an own CLAUDE.md
            for own in (None, "mine\n"):
                c, main_md, copy = fresh(own)
                assert level() == "FAIL"
                mine = rule_items()
                assert len(mine) == 1 and mine[0]["run"] == [["write", os.path.join(KISS, "rules", "codegraph.md"), "to", copy]], mine
                assert copy in mine[0]["changes"] and "CLAUDE.md" not in mine[0]["changes"] + mine[0]["what"], mine
                assert "start a new session" in mine[0]["changes"], mine
                lines, ok, *_ = apply(mine, "all")
                assert ok and whole(copy) == real and whole(main_md) == own and level() == "OK" and rule_items() == [], lines
            # a stale section with own lines above and below: the move
            c, main_md, copy = fresh("# Me\n\nabove\n\n" + stale + "\n\n## Mine\nbelow\n")
            old = whole(main_md)
            assert level() == "WARN"
            mine = rule_items()
            assert len(mine) == 1 and mine[0]["what"] == "move the CodeGraph section of %s to %s" % (os.path.realpath(main_md), copy), mine
            assert copy in mine[0]["changes"] and os.path.realpath(main_md) in mine[0]["changes"] and "backup" in mine[0]["changes"] and "start a new session" in mine[0]["changes"], mine
            lines, ok, *_ = apply(mine, "all")
            backups = glob.glob(main_md + ".kiss-backup-*")
            assert ok and whole(copy) == real and whole(main_md) == "# Me\n\nabove\n\n## Mine\nbelow\n", (lines, whole(main_md))
            assert len(backups) == 1 and whole(backups[0]) == old and backups[0] in " ".join(lines), lines
            assert level() == "OK" and rule_items() == [], "a re-run after a move offers nothing"
            # the section last in the file; a CODEGRAPH_START block stays whole; a CRLF file keeps its line ends
            for before, after in (("# Me\n\nabove\n\n" + stale, "# Me\n\nabove\n"),
                                  ("# Me\n\n" + stale + "\n<!-- CODEGRAPH_START -->\nb\n<!-- CODEGRAPH_END -->\n## Last\n",
                                   "# Me\n\n<!-- CODEGRAPH_START -->\nb\n<!-- CODEGRAPH_END -->\n## Last\n"),
                                  ("# Me\r\n\r\nabove\r\n\r\n" + stale + "\r\n## Mine\r\n", "# Me\r\n\r\nabove\r\n\r\n## Mine\r\n")):
                c, main_md, copy = fresh(before)
                lines, ok, *_ = apply(rule_items(), "all")
                assert ok and whole(main_md) == after, (lines, whole(main_md))
            # an exact section: no item, no write
            c, main_md, copy = fresh("# Me\n\n" + real + "\n## Mine\n")
            assert level() == "OK" and rule_items() == [] and not os.path.exists(copy) and sorted(os.listdir(c)) == ["CLAUDE.md"]
            # a stale and an edited copy: the replace item, a backup whose name does not end in .md
            for text in (real.split("**Subagents**")[0], stale):
                c, main_md, copy = fresh("mine\n")
                write_file(copy, text)
                mine = rule_items()
                assert [i["what"] for i in mine] == ["replace the CodeGraph section of " + os.path.realpath(copy)], mine
                lines, ok, *_ = apply(mine, "all")
                backups = glob.glob(copy + ".kiss-backup-*")
                assert ok and whole(copy) == real and whole(main_md) == "mine\n" and len(backups) == 1 and whole(backups[0]) == text, lines
                assert not backups[0].endswith(".md") and "start a new session" in mine[0]["after"], (backups, mine)
                assert not glob.glob(os.path.join(c, "rules", "*.kiss-new")) and rule_items() == [] and level() == "OK"
            # F11: the backup fails after the copy (a name too long for the backup): the message says two copies load
            c, main_md, copy = fresh()
            long_name = os.path.join(c, "C" * 240 + ".md")
            write_file(long_name, "# Me\n\n" + stale + "\n## Mine\n")
            code, said = execute(["move", "the", "CodeGraph", "section", "of", long_name, "to", copy, "with", os.path.join(KISS, "rules", "codegraph.md")])
            assert code == 1 and "two copies load until a re-run" in said and whole(copy) == real and whole(long_name).endswith("## Mine\n") and stale in whole(long_name), said
            # the first write fails: a folder at the copy's path
            c, main_md, copy = fresh("# Me\n\n" + stale + "\n## Mine\n")
            old = whole(main_md)
            os.makedirs(copy)
            lines, ok, *_ = apply(rule_items(), "all")
            said = "\n".join(lines)
            assert not ok and whole(main_md) == old and "unchanged" in said and os.path.isdir(copy) and not glob.glob(main_md + ".kiss-backup-*"), said
            # the second write fails: a folder at CLAUDE.md's temp file; a re-run ends with one copy
            c, main_md, copy = fresh("# Me\n\n" + stale + "\n## Mine\n")
            old = whole(main_md)
            os.mkdir(main_md + ".kiss-new")
            lines, ok, *_ = apply(rule_items(), "all")
            said = "\n".join(lines)
            backups = glob.glob(main_md + ".kiss-backup-*")
            assert not ok and whole(main_md) == old and whole(copy) == real and len(backups) == 1 and whole(backups[0]) == old, said
            assert "two copies load until a re-run" in said and backups[0] in said, said
            assert level() == "WARN", "two copies load: the check does not say OK"
            os.rmdir(main_md + ".kiss-new")
            lines, ok, *_ = apply(rule_items(), "all")
            assert ok and whole(main_md) == "# Me\n\n## Mine\n" and level() == "OK" and rule_items() == [], lines
            # an interrupt after the copy, before the section's removal: stale or exact, the next setup ends with one copy
            for section_text in (stale, real):
                c, main_md, copy = fresh("# Me\n\n" + section_text + "\n## Mine\n")
                write_file(copy, real)
                mine = rule_items()
                assert [i["what"].startswith("move the CodeGraph section") for i in mine] == [True], mine
                lines, ok, *_ = apply(mine, "all")
                assert ok and whole(main_md) == "# Me\n\n## Mine\n" and whole(copy) == real and rule_items() == [], lines
            # a section and a stale copy: the copy's old text goes to a backup too
            c, main_md, copy = fresh("# Me\n\n" + stale + "\n## Mine\n")
            write_file(copy, stale)
            lines, ok, *_ = apply(rule_items(), "all")
            backups = glob.glob(copy + ".kiss-backup-*")
            assert ok and whole(copy) == real and len(backups) == 1 and whole(backups[0]) == stale and not backups[0].endswith(".md"), lines
            # an interrupted write's temp file loads nothing
            c, main_md, copy = fresh("mine\n")
            write_file(copy + ".kiss-new", real)
            assert level() == "FAIL"
            # a CLAUDE.md with bad bytes stops before any write
            c, main_md, copy = fresh()
            with open(main_md, "wb") as f:
                f.write(b"# Me\n\xe9t\xe9\n\n" + stale.encode() + b"\n## Mine\n")
            old = open(main_md, "rb").read()
            mine = rule_items()
            assert [(i["n"], "UTF-8" in i["hand"]) for i in mine] == [(None, True)], mine
            code, said = execute(["move", "the", "CodeGraph", "section", "of", main_md, "to", copy, "with", os.path.join(KISS, "rules", "codegraph.md")])
            assert code == 1 and not os.path.exists(copy) and open(main_md, "rb").read() == old and not glob.glob(main_md + ".kiss-backup-*"), said
            # a symlinked CLAUDE.md keeps its link, and the target holds the change
            c, main_md, copy = fresh()
            target = os.path.join(fx, "dotfiles", "CLAUDE.md")
            write_file(target, "# Me\n\n" + stale + "\n## Mine\n")
            os.symlink(target, main_md)
            lines, ok, *_ = apply(rule_items(), "all")
            assert ok and os.path.islink(main_md) and whole(target) == "# Me\n\n## Mine\n" and whole(copy) == real, lines
            write_file(os.path.join(fx, "dotfiles", "settings.json"), "{}")     # a link stays a link in the settings write too
            os.symlink(os.path.join(fx, "dotfiles", "settings.json"), settings_path())
            set_feedback(settings_path(), True)
            assert os.path.islink(settings_path()) and json.load(open(os.path.join(fx, "dotfiles", "settings.json"))) == {"env": {"KISS_FEEDBACK": "1"}}
            # four hops load, a fifth does not; a rule in a subfolder of rules/ counts
            c, main_md, copy = fresh("@a.md\n")
            for this, nxt in (("a", "b"), ("b", "c"), ("c", "d")):
                write_file(os.path.join(c, this + ".md"), "@%s.md\n" % nxt)
            write_file(os.path.join(c, "d.md"), real)
            assert level() == "OK", "the rule at hop 4"
            write_file(os.path.join(c, "d.md"), "@e.md\n")
            write_file(os.path.join(c, "e.md"), real)
            assert level() == "FAIL", "the rule at hop 5"
            c, main_md, copy = fresh()
            write_file(os.path.join(c, "rules", "sub", "x.md"), real)
            assert level() == "OK" and rule_items() == []
            # F10: a ### rule ends at the next ###; the owner's next ### sections stay. Inside a ## section a ### stays with it
            c, main_md, copy = fresh("# Me\n## Tools\n### CodeGraph\n" + stale.split("\n", 1)[1] + "### Python\nUse uv.\n### Git\nOwn.\n## Other\n")
            mine = rule_items()
            assert 'to just before "### Python"' in mine[0]["changes"], mine
            lines, ok, *_ = apply(mine, "all")
            assert ok and whole(main_md) == "# Me\n## Tools\n\n### Python\nUse uv.\n### Git\nOwn.\n## Other\n", whole(main_md)
            c, main_md, copy = fresh("# Me\n\n" + stale + "### Inside\nx\n## Mine\n")
            lines, ok, *_ = apply(rule_items(), "all")
            assert ok and whole(main_md) == "# Me\n\n## Mine\n", whole(main_md)
            md3 = os.path.join(fx, "codex", "AGENTS.md")                # the replace has the same end
            mine, _ = items("codex", md3, "# Me\n### CodeGraph\n" + stale.split("\n", 1)[1] + "### Python\n## Other\n")
            assert 'to just before "### Python"' in mine[0]["changes"], mine
            lines, ok, *_ = apply(mine, "all")
            assert ok and whole(md3) == "# Me\n" + real + "\n### Python\n## Other\n", whole(md3)
            # F7: each file's own section is compared: an own file with no heading after an exact copy, or after an exact section
            for files in ({"CLAUDE.md": "mine\n", "rules/kiss.md": real, "rules/zz.md": "Keep tests small.\n"},
                          {"CLAUDE.md": "# Me\n\n" + real, "rules/style.md": "Keep tests small.\n"}):
                c, main_md, copy = fresh()
                for rel, text in files.items():
                    write_file(os.path.join(c, rel), text)
                assert level() == "OK" and rule_items() == [], files.keys()
            # F8, F9: an own file with a bold word or a plain word of a lead-in holds no rule: FAIL, the new copy, the file untouched
            for rel, text in (("rules/team.md", "## Team\n\n**Subagents** use a brief.\n\nOwn line.\n"),
                              ("CLAUDE.md", "## Agents\n**Subagents** use a brief.\nOwn line.\n## Other\n"),
                              ("CLAUDE.md", "Subagents get a brief.\n"), ("rules/team.md", "Subagents get a brief.\n")):
                c, main_md, copy = fresh("mine\n")
                write_file(os.path.join(c, rel), text)
                assert level() == "FAIL", (rel, text)
                mine = rule_items()
                assert [i["run"] for i in mine] == [[["write", os.path.join(KISS, "rules", "codegraph.md"), "to", copy]]], mine
                lines, ok, *_ = apply(mine, "all")
                assert ok and whole(copy) == real and whole(os.path.join(c, rel)) == text and level() == "OK" and rule_items() == [], lines
            # F9: an exact copy beside an own section with two bold lead-ins: OK, no item, no move
            c, main_md, copy = fresh("## Notes\n**Subagents** a\n**Keep it fresh** b\nOwn line.\n")
            write_file(copy, real)
            assert level() == "OK" and rule_items() == []
            # the holder test: more than half of the lead-ins, in one file, in bold
            half = [m for m in markers()][:len(markers()) // 2]
            bold = "".join("**%s** x\n" % m for m in half)
            c, main_md, copy = fresh(bold)
            assert level() == "FAIL", "half of the lead-ins"
            c, main_md, copy = fresh(bold)
            write_file(os.path.join(c, "rules", "b.md"), "**%s** x\n" % markers()[-1])
            assert level() == "FAIL", "more than half only across two files"
            c, main_md, copy = fresh("".join("%s x\n" % m for m in markers()))
            assert level() == "FAIL", "every lead-in, in plain words"
            c, main_md, copy = fresh(bold + "**%s** x\n" % markers()[-1])
            assert level() == "WARN", "more than half"
            # F19: OK only when no holder differs, each read on its own; the item goes to the first that differs
            c, main_md, copy = fresh("# Me\n\n" + stale + "\n## Mine\n")
            write_file(copy, real)
            assert level() == "WARN" and [i["what"] for i in rule_items()] == ["move the CodeGraph section of %s to %s" % (os.path.realpath(main_md), copy)]
            for own, rel in (("mine\n", "a-old.md"), ("# Me\n\n" + real, "old.md")):
                c, main_md, copy = fresh(own)
                if rel == "a-old.md":
                    write_file(copy, real)
                old_copy = os.path.join(c, "rules", rel)
                write_file(old_copy, stale)
                text, files, _, _ = agent_setup("claude")
                said = check_rule("claude", text, files, markers(), real)[0]
                assert said[0] == "WARN" and os.path.realpath(old_copy) in said[2], said
                mine = rule_items()
                assert [i["what"] for i in mine] == ["replace the CodeGraph section of " + os.path.realpath(old_copy)], mine
                lines, ok, *_ = apply(mine, "all")
                assert ok and whole(old_copy) == real and whole(main_md) == own and level() == "OK" and rule_items() == [], lines
            # F13: the WARN names the one file that holds the rule, and setup does the rest: for all four agents
            for agent, env, name in (("claude", "CLAUDE_CONFIG_DIR", "CLAUDE.md"), ("codex", "CODEX_HOME", "AGENTS.md")):
                c, main_md, copy = fresh()
                os.environ[env] = c
                write_file(os.path.join(c, name), "# Me\n\n" + stale)
                write_file(os.path.join(c, "rules", "a.md"), "Own.\n")
                text, files, _, _ = agent_setup(agent)
                said = check_rule(agent, text, files, markers(), real)[0]
                assert said[0] == "WARN" and os.path.realpath(os.path.join(c, name)) in said[2] and "a.md" not in said[2], said
                assert "run kiss-doctor setup" in said[2] and "replace the section" not in said[2], said
                write_file(os.path.join(c, name), "# Me\n\n" + real.split("**Subagents**")[0])
                text, files, _, _ = agent_setup(agent)
                said = check_rule(agent, text, files, markers(), real)[0]
                assert said[0] == "WARN" and "Subagents" in said[2] and os.path.realpath(os.path.join(c, name)) in said[2] and "run kiss-doctor setup" in said[2], said
            # F12: a config folder with [ ] in its path finds its copy
            c = os.path.join(fx, "D [x]")
            write_file(os.path.join(c, "rules", "kiss.md"), real)
            os.environ["CLAUDE_CONFIG_DIR"] = c
            assert level() == "OK" and rule_items() == []
            # T1: a Codex home with [ ] in its path finds its plugin
            c = os.path.join(fx, "C [x]")
            os.makedirs(os.path.join(c, "plugins", "cache", "m", "p", "1.0"))
            write_file(os.path.join(c, "config.toml"), '[plugins."p@m"]\nenabled = true\n')
            os.environ["CODEX_HOME"] = c
            assert ("p@m", os.path.join(c, "plugins", "cache", "m", "p", "1.0")) in agent_setup("codex")[2], agent_setup("codex")[2]
            # D14: the holder test is Claude Code's: the other agents' plans stay: any bold lead-in the replace, plain words by hand
            home_was, three_bold = HOME, "## CodeGraph\n" + "".join("**%s** x\n" % m for m in markers()[:3]) + "Own line.\n## Other\n"
            globals()["HOME"] = fx
            try:
                for agent, env, name in (("codex", "CODEX_HOME", "AGENTS.md"), ("gemini", None, ".gemini/GEMINI.md"), ("antigravity", None, ".gemini/GEMINI.md")):
                    c = os.path.join(fx, "other " + agent)
                    if env:
                        os.environ[env] = c
                    else:
                        c = fx
                    path = os.path.join(c, name)
                    other_sys = dict(got, agents=[agent])
                    for text, want in ((three_bold, "replace"), ("## Agents\n**Subagents** use a brief.\nOwn line.\n## Other\n", "replace"),
                                       ("Subagents get a brief.\n", "hand"), ("".join("%s x\n" % m for m in markers()), "hand"), ("nothing\n", "append")):
                        write_file(path, text)
                        mine = [i for i in plan(other_sys, gaps(other_sys)) if "CodeGraph rule" in i["what"] or "CodeGraph section" in i["what"]]
                        assert len(mine) == 1, (agent, text, mine)
                        if want == "replace":
                            assert mine[0]["n"] and mine[0]["what"] == "replace the CodeGraph section of " + os.path.realpath(path), (agent, text, mine)
                        elif want == "hand":
                            assert not mine[0]["n"] and mine[0]["hand"].startswith("by hand: no bold lead-in of the rule in "), (agent, text, mine)
                        else:
                            assert mine[0]["n"] and mine[0]["run"] == [["cat", os.path.join(KISS, "rules", "codegraph.md"), ">>", path]], (agent, text, mine)
                        joined, files, _, _ = agent_setup(agent)
                        said = check_rule(agent, joined, files, markers(), real)[0]
                        assert said[0] == ("FAIL" if want == "append" else "WARN"), (agent, text, said)
                        assert FILE_BREAK not in joined, (agent, "only Claude Code's read splits on it")
            finally:
                globals()["HOME"] = home_was
            # another agent's plan names no path under the Claude config folder
            c, main_md, copy = fresh("# Me\n\n" + stale)
            other = dict(got, agents=["codex"])
            assert c not in json.dumps(plan(other, gaps(other))), plan(other, gaps(other))
            os.makedirs(os.path.join(fx, "bin"))                       # F3: copied but its folder not on PATH
            with open(os.path.join(fx, "bin", "cgcallers"), "w") as f:
                f.write("x")
            assert "cgcallers" not in gaps(dict(got, agents=[])), "cgcallers planned again"
            line = 'export PATH="%s:$PATH"' % os.path.join(fx, "bin")
            assert any(line in l for l in by_hand(got, [], [])), by_hand(got, [], [])
            assert not any("export PATH" in l for l in by_hand(dict(got, path=os.path.join(fx, "bin")), [], []))
        finally:
            for k, v in old_env.items():
                os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
    print("doctor selftest ok")


def main(argv):
    if argv[1:] == ["--selftest"]:
        return selftest()
    if argv[1:2] == ["feedback"]:
        if len(argv) != 4 or argv[2] not in ("on", "off") or argv[3] not in CLI:
            sys.exit("usage: doctor.py feedback on|off <%s>" % "|".join(CLI))
        on, settings = argv[2] == "on", settings_path()
        try:
            lines = set_feedback(settings, on) if argv[3] == "claude" else feedback_by_hand(argv[3], on)
        except OSError as e:
            sys.exit("%s: cannot write it (%s); left as it was" % (settings, " ".join(str(e).split())))
        print("\n".join(lines + ["This run gives no block when the mode was off at its start."]))
        return
    if argv[1:2] == ["setup"]:
        system = detect()
        system["agents"], answer, pid = setup_args(argv[2:], system["agents"])
        lines, ok = setup(system, answer, pid=pid)
        print("\n".join(lines))
        sys.exit(0 if ok else 1)
    agents = argv[1:] or [a for a, cli in CLI.items() if shutil.which(cli)]
    unknown = [a for a in agents if a not in CLI]
    if unknown or not agents:
        sys.exit(f"name an agent: {', '.join(CLI)}" + (f" (unknown: {', '.join(unknown)})" if unknown else " (none on PATH)"))
    lines, fails = report(agents)
    print("\n".join(lines))
    sys.exit(1 if fails else 0)


def report(agents):
    """The checks: (the report's lines, the number of FAIL lines)."""
    need, marks = required(), markers()
    rule = read(os.path.join(KISS, "rules", "codegraph.md"))
    repo = run(["git", "rev-parse", "--show-toplevel"]).strip() if shutil.which("git") else ""
    rows = check_tools() + check_servers(repo) + check_feedback(settings_path(), project=os.getcwd())
    for agent in agents:
        text, files, roots, note = agent_setup(agent)
        rows += check_rule(agent, text, files, marks, rule) + check_skills(agent, roots, need, note, loaded_here(agent))
        rows += check_mcp(agent)
    out = [f"{level:<5} {agent:<12} {what}" + (f"  [fix: README \"{fix}\"]" if fix else "") for level, agent, what, fix in rows]
    fails, warns, infos = (sum(r[0] == lv for r in rows) for lv in ("FAIL", "WARN", "INFO"))
    return out + [f"\n{fails} FAIL, {warns} WARN, {infos} INFO, {len(rows) - fails - warns - infos} OK ({', '.join(agents)})"], fails


if __name__ == "__main__":
    main(sys.argv)
