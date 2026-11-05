"""60 секундын batch sender + network/API error handling (Өдөр 3, 6).

Илгээж чадаагүй batch-ийг spool файлд (JSON Lines) хадгалж, дараагийн удаа
хамгийн хуучнаас нь эхлэн дахин илгээнэ. Agent restart хийсэн ч өгөгдөл алдагдахгүй.
"""

import json
import logging
import os
import urllib.error
import urllib.request

log = logging.getLogger("agent.sender")


class BatchSender:
    def __init__(self, api_url, api_token, spool_file, timeout=10, max_spool_batches=10000, token_file=None):
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
        with open(self.token_file, encoding="utf-8") as handle:
            tokens = json.load(handle)
        if refresh:
            base = self.api_url.split("/api/")[0]
            request = urllib.request.Request(base + "/api/auth/refresh/",
                data=json.dumps({"refresh":tokens["refresh"]}).encode(),
                headers={"Content-Type":"application/json"}, method="POST")
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                tokens.update(json.load(response))
            temp = self.token_file + ".batch.tmp"
            with open(temp, "w", encoding="utf-8") as handle:
                os.chmod(temp, 0o600)
                json.dump(tokens, handle)
            os.replace(temp, self.token_file)
        return tokens["access"]

    def post(self, batch, retry=True):
        """True: сервер хүлээж авсан эсвэл буцаагдсан (дахин илгээх утгагүй). False: дахин оролдоно."""
        try:
            token = self._token()
        except (OSError, ValueError, KeyError) as exc:
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
                except (OSError, ValueError, KeyError) as exc:
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
        self._write_spool(remaining)
        if remaining:
            log.info("Sent %d batch(es), %d waiting in spool", sent, len(remaining))
        return sent, len(remaining)

    def spool_only(self, batch):
        """Унтрах үед: сүлжээ хүлээхгүйгээр batch-ийг spool руу бичнэ."""
        with open(self.spool_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(batch) + "\n")

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
        tmp = self.spool_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            for item in items:
                f.write(json.dumps(item) + "\n")
        os.replace(tmp, self.spool_file)
