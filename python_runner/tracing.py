"""Deterministic post-line snapshots for the Two Sum animation MVP.

The trace uses the v1 RFC envelope and observes only the selected
Solution.twoSum code object. Submitted source code is never rewritten.

The recorder tracks local variables and supported heap objects to produce
state snapshots for the existing algorithm-animation adapter.
"""

import hashlib
import math
import sys
import uuid


class TraceLimit(Exception):
    """Raised when recording would exceed the configured event limit."""

    pass


class UnsupportedTraceValue(Exception):
    """Raised when a value cannot be represented in the trace schema."""

    pass


class TraceRecorder:
    """Observe a selected Python function and record post-line state.

    The public attributes are retained because other runner components may
    depend on their names. A snapshot represents observable Python state,
    not a reconstruction of every operation within a source line.
    """

    def __init__(self, target_code, max_events=250):
        """Initialise tracing configuration and per-execution state.

        Args:
            target_code: Exact Python code object to observe.
            max_events: Maximum number of events to record.
        """
        # PURPOSE: Identify the function to trace without altering its code.
        self.target_code = target_code

        # SAFETY: Bound the number of events retained during execution.
        self.max_events = max_events

        # STATE CHANGES: Events and line state accumulate as tracing runs.
        self.events = []
        self.pending_line = None

        # DATA FLOW: Stable tokens link frame variables to heap containers.
        self.object_ids = {}
        self.retained = []

        # STATE CHANGES: Save the preceding snapshot for event inference.
        self.previous = None
        self.active = False

    def encode(self, value, heap):
        """Encode a runtime value using the trace's supported JSON types.

        Primitive values are emitted directly. Exact lists and dictionaries
        are stored in the supplied heap and represented by object references.
        The caller shares one heap while recursively encoding a snapshot.

        Args:
            value: Runtime value to represent in the trace.
            heap: Mutable heap snapshot receiving encoded containers.

        Returns:
            A primitive value or a dictionary containing a '$ref' token.

        Raises:
            UnsupportedTraceValue: If the value has an unsupported type,
                a non-finite float, or an oversized container.
        """
        # CONDITION: Primitive JSON-compatible values need no heap entry.
        if value is None or type(value) in (bool, str, int):
            return value

        # CONDITION: Only finite floats are valid in standard JSON.
        if type(value) is float:
            if not math.isfinite(value):
                raise UnsupportedTraceValue('Non-finite float cannot be traced')
            return value

        # LIMITATION: Other runtime types, including iterators, are not
        # serialised; only exact built-in lists and dictionaries are handled.
        if type(value) not in (list, dict):
            raise UnsupportedTraceValue(
                'Unsupported runtime value: ' + type(value).__name__
            )

        # PURPOSE: Detect aliases using Python object identity, not equality.
        python_object_identity = id(value)

        # CONDITION: Assign a stable reference the first time the object
        # appears anywhere in this recorder's execution.
        if python_object_identity not in self.object_ids:
            object_reference_token = 'obj-' + str(len(self.object_ids) + 1)
            self.object_ids[python_object_identity] = object_reference_token

            # SAFETY: Hold a strong reference so Python cannot reuse its id.
            self.retained.append(value)

        object_reference_token = self.object_ids[python_object_identity]

        # CONDITION: Encode each object only once per snapshot, even when
        # multiple variables refer to it or it contains a reference to itself.
        if object_reference_token not in heap:
            if len(value) > 256:
                # SAFETY: Avoid unbounded container snapshot sizes.
                raise UnsupportedTraceValue('Container too large for tracing')

            # REASON: Insert a placeholder before recursion so aliases and
            # cycles cannot cause infinite recursive encoding.
            heap[object_reference_token] = (
                {'kind': 'list', 'items': []}
                if type(value) is list
                else {'kind': 'dict', 'entries': []}
            )

            if type(value) is list:
                # DATA FLOW: Store encoded elements under this list's token.
                heap[object_reference_token]['items'] = [
                    self.encode(element_value, heap)
                    for element_value in value
                ]
            else:
                # DATA FLOW: Preserve dictionary iteration order and encode
                # each key/value pair using the same shared heap.
                heap[object_reference_token]['entries'] = [
                    [
                        self.encode(dictionary_key, heap),
                        self.encode(dictionary_value, heap)
                    ]
                    for dictionary_key, dictionary_value in value.items()
                ]

        # FUNCTIONALITY: Local variables point to containers via references.
        return {'$ref': object_reference_token}

    def snapshot(self, frame):
        """Capture supported local variables and their referenced objects.

        Args:
            frame: Interpreter frame of the function being observed.

        Returns:
            A trace state containing one solution frame and its heap.
            Unsupported local values are omitted rather than fabricated.
        """
        heap_snapshot = {}
        local_variables = {}

        # PURPOSE: Sorting by variable name makes snapshot order repeatable.
        for variable_name, variable_value in sorted(frame.f_locals.items()):
            # CONDITION: Do not expose the method's instance reference.
            if variable_name == 'self':
                continue

            try:
                # DATA FLOW: Encoding a local may populate the shared heap.
                local_variables[variable_name] = self.encode(
                    variable_value, heap_snapshot
                )
            except UnsupportedTraceValue:
                # LIMITATION: Objects such as enumerate iterators have no
                # supported representation; never invent their contents.
                continue

        # COMPATIBILITY: Preserve the exact frame and heap schema keys.
        return {
            'frames': [
                {
                    'frameId': 'solution',
                    'function': 'Solution.twoSum',
                    'locals': local_variables
                }
            ],
            'heap': heap_snapshot
        }

    def infer_kind(self, state):
        """Classify a state transition using the previous snapshot.

        Args:
            state: Current post-line state snapshot.

        Returns:
            (event_kind, event_details): A dictionary append, change to a
            local named 'index', or a default assignment event.

        Limitations:
            Only a new trailing dictionary entry is recognised as a
            container write. Existing-key updates and other mutations fall
            back to 'assign'. Iterations are inferred only for 'index'.
        """
        # CONDITION: No comparison is possible before the first snapshot.
        if self.previous:
            previous_heap_snapshot = self.previous['heap']

            # FUNCTIONALITY: Look for one newly appended dictionary entry.
            for object_reference_token, current_heap_object in (
                state['heap'].items()
            ):
                # CONDITION: Only compare dictionaries present in both heaps.
                if (
                    current_heap_object['kind'] != 'dict'
                    or object_reference_token not in previous_heap_snapshot
                ):
                    continue

                previous_dictionary_entries = previous_heap_snapshot[
                    object_reference_token
                ]['entries']
                current_dictionary_entries = current_heap_object['entries']

                # CONDITION: One new final entry, with the earlier entries
                # unchanged, matches the supported container-write pattern.
                if (
                    len(current_dictionary_entries)
                    == len(previous_dictionary_entries) + 1
                    and current_dictionary_entries[
                        :len(previous_dictionary_entries)
                    ] == previous_dictionary_entries
                ):
                    new_dictionary_key, new_dictionary_value = (
                        current_dictionary_entries[-1]
                    )
                    return (
                        'container_write',
                        {
                            'objectId': object_reference_token,
                            'key': new_dictionary_key,
                            'value': new_dictionary_value
                        }
                    )

            previous_local_variables = self.previous['frames'][0]['locals']
            current_local_variables = state['frames'][0]['locals']

            # CONDITION: The traced solution's local called 'index'
            # changed. This is a heuristic, not an interpreter loop event.
            if (
                'index' in current_local_variables
                and current_local_variables.get('index')
                != previous_local_variables.get('index')
            ):
                return ('iteration', {})

        # LIMITATION: Unrecognised state transitions are labelled 'assign'.
        return ('assign', {})

    def push(self, line, frame, is_return=False, return_value=None):
        """Record one post-line event and advance the previous snapshot.

        Args:
            line: Original source line associated with the event.
            frame: Current interpreter frame.
            is_return: Whether this event captures a function return.
            return_value: Return value supplied by the trace callback.

        Raises:
            TraceLimit: If recording another event exceeds max_events.
            UnsupportedTraceValue: If the return value cannot be encoded.
        """
        # SAFETY: Check the limit before taking another snapshot.
        if len(self.events) >= self.max_events:
            raise TraceLimit('Execution exceeded maximum trace events')

        current_state_snapshot = self.snapshot(frame)
        event_kind, event_details = self.infer_kind(current_state_snapshot)

        if is_return:
            # CONDITION: A return event overrides inferred assignment kind.
            event_kind = 'return'
            try:
                event_details = {
                    'value': self.encode(
                        return_value, current_state_snapshot['heap']
                    )
                }
            except UnsupportedTraceValue:
                raise UnsupportedTraceValue('Unsupported return value')

        # COMPATIBILITY: Preserve field names, event ordering and phase.
        self.events.append({
            'seq': len(self.events),
            'sourceLine': line,
            'phase': 'after',
            'kind': event_kind,
            'details': event_details,
            'state': current_state_snapshot
        })

        # STATE CHANGES: The next event compares against this snapshot.
        self.previous = current_state_snapshot

    def trace(self, frame, event, arg):
        """Handle interpreter callbacks for the selected function.

        Args:
            frame: Frame generating the interpreter event.
            event: Python trace event name ('call', 'line', 'return', etc.).
            arg: Event-specific data; for 'return', the returned value.

        Returns:
            This callback while observing the target frame, or None for
            calls and frames that must not be traced.

        Raises:
            TraceLimit: Propagated when the event budget is exhausted.
            UnsupportedTraceValue: Propagated for unsupported return data.
        """
        # CONDITION: Trace only calls with the exact target code object.
        if event == 'call':
            if frame.f_code is self.target_code:
                self.active = True
                self.pending_line = None
                return self.trace
            return None

        # CONDITION: Ignore unrelated frames and inactive tracing.
        if not self.active or frame.f_code is not self.target_code:
            return None

        if event == 'line':
            # FUNCTIONALITY: A line callback occurs before the next line.
            # The current locals therefore represent the preceding line's
            # post-execution state; defer recording the newest line.
            if self.pending_line is not None:
                self.push(self.pending_line, frame)
            self.pending_line = frame.f_lineno

        elif event == 'return':
            # CONDITION: Flush the final pending source line and its
            # return value because no later line callback will do so.
            if self.pending_line is not None:
                self.push(
                    self.pending_line,
                    frame,
                    is_return=True,
                    return_value=arg
                )
            self.pending_line = None
            self.active = False

        # STATE CHANGES: Continue receiving events for this target frame.
        return self.trace

    def envelope(self, request, status='completed', error=None):
        """Wrap recorded events in the existing v1 execution-trace format.

        Args:
            request: Original request with source.text and invocation data.
            status: Execution status to publish.
            error: Optional error payload; None for successful execution.

        Returns:
            JSON-compatible trace metadata and chronological events.
        """
        # DATA FLOW: Source text is included unchanged in trace metadata.
        source_code_text = request['source']['text']

        return {
            'schemaVersion': '1.0.0',
            'runId': uuid.uuid4().hex,
            'language': 'python',
            'source': {
                'filename': 'solution.py',
                'text': source_code_text,
                'sha256': hashlib.sha256(
                    source_code_text.encode('utf-8')
                ).hexdigest(),
                'lineBase': 1
            },
            'invocation': request['invocation'],
            'status': status,
            'events': self.events,
            'error': error
        }
