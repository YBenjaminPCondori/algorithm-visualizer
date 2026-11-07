"""P3-02 LeetCode Python runner: validated JSON stdin -> isolated worker -> JSON stdout.

Execution is for locally trusted code. A subprocess plus restricted builtins is NOT a sandbox.
"""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

CONTRACT_VERSION = "1.0.0"
MAX_REQUEST_BYTES = 65536
MAX_SOURCE_BYTES = 32768
DEFAULT_TIMEOUT_MS = 2000
MAX_TIMEOUT_MS = 10000


def failure(code, message, phase="validation", status="failed", source_line=None):
    return {
        "contractVersion": CONTRACT_VERSION,
        "status": status,
        "result": None,
        "sourceSha256": None,
        "error": {
            "code": code,
            "message": message,
            "phase": phase,
            "sourceLine": source_line,
        },
    }


def validate_request(req):
    if not isinstance(req, dict):
        raise ValueError("request must be a JSON object")
    if req.get("contractVersion") != CONTRACT_VERSION:
        raise ValueError("contractVersion must be '1.0.0'")
    source = req.get("source")
    if not isinstance(source, dict) or not isinstance(source.get("text"), str):
        raise ValueError("source.text must be a string")
    if not isinstance(source.get("filename", "solution.py"), str):
        raise ValueError("source.filename must be a string")
    if not source["text"].strip():
        raise ValueError("source.text must not be empty")
    if len(source["text"].encode("utf-8")) > MAX_SOURCE_BYTES:
        raise ValueError("source.text exceeds 32768 UTF-8 bytes")
    invocation = req.get("invocation")
    if not isinstance(invocation, dict):
        raise ValueError("invocation must be an object")
    if invocation.get("className") != "Solution":
        raise ValueError("invocation.className must be 'Solution'")
    method = invocation.get("method")
    if method not in ("twoSum", "addTwoNumbers"):
        raise ValueError("P3-02 supports only invocation.method=twoSum or addTwoNumbers")
    args = invocation.get("args")
    if not isinstance(args, list) or len(args) != 2:
        raise ValueError("invocation.args must contain [nums, target]")
    first, second = args
    if method == "twoSum":
        if not isinstance(first, list) or not all(type(x) is int for x in first):
            raise TypeError("nums must be a JSON array of integers")
        if type(second) is not int:
            raise TypeError("target must be a JSON integer")
    else:
        for name, digits in zip(("l1", "l2"), (first, second)):
            if not isinstance(digits, list) or len(digits) > 1000 or not all(
                type(d) is int and 0 <= d <= 9 for d in digits
            ):
                raise TypeError(f"{name} must be an array of at most 1000 digits in 0..9")
    limits = req.get("limits", {})
    if not isinstance(limits, dict):
        raise ValueError("limits must be an object")
    timeout = limits.get("wallTimeMs", DEFAULT_TIMEOUT_MS)
    if type(timeout) is not int or not (1 <= timeout <= MAX_TIMEOUT_MS):
        raise ValueError("limits.wallTimeMs must be an integer from 1 to 10000")
    return timeout


def execute_request(req):
    try:
        timeout_ms = validate_request(req)
    except (TypeError, ValueError) as exc:
        code = "UNSUPPORTED_VALUE" if isinstance(exc, TypeError) else "INVALID_REQUEST"
        return failure(code, str(exc))

    digest = hashlib.sha256(req["source"]["text"].encode("utf-8")).hexdigest()
    worker = Path(__file__).with_name("_worker.py")
    cmd = [sys.executable, "-I", "-B", str(worker)]
    try:
        proc = subprocess.run(
            cmd,
            input=json.dumps(req, ensure_ascii=False),
            capture_output=True,
            text=True,
            timeout=timeout_ms / 1000.0,
            check=False,
        )
    except subprocess.TimeoutExpired:
        resp = failure("EXECUTION_TIMEOUT", "Execution exceeded the wall-time limit", phase="execution", status="limited")
        resp["sourceSha256"] = digest
        return resp
    except OSError:
        resp = failure("INTERNAL_ERROR", "Could not start the Python worker", phase="internal")
        resp["sourceSha256"] = digest
        return resp

    try:
        response = json.loads(proc.stdout)
        if not isinstance(response, dict) or response.get("contractVersion") != CONTRACT_VERSION:
            raise ValueError("invalid worker response")
        if response.get("status") not in ("completed", "failed", "limited"):
            raise ValueError("invalid worker status")
    except (ValueError, json.JSONDecodeError):
        response = failure("INTERNAL_ERROR", "Python worker failed to return a valid response", phase="internal")
    response["sourceSha256"] = digest
    return response


def main():
    raw = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
    if len(raw) > MAX_REQUEST_BYTES:
        response = failure("INVALID_REQUEST", "Request exceeds 65536 bytes")
    else:
        try:
            req = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            response = failure("INVALID_REQUEST", "Request is not valid UTF-8 JSON")
        else:
            response = execute_request(req)
    sys.stdout.write(json.dumps(response, separators=(",", ":"), ensure_ascii=False) + "\n")
    return 0 if response["status"] == "completed" else 2 if response["status"] == "limited" else 1


if __name__ == "__main__":
    sys.exit(main())
