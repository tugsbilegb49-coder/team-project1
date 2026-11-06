"""60 секундын batch sender + network/API error handling (Өдөр 3, 6).

Илгээж чадаагүй batch-ийг spool файлд (JSON Lines) хадгалж, дараагийн удаа
хамгийн хуучнаас нь эхлэн дахин илгээнэ. Agent restart хийсэн ч өгөгдөл алдагдахгүй.
"""

import json
import logging
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
from token_store import read_tokens, save_tokens, StaleTokenError
import urllib.error
import urllib.request

log = logging.getLogger("agent.sender")


class BatchSender:
    def __init__(self, api_url, api_token, spool_file, timeout=10, max_spool_batches=10000, token_file=None, max_spool_bytes=10 * 1024 * 1024):
        if isinstance(max_spool_batches, bool) or not isinstance(max_spool_batches, int) or max_spool_batches < 1:
            raise ValueError("max_spool_batches must be a positive integer")
        if isinstance(max_spool_bytes, bool) or not isinstance(max_spool_bytes, int) or max_spool_bytes < 1024:
            raise ValueError("max_spool_bytes must be at least 1024")
        self.max_spool_bytes = max_spool_bytes
        self.token_file = token_file
        self.api_url = api_url
        self.api_token = api_token
        self.spool_file = spool_file
        self.timeout = timeout
        self.max_spool_batches = max_spool_batches
        os.makedirs(os.path.dirname(os.path.abspath(spool_file)), exist_ok=True)

    def _token(self, refresh=False):
        if not self.token_file:
            return self.api_token
        tokens = read_tokens(self.token_file)
        if refresh:
            expected_refresh = tokens["refresh"]
            base = self.api_url.split("/api/")[0]
            request = urllib.request.Request(base + "/api/auth/refresh/",
                data=json.dumps({"refresh":tokens["refresh"]}).encode(),
                headers={"Content-Type":"application/json"}, method="POST")
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                tokens.update(json.load(response))
            save_tokens(self.token_file, tokens, expected_refresh=expected_refresh)
        return tokens["access"]

    def post(self, batch, retry=True):
        """True: сервер хүлээж авсан эсвэл буцаагдсан (дахин илгээх утгагүй). False: дахин оролдоно."""
        try:
            token = self._token()
        except (OSError, ValueError, KeyError, StaleTokenError) as exc:
            log.error("Login required; retaining batch: %s", exc)
            return False
        body = json.dumps(batch).encode("utf-8")
        request = urllib.request.Request(
            self.api_url, data=body, method="POST",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return 200 <= response.status < 300
        except urllib.error.HTTPError as e:
            if e.code == 401 and self.token_file and retry:
                try:
                    self._token(refresh=True)
                except (OSError, ValueError, KeyError, StaleTokenError) as exc:
                    log.error("Login refresh failed; retaining batch: %s", exc)
                    return False
                return self.post(batch, retry=False)
            if e.code in (401, 403):
                log.error("Authentication or consent required; retaining batch")
                return False
            if 400 <= e.code < 500 and e.code not in (408, 429):
                # Contract/auth алдаа: дахин илгээвэл ч мөн л буцаагдана.
                log.error("API rejected batch %s: HTTP %s %s", batch.get("period_start"), e.code, e.read()[:300])
                return True
            log.warning("API error HTTP %s, will retry", e.code)
            return False
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            log.warning("Network error: %s, will retry", e)
            return False

    def send(self, batch):
        """Эхлээд хуучин spool-оо, дараа нь шинэ batch-ийг илгээнэ."""
        pending = self._read_spool() + [batch]
        sent = 0
        for item in pending:
            if not self.post(item):
                break
            sent += 1
        remaining = pending[sent:]
        if len(remaining) > self.max_spool_batches:
            log.warning("Spool full, dropping %d oldest batches", len(remaining) - self.max_spool_batches)
            remaining = remaining[-self.max_spool_batches:]
        retained = self._write_spool(remaining)
        if retained:
            log.info("Sent %d batch(es), %d waiting in spool", sent, retained)
        return sent, retained

    def spool_only(self, batch):
        """Унтрах үед: сүлжээ хүлээхгүйгээр batch-ийг spool руу бичнэ."""
        self._write_spool(self._read_spool() + [batch])

    def _read_spool(self):
        if not os.path.exists(self.spool_file):
            return []
        items = []
        with open(self.spool_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError:
                    log.warning("Skipping corrupt spool line")
        return items

    def _write_spool(self, items):
        lines, total = [], 0
        for item in reversed(items):
            line = json.dumps(item, ensure_ascii=False) + "\n"
            size = len(line.encode("utf-8"))
            if size > self.max_spool_bytes:
                continue
            if len(lines) >= self.max_spool_batches or total + size > self.max_spool_bytes:
                break
            lines.append(line)
            total += size
        dropped = len(items) - len(lines)
        if dropped:
            log.warning("Spool limit: dropped %d oldest/oversized batches", dropped)
        tmp = self.spool_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            os.chmod(tmp, 0o600)
            for line in reversed(lines):
                f.write(line)
        os.replace(tmp, self.spool_file)
        return len(lines)
