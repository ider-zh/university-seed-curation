import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from university_curation import sources

class Response(io.BytesIO):
    def __init__(self,data,headers=None):super().__init__(json.dumps(data).encode());self.headers=headers or {}

class RetryTests(unittest.TestCase):
    def test_maxlag_uses_retry_after_then_recovers(self):
        with patch.object(sources,'urlopen',side_effect=[Response({'error':{'code':'maxlag'}},{'Retry-After':'8'}),Response({'ok':True})]), \
             patch.object(sources.time,'sleep') as sleep,patch.object(sources.random,'uniform',return_value=0):
            self.assertEqual(sources.download('https://www.wikidata.org/w/api.php'),{'ok':True})
            sleep.assert_called_once_with(8)
    def test_long_server_delay_returns_task_to_manager_without_shortening_wait(self):
        with patch.object(sources,'urlopen',return_value=Response({'error':{'code':'maxlag'}},{'Retry-After':'360'})),patch.object(sources.time,'sleep') as sleep:
            with self.assertRaises(sources.RetryableSourceError) as caught:sources.download('https://www.wikidata.org/w/api.php')
            self.assertEqual(caught.exception.retry_after,360);sleep.assert_not_called()
    def test_http_throttle_and_retry_budget(self):
        error=HTTPError('https://www.wikidata.org',429,'busy',{'Retry-After':'120'},None)
        with patch.object(sources,'urlopen',side_effect=error),patch.object(sources.time,'sleep') as sleep:
            with self.assertRaises(sources.RetryableSourceError) as caught:sources.download('https://www.wikidata.org/w/api.php')
            self.assertEqual(caught.exception.code,'http_429');sleep.assert_not_called()
    def test_repeated_maxlag_never_returns_successful_empty_data(self):
        with patch.object(sources,'urlopen',side_effect=lambda *a,**k:Response({'error':{'code':'maxlag'}})), \
             patch.object(sources.time,'sleep') as sleep,patch.object(sources.random,'uniform',return_value=0):
            with self.assertRaises(sources.RetryableSourceError):sources.download('https://www.wikidata.org/w/api.php')
            self.assertEqual([c.args[0] for c in sleep.call_args_list],[5,10])
