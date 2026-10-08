import importlib.util
import json
import os
from pathlib import Path
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from http.server import ThreadingHTTPServer

spec = importlib.util.spec_from_file_location('field_assistant_gateway', Path(__file__).resolve().parents[1] / 'tools' / 'assistant_gateway.py')
gateway = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gateway)


class GatewayChecks(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), gateway.Handler)
        self.server.origins = {'http://127.0.0.1:8777'}
        self.server.token = 'local-test-token-with-at-least-24-characters'
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = 'http://127.0.0.1:'+str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, path='/api/assistant/config', token=None, origin=None, method='GET', body=None):
        headers = {'Origin': origin or 'http://127.0.0.1:8777',
                   'Authorization': token or 'Bearer '+self.server.token,
                   'X-Studio-Request': '1'}
        req = Request(self.url+path, method=method, data=body, headers=headers)
        try:
            response = urlopen(req, timeout=3)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response), response.headers

    def test_origin_and_access_token_are_required(self):
        for token, origin in [('Bearer wrong', None), ('Bearer non-ASCII-é', None), (None, 'https://untrusted.invalid')]:
            with self.subTest(token=token, origin=origin):
                code, body, _ = self.request(token=token, origin=origin)
                self.assertEqual(code, 403)
                self.assertNotIn(self.server.token, json.dumps(body))

    def test_authorized_config_discloses_no_secret_and_only_exact_origin(self):
        with patch.dict(os.environ, {}, clear=True):
            code, body, headers = self.request()
        self.assertEqual(code, 200)
        self.assertFalse(body['enabled'])
        self.assertEqual(headers['Access-Control-Allow-Origin'], 'http://127.0.0.1:8777')
        self.assertNotIn(self.server.token, json.dumps(body))
        self.assertEqual(self.request('/api/datasets')[0], 404)

    def test_bad_chat_body_is_bounded_before_provider_call(self):
        with patch.object(gateway, 'chat', side_effect=AssertionError('Must not reach provider')) as chat:
            self.assertEqual(self.request('/api/assistant/chat', method='POST', body=b'')[0], 400)
            self.assertEqual(self.request('/api/assistant/chat', method='POST', body=b'invalid json')[0], 400)
            chat.assert_not_called()


if __name__ == '__main__':
    unittest.main()
