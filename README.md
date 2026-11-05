# Ажилтны бүтээмжийн систем — Backend

Django + Django REST Framework backend. Python 3.10–3.14, Django 5.2.
Төлөвлөгөөний **1-р хүний 1–7 өдрийн backend ажлын хүрээ**: CRUD, JWT,
activity batch, камерын боловсруулсан үр дүн, score service, dashboard aggregate API.
Frontend, desktop agent, YOLO болон Random Forest сургалтыг энэ repository хэрэгжүүлэхгүй.

## 1. Ажиллуулах

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -c 'import secrets; print(secrets.token_urlsafe(60))'
```

Хэвлэгдсэн утгыг `.env` доторх `SECRET_KEY`-д тавина. Энэ workspace-д `.env`
болон `.venv` аль хэдийн үүсгэсэн тул дахин хуулж солих шаардлагагүй.

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

- Health: http://127.0.0.1:8000/api/health/
- Swagger: http://127.0.0.1:8000/api/docs/
- OpenAPI: http://127.0.0.1:8000/api/schema/
- Django admin: http://127.0.0.1:8000/admin/

`createsuperuser` хэрэглэгч API дээр бүх эрхтэй. Бусад хэрэглэгчийг admin эрхтэй
JWT ашиглан `POST /api/users/`-аар үүсгэнэ. API role нь Django admin сайт руу нэвтрэх
`is_staff` эрхээс тусдаа.

## 2. PostgreSQL

Локал шалгалт SQLite ашиглана. PostgreSQL ашиглах бол `requirements.txt`-ийн
`psycopg[binary]` драйверийг суулгаж, database болон user-аа PostgreSQL дээр үүсгээд
`.env`-д дараахыг тохируулна:

```dotenv
DB_ENGINE=postgresql
DB_NAME=productivity
DB_USER=productivity
DB_PASSWORD=your-own-password
DB_HOST=localhost
DB_PORT=5432
```

Дараа нь `python manage.py migrate`. SQLite-ийн өгөгдөл PostgreSQL рүү автоматаар
шилжихгүй. PostgreSQL орчны интеграцийн тестийг энэ workspace-д ажиллуулаагүй.

## 3. Authentication ба эрх

```bash
curl -X POST http://127.0.0.1:8000/api/auth/login/ \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"YOUR_PASSWORD"}'
```

Хариу: `access`, `refresh`. Дараагийн хүсэлтэд `Authorization: Bearer ACCESS_TOKEN`
header явуулна. Swagger-ийн **Authorize** товчид access token оруулж болно.
Access token 30 минут, refresh token 1 өдөр хүчинтэй.

| Role | Унших хүрээ | Өөрчлөх эрх |
| --- | --- | --- |
| admin / superuser | Бүх мэдээлэл | User үүсгэх, employee/department/task/workstation CRUD, camera үр дүн, score тооцох |
| manager | Өөрийн хэлтсийн мэдээлэл, тайлан | Өөрийн activity илгээх, өөрийн consent бүртгэх |
| employee | Өөрийн мэдээлэл, даалгавар, score, тайлан | Өөрийн activity илгээх, өөрийн consent бүртгэх |

Хэрэглэгч Employee profile-гүй бол өгөгдлийн харагдах хүрээ хоосон.
Ажилтны profile-ийг admin үүсгэнэ. Чанарын үнэлгээг зөвхөн admin оруулна.
Хэн ч өөр хүний consent-ийг API-аар олгох боломжгүй; consent түүх append-only.
Audit өгөгдөл, оноог Django admin-аар засах/устгахыг хаасан.

- `POST /api/auth/refresh/`: `{"refresh":"..."}` → шинэ access, refresh.
- Refresh rotation хийсний дараа өмнөх refresh хүчингүй болно.
- `POST /api/auth/logout/`: `{"refresh":"..."}` → refresh blacklist.
- Logout хийсэн ч өмнө олгогдсон access token 30 минутын хугацаагаа дуустал хүчинтэй.
- `GET /api/users/me/`: нэвтэрсэн хэрэглэгчийн мэдээлэл.

## 4. API endpoints

Бүх URL төгсгөлдөө `/`-тай. List хариу `count`, `next`, `previous`, `results`
талбаруудтай; нэг хуудас 50 мөр, `?page=2` ашиглана.

| URL | Method | Зориулалт |
| --- | --- | --- |
| `/api/health/` | GET | Authentication шаардахгүй DB health, 200 эсвэл 503 |
| `/api/users/` | POST | Хэрэглэгч үүсгэх |
| `/api/users/me/` | GET | Өөрийн хэрэглэгч |
| `/api/departments/`, `/api/departments/{id}/` | GET, POST / GET, PUT, PATCH, DELETE | Хэлтэс |
| `/api/employees/`, `/api/employees/{id}/` | GET, POST / GET, PUT, PATCH, DELETE | Ажилтан |
| `/api/tasks/`, `/api/tasks/{id}/` | GET, POST / GET, PUT, PATCH, DELETE | Даалгавар |
| `/api/workstations/`, `/api/workstations/{id}/` | GET, POST / GET, PUT, PATCH, DELETE | Компьютер/камерын ажлын байр |
| `/api/consents/`, `/api/consents/{id}/` | GET, POST / GET | Зөвшөөрлийн түүх |
| `/api/activity/batch/` | POST | 1–500 event-ийг атомик хадгалах |
| `/api/activity/`, `/api/activity/{id}/` | GET | Activity түүх |
| `/api/camera/observations/` | POST, GET | Боловсруулсан detection үр дүн |
| `/api/camera/observations/{id}/` | GET | Нэг observation |
| `/api/scores/calculate/` | POST | Өдрийн оноо тооцох/шинэчлэх |
| `/api/scores/`, `/api/scores/{id}/` | GET | Онооны түүх |
| `/api/reports/` | GET | Dashboard aggregate |

401: token байхгүй/хүчингүй. 403: эрх хүрэхгүй. 404: харах эрхгүй эсвэл байхгүй ID.
400: validation, duplicate event, эсвэл холбоотой record устгах хүсэлт.
429: rate limit. Health endpoint-оос бусад business API authentication шаарддаг.
Холбоотой түүхтэй record-уудыг устгахгүй; шаардлагатай бол admin сайтаас user-ийг
`is_active=False` болгон идэвхгүй болгоно.

## 5. Integration хийх дараалал ба JSON жишээ

Доорх ID-ууд жишээ; API хариунаас ирсэн бодит ID-г хэрэглэнэ. Хугацаа нь ISO 8601,
timezone offset-тай байна. Agent бүр event_id-даа шинэ UUID үүсгэнэ.

### Admin: user → department → employee → workstation

`POST /api/users/`:

```json
{"username":"employee1","password":"Use-your-own-long-password!","first_name":"Бат","role":"employee"}
```

`POST /api/departments/`:

```json
{"name":"Программ хангамж"}
```

`POST /api/employees/`:

```json
{"user":2,"department":1,"position":"Хөгжүүлэгч","expected_daily_minutes":480}
```

`POST /api/workstations/`:

```json
{"code":"PC-001","employee":1,"camera_id":"CAM-001"}
```

Workstation-ийн эзэмшигчийг өөрчлөх боломжгүй. Шинэ эзэмшигчид шинэ code-тай
record үүсгэнэ; ингэснээр хуучин activity-ийн эзэмшил зөрөхгүй.

### Employee: өөрийн token-оор consent өгөх

`POST /api/consents/`:

```json
{"employee":1,"activity_allowed":true,"camera_allowed":true}
```

Consent өгсний **дараах** event-үүдийг хүлээн авна. Хүсэлт илгээх үеийн хамгийн
сүүлийн consent мөн зөвшөөрсөн байх ёстой. Цуцлахдаа шинэ consent-ийг false
утгаар POST хийнэ. Өмнөх түүхийг устгахгүй.

### Admin: даалгавар

`POST /api/tasks/` (хугацааг бодит ажилдаа тохируулна):

```json
{
  "employee":1,
  "title":"Activity API integration",
  "description":"Agent-тай холбох",
  "started_at":"2026-11-05T09:00:00+08:00",
  "due_at":"2026-11-05T18:00:00+08:00",
  "status":"in_progress"
}
```

Төлөв: `todo`, `in_progress`, `done`. `done` үед `completed_at` шаардлагатай,
ирээдүйн completion хориглоно. Дууссан даалгаврын `quality_score` нь 0–100.
Oноо тооцохоос өмнө admin чанарын үнэлгээг PATCH хийнэ.

### Desktop agent: activity batch

`POST /api/activity/batch/`, employee-ийн token:

```json
{
  "events":[
    {
      "event_id":"60d93303-a69b-49b1-8eed-199b2a1f2358",
      "employee":1,
      "workstation":1,
      "started_at":"2026-11-05T10:00:00+08:00",
      "ended_at":"2026-11-05T10:05:00+08:00",
      "application":"VS Code",
      "category":"development",
      "active_seconds":280
    }
  ]
}
```

Ангилал: `documents`, `data`, `development`, `design`, `crm`, `internal`.
Зөвхөн ажлын зориулалттай аппын нэр, хэрэглээний хугацаа хадгална. Keylog,
цонхны гарчиг, screenshot, вэбийн агуулга хадгалах талбар байхгүй.

- Бүх event зөв бол 201, хадгалсан event-үүдийн array буцаана.
- Нэг event буруу бол batch бүхэлдээ хадгалагдахгүй.
- Давхардсан UUID 400; client амжилттай хадгалсан UUID-г дахин илгээхгүй.
- Нэг ажилтны хугацаа өөр workstation дээр ч давхардахгүй.
- `active_seconds` нь interval-аас ихгүй; end нь start-аас хойш, одоогоос өмнө.
- Улаанбаатарын шөнө дунд дамнасан interval-ийг хоёр event болгон хуваана.

### Camera module: detection үр дүн

`POST /api/camera/observations/`, admin token:

```json
{
  "event_id":"c1733683-bcc0-45b4-a8e1-355e33ea9430",
  "employee":1,
  "workstation":1,
  "observed_at":"2026-11-05T10:03:00+08:00",
  "person_count":1,
  "confidence":0.96
}
```

Employee нь workstation-ийн бүртгэлтэй эзэмшигч; person_count нь тухайн хүн хэн
болохыг тогтоохгүй. Камерын raw зураг/бичлэг хадгалахгүй. Confidence 0–1,
person_count 0–1000. Camera болон activity consent тусдаа.

### Score service

`POST /api/scores/calculate/`, admin token:

```json
{"employee":1,"date":"2026-11-05"}
```

Нэг employee/date хосод нэг record; дахин тооцох нь шинэчилнэ. Ирээдүйн өдрийг
хүлээн авахгүй. T/Q/D/W-ийг client дур мэдэн илгээхгүй, хадгалсан өгөгдлөөс гаргана.

Төлөвлөгөө T/Q/D/W-ийн нэр, жинг тодорхойлсон боловч дэд тооцооллыг заагаагүй.
Энэ хувилбар дараах **анхны хэрэгжүүлэлтийн дүрэм** ашиглана:

| Үзүүлэлт | Тооцоолол |
| --- | --- |
| T | Тухайн өдөр due болсон даалгавраас тэр өдрийн эцэс гэхэд дууссан хувь |
| Q | Дээрх дууссан даалгавруудын quality_score дундаж |
| D | Тухайн өдөр due болсон нийт даалгавраас deadline-аас өмнө/тэнцүү дууссан хувь |
| W | Тухайн өдрийн ажлын аппын active_seconds / (expected_daily_minutes × 60) × 100 |
| P | 0.4T + 0.3Q + 0.2D + 0.1W |

Бүгд 0–100-д хязгаарлагдаж 2 орны нарийвчлалтай. Low: P < 65,
Medium: 65 ≤ P < 85, High: P ≥ 85. Ангилал нь 2 оронд тоймлосон P дээр үндэслэнэ.
**Камерын үзүүлэлт оноонд орохгүй.** Босгын ангилал нь Random Forest таамаглал биш.

Даалгаваргүй өдрийн T/Q/D=0, activity байхгүй бол W=0. Completed task чанарын
үнэлгээгүй бол 400 өгч, оноо хадгалахгүй. Өгөгдөлгүй өдрийн 0 оноог бодит
гүйцэтгэлийн баталгаатай үнэлгээ гэж үзэхгүй. Тайлан нь зөвхөн тооцсон score-уудыг
агрегатлана; score_count-оор хамрагдсан хэмжээг харуулна. Data/quality/due date
өөрчлөгдвөл холбогдох өдрүүдийн score-ийг дахин тооцно. Автомат scheduler одоогоор
байхгүй; admin endpoint-ийг өдөр бүр эсвэл integration job-оос дуудна.

### Dashboard / report

```text
GET /api/reports/?start=2026-11-01&end=2026-11-30&department=1
GET /api/scores/?start=2026-11-01&end=2026-11-30
```

Report нь employee_count, score_count, average_score, task_count,
completed_tasks, task_completion_percent, daily, weekly, monthly,
departments, workload буцаана. Огнооны хязгаар inclusive, timezone Asia/Ulaanbaatar.
Default нь тухайн сарын эхнээс өнөөдөр. Хамгийн ихдээ 366 өдрийн зөрүү зөвшөөрнө.
Дундаж нь хадгалсан employee-day score бүрт ижил жин өгнө; missing score-ийг 0 гэж
нөхөхгүй. Department filter нь харах эрхийн хүрээг өргөжүүлэхгүй.

## 6. Шалгалт

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
python manage.py spectacular --file schema.yml --validate --fail-on-warn
```

Тестүүд: JWT login/refresh/logout, role болон object isolation, CRUD,
password validation, task validation, consent, activity atomic batch/duplicate/overlap,
camera validation, score calculation/idempotence/threshold, report scope/date validation,
OpenAPI generation. Локал тест SQLite дээр ажилладаг.

## 7. Багийн integration ба deployment

- Хүн 2/4/5 Swagger schema-аас payload болон response-оо шалгана.
- Хүн 3 `core/models.py`, `core/migrations/`, `core/services.py`-г хамт шалгана.
- Model өөрчилбөл `makemigrations`, `migrate`, test ажиллуулна.
- Git remote холбосны дараа `feature/backend-api` branch-ийг push хийж PR нээнэ.
- Production: `DEBUG=false`, өөрийн SECRET_KEY, зөв ALLOWED_HOSTS/CORS,
  HTTPS reverse proxy болон WSGI/ASGI server ашиглана; `runserver` нь development-д.
- PostgreSQL дээр employee row lock нь batch-уудын overlap шалгалтыг сериалчилна.
  SQLite нь select_for_update row lock хэрэгжүүлдэггүй тул concurrent ingestion-д PostgreSQL хэрэглэнэ.
- Default rate limit нь process-local cache ашиглана. Олон worker орчинд shared cache
  тохируулж, login limit-ийг proxy түвшинд мөн тохируулна.
- Camera integration нь одоогоор admin token шаарддаг. Production service-д тусгай
  хязгаарлагдсан machine credential нэмэх шаардлагатай; admin password-ийг agent-д тараахгүй.
