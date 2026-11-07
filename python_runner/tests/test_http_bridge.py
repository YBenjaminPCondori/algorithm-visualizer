"""Localhost HTTP contract smoke tests for the Python/React bridge.

Uses the stdlib HTTP server on an ephemeral localhost port; no browser/npm needed.
"""
import json
import pathlib
import sys
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from server import Handler


class HttpBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = 'http://127.0.0.1:%d' % cls.server.server_port
        cls.input = json.loads((ROOT / 'examples' / 'two_sum_request.json').read_text())
        cls.input['limits'] = {'wallTimeMs': 8000}

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join(timeout=5)
        cls.server.server_close()

    def request(self, path, body=None, method='GET', origin=None):
        headers = {}
        if body is not None:
            headers['Content-Type'] = 'application/json'
            data = json.dumps(body).encode('utf-8')
        else:
            data = None
        if origin is not None:
            headers['Origin'] = origin
        if method == 'OPTIONS':
            headers['Access-Control-Request-Method'] = 'POST'
            headers['Access-Control-Request-Headers'] = 'Content-Type'
        req = Request(self.base + path, data=data, method=method, headers=headers)
        try:
            response = urlopen(req, timeout=8)
        except HTTPError as exc:
            response = exc
        with response:
            raw = response.read()
            content = json.loads(raw) if raw else None
            return response.status, response.headers, content

    def test_health(self):
        code, _, resp = self.request('/health')
        self.assertEqual(code, 200)
        self.assertEqual(resp['status'], 'ok')

    def test_post_two_sum_has_playback_contract(self):
        code, headers, resp = self.request('/api/tracers/py', self.input, method='POST', origin='http://localhost:3000')
        self.assertEqual(code, 200)
        self.assertEqual(headers['Access-Control-Allow-Origin'], 'http://localhost:3000')
        self.assertEqual(resp['status'], 'completed')
        self.assertEqual(resp['result'], [0, 1])
        self.assertEqual(resp['trace']['status'], 'completed')
        self.assertEqual(len(resp['commands']), 22)
        self.assertEqual(resp['commands'][0]['method'], 'Array1DTracer')
        self.assertEqual(resp['commands'][-1]['method'], 'delay')
        self.assertEqual(resp['commands'][-1]['args'], [6])

    def test_cors_preflight_allowed(self):
        code, headers, resp = self.request('/api/tracers/py', method='OPTIONS', origin='http://127.0.0.1:3000')
        self.assertEqual(code, 204)
        self.assertEqual(headers['Access-Control-Allow-Origin'], 'http://127.0.0.1:3000')
        self.assertIsNone(resp)

    def test_cors_rejects_foreign_origin(self):
        code, _, resp = self.request('/api/tracers/py', self.input, method='POST', origin='https://example.com')
        self.assertEqual(code, 403)
        self.assertEqual(resp['error'], 'Origin not allowed')

    def test_rejects_wrong_problem(self):
        request = json.loads(json.dumps(self.input))
        request['invocation']['method'] = 'addTwoNumbers'
        code, _, resp = self.request('/api/tracers/py', request, method='POST')
        self.assertEqual(code, 400)
        self.assertEqual(resp['error']['code'], 'INVALID_REQUEST')

    def test_rejects_invalid_inputs(self):
        request = json.loads(json.dumps(self.input))
        request['invocation']['args'] = ['not-an-array', 9]
        code, _, resp = self.request('/api/tracers/py', request, method='POST')
        self.assertEqual(code, 422)
        self.assertEqual(resp['error']['code'], 'UNSUPPORTED_VALUE')

    def test_rejects_unknown_route(self):
        code, _, resp = self.request('/invalid')
        self.assertEqual(code, 404)


if __name__ == '__main__':
    unittest.main()
