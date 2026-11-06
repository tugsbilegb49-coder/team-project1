import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sender import BatchSender


class SpoolLimitsTests(unittest.TestCase):
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
