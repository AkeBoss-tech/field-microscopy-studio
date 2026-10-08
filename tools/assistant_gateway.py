"""Optional loopback gateway for the static studio's image-aware assistant.

Explicit origins and a separate gateway token protect server-held provider credentials.
The gateway handles assistance only; it never opens images or writes a workspace.
"""
import argparse
import hmac
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from assistant import chat, configuration


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # Requests contain private questions; avoid access logs.

    def allowed(self):
        origin = self.headers.get('Origin')
        return origin and origin in self.server.origins

    def send(self, value, status=200):
        raw = json.dumps(value).encode()
        self.send_response(status)
        if self.allowed():
            self.send_header('Access-Control-Allow-Origin', self.headers['Origin'])
            self.send_header('Vary', 'Origin')
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(raw)

    def authorized(self):
        host = self.headers.get('Host', '')
        expected = {'localhost:'+str(self.server.server_port), '127.0.0.1:'+str(self.server.server_port)}
        token = self.headers.get('Authorization', '')
        return host in expected and self.allowed() and hmac.compare_digest(token.encode('utf-8'), ('Bearer '+self.server.token).encode('utf-8'))

    def do_OPTIONS(self):
        if not self.allowed():
            return self.send({'error': 'Origin not allowed'}, 403)
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', self.headers['Origin'])
        self.send_header('Access-Control-Allow-Headers', 'Authorization, Content-Type, X-Studio-Request')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Vary', 'Origin')
        self.end_headers()

    def do_GET(self):
        if not self.authorized():
            return self.send({'error': 'Check the gateway origin and access token'}, 403)
        if self.path != '/api/assistant/config':
            return self.send({'error': 'Not found'}, 404)
        self.send(configuration())

    def do_POST(self):
        if not self.authorized() or self.headers.get('X-Studio-Request') != '1':
            return self.send({'error': 'Check the gateway origin and access token'}, 403)
        if self.path != '/api/assistant/chat':
            return self.send({'error': 'Not found'}, 404)
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 7000000:
                raise ValueError('Assistant request exceeds size limit')
            body = json.loads(self.rfile.read(size))
            self.send(chat(body))
        except Exception as error:
            self.send({'error': str(error) if isinstance(error, ValueError) else 'Assistant request failed'}, 400)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8788)
    parser.add_argument('--origin', action='append', required=True, help='Exact trusted studio origin; repeat for multiple origins')
    args = parser.parse_args()
    token = os.environ.get('FIELD_ASSISTANT_TOKEN', '')
    if len(token) < 24:
        parser.error('Set FIELD_ASSISTANT_TOKEN to a separate random token of at least 24 characters')
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    server.token = token
    server.origins = set(args.origin)
    print('Assistant gateway listening at http://127.0.0.1:'+str(args.port), flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
