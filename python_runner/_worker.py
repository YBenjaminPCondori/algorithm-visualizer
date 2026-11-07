"""Runs a narrowly supported LeetCode Solution.twoSum within a child interpreter.

NOT a security boundary: AST checks, restricted builtins and process timeouts do not
make Python execution safe against malicious code. Use locally trusted solutions.
"""
import ast
import contextlib
import inspect
import io
import json
import math
import sys
import traceback
import typing

VERSION = "1.0.0"
MAX_RESULT_BYTES = 65536


class UnsupportedSource(Exception):
    pass


class SourceChecker(ast.NodeVisitor):
    def visit_Import(self, node):
        raise UnsupportedSource("P3-01 does not support import statements")

    def visit_ImportFrom(self, node):
        if node.module != "typing" or node.level != 0 or any(
            item.name not in ("List", "Dict", "Tuple", "Optional", "Any") for item in node.names
        ):
            raise UnsupportedSource("P3-01 supports only selected typing imports")
        self.generic_visit(node)

    def visit_Attribute(self, node):
        if node.attr.startswith("__"):
            raise UnsupportedSource("dunder attribute access is unsupported")
        self.generic_visit(node)

    def visit_Name(self, node):
        if node.id in ("__builtins__", "__loader__", "__spec__", "__import__"):
            raise UnsupportedSource("runtime introspection names are unsupported")
        self.generic_visit(node)


BUILTIN_NAMES = (
    "__build_class__", "object", "enumerate", "range", "len", "dict", "list", "set",
    "tuple", "int", "float", "str", "bool", "abs", "min", "max", "sum",
    "zip", "sorted", "reversed", "any", "all", "isinstance", "ValueError",
    "TypeError", "Exception", "print"
)


def limited_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name != "typing" or level:
        raise ImportError("Only selected typing imports are supported")
    return typing


def error(code, message, phase, line=None):
    return {
        "contractVersion": VERSION,
        "status": "failed",
        "result": None,
        "error": {"code": code, "message": message[:300], "phase": phase, "sourceLine": line},
    }


def source_line(exc):
    if isinstance(exc, SyntaxError):
        return exc.lineno
    for frame in traceback.extract_tb(exc.__traceback__)[::-1]:
        if frame.filename == "solution.py":
            return frame.lineno
    return None


def run(req):
    source = req["source"]["text"]
    inv = req["invocation"]
    try:
        tree = ast.parse(source, filename="solution.py")
        SourceChecker().visit(tree)
    except SyntaxError as exc:
        return error("INVALID_REQUEST", f"SyntaxError: {exc.msg}", "validation", exc.lineno)
    except UnsupportedSource as exc:
        return error("UNSUPPORTED_SIGNATURE", str(exc), "validation")

    import builtins
    allowed = {name: getattr(builtins, name) for name in BUILTIN_NAMES}
    allowed["__import__"] = limited_import
    env = {"__builtins__": allowed, "__name__": "__solution__"}
    for name in ("List", "Dict", "Tuple", "Optional", "Any"):
        env[name] = getattr(typing, name)

    try:
        # Silences ordinary print() so the worker's stdout remains JSON-only.
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            exec(compile(tree, "solution.py", "exec"), env, env)
            cls = env.get("Solution")
            if not inspect.isclass(cls):
                return error("UNSUPPORTED_SIGNATURE", "class Solution was not found", "validation")
            solution = cls()
            method = getattr(solution, "twoSum", None)
            if not callable(method):
                return error("UNSUPPORTED_SIGNATURE", "Solution.twoSum is not callable", "validation")
            try:
                inspect.signature(method).bind(*inv["args"])
            except (ValueError, TypeError):
                return error("UNSUPPORTED_SIGNATURE", "Solution.twoSum signature does not accept [nums, target]", "validation")
            value = method(*inv["args"])
    except BaseException as exc:
        return error("RUNTIME_EXCEPTION", f"{type(exc).__name__}: {exc}", "execution", source_line(exc))

    if isinstance(value, list) and all(type(v) is int for v in value) and len(value) in (0, 2):
        try:
            result_json = json.dumps(value, allow_nan=False, separators=(",", ":"))
            if len(result_json.encode("utf-8")) > MAX_RESULT_BYTES:
                raise ValueError("result too large")
        except (TypeError, ValueError):
            return error("SERIALIZATION_ERROR", "Result is not serializable", "serialization")
        return {"contractVersion": VERSION, "status": "completed", "result": value, "error": None}
    return error("UNSUPPORTED_VALUE", "Two Sum must return [] or a two-element integer index list", "serialization")


def main():
    try:
        req = json.loads(sys.stdin.read())
        response = run(req)
    except BaseException:
        response = error("INTERNAL_ERROR", "Unexpected worker failure", "internal")
    sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()
