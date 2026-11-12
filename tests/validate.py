"""Static checks run before packaging: AST parse, compile, and a globals scan.

The globals scan reports, per function:
  - a 'global' statement that comes after the name is first used in that function;
  - assignment to a module-level name without a 'global' declaration (creates a local
    that silently shadows the global).
Run: python tests/validate.py [files...]   (defaults to every .py in the repo root)
"""
import ast
import glob
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Present in v1.3.0, reported but not counted. selectionChanged's local sendValue may be a
# real bug (it shadows the global the slider path sends); left alone because nothing asked for it.
KNOWN = {("connectToLight", "lightName"), ("_animEditJSON", "errDlg"),
         ("selectionChanged", "sendValue"), ("saveCustomPresetDialog", "errDlg")}


def moduleGlobals(tree):
    """Names bound by module-level statements, following if/try/for/with blocks but not
    descending into function or class bodies."""
    names = set()

    def visit(stmts):
        for node in stmts:
            if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for t in targets:
                    for x in ast.walk(t):
                        if isinstance(x, ast.Name):
                            names.add(x.id)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(node.name)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    names.add((alias.asname or alias.name).split(".")[0])
            elif isinstance(node, (ast.If, ast.For, ast.While, ast.With)):
                visit(node.body)
                visit(getattr(node, "orelse", []))
            elif isinstance(node, ast.Try):
                visit(node.body)
                for h in node.handlers:
                    visit(h.body)
                visit(node.orelse)
                visit(node.finalbody)

    visit(tree.body)
    return names


def scanFunction(fn, globalsSet, path, problems):
    declared = {}
    for n in ast.walk(fn):
        if isinstance(n, ast.Global):
            for name in n.names:
                declared.setdefault(name, n.lineno)
    firstUse = {}
    stores = {}
    for n in ast.walk(fn):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)) and n is not fn:
            continue
        if isinstance(n, ast.Name):
            firstUse[n.id] = min(firstUse.get(n.id, n.lineno), n.lineno)
            if isinstance(n.ctx, ast.Store):
                stores.setdefault(n.id, n.lineno)
    for name, line in declared.items():
        if name in firstUse and firstUse[name] < line:
            problems.append("%s:%d %s(): '%s' used on line %d before its global declaration" % (path, line, fn.name, name, firstUse[name]))
    args = {a.arg for a in fn.args.args + fn.args.kwonlyargs + fn.args.posonlyargs}
    for name, line in stores.items():
        if name in globalsSet and name not in declared and name not in args:
            known = " [known, v1.3.0]" if (fn.name, name) in KNOWN else ""
            problems.append("%s:%d %s(): assigns module global '%s' without a global declaration%s" % (path, line, fn.name, name, known))


# Functions that run on the worker, HTTP or compositor threads. Qt widgets may only be used on
# the GUI thread, so these reach the main window only through its signals (mainWindow.xSignal.emit),
# runOnGui and selectionSnapshot.
OFF_GUI_THREAD = {"workerThread", "writeToLight", "parallelWriteToLights", "parallelAction", "connectToLight",
                  "disconnectFromLight", "processMultipleSends", "sendShowFrames", "processHTMLCommands",
                  "findDevices", "getLightChannelandPower", "printDebugString", "do_GET", "do_POST"}
GUI_SAFE = {"runOnGui", "selectionSnapshot"}


def scanGuiCalls(fn, path, problems):
    for n in ast.walk(fn):
        if not isinstance(n, ast.Call):
            continue
        chain = []
        f = n.func
        while isinstance(f, ast.Attribute):
            chain.insert(0, f.attr)
            f = f.value
        if not (isinstance(f, ast.Name) and f.id == "mainWindow" and chain):
            continue
        if chain[0] in GUI_SAFE or (len(chain) == 2 and chain[0].endswith("Signal") and chain[1] == "emit"):
            continue
        problems.append("%s:%d %s(): calls mainWindow.%s off the GUI thread (emit a signal or use runOnGui)"
                        % (path, n.lineno, fn.name, ".".join(chain)))


def checkFile(path):
    problems = []
    src = open(path, encoding="utf-8").read()
    try:
        tree = ast.parse(src, filename=path)
    except SyntaxError as e:
        return ["%s: AST parse failed: %s" % (path, e)]
    try:
        compile(src, path, "exec")  # in memory, so no .pyc lands next to the source
    except SyntaxError as e:
        problems.append("%s: compile failed: %s" % (path, e))
    g = moduleGlobals(tree)
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            scanFunction(n, g, os.path.basename(path), problems)
            if n.name in OFF_GUI_THREAD and os.path.basename(path) == "NeewerLux.py":
                scanGuiCalls(n, os.path.basename(path), problems)
    return problems


def main(argv):
    files = argv or sorted(glob.glob(os.path.join(ROOT, "*.py")))
    allProblems = []
    for f in files:
        allProblems += checkFile(f)
    for p in allProblems:
        print(p)
    new = [p for p in allProblems if not p.endswith("[known, v1.3.0]")]
    print("validate:", len(files), "files,", len(new), "new findings,", len(allProblems) - len(new), "known from v1.3.0")
    return 1 if new else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
