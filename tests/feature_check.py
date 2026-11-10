"""Guards against packaging from a stale copy: compares this checkout with a previous
release and reports anything that disappeared.

Checks every top-level function and class method, every widget attribute set in the UI
module, every global preference key, every HTTP GET parameter and POST endpoint, and the
animation library. Intentional removals are listed in REMOVED with the reason.
Run: python tests/feature_check.py <path to the previous release>
"""
import ast
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

REMOVED = {
    "animationEngineThread": "replaced by neewerlux_show.AnimationTimeline and the compositor",
    "animationSendFrame": "replaced by commandToByteValue and the show mailbox",
    "interpolateHSI": "moved to neewerlux_show (_lerpHSI)",
    "interpolateCCT": "moved to neewerlux_show (_lerpCCT)",
    "notifyCallback": "replaced by per-light callbacks from _makeNotifyCallback",
}


def functions(path):
    tree = ast.parse(open(path, encoding="utf-8").read())
    names = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(n.name)
    return names


def selfAttrs(path):
    return set(re.findall(r"self\.([A-Za-z_][A-Za-z0-9_]*)\s*=", open(path, encoding="utf-8").read()))


def prefKeys(path):
    src = open(path, encoding="utf-8").read()
    return set(re.findall(r'prefsParser\.add_argument\("--([A-Za-z_0-9]+)"', src))


def httpArgs(path):
    src = open(path, encoding="utf-8").read()
    return set(re.findall(r'parser\.add_argument\("--([a-z_]+)"', src))


def postPaths(path):
    return set(re.findall(r'"(/NeewerLux/[a-z]+)"', open(path, encoding="utf-8").read()))


def animations(root):
    d = os.path.join(root, "light_prefs", "animations")
    return set(os.listdir(d)) if os.path.isdir(d) else set()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    old = os.path.abspath(sys.argv[1])
    problems = []

    def compare(label, a, b, allowed=()):
        missing = sorted(x for x in a - b if x not in allowed)
        for m in missing:
            problems.append(label + ": " + m + " is missing")
        print("%-24s %4d before, %4d now, %d missing" % (label, len(a), len(b), len(missing)))

    oldFuncs, newFuncs = set(), set()
    for f in os.listdir(old):
        if f.endswith(".py"):
            oldFuncs |= functions(os.path.join(old, f))
            if os.path.exists(os.path.join(ROOT, f)):
                newFuncs |= functions(os.path.join(ROOT, f))
            else:
                problems.append("module " + f + " is missing")
    compare("functions and classes", oldFuncs, newFuncs, REMOVED)
    for name in sorted(REMOVED):
        if name in oldFuncs and name not in newFuncs:
            print("  removed on purpose:", name, "-", REMOVED[name])
    compare("UI widget attributes", selfAttrs(os.path.join(old, "neewerlux_ui.py")), selfAttrs(os.path.join(ROOT, "neewerlux_ui.py")))
    compare("main window attributes", selfAttrs(os.path.join(old, "NeewerLux.py")), selfAttrs(os.path.join(ROOT, "NeewerLux.py")))
    compare("preference keys", prefKeys(os.path.join(old, "NeewerLux.py")), prefKeys(os.path.join(ROOT, "NeewerLux.py")))
    compare("HTTP GET parameters", httpArgs(os.path.join(old, "NeewerLux.py")), httpArgs(os.path.join(ROOT, "NeewerLux.py")))
    compare("HTTP paths", postPaths(os.path.join(old, "NeewerLux.py")), postPaths(os.path.join(ROOT, "NeewerLux.py")))
    compare("animation files", animations(old), animations(ROOT))
    for p in problems:
        print("MISSING", p)
    print("feature check:", "PASS" if not problems else "FAIL")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
