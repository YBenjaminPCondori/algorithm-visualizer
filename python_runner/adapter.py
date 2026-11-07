"""Allowlisted adapter from observed Two Sum post-line snapshots to legacy commands.

No user-supplied method or constructor names are ever forwarded to the viewer.
"""


def cmd(key, method, *args):
    return {'key': key, 'method': method, 'args': list(args)}


def referenced_object(state, local_value):
    if type(local_value) is not dict or set(local_value) != {'$ref'}:
        return None
    return state['heap'].get(local_value['$ref'])


def arrays_and_dicts(state):
    locals_ = state['frames'][0]['locals']
    arrays, dictionaries = [], []
    for name, encoded in locals_.items():
        obj = referenced_object(state, encoded)
        if not obj:
            continue
        if obj['kind'] == 'list':
            arrays.append((name, obj['items']))
        elif obj['kind'] == 'dict':
            dictionaries.append((name, obj['entries']))
    return arrays, dictionaries, locals_


def choose_index(locals_, length):
    for name in ('index', 'i', 'idx', 'pos', 'j'):
        v = locals_.get(name)
        if type(v) is int and 0 <= v < length:
            return v
    return None


def display_value(value):
    """Only pass React-renderable scalar values to the legacy table renderer."""
    if value is None or type(value) in (bool, int, float, str):
        return value
    if isinstance(value, dict) and set(value) == {'$ref'}:
        return '<' + str(value['$ref']) + '>'
    raise ValueError('unsupported visualisation value')


def adapt_two_sum(trace, result):
    if trace.get('schemaVersion') != '1.0.0' or trace.get('status') != 'completed':
        raise ValueError('unsupported trace version/status')
    events = trace.get('events', [])
    if not isinstance(events, list) or not events:
        raise ValueError('trace contains no events')
    if not (isinstance(result, list) and len(result) in (0, 2)):
        raise ValueError('unsupported Two Sum return value')
    nums = trace['invocation']['args'][0]
    if not isinstance(nums, list) or len(nums) > 256:
        raise ValueError('array is too large')
    out = [
        cmd('nums', 'Array1DTracer', 'input array'),
        cmd('nums', 'set', nums),
        cmd('seen', 'Array2DTracer', 'hash map: [key, index]'),
        cmd('seen', 'set', []),
        cmd('answer', 'Array1DTracer', 'result indices'),
        cmd('answer', 'set', []),
        cmd('root', 'VerticalLayout', ['nums', 'seen', 'answer']),
        cmd(None, 'setRoot', 'root'),
    ]
    prior_dict = []
    prior_array = list(nums)
    selected = None
    for step, event in enumerate(events):
        if event['seq'] != step or event['phase'] != 'after':
            raise ValueError('invalid event ordering')
        state = event['state']
        arrays, dicts, locals_ = arrays_and_dicts(state)
        # Prefer the argument's value, but allow its variable to be renamed.
        for name, arr in arrays:
            if name in ('nums', 'numbers', 'arr', 'array') or arr == prior_array:
                if arr != prior_array:
                    out.append(cmd('nums', 'set', arr))
                    prior_array = list(arr)
                break
        # Two Sum MVP visualises the first dictionary in the Solution frame.
        if dicts:
            table = dicts[0][1]
            if table != prior_dict:
                out.append(cmd('seen', 'set', [[display_value(v) for v in pair] for pair in table]))
                prior_dict = [list(pair) for pair in table]
        current_index = choose_index(locals_, len(nums))
        if current_index != selected:
            if selected is not None:
                out.append(cmd('nums', 'deselect', selected))
            if current_index is not None:
                out.append(cmd('nums', 'select', current_index))
            selected = current_index
        if event['kind'] == 'return':
            out.append(cmd('answer', 'set', result))
        source_line = event['sourceLine']
        if type(source_line) is not int or source_line < 1:
            raise ValueError('invalid line number')
        out.append(cmd(None, 'delay', source_line - 1))
    if events[-1]['kind'] != 'return':
        raise ValueError('missing return event')
    if len(out) > 1500:
        raise ValueError('command limit exceeded')
    return out
