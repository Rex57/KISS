#!/usr/bin/env python3
"""The guarded write of kiss-dream (SKILL.md, "Another writer"): every change to a memory folder goes through here.

  python3 -I guard.py start MEMDIR            make the private scratch folder (first/, expected/, drafts/); print it
                                              (LOCK-HELD, exit 3, and no copy when the lock is held)
  python3 -I guard.py where MEMDIR            print this run's scratch folder (the newest one for MEMDIR)
  python3 -I guard.py write MEMDIR FILE...    copy drafts/FILE into MEMDIR
  python3 -I guard.py move MEMDIR TRASH FILE...  move MEMDIR/FILE into the TRASH folder
  python3 -I guard.py again MEMDIR            after CHANGED: copy MEMDIR to copy-2/ (copy-3/...), make it the expected copy
  python3 -I guard.py finish MEMDIR TRASH     at the end: move this run's scratch folder into the TRASH folder
  python3 -I guard.py --selftest

Before a write or move: LOCK-HELD (exit 3) when MEMDIR/.consolidate-lock is under one hour old and its PID lives;
CHANGED (exit 4) and the changed files when MEMDIR differs from expected/ (a note this run did not write). Else it
writes, updates expected/, prints WRITTEN and compares each written note with its draft (exit 5 on a difference).
It never writes, touches or removes the lock. The scratch folder is ~/.cache/kiss-dream/<project>-<time>/, mode 700.
"""
import filecmp, os, shutil, sys, time

LOCK = ".consolidate-lock"


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
    if lock_held(memdir):
        return None
    os.makedirs(root(), mode=0o700, exist_ok=True)
    base = os.path.join(root(), "%s@%s" % (project(memdir), time.strftime("%Y%m%d-%H%M%S")))
    c, n = base, 1
    while os.path.exists(c):
        n += 1
        c = "%s-%d" % (base, n)
    os.mkdir(c, 0o700)
    copy(memdir, os.path.join(c, "first"))
    copy(memdir, os.path.join(c, "expected"))
    os.mkdir(os.path.join(c, "drafts"))
    return c


def lock_held(memdir, now=None):
    path = os.path.join(memdir, LOCK)
    try:
        age = (now or time.time()) - os.path.getmtime(path)
        text = open(path).read().split()
    except OSError:
        return False
    if age >= 3600:
        return False
    try:
        pid = int(text[0])                          # Claude Code may add a second line (a time)
    except (IndexError, ValueError):
        return True                                 # a fresh lock we cannot read: treat it as held
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
    # shortcut: the lock is checked, not held; a writer that starts during this write is caught only at the next
    # write. Upgrade to taking a lock of our own if Claude Code ever documents one for other writers.
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
    n = 2
    while os.path.exists(os.path.join(c, "copy-%d" % n)):
        n += 1
    name = "copy-%d" % n
    diff = changed(memdir, os.path.join(c, "expected"))
    copy(memdir, os.path.join(c, name))
    shutil.rmtree(os.path.join(c, "expected"))
    copy(memdir, os.path.join(c, "expected"))
    return 0, ["new copy %s; changed since the last copy: %s" % (os.path.join(c, name), " ".join(diff) or "nothing")]


def finish(memdir, c, trash):
    os.makedirs(trash, exist_ok=True)
    dst = os.path.join(trash, os.path.basename(c))
    shutil.move(c, dst)
    return 0, ["scratch folder moved to %s" % dst]


def selftest():
    import subprocess, tempfile
    with tempfile.TemporaryDirectory() as t:
        os.environ["XDG_CACHE_HOME"] = os.path.join(t, "cache")
        mem = os.path.join(t, "proj-x", "memory")
        os.makedirs(mem)
        for f, text in [("MEMORY.md", "- [a](a.md)\n"), ("a.md", "old a\n"), ("b.md", "old b\n")]:
            open(os.path.join(mem, f), "w").write(text)
        c = start(mem)
        c2 = start(mem)                                    # a second start in the same second gets its own folder
        assert c2 != c and os.path.isdir(c2)
        shutil.rmtree(c2)
        assert where(mem) == c and oct(os.stat(c).st_mode & 0o777) == "0o700", c
        assert sorted(os.listdir(c)) == ["drafts", "expected", "first"]
        open(os.path.join(c, "drafts", "a.md"), "w").write("new a\n")
        # a held lock: a live PID, written now
        sleeper = subprocess.Popen(["sleep", "30"])
        try:
            open(os.path.join(mem, LOCK), "w").write(str(sleeper.pid))
            code, out = write(mem, c, ["a.md"])
            assert code == 3 and out[0].startswith("LOCK-HELD"), out
            assert start(mem) is None                      # start refuses under a held lock, before any copy
            assert open(os.path.join(mem, "a.md")).read() == "old a\n"
            assert move(mem, c, os.path.join(t, "trash"), ["b.md"])[0] == 3 and os.path.isfile(os.path.join(mem, "b.md"))
            # an old lock (over one hour) does not hold
            old = time.time() - 3700
            os.utime(os.path.join(mem, LOCK), (old, old))
            assert not lock_held(mem)
        finally:
            sleeper.kill()
            sleeper.wait()
        # Claude Code's two-line lock (the PID, then a time) holds too
        sleeper = subprocess.Popen(["sleep", "30"])
        try:
            open(os.path.join(mem, LOCK), "w").write("%d\n1793681077000" % sleeper.pid)
            assert lock_held(mem) and write(mem, c, ["a.md"])[0] == 3
        finally:
            sleeper.kill()
            sleeper.wait()
        # an empty fresh lock reads as held; an empty old one does not
        open(os.path.join(mem, LOCK), "w").close()
        assert lock_held(mem)
        old = time.time() - 3700
        os.utime(os.path.join(mem, LOCK), (old, old))
        assert not lock_held(mem)
        open(os.path.join(mem, LOCK), "w").write("999999999")
        # a dead PID does not hold, also when the lock is new
        os.utime(os.path.join(mem, LOCK), None)
        assert not lock_held(mem)
        # another writer changed a note: no write, CHANGED names it
        open(os.path.join(mem, "b.md"), "a").write("late fact\n")
        code, out = write(mem, c, ["a.md"])
        assert code == 4 and out == ["CHANGED: b.md"], out
        assert open(os.path.join(mem, "a.md")).read() == "old a\n"
        code, out = again(mem, c)
        assert code == 0 and "copy-2" in out[0] and out[0].endswith("b.md"), out
        for _ in range(5):                                 # more copies than names once existed: no StopIteration
            again(mem, c)
        assert os.path.isdir(os.path.join(c, "copy-7"))
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
        # the end: the scratch folder goes into the trash, and no copy stays in the cache
        code, out = finish(mem, c, os.path.join(t, "trash"))
        assert code == 0 and not os.path.exists(c) and os.path.isdir(os.path.join(t, "trash", os.path.basename(c), "first")), out
    print("guard selftest ok")


def main(argv):
    if argv[1:] == ["--selftest"]:
        return selftest()
    if len(argv) < 3 or argv[1] not in ("start", "where", "write", "move", "again", "finish"):
        sys.exit(__doc__)
    cmd, memdir = argv[1], argv[2]
    if not os.path.isdir(memdir):
        sys.exit("not a folder: %s" % memdir)
    if cmd == "start":
        c = start(memdir)
        if c is None:
            print("LOCK-HELD: another consolidation holds %s; nothing copied" % os.path.join(memdir, LOCK))
            sys.exit(3)
        print(c)
        return
    if cmd == "where":
        print(where(memdir))
        return
    c = where(memdir)
    if cmd in ("write", "move", "finish") and len(argv) < (5 if cmd == "move" else 4):
        sys.exit("name the files to %s" % cmd)
    if cmd == "write":
        code, out = write(memdir, c, argv[3:])
    elif cmd == "move":
        code, out = move(memdir, c, argv[3], argv[4:])
    elif cmd == "finish":
        code, out = finish(memdir, c, argv[3])
    else:
        code, out = again(memdir, c)
    print("\n".join(out))
    sys.exit(code)


if __name__ == "__main__":
    main(sys.argv)
