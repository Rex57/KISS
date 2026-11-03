#!/usr/bin/env python3
"""Check this device for a KISS run (kiss-doctor/SKILL.md). Reads only; changes nothing.

  python3 -I doctor.py [AGENT ...]    AGENT: claude, codex, gemini, antigravity (default: each one whose CLI is on PATH)
  python3 -I doctor.py feedback on|off   set env.KISS_FEEDBACK in Claude Code's user settings ("1" or "0"), with a backup
  python3 -I doctor.py --selftest

Each line: OK, INFO, WARN or FAIL, the agent, what was checked, and for a WARN or FAIL the README section with the fix.
Exit 1 when a line is FAIL.

The required skills come from the table in kiss-harness/SKILL.md, the rule's markers from the bold lead-ins of
rules/codegraph.md, so neither list is kept here.
"""
import glob, json, os, re, shutil, subprocess, sys

KISS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
HOME = os.path.expanduser("~")
CLI = {"claude": "claude", "codex": "codex", "gemini": "gemini", "antigravity": "agy"}


def read(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def required(kiss=KISS):
    """{skill: README section with its install}: KISS's own skills and the harness's table of external ones."""
    out = {d: "Install KISS" for d in sorted(os.listdir(os.path.join(kiss, "skills")))}
    table = read(os.path.join(kiss, "skills", "kiss-harness", "SKILL.md"))
    for name, source in re.findall(r"^\| `([a-z0-9-]+)` \| ([^|]+?) \|", table, re.M):
        out[name] = "Install " + source
    return out


def markers(kiss=KISS):
    return [m.rstrip(":.") for m in re.findall(r"^\*\*(.+?)\*\*", read(os.path.join(kiss, "rules", "codegraph.md")), re.M)]


def with_imports(path, depth=5, seen=None):
    """The file's text plus every `@file` it imports (Claude Code's CLAUDE.md syntax, 5 hops deep)."""
    seen = set() if seen is None else seen
    path = os.path.realpath(os.path.expanduser(path))
    if path in seen or not os.path.isfile(path):
        return ""
    seen.add(path)
    text = read(path)
    if depth:
        for ref in re.findall(r"(?:^|\s)@(\S+)", text):
            ref = os.path.join(os.path.dirname(path), os.path.expanduser(ref))
            if os.path.isfile(ref):
                text += "\n" + with_imports(ref, depth - 1, seen)
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
        files = [os.path.join(home, "CLAUDE.md")]
        return with_imports(files[0]), files, roots + [("~/.claude/skills", os.path.join(home, "skills"))], ""
    if agent == "codex":
        home = os.environ.get("CODEX_HOME") or os.path.join(HOME, ".codex")
        cfg = os.path.join(home, "config.toml")
        roots = []
        for pid in codex_enabled(read(cfg) if os.path.isfile(cfg) else ""):
            name, _, market = pid.partition("@")
            versions = sorted(glob.glob(os.path.join(home, "plugins", "cache", market, name, "*")), key=os.path.getmtime)
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


def check_rule(agent, text, files, marks):
    shown = " or ".join(f.replace(HOME, "~") for f in files)
    have = [m for m in marks if m in text]
    if not text:
        out = [("FAIL", agent, f"CodeGraph rule: no {shown}", "The CodeGraph rule")]
    elif len(have) == len(marks):
        out = [("OK", agent, f"CodeGraph rule in {shown}", "")]
    elif have:
        lacks = ", ".join(m for m in marks if m not in have)
        out = [("WARN", agent, f"CodeGraph rule in {shown} is an older or edited copy: lacks {lacks}", "The CodeGraph rule")]
    else:
        out = [("FAIL", agent, f"CodeGraph rule: not in {shown}", "The CodeGraph rule")]
    if re.search(r"^\W*CODEGRAPH_START\W*$", text, re.M):  # the marker line, not the rule's own mention of it
        out.append(("WARN", agent, "a CODEGRAPH_START block from `codegraph install`: delete it", "The CodeGraph rule"))
    return out


def check_skills(agent, roots, need, note="", here=()):
    """here: the KISS skills of the folder this script runs from, which the running session loaded."""
    seen = {}
    for label, root in roots:
        for name, path in skills_in(root).items():
            seen.setdefault(name, {}).setdefault(os.path.realpath(path), label)
    out = []
    for name, fix in need.items():
        copies = seen.get(name, {})
        if not copies and name in here:
            out.append(("INFO", agent, f"skill {name}: not installed, but this session loaded it from {KISS}"
                        " (a --plugin-dir session, or a KISS repo newer than the install)", ""))
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
            out.append(("OK", agent, f"skill {name} ({label})", ""))
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


PROFILES = [".zshenv", ".zprofile", ".zshrc", ".bash_profile", ".bashrc", ".profile"]


def settings_path():
    return os.path.join(os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(HOME, ".claude"), "settings.json")


def feedback_mode(settings, home=HOME, env=None, project=None):
    """(on?, where). The value this session has (its environment) decides; where names the first place that sets
    that value: Claude Code's user settings env, the project's .claude settings, then a shell profile's export."""
    places = [(settings, "Claude Code's settings env (%s)" % settings.replace(home, "~", 1))]
    if project:
        places += [(os.path.join(project, ".claude", n), "the project's .claude/%s env" % n) for n in ("settings.local.json", "settings.json")]
    found = []
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
            found.append((m[-1], "the shell profile ~/%s" % name))
    now = (env or {}).get("KISS_FEEDBACK")
    if now is None:
        return (found[0][0] == "1", found[0][1]) if found else (False, "set nowhere")
    where = next((label for value, label in found if value == now), "this session's environment only: a --settings flag or the shell that started it")
    return now == "1", where


def check_feedback(settings):
    on, where = feedback_mode(settings, env=os.environ, project=os.getcwd())
    return [("INFO", "device", "feedback mode: %s (%s)" % ("on" if on else "off", where), "")]


def set_feedback(settings, on):
    """Set only env.KISS_FEEDBACK in the settings file, after a backup beside it. Returns the lines to print."""
    data = {}
    if os.path.exists(settings):
        try:
            data = json.load(open(settings))
            assert isinstance(data, dict)
        except (OSError, ValueError, AssertionError) as e:
            sys.exit("%s: cannot read it as a JSON object (%s); left untouched" % (settings, type(e).__name__))
        backup = settings + ".kiss-backup"
        shutil.copy2(settings, backup)
    else:
        backup = None
        os.makedirs(os.path.dirname(settings), exist_ok=True)
    if not isinstance(data.get("env"), dict):
        data["env"] = {}
    data["env"]["KISS_FEEDBACK"] = "1" if on else "0"
    with open(settings, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    return ["feedback mode %s in %s%s" % ("on" if on else "off", settings, " (backup: %s)" % backup if backup else ""),
            "Claude Code: start a new session for it to apply.",
            "Codex, Gemini CLI, Antigravity: put this line in your shell profile yourself: export KISS_FEEDBACK=%s" % ("1" if on else "0")]


def selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as t:
        def put(rel, text):
            path = os.path.join(t, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write(text)
            return path
        put("kiss/rules/codegraph.md", "## CodeGraph\n\n**Which index.** a\n**`callers` is incomplete:** b\n")
        put("kiss/skills/kiss-harness/SKILL.md", "| Skill | From |\n|---|---|\n| `tdd` | Matt Pocock's skills | x |\n| `ponytail` | ponytail | y |\n")
        put("kiss/skills/kiss-doctor/SKILL.md", "---\nname: kiss-doctor\n---\n")
        kiss = os.path.join(t, "kiss")
        need = required(kiss)
        assert need == {"kiss-doctor": "Install KISS", "kiss-harness": "Install KISS", "tdd": "Install Matt Pocock's skills",
                        "ponytail": "Install ponytail"}, need
        marks = markers(kiss)
        assert marks == ["Which index", "`callers` is incomplete"], marks
        # the rule: in an imported file, an edited copy, none at all, and the installer's block
        main = put("home/CLAUDE.md", "intro\n@rules.md\n@types/node is not a file\n")
        put("home/rules.md", "**Which index.** x\n**`callers` is incomplete** (my note): y\n")
        assert check_rule("claude", with_imports(main), [main], marks)[0][0] == "OK"
        assert check_rule("claude", "**Which index.** only", [main], marks)[0][0] == "WARN"
        assert check_rule("claude", "nothing", [main], marks)[0][0] == "FAIL"
        assert check_rule("claude", "", [main], marks)[0][0] == "FAIL"
        assert len(check_rule("claude", "Which index `callers` is incomplete: delete a `CODEGRAPH_START` block", [main], marks)) == 1
        assert check_rule("claude", "Which index `callers` is incomplete\n<!-- CODEGRAPH_START -->\n", [main], marks)[1][0] == "WARN"
        # the skills: once, twice, user-only, missing
        put("a/skills/tdd/SKILL.md", "---\nname: tdd\n---\n")
        put("a/skills/ponytail/SKILL.md", "---\nname: ponytail\ndisable-model-invocation: true\n---\n")
        put("b/skills/engineering/tdd/SKILL.md", "---\nname: tdd\n---\n")
        put("a/skills/.hidden/kiss-doctor/SKILL.md", "---\nname: kiss-doctor\n---\n")
        one = {r[2].split()[1].rstrip(":"): r[0] for r in check_skills("claude", [("a", os.path.join(t, "a"))], need)}
        assert one == {"kiss-doctor": "FAIL", "kiss-harness": "FAIL", "tdd": "OK", "ponytail": "FAIL"}, one
        assert [r[3] for r in check_skills("claude", [("a", os.path.join(t, "a"))], need) if "user-only" in r[2]] == ["User-only skills"]
        # a KISS skill the session loaded from the script's own folder but not installed: INFO with the reason
        here = {r[2].split()[1].rstrip(":"): r for r in check_skills("claude", [("a", os.path.join(t, "a"))], need, here={"kiss-harness"})}
        assert here["kiss-harness"][0] == "INFO" and "--plugin-dir" in here["kiss-harness"][2], here
        assert here["kiss-doctor"][0] == "FAIL", here
        # KISS's own skill is user-only on purpose: no FAIL
        put("c/skills/kiss-doctor/SKILL.md", "---\nname: kiss-doctor\ndisable-model-invocation: true\n---\n")
        assert check_skills("claude", [("c", os.path.join(t, "c"))], {"kiss-doctor": "Install KISS"})[0][0] == "OK"
        two =check_skills("claude", [("a", os.path.join(t, "a")), ("b", os.path.join(t, "b"))], {"tdd": "x"})
        assert two[0][0] == "WARN" and "2 times" in two[0][2], two
        assert check_skills("claude", [("a", os.path.join(t, "a")), ("a", os.path.join(t, "a"))], {"tdd": "x"})[0][0] == "OK"
        # the feedback mode: where it is set, and the switch on a scratch settings file
        home = os.path.join(t, "fhome")
        os.makedirs(home)
        st = os.path.join(home, "cfg", "settings.json")
        assert feedback_mode(st, home) == (False, "set nowhere")
        put("fhome/.zshrc", "export PATH=x\nexport KISS_FEEDBACK=1\n")
        assert feedback_mode(st, home) == (True, "the shell profile ~/.zshrc"), feedback_mode(st, home)
        original = {"model": "opus", "permissions": {"allow": ["Read"]}, "hooks": {"Stop": []}}
        put("fhome/cfg/settings.json", json.dumps(original))
        lines = set_feedback(st, False)
        assert os.path.isfile(st + ".kiss-backup") and json.load(open(st + ".kiss-backup")) == original, lines
        got = json.load(open(st))
        assert got == dict(original, env={"KISS_FEEDBACK": "0"}), got
        assert feedback_mode(st, home) == (False, "Claude Code's settings env (~/cfg/settings.json)"), feedback_mode(st, home)   # off wins over the profile
        put("fhome/cfg/settings.json", json.dumps(dict(original, env={"PATH_X": "y"})))
        set_feedback(st, True)
        assert json.load(open(st)) == dict(original, env={"PATH_X": "y", "KISS_FEEDBACK": "1"})
        assert "new session" in " ".join(lines) and "export KISS_FEEDBACK=0" in " ".join(lines)
        put("fhome/cfg/settings.json", "{ not json")
        try:
            set_feedback(st, True)
            raise AssertionError("an unreadable file was written")
        except SystemExit as e:
            assert "left untouched" in str(e)
        assert read(st) == "{ not json"
        fresh = os.path.join(home, "new", "settings.json")
        set_feedback(fresh, True)
        assert json.load(open(fresh)) == {"env": {"KISS_FEEDBACK": "1"}} and not os.path.exists(fresh + ".kiss-backup")
        # the session's own value decides; where names the place that sets it
        assert feedback_mode(fresh, home, env={"KISS_FEEDBACK": "1"}) == (True, "Claude Code's settings env (~/new/settings.json)")
        assert feedback_mode(os.path.join(t, "none.json"), home, env={"KISS_FEEDBACK": "1"}) == (True, "the shell profile ~/.zshrc")
        assert feedback_mode(os.path.join(t, "none.json"), home, env={"KISS_FEEDBACK": "0"})[1].startswith("this session's environment only")
        put("proj/.claude/settings.local.json", json.dumps({"env": {"KISS_FEEDBACK": "0"}}))
        assert feedback_mode(os.path.join(t, "none.json"), home, env={"KISS_FEEDBACK": "0"}, project=os.path.join(t, "proj")) == (False, "the project's .claude/settings.local.json env")
    cfg = '[plugins."kiss@kiss"]\nenabled = true\n\n[plugins."old@m"]\nenabled = false\n[tui]\nenabled = true\n'
    assert codex_enabled(cfg) == ["kiss@kiss"], codex_enabled(cfg)
    print("doctor selftest ok")


def main(argv):
    if argv[1:] == ["--selftest"]:
        return selftest()
    if argv[1:2] == ["feedback"]:
        if argv[2:] not in (["on"], ["off"]):
            sys.exit("usage: doctor.py feedback on|off")
        print("\n".join(set_feedback(settings_path(), argv[2] == "on")))
        return
    agents = argv[1:] or [a for a, cli in CLI.items() if shutil.which(cli)]
    unknown = [a for a in agents if a not in CLI]
    if unknown or not agents:
        sys.exit(f"name an agent: {', '.join(CLI)}" + (f" (unknown: {', '.join(unknown)})" if unknown else " (none on PATH)"))
    need, marks = required(), markers()
    rows = check_tools() + check_feedback(settings_path())
    for agent in agents:
        text, files, roots, note = agent_setup(agent)
        # the script's own KISS folder is what this Claude Code session loaded (CLAUDECODE=1 in its shell)
        here = skills_in(os.path.join(KISS, "skills")) if agent == "claude" and os.environ.get("CLAUDECODE") == "1" else {}
        rows += check_rule(agent, text, files, marks) + check_skills(agent, roots, need, note, here)
    for level, agent, what, fix in rows:
        print(f"{level:<5} {agent:<12} {what}" + (f"  [fix: README \"{fix}\"]" if fix else ""))
    fails, warns, infos = (sum(r[0] == lv for r in rows) for lv in ("FAIL", "WARN", "INFO"))
    print(f"\n{fails} FAIL, {warns} WARN, {infos} INFO, {len(rows) - fails - warns - infos} OK ({', '.join(agents)})")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main(sys.argv)
