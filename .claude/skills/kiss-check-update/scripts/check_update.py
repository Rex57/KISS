#!/usr/bin/env python3
"""kiss-check-update: compare the record of every upstream source KISS uses (upstream.json) with what is out now.

  python3 -I check_update.py                  one line per finding, or "same" per source; exit 1 on any change,
                                              exit 2 when gh, npm or claude fails (nothing compared)
  python3 -I check_update.py --update NAME... after the port: write the current upstream into the record, for the
                                              named sources only
  python3 -I check_update.py --record FILE ... the same, with another record (a test)
  python3 -I check_update.py --selftest

GitHub sources: the latest release tag (gh api), each recorded file's blob sha at that tag (a copied rule's text
fingerprint), and each called skill's frontmatter (still callable: no `disable-model-invocation: true`). A changed
file gives its compare link. CodeGraph: the latest npm version, and `codegraph <command> --help` for each flag KISS
uses. The mods API: the local Claude Code build; a new build runs `claude plugin validate` and `claude plugin test`
on the KISS repo. Needs the network (gh, npm). The record names upstream repos and paths, never a local path.
"""
import contextlib, io, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
RECORD = os.path.join(os.path.dirname(HERE), "upstream.json")
KISS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))


def sh(*cmd):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        return 127, "", "%s: not on PATH" % cmd[0]
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def broken(cmd, err):
    """A gh or npm call failed: exit 2, so a failure never reads as a change (exit 1)."""
    sys.stderr.write("%s failed: %s\n" % (" ".join(cmd[:3]), err or "no output"))
    sys.exit(2)


def must(*cmd):
    """The output of a command that must work (a gh or npm call): exit with its error when it fails or says nothing."""
    code, out, err = sh(*cmd)
    if code or not out:
        broken(cmd, err)
    return out


def file_call(*cmd):
    """A file at a tag: its output, None when GitHub answers 404 (the file is gone); exit on any other error."""
    code, out, err = sh(*cmd)
    if code == 0:
        return out
    if "404" in err or "Not Found" in err:
        return None
    broken(cmd, err)


class Live:
    """The real upstream, read through gh, npm and the local CLIs."""
    def latest(self, repo):
        return must("gh", "api", "repos/%s/releases/latest" % repo, "--jq", ".tag_name")

    def blob(self, repo, path, tag):
        return file_call("gh", "api", "repos/%s/contents/%s?ref=%s" % (repo, path, tag), "--jq", ".sha") or None

    def text(self, repo, path, tag):
        return file_call("gh", "api", "-H", "Accept: application/vnd.github.raw", "repos/%s/contents/%s?ref=%s" % (repo, path, tag))

    def npm_latest(self, package):
        return must("npm", "view", package, "version")

    def help(self, tool, command):
        code, out, _ = sh(tool, command, "--help")
        return out if code == 0 else ""

    def build(self):
        return must("claude", "--version").split(" ")[0]

    def validate(self):
        return sh("claude", "plugin", "validate", KISS)[0] == 0

    def test(self):
        return sh("claude", "plugin", "test", KISS)[0] == 0


def user_only(text):
    m = re.match(r"---\r?\n(.*?)\r?\n---", text or "", re.S)
    return bool(m and re.search(r"^disable-model-invocation:\s*true\s*$", m.group(1), re.M))


def compare(record, up):
    """[(source name, line, changed?)]: one line per finding, or one "same" line per source."""
    out = []
    for s in record["sources"]:
        found = []
        if "repo" in s:
            new = up.latest(s["repo"])
            if not new:
                sys.exit("%s: no latest release tag (gh failed?): nothing compared" % s["repo"])
            link = "https://github.com/%s/compare/%s...%s" % (s["repo"], s["tag"], new)
            if new != s["tag"]:
                found.append("new release %s (recorded %s): %s" % (new, s["tag"], link))
                for f in s.get("files", []):
                    sha = up.blob(s["repo"], f["path"], new)
                    if sha is None:
                        found.append("gone: %s (copied by %s)" % (f["path"], ", ".join(f.get("kiss_files", [])) or "KISS"))
                    elif sha != f["fingerprint"]:
                        found.append("changed: %s (copied by %s): %s" % (f["path"], ", ".join(f.get("kiss_files", [])) or "KISS", link))
                for c in s.get("called", []):
                    text = up.text(s["repo"], c["path"], new)
                    if text is None:
                        found.append("gone: skill %s (%s)" % (c["skill"], c["path"]))
                    elif user_only(text):
                        found.append("no longer callable: skill %s is user-only at %s" % (c["skill"], new))
        if "package" in s:
            new = up.npm_latest(s["package"])
            if not new:
                sys.exit("%s: no latest version (npm failed?): nothing compared" % s["package"])
            if new != s["version"]:
                found.append("new version %s (recorded %s): https://github.com/%s/compare/v%s...v%s"
                             % (new, s["version"], s["github"], s["version"], new))
            for command, flags in s["commands"].items():
                text = up.help(s["tool"], command)
                for flag in flags:
                    if not re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(flag), text):
                        found.append("flag gone: %s %s %s" % (s["tool"], command, flag))
        if "build" in s:
            new = up.build()
            if new != s["build"]:
                found.append("build changed: %s (recorded %s): plugin validate %s, plugin test %s"
                             % (new, s["build"], "ok" if up.validate() else "FAILS", "ok" if up.test() else "FAILS"))
        out += [(s["name"], line, True) for line in found] or [(s["name"], "same (%s)" % (s.get("tag") or s.get("version") or s.get("build")), False)]
    return out


def update(record, up, names):
    unknown = set(names) - {s["name"] for s in record["sources"]}
    if unknown:
        sys.exit("not in the record: %s" % ", ".join(sorted(unknown)))
    for s in record["sources"]:
        if s["name"] not in names:
            continue
        if "repo" in s:
            tag = up.latest(s["repo"])
            prints = [up.blob(s["repo"], f["path"], tag) for f in s.get("files", [])] if tag else []
            if not tag or None in prints:
                gone = [f["path"] for f, p in zip(s.get("files", []), prints) if p is None]
                sys.exit("%s: refused, the record is unchanged: %s" % (s["name"], "no latest tag" if not tag else "gone at %s: %s" % (tag, ", ".join(gone))))
            s["tag"] = tag
            for f, p in zip(s.get("files", []), prints):
                f["fingerprint"] = p
        if "package" in s:
            version = up.npm_latest(s["package"])
            if not version:
                sys.exit("%s: refused, no latest version" % s["name"])
            s["version"] = version
        if "build" in s:
            build = up.build()
            if not build:
                sys.exit("%s: refused, no build" % s["name"])
            s["build"] = build
    return record


def selftest():
    class Fake:
        def __init__(self, **kw):
            self.__dict__.update(kw)
        def latest(self, repo): return self.tags[repo]
        def blob(self, repo, path, tag): return self.blobs.get((repo, path, tag))
        def text(self, repo, path, tag): return self.texts.get((repo, path, tag))
        def npm_latest(self, package): return self.npm
        def help(self, tool, command): return self.helps.get(command, "")
        def build(self): return self.claude
        def validate(self): return True
        def test(self): return False
    record = {"sources": [
        {"name": "skills", "repo": "o/skills", "tag": "v1.0.0",
         "files": [{"path": "a/retro/SKILL.md", "fingerprint": "s1", "kiss_files": ["skills/x/retro.md"]},
                   {"path": "a/wayfinder/SKILL.md", "fingerprint": "s2", "kiss_files": ["skills/y/map.md"]}],
         "called": [{"skill": "tdd", "path": "a/tdd/SKILL.md"}, {"skill": "pr", "path": "a/pr/SKILL.md"}]},
        {"name": "ponytail", "repo": "o/ponytail", "tag": "v5.0.0", "files": [{"path": "p/SKILL.md", "fingerprint": "p1"}]},
        {"name": "codegraph", "package": "@o/codegraph", "github": "o/codegraph", "tool": "codegraph", "version": "1.6.2",
         "commands": {"explore": ["-p"], "callers": ["-p", "--limit"]}},
        {"name": "mods", "build": "2.1.317"}]}
    same = Fake(tags={"o/skills": "v1.0.0", "o/ponytail": "v5.0.0"}, blobs={}, texts={}, npm="1.6.2", claude="2.1.317",
                helps={"explore": "-p, --path <path>", "callers": "-p, --path <path>\n--limit <n>"})
    lines = compare(record, same)
    assert [c for _, _, c in lines] == [False] * 4 and lines[0][1] == "same (v1.0.0)", lines
    new = Fake(tags={"o/skills": "v1.1.0", "o/ponytail": "v5.0.0"}, npm="1.6.2", claude="2.1.320",
               blobs={("o/skills", "a/retro/SKILL.md", "v1.1.0"): "s1-new"},
               texts={("o/skills", "a/tdd/SKILL.md", "v1.1.0"): "---\nname: tdd\n---\n",
                      ("o/skills", "a/pr/SKILL.md", "v1.1.0"): "---\nname: pr\ndisable-model-invocation: true\n---\n"},
               helps={"explore": "-p, --path <path>", "callers": "-p, --path <path>"})
    lines = compare(record, new)
    text = "\n".join("%s: %s" % (n, l) for n, l, _ in lines)
    link = "https://github.com/o/skills/compare/v1.0.0...v1.1.0"
    assert "skills: changed: a/retro/SKILL.md (copied by skills/x/retro.md): " + link in text, text
    assert "skills: gone: a/wayfinder/SKILL.md (copied by skills/y/map.md)" in text, text
    assert "skills: no longer callable: skill pr is user-only at v1.1.0" in text and "skill tdd" not in text, text
    assert "ponytail: same (v5.0.0)" in text, text
    assert "codegraph: flag gone: codegraph callers --limit" in text and "callers -p" not in text, text
    assert "mods: build changed: 2.1.320 (recorded 2.1.317): plugin validate ok, plugin test FAILS" in text, text
    assert len(text.splitlines()) == len(lines) == 7, text            # each finding on its own line
    # --update writes only the named source
    new.blobs[("o/skills", "a/wayfinder/SKILL.md", "v1.1.0")] = "s2-new"      # an update needs every file present
    up = update(json.loads(json.dumps(record)), new, ["skills"])
    assert up["sources"][0]["tag"] == "v1.1.0" and up["sources"][0]["files"][0]["fingerprint"] == "s1-new"
    assert up["sources"][3]["build"] == "2.1.317" and up["sources"][1] == record["sources"][1]
    # a failing gh: no tag means exit, never "new release" and "gone"; --update writes nothing
    broken = Fake(tags={"o/skills": "", "o/ponytail": ""}, blobs={}, texts={}, npm="", claude="", helps={})
    for call in (lambda: compare(record, broken), lambda: update(json.loads(json.dumps(record)), broken, ["skills"])):
        try:
            call()
            raise AssertionError("a failing gh was not refused")
        except SystemExit as e:
            assert "no latest" in str(e), e
    kept = json.loads(json.dumps(record))
    gone = Fake(tags={"o/skills": "v1.1.0"}, blobs={("o/skills", "a/retro/SKILL.md", "v1.1.0"): "x"}, texts={}, npm="", claude="", helps={})
    try:
        update(kept, gone, ["skills"])
        raise AssertionError("a None fingerprint was written")
    except SystemExit as e:
        assert "a/wayfinder/SKILL.md" in str(e) and kept == record, e
    # a failing command exits 2, never 1 (a change)
    for call in (lambda: must("false"), lambda: must("true"), lambda: file_call("sh", "-c", "echo boom >&2; exit 1")):
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                call()
            raise AssertionError("a failing command did not exit")
        except SystemExit as e:
            assert e.code == 2, e.code
    assert file_call("sh", "-c", "echo 'HTTP 404: Not Found' >&2; exit 1") is None      # a 404 is a gone file, not a failure
    # the exit code: 1 on any change
    del new.blobs[("o/skills", "a/wayfinder/SKILL.md", "v1.1.0")]
    with contextlib.redirect_stdout(io.StringIO()):
        assert run(record, new) == 1 and run(record, same) == 0
    print("check_update selftest ok")


def run(record, up):
    lines = compare(record, up)
    for name, line, _ in lines:
        print("%-10s %s" % (name, line))
    return 1 if any(c for _, _, c in lines) else 0


def main(argv):
    if argv[1:] == ["--selftest"]:
        return selftest()
    global RECORD
    if argv[1:2] == ["--record"] and len(argv) > 2:      # a planted record for a test
        RECORD, argv = argv[2], argv[:1] + argv[3:]
    record = json.load(open(RECORD))
    if argv[1:2] == ["--update"]:
        if not argv[2:]:
            sys.exit("name the sources to update: %s" % ", ".join(s["name"] for s in record["sources"]))
        json.dump(update(record, Live(), argv[2:]), open(RECORD, "w"), indent=2)
        open(RECORD, "a").write("\n")
        print("updated: %s" % ", ".join(argv[2:]))
        return
    if argv[1:]:
        sys.exit(__doc__)
    sys.exit(run(record, Live()))


if __name__ == "__main__":
    main(sys.argv)
