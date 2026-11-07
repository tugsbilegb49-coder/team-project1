import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sender import BatchSender, StaleTokenError
from token_store import save_tokens


class SpoolLimitsTests(unittest.TestCase):
    def test_account_spools_remain_separate_across_login_and_refresh(self):
        import base64
        def tokens(user, serial):
            payload=base64.urlsafe_b64encode(json.dumps({'user_id':user,'jti':serial}).encode()).decode().rstrip('=')
            return {'access':'access-'+serial,'refresh':'header.'+payload+'.signature'}
        with TemporaryDirectory() as directory:
            root=Path(directory);login=root/'tokens.json';base=root/'spool.jsonl'
            base.write_text('{"legacy":true}\n')
            save_tokens(login,tokens(1,'first'))
            a=BatchSender('http://localhost/api/v1/activity','',str(base),token_file=login)
            a.spool_only({'account':'A'})
            save_tokens(login,tokens(1,'refreshed'))
            a.check_account()
            again=BatchSender(a.api_url,'',str(base),token_file=login)
            self.assertEqual(again.spool_file,a.spool_file)
            save_tokens(login,tokens(2,'second'))
            with self.assertRaises(StaleTokenError): a.send({'account':'B'})
            b=BatchSender(a.api_url,'',str(base),token_file=login)
            self.assertEqual(b._read_spool(),[])
            self.assertEqual(a._read_spool(),[{'account':'A'}])
            self.assertEqual(base.read_text(),'{"legacy":true}\n')

    def test_shutdown_spool_respects_count_and_bytes(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'spool.jsonl'
            sender=BatchSender('http://localhost','token',str(path),max_spool_batches=2,max_spool_bytes=1024)
            for number in range(3):
                sender.spool_only({'id':number,'text':'x'*350})
            rows=[json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual([row['id'] for row in rows],[1,2])
            self.assertLessEqual(path.stat().st_size,1024)
            sender.spool_only({'id':3,'text':'x'*2000})
            self.assertEqual(len(sender._read_spool()),2)

    def test_send_returns_retained_count_after_byte_limit(self):
        from unittest.mock import patch
        with TemporaryDirectory() as directory:
            sender=BatchSender('http://localhost','token',str(Path(directory)/'spool.jsonl'),max_spool_bytes=1024)
            with patch.object(sender,'post',return_value=False):
                for number in range(3):
                    sent,waiting=sender.send({'id':number,'text':'x'*500})
            self.assertEqual(sent,0)
            self.assertEqual(waiting,len(sender._read_spool()))
            self.assertEqual(waiting,1)
