# Computer activity agent

Keyboard/mouse-ийн **агуулгыг биш**, зөвхөн ажилласан хугацаа, idle хугацаа, app usage-ийг
60 секунд тутам нэгтгэн backend руу илгээдэг local Python agent.

## Нууцлалын дүрэм (хатуу)

| Дүрэм | Хэрхэн хэрэгжсэн |
|---|---|
| Keystroke text, password, clipboard, file content хадгалахгүй | `collector.py`: keyboard callback `key`-г огт уншихгүй, зөвхөн тоолно. `contract.py`: `keystrokes`, `password`, `clipboard`... талбартай batch-ийг API буцаана |
| Mouse-ийн нарийн координат хадгалахгүй | Click/scroll-ийг тоолно, `x, y`-г хаяна. Хөдөлгөөн зөвхөн idle timer-г шинэчилнэ |
| Event бүрийг сервер рүү явуулахгүй | 60 секундын summary-г нэг batch болгож илгээнэ |
| Цонхны гарчиг авахгүй | Зөвхөн процессын нэр (`chrome.exe`) |
| Hostname явуулахгүй | `device_id` нь hostname+MAC-ийн SHA-256 hash |

## Файлын бүтэц

```
agent.py              run / check / mock command
collector.py          pynput listener, idle timer, psutil foreground app
sender.py             60 сек batch sender, retry, spool (offline хадгалалт)
contract.py           Activity JSON contract + validation
summary.py            W metric-д зориулсан active/idle/app summary
mock_server.py        Туршилтын API + SQLite DB (activity, camera, summary)
check_permissions.py  OS permission шалгалт
run_agent.bat         Унавал автоматаар дахин асаадаг Windows script
tests/                Unit, integration, reliability test
```

## Суулгах

```bash
cd activity_agent
python -m pip install -r requirements.txt
python agent.py check
```

`check` бүх мөрөнд `OK` гарвал бэлэн. `config.json`-д ажилтан бүрийн `employee_id`-г өөрчилнө.

## Ажиллуулах

```bash
# 1-р терминал: backend (бодит backend байхгүй үед)
python mock_server.py --port 8000

# 2-р терминал: agent
python agent.py mock     # нэг туршилтын batch илгээж API contract шалгана
python agent.py run      # agent ажиллуулна, Ctrl+C-ээр зогсооно
```

Өдрийн summary авах:

```bash
curl -H "Authorization: Bearer dev-token" "http://127.0.0.1:8000/api/v1/summary?employee_id=emp-001&date=2026-11-05"
```

Хариуд `activity` (active/idle секунд, `active_ratio`, top apps) болон тухайн employee/date-ийн
`camera_events` хамт ирнэ. Score service нь `activity.active_ratio`, `top_apps`-ийг W metric-д ашиглана.

### Компьютер асахад автоматаар ажиллуулах (Windows)

```bat
schtasks /create /tn "ActivityAgent" /sc onlogon /rl limited /tr "\"C:\full\path\activity_agent\run_agent.bat\""
```

Устгах: `schtasks /delete /tn "ActivityAgent" /f`

## config.json

| Түлхүүр | Утга |
|---|---|
| `api_url`, `api_token` | Backend endpoint ба Bearer token |
| `employee_id` | Ажилтны ID (camera module-тэй ижил ID байх ёстой) |
| `batch_interval_seconds` | Илгээх давтамж (60) |
| `idle_threshold_seconds` | Хэдэн секунд input байхгүй бол idle гэж тооцох (60) |
| `spool_file` | Илгээж чадаагүй batch-ууд хадгалагдах файл |
| `max_spool_batches` | Spool-ийн дээд хэмжээ (10000 ≈ 7 хоног) |

## Activity JSON contract (v1.0)

`POST /api/v1/activity`, header `Authorization: Bearer <token>`:

```json
{
  "schema_version": "1.0",
  "agent_version": "0.1.0",
  "employee_id": "emp-001",
  "device_id": "dde59b7ef949f039",
  "period_start": "2026-11-05T02:12:28Z",
  "period_end": "2026-11-05T02:13:28Z",
  "active_seconds": 42,
  "idle_seconds": 18,
  "keyboard_events": 120,
  "mouse_events": 15,
  "apps": [{"name": "chrome.exe", "seconds": 30}, {"name": "code.exe", "seconds": 12}]
}
```

- Бүх цаг **UTC** (`Z`). Camera module ч мөн UTC ашиглавал timestamp шууд тулгагдана.
  Backend өдрийг `--tz-offset` (Монгол: 8) ашиглан орон нутгийн огноо руу хөрвүүлнэ.
- `(employee_id, device_id, period_start)` давтагдвал сервер алгасна, тиймээс retry аюулгүй.
- Хариу: `201` хадгалсан, `200` давхардсан, `422` contract алдаа, `401` token буруу.

## Найдвартай байдал

- **Сүлжээ/API унтарсан**: batch `data/spool.jsonl`-д хадгалагдаж, холболт сэргэхэд хамгийн хуучнаас нь эхлэн илгээгдэнэ.
- **5xx, 408, 429**: дахин оролдоно. **Бусад 4xx**: log-д бичээд хаяна (дахин илгээсэн ч буцаагдана).
- **Agent restart**: spool файл диск дээр байгаа тул өгөгдөл алдагдахгүй. `run_agent.bat` унасан agent-ийг дахин асаана.
- **Laptop sleep**: 10 секундээс урт завсрыг active/idle-д тоолохгүй.
- **Listener зогсвол**: main loop автоматаар дахин эхлүүлнэ.

## Test

```bash
python -m unittest discover -s tests -v
```

1/3/5 минутын idle test, contract validation, Agent → API → DB, camera холбоо, сүлжээ тасрах/сэргэх,
давхар илгээлт, буруу token зэргийг шалгана (fake clock тул хэдхэн секундэд дуусна).

**Гараар шалгах (3 laptop):** laptop бүр дээр `check` → `run`, 1/3/5 минут гар/mouse-д хүрэхгүй
байж summary-д `idle_seconds` нэмэгдэж байгааг харна. Wi-Fi-г 2 минут салгаад буцааж залгахад
`data/agent.log`-д "waiting in spool" гарч, дараа нь бүх batch сервер дээр ирсэн байх ёстой.

## Troubleshooting

| Асуудал | Шийдэл |
|---|---|
| `pynput listener FAIL` (macOS) | System Settings → Privacy & Security → **Accessibility** болон **Input Monitoring**-д Terminal/Python-г нэмээд terminal-аа дахин нээнэ |
| `pynput listener FAIL` (Linux) | Wayland дэмжигдэхгүй; login дэлгэц дээр "Ubuntu on Xorg" сонгоно |
| `Foreground app detection FAIL` | Windows: ажиллаж байгаа app admin эрхтэй бол нэрийг нь уншиж чадахгүй ("unknown"). macOS: `pip install pyobjc-framework-Cocoa` |
| `API холболт FAIL` | `mock_server.py` ажиллаж байгаа эсэх, `config.json`-ийн `api_url` зөв эсэхийг шалгана. Agent ажиллаж чадна, өгөгдөл spool-д хуримтлагдана |
| `HTTP 401` log-д | `config.json`-ийн `api_token` backend-ийнхтэй таарахгүй байна |
| `HTTP 422` log-д | Contract зөрсөн; log дээрх `errors`-ийг харна |
| Кирилл үсэг `?` болж харагдана | Terminal дээр `chcp 65001` |
| `ModuleNotFoundError: pynput` | `python -m pip install -r requirements.txt` (agent-ийг ажиллуулж буй python-оор) |
| Spool файл томорч байна | Backend удаан хугацаанд хүрэхгүй байна; `data/agent.log`-г шалгана |
