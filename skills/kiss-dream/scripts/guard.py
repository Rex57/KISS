#!/usr/bin/env python3
"""The guarded write of kiss-dream (SKILL.md, "Another writer"): every change to a memory folder goes through here.

  python3 -I guard.py start MEMDIR            make the private scratch folder (first/, expected/, drafts/); print it
  python3 -I guard.py where MEMDIR            print this run's scratch folder (the newest one for MEMDIR)
  python3 -I guard.py write MEMDIR FILE...    copy drafts/FILE into MEMDIR
  python3 -I guard.py move MEMDIR TRASH FILE...  move MEMDIR/FILE into the TRASH folder
  python3 -I guard.py again MEMDIR            after CHANGED: copy MEMDIR to second/ (third/...), make it the expected copy
  python3 -I guard.py --selftest

Before a write or move: LOCK-HELD (exit 3) when MEMDIR/.consolidate-lock is under one hour old and its PID lives;
CHANGED (exit 4) and the changed files when MEMDIR differs from expected/ (a note this run did not write). Else it
writes, updates expected/, prints WRITTEN and compares each written note with its draft (exit 5 on a difference).
It never writes, touches or removes the lock. The scratch folder is ~/.cache/kiss-dream/<project>-<time>/, mode 700.
"""
import filecmp, os, shutil, sys, time

LOCK = ".consolidate-lock"
STEPS = ["second", "third", "fourth", "fifth"]


def root():
    return os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache"), "kiss-dream")


def project(memdir):
    return os.path.basename(os.path.dirname(os.path.abspath(memdir))) or "memory"


def where(memdir):
    runs = sorted(d for d in os.listdir(root()) if d.startswith(project(memdir) + "@")) if os.path.isdir(root()) else []
    if not runs:
        sys.exit("no scratch folder for %s: run `start` first" % memdir)
    return os.path.join(root(), runs[-1])


def copy(src, dst):
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(LOCK))


def start(memdir):
    os.makedirs(root(), mode=0o700, exist_ok=True)
    c = os.path.join(root(), "%s@%s" % (project(memdir), time.strftime("%Y%m%d-%H%M%S")))
    os.mkdir(c, 0o700)
    copy(memdir, os.path.join(c, "first"))
    copy(memdir, os.path.join(c, "expected"))
    os.mkdir(os.path.join(c, "drafts"))
    return c


def lock_held(memdir, now=None):
    path = os.path.join(memdir, LOCK)
    try:
        age = (now or time.time()) - os.path.getmtime(path)
        pid = int(open(path).read().strip())
    except (OSError, ValueError):
        return False
    if age >= 3600:
        return False
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True           # it lives, owned by another user
    except OSError:
        return False
    return True


def changed(memdir, expected):
    names = lambda d: {f for f in os.listdir(d) if f != LOCK and os.path.isfile(os.path.join(d, f))}
    have, want = names(memdir), names(expected)
    diff = sorted(have ^ want)
    diff += sorted(f for f in have & want if not filecmp.cmp(os.path.join(memdir, f), os.path.join(expected, f), shallow=False))
    return diff


def guarded(memdir, c, change):
    """Check, then change. Returns (exit code, lines)."""
    if lock_held(memdir):
        return 3, ["LOCK-HELD: another consolidation holds %s" % os.path.join(memdir, LOCK)]
    diff = changed(memdir, os.path.join(c, "expected"))
    if diff:
        return 4, ["CHANGED: %s" % " ".join(diff)]
    return change()


def write(memdir, c, files):
    def change():
        for f in files:
            shutil.copy2(os.path.join(c, "drafts", f), os.path.join(memdir, f))
            shutil.copy2(os.path.join(c, "drafts", f), os.path.join(c, "expected", f))
        bad = [f for f in files if not filecmp.cmp(os.path.join(c, "drafts", f), os.path.join(memdir, f), shallow=False)]
        return (5 if bad else 0), ["WRITTEN: %s" % " ".join(files)] + ["DIFFERS from its draft: %s" % f for f in bad]
    missing = [f for f in files if not os.path.isfile(os.path.join(c, "drafts", f))]
    return (2, ["no draft: %s" % " ".join(missing)]) if missing else guarded(memdir, c, change)


def move(memdir, c, trash, files):
    def change():
        os.makedirs(trash, exist_ok=True)
        for f in files:
            dst = os.path.join(trash, f)
            n = 1
            while os.path.exists(dst):
                n += 1
                dst = os.path.join(trash, "%s-%d" % (f, n))
            shutil.move(os.path.join(memdir, f), dst)
            os.remove(os.path.join(c, "expected", f))
        return 0, ["WRITTEN: moved %s to %s" % (" ".join(files), trash)]
    missing = [f for f in files if f == LOCK or not os.path.isfile(os.path.join(memdir, f))]
    return (2, ["not a note here: %s" % " ".join(missing)]) if missing else guarded(memdir, c, change)


def again(memdir, c):
    name = next(s for s in STEPS if not os.path.exists(os.path.join(c, s)))
    diff = changed(memdir, os.path.join(c, "expected"))
    copy(memdir, os.path.join(c, name))
    shutil.rmtree(os.path.join(c, "expected"))
    copy(memdir, os.path.join(c, "expected"))
    return 0, ["new copy %s; changed since the last copy: %s" % (os.path.join(c, name), " ".join(diff) or "nothing")]


def selftest():
    import subprocess, tempfile
    with tempfile.TemporaryDirectory() as t:
        os.environ["XDG_CACHE_HOME"] = os.path.join(t, "cache")
        mem = os.path.join(t, "proj-x", "memory")
        os.makedirs(mem)
        for f, text in [("MEMORY.md", "- [a](a.md)\n"), ("a.md", "old a\n"), ("b.md", "old b\n")]:
            open(os.path.join(mem, f), "w").write(text)
        c = start(mem)
        assert where(mem) == c and oct(os.stat(c).st_mode & 0o777) == "0o700", c
        assert sorted(os.listdir(c)) == ["drafts", "expected", "first"]
        open(os.path.join(c, "drafts", "a.md"), "w").write("new a\n")
        # a held lock: a live PID, written now
        sleeper = subprocess.Popen(["sleep", "30"])
        try:
            open(os.path.join(mem, LOCK), "w").write(str(sleeper.pid))
            code, out = write(mem, c, ["a.md"])
            assert code == 3 and out[0].startswith("LOCK-HELD"), out
            assert open(os.path.join(mem, "a.md")).read() == "old a\n"
            assert move(mem, c, os.path.join(t, "trash"), ["b.md"])[0] == 3 and os.path.isfile(os.path.join(mem, "b.md"))
            # an old lock (over one hour) does not hold
            old = time.time() - 3700
            os.utime(os.path.join(mem, LOCK), (old, old))
            assert not lock_held(mem)
        finally:
            sleeper.kill()
            sleeper.wait()
        # a dead PID does not hold, also when the lock is new
        os.utime(os.path.join(mem, LOCK), None)
        assert not lock_held(mem)
        # another writer changed a note: no write, CHANGED names it
        open(os.path.join(mem, "b.md"), "a").write("late fact\n")
        code, out = write(mem, c, ["a.md"])
        assert code == 4 and out == ["CHANGED: b.md"], out
        assert open(os.path.join(mem, "a.md")).read() == "old a\n"
        code, out = again(mem, c)
        assert code == 0 and "second" in out[0] and out[0].endswith("b.md"), out
        assert open(os.path.join(c, "first", "b.md")).read() == "old b\n"          # the first copy stays
        # the write goes through, expected follows, the lock is untouched
        lock_before = os.stat(os.path.join(mem, LOCK)).st_mtime
        code, out = write(mem, c, ["a.md"])
        assert code == 0 and out == ["WRITTEN: a.md"], out
        assert open(os.path.join(mem, "a.md")).read() == "new a\n" == open(os.path.join(c, "expected", "a.md")).read()
        assert os.stat(os.path.join(mem, LOCK)).st_mtime == lock_before
        # a move goes to the trash, and a second write does not see our own changes as another writer's
        code, out = move(mem, c, os.path.join(t, "trash"), ["b.md"])
        assert code == 0 and os.path.isfile(os.path.join(t, "trash", "b.md")) and not os.path.exists(os.path.join(mem, "b.md")), out
        open(os.path.join(c, "drafts", "MEMORY.md"), "w").write("- [a](a.md) new\n")
        assert write(mem, c, ["MEMORY.md"])[0] == 0
        assert write(mem, c, ["nope.md"])[0] == 2 and move(mem, c, t, [LOCK])[0] == 2
    print("guard selftest ok")


def main(argv):
    if argv[1:] == ["--selftest"]:
        return selftest()
    if len(argv) < 3 or argv[1] not in ("start", "where", "write", "move", "again"):
        sys.exit(__doc__)
    cmd, memdir = argv[1], argv[2]
    if not os.path.isdir(memdir):
        sys.exit("not a folder: %s" % memdir)
    if cmd == "start":
        print(start(memdir))
        return
    if cmd == "where":
        print(where(memdir))
        return
    c = where(memdir)
    if cmd in ("write", "move") and len(argv) < (4 if cmd == "write" else 5):
        sys.exit("name the files to %s" % cmd)
    if cmd == "write":
        code, out = write(memdir, c, argv[3:])
    elif cmd == "move":
        code, out = move(memdir, c, argv[3], argv[4:])
    else:
        code, out = again(memdir, c)
    print("\n".join(out))
    sys.exit(code)


if __name__ == "__main__":
    main(sys.argv)
