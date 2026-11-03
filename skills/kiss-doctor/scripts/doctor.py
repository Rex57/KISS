#!/usr/bin/env python3
"""Check this device for a KISS run (kiss-doctor/SKILL.md). Reads only, except `feedback on|off`, which sets
env.KISS_FEEDBACK in Claude Code's user settings.

  python3 -I doctor.py [AGENT ...]    AGENT: claude, codex, gemini, antigravity (default: each one whose CLI is on PATH)
  python3 -I doctor.py feedback on|off   set env.KISS_FEEDBACK in Claude Code's user settings ("1" or "0"), with a backup
  python3 -I doctor.py setup             the numbered plan of what is missing, from the install table (installs nothing)
  python3 -I doctor.py setup --apply all|none|1,3   run those plan items, one at a time; stop at the first failure;
                                         then the checks again and the steps by hand. Never sudo, never a shell profile.
  python3 -I doctor.py --selftest

Each line: OK, INFO, WARN or FAIL, the agent, what was checked, and for a WARN or FAIL the README section with the fix.
Exit 1 when a line is FAIL.

The required skills come from the table in kiss-harness/SKILL.md, the rule's markers from the bold lead-ins of
rules/codegraph.md, so neither list is kept here.
"""
import glob, json, os, platform, re, shlex, shutil, subprocess, sys, time

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
        stamp = settings + ".kiss-backup-" + time.strftime("%Y%m%d-%H%M%S")
        backup, n = stamp, 1
        while os.path.exists(backup):           # one backup per switch, also two switches in one second
            n += 1
            backup = "%s-%d" % (stamp, n)
        shutil.copy2(settings, backup)
    else:
        backup = None
        os.makedirs(os.path.dirname(settings), exist_ok=True)
    if not isinstance(data.get("env"), dict):
        data["env"] = {}
    data["env"]["KISS_FEEDBACK"] = "1" if on else "0"
    with open(settings, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return ["feedback mode %s in %s%s" % ("on" if on else "off", settings, " (backup: %s)" % backup if backup else ""),
            "Claude Code: start a new session for it to apply.",
            "Codex, Gemini CLI, Antigravity: put this line in your shell profile yourself: export KISS_FEEDBACK=%s" % ("1" if on else "0")]


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
     "changes": "adds {repo}/.codegraph/", "run": ["codegraph init -y {repo}"]},
    {"key": "rule", "what": "the CodeGraph rule", "source": "https://github.com/Rex57/KISS (rules/codegraph.md)",
     "changes": "appends the rule to {file}", "agents": {a: ["cat {kiss}/rules/codegraph.md >> {file}"] for a in CLI}},
    {"key": "Install KISS", "what": "KISS", "source": "https://github.com/Rex57/KISS", "changes": "adds the KISS plugin to {agent}",
     "agents": {"claude": ["claude plugin marketplace add Rex57/KISS", "claude plugin install kiss@kiss"],
                "codex": ["codex plugin marketplace add Rex57/KISS", "codex plugin add kiss@kiss"],
                "gemini": ["gemini extensions install https://github.com/Rex57/KISS"]},
     "hand": {"antigravity": "git clone https://github.com/Rex57/KISS.git, then agy plugin install ./KISS"}},
    {"key": "Install ponytail", "what": "ponytail", "source": "https://github.com/DietrichGebert/ponytail",
     "changes": "adds the ponytail plugin to {agent}",
     "agents": {"claude": ["claude plugin marketplace add DietrichGebert/ponytail", "claude plugin install ponytail@ponytail"],
                "codex": ["codex plugin marketplace add DietrichGebert/ponytail", "codex plugin add ponytail@ponytail"],
                "gemini": ["gemini extensions install https://github.com/DietrichGebert/ponytail"]},
     "hand": {"antigravity": "follow https://github.com/DietrichGebert/ponytail/blob/main/INSTALL.md"},
     "after": {"codex": "in Codex, open /hooks, trust ponytail's two hooks, and start a new thread"}},
    {"key": "Install Matt Pocock's skills", "what": "Matt Pocock's skills", "source": "https://github.com/mattpocock/skills",
     "changes": "adds Matt Pocock's skills to {agent}",
     "agents": {"claude": ["claude plugin install mattpocock-skills@claude-plugins-official"],
                "codex": ["codex plugin marketplace add mattpocock/skills", "codex plugin add mattpocock-skills@mattpocock"],
                "gemini": ["gemini skills install https://github.com/mattpocock/skills.git --path skills/engineering",
                           "gemini skills install https://github.com/mattpocock/skills.git --path skills/productivity"]},
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
            if row["key"] == "rule":
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
            run = [[w.format(**values) for w in shlex.split(c)] for c in cmds]
            n += bool(run and not hand)
            out.append({"n": n if run and not hand else None, "what": row["what"], "agent": agent, "run": run, "hand": hand,
                        "source": row["source"], "changes": row["changes"].format(**values),
                        "after": row.get("after", {}).get(agent, "")})
    return out


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
    out += by_hand(items, [i for i in items if i["n"]])
    if any(i["n"] for i in items):
        out.append("Answer all, none, or the numbers to install (for example 1,3).")
    return out


def by_hand(items, ran):
    """The steps only the owner can do: the items setup never runs, the steps after the items in `ran`, the links."""
    out, hand = [], [i for i in items if not i["n"]]
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


def execute(argv):
    """Run one table command, without a shell: (exit code, output). The two file commands run in Python, so they
    work where no POSIX shell is."""
    try:
        if argv[0] == "cat" and argv[2:3] == [">>"]:
            old = read(argv[3]) if os.path.isfile(argv[3]) else ""
            os.makedirs(os.path.dirname(argv[3]), exist_ok=True)
            with open(argv[3], "a", encoding="utf-8") as f:
                f.write(("\n" if old and not old.endswith("\n") else "") + read(argv[1]))
            return 0, ""
        if argv[:3] == ["install", "-m", "755"]:
            os.makedirs(os.path.dirname(argv[4]), exist_ok=True)
            shutil.copyfile(argv[3], argv[4])
            os.chmod(argv[4], 0o755)
            return 0, ""
        p = subprocess.run([shutil.which(argv[0]) or argv[0]] + argv[1:], capture_output=True, text=True, timeout=900)
        return p.returncode, (p.stdout + p.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)


def apply(items, answer, runner=execute):
    """Run the items the owner's answer names (all, none, or numbers), in the plan's order, one at a time; stop at
    the first failure. (lines, ok, the items that ran)."""
    numbered = {i["n"]: i for i in items if i["n"]}
    words = [w for w in re.split(r"[,\s]+", answer.strip().lower()) if w]
    if words == ["all"] or words == ["none"]:
        want = sorted(numbered) if words == ["all"] else []
    elif words and all(w.isdigit() and int(w) in numbered for w in words):
        want = sorted({int(w) for w in words})
    else:
        return [f"refused: {answer!r} is not all, none, or numbers of the plan ({', '.join(map(str, numbered)) or 'none'});"
                " nothing ran"], False, []
    sudo = [n for n in want if any(c[0] == "sudo" for c in numbered[n]["run"])]
    if sudo:                                    # plan() never numbers one; this guard keeps it so
        return [f"refused: item {', '.join(map(str, sudo))} needs sudo: run it yourself; nothing ran"], False, []
    out, ran = [], []
    for n in want:
        i = numbered[n]
        for argv in i["run"]:
            code, output = runner(argv)
            if code:
                rest = [str(m) for m in want if m > n]
                return out + [f"FAIL {n}. {i['what']} ({i['agent']}): {command(argv)} exited {code}"] + [
                    "   " + line for line in output.splitlines()[-20:]] + (
                    [f"not run: {', '.join(rest)}"] if rest else []), False, ran + [i]
        out.append(f"done {n}. {i['what']} ({i['agent']})")
        ran.append(i)
    return out, True, ran


def setup(system, answer=None, runner=execute, find=None, checks=None):
    """`setup` prints the plan; `setup --apply <answer>` runs it, then the checks again and the steps by hand."""
    items = plan(system, (find or gaps)(system))
    if answer is None:
        return plan_lines(system, items), True
    lines, ok, ran = apply(items, answer, runner)
    if ran:
        lines += ["", "The checks again:"] + (checks or (lambda: report(system["agents"])[0]))()
    if ran or ok:
        lines += [""] + by_hand(items, ran)
    return lines, ok


def loaded_here(agent):
    """The script's own KISS folder is what this Claude Code session loaded (CLAUDECODE=1 in its shell)."""
    return skills_in(os.path.join(KISS, "skills")) if agent == "claude" and os.environ.get("CLAUDECODE") == "1" else {}


def detect():
    shell = os.environ.get("SHELL") or os.environ.get("COMSPEC") or ""
    repo = run(["git", "rev-parse", "--show-toplevel"]).strip() if shutil.which("git") else ""
    return {"os": {"Darwin": "macos", "Windows": "windows"}.get(platform.system(), "linux"),
            "shell": os.path.basename(shell), "pm": next((p for p in PMS if shutil.which(p)), None),
            "agents": [a for a, cli in CLI.items() if shutil.which(cli)], "repo": repo or None,
            "bin": os.environ.get("KISS_BIN") or os.path.join(HOME, ".local", "bin"), "kiss": KISS}


def gaps(system):
    """What the checks find missing on this machine, in plan()'s form."""
    out = {k: {} for k, missing in [("git", not shutil.which("git")), ("python", sys.version_info < (3, 9)),
                                     ("node", not (shutil.which("node") and shutil.which("npm"))),
                                     ("codegraph", not shutil.which("codegraph")), ("cgcallers", not shutil.which("cgcallers")),
                                     ("index", system["repo"] and not os.path.isdir(os.path.join(system["repo"], ".codegraph")))]
           if missing}
    need, marks = required(), markers()
    for agent in system["agents"]:
        text, files, roots, note = agent_setup(agent)
        if check_rule(agent, text, files, marks)[0][0] == "FAIL":
            out[(agent, "rule")] = {"file": files[0]}
        for level, _, _, fix in check_skills(agent, roots, need, note, loaded_here(agent)):
            if level == "FAIL" and fix.startswith("Install "):
                out[(agent, fix)] = {}
    return out


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
        put("fhome/cfg/settings.json", json.dumps({"env": {"KISS_FEEDBACK": "1"}}))
        assert feedback_mode(st, home) == (False, "set for Claude Code only, in Claude Code's settings env (~/cfg/settings.json)"), feedback_mode(st, home)
        os.remove(st)
        put("fhome/.zshrc", "export PATH=x\nexport KISS_FEEDBACK=1\n")
        assert feedback_mode(st, home) == (True, "the shell profile ~/.zshrc"), feedback_mode(st, home)
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
        assert json.load(open(fresh)) == {"env": {"KISS_FEEDBACK": "1"}} and not glob.glob(fresh + ".kiss-backup*")
        # the session's own value decides; where names the place that sets it
        assert feedback_mode(fresh, home, env={"KISS_FEEDBACK": "1"}) == (True, "Claude Code's settings env (~/new/settings.json)")
        assert feedback_mode(os.path.join(t, "none.json"), home, env={"KISS_FEEDBACK": "1"}) == (True, "the shell profile ~/.zshrc")
        assert feedback_mode(os.path.join(t, "none.json"), home, env={"KISS_FEEDBACK": "0"})[1].startswith("this session's environment only")
        put("proj/.claude/settings.local.json", json.dumps({"env": {"KISS_FEEDBACK": "0"}}))
        assert feedback_mode(os.path.join(t, "none.json"), home, env={"KISS_FEEDBACK": "0"}, project=os.path.join(t, "proj")) == (False, "the project's .claude/settings.local.json env")
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
    gaps = {"codegraph": {}, "cgcallers": {}, "index": {}, ("claude", "Install ponytail"): {},
            ("codex", "Install ponytail"): {}, ("codex", "Install Matt Pocock's skills"): {},
            ("claude", "rule"): {"file": "/h/.claude/CLAUDE.md"}, ("gemini", "Install ponytail"): {}}
    got = show(plan(sysfor(), gaps))
    assert got == [
        ("CodeGraph", "device", ["npm install -g @colbymchenry/codegraph"], ""),
        ("cgcallers", "device", ["install -m 755 /k/skills/kiss-harness/scripts/cgcallers.py /b/cgcallers"], ""),
        ("the CodeGraph index of this repo", "device", ["codegraph init -y /r/my app"], ""),
        ("the CodeGraph rule", "claude", ["cat /k/rules/codegraph.md >> /h/.claude/CLAUDE.md"], ""),
        ("ponytail", "claude", ["claude plugin marketplace add DietrichGebert/ponytail", "claude plugin install ponytail@ponytail"], ""),
        ("ponytail", "codex", ["codex plugin marketplace add DietrichGebert/ponytail", "codex plugin add ponytail@ponytail"], ""),
        ("Matt Pocock's skills", "codex", ["codex plugin marketplace add mattpocock/skills", "codex plugin add mattpocock-skills@mattpocock"], ""),
    ], got                                                                    # gemini is not on PATH: not planned
    items = plan(sysfor(), gaps)
    assert [i["n"] for i in items] == [1, 2, 3, 4, 5, 6, 7] and all(i["source"] and i["changes"] for i in items), items
    assert "/hooks" in items[5]["after"] and items[4]["after"] == "", items
    assert items[2]["run"] == [["codegraph", "init", "-y", "/r/my app"]]     # a path with a space stays one word
    assert command(items[2]["run"][0]) == "codegraph init -y '/r/my app'"
    shared = plan(sysfor(agents=["gemini", "antigravity"]), {("gemini", "rule"): {"file": "/h/.gemini/GEMINI.md"},
                                                             ("antigravity", "rule"): {"file": "/h/.gemini/GEMINI.md"},
                                                             ("gemini", "Install ponytail"): {}, ("antigravity", "Install ponytail"): {},
                                                             ("antigravity", "Install KISS"): {}})
    assert show(shared) == [
        ("the CodeGraph rule", "gemini", ["cat /k/rules/codegraph.md >> /h/.gemini/GEMINI.md"], ""),   # one file, appended once
        ("KISS", "antigravity", [], "by hand: git clone https://github.com/Rex57/KISS.git, then agy plugin install ./KISS"),
        ("ponytail", "gemini", ["gemini extensions install https://github.com/DietrichGebert/ponytail"], ""),
        ("ponytail", "antigravity", [], "by hand: follow https://github.com/DietrichGebert/ponytail/blob/main/INSTALL.md"),
    ], show(shared)
    text = "\n".join(plan_lines(sysfor(os="linux", pm="apt"), plan(sysfor(os="linux", pm="apt"), dict(gaps, git={}))))
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
    checks = lambda: ["CHECKS AGAIN"]
    find = lambda system: gaps                               # numbered: 1 CodeGraph, 2 cgcallers, 3 index, 4 rule, 5-7 plugins
    lines, ok = setup(sysfor(os="linux", pm="apt"), "1,3", runner(), lambda system: dict(gaps, git={}), checks)
    assert ok and ran == ["npm install -g @colbymchenry/codegraph", "codegraph init -y /r/my app"], ran
    text = "\n".join(lines)
    assert "CHECKS AGAIN" in text and "sudo apt install -y git" in text and "start a new session" not in text, text
    ran.clear()
    lines, ok = setup(sysfor(), "6, 5,5", runner(), find, checks)     # the plan's order, each once; the /hooks step after
    assert ok and ran == ["claude plugin marketplace add DietrichGebert/ponytail", "claude plugin install ponytail@ponytail",
                          "codex plugin marketplace add DietrichGebert/ponytail", "codex plugin add ponytail@ponytail"], ran
    assert "/hooks" in "\n".join(lines) and "start a new session" in "\n".join(lines), lines
    ran.clear()
    lines, ok = setup(sysfor(), "all", runner(fail={"codegraph init -y /r/my app"}), find, checks)
    text = "\n".join(lines)
    assert not ok and ran == ["npm install -g @colbymchenry/codegraph",
                              "install -m 755 /k/skills/kiss-harness/scripts/cgcallers.py /b/cgcallers",
                              "codegraph init -y /r/my app"], ran              # stops at the first failure
    for want in ("done 1. CodeGraph", "done 2. cgcallers", "FAIL 3.", "codegraph init -y '/r/my app'", "npm ERR! 404",
                 "not run: 4, 5, 6, 7", "CHECKS AGAIN"):
        assert want in text, (want, text)
    for answer in ("8", "0", "1,x", "rm -rf /", ""):                  # outside the plan: refused, nothing runs
        ran.clear()
        lines, ok = setup(sysfor(), answer, runner(), find, checks)
        assert not ok and ran == [] and "refused" in lines[0] and "CHECKS AGAIN" not in lines, (answer, lines)
    ran.clear()
    assert setup(sysfor(), "none", runner(), find, checks)[1] and ran == []
    sudo = [{"n": 1, "what": "git", "agent": "device", "run": [["sudo", "apt", "install", "-y", "git"]], "hand": "",
             "source": "s", "changes": "c", "after": ""}]
    lines, ok, _ = apply(sudo, "1", runner())                              # a sudo command never runs, even if numbered
    assert not ok and ran == [] and "sudo" in lines[0], lines
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
    print("doctor selftest ok")


def main(argv):
    if argv[1:] == ["--selftest"]:
        return selftest()
    if argv[1:2] == ["feedback"]:
        if argv[2:] not in (["on"], ["off"]):
            sys.exit("usage: doctor.py feedback on|off")
        print("\n".join(set_feedback(settings_path(), argv[2] == "on")))
        return
    if argv[1:2] == ["setup"]:
        if argv[2:] and (argv[2] != "--apply" or len(argv) != 4):
            sys.exit("usage: doctor.py setup [--apply all|none|<numbers>]")
        lines, ok = setup(detect(), argv[3] if argv[2:] else None)
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
    rows = check_tools() + check_feedback(settings_path())
    for agent in agents:
        text, files, roots, note = agent_setup(agent)
        rows += check_rule(agent, text, files, marks) + check_skills(agent, roots, need, note, loaded_here(agent))
    out = [f"{level:<5} {agent:<12} {what}" + (f"  [fix: README \"{fix}\"]" if fix else "") for level, agent, what, fix in rows]
    fails, warns, infos = (sum(r[0] == lv for r in rows) for lv in ("FAIL", "WARN", "INFO"))
    return out + [f"\n{fails} FAIL, {warns} WARN, {infos} INFO, {len(rows) - fails - warns - infos} OK ({', '.join(agents)})"], fails


if __name__ == "__main__":
    main(sys.argv)
