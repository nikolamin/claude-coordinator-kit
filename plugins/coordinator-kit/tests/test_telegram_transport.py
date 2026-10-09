"""Offline HTTP adapter checks. The token-shaped fixture is deliberately unusable."""
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from telegram_status import ApiError, NoRedirect, TelegramAPI


class Response(io.BytesIO):
    pass


class Opener:
    def __init__(self, value=None, error=None):
        self.value, self.error, self.requests = value, error, []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        if self.error:
            raise self.error
        return Response(self.value if isinstance(self.value, bytes) else json.dumps(self.value).encode())


class TelegramTransportTests(unittest.TestCase):
    def api(self, value=None, error=None):
        opener = Opener(value, error)
        with patch.dict(os.environ, {'OFFLINE_STATUS_TOKEN': '123:OFFLINE_EXAMPLE'}), \
                patch('telegram_status.urllib.request.build_opener', return_value=opener):
            api = TelegramAPI({'token_env': 'OFFLINE_STATUS_TOKEN'})
        return api, opener

    def test_real_request_shape_uses_fixed_https_json_and_bounded_timeout(self):
        api, opener = self.api({'ok': True, 'result': {'message_id': 7}})
        params = {'chat_id': '456', 'text': 'A & B', 'disable_notification': True}
        self.assertEqual(api('sendMessage', params), {'message_id': 7})
        request, timeout = opener.requests[0]
        self.assertEqual(request.full_url, 'https://api.telegram.org/bot123:OFFLINE_EXAMPLE/sendMessage')
        self.assertEqual(request.get_method(), 'POST')
        self.assertEqual(json.loads(request.data), params)
        self.assertEqual(timeout, 10)
        self.assertEqual(api.bot_id, '123')

    def test_provider_descriptions_are_replaced_by_fixed_categories(self):
        for description, expected in (
                ('Bad Request: message is not modified', 'not_modified'),
                ('Bad Request: message to edit not found', 'not_found'),
                ('Bad Request: message to delete not found', 'not_found'),
                ("Bad Request: message can't be deleted", 'cannot_delete'),
                ('Rejected private diagnostic content', 'api_rejected')):
            with self.subTest(expected=expected):
                api, _ = self.api({'ok': False, 'description': description,
                                  'parameters': {'retry_after': 123}})
                with self.assertRaises(ApiError) as raised:
                    api('sendMessage', {})
                self.assertEqual(str(raised.exception), expected)
                self.assertEqual(raised.exception.__dict__, {'category': expected, 'retry_after': 123})

    def test_http_error_body_is_classified_without_leaking_the_url(self):
        error = urllib.error.HTTPError('https://example.invalid/private-diagnostic', 429,
                                       'private-diagnostic', {}, io.BytesIO(json.dumps({
                                           'ok': False, 'description': 'private-diagnostic',
                                           'parameters': {'retry_after': 5}}).encode()))
        api, _ = self.api(error=error)
        with self.assertRaises(ApiError) as raised:
            api('sendMessage', {})
        self.assertEqual(str(raised.exception), 'api_rejected')
        self.assertEqual(raised.exception.retry_after, 5)

    def test_ambiguous_transport_and_malformed_receipts_never_claim_success(self):
        fixtures = [
            (None, urllib.error.URLError('private-diagnostic')),
            (b'<html>private-diagnostic</html>', None),
            ({'ok': True, 'result': {}}, None),
            ({'ok': True, 'result': {'message_id': True}}, None),
            ({'ok': True, 'result': {'message_id': -3}}, None),
            ({'result': {'message_id': 3}}, None),
            ([], None),
        ]
        for value, error in fixtures:
            api, _ = self.api(value, error)
            with self.subTest(value=value), self.assertRaises(ApiError) as raised:
                api('sendMessage', {})
            self.assertEqual(str(raised.exception), 'transport_unknown')
        api, _ = self.api({'ok': True, 'result': False})
        with self.assertRaises(ApiError) as raised:
            api('deleteMessage', {})
        self.assertEqual(str(raised.exception), 'transport_unknown')
        for result in (None, {}, True, {'message_id': False}):
            api, _ = self.api({'ok': True, 'result': result})
            with self.subTest(edit_result=result):
                with self.assertRaises(ApiError) as raised:
                    api('editMessageText', {'chat_id': '456', 'message_id': 7})
                self.assertEqual(str(raised.exception), 'transport_unknown')
        api, _ = self.api({'ok': True, 'result': {'message_id': 7}})
        self.assertEqual(api('editMessageText', {'chat_id': '456', 'message_id': 7}), {'message_id': 7})

    def test_redirects_and_receiver_methods_are_not_followed(self):
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, '', {}, 'https://example.invalid'))
        api, opener = self.api({'ok': True})
        with self.assertRaises(ValueError):
            api('getUpdates', {})
        self.assertEqual(opener.requests, [])

    def test_invalid_credentials_fail_before_opening_transport(self):
        with patch.dict(os.environ, {'OFFLINE_STATUS_TOKEN': 'not-a-token'}), \
                patch('telegram_status.urllib.request.build_opener') as opener:
            with self.assertRaises(ValueError) as raised:
                TelegramAPI({'token_env': 'OFFLINE_STATUS_TOKEN'})
            self.assertNotIn('not-a-token', str(raised.exception))
            opener.assert_not_called()


if __name__ == '__main__':
    unittest.main()
