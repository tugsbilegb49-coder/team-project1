# Productivity System

Ajiltnii buteemj hyanah sistem (Django + PostgreSQL). Data tsugluulah ni
**ajiltnii zuvshuurliin daguu** (`ConsentRecord`) hiigdene.

## Suulgalt (Windows)

```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env      (.env dotor DB_PASSWORD-oo bichne)
python manage.py makemigrations core
python manage.py migrate
python manage.py seed
python manage.py report
```

## Ajilluulah

| Yu | Komand |
|---|---|
| Admin | `python manage.py createsuperuser` + `python manage.py runserver` |
| Computer collector | `python -m collector.computer_agent 1` |
| Camera (opencv-python, mediapipe suulgana) | `python -m camera.camera_agent 1` |
| Dashboard | `streamlit run dashboard/app.py` |

## Nuutsлал
- Tovshiltiin text, dalgetsiin zurag, camera-iin zurag HADGALAHGUI.
- Zuvshuurul baihgui ajiltnii data tsugluulahgui.

Docs: `docs/naming.md`, `docs/erd.dbml`
