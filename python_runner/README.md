# Python LeetCode runner (P3-02)

A standalone **Python CLI**, with **no external Python dependencies**. It executes locally trusted, unmodified `class Solution` code using JSON input/output. This does **not** yet integrate with the React visualiser or produce trace events.

## Supported methods

| Method | `invocation.args` | Result |
| --- | --- | --- |
| `twoSum` | `[nums, target]` where `nums` is an integer array and `target` is an integer | `[]` or `[index1, index2]` |
| `addTwoNumbers` | `[l1, l2]` where each is an array of 0–9 digits in **reverse-digit order** | Array of result digits, likewise reversed |

For `addTwoNumbers`, the runner converts the arrays to singly linked lists before calling the source. It injects the usual `ListNode(val=0, next=None)` definition, unless the source defines its own `ListNode` class. `Optional`, `List`, `Dict`, `Tuple`, and `Any` are also available for LeetCode-style type annotations. Empty input arrays become `None` and a `None` return becomes `[]`; this is an extension beyond LeetCode 2's nonempty-input constraints.

Up to **1,000 digits per input list** are accepted. The output is checked for cyclic references, invalid node values, bad node types and excessive length.

## Run locally

From the repository root, using Python 3.8+:

**Windows PowerShell:**

```powershell
Get-Content -Raw python_runner/examples/two_sum_request.json | python python_runner/run.py
Get-Content -Raw python_runner/examples/add_two_numbers_request.json | python python_runner/run.py
python -m unittest discover -s python_runner/tests -v
```

**Bash:**

```bash
python python_runner/run.py < python_runner/examples/two_sum_request.json
python python_runner/run.py < python_runner/examples/add_two_numbers_request.json
python -m unittest discover -s python_runner/tests -v
```

## Request contract

```json
{
  "contractVersion": "1.0.0",
  "source": {"filename": "solution.py", "text": "class Solution:\n    def addTwoNumbers(self, l1, l2):\n        return l1"},
  "invocation": {"className": "Solution", "method": "addTwoNumbers", "args": [[2, 4, 3], [5, 6, 4]]},
  "limits": {"wallTimeMs": 2000}
}
```

The example source above only demonstrates the request shape; use `examples/add_two_numbers_request.json` for the actual addition algorithm.

Successful response shape:

```json
{"contractVersion":"1.0.0","status":"completed","result":[7,0,8],"error":null,"sourceSha256":"<hex SHA-256>"}
```

Failures have `status: "failed"` and `error: {code, message, phase, sourceLine}`. Timeout uses `status: "limited"` and `EXECUTION_TIMEOUT`. Process exit codes are 0 for completed, 1 for failed, 2 for limited.

## Limitations / security

- **Not a security sandbox.** It must only be used with locally trusted code. Restricted imports/dunder filtering and child process wall-time termination are not sufficient protections against hostile Python code; there are no CPU/memory/filesystem/network quotas or process-tree containment.
- Supports only the two named methods, with deliberately narrow JSON input and output types. Source code is compiled **unchanged** (not rewritten to add instrumentation).
- No execution trace, AST/line-event capture, hash-table or linked-list visualisation, AI model, HTTP endpoint, Node.js package modification or UI integration.
- The tool preserves the original front-end and lockfile. Tracing begins in a later phase.
