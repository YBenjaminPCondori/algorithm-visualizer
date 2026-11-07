import json
import pathlib
import subprocess
import sys
import unittest

BASE = pathlib.Path(__file__).resolve().parents[1]
SOLUTION = json.loads((BASE / 'examples' / 'two_sum_request.json').read_text())


def run_traced(code=None, inputs=None, max_events=250):
    req = json.loads(json.dumps(SOLUTION))
    if code is not None:
        req['source']['text'] = code
    if inputs is not None:
        req['invocation']['args'] = inputs
    req['trace'] = {'enabled': True, 'maxEvents': max_events}
    proc = subprocess.run([sys.executable, str(BASE / 'run.py')], input=json.dumps(req),
                          capture_output=True, text=True, timeout=12)
    return proc.returncode, json.loads(proc.stdout)


def replay(commands):
    # Independent, deliberately minimal model of existing command interpreter.
    objects = {}
    initial = 0
    chunks = [[]]
    line_numbers = []
    for command in commands:
        key, name, args = command['key'], command['method'], command['args']
        if key is None and name == 'delay':
            line_numbers.append(args[0])
            chunks.append([])
        else:
            chunks[-1].append(command)
    if not chunks[-1]:
        raise AssertionError('trailing empty chunk')
    assert len(chunks) == len(line_numbers) + 1
    for chunk in chunks:
        for command in chunk:
            key, name, args = command['key'], command['method'], command['args']
            if name.endswith('Tracer') or name.endswith('Layout'):
                objects[key] = {'class': name, 'value': None, 'selected': set()}
            elif name == 'setRoot':
                assert args[0] in objects
            elif name == 'set':
                objects[key]['value'] = args[0]
            elif name == 'select':
                objects[key]['selected'].add(args[0])
            elif name == 'deselect':
                objects[key]['selected'].discard(args[0])
            else:
                raise AssertionError('unexpected method: ' + name)
    return objects


class AnimationTests(unittest.TestCase):
    def test_trace_and_commands(self):
        code, resp = run_traced()
        self.assertEqual(code, 0, resp)
        self.assertEqual(resp['result'], [0, 1])
        trace = resp['trace']
        self.assertEqual(trace['schemaVersion'], '1.0.0')
        events = trace['events']
        self.assertGreaterEqual(len(events), 5)
        self.assertEqual([e['seq'] for e in events], list(range(len(events))))
        self.assertTrue(all(e['phase'] == 'after' for e in events))
        self.assertEqual(events[-1]['kind'], 'return')
        self.assertTrue(any(e['kind'] == 'container_write' for e in events))
        self.assertTrue(any(e['state']['heap'] for e in events))
        self.assertTrue(any(e['sourceLine'] == 8 for e in events))
        self.assertEqual(len(resp['commands']), 21)
        objects = replay(resp['commands'])
        self.assertEqual(objects['nums']['value'], [2, 7, 11, 15])
        self.assertEqual(objects['seen']['value'], [[2, 0]])
        self.assertEqual(objects['nums']['selected'], {1})
        self.assertEqual(objects['answer']['value'], [0, 1])

    def test_alternative_variable_names(self):
        source = '''class Solution:
    def twoSum(self, numbers, target):
        seen = {}
        for i, number in enumerate(numbers):
            missing = target - number
            if missing in seen:
                return [seen[missing], i]
            seen[number] = i
        return []
'''
        code, resp = run_traced(code=source)
        self.assertEqual(code, 0, resp)
        self.assertEqual(resp['result'], [0, 1])
        objects = replay(resp['commands'])
        self.assertEqual(objects['seen']['value'], [[2, 0]])
        self.assertEqual(objects['nums']['selected'], {1})

    def test_no_solution(self):
        code, resp = run_traced(inputs=[[1, 2, 3], 25])
        self.assertEqual(code, 0, resp)
        self.assertEqual(resp['result'], [])
        self.assertEqual(replay(resp['commands'])['answer']['value'], [])

    def test_duplicate_elements(self):
        code, resp = run_traced(inputs=[[3, 3], 6])
        self.assertEqual(code, 0, resp)
        self.assertEqual(resp['result'], [0, 1])
        self.assertEqual(replay(resp['commands'])['seen']['value'], [[3, 0]])

    def test_event_budget(self):
        code, resp = run_traced(max_events=2)
        self.assertEqual(code, 2)
        self.assertEqual(resp['error']['code'], 'EVENT_LIMIT')
        self.assertNotIn('commands', resp)

    def test_trace_explicit_opt_in(self):
        req = json.loads(json.dumps(SOLUTION))
        proc = subprocess.run([sys.executable, str(BASE / 'run.py')], input=json.dumps(req),
                              capture_output=True, text=True, timeout=12)
        self.assertEqual(proc.returncode, 0)
        self.assertNotIn('commands', json.loads(proc.stdout))

    def test_linked_list_trace_is_not_supported(self):
        req = json.loads((BASE / 'examples' / 'add_two_numbers_request.json').read_text())
        req['trace'] = {'enabled': True}
        proc = subprocess.run([sys.executable, str(BASE / 'run.py')], input=json.dumps(req),
                              capture_output=True, text=True, timeout=12)
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(json.loads(proc.stdout)['error']['code'], 'INVALID_REQUEST')

    def test_nonfinite_trace_input(self):
        # The JSON protocol validates input type, but renderer allows only finite numeric values.
        code, resp = run_traced(inputs=[[2, -7, 11, 15], 4])
        self.assertEqual(code, 0, resp)
        self.assertTrue(len(resp['trace']['events']) > 0)

    def test_source_line_zero_based_adapter(self):
        _, resp = run_traced()
        delays = [c['args'][0] for c in resp['commands'] if c['method'] == 'delay']
        self.assertEqual(delays[0], resp['trace']['events'][0]['sourceLine'] - 1)


if __name__ == '__main__':
    unittest.main()
