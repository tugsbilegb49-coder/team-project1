<<<<<<< HEAD

# WorkTrack

Ажлын бүтээмж болон даалгавар хянах веб аппликейшн.

## Ашигласан технологи
- React
- Vite
- JavaScript
- CSS
- LocalStorage

## Үндсэн боломжууд
- Даалгавар нэмэх
- Даалгавар устгах
- Даалгаврын төлөв өөрчлөх
- Ажилтанд даалгавар хуваарилах
- Ажилтнаар шүүх
- Төлөвөөр шүүх
- Хугацаа хэтэрсэн даалгавар хянах
- Dashboard хэсэгт мэдээлэл харах

## Ажиллуулах заавар

```bash
npm install
npm run dev
```

=======
# Ажилтны идэвх хянах систем

Энэ төсөл нь camera-аар `WORKING`, `IDLE`, `PHONE`, `AWAY` төлөв илрүүлж,
компьютер дээр ашигласан application-ийн хугацааг бүртгэнэ. Үр дүнг Django
backend болон Streamlit dashboard дээр харна.

## Шаардлага

- Python 3
- Mac-ийн built-in camera эсвэл USB camera
- Camera ашиглах зөвшөөрөл

## Эхний тохиргоо

Төслийн үндсэн хавтас руу орно:

```bash
cd ~/Desktop/bolson/worker-activity-monitor
```

Camera болон dashboard-ийн сангуудыг суулгана:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Backend-ийн сангуудыг суулгана:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
```

## Ажиллуулах

Гурван Terminal нээнэ.

### 1. Backend асаах

```bash
cd ~/Desktop/bolson/worker-activity-monitor/backend
source .venv/bin/activate
python manage.py runserver
```

Backend: `http://127.0.0.1:8000/admin/`

### 2. Computer agent асаах

Эхний удаа config файл үүсгэнэ:

```bash
cd ~/Desktop/bolson/worker-activity-monitor
cp agent/config.example.json agent/config.json
```

`agent/config.json` файл доторх `employee_username`-ийг Django admin-д
үүсгэсэн username-аар солино.

Эхний удаа нэвтэрч device бүртгүүлнэ:

```bash
python3 agent/main.py --login
python3 agent/main.py --grant-consent 2026-11
```

Дараа нь agent-аа асаана:

```bash
python3 agent/main.py
```

Энэ terminal-ийг нээлттэй үлдээнэ. Agent нь 30 секунд тутам идэвхтэй байгаа
application болон idle хугацааг backend рүү илгээнэ.

### 3. Camera monitor асаах

Шинэ Terminal дээр:

```bash
cd ~/Desktop/bolson/worker-activity-monitor
source .venv/bin/activate
python3 main.py
```

Mac camera permission асуувал **System Settings → Privacy & Security →
Camera** хэсгээс Terminal эсвэл VS Code-д зөвшөөрөл өгнө.

`config.yaml` файл дахь `camera_index: 0` нь MacBook-ийн дотоод camera.
USB camera ашиглавал `1` болгож туршиж болно.

## Үр дүн харах

Шинэ Terminal дээр:

```bash
cd ~/Desktop/bolson/worker-activity-monitor
source .venv/bin/activate
streamlit run dashboard/app.py
```

Terminal дээр гарсан `http://localhost:8501` холбоосыг browser-оор нээнэ.

Dashboard-ийн зүүн талд:

1. **Django API** сонгоно.
2. API URL: `http://127.0.0.1:8000`
3. Username, password-оо оруулж **Login** дарна.

Dashboard дээр application бүрийн минут, camera төлөвийн хугацаа болон нийт
productivity score харагдана.

## Зогсоох

Agent, camera болон backend ажиллаж буй Terminal бүр дээр `Ctrl + C` дарна.
>>>>>>> origin/database
