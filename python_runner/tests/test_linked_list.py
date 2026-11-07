"""Add Two Numbers validation, conversion and regression tests."""
import json
import subprocess
import sys
import unittest
from pathlib import Path

RUNNER = Path(__file__).resolve().parents[1] / 'run.py'
SOLUTION = '''class Solution(object):
    def addTwoNumbers(self, l1, l2):
        head = ListNode(0)
        tail = head
        carry = 0
        while l1 is not None or l2 is not None or carry != 0:
            l1_d1 = l1.val if l1 is not None else 0
            l2_d2 = l2.val if l2 is not None else 0
            total = l1_d1 + l2_d2 + carry
            d = total % 10
            carry = total // 10
            tail.next = ListNode(d)
            tail = tail.next
            l1 = l1.next if l1 is not None else None
            l2 = l2.next if l2 is not None else None
        return head.next
'''


def invoke(source=SOLUTION, args=None, method='addTwoNumbers'):
    if args is None:
        args = [[2, 4, 3], [5, 6, 4]]
    request = {
        'contractVersion': '1.0.0',
        'source': {'filename': 'solution.py', 'text': source},
        'invocation': {'className': 'Solution', 'method': method, 'args': args},
        'limits': {'wallTimeMs': 2000},
    }
    proc = subprocess.run([sys.executable, str(RUNNER)], input=json.dumps(request),
                          text=True, capture_output=True, timeout=10)
    return proc.returncode, json.loads(proc.stdout), proc.stderr


class AddTwoNumbersTests(unittest.TestCase):
    def assert_result(self, expected, args=None, source=SOLUTION):
        code, response, stderr = invoke(source=source, args=args)
        self.assertEqual(code, 0, (response, stderr))
        self.assertEqual(response['status'], 'completed')
        self.assertEqual(response['result'], expected)
        self.assertIsNone(response['error'])

    def test_rfc_example(self):
        self.assert_result([7, 0, 8])

    def test_long_carry(self):
        self.assert_result([8, 9, 9, 9, 0, 0, 0, 1],
                           [[9, 9, 9, 9, 9, 9, 9], [9, 9, 9, 9]])

    def test_output_carry_new_node(self):
        self.assert_result([0, 0, 1], [[9, 9], [1]])

    def test_unequal_lengths(self):
        self.assert_result([9, 9, 9], [[7], [2, 9, 9]])

    def test_zero(self):
        self.assert_result([0], [[0], [0]])

    def test_empty_lists(self):
        self.assert_result([], [[], []])

    def test_second_empty(self):
        self.assert_result([4, 3], [[4, 3], []])

    def test_typed_leetcode_solution(self):
        source = 'from typing import Optional\nclass Solution:\n    def addTwoNumbers(self, l1: Optional[ListNode], l2: Optional[ListNode]) -> Optional[ListNode]:\n' + '\n'.join('        ' + line for line in SOLUTION.splitlines()[2:]) + '\n'
        self.assert_result([7, 0, 8], source=source)

    def test_explicit_listnode_class(self):
        source = '''class ListNode:
    def __init__(self, val=0, next=None):
        self.val = val
        self.next = next
''' + SOLUTION
        self.assert_result([7, 0, 8], source=source)

    def test_reject_string_digit(self):
        code, response, _ = invoke(args=[[2, '4', 3], [5, 6, 4]])
        self.assertEqual(code, 1)
        self.assertEqual(response['error']['code'], 'UNSUPPORTED_VALUE')

    def test_reject_bool_digit(self):
        _, response, _ = invoke(args=[[True], [5]])
        self.assertEqual(response['error']['code'], 'UNSUPPORTED_VALUE')

    def test_reject_digit_outside_range(self):
        _, response, _ = invoke(args=[[10], [3]])
        self.assertEqual(response['error']['code'], 'UNSUPPORTED_VALUE')

    def test_reject_oversized_input(self):
        _, response, _ = invoke(args=[[0] * 1001, [1]])
        self.assertEqual(response['error']['code'], 'UNSUPPORTED_VALUE')

    def test_reject_wrong_argument_count(self):
        _, response, _ = invoke(args=[[1]])
        self.assertEqual(response['error']['code'], 'INVALID_REQUEST')

    def test_return_wrong_type(self):
        src = 'class Solution:\n    def addTwoNumbers(self, l1, l2):\n        return [7, 0, 8]\n'
        _, response, _ = invoke(source=src)
        self.assertEqual(response['error']['code'], 'UNSUPPORTED_VALUE')

    def test_return_cycle(self):
        src = 'class Solution:\n    def addTwoNumbers(self, l1, l2):\n        head = ListNode(7)\n        head.next = head\n        return head\n'
        _, response, _ = invoke(source=src)
        self.assertEqual(response['error']['code'], 'UNSUPPORTED_VALUE')
        self.assertIn('cycle', response['error']['message'])

    def test_return_invalid_digit(self):
        src = 'class Solution:\n    def addTwoNumbers(self, l1, l2):\n        return ListNode(17)\n'
        _, response, _ = invoke(source=src)
        self.assertEqual(response['error']['code'], 'UNSUPPORTED_VALUE')

    def test_return_invalid_next(self):
        src = 'class Solution:\n    def addTwoNumbers(self, l1, l2):\n        head = ListNode(3)\n        head.next = 5\n        return head\n'
        _, response, _ = invoke(source=src)
        self.assertEqual(response['error']['code'], 'UNSUPPORTED_VALUE')

    def test_missing_add_two_numbers_method(self):
        src = 'class Solution:\n    def twoSum(self, nums, target):\n        return []\n'
        _, response, _ = invoke(source=src)
        self.assertEqual(response['error']['code'], 'UNSUPPORTED_SIGNATURE')

    def test_runtime_error_line_number(self):
        src = 'class Solution:\n    def addTwoNumbers(self, l1, l2):\n        raise ValueError("bad")\n'
        _, response, _ = invoke(source=src)
        self.assertEqual(response['error']['code'], 'RUNTIME_EXCEPTION')
        self.assertEqual(response['error']['sourceLine'], 3)


if __name__ == '__main__':
    unittest.main()
