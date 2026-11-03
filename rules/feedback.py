#!/usr/bin/env python3
"""Print a KISS skill's feedback step, only when the feedback mode is on (KISS_FEEDBACK=1).

  python3 -I feedback.py STEP SKILL      e.g. `feedback.py 5 kiss-doctor`; prints nothing when the mode is off
  python3 -I feedback.py --selftest

The step holds the rule of rules/feedback.md (its one home) with the skill's name and the KISS version (from
gemini-extension.json; all four manifests carry the same one) written in, so the run needs no read outside its
project. Each KISS skill runs this as its last step (a Claude Code inline command).
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))


def step(n, skill, env, root=os.path.dirname(HERE)):
    if env.get("KISS_FEEDBACK") != "1":
        return ""
    rule = open(os.path.join(root, "rules", "feedback.md"), encoding="utf-8").read()
    version = json.load(open(os.path.join(root, "gemini-extension.json")))["version"]
    body = rule.split("\n\n", 2)[2].strip()                   # the rule without its heading and its intro
    body = body.replace("<the skill's name>", skill).replace("<version>", version)
    return ("%s. **KISS feedback** (the feedback mode is on), in every run, also one that stops early or fails. "
            "This skill is `%s`, KISS %s.\n\n%s\n" % (n, skill, version, body))


def selftest():
    on = step(7, "kiss-doctor", {"KISS_FEEDBACK": "1"})
    version = json.load(open(os.path.join(os.path.dirname(HERE), "gemini-extension.json")))["version"]
    assert on.startswith("7. **KISS feedback**"), on[:80]
    assert "Skill: kiss-doctor, KISS %s" % version in on and "## KISS feedback" in on and "Proposed changes:" in on, on
    assert "feedback mode is off by default" not in on and "<version>" not in on.replace("KISS <version>`", "") and "Keep the project out" in on, on
    for env in ({}, {"KISS_FEEDBACK": ""}, {"KISS_FEEDBACK": "0"}, {"KISS_FEEDBACK": "true"}):
        assert step(7, "kiss-doctor", env) == "", env
    print("feedback selftest ok")


def main(argv):
    if argv[1:] == ["--selftest"]:
        return selftest()
    if len(argv) != 3:
        sys.exit(__doc__)
    sys.stdout.write(step(argv[1], argv[2], os.environ))


if __name__ == "__main__":
    main(sys.argv)
