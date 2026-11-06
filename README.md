# WorkTrack

React frontend, Django API, computer activity agent болон camera monitor нь нэг
`backend/` сервер, нэг database ашиглана. Root болон `backend/` доторх `manage.py`
хоёулаа ижил Django төслийг ажиллуулна.

## Нэг даралтаар асаах (macOS)

Finder-ээс төслийн хавтас дахь **Start WorkTrack.command** файлыг давхар дарна.
Энэ нь Python environment, backend dependency, npm dependency-ийг шаардлагатай үед
бэлдэж, migration хийгээд backend, frontend, computer agent-ийг хамт асаана.
Серверүүд өмнө нь ажиллаж байвал дахин асаахгүй. Browser автоматаар нээгдэнэ.
Анх удаа Python 3 болон Node.js/npm суусан байх шаардлагатай.

- Admin account байхгүй бол terminal дотор үүсгэх алхам гарна.
- Agent-ийн эхний тохиргоонд хугацаагаа бүртгүүлэх account-ийн username/password
  оруулна. Password дэлгэц дээр харагдахгүй, файлд хадгалагдахгүй; JWT хадгалагдана.
- Monitoring consent байхгүй бол зөвшөөрөл асууна. Татгалзвал зөвхөн веб ажиллана.
- Camera асаах эсэхийг `y/N` асуултаар сонгоно. `y` гэвэл camera dependency-ийг
  шаардлагатай үед суулгана. OS camera permission тусдаа шаардагдаж болно.
- Launcher цонхыг нээлттэй байлгана. Зогсоохдоо **Ctrl+C** дарна.
  Launcher өөрөө асаасан process-уудаа л зогсооно.

Дараагийн удаа зөвхөн энэ файлыг давхар дарахад хангалттай. Хадгалсан login-ийн
хугацаа дуусвал дахин нэвтрэхийг асууна. Agent өмнө нь pause болсон бол pause
төлөвийг хэвээр хадгална; resume хийхдээ `python agent/main.py --resume` ашиглана.
Веб дотор нэвтэрсэн account болон agent-ийн account тусдаа тул dashboard дээр
agent-д сонгосон хэрэглэгчийн тайланг харна.

Terminal-аас ашиглах хувилбарууд:

```bash
python3 worktrack.py              # Backend + frontend + agent, camera сонголт
python3 worktrack.py --web-only   # Зөвхөн веб систем
python3 worktrack.py --camera     # Agent болон camera хамт
```

Log-ууд `.runtime/backend.log`, `frontend.log`, `agent.log`, `camera.log` дотор байна.
Launcher ажиллаж байхад agent-ийг өөр terminal эсвэл OS startup script-ээр давхар
асаахгүй. macOS startup helper-ийн тохиргоо launcher-аас тусдаа хэвээр.

## Тохируулах

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
npm ci
cp backend/.env.example backend/.env
```

`backend/.env` дахь `DJANGO_SECRET_KEY`-г өөрийн random утгаар солино.
Хэрэв файл өмнө нь байгаа бол хуулж дарж болохгүй.

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Хоёр дахь terminal:

```bash
npm run dev
```

http://localhost:5173 дээр superuser-аар нэвтэрнэ. Vite `/api/` хүсэлтийг
http://127.0.0.1:8000 руу дамжуулна. Production build-д ижил origin reverse proxy
эсвэл build хийхээс өмнө `VITE_API_URL` болон backend CORS тохируулна.

## Хэрэглэх дараалал

1. Багийн гишүүд хэсэгт username, нэр, нууц үгтэй employee үүсгэнэ.
   Department, manager тохиргоог http://127.0.0.1:8000/admin/ дээр хийнэ.
2. Даалгавар хэсэгт ажилтанд task хуваарилж, deadline, status, чанарын үнэлгээг оруулна.
3. Ажилтан өөрийн account-аар agent-д нэвтэрч, monitoring consent олгоно.
4. Agent/camera өгөгдөл ирсний дараа Dashboard дээр ажилтан, өдөр сонгож
   «Оноо тооцох / шинэчлэх» дарна. Application, camera, score нь database-аас уншигдана.

Admin бүх хэрэглэгчийг, manager өөрийн хэлтсийг, employee зөвхөн өөрийн өгөгдлийг харна.
Task өөрчлөх эрх admin/manager-д байна. Нэр, task зэрэг бизнес өгөгдөл browser-ийн
localStorage-д хадгалагдахгүй. Login session нь tab-ийн sessionStorage-д хадгалагдана.

## Computer agent (үндсэн)

```bash
pip install -r activity_agent/requirements.txt
cp agent/config.example.json agent/config.json
python agent/main.py --login
python agent/main.py --grant-consent 2026-11
python agent/main.py
```

Тохиргооны API URL нь `http://127.0.0.1:8000`. Employee account-аар login хийнэ.
Agent нь device enroll, JWT refresh, offline queue ашиглана. OS-specific setup-ийг
`agent/` доторх script-үүдээс харна. Давхар хугацаа бүртгэхээс сэргийлж нэг компьютер
дээр хоёр computer agent зэрэг ажиллуулахгүй.

### Үндсэн agent-ийн хугацааны нарийвчлал

`agent/config.json` дахь `poll_interval_seconds` нь идэвхтэй апп шалгах давтамж
(default **1 секунд**), `interval_seconds` нь сервер рүү хуримтлагдсан segment-үүдийг
илгээх давтамж (default **30 секунд**) юм. Хуучин config-д шинэ түлхүүр байхгүй байсан
ч 1 секундийн default автоматаар хэрэглэгдэнэ.

VS Code → Safari → VS Code гэж 30 секунд дотор солигдсон ч segment бүр тусдаа
хадгалагдана. Апп хэвээр байсан ч 30 секунд тутам segment-ийг тасалж илгээнэ.
Upload нь тусдаа thread дээр ажилладаг тул сүлжээ удаашрахад sampler-ийг хүлээлгэхгүй.
Segment хаагдах бүрд offline queue-д хадгална; retry нь дараагийн upload мөчлөгт хийгдэнэ.
Ctrl+C үед сүүлийн ажигласан цаг хүртэлх segment-ийг хадгалж, queue илгээхэд
хамгийн ихдээ 5 секунд хүлээнэ. Үлдсэн өгөгдөл дараагийн асаалтанд дахин илгээгдэнэ.

Энэ нь polling тул 1 секундээс богино апп шилжилт алдагдаж болно; OS lookup удах үед
бодит sample хоорондын хугацаа уртсаж болно. Апп таних алдаа гарвал танигдаагүй
завсрыг өмнөх аппад таамгаар нэмэхгүй. Pause үед шинэ хугацаа цуглуулахгүй.
Энэ өөрчлөлт alternative `activity_agent/`-ийн collector-т хамаарахгүй.

### Өдөр солигдох, sleep/resume

Үндсэн agent-ийн interval-ийг `Asia/Ulaanbaatar`-ын 00:00 заагаар хуваана.
Жишээ нь 23:59:50–00:00:10 хооронд Code ашиглавал хоёр өдөрт тус бүр 10 секунд
хадгална. OS timezone өөр байсан ч тайлангийн өдөр Улаанбаатараар тооцогдоно.
API-ийн 3600 секундийн хязгаарыг давах урт segment мөн жижиглэгдэнэ.

`max_sample_gap_seconds` нь default **10 секунд**. Хоёр observation хооронд
үүнээс урт завсар гарвал үндсэн agent өмнөх segment-ийг сүүлийн баталгаатай
observation дээр дуусгаж, сэрсний дараа шинээр эхлүүлнэ. Sleep болон удаан гацсан
завсрыг ашигласан хугацаанд тооцохгүй. Энэ нь OS sleep event биш, sampling gap-д
суурилсан хамгаалалт учраас 10 секундээс богино sleep-ийг ялгахгүй.

Wall clock болон monotonic clock зөрөх, цаг ухрах үед мөн interval тасална.
Цаг ухарвал өмнө хадгалсан дууссан цагт хүрэх хүртэл шинэ хугацаа бүртгэхгүй,
ингэснээр давхардсан мөр үүсгэхгүй. Компьютерийн цаг серверээс ихээр түрүүлсэн бол
серверийн future-time validation хүсэлтийг буцааж болох тул OS цагийг зөв тохируулна.

Single-person camera uploader ч segment-ээ өдөр болон 3600 секундээр хуваана.
Camera timestamp нь дууссан цаг тул яг 00:00-д дууссан хэсэг өмнөх өдөрт тоологдоно.
Backend camera тайланд өмнө нь хадгалсан өдөр дамнасан мөрийн хугацааг мөн хоёр
өдөрт хувааж харуулна; database-ийн хуучин мөрийг өөрчлөхгүй. Camera capture-ийн
sleep хугацааг ялгах нь энэ үндсэн agent-ийн sampling-gap хамгаалалтад хамаарахгүй.

## Activity agent (өөр хувилбар)

```bash
pip install -r activity_agent/requirements.txt
python agent/main.py --login
python agent/main.py --grant-consent 2026-11
```

`activity_agent/config.json` дахь `employee_id`-г login хийсэн username болгон солино.
`token_file` нь үндсэн agent-ийн JWT файл; `dev-token` ашиглахгүй.

```bash
python activity_agent/agent.py run
```

`POST /api/v1/activity` compatibility endpoint нь batch-ийг ижил Django database-д
хадгалж, retry хийхэд ижил мөрийг дахин үүсгэхгүй. Aggregate app хугацаанд дарааллын
мэдээлэл байдаггүй тул хадгалсан цагийн offset нь бодит foreground дараалал биш.
Энэ contract-д app-ийн work ангилал байхгүй учраас `OTHER` ангиллаар хадгална;
keyboard/mouse event тоонуудыг database-д хадгалахгүй. Mock server нь зөвхөн тусдаа
тестийн хэрэгсэл; үндсэн системд асаах шаардлагагүй.

## Camera

```bash
pip install -r requirements.txt
python main.py
```

`config.yaml`-ийн `api_sync.enabled: true` нь camera state-ийг agent-ийн account,
device, token ашиглан `/api/activity-events/ingest/` рүү илгээнэ. Camera permission
олгох шаардлагатай. Single-person горимд account-д хамааруулна; multi-person
camera identity integration хийгдээгүй. Raw зураг API руу илгээхгүй.

## Database ба хуучин backend

SQLite default файл: `backend/db.sqlite3`. PostgreSQL-д `backend/.env` дахь
`POSTGRES_*` утгуудыг тохируулаад migrate хийнэ. Хуучин root `db.sqlite3`-ийг өөрчлөхгүй;
түүний `core` schema-г шинэ database руу автоматаар зөөхгүй. `core/` нь өмнөх
хэрэгжүүлэлтийн эх код бөгөөд үндсэн серверт ачаалагдахгүй. Доорх API заавар нь
зөвхөн одоогийн `backend/` серверт хамаарна. Хуучин `core/` endpoint болон model-ууд
одоогийн API-тай ижил биш; өмнөх эх код, зааврыг Git түүхээс харж болно.

Оноо нь `backend/scoring/services.py`-ийн дүрмийг ашиглана: T/Q/D нь task-аас,
W нь computer activity-ийн WORK харьцаанаас; computer data байхгүй үед camera
WORKING харьцаанаас гарна. Энэ дүрэм хуучин `core`-ийн дүрмээс ялгаатай.

## Шалгах

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test users workforce activity scoring
python -m unittest discover -s agent -p 'test*.py'
python -m unittest discover -s activity_agent/tests
npm run test
npm run lint
npm run build
```

Integration тест нь JWT login → task → device/consent → computer/camera ingest →
score → dashboard урсгал, batch replay, бусдын account-аар бичихийг хориглох,
invalid batch-ийн atomicity-г шалгана. Бодит camera capture болон PostgreSQL-г
эдгээр SQLite тестүүд баталгаажуулахгүй.

## API лавлагаа

Business API бүр JWT authentication шаарддаг. Login-оос авсан access token-ийг
`Authorization: Bearer ACCESS_TOKEN` header-т явуулна. Access token 30 минут,
refresh token 1 өдөр хүчинтэй. Agent-ууд refresh token ашиглан access-аа шинэчилнэ.

| Endpoint | Method | Зориулалт |
| --- | --- | --- |
| `/api/auth/login/` | POST | Username, password-аар access/refresh авах |
| `/api/auth/refresh/` | POST | Refresh token-оор access шинэчлэх |
| `/api/users/`, `/api/users/{id}/` | GET, POST / GET, PUT, PATCH, DELETE | User удирдах; өөрчлөх эрх зөвхөн admin |
| `/api/users/me/` | GET | Одоогийн хэрэглэгч |
| `/api/departments/`, `/api/departments/{id}/` | GET, POST / GET, PUT, PATCH, DELETE | Хэлтэс; өөрчлөх эрх зөвхөн admin |
| `/api/tasks/`, `/api/tasks/{id}/` | GET, POST / GET, PUT, PATCH, DELETE | Task; өөрчлөх эрх admin/manager |
| `/api/devices/enroll/` | POST | Өөрийн workstation бүртгүүлэх |
| `/api/devices/` | GET | Харах эрхтэй device-ууд |
| `/api/consents/grant/` | POST | Өөрийн monitoring consent олгох |
| `/api/consents/revoke/` | POST | Өөрийн consent цуцлах |
| `/api/consents/status/` | GET | Өөрийн consent төлөв |
| `/api/computer-activity/ingest/` | POST | Үндсэн agent-ийн application segment |
| `/api/computer-activity/` | GET | Computer activity түүх |
| `/api/activity-events/ingest/` | POST | Өөрийн camera state segment |
| `/api/activity-events/` | GET | Camera activity түүх |
| `/api/v1/activity` | POST | Өөр agent-ийн v1.0 batch; төгсгөлийн `/` байхгүй |
| `/api/scores/calculate/` | POST | Employee/date оноо тооцох буюу шинэчлэх |
| `/api/scores/dashboard/?employee_id=2&date=2026-11-05` | GET | Өдрийн score, application, camera summary |
| `/api/scores/` | GET | Харах эрхтэй онооны түүх |

List хариу нь `count`, `next`, `previous`, `results` бүтэцтэй; нэг хуудсанд 50 мөр.
`employee`, `employee_id`, `device_id` утгуудыг бодит API хариунаас авна.

Login хүсэлтийн JSON:

```json
{"username":"employee1","password":"YOUR_PASSWORD"}
```

Task үүсгэх JSON (admin/manager):

```json
{"employee":2,"title":"API integration","description":"Agent холбох","due_date":"2026-11-05","status":"TODO"}
```

Task status нь `TODO`, `IN_PROGRESS`, `DONE`. `DONE` болоход сервер `completed_at`
онооно; дахин нээхэд цэвэрлэнэ. `quality_score` нь 0–100 эсвэл null.

Computer segment-ийн JSON (тухайн employee-ийн token):

```json
{"started_at":"2026-11-05T10:00:00+08:00","duration_seconds":30,"application":"Code","category":"WORK"}
```

Category: `WORK`, `COMMUNICATION`, `BROWSER`, `OTHER`. Camera segment:

```json
{"timestamp":"2026-11-05T10:00:00+08:00","duration_seconds":30,"state":"WORKING"}
```

Camera state: `WORKING`, `PHONE`, `IDLE`, `AWAY`. Хоёр ingest endpoint-д enrollment
хариуны `device_id`-г нэмэх боломжтой; device нь нэвтэрсэн хэрэглэгчийнх байна.
`REQUIRE_MONITORING_CONSENT=true` үед өмнө нь consent grant хийсэн байх ёстой:

```json
{"policy_version":"2026-11"}
```

Оноо тооцох JSON:

```json
{"employee_id":2,"date":"2026-11-05"}
```

Admin бүх ажилтанд, manager өөрийн хэлтэст, employee өөртөө оноо тооцож болно.
Ирээдүйн өдрийн оноо тооцохгүй. Өгөгдөл өөрчлөгдвөл дахин тооцно.

## Activity хугацааны API шалгалт

Computer/camera ingest болон API-аар admin үүсгэх, засах хүсэлтэд дараах дүрэм үйлчилнэ:

- `duration_seconds` нь finite тоо, 0-ээс их, хамгийн ихдээ 3600 секунд байна.
- Computer event-ийн `started_at + duration_seconds` нь ирээдүйд байж болохгүй.
- Camera-ийн `timestamp` нь segment-ийн **дууссан цаг**; эхэлсэн цаг нь
  `timestamp - duration_seconds`. Дууссан цаг ирээдүйд байж болохгүй.
- Нэг ажилтны computer event-үүд төхөөрөмжөөс үл хамааран давхцахгүй.
  Camera нь тусдаа stream тул computer event-тэй зэрэг бүртгэгдэж болно.
- Camera uploader хугацааг 0.1 секундээр тоймлодог тул camera event хоорондын
  0.1 секунд хүртэлх rounding зөрүүг зөвшөөрнө. Computer stream-д энэ зөрүүг зөвшөөрөхгүй.
- Яг ижил event дахин ирвэл 200 буцааж, давхар мөр үүсгэхгүй. Залгаа interval-ууд зөвшөөрөгдөнө.
- Batch-ийн хугацаа ирээдүйд байж болохгүй. Нэг мөр давхцвал batch-ийн бүх шинэ мөр,
  тухайн хүсэлтээр үүсгэсэн device хамт rollback хийгдэнэ. Алдаа нь 400 байна.

Энэ шалгалт өмнө нь хадгалсан өгөгдлийг автоматаар цэвэрлэхгүй. Django admin сайт
болон CSV import нь API-аас тусдаа зам тул дээрх API шалгалтаар хамгаалагдахгүй.

## Activity agent-ийн contract ба найдвартай байдал

`activity_agent/` дотор `collector.py` нь хугацаа болон app-ийг цуглуулж,
`contract.py` batch үүсгэж шалгана. `sender.py` нь offline spool, retry, JWT refresh
хариуцна. `summary.py`, `mock_server.py` нь тусдаа туршилтын хэрэгсэл.

`POST /api/v1/activity` хүсэлт:

```json
{
  "schema_version":"1.0",
  "agent_version":"0.1.0",
  "employee_id":"employee1",
  "device_id":"dde59b7ef949f039",
  "period_start":"2026-11-05T02:00:00Z",
  "period_end":"2026-11-05T02:01:00Z",
  "active_seconds":42,
  "idle_seconds":18,
  "keyboard_events":120,
  "mouse_events":15,
  "apps":[{"name":"chrome.exe","seconds":30},{"name":"code.exe","seconds":12}]
}
```

`employee_id` нь нэвтэрсэн username эсвэл user ID-г string хэлбэрээр агуулна.
Цаг нь timezone-тай байна; agent UTC `Z` формат үүсгэдэг. Django өдрийн тайланг
`Asia/Ulaanbaatar` timezone-аар гаргана. Batch нь хамгийн ихдээ 3600 секунд,
500 app мөртэй. App секундийн нийлбэр active хугацаанаас хэтрэхгүй, rounding-ийн
2 секундийн зөрүү зөвшөөрнө. Validation бүхэлдээ амжилттай болсны дараа хадгална.

| Тохиргоо | Зориулалт |
| --- | --- |
| `api_url` | `http://127.0.0.1:8000/api/v1/activity` |
| `token_file` | `../agent/.agent_tokens.json`; зам нь config байрласан хавтаснаас |
| `employee_id` | Login хийсэн username |
| `batch_interval_seconds` | Batch илгээх давтамж; default 60 секунд |
| `idle_threshold_seconds` | Input байхгүй үед idle болох босго; default 60 секунд |
| `spool_file` | Илгээгдээгүй batch-ийн JSON Lines файл |
| `max_spool_batches` | Хадгалах batch-ийн дээд тоо; default 10000 |

Шинэ app мөр хадгалбал 201, ижил batch дахин ирж шинэ мөр үүсэхгүй бол 200.
Contract алдаа 400, JWT алдаа 401, identity/consent/device эрхийн алдаа 403.
Сүлжээний алдаа, 5xx, 408, 429 үед spool-д хадгалж дахин оролдоно. 401/403 үед
өгөгдлийг хадгалж login эсвэл consent засагдахыг хүлээнэ. Бусад 4xx алдаатай batch-ийг
log-д бичээд дахин илгээхгүй. Spool хязгаарт хүрвэл хамгийн хуучин batch-ууд хасагдана.

Agent restart хийсэн ч spool хадгалагдана. Laptop sleep-ийн 10 секундээс урт
завсрыг activity гэж тооцохгүй. Listener зогсвол main loop дахин эхлүүлнэ.
Нэг туршилтын batch илгээхдээ `python activity_agent/agent.py mock` ашиглана;
энэ нь тохируулсан бодит endpoint руу өгөгдөл бичдэгийг анхаарна.

## Нууцлал ба OS permission

Keyboard/mouse-ийн агуулга, clipboard, цонхны гарчиг, file content, screenshot-ийг
computer agent илгээхгүй. Alternative agent key/click-ийн тоог batch-д оруулдаг ч
Django adapter тэдгээрийг хадгалахгүй. Mouse coordinate нь idle илрүүлэхэд ашиглагдаж,
серверт явдаггүй. Alternative device ID нь hostname/MAC-ийн hash бөгөөд hostname
өөрөө илгээгдэхгүй. Camera API зөвхөн боловсруулсан state, хугацаа хүлээн авна.

macOS-д шаардлагатай үед System Settings → Privacy & Security хэсгийн Accessibility,
Input Monitoring болон Camera эрхийг Terminal/Python-д олгоно. Linux Wayland-д
input listener ажиллахгүй бол Xorg session ашиглана. Foreground app танихад macOS
дээр `pyobjc-framework-Cocoa` шаардлагатай байж болно.

## Асуудал шийдэх

| Асуудал | Шалгах зүйл |
| --- | --- |
| Frontend API хүрэхгүй | Django 8000 порт дээр, Vite 5173 дээр ажиллаж байгаа эсэх; `VITE_API_URL`, proxy, CORS |
| Login 401 | Username/password шалгах; agent-д `python agent/main.py --login` дахин ажиллуулах |
| Ingest 403 | Consent grant, device enabled болон username тохирч байгаа эсэх |
| Batch 400 | Log дахь validation алдаа; app секунд, period, schema version |
| ModuleNotFoundError | `.venv` идэвхтэй эсэх; тухайн хэсгийн requirements-ийг ижил Python-оор суулгасан эсэх |
| Spool томорч байна | Backend холболт, token/consent болон `activity_agent/data/agent.log` |
| Camera мэдээлэл харагдахгүй | `api_sync.enabled`, agent login/token, camera permission, single-person горим |
| Оноо хуучин байна | Зөв employee/date сонгоод «Оноо тооцох / шинэчлэх» дарах |

Agent/camera terminal-уудыг `Ctrl+C`-ээр зогсооно. Үндсэн agent-ийн pause/resume болон
OS startup сонголтуудыг `python agent/main.py --help` болон `agent/` доторх install
script-ийн `--help`-ээс харна. Startup script-үүдийг ашиглахаас өмнө тэдгээрийн
Python болон project замыг өөрийн virtual environment-тэй тааруулна.
