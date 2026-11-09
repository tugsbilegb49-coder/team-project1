# WorkTrack

React frontend, Django API, computer activity agent болон camera monitor нь нэг
`backend/` сервер, нэг database ашиглана. Root болон `backend/` доторх `manage.py`
хоёулаа ижил Django төслийг ажиллуулна.

## Нэг даралтаар асаах (macOS)

Finder-ээс төслийн хавтас дахь **Start WorkTrack.command** файлыг давхар дарна.
Энэ нь Python environment, backend dependency, npm dependency-ийг шаардлагатай үед
бэлдэж, migration хийгээд backend, frontend, онооны scheduler, computer agent-ийг хамт асаана.
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

Log-ууд `.runtime/backend.log`, `frontend.log`, `scheduler.log`, `backup.log`, `agent.log`, `camera.log` дотор байна.
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
   Хэлтсээ вебийн «Багийн гишүүд» хэсэгт үүсгэж сонгоно. Manager-д хэлтэс заавал байна.
2. Даалгавар хэсэгт идэвхтэй ажилтанд task хуваарилж, deadline, status оруулна.
   Чанарын үнэлгээг 0–100, хоёр орны нарийвчлалтай оруулаад «Үнэлгээ хадгалах» дарна.
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

## Browser website usage (Chrome / Edge)

Activity тайлангийн график нь app болон website ашигласан хугацааг тус тусад нь
харуулна. Website-ийн домэйн цуглуулахын тулд ажилтан бүр Chrome эсвэл Edge дээр
`browser_extension/` хавтсыг extension болгон суулгана:

1. `chrome://extensions` нээж Developer mode-ийг асаана.
2. **Load unpacked** сонгоод төслийн `browser_extension/` хавтсыг заана.
3. WorkTrack Website Time extension-ийн Options хэсэгт backend API хаягаа оруулж,
   ажилтны account-аар нэвтэрнэ. Нэвтрэхэд monitoring consent идэвхтэй байх ёстой.

Extension зөвхөн browser цонх фокустай, ажилтан сүүлийн 15 секундэд идэвхтэй үед
идэвхтэй tab-ын hostname, эхэлсэн цаг, үргэлжилсэн хугацааг хадгална. URL-ийн зам,
query, хуудасны агуулга, browsing history-г илгээхгүй. Extension upload бүрийн өмнө
consent төлөвийг шалгана; consent байхгүй эсвэл цуцлагдсан бол session, queue-г
цэвэрлээд бүртгэлийг зогсооно. Backend API consent-ийг default-оор заавал шалгана
(`REQUIRE_MONITORING_CONSENT=true`). Desktop agent consent-ийг 30 секунд тутам шалгаж,
цуцлагдсаныг мэдвэл local collection-оо pause хийнэ. Дахин зөвшөөрсний дараа
`python agent/main.py --resume` ажиллуулна. Гишүүн болон огноог Тайлан дээр
сонгоход app болон website-ийн хугацааны график шинэчлэгдэнэ.

Single-person camera uploader ч segment-ээ өдөр болон 3600 секундээр хуваана.
Camera timestamp нь дууссан цаг тул яг 00:00-д дууссан хэсэг өмнөх өдөрт тоологдоно.
Backend camera тайланд өмнө нь хадгалсан өдөр дамнасан мөрийн хугацааг мөн хоёр
өдөрт хувааж харуулна; database-ийн хуучин мөрийг өөрчлөхгүй. Camera tracker мөн `max_camera_gap_seconds` (default 10) хамгаалалттай. Single болон
multi-person горимд урт observation gap-ийг тооцохгүй, өмнөх хугацааг сүүлийн frame
ажигласан timestamp-тайгаар хадгална.

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
Энэ contract-ийн аппуудыг серверийн `PRODUCTIVE_APPLICATIONS` жагсаалтаар
`WORK`, browser нэрээр `BROWSER`, харилцааны аппын нэрээр `COMMUNICATION`, бусдыг
`OTHER` гэж ангилна. Idle хугацааг `Idle/OTHER`, апп нь тодорхойгүй active хугацааг
`Unattributed activity/OTHER` segment болгон хадгалж, W-ийн нийт хугацаанд оруулна.
Keyboard/mouse event тоонуудыг database-д хадгалахгүй. Mock server нь зөвхөн тусдаа
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
түүний `core` schema-г шинэ database руу автоматаар зөөхгүй. `legacy/core/` нь өмнөх
хэрэгжүүлэлтийн эх код бөгөөд үндсэн серверт ачаалагдахгүй. Доорх API заавар нь
зөвхөн одоогийн `backend/` серверт хамаарна. Хуучин `core/` endpoint болон model-ууд
одоогийн API-тай ижил биш; өмнөх эх код, зааврыг Git түүхээс харж болно.

Оноо нь `backend/scoring/services.py`-ийн дүрмийг ашиглана: T/Q/D нь task-аас,
W нь computer activity-ийн WORK харьцаанаас; computer data байхгүй үед camera
WORKING харьцаанаас гарна. Энэ дүрэм хуучин `core`-ийн дүрмээс ялгаатай.

## Онооны тодорхой дүрэм

| Үзүүлэлт | Тооцоолол |
| --- | --- |
| T | Тухайн өдөр due болсон task-уудаас тэр өдрийн эцэс гэхэд DONE болсон хувь |
| Q | Дээрх completed task бүрийн `quality_score`-ийн дундаж |
| D | Тухайн өдөр due болсон нийт task-аас deadline өдрөөсөө оройтохгүй дууссан хувь |
| W | WORK секунд / нийт computer activity секунд × 100; idle, browser, unknown хугацаа нийтэд орно |
| P | `0.4T + 0.3Q + 0.2D + 0.1W` |

Computer data байхгүй бол W нь camera-ийн WORKING / нийт camera секунд болно.
Camera fallback байгаа нь аппын W-тэй ижил хэмжигдэхүүн биш бөгөөд онооны энэ
хувилбарын сонгосон дүрэм юм. T/Q/D-д task байхгүй бол 0, activity байхгүй бол W=0.
Өгөгдөлгүй өдрийн 0 нь баталгаатай муу гүйцэтгэл гэсэн дүгнэлт биш.
P-г 0–100-д хязгаарлаж 2 оронд тоймлоно. LOW: P < 65, MEDIUM: 65 ≤ P < 85,
HIGH: P ≥ 85. Энэ нь дүрэмд суурилсан тооцоо; AI таамаглал биш.

Дууссан task-ийн completion timestamp эсвэл Q үнэлгээ дутуу бол шинэ оноо
хадгалахгүй. API 400 болон асуудалтай `task_ids` буцаана. 0 гэсэн чанарын үнэлгээ
бол зөв утга; null-аас ялгаатай. Хэрэв өмнөх score байсан бол түүнийг өөрчлөхгүй;
өмнөх `calculated_at`-тай тооцоо хэвээр үлдэнэ. Үнэлгээг нөхөөд дахин тооцно.
Дараагийн өдөр дууссан task нь өмнөх өдрийн T/Q/D-г буцааж нэмэгдүүлэхгүй.
Өдрийн CLI/scheduler нь үнэлгээ дутуу ажилтныг log-д мэдээлээд бусдын тооцоог үргэлжлүүлнэ.

Alternative agent-ийн server allowlist-ийг `backend/.env`-д тохируулна:

```dotenv
PRODUCTIVE_APPLICATIONS=Visual Studio Code,Code,PyCharm,WINWORD,Microsoft Word
```

App нэрийн том/жижиг үсэг, `.exe`, `.app` өргөтгөлийг normalize хийнэ. `code.exe`
нь `Code`-той таарна. Safari/Chrome нь default WORK биш. Ажлын browser-ийг WORK
болгох шаардлагатай бол нэрийг жагсаалтад ил тод нэмнэ. Серверээ дахин асааж хэрэглэнэ.
Энэ жагсаалт alternative batch-д үйлчилнэ; үндсэн agent-ийн ангиллыг
`agent/config.json` дахь `productive_apps` удирдана.

Өмнө хадгалсан ангиллыг автоматаар өөрчлөхгүй. Accepted batch-ийг replay хийхэд
allowlist өөрчлөгдсөн байсан ч өмнөх category хадгалагдана. Хуучин `OTHER` мөрүүдийг
дахин ангилах migration энэ өөрчлөлтөд ороогүй. Шинэ дүрмээр оноогоо харахын тулд
өгөгдөл/чанарын үнэлгээгээ шалгаад score-оо дахин тооцно.

## Оноо автоматаар шинэчлэх

`Start WorkTrack.command` launcher нь backend/frontend-тэй хамт score scheduler
асаана. `--web-only` горимд ч scheduler ажиллана. Асаах үед болон дараа нь
**60 секунд тутам**, `Asia/Ulaanbaatar` timezone-оор **өнөөдөр ба өчигдрийн**
идэвхтэй хэрэглэгчдийн оноог дахин тооцно. Ингэснээр agent-ийн шинэ activity,
шөнө дунд дамнасан бүртгэл, хоцорч ирсэн queue, нөхөж оруулсан quality үнэлгээ
дараагийн мөчлөгт тусна. Ижил employee/date score-ийг шинэчилнэ, давхар score үүсгэхгүй.

Чанарын үнэлгээ дутуу ажилтныг log-д мэдээлээд алгасна; бусдыг үргэлжлүүлнэ.
Дараагийн мөчлөгт дахин шалгана. Database түр завгүй эсвэл бэлэн биш үед алдааг
log-д бичээд дараагийн мөчлөгт дахин оролдоно. Log: `.runtime/scheduler.log`.
Launcher-ийг Ctrl+C-ээр зогсооход өөрийн асаасан scheduler мөн зогсоно.

Гараар серверүүдээ асаадаг бол scheduler-ийг тусдаа terminal-д ажиллуулна:

```bash
python manage.py run_score_scheduler                 # Default: 60 секунд
python manage.py run_score_scheduler --interval 120  # 120 секунд тутам
python manage.py run_score_scheduler --once          # Хоёр өдрийг нэг удаа тооцоод гарах
```

Docker Compose-ийн scheduler мөн `--interval 60` ашиглана. Хуучин `--hour` болон
`--minute` сонголтыг шинэчилж `--interval` болгосон. Давтамж 10–3600 секунд байна.

Хоёроос олон хоногийн өмнөх өгөгдөл өөрчлөгдвөл тухайн өдрийг тусад нь дахин тооцно:

```bash
python manage.py calculate_daily_scores --date 2026-11-01
```

Компьютер унтарсан эсвэл launcher зогссон үед локал scheduler ажиллахгүй. Дахин
асаахад зөвхөн өнөөдөр/өчигдрийг нөхөж тооцно; бүх хуучин өдрийг автоматаар нөхөхгүй.
Вебийн нээлттэй хуудас автоматаар дахин хүсэлт явуулдаг болоогүй: шинэ оноог харахдаа
Dashboard-ийн «Шинэчлэх» дарна. «Оноо тооцох / шинэчлэх» товч гараар шууд тооцох
боломж хэвээр байна.

## Backup, restore болон хадгалалтын хязгаар

### Database backup

```bash
python manage.py backup_database
python manage.py backup_database --output backend/backups/my-backup.sqlite3
```

Default файл нь `backend/backups/database-TIMESTAMP-RANDOM.sqlite3` (SQLite)
эсвэл `.dump` (PostgreSQL). Existing output файлыг дарж бичихгүй. Backup файл
0600 permission-тэй бөгөөд `backups/`, `*.dump`, `*.sqlite3` нь Git-д орохгүй.
Database дотор account/password hash, token blacklist, task болон activity байдаг тул
backup-ийг хувийн, найдвартай хадгалалт руу өөрөө хуулна. Энэ команд backup-ийг
автоматаар cloud руу upload хийхгүй. Launcher одоо өдөр тутмын backup scheduler
хамт асаана; доорх автомат backup хэсгийг үзнэ үү.

SQLite нь online backup API ашиглаж WAL дахь committed өгөгдлийг хамруулна.
PostgreSQL нь custom-format `pg_dump`, restore-д `pg_restore` ашиглана. Эдгээр CLI
суусан, server-тэй нийцэх хувилбартай байх ёстой. Нууц үгийг command argument-д
бичихгүй; subprocess environment-оор дамжуулна. 2026-11-06-нд PostgreSQL 17.11-ийн тусдаа түр cluster дээр бодит backup/restore,
safety backup-ийг өөр database-д сэргээх туршилт амжилттай хийгдсэн.

### Restore

Эхлээд файлыг өөрчлөлтгүй шалгана:

```bash
python manage.py restore_database backend/backups/my-backup.sqlite3
```

Жинхэнэ restore хийхийн **өмнө launcher, тусдаа backend/scheduler, agent/camera-аа
зогсооно**. Ижил project/schema-гийн backup ашиглана. Дараа нь:

```bash
python manage.py restore_database backend/backups/my-backup.sqlite3 --apply --confirm-stopped
```

`--confirm-stopped` нь process-уудыг автоматаар унтраахгүй; өөрөө зогсоосныг
баталж өгч буй flag. Restore-оос өмнө одоогийн database-ийн safety backup-ийг
`backend/backups/` дотор үүсгэнэ. SQLite integrity/schema шалгалт хийж, live database
файлыг өөрт нь restore хийхийг хориглоно. PostgreSQL restore нь single transaction
ашиглана. Restore амжилттай бол launcher-аа дахин асаана; сэргээгдсэн account,
password, token төлөв backup авсан үеийнх болно. Локал agent queue нь тусдаа файл
тул database restore түүнийг буцааж сэргээхгүй.

### Хуучин activity цэвэрлэх

```bash
python manage.py cleanup_activity --days 90          # Зөвхөн тоо, cutoff харуулна
python manage.py backup_database                     # Эхлээд backup авна
python manage.py cleanup_activity --days 90 --apply  # Жинхэнэ устгал
```

Default хадгалалт 90 хоног (`ACTIVITY_RETENTION_DAYS`), minimum 1 хоног. Баталгаатай
өдрийн backup-ийн дараа `ACTIVITY_RETENTION_AUTO=true` үед хуучин camera, computer,
website activity болон тухайн өдрийн оноонууд автоматаар цэвэрлэгдэнэ. Camera-ийн дууссан timestamp,
computer interval-ийн дууссан цагаар cutoff-оос бүхэлдээ өмнөх мөрийг сонгоно.
Cutoff дамнасан segment-ийг хадгална. User, task, consent, device болон audit
бүртгэлийг үлдээнэ. Автомат цэвэрлэгээг унтраах бол `ACTIVITY_RETENTION_AUTO=false`
болгоно; гараар ажиллуулах үед `--apply` байхгүй бол юу ч устгахгүй. Local daily backup-аас
`BACKUP_KEEP` (default 7) ширхэг snapshot хадгална; тэдгээрт хуучин мөр нэмэлт хугацаанд
байж болно. Optional external backup хуулбаруудыг автоматаар устгахгүй.
SQLite файл logical delete хийсний дараа шууд жижигрэх албагүй.

Цэвэрлэсэн хуучин өдрийн score-ийг дараа нь дахин тооцвол activity өгөгдөл нь
байхгүй тул W өөрчлөгдөж болно. Хуучин тайлангаа дахин тооцох шаардлагатай бол
retention хугацаагаа уртасгах эсвэл backup-аас тусдаа орчинд шалгана.

### Offline queue хязгаар

Үндсэн agent: `agent/config.json` дахь `max_queue_events` (default 10000),
`max_queue_bytes` (default 10485760 буюу 10 MiB). Camera-д ижил утгууд
`config.yaml`-ийн `api_sync` дотор байна. Alternative agent-ийн config нь
`max_spool_batches=10000`, `max_spool_bytes=10485760` ашиглана.

Queue дүүрвэл **хамгийн шинэ бүртгэлүүдийг хадгалж, хуучин бүртгэлүүдийг хасна**;
ганц мөр нь byte хязгаараас том бол тэр мөрийг алгасна. Хасагдсан тоог log-д
мэдээлнэ. Хязгаараас хэтэрсэн offline хугацааны бүх өгөгдөл хадгалагдана гэсэн
баталгаа байхгүй. Хязгаарыг нэмэх эсвэл backend холболтоо сэргээх шаардлагатай.
Queue нь UTF-8 файлд бичигдэх бодит хэмжээгээр хязгаарлагдана; temp файл бичих
зуур дискэнд нэмэлт зай хэрэгтэй. Agent upload хийж байх үед queue дүүрсэн ч
хараахан илгээгдээгүй шинэ мөрийг андуурч устгахгүй.

## Үлдсэн ажлуудын нэмэлт хэрэгслүүд

### Хуучин backend-ийн архив

Өмнөх `core/` source нь `legacy/core/` дотор бүрэн хадгалагдсан. Үндсэн Django
`INSTALLED_APPS`-д орохгүй, хуучин root database-ийг нүүлгээгүй. Өдөр тутмын өөрчлөлтөө
`backend/` дээр хийнэ. `pytest.ini` нь root pytest-ийг `tests/` дээр ажиллуулж,
архивын Django tests-ийг санамсаргүй импортлохоос хамгаална. Backend tests-ийг
`python manage.py test users workforce activity scoring` гэж тусад нь ажиллуулна.

### Хуучин activity шалгах, ангиллыг засах

```bash
python manage.py review_activity --limit 100           # Preview, database өөрчлөхгүй
python manage.py review_activity --employee 2          # Нэг ажилтан
python manage.py backup_database
python manage.py review_activity --apply               # Зөвхөн aggregate category засна
```

Invalid duration, ирээдүйн болон давхардсан interval-ийг ID-тай нь мэдээлнэ.
Зөвхөн `activity_agent` platform, `activity-agent-` device prefix-тэй aggregate
record-ийн category-г server allowlist-аар засна. `Idle`, unknown хугацаа болон
үндсэн agent-ийн ангиллыг өөрчлөхгүй. Буруу timestamp/duration-ийг тааж засахгүй,
ямар ч мөр устгахгүй. Тэдгээрийг эх сурвалжтай тулгаж гараар шалгана. Ангилал
зассан хуучин өдрүүдийн score-ийг тусад нь дахин тооцно.

### Өдөр тутмын автомат backup

Launcher нь score scheduler-ээс тусдаа `run_backup_scheduler` процесс асаадаг.
Асаах үед болон цаг тутам шалгаж, Улаанбаатарын нэг өдөрт нэг `daily-*.sqlite3`
эсвэл `daily-*.dump` үүсгэнэ. Default-аар **сүүлийн 7 daily backup** үлдээнэ.
Гараар авсан `database-*`, restore-ийн safety backup, custom нэртэй файлуудыг
retention устгахгүй. Backup байхгүй/эвдэрсэн эсвэл copy диск олдохгүй үед log-д
алдаа мэдээлээд дараагийн цагт retry хийнэ; copy амжилтгүй бол local retention хийхгүй.

```bash
python manage.py run_backup_scheduler --once
python manage.py backup_cycle --keep 14
python manage.py backup_cycle --copy-dir /Volumes/MyBackup/WorkTrack --keep 7
```

Copy directory урьдчилж үүссэн, диск mount болсон байх ёстой. Хоёр дахь хуулбарыг
SHA-256 checksum-аар шалгадаг. `BACKUP_KEEP`, `BACKUP_COPY_DIR` environment-оор
scheduler-ийг тохируулна. Docker-д энэ disk path-ийг backup container дотор volume
болгон тусад нь mount хийх шаардлагатай. External хуулбаруудыг автоматаар prune
хийхгүй. Log: `.runtime/backup.log`. Launcher унтарсан үед автомат backup ажиллахгүй.

### Олон төхөөрөмжийн урт HTTP soak ба camera үнэлгээ

```bash
python verify_soak.py --seconds 60 --devices 3
python verify_soak.py --seconds 28800 --devices 10     # 8 цагийн synthetic HTTP soak
```

Үргэлжлэх хугацааг хурдасгахгүй: 28800 нь бодит 8 цаг ажиллана. Түр SQLite test
DB, бодит Django HTTP сервер дээр synthetic device-ууд сегмент илгээж, replay,
JWT refresh, saved login дахин ашиглах, нийт record count-ийг шалгана. Үндсэн
user/database, camera болон foreground app capture ашиглахгүй. Report нь
`.runtime/soak-report.json`. Process тасарвал report-ийг амжилттай гэж бичихгүй.

60 секунд / 3 device туршилт: 180 segment, дундаж HTTP ~8 ms, max ~50 ms,
давхар record үүсээгүй. Энэ нь 8 цагийн бодит төхөөрөмжийн баталгаа биш;
8 цагийн run болон олон бодит workstation-ийн тестийг хараахан ажиллуулаагүй.

Camera-ийн accuracy-д хүний баталгаажуулсан label хэрэгтэй. CSV-ийн жишээ:

```csv
expected,predicted
WORKING,WORKING
PHONE,IDLE
```

```bash
python evaluate_camera.py /path/to/manually-labeled.csv
```

Accuracy, state бүрийн precision/recall, confusion matrix гаргана. Label байхгүй
state-ийн metric нь null; бодит annotation байхгүй үед accuracy-г зохиож мэдээлэхгүй.
Нэг frame inference болон fake-clock gap тест нь accuracy судалгаа биш.

### Локал deployment бэлтгэл

`compose.production.yml` нь **backend API**-д зориулсан template; React build
оруулдаггүй. PostgreSQL 17, multi-worker Gunicorn, Caddy HTTPS proxy, score болон
backup scheduler агуулна. Backend/database host port нээхгүй; proxy л 80/443 нээнэ.
Database cache нь worker-уудын login throttle state-ийг хуваалцана; entrypoint
`createcachetable` ажиллуулдаг. `/api/health/` нь DB/cache round-trip шалгаж 200/503
буцаана. Process crash үед restart policy үйлчилнэ; unhealthy төлөв нь өөрөө
container restart хийх баталгаа биш. JSON logs нь 10 MiB × 3 файлаар эргэнэ.

```bash
cp deploy/production.env.example deploy/production.env
# Domain, private secret, password, CORS origin-оо өөрийн утгаар засна.
docker compose --env-file deploy/production.env -f compose.production.yml config
docker compose --env-file deploy/production.env -f compose.production.yml up -d --build
docker compose --env-file deploy/production.env -f compose.production.yml logs --tail=100 backend scheduler backup proxy
```

Бодит HTTPS-д domain DNS сервер рүү заасан, 80/443 хүрдэг байх шаардлагатай.
`DJANGO_DEBUG=false` үед placeholder/богино SECRET_KEY-г сервер хүлээн авахгүй.
`TRUST_PROXY_HEADERS` зөвхөн backend шууд интернетэд нээлтгүй үед хэрэглэнэ.
Trusted proxy IP нь template-ийн `172.30.0.2`; subnet өөрчилбөл IP ба trusted setting-ээ
хамт өөрчилнө. Caddy хэрэглэгчийн forwarded IP header-ийг overwrite хийдэг.
`CORS_ALLOWED_ORIGINS`-д зөвхөн зөвшөөрсөн frontend origin-уудыг бичнэ.
Production env болон backup-ууд image/Git-д орохгүй.

Энэ Mac дээр YAML/config, health/proxy tests, бодит 2-worker Gunicorn болон
PostgreSQL shared cache-ийг шалгасан. Docker/Caddy container build, бодит domain-ийн
TLS certificate, public deployment, external monitoring/alert-ийг ажиллуулаагүй.
Энэ хэсэг хэрэглэгчийн сонгосон **локал бэлтгэл**, public deployment биш.

Тохиргооны лавлагаа: [Django database cache](https://docs.djangoproject.com/en/5.2/topics/cache/#database-caching),
[Caddy reverse proxy](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy).

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
| `/api/auth/logout/` | POST | Өөрийн refresh token-ийг хүчингүй болгох; access authentication шаардлагатай |
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
| `/api/scores/summary/?start_date=2026-11-01&end_date=2026-11-07&department_id=2` | GET | 31 хүртэл хоногийн нэгтгэл; ажилтан эсвэл эрхтэй хэлтэс сонгоно |
| `/api/audit-logs/` | GET | Admin-д ажилтан, хэлтэс, consent-ийн өөрчлөлтийн түүх |
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
`REQUIRE_MONITORING_CONSENT=true` (default) үед өмнө нь consent grant хийсэн байх ёстой:

```json
{"policy_version":"2026-11"}
```

Оноо тооцох JSON:

```json
{"employee_id":2,"date":"2026-11-05"}
```

Admin бүх ажилтанд, manager өөрийн хэлтэст, employee өөртөө оноо тооцож болно.
Ирээдүйн өдрийн оноо тооцохгүй. Өгөгдөл өөрчлөгдвөл дахин тооцно.

## Frontend-ийн regression шалгалт

```bash
npm run test                         # API/session unit tests
npm run lint
npm run build
npx playwright install chromium      # Browser test runtime, нэг удаа
npm run test:e2e                      # Mock API-тай бодит browser regression
python verify_frontend.py            # Шинэ түр DB + бодит Django + browser smoke
```

Browser regression нь хадгалалтын үеийн task draft, manager-ийн хэлтэс,
идэвхгүй assignee, quality validation/save, report selection болон late response,
server logout, offline startup/retry, expired session, 320px chart overflow-ийг
шалгана. Playwright нь тусдаа Vite порт ашиглаж, үндсэн backend руу test өгөгдөл
бичихгүй. `verify_frontend.py` нь түр SQLite DB/server үүсгэж login → department →
manager → task → quality → deactivate → logout/refresh revocation урсгалыг
бодитоор ажиллуулаад бүх түр process/file-аа цэвэрлэнэ.

Default browser suite-д live smoke case алгасагдана; түүнийг `verify_frontend.py`-аар
ажиллуулна. Test artifact нь `.runtime/frontend-e2e/` дотор, Git-д орохгүй.
Өөр ажилтан/өдөр сонгоход хуучин тайлан шууд нуугдаж, шинэ хүсэлтийн хариуг л харуулна.
Хадгалалтын үед task form нуухгүй, талбаруудыг disable хийж draft-ийг хадгална.

## Бодит орчны шалгалт

2026-11-06-нд энэ Mac дээр хийсэн шалгалтууд:

| Шалгалт | Үр дүн |
| --- | --- |
| macOS foreground app | Safari → Code гэж бодитоор шилжүүлэхэд хоёул зөв танигдсан |
| Idle timer | OS-оос idle секунд уншигдсан |
| Camera capture | Webcam нээгдэж 1920×1080 frame ирсэн |
| Camera → YOLO → state | Бодит нэг frame боловсруулж хүчинтэй state буцаасан; зураг хадгалаагүй/upload хийгээгүй |
| Primary agent offline → recovery | Бодит TCP connection-refused үед queue хадгалж, Django HTTP сервер сэргэхэд илгээсэн; replay давхар хугацаа үүсгээгүй |
| Tracker/association/gaze | 17 unit тест амжилттай; энэ нь бодит detection accuracy-ийн үнэлгээ биш |
| Sleep/resume | Хэрэглэгч Mac-аа унтуулаад сэрээсэн; 10.17 секундийн observation gap илэрч app time-д ороогүй |
| PostgreSQL 17.11 | Migration, shared cache, 2-worker Gunicorn болон 70 backend test case шалгасан; opt-in soak 1 case тусдаа ажилласан |
| PostgreSQL concurrency | Давхардсан хоёр хүсэлтээс нэг нь 201, нөгөө нь 400; ижил replay нь 201/200, нэг мөр хадгалсан |
| PostgreSQL backup/restore | `pg_dump` → өөрчлөлт оруулах → `pg_restore` → өөрчлөлт буцсан; safety dump-ийг өөр database-д мөн сэргээсэн |

Offline/recovery туршилт нь **локал endpoint хүрэхгүй болох** нөхцөл үүсгэсэн;
Mac-ийн Wi-Fi-г унтраагаагүй. Django-ийн түр test database ашигласан, үндсэн
хэрэглэгчийн database руу test event нэмээгүй. YOLO-ийн стандарт `yolov8n.pt` weight
локал татагдсан бөгөөд Git-д орохгүй.

Дахин шалгах integration тест:

```bash
python manage.py test workforce.tests.LiveUploaderTests.test_primary_agent_offline_queue_recovers_against_real_django
python -m pytest tests/test_activity_tracker.py tests/test_association.py tests/test_gaze.py -q
```

Sleep/resume-ийг өөрөө туршихдаа launcher-аа асааж, VS Code дээр хэдэн секунд
ажиллаад Apple → Sleep сонгон 20 секундээс удаан хүлээнэ. Сэрээсний дараа дахин
хэдэн секунд ажиллаад `.runtime/agent.log` дахь `Sleep/clock gap skipped` мөрийг
шалгана. Dashboard-ийн нийт app хугацаанд унтсан 20 секунд нэмэгдээгүй байх ёстой.
Туршилтын өмнөх/дараах хугацааг ялгаж үзнэ; нийт өмнөх бүртгэлийг нойртой андуурахгүй.

PostgreSQL-ийн тестэд тусдаа тестийн server/database болон test database үүсгэх
эрхтэй хэрэглэгч хэрэгтэй. `backend/.env`-ийн `POSTGRES_*`-ийг тухайн орчинд
тохируулж `python manage.py test users workforce activity scoring` ажиллуулна.
SQLite дээрх амжилт PostgreSQL row locking, migration, backup/restore-ийг дангаараа
батлахгүй. Энэ Mac дээр PostgreSQL 17 суулгаж, зөвхөн private Unix socket ашигласан
түр cluster дээр дээрх тестүүдийг хийсэн. Байнгын service асаагаагүй, үндсэн
SQLite database болон `backend/.env`-ийг PostgreSQL рүү өөрчлөөгүй.

Дахин тусгаарласан PostgreSQL шалгалт хийх:

```bash
python verify_postgresql.py
# PATH-д PostgreSQL tool байхгүй бол:
python verify_postgresql.py --pg-bin /opt/homebrew/opt/postgresql@17/bin
```

Энэ script нь түр cluster/database үүсгэж, migrations, нийт backend тест,
concurrent ingest, backup/restore шалгаад серверээ зогсоож cluster-ээ устгана.
Үндсэн database руу холбогдохгүй. macOS/Linux дээр локал PostgreSQL binary шаардана.
Товч үр дүн `.runtime/postgresql-verification.json` файлд үлдэнэ.

Бодит sleep хэмжилт хийх команд:

```bash
python verify_sleep.py
```

READY гарсны дараа Apple → Sleep сонгоод 20 секунд хүлээн сэрээнэ. Script нь
үндсэн agent-ийн бодит sampler-ийг ашиглах боловч HTTP uploader-ийг diagnostic
recorder-оор сольдог тул database руу бичихгүй. Сэрсний дараа 8 секунд ажиглаад
дуусна. Default дээд хугацаа 300 секунд. Завсар илрээгүй бол **inconclusive**,
илэрсэн завсрыг app time-д оруулаагүй бол **passed** гарна. Үр дүн
`.runtime/sleep-resume-test.json` файлд үлдэнэ.

## Login хамгаалалт ба logout

`POST /api/auth/login/` нь амжилттай болон амжилтгүй оролдлогыг хамтад нь хязгаарлана:

- Нэг IP хаягаас **10 оролдлого/минут**.
- Нэг username-д бүх IP нийлээд **20 оролдлого/минут**.
- Хязгаар давбал **429** болон хэдэн секунд хүлээхийг заасан `Retry-After` header буцаана.
  Энэ нь account-ийг байнга lock хийхгүй; цонх өнгөрөхөд дахин нэвтэрч болно.

Username cache key-д plain text-ээр хадгалагдахгүй. Хэрэглэгчийн илгээсэн
`X-Forwarded-For`-д шууд итгэхгүй; local deployment `REMOTE_ADDR` ашиглана.
Default Django cache нь process-local тул олон worker/server дээр shared cache
болон trusted reverse proxy-ийн IP тохиргоо шаардлагатай. DRF throttle нь local
түвшний хамгаалалт; зэрэгцсэн request-ийн яг атомик hard limit биш.

Logout хүсэлтэд өөрийн access token-ийг Authorization header-т, refresh token-ийг JSON-д өгнө:

```json
{"refresh":"YOUR_REFRESH_TOKEN"}
```

Амжилттай бол **204**. Refresh token blacklist-д орж, дахин refresh хийхэд 401 болно.
Өөр хэрэглэгчийн refresh-ийг хүчингүй болгох хүсэлт 403. Logout нь тухайн нэг
refresh token-д үйлчилнэ; бусад төхөөрөмжийн өөр login session-ийг автоматаар хаахгүй.
Өмнө олгосон **access token 30 минутын хугацаагаа дуустал хүчинтэй** хэвээр байна.
Refresh rotation-ийг асаагаагүй: agent/camera нэг refresh файл ашигладаг урсгалыг хадгалсан.

Үндсэн agent-аас logout хийх:

```bash
python agent/main.py --logout
```

Энэ нь collection-ийг pause хийж, сервер дээр refresh-ийг revoke хийгээд локал token
файлыг устгана. Сервер хүрэхгүй бол collection paused хэвээр, token файлыг retry-д
хадгална. Logout хийсний дараа camera болон alternative agent мөн shared login-гүй
болно. Дахин ашиглахдаа `--login`, дараа нь `--resume` хийнэ; offline queue-г устгахгүй.

Шинэ blacklist хүснэгтүүдийг үүсгэхийн тулд `python manage.py migrate` ажиллуулна
(launcher үүнийг өөрөө хийдэг). Хугацаа дууссан token бүртгэлийг цэвэрлэх команд:

```bash
python manage.py flushexpiredtokens
```

Frontend-ийн «Гарах» товч одоо logout API-г дуудаж refresh token-ийг revoke хийсний
дараа browser-ийн session-ийг цэвэрлэнэ. Серверийн түр алдаанд session-ийг хадгалж,
алдаа харуулан retry хийх боломж үлдээнэ. Refresh 400/401 үед login руу буцна;
refresh 500/503, network failure үед token-ийг устгахгүй. Logout дээр refresh нь
аль хэдийн хүчингүй/хугацаа дууссан гэсэн 400 ирвэл local session-оос гарна. Зэрэгцсэн expired
хүсэлтүүд нэг refresh хүсэлт хуваалцана. Logout-ийн өмнөх data/login/refresh
хариу шинэ session эсвэл UI-г сэргээхгүй.

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
