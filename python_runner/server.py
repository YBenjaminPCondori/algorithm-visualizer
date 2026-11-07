"""Local-only HTTP bridge for the React UI. stdlib, no npm changes.

Run: python python_runner/server.py
Only bind to 127.0.0.1. Not a sandbox; only run locally trusted source.
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(__file__))
from run import MAX_REQUEST_BYTES, execute_request, failure

ALLOWED_ORIGINS = {'http://localhost:3000', 'http://127.0.0.1:3000'}


class Handler(BaseHTTPRequestHandler):
    def cors_origin(self):
        origin = self.headers.get('Origin', '')
        return origin if origin in ALLOWED_ORIGINS else None

    def reply(self, status, payload):
        encoded = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(encoded)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        origin = self.cors_origin()
        if origin:
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Vary', 'Origin')
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        if self.path == '/health':
            self.reply(200, {'status': 'ok', 'service': 'python-runner', 'contractVersion': '1.0.0'})
        else:
            self.reply(404, {'error': 'Not found'})

    def do_OPTIONS(self):
        if self.path != '/api/tracers/py' or not self.cors_origin():
            self.reply(403, {'error': 'Origin not allowed'})
            return
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', self.cors_origin())
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Access-Control-Max-Age', '300')
        self.send_header('Content-Length', '0')
        self.end_headers()

    def do_POST(self):
        if self.path != '/api/tracers/py':
            self.reply(404, {'error': 'Not found'})
            return
        origin = self.headers.get('Origin')
        if origin and not self.cors_origin():
            self.reply(403, {'error': 'Origin not allowed'})
            return
        try:
            length = int(self.headers.get('Content-Length', '-1'))
        except ValueError:
            length = -1
        if not 0 <= length <= MAX_REQUEST_BYTES:
            self.reply(413, failure('INVALID_REQUEST', 'Invalid Content-Length or request too large'))
            return
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw.decode('utf-8'))
        except (ValueError, UnicodeDecodeError):
            self.reply(400, failure('INVALID_REQUEST', 'Request must be JSON'))
            return
        # This route is specifically for the Two Sum animation MVP.
        invocation = body.get('invocation') if isinstance(body, dict) else None
        if not isinstance(invocation, dict) or invocation.get('method') != 'twoSum':
            self.reply(400, failure('INVALID_REQUEST', 'Only Two Sum visualisation is supported'))
            return
        body['trace'] = {'enabled': True, 'maxEvents': 250}
        response = execute_request(body)
        if response['status'] == 'completed':
            code = 200
        elif response['status'] == 'limited':
            code = 422
        elif response['error'] and response['error']['phase'] == 'internal':
            code = 500
        else:
            code = 422
        self.reply(code, response)


def serve(host='127.0.0.1', port=8765):
    print('Local Two Sum tracer available at http://%s:%d/health' % (host, port), flush=True)
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == '__main__':
    serve()
