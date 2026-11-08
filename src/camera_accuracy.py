"""Measure how well presence detection works on this camera, in this room, for this person.

`python main.py --mode measure --consent` opens a page at http://127.0.0.1:8770 that guides the
person through five 30-second steps (sitting normally, away, looking at a phone, turned sideways,
away again). Twice a second the camera's person confidence is recorded next to what the person was
actually doing, so the result is a real measurement rather than a guess. No image or video is kept:
only (step, expected, confidence) numbers, saved to .runtime/camera-accuracy.json.

The result shows accuracy at the current threshold and which threshold (the admin's «Камерын
итгэлцлийн босго») would have done best on these samples.
"""

from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import statistics
import threading
import time

PORT = 8770
STEP_SECONDS = 30
SETTLE_SECONDS = 4  # The first seconds of a step are spent moving; they are not scored.
SAMPLE_EVERY = 0.5
FLOOR = 0.05  # Detector threshold during the measurement, so weaker detections are seen too.
STEPS = (
    ('present', 'Компьютерийнхээ өмнө суугаад хэвийн ажилла: дэлгэц рүү харж, бич.'),
    (
        'absent',
        'Босоод камерт харагдахгүй газар оч (өрөөнөөс гарах эсвэл камерын ард зогсох). '
        '30 секундын дараа дохио дуугарахад буцаж ир.',
    ),
    ('present', 'Суугаад утсаа гартаа барьж, доош хар.'),
    ('present', 'Сандал дээрээ хажуу тийш эргэж эсвэл арагшаа налж суу.'),
    ('absent', 'Дахин гарч, камерт харагдахгүй газар 30 секунд бай. Дохио дуугарахад буцаж ир.'),
)
THRESHOLDS = [round(0.10 + 0.05 * step, 2) for step in range(17)]  # 0.10 … 0.90


def score(samples, threshold):
    """Accuracy of `confidence >= threshold` against what the person was doing."""
    hits = [(row['expected'] == 'present') == (row['confidence'] >= threshold) for row in samples]
    present = [hit for hit, row in zip(hits, samples) if row['expected'] == 'present']
    absent = [hit for hit, row in zip(hits, samples) if row['expected'] == 'absent']

    def share(values):
        return sum(values) / len(values) if values else None

    seen, missed = share(present), share(absent)
    return {
        'threshold': threshold,
        'accuracy': share(hits),
        'present_detected': seen,  # Sitting there and counted as present.
        'absent_detected': missed,  # Away and counted as away.
        'balanced_accuracy': (seen + missed) / 2 if seen is not None and missed is not None else share(hits),
    }


def evaluate(samples, current=0.45):
    if not samples:
        raise ValueError('No samples were recorded.')
    sweep = [score(samples, threshold) for threshold in THRESHOLDS]
    best = max(sweep, key=lambda row: (round(row['balanced_accuracy'], 4), -abs(row['threshold'] - current)))
    steps = []
    for index, (expected, instruction) in enumerate(STEPS):
        rows = [row for row in samples if row['step'] == index]
        if rows:
            steps.append(
                {
                    'step': index + 1,
                    'expected': expected,
                    'instruction': instruction,
                    'samples': len(rows),
                    'accuracy': score(rows, current)['accuracy'],
                    'median_confidence': round(statistics.median(row['confidence'] for row in rows), 3),
                }
            )
    latencies = [row['ms'] for row in samples if 'ms' in row]
    return {
        'samples': len(samples),
        'current': score(samples, current),
        'best': best,
        'sweep': sweep,
        'steps': steps,
        'median_detection_ms': round(statistics.median(latencies)) if latencies else None,
    }


class Session:
    """The state the guidance page shows; the camera loop in run() moves it forward."""

    def __init__(self, current):
        self.current = current
        self.lock = threading.Lock()
        self.stage = 'loading'  # loading → ready → running → done | error
        self.step = -1
        self.step_ends = 0.0
        self.result = None
        self.error = ''
        self.started = threading.Event()
        self.finished = threading.Event()

    def view(self):
        with self.lock:
            remaining = max(0, round(self.step_ends - time.monotonic())) if self.stage == 'running' else None
            step = STEPS[self.step] if 0 <= self.step < len(STEPS) else None
            return {
                'stage': self.stage,
                'step': self.step + 1,
                'steps': len(STEPS),
                'expected': step[0] if step else None,
                'instruction': step[1] if step else None,
                'remaining': remaining,
                'result': self.result,
                'error': self.error,
            }


def handler_for(session):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, status, body, kind):
            self.send_response(status)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)

        def allowed(self):
            return self.headers.get('Host') in (f'127.0.0.1:{PORT}', f'localhost:{PORT}')

        def do_GET(self):
            if not self.allowed():
                return self.reply(403, b'{}', 'application/json')
            if self.path == '/state':
                return self.reply(200, json.dumps(session.view(), ensure_ascii=False).encode(), 'application/json')
            self.reply(200, PAGE.encode(), 'text/html; charset=utf-8')

        def do_POST(self):
            origin = self.headers.get('Origin')
            if not self.allowed() or origin not in (f'http://127.0.0.1:{PORT}', f'http://localhost:{PORT}'):
                return self.reply(403, b'{}', 'application/json')
            if self.path == '/start' and session.stage == 'ready':
                session.started.set()
            elif self.path == '/finish':
                session.finished.set()
            self.reply(200, b'{}', 'application/json')

    return Handler


class AccuracySession:
    def __init__(self, config):
        self.config = config
        self.current = float(config.get('confidence_threshold', 0.45))
        self.report = Path(config.get('accuracy_report', '.runtime/camera-accuracy.json'))

    def run(self, seconds=None):
        import webbrowser

        from src.camera_capture import check_session, open_camera, unopened_camera_error
        from src.detector import ObjectDetector

        session = Session(self.current)
        server = ThreadingHTTPServer(('127.0.0.1', PORT), handler_for(session))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        print(f'Camera accuracy: open http://127.0.0.1:{PORT} and follow the steps.', flush=True)
        webbrowser.open(f'http://127.0.0.1:{PORT}')
        cap = None
        try:
            detector = ObjectDetector(self.config['model_name'], FLOOR)
            person = self.config.get('labels', {}).get('person', 'person')
            import numpy as np

            detector.detect_presence(np.zeros((480, 640, 3), dtype=np.uint8), person)  # Load the model now.
            with session.lock:
                session.stage = 'ready'
            while not session.started.wait(0.2):
                check_session()
            cap = open_camera(self.config['camera_index'])
            if cap is None or not cap.isOpened():
                raise unopened_camera_error()
            samples = []
            for index in range(len(STEPS)):
                begins = time.monotonic()
                with session.lock:
                    session.stage, session.step, session.step_ends = 'running', index, begins + STEP_SECONDS
                next_sample = begins + SETTLE_SECONDS
                while time.monotonic() < begins + STEP_SECONDS:
                    check_session()
                    ok, frame = cap.read()
                    if not ok:
                        raise RuntimeError('Camera frame could not be read.')
                    now = time.monotonic()
                    if now >= next_sample:
                        before = time.perf_counter()
                        found = detector.detect_presence(frame, person)
                        samples.append(
                            {
                                'step': index,
                                'expected': STEPS[index][0],
                                'confidence': round(found['confidence'], 4),
                                'ms': round((time.perf_counter() - before) * 1000, 1),
                            }
                        )
                        next_sample = now + SAMPLE_EVERY
            cap.release()  # The camera goes off as soon as the steps are done.
            cap = None
            result = evaluate(samples, self.current)
            self.report.parent.mkdir(parents=True, exist_ok=True)
            self.report.write_text(
                json.dumps(
                    {'measured_at': datetime.now().astimezone().isoformat(), **result, 'raw': samples},
                    ensure_ascii=False,
                    indent=1,
                ),
                encoding='utf-8',
            )
            with session.lock:
                session.stage, session.result = 'done', result
            print(json.dumps({key: result[key] for key in ('samples', 'current', 'best')}, ensure_ascii=False))
            session.finished.wait(seconds or 600)  # Keep the page's result readable for a while.
        except Exception as exc:
            with session.lock:
                session.stage, session.error = 'error', str(exc) or exc.__class__.__name__
            session.finished.wait(60)
            raise
        finally:
            if cap is not None:
                cap.release()
            server.shutdown()
            server.server_close()


PAGE = """<!doctype html>
<html lang="mn"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Камерын нарийвчлал</title>
<style>
:root{--bg:#f3f6f5;--card:#fff;--ink:#17221f;--muted:#586763;--line:#d9e3df;--accent:#14957c;--soft:#dff3ee;--away:#c27a10;--awaysoft:#fbf0dc}
@media (prefers-color-scheme: dark){:root{--bg:#0f1614;--card:#17211e;--ink:#e5eeeb;--muted:#9db0ab;--line:#2a3834;--accent:#3cc9aa;--soft:#163a32;--away:#f0b14a;--awaysoft:#3a2c12;color-scheme:dark}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:17px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif;padding:24px 16px}
main{max-width:720px;margin:0 auto;display:grid;gap:18px}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:22px;display:grid;gap:12px}
h1{margin:0;font-size:26px}p{margin:0}.muted{color:var(--muted)}
button{font:inherit;font-weight:600;border:0;border-radius:10px;padding:12px 20px;background:var(--accent);color:#fff;cursor:pointer;justify-self:start}
button:disabled{opacity:.5;cursor:default}
.now{font-size:24px;font-weight:600;line-height:1.35}
.badge{justify-self:start;padding:4px 12px;border-radius:999px;font-weight:600;font-size:14px;background:var(--soft);color:var(--accent)}
.badge.absent{background:var(--awaysoft);color:var(--away)}
.clock{font:600 64px/1 ui-monospace,Menlo,monospace;font-variant-numeric:tabular-nums}
.bar{height:8px;border-radius:8px;background:var(--line);overflow:hidden}.bar i{display:block;height:100%;background:var(--accent);transition:width .4s}
table{border-collapse:collapse;width:100%;font-size:15px;font-variant-numeric:tabular-nums}
td,th{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left}th{color:var(--muted);font-weight:500}
.big{font-size:40px;font-weight:700}.wrap{overflow-x:auto}
tr.best td{font-weight:700;color:var(--accent)}
</style></head><body><main>
<section class="card"><h1>Камерын нарийвчлалыг хэмжих</h1>
<p class="muted">5 алхам, тус бүр 30 секунд (нийт 2.5 минут). Алхам бүрийн зааврыг дагана. Камер секундэд 2 удаа «хүн байна уу» гэж
дүгнэнэ. Зураг, бичлэг хадгалахгүй, зөвхөн тоо.</p></section>
<section class="card" id="panel"><p>Загвар ачаалж байна…</p></section>
</main><script>
const panel = document.getElementById('panel');
let lastStep = 0, audio = null;
function beep() {
  try {
    audio = audio || new AudioContext();
    const o = audio.createOscillator(), g = audio.createGain();
    o.frequency.value = 880; g.gain.value = 0.15; o.connect(g); g.connect(audio.destination);
    o.start(); o.stop(audio.currentTime + 0.35);
  } catch (e) {}
}
function esc(text) { return String(text).replace(/[&<>"]/g, (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c])); }
function pct(v) { return v == null ? '—' : Math.round(v * 100) + '%'; }
async function post(path) { await fetch(path, {method: 'POST'}); }
function render(s) {
  if (s.stage === 'loading') { panel.innerHTML = '<p>Загвар ачаалж байна…</p>'; return; }
  if (s.stage === 'ready') {
    panel.innerHTML = '<p class="now">Бэлэн үү?</p><p>Компьютерийнхээ өмнө хэвийн суугаад «Эхлэх» дарна. Алхам солигдох бүрд дохио дуугарна — дуу асаалттай эсэхийг шалгаарай.</p><button id="go">Эхлэх</button>';
    document.getElementById('go').onclick = () => { beep(); post('/start'); };
    return;
  }
  if (s.stage === 'running') {
    if (s.step !== lastStep) { if (lastStep) beep(); lastStep = s.step; }
    const away = s.expected === 'absent';
    panel.innerHTML = `<span class="badge ${away ? 'absent' : ''}">Алхам ${s.step}/${s.steps} · ${away ? 'Байхгүй' : 'Байгаа'}</span>
      <p class="now">${s.instruction}</p><div class="clock">${s.remaining}</div>
      <div class="bar"><i style="width:${((s.step - 1) * 30 + (30 - s.remaining)) / (s.steps * 30) * 100}%"></i></div>`;
    return;
  }
  if (s.stage === 'error') { panel.innerHTML = '<p class="now">Алдаа гарлаа</p><p>' + esc(s.error) + '</p>'; return; }
  if (s.stage === 'done') {
    if (lastStep !== -1) { beep(); lastStep = -1; }
    const r = s.result, c = r.current, b = r.best;
    const rows = r.sweep.map(x => `<tr class="${x.threshold === b.threshold ? 'best' : ''}"><td>${x.threshold.toFixed(2)}</td><td>${pct(x.present_detected)}</td><td>${pct(x.absent_detected)}</td><td>${pct(x.accuracy)}</td></tr>`).join('');
    const steps = r.steps.map(x => `<tr><td>${x.step}</td><td>${x.expected === 'present' ? 'Байгаа' : 'Байхгүй'}</td><td>${pct(x.accuracy)}</td><td>${x.median_confidence.toFixed(2)}</td></tr>`).join('');
    panel.innerHTML = `<p class="muted">Дууслаа. Камер унтарсан.</p>
      <p>Одоогийн босго ${c.threshold.toFixed(2)}-оор нарийвчлал</p><p class="big">${pct(c.accuracy)}</p>
      <p>Суугаа үед «байгаа» гэж зөв таньсан: <b>${pct(c.present_detected)}</b> · Байхгүй үед «байхгүй» гэж зөв таньсан: <b>${pct(c.absent_detected)}</b></p>
      <p>Хамгийн сайн босго энэ хэмжилтэд: <b>${b.threshold.toFixed(2)}</b> (${pct(b.accuracy)}). Админ «Тохиргоо → Камерын итгэлцлийн босго»-д оруулж болно.</p>
      <p class="muted">Энэ нь нэг удаагийн богино хэмжилт. Босгоо солихоос өмнө өөр гэрэлтүүлэг, өөр цагт 2–3 удаа давтаж хэмжвэл илүү найдвартай.</p>
      <p class="muted">${r.samples} ажиглалт; нэг дүгнэлт ~${r.median_detection_ms} ms. Тоо: .runtime/camera-accuracy.json</p>
      <h2>Алхам бүрээр (босго ${c.threshold.toFixed(2)})</h2><div class="wrap"><table><tr><th>Алхам</th><th>Үнэн</th><th>Зөв</th><th>Дундаж итгэлцүүр</th></tr>${steps}</table></div>
      <h2>Босго бүрээр</h2><div class="wrap"><table><tr><th>Босго</th><th>Байгааг таньсан</th><th>Байхгүйг таньсан</th><th>Нийт</th></tr>${rows}</table></div>
      <button id="end">Дуусгах</button>`;
    document.getElementById('end').onclick = () => post('/finish');
  }
}
let shown = '';
async function poll() {
  try {
    const s = await (await fetch('/state')).json();
    const key = JSON.stringify(s);
    if (key !== shown) { shown = key; render(s); }
  } catch (e) {}
  setTimeout(poll, 500);
}
poll();
</script></body></html>
"""
