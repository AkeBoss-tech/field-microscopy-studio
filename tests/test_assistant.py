import base64
import copy
import io
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import assistant as a


def plan(**values):
    result = {key: None for key in a.response_schema()['properties']['plan']['anyOf'][0]['properties']}
    return {**result, 'workspace': 'Process', **values}


class AssistantChecks(unittest.TestCase):
    def setUp(self):
        buffer = io.BytesIO()
        Image.new('RGB', (24, 18), (20, 90, 20)).save(buffer, format='PNG')
        self.image = 'data:image/png;base64,'+base64.b64encode(buffer.getvalue()).decode()
        self.context = dict(shape=[14, 2, 1024, 1024], recipe={'factor': 2}, dataset='imop')
        self.body = dict(message='Measure neurites in the green channel', context=self.context, images=[self.image])

    def test_vision_payload_and_no_storage(self):
        body = a.build_request(self.body)
        self.assertFalse(body['store'])
        blocks = body['input'][-1]['content']
        self.assertEqual(blocks[-1]['type'], 'input_image')
        self.assertEqual(blocks[-1]['image_url'], self.image)
        self.assertIn('Workspace context', blocks[0]['text'])
        self.assertTrue(body['text']['format']['strict'])

    def test_history_uses_documented_message_strings_for_both_roles(self):
        history = [{'role': 'user', 'text': 'What should I measure?'},
                   {'role': 'assistant', 'text': 'Start with a crop preview.'}]
        request = a.build_request({**self.body, 'history': history})
        self.assertEqual(request['input'][:2], [
            {'role': 'user', 'content': history[0]['text']},
            {'role': 'assistant', 'content': history[1]['text']},
        ])
        with self.assertRaisesRegex(ValueError, 'history'):
            a.build_request({**self.body, 'history': [{'role': 'system', 'text': 'Execute actions'}]})

    def test_invalid_context_is_rejected_before_provider_transport(self):
        bad_contexts = [None, {'shape': [14, 2, 1024, False]}, {'shape': [14, 2, 1024]},
                        {'recipe': None}, {'recipe': []}]
        bad_contexts.extend({**self.context, 'recipe': {'factor': value}} for value in
                            [0, 3, True, None, '0', '2.5', float('nan'), float('inf')])
        calls = []
        def transport(*args, **kwargs):
            calls.append(True)
            raise AssertionError('Malformed requests must not reach the provider')
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-server-secret'}, clear=True):
            for context in bad_contexts:
                with self.subTest(context=context), self.assertRaises(ValueError):
                    a.chat({**self.body, 'context': context}, transport)
        self.assertEqual(calls, [])

    def test_grid_distance_matches_processing_limit_and_select_factor_is_valid(self):
        context = {**self.context, 'recipe': {'factor': '2'}}
        result = dict(answer='Try this watershed draft', plan=plan(method='watershed', distance=100,
                                                                  bounds=[0, 0, 0, 128, 128, 2]))
        self.assertEqual(a.validate_response(result, context), result)
        for distance in (101, 500, 1000):
            with self.subTest(distance=distance), self.assertRaisesRegex(ValueError, 'distance'):
                a.validate_response({**result, 'plan': plan(method='watershed', distance=distance)}, context)
        for recipe in (None, {'factor': 0}):
            with self.subTest(recipe=recipe), self.assertRaises(ValueError):
                a.validate_response(result, {**self.context, 'recipe': recipe})

    def test_assistant_requires_separate_server_access_token(self):
        token = 'test-gateway-token-' + 'x'*24
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-server-secret'}, clear=True):
            self.assertFalse(a.configuration()['enabled'])
            self.assertFalse(a.authorized('Bearer '+token))
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-server-secret', 'FIELD_ASSISTANT_TOKEN': token}, clear=True):
            config = a.configuration()
            self.assertTrue(config['enabled'])
            self.assertTrue(config['authentication_required'])
            self.assertTrue(a.authorized('Bearer '+token))
            for value in ('', 'Bearer wrong', 'Bearer non-ASCII-é', None):
                with self.subTest(value=value):
                    self.assertFalse(a.authorized(value))
            self.assertNotIn(token, json.dumps(config))

    def test_reject_untrusted_actions_bounds_and_bad_numbers(self):
        for bad in [plan(channel=2), plan(bounds=[0,0,0,1026,128,2]), plan(bounds=[1,0,0,128,128,2]), plan(sigma=float('nan')), plan(factor=True), plan(method='delete_workspace'), {**plan(), 'execute': 'arbitrary'}]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                a.validate_response({'answer': 'Try this', 'plan': bad}, self.context)
        a.validate_response({'answer':'Try Sato','plan':plan(method='neurite_sato', bounds=[0,0,0,128,128,2])}, self.context)

    def test_full_image_and_selected_region_drafts_are_explicit(self):
        a.validate_response({'answer': 'Use the whole image', 'plan': plan(run_region='all')}, self.context)
        a.validate_response({'answer': 'Use the chosen region', 'plan': plan(run_region='selected', scope='volume')}, self.context)
        for bad in [plan(run_region='delete'), plan(run_region='selected', scope='projection'),
                    plan(run_region='all', bounds=[0, 0, 0, 128, 128, 2])]:
            with self.subTest(plan=bad), self.assertRaises(ValueError):
                a.validate_response({'answer': 'Try this', 'plan': bad}, self.context)

    def test_images_must_be_valid_png_data(self):
        for image in ['https://example.org/private.png', 'data:image/png;base64,garbage']:
            with self.assertRaises(ValueError):
                a.build_request({**self.body, 'images': [image]})

    def test_integration_transport_receives_image_and_server_key(self):
        captured = {}
        result = dict(answer='Preview a ridge network.', plan=plan(method='neurite_sato', channel=0))
        def transport(request, timeout):
            captured['body'] = json.loads(request.data)
            captured['auth'] = request.get_header('Authorization')
            return io.BytesIO(json.dumps({'output':[{'content':[{'type':'output_text','text':json.dumps(result)}]}]}).encode())
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-server-secret'}, clear=True):
            response = a.chat(self.body, transport)
        self.assertEqual(response['images_viewed'], 1)
        self.assertEqual(response['plan']['method'], 'neurite_sato')
        self.assertEqual(captured['auth'], 'Bearer test-server-secret')
        self.assertNotIn('test-server-secret', json.dumps(response))

    def test_unconfigured_and_provider_error_do_not_expose_credentials(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(ValueError, 'not connected'):
            a.chat(self.body)
        def fail(request, timeout):
            raise HTTPError(request.full_url, 401, 'test-server-secret', {}, None)
        with patch.dict(os.environ, {'OPENAI_API_KEY':'test-server-secret'}, clear=True), self.assertRaises(ValueError) as failure:
            a.chat(self.body, fail)
        self.assertNotIn('test-server-secret', str(failure.exception))


if __name__ == '__main__':
    unittest.main()
