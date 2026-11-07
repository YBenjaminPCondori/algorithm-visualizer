# P3-01: Standalone LeetCode Two Sum execution wrapper

**Status:** Experimental, standalone Python implementation. No tracing/AI/visualisation/frontend changes.

## Run

From the root containing `python_runner/`, using Python 3.8+:

```powershell
python python_runner/run.py < python_runner/examples/two_sum_request.json
python -m unittest discover -s python_runner/tests -v
```

`run.py` accepts a UTF-8 JSON request on stdin and emits one JSON response on stdout. No external Python dependencies.

### Request

```json
{
  "contractVersion": "1.0.0",
  "source": {"filename": "solution.py", "text": "class Solution:\n    def twoSum(self, nums, target):\n        return [0,1]"},
  "invocation": {"className": "Solution", "method": "twoSum", "args": [[2,7,11,15],9]},
  "limits": {"wallTimeMs": 2000}
}
```

### Success response

```json
{"contractVersion":"1.0.0","status":"completed","result":[0,1],"error":null,"sourceSha256":"<SHA-256>"}
```

Errors have `status:"failed"` and `{code,message,phase,sourceLine}`; timeout has `status:"limited"` and code `EXECUTION_TIMEOUT`. Exit codes: success 0, failed 1, limited 2. `sourceSha256` is a hex digest for validated requests, otherwise null.

## Scope

- Supports `Solution.twoSum(nums: list[int], target: int)` with JSON integer inputs.
- Does **not** support linked lists, arbitrary libraries, other LeetCode methods, execution traces, visualisations or arbitrary Python values.
- The user's submitted source is compiled verbatim; it is never edited to add tracer calls.
- Attempts to reject direct imports (except selected `typing` imports) and dunder attribute access. These are *compatibility and accident-reduction checks*, **not a security sandbox**.
- A subprocess timeout is enforced by the parent. CPU and memory quotas, process-tree containment, filesystem/network restrictions and robust OS isolation are **not** implemented; do not run malicious or untrusted third-party code. Windows process descendants may survive a parent timeout.
- The implementation never modifies the existing React application, dependencies or npm lockfile.
- No HTTP service yet; a local HTTP adapter belongs to a later phase.

## Next milestone

P3-02 `ListNode` support only after this runner is reviewed. P4-01 execution tracing remains separate.
