"""Run from project root: python -m unittest discover -s python_runner/tests -v."""
import json
import subprocess
import sys
import unittest
from pathlib import Path

RUNNER = Path(__file__).resolve().parents[1] / "run.py"

CODE = '''class Solution(object):
    def twoSum(self, nums, target_value):
        seen = {}
        for index, num in enumerate(nums):
            complement = target_value - num
            if complement in seen:
                return [seen[complement], index]
            seen[num] = index
        return []
'''


def invoke(source=CODE, args=None, method="twoSum", class_name="Solution", timeout=2000):
    if args is None:
        args = [[2, 7, 11, 15], 9]
    request = {
        "contractVersion": "1.0.0",
        "source": {"filename": "solution.py", "text": source},
        "invocation": {"className": class_name, "method": method, "args": args},
        "limits": {"wallTimeMs": timeout},
    }
    proc = subprocess.run([sys.executable, str(RUNNER)], input=json.dumps(request), text=True,
                          capture_output=True, timeout=15)
    return proc.returncode, json.loads(proc.stdout), proc.stderr


class RunnerTests(unittest.TestCase):
    def test_two_sum(self):
        code, response, _ = invoke()
        self.assertEqual(code, 0)
        self.assertEqual(response["status"], "completed")
        self.assertEqual(response["result"], [0, 1])
        self.assertEqual(len(response["sourceSha256"]), 64)

    def test_duplicate_values(self):
        _, response, _ = invoke(args=[[3, 3], 6])
        self.assertEqual(response["result"], [0, 1])

    def test_negative_values(self):
        _, response, _ = invoke(args=[[-3, 4, 3, 90], 0])
        self.assertEqual(response["result"], [0, 2])

    def test_no_match(self):
        _, response, _ = invoke(args=[[1, 2], 9])
        self.assertEqual(response["result"], [])

    def test_missing_solution(self):
        code, response, _ = invoke("class Other:\n    pass\n")
        self.assertEqual(code, 1)
        self.assertEqual(response["error"]["code"], "UNSUPPORTED_SIGNATURE")

    def test_missing_method(self):
        code, response, _ = invoke("class Solution:\n    pass\n")
        self.assertEqual(code, 1)
        self.assertEqual(response["error"]["code"], "UNSUPPORTED_SIGNATURE")

    def test_bad_signature(self):
        _, response, _ = invoke("class Solution:\n    def twoSum(self, nums):\n        return []\n")
        self.assertEqual(response["error"]["code"], "UNSUPPORTED_SIGNATURE")

    def test_runtime_exception_with_source_line(self):
        _, response, _ = invoke("class Solution:\n    def twoSum(self, nums, target):\n        raise ValueError('bad')\n")
        self.assertEqual(response["error"]["code"], "RUNTIME_EXCEPTION")
        self.assertEqual(response["error"]["sourceLine"], 3)

    def test_timeout(self):
        source = "class Solution:\n    def twoSum(self, nums, target):\n        while True: pass\n"
        code, response, _ = invoke(source, timeout=700)
        self.assertEqual(code, 2)
        self.assertEqual(response["status"], "limited")
        self.assertEqual(response["error"]["code"], "EXECUTION_TIMEOUT")

    def test_bad_input(self):
        _, response, _ = invoke(args=[[1, "2"], 3])
        self.assertEqual(response["error"]["code"], "UNSUPPORTED_VALUE")

    def test_unchanged_rfc_source(self):
        src = """class Solution(object):
    def twoSum(self, nums, target_value):
        nums_hash_table = {}
        for index, num_value in enumerate(nums):
            complement = target_value - num_value
            if complement in nums_hash_table:
                return [nums_hash_table.get(complement), index]
            nums_hash_table[num_value] = index
        return []
"""
        code, response, _ = invoke(src)
        self.assertEqual(code, 0)
        self.assertEqual(response["result"], [0, 1])

    def test_import_restriction(self):
        _, response, _ = invoke("import os\n" + CODE)
        self.assertEqual(response["error"]["code"], "UNSUPPORTED_SIGNATURE")

    def test_typing_annotations(self):
        src = "from typing import List\nclass Solution:\n    def twoSum(self, nums: List[int], target: int) -> List[int]:\n        return [0, 1]\n"
        code, response, _ = invoke(src)
        self.assertEqual(code, 0)
        self.assertEqual(response["result"], [0, 1])

    def test_syntax_error(self):
        _, response, _ = invoke("class Solution(:\n    pass\n")
        self.assertEqual(response["error"]["code"], "INVALID_REQUEST")
        self.assertEqual(response["error"]["sourceLine"], 1)

    def test_invalid_json_protocol(self):
        proc = subprocess.run([sys.executable, str(RUNNER)], input="not-json", text=True,
                              capture_output=True, timeout=10)
        payload = json.loads(proc.stdout)
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(payload["error"]["code"], "INVALID_REQUEST")


if __name__ == "__main__":
    unittest.main()
