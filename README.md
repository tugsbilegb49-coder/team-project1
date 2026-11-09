# Ажлын бүтээмж шалгах систем

## Төслийн зорилго

Компьютерийн идэвхийн мэдээлэл болон зөвшөөрөлтэй camera presence detection-ийг ашиглан турших систем. Camera модуль зураг, бичлэг хадгалахгүй; ажилтны ID, timestamp, хүн байгаа эсэх, confidence утгыг API руу илгээнэ.

## Бүтэц

- activity_agent/agent.py — activity agent-ийн entry point
- activity_agent/agent_core/ — collector, contract, sender, summary модулиуд
- activity_agent/mock_server.py — SQLite mock API
- activity_agent/camera_ai/person_detection.py — OpenCV + YOLO presence detection
- activity_agent/camera_ai/evaluate_detection.py — гараар шошголох camera QA
- activity_agent/camera_ai/ai_experiment.py — Random Forest туршилт
- activity_agent/qa_samples.csv — гараар шошголсон AI туршилтын өгөгдөл
- activity_agent/tests/ — автомат тестүүд
- activity_agent/docs/camera_ai_qa.md — consent checklist, QA тайлан, хязгаарлалт

## Ажиллуулах

Төслийн activity_agent хавтас дотроос:

1. API сервер: python mock_server.py
2. Өөр терминалд camera AI: python camera_ai/person_detection.py
3. Гараар camera QA: python camera_ai/evaluate_detection.py — P хүн байна, N хүн байхгүй, Q дуусгах. Сонгосон label болон prediction qa_samples.csv-д нэмэгдэнэ.
4. Random Forest туршилт: python camera_ai/ai_experiment.py
5. Бүх автомат тест: python -m unittest discover -s tests -v

Camera ашиглахаас өмнө камерын зөвшөөрөл авч, API-ийн config.json тохиргоог шалгана.

## Camera detection

YOLOv8-ийн COCO person ангилалд 0.5 confidence threshold хэрэглэнэ. Төлөв 5 кадр дараалан тогтвортой байвал өөрчлөлтийг API руу явуулна. Түр зуурын сүлжээний алдаанд илгээхийг програм ажиллаж байх хугацаанд дахин оролдоно. Зураг болон бичлэгийг файлд хадгалахгүй.

## QA-ийн одоогийн нотолгоо

| Үзүүлэлт | Утга |
|---|---:|
| Гараар шошголсон дээж | 12 |
| TP / FP / FN / TN | 5 / 0 / 2 / 5 |
| Precision | 1.000 |
| Recall | 0.714 |
| F1 | 0.833 |
| Accuracy | 0.833 |

Энэ бол 12 дээжийн урьдчилсан туршилт бөгөөд нийтлэг нарийвчлалын баталгаа биш. Одоогийн qa_samples.csv 10 мөртэй тул дээрх 12 дээжийн үр дүнг CSV-ээс бүрэн давтан тооцох боломжгүй. Эцсийн хамгаалалтаас өмнө хоёр эх сурвалжийг тулгаж, QA CSV-г бодит шошготой бүрэн болгоно.

Random Forest-ийн label нь actual_present; feature нь predicted_present ба confidence. Одоогийн өгөгдөл 10 мөртэй тул туршилтыг зориуд сургахгүй. Одоогийн AI туршилтын үнэлгээ: LOW — 20 мөрийн доод босго хүрээгүй. Accuracy/F1-ийг хангалтгүй өгөгдлөөс зохиомлоор гаргахгүй.

## Нууцлал ба зөвшөөрөл

Камер ашиглахаас өмнө зорилго, боловсруулж буй мэдээлэл, хадгалалт ба татгалзах боломжийг тайлбарлан зөвшөөрөл авна. Туршилтын checklist болон системийн үлдсэн хязгаарлалтыг activity_agent/docs/camera_ai_qa.md баримтаас үзнэ.

## Тестийн төлөв

Сүүлийн шалгалтаар Python syntax шалгалт амжилттай, автомат тестүүд 20/20 амжилттай болсон. Бодит вебкамераар live demo-г энэ орчинд шалгаагүй.