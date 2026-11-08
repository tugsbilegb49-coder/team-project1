# WorkTrack — Админы гарын авлага

Энгийн хэрэглээ: [README](../README.md). Хөгжүүлэлт: [developer.md](developer.md).

## Agent төлөв, тайлан, өөрчлөлтийн түүх

- **Agent төлөв**: account, төхөөрөмж, computer/camera-ийн online, pause, offline
  төлөв, сүүлийн холболт/илгээлт, хүлээгдэж буй queue, алдааны төрлийг харуулна.
  Үндсэн agent болон camera 30 секунд тутам heartbeat илгээнэ; 90 секундээс
  хуучирвал offline болно. Огт heartbeat ирээгүй төхөөрөмжийг ажиллаж байна гэж
  таамаглахгүй. Хуудсыг 30 секунд тутам шинэчилнэ. Өөр хувилбарын
  `activity_agent/` collector өөрийн heartbeat илгээдэггүй; үндсэн launcher ашиглана.
- **Тайлан → Тайлан татах**: эхлэх/дуусах өдөр, ажилтан, CSV эсвэл Excel (.xlsx)
  сонгоно. Admin бүх, manager хэлтсийн, employee өөрийн өгөгдлийг экспортолно.
  Нэг хүсэлтэд хамгийн ихдээ 366 өдөр, 50,000 мөр. Хадгалсан score байхгүй бол
  нүдийг хоосон үлдээнэ; автоматаар оноо зохиохгүй. Computer/work секунд болон
  presence sample тоо тусдаа баганатай; presence-ийг ажилласан хугацаа гэж үзэхгүй.
  Spreadsheet formula болж ажиллаж болох хэрэглэгчийн нэрийг text болгон хамгаална.
- **Өөрчлөлтийн түүх**: task, чанарын үнэлгээ, хэрэглэгчийн эрх/идэвх, consent,
  monitoring тохиргоо, тайлан экспортын actor/time болон зөвшөөрсөн талбаруудыг
  хадгална. API болон Django admin-ийн task/user өөрчлөлтүүд ижил түүхэнд орно.
  Нууц үг, password hash, token хадгалахгүй; history API нь зөвхөн унших эрхтэй.
- **Мэдэгдэл**: хугацаа хэтэрсэн/өнөөдөр дуусах task, offline agent, upload алдаа,
  queue хүлээгдэж байгааг веб дотор харуулна. Асуудал шийдэгдмэгц дараагийн
  шинэчлэлтээр арилна. Email болон гаднын чат руу илгээхгүй.
- **Тохиргоо** (зөвхөн admin): ажилд тооцох апп, camera confidence threshold,
  local CSV-ийн хэмжээ/backup/хоног, database activity хадгалах хоногийг удирдана.
  Agent дараагийн амжилттай холболтоор өөрчлөлтийг авна; сүлжээ тасарвал ажиллаж буй
  process сүүлийн авсан тохиргоогоо хэрэглэнэ. Нэгэн зэрэг зассан хуучин хувилбарыг
  409 хариугаар буцааж, дахин уншихыг шаардана. Local CSV-д өөрчлөлт хэрэгжихэд
  шинэ хязгаарт багтах хуучин generated log-ууд цэвэрлэгдэж болно.

Автомат database цэвэрлэгээ эхэндээ **унтраалттай**. Admin үүнийг тусад нь сонгож
хадгалсан үед launcher-ийн backup scheduler амжилттай backup авсны дараа л
хуучин activity-г устгана. Доорх backup/retention хэсгийг үзнэ үү.

## Database ба хуучин backend

SQLite default файл: `backend/db.sqlite3`. PostgreSQL-д `backend/.env` дахь
`POSTGRES_*` утгуудыг тохируулаад migrate хийнэ. Хуучин `core` backend-ийн хоосон root
`db.sqlite3` (зөвхөн Django-ийн дотоод хүснэгттэй, хэрэглэгчийн мэдээлэлгүй) устгагдсан. `legacy/core/` нь өмнөх
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
python manage.py cleanup_activity --days 90 --apply --backup  # Backup шалгаад устгана
```

Default хадгалалт төв тохиргооноос (анх 90 хоног), minimum 1 хоног. Camera-ийн дууссан timestamp,
computer interval-ийн дууссан цагаар cutoff-оос бүхэлдээ өмнөх мөрийг сонгоно.
Cutoff дамнасан segment-ийг хадгална. User, task, consent, device болон хадгалсан
score-уудыг устгахгүй. `--apply` байхгүй үед юу ч устгахгүй. Автомат горим зөвхөн
admin-ийн opt-in тохиргоогоор асна. Устгалын сонголтод тухайн үеийн ID хязгаар
ашиглаж, backup хүлээх зуур шинээр ирсэн хуучин timestamp-тай мөрийг хамруулахгүй.
`--backup` нь устгахаас яг өмнө шинэ backup үүсгэж шалгана; алдаа гарвал устгахгүй.
Автомат горим үргэлж энэ хамгаалалттай. `retention-*.sqlite3/.dump` generated safety
backup-аас хамгийн сүүлийн 7-г хадгална; daily/manual backup-д хүрэхгүй.
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

Үндсэн agent болон camera uploader-ийн event endpoint 400/409/413/422 буцаавал
тухайн мөрийг queue-тай ижил хавтасны `*.rejected.json` файлд тусгаарлаж,
дараагийн мөрийг илгээнэ. Тусгаарласан файл хамгийн сүүлийн 1000 мөр, 1 MiB
хязгаартай; timestamp, HTTP status, event хадгална. Түүнийг шалгаж өгөгдлийн
шалтгааныг засна. Auth/refresh алдаа, 404, 408, 429, 5xx болон сүлжээний алдаанд
queue-г хадгалж дараа дахин оролдоно. Тусгаарласан файлыг бичиж чадахгүй бол
эх мөрийг queue-д үлдээнэ.

Camera segment-ийг эхлээд дискэнд хадгалж, HTTP upload-ийг тусдаа thread хийнэ.
Backend удаашрахад frame loop сүлжээ хүлээхгүй. Зогсоохдоо upload-д 5 секунд
хүлээж, үлдсэнийг дараагийн асаалтад илгээнэ. Python integration-д
`uploader.flush(timeout=5)`-аар хүлээж, `uploader.close()`-оор worker-ийг хаана.

Үндсэн agent, camera, alternative agent нь JWT файлыг process хоорондын lock,
давтагдахгүй temp файл, atomic replace ашиглан бичнэ. Refresh-ийн хариу хожуу
ирэхэд шинэ login-ийг дарах эсвэл logout хийсэн login-ийг сэргээхгүй.

Queue/spool нь API origin болон JWT user ID-аас гаргасан hash нэрээр account бүрт
тусдаа хадгалагдана. Ижил account дахин нэвтрэх/refresh хийхэд өмнөх queue үргэлжилнэ;
өөр account-ийн мөрийг авахгүй. Ажиллаж буй collector-ийн login солигдвол зогсоож,
тухайн account-ийн queue-г хадгална. Account солихдоо agent/camera-аа эхлээд зогсоож,
шинээр login хийгээд дахин асаана. Хуучин account тодорхойгүй bare queue болон
`unverified` файл автоматаар одоогийн хэрэглэгчид оноогдохгүй. Файлыг хадгалж,
эзэмшигчийг тусад нь шалгана; зүгээр нэрийг нь солиод upload хийж болохгүй.

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

**Хоёр дахь хуулбар.** Сервер эвдэрвэл backup хамт алга болохгүйн тулд вебийн
**Тохиргоо → Сервер ба backup** хэсэгт серверийн компьютер дээрх өөр хавтсыг (USB диск,
сүлжээний хавтас, Google Drive / OneDrive-ийн синк хийдэг хавтас) бичнэ. Хавтас байгаа,
бичих эрхтэй эсэхийг хадгалахдаа шалгана. Серверийн `BACKUP_COPY_DIR` тохиргоо байвал
тэр нь давуу эрхтэй (Docker). Хуулбарыг SHA-256-аар шалгаж, тэнд сүүлийн 30-ыг
(`BACKUP_COPY_KEEP`) үлдээнэ; өөр нэртэй файлд хүрэхгүй. Copy диск олдохгүй бол local
retention хийхгүй.

**Анхааруулга.** Сүүлийн оролдлого амжилтгүй болсон, эсвэл 36 цагаас дээш амжилттай backup
болоогүй бол админы **Мэдэгдэл**-д гарна. Үр дүн `backups/status.json`-д хадгалагдана.
`BACKUP_KEEP` нь local хуулбарын тоо. Docker-д copy диск-ийг backup container дотор volume
болгон mount хийнэ. Log: `.runtime/backup.log`. Launcher унтарсан үед автомат backup
ажиллахгүй (оффисын серверт «Компьютер асахад WorkTrack-ийг автоматаар асаах»-ыг асаана).

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

### Багийн горимын бүтэц

Ажилтны компьютер (installer-ийн апп эсвэл `worktrack.py --team`) локал database, сервер
асаахгүй. `desktop/gateway.py` нь `127.0.0.1:5173` дээр бэлэн вэб хуудсыг (dist/) өгч, `/api/...`-г
төв сервер рүү, `/desktop/...`-г локал удирдлага (8766) руу дамжуулна. Тиймээс төв серверт CORS
тохиргоо хэрэггүй. Серверийн хаяг `<WORKTRACK_HOME>/.runtime/server.json`-д хадгалагдана.
Суулгасан аппын өгөгдөл: Windows `%LOCALAPPDATA%\WorkTrack`, macOS
`~/Library/Application Support/WorkTrack`.

Оффисын сервер (`worktrack.py --share`) нь Django-г зөвхөн `127.0.0.1:8000` дээр
`DEBUG=false`-оор ажиллуулна. Оффисын сүлжээнд `desktop/tls.py`-ийн HTTPS front end
`0.0.0.0:8443` дээр сонсож, Django руу дамжуулна (`X-Forwarded-For`-оор компьютер бүрийн
хаягийг өгдөг тул login throttle хүн бүрт тусдаа). Сервер анх асахдаа өөрийн гэрчилгээг
`.runtime/tls/`-д үүсгэж хадгална; IP солигдсон ч код өөрчлөгдөхгүй. Гэрчилгээг certificate
authority батлаагүй тул ажилтан **серверийн код**-ыг (гэрчилгээний SHA-256-ийн эхний 12 тэмдэгт)
оруулна. Ажилтны апп бүтэн fingerprint-ийг `server.json`-д хадгалж, цаашид зөвхөн тэр
гэрчилгээтэй сервертэй ярина (`agent/transport.py`, `WORKTRACK_SERVER_PIN`). Хаяг, код
серверийн цонх болон **Тохиргоо → Сервер ба backup**-д харагдана. `.runtime/tls/server.key`-г
устгавал шинэ код үүсч, бүх ажилтан дахин холбогдоно. Энэ нь Django-ийн хөгжүүлэлтийн сервер
тул жижиг оффист зориулсан; `/admin` зөвхөн серверийн компьютер дээрээс ч secure cookie
шаарддаг тул ажиллахгүй (вебийн админ хэсгийг ашиглана). Олон хүн эсвэл гаднаас хандах бол
доорх HTTPS deployment-ийг ашиглана.

Installer-ийг `python packaging/build_client.py` build хийнэ (PyInstaller). CI
(`.github/workflows/installer.yml`) нь Windows, macOS дээр build хийж, `verify_client.py`-аар
ажилтны бүх урсгалыг (суулгасан аппыг оффисын HTTPS сервер, кодтой) туршаад zip-ийг хадгална.

Tray дүрс (`desktop/tray.py`) нь тусдаа жижиг процесс: launcher түүнийг нууц түлхүүртэй асааж,
тэр зөвхөн `127.0.0.1:8766/desktop/tray/`-тай ярина. Эхлүүлэх үед сүүлд сонгосон даалгаврыг
(`.runtime/last-task.json`) эхлүүлнэ; даалгавар дууссан/шилжсэн бол хуудсыг нээж шинээр сонгуулна.
Хуудас нээлттэй эсэхээс үл хамааран WorkTrack нь бүртгэж байх үед даалгаврын цагийн session-ийг 30
секунд тутам сунгана (`desktop/workday.py`; сервер 90 секунд мэдээгүй session-ийг дуусгадаг).
Эх кодоос ажиллуулахад tray-д `pip install pystray pillow` хэрэгтэй; суулгасан аппад орсон.

### Ажилтны аппын шинэ хувилбар гаргах

1. `agent/version.py`-ийн `VERSION`-ийг нэмнэ (жишээ нь `1.1.0`), commit хийнэ.
2. `git tag v1.1.0 && git push origin v1.1.0`. Installer workflow хоёр zip-ийг build хийж,
   туршаад **GitHub Releases**-д нийтэлнэ (tag ба `VERSION` таарахгүй бол зогсоно).
3. Вебийн **Тохиргоо → Ажилтны аппын шинэ хувилбар**-т `1.1.0` болон холбоосыг
   (`https://github.com/<owner>/<repo>/releases/latest`) бичнэ.

Хуучин аппууд 6 цаг тутам серверээс шалгаж, нэг удаа мэдэгдэл гаргаад «Миний өнөөдөр»-т татах
холбоос харуулна. Ажилтан WorkTrack-аа хааж, шинэ хувилбарыг хуучин хавтасны оронд хуулна;
өгөгдөл хэрэглэгчийн профайлд тул хадгалагдана. Апп өөрөө татаж суулгахгүй. Компьютер бүрийн
хувилбар «Төхөөрөмжийн төлөв»-д харагдана.

### Тоон гарын үсэг

Гарын үсэггүй апп анх нээхэд Windows SmartScreen, macOS Gatekeeper анхааруулга гаргадаг
бөгөөд олон компанийн IT ийм аппыг хориглодог. Гэрчилгээг байгууллага өөрөө авна:

- **macOS:** [Apple Developer Program](https://developer.apple.com/programs/) (жилд $99) →
  «Developer ID Application» гэрчилгээ → Keychain-аас `.p12` болгон export. GitHub repo-ийн
  **Settings → Secrets and variables → Actions**-д: `MACOS_CERT_P12_BASE64` (`base64 -i cert.p12`),
  `MACOS_CERT_PASSWORD`, `MACOS_SIGN_IDENTITY` (`Developer ID Application: Нэр (TEAMID)`),
  notarization-д `APPLE_ID`, `APPLE_TEAM_ID`, `APPLE_APP_PASSWORD` (appleid.apple.com-ийн
  app-specific password).
- **Windows:** code signing гэрчилгээ (OV/EV) худалдан авна. `.pfx` файлтай бол
  `WINDOWS_CERT_PFX_BASE64`, `WINDOWS_SIGN_PASSWORD` secret нэмнэ. 2023 оноос хойш ихэнх
  гэрчилгээ USB token эсвэл cloud HSM дээр ирдэг тул `.pfx` гаргах боломжгүй байж болно; тэгвэл
  token-той Windows компьютер дээр `WINDOWS_SIGN_THUMBPRINT=<гэрчилгээний thumbprint>` тавиад
  `python packaging/build_client.py` ажиллуулна (Windows SDK-ийн `signtool`).

Secret байхгүй үед CI гарын үсэггүй (macOS-д ad-hoc) build хийсээр байна. Гарын үсэг зурах алхам
бодит гэрчилгээгээр хараахан туршигдаагүй: анхны удаа CI-ийн «Sign» алхмын log-ийг шалгана уу.

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

## AI туршилтын өгөгдөл (өдрийн өөрийн үнэлгээ)

Ажилтан «Ажил дуусгах» дарахад «Өнөөдөр хэр бүтээмжтэй байсан бэ? Бага / Дунд / Өндөр» гэж
асууна (өдөрт нэг удаа; «Дараа» дарж алгасаж болно, хуудсан дээр асуулт үлдэнэ; тухайн өдөртөө
«Өөрчлөх»-өөр засна). Энэ нь албан ёсны оноонд нөлөөлөхгүй; `ai/experiment.py`-ийн шошго болно.

```bash
python manage.py export_ai_dataset --out ~/worktrack-ai/dataset.csv [--since 2026-11-01] [--require-camera]
python ai/experiment.py --data-kind real --csv ~/worktrack-ai/dataset.csv
```

Нэг мөр = үнэлгээ өгсөн, компьютерийн бүртгэлтэй нэг хүний нэг өдөр. Хүнийг нэр, id-гаар биш,
серверийн нууц түлхүүрээс гаргасан `p-…` кодоор тэмдэглэнэ. Үзүүлэлтүүд (0–1): идэвхтэй хугацааны
хувь, ажлын програмын хувь, камерт харагдсан хувь (камергүй өдөр 0; `--require-camera` нь тийм
өдрийг хасна), тухайн өдөр дуусах ёстой даалгаврын гүйцэтгэл (онооны T). Туршилтад ядаж 30 мөр,
5 хүн, гурван шошго бүгд хэрэгтэй; команд юу дутуу байгааг хэлнэ. Файлыг Git-д бүү оруул.

## Нууц үгээ мартсан ажилтан

Имэйл шаардахгүй. Админ **Багийн гишүүд** → тухайн хүний **Сэргээх код үүсгэх**-ийг дарж,
`ABCD-EFGH-JKLM` маягийн кодыг ажилтанд биечлэн эсвэл хувийн мессежээр өгнө. Ажилтан нэвтрэх
хуудасны **Нууц үгээ мартсан уу?** дээр нэвтрэх нэр, код, шинэ нууц үгээ оруулна. Код 24 цаг
хүчинтэй, нэг удаа ажиллана, шинэ код үүсгэвэл хуучин нь хүчингүй. Серверт зөвхөн hash
хадгалагдана; оролдлогыг login-ийн адил хязгаарлана. Амжилттай бол хуучин session-ууд хаагдана.
Админ ажилтны шинэ нууц үгийг мэдэхгүй. Шууд шинэ нууц үг тохируулах (**Нууц үг шинэчлэх**)
боломж хэвээр байна.

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

