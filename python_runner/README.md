# Python LeetCode runner + Two Sum animation MVP

A standalone **Python CLI**, with **no external Python dependencies**. It executes locally trusted, unmodified `class Solution` code using JSON input/output. Two Sum now also supports opt-in execution tracing, an existing-format command adapter, and a local HTTP bridge for the React visualiser. Add Two Numbers execution remains unchanged; its animation is out of scope.

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
- Two Sum now supports observed post-line snapshots, array/hash-table/result commands, and a localhost HTTP endpoint. Linked-list **animation**, AI explanations and a secure public sandbox are not implemented. No Node package modifications.
- The tool preserves the original front-end and lockfile. Tracing begins in a later phase.

## Two Sum animation MVP

The animation reuses the existing `Array1DTracer`, `Array2DTracer`,
`VerticalLayout`, `Player` and `VisualizationViewer`; it does **not**
replace the rendering engine. Tracer snapshots represent actual completed
Python source lines; they do not expose every intermediate dictionary lookup
or arbitrary Python operation. A selection is shown when the loop variable is
named `index`, `i`, `idx`, `pos` or `j`.

### Start locally

Open **two terminals** in the repository root.

Terminal 1 — start the Python trace service (Python 3.8+):

```powershell
python python_runner/server.py
```

Confirm http://127.0.0.1:8765/health displays `status: ok`.

Terminal 2 — run the *existing* React development app using a compatible
Node.js version and its currently locked dependencies:

```powershell
npm.cmd start
```

At http://localhost:3000: choose **Python** in the language menu,
select **Scratch Paper → New ...**, and open the `code.py` tab.
Paste an ordinary `class Solution` / `twoSum` implementation without
any tracer modifications. Enter test arguments in the JSON input field,
for example `[[2,7,11,15],9]`. Click **Build**, then use
**Play**, **Pause**, **previous**, **next** and **Restart**.

The Python HTTP endpoint uses `127.0.0.1:8765` and accepts only
browser origins `localhost:3000` or `127.0.0.1:3000`.
Existing legacy back-end APIs still use the original React proxy at
`localhost:8080`. Without the optional original server, the algorithm
catalogue may show a loading error even when the Python animation path works.

The text input is positional `[nums, target]`. For example:
`[[3,3],6]` and `[[-3,4,3,90],0]`.

### API

`POST http://127.0.0.1:8765/api/tracers/py` with the existing
request envelope for `Solution.twoSum` (trace mode is enabled by
the local server). Response includes `result`, `trace` (RFC v1 full
post-line snapshots) and `commands` (existing `{key,method,args}` format).

For CLI usage, add `"trace": {"enabled": true, "maxEvents": 250}`
to a Two Sum request. Example:
```powershell
Get-Content -Raw python_runner/examples/two_sum_animation_request.json | python python_runner/run.py
```

### Validation

```powershell
python -m unittest discover -s python_runner/tests -v
```

The Python unit suite includes existing Two Sum and Add Two Numbers tests,
contract validation, adapter replay simulation, and trace limit cases.
A local HTTP smoke test verifies the 200 response, CORS and the 21 commands
for the standard Two Sum example. **An actual React browser smoke test and
a legacy npm build have not yet been run in this environment.**

### Limits and security

- **Not a sandbox:** only use trusted local code. Process isolation and
  timeout do not prevent all filesystem/network or process-tree abuse.
- The animation only covers the Two Sum family with supported list/dict
  snapshots, maximum 256 array values and maximum 250 events by default.
- No dependency upgrades; `package.json` and `package-lock.json`
  are unchanged. Other language pathways remain as before.
