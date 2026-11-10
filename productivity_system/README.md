# Productivity System

Ajiltnii buteemj hyanah sistem (Django + PostgreSQL). Data tsugluulah ni
ajiltnii zuvshuurliin daguu (`ConsentRecord`) hiigdene.

## Suulgalt (Windows)

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# .env dotor DB_PASSWORD bolon DJANGO_SECRET_KEY-g tohiruulna
python manage.py migrate
python manage.py createsuperuser
python manage.py seed       # turshiltiin medeelel uusgene
python manage.py report
python manage.py report --from 2026-01-01 --to 2026-01-31
```

Camera collector ashiglah bol optional dependency suulgana:

```powershell
pip install opencv-python mediapipe
```

Production deer `.env`-d random, nuuts `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=False`
bolon serveriin domain-uudiig `DJANGO_ALLOWED_HOSTS`-d bichne. Production
secret key baihgui bol Django aldaatai tohirgoogoor asahaas tatgalzana.
PostgreSQL suulgaagui local hugjuulelted `.env`-d `DB_ENGINE=sqlite`,
`DB_NAME=db.sqlite3` gej tohiruulaad SQLite ashiglaj bolno; production deer
PostgreSQL songono.

## Ajilluulah

| Yu | Komand |
|---|---|
| Admin | `python manage.py runserver` |
| Computer collector | `python -m collector.computer_agent <employee_id>` |
| Camera collector (opencv-python, mediapipe shaardana) | `python -m camera.camera_agent <employee_id>` |
| Dashboard | `streamlit run dashboard/app.py` |

Dashboard bolon `report` command ijil songoson hugatsaag ashiglaj bolno. Report
command-d `--from` esvel `--to`-g danгаар ni ugch bolno.

Collector ehluulehees umnu admin deer employee-d `computer` esvel `camera`
zuvshuurul ugnu. Zuvshuurul tsutslahdaa tuhain employee bolon consent type-d
`is_granted=False` shine record uusgene. Hamgiin suuld uusgesen shiidver
hereglegdej, collector 5 sekund dotor zogsono.

`python manage.py seed` ni baigaa data-g uurchluhgui. Demo data-g shineer uusgeh
shaardlagatai bol `python manage.py seed --clear` ashiglaj bolno. Ene ni ene
systemiin productivity data-g ustgaad demo data-aar solino.

## Nuutslal

- Tovshiltiin text, delgetsiin zurag, camera-iin zurag hadgalahgui.
- Consent baihgui bol activity/camera data tsugluulahgui.
- Ajiltan, task, consent-iig admin hesgees udirdana.

Docs: `docs/naming.md`, `docs/erd.dbml`
