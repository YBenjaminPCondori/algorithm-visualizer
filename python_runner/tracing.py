"""Deterministic post-line snapshots for the Two Sum animation MVP.

The trace has the v1 RFC envelope. The recorder only observes the selected
Solution.twoSum call. It never rewrites or alters the submitted source.
"""
import hashlib
import math
import sys
import uuid


class TraceLimit(Exception):
    pass


class UnsupportedTraceValue(Exception):
    pass


class TraceRecorder:
    def __init__(self, target_code, max_events=250):
        self.target_code = target_code
        self.max_events = max_events
        self.events = []
        self.pending_line = None
        self.object_ids = {}
        self.retained = []
        self.previous = None
        self.active = False

    def encode(self, value, heap):
        if value is None or type(value) in (bool, str, int):
            return value
        if type(value) is float:
            if not math.isfinite(value):
                raise UnsupportedTraceValue('Non-finite float cannot be traced')
            return value
        if type(value) not in (list, dict):
            raise UnsupportedTraceValue('Unsupported runtime value: ' + type(value).__name__)
        ident = id(value)
        if ident not in self.object_ids:
            token = 'obj-' + str(len(self.object_ids) + 1)
            self.object_ids[ident] = token
            self.retained.append(value)  # prevents id reuse
        token = self.object_ids[ident]
        if token not in heap:
            if len(value) > 256:
                raise UnsupportedTraceValue('Container too large for tracing')
            # Insert placeholder before recursion so aliases/cycles cannot recurse forever.
            heap[token] = {'kind': 'list', 'items': []} if type(value) is list else {'kind': 'dict', 'entries': []}
            if type(value) is list:
                heap[token]['items'] = [self.encode(v, heap) for v in value]
            else:
                heap[token]['entries'] = [[self.encode(k, heap), self.encode(v, heap)] for k, v in value.items()]
        return {'$ref': token}

    def snapshot(self, frame):
        heap = {}
        locals_ = {}
        for name, value in sorted(frame.f_locals.items()):
            if name == 'self':
                continue
            try:
                locals_[name] = self.encode(value, heap)
            except UnsupportedTraceValue:
                # e.g. an enumerate iterator: do not fabricate its state.
                continue
        return {'frames': [{'frameId': 'solution', 'function': 'Solution.twoSum', 'locals': locals_}], 'heap': heap}

    def infer_kind(self, state):
        if self.previous:
            old_heap = self.previous['heap']
            for token, obj in state['heap'].items():
                if obj['kind'] != 'dict' or token not in old_heap:
                    continue
                before = old_heap[token]['entries']
                after = obj['entries']
                if len(after) == len(before) + 1 and after[:len(before)] == before:
                    key, val = after[-1]
                    return ('container_write', {'objectId': token, 'key': key, 'value': val})
            old = self.previous['frames'][0]['locals']
            current = state['frames'][0]['locals']
            if 'index' in current and current.get('index') != old.get('index'):
                return ('iteration', {})
        return ('assign', {})

    def push(self, line, frame, is_return=False, return_value=None):
        if len(self.events) >= self.max_events:
            raise TraceLimit('Execution exceeded maximum trace events')
        state = self.snapshot(frame)
        kind, details = self.infer_kind(state)
        if is_return:
            kind = 'return'
            try:
                details = {'value': self.encode(return_value, state['heap'])}
            except UnsupportedTraceValue:
                raise UnsupportedTraceValue('Unsupported return value')
        self.events.append({
            'seq': len(self.events), 'sourceLine': line,
            'phase': 'after', 'kind': kind, 'details': details, 'state': state
        })
        self.previous = state

    def trace(self, frame, event, arg):
        if event == 'call':
            if frame.f_code is self.target_code:
                self.active = True
                self.pending_line = None
                return self.trace
            return None
        if not self.active or frame.f_code is not self.target_code:
            return None
        if event == 'line':
            if self.pending_line is not None:
                self.push(self.pending_line, frame)
            self.pending_line = frame.f_lineno
        elif event == 'return':
            if self.pending_line is not None:
                self.push(self.pending_line, frame, is_return=True, return_value=arg)
            self.pending_line = None
            self.active = False
        return self.trace

    def envelope(self, request, status='completed', error=None):
        source = request['source']['text']
        return {
            'schemaVersion': '1.0.0',
            'runId': uuid.uuid4().hex,
            'language': 'python',
            'source': {'filename': 'solution.py', 'text': source,
                       'sha256': hashlib.sha256(source.encode('utf-8')).hexdigest(), 'lineBase': 1},
            'invocation': request['invocation'], 'status': status,
            'events': self.events, 'error': error,
        }
