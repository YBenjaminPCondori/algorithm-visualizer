"""Runs supported LeetCode Solution methods within a child interpreter.

NOT a security boundary: AST checks, restricted builtins and process timeouts do not
make Python execution safe against malicious code. Use locally trusted solutions.
"""
import ast
import contextlib
import inspect
import io
import json
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
from tracing import TraceRecorder, TraceLimit, UnsupportedTraceValue
import traceback
import typing

VERSION = "1.0.0"
MAX_RESULT_BYTES = 65536
MAX_OUTPUT_NODES = 2001


class ListNode:
    """LeetCode-compatible singly linked list node injected into user globals."""

    def __init__(self, val=0, next=None):
        self.val = val
        self.next = next


def to_linked_list(values, node_cls):
    head = None
    tail = None
    for value in values:
        node = node_cls(value)
        # A compatible ListNode implementation must expose a mutable next field.
        node.next = None
        if tail is None:
            head = node
        else:
            tail.next = node
        tail = node
    return head


def from_linked_list(head, node_cls):
    result = []
    seen = set()
    node = head
    while node is not None:
        if not isinstance(node, node_cls):
            raise ValueError("result contains an object that is not a ListNode")
        ident = id(node)
        if ident in seen:
            raise ValueError("result linked list contains a cycle")
        seen.add(ident)
        if len(result) >= MAX_OUTPUT_NODES:
            raise ValueError("result linked list exceeds 2001 nodes")
        if type(node.val) is not int or not 0 <= node.val <= 9:
            raise ValueError("result contains a non-digit ListNode value")
        result.append(node.val)
        node = node.next
    return result


class UnsupportedSource(Exception):
    pass


class SourceChecker(ast.NodeVisitor):
    def visit_Import(self, node):
        raise UnsupportedSource("P3-02 does not support import statements")

    def visit_ImportFrom(self, node):
        if node.module != "typing" or node.level != 0 or any(
            item.name not in ("List", "Dict", "Tuple", "Optional", "Any") for item in node.names
        ):
            raise UnsupportedSource("P3-02 supports only selected typing imports")
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
    env = {"__builtins__": allowed, "__name__": "__solution__", "ListNode": ListNode}
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
            method_name = inv["method"]
            method = getattr(solution, method_name, None)
            if not callable(method):
                return error("UNSUPPORTED_SIGNATURE", "Solution." + method_name + " is not callable", "validation")
            args = inv["args"]
            node_cls = env.get("ListNode")
            if method_name == "addTwoNumbers":
                if not inspect.isclass(node_cls):
                    return error("UNSUPPORTED_SIGNATURE", "ListNode must be a class", "validation")
                try:
                    args = [to_linked_list(values, node_cls) for values in args]
                except (TypeError, AttributeError) as exc:
                    return error("UNSUPPORTED_SIGNATURE", "ListNode construction failed: " + str(exc), "validation")
            try:
                inspect.signature(method).bind(*args)
            except (ValueError, TypeError):
                return error("UNSUPPORTED_SIGNATURE", "Solution." + method_name + " does not accept two inputs", "validation")
            trace_requested = req.get('trace', {}).get('enabled', False)
            recorder = TraceRecorder(method.__func__.__code__, req['trace'].get('maxEvents', 250)) if trace_requested else None
            if recorder:
                sys.settrace(recorder.trace)
            try:
                value = method(*args)
            finally:
                if recorder:
                    sys.settrace(None)
    except TraceLimit as exc:
        response = error("EVENT_LIMIT", str(exc), "execution")
        response['status'] = 'limited'
        return response
    except UnsupportedTraceValue as exc:
        return error("UNSUPPORTED_VALUE", str(exc), "execution")
    except BaseException as exc:
        return error("RUNTIME_EXCEPTION", f"{type(exc).__name__}: {exc}", "execution", source_line(exc))

    if inv["method"] == "twoSum":
        if not (isinstance(value, list) and all(type(v) is int for v in value) and len(value) in (0, 2)):
            return error("UNSUPPORTED_VALUE", "Two Sum must return [] or a two-element integer index list", "serialization")
        result = value
    else:
        try:
            result = from_linked_list(value, node_cls)
        except (ValueError, AttributeError, TypeError) as exc:
            return error("UNSUPPORTED_VALUE", "Add Two Numbers result: " + str(exc), "serialization")
    try:
        if len(json.dumps(result, allow_nan=False, separators=(",", ":")).encode("utf-8")) > MAX_RESULT_BYTES:
            raise ValueError("result too large")
    except (TypeError, ValueError):
        return error("SERIALIZATION_ERROR", "Result is not serializable", "serialization")
    response = {"contractVersion": VERSION, "status": "completed", "result": result, "error": None}
    if recorder:
        response['trace'] = recorder.envelope(req)
    return response


def main():
    try:
        req = json.loads(sys.stdin.read())
        response = run(req)
    except BaseException:
        response = error("INTERNAL_ERROR", "Unexpected worker failure", "internal")
    sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()
