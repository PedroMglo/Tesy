import unittest
from unittest.mock import patch
from optin_integration_client import grade
from run_task_server import fetch
from c2_server_run import stream_chat
class IntegrationClientTests(unittest.TestCase):
    def test_grader_strict_json_and_history(self):
        self.assertTrue(grade(0,'12345',None));self.assertTrue(grade(1,'12345','12345'))
        self.assertFalse(grade(1,'54321','12345'))
        for i,port in [(2,18440),(3,18441)]:
            good='{"projeto":"Lume","local":true,"armazenamento":"disco","porta":'+str(port)+'}'
            self.assertTrue(grade(i,good,None));self.assertFalse(grade(i,'```json\n'+good+'\n```',None));self.assertFalse(grade(i,good.replace('true','1'),None));self.assertFalse(grade(i,good.replace('Lume','Aster'),None))
    def test_http_explicit_endpoint_and_default_preserved(self):
        with patch('run_task_server.urlopen') as send:
            send.return_value.__enter__.return_value.read.return_value=b'{}'
            fetch('/health',base_url='http://127.0.0.1:18440')
            self.assertEqual(send.call_args.args[0].full_url,'http://127.0.0.1:18440/health')
