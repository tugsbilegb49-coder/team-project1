# Camera AI QA and final integration

## Хамрах хүрээ

OpenCV webcam capture, YOLOv8 person detection, confidence threshold, Random Forest-ийн туршилтын өгөгдөл, camera QA metrics, API integration болон зөвшөөрөл/privacy шалгана. Энэ баримт нь төлөвлөгөөний checklist болохоос бодитоор аваагүй зөвшөөрлийг баталсан тайлан биш.

## Consent checklist

Бодит хүнтэй тест хийхээс өмнө мөр бүрийг шалгана.

- [ ] Камер ашиглах зорилгыг оролцогчид тайлбарласан.
- [ ] Хүн байгаа эсэх, confidence, timestamp болон employee ID API-д илгээгдэхийг тайлбарласан.
- [ ] Зураг, бичлэг хадгалахгүй гэдгийг тайлбарласан.
- [ ] Сайн дурын, тодорхой зөвшөөрлийг бүртгэсэн.
- [ ] Татгалзах/зөвшөөрлөө буцаах боломж болон холбоо барих хүнийг тайлбарласан.
- [ ] Камерын OS permission-ийг зөвшөөрсөн.
- [ ] Туршилтын өгөгдөлд нууц үг, frame, зураг, бичлэг оруулаагүй.
- [ ] Туршилтын дараа API-д зөвхөн шаардлагатай event хадгалагдаж буйг шалгасан.

Бодит оролцогчийн мэдээллийг энд бичихгүй. Зөвшөөрлийн бүртгэлийг байгууллагын баталсан тусдаа журмаар хадгална.

| Нууц нэр | Зорилго тайлбарласан | Зөвшөөрөл бүртгэсэн | Opt-out тайлбарласан | Camera permission |
|---|---|---|---|---|
| U01 | [ ] | [ ] | [ ] | [ ] |
| U02 | [ ] | [ ] | [ ] | [ ] |
| U03 | [ ] | [ ] | [ ] | [ ] |
| U04 | [ ] | [ ] | [ ] | [ ] |
| U05 | [ ] | [ ] | [ ] | [ ] |

## QA арга ба metric

Camera QA скрипт дээр оператор frame-ийн бодит label-ийг P (хүн байна) эсвэл N (хүн байхгүй) товчоор тэмдэглэнэ. Prediction ба бодит label-ийг qa_samples.csv-д хадгална.

| Metric | Томьёо |
|---|---|
| Precision | TP / (TP + FP) |
| Recall | TP / (TP + FN) |
| F1 | 2 × Precision × Recall / (Precision + Recall) |
| Accuracy | (TP + TN) / (TP + FP + FN + TN) |

### Одоогийн гараар тэмдэглэсэн тайлан

| Дээж | TP | FP | FN | TN | Precision | Recall | F1 | Accuracy |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 12 | 5 | 0 | 2 | 5 | 1.000 | 0.714 | 0.833 | 0.833 |

Энэ үр дүн нь зөвхөн тухайн 12 дээжид хамаарна. Одоогийн qa_samples.csv файл 10 мөртэй бөгөөд 5 TP, 0 FP, 0 FN, 5 TN байна. Иймээс README-д байгаа 12 дээжийн тооцоог CSV-ээр одоогоор давтан баталгаажуулах боломжгүй. Үлдсэн хоёр дээжийн label/confidence-ийг эх бүртгэлээс баталгаажуулж CSV-д нэмэх эсвэл QA-г дахин явуулж тайланг шинэчилнэ.

## Random Forest feature/label төлөвлөгөө

- Label: actual_present (0 = хүн байхгүй, 1 = хүн байна)
- Feature: predicted_present, confidence
- Үнэлгээ: тогтмол random seed-тэй, stratified train/test split; Accuracy, Precision, Recall, F1
- Доод босго: 20 label-тай мөр, хоёр class хоёулаа байх

Одоогийн dataset 10 мөр тул загварыг сургахгүй. Туршилтын төлөв LOW: доод босго хүрээгүй. Одоогоор Random Forest Accuracy/F1 тайлагнах үндэс байхгүй. YOLO prediction-ийг feature болгон ашиглаж байгаа тул энэ туршилтын үр дүн нь YOLO-оос хамааралтай, бие даасан camera benchmark гэж тайлбарлаж болохгүй.

## Expected vs actual integration log

| Шалгалт | Хүлээгдэж буй үр дүн | Одоогийн бодит нотолгоо | Төлөв |
|---|---|---|---|
| Mock API camera event | Event employee/date-ээр summary-д харагдах | test_camera_linked_by_employee_and_date амжилттай | PASS |
| Activity collector | Идэвхтэй/idle хугацаа болон input event зөв тоологдох | Collector-ийн 8 unit test амжилттай | PASS |
| Activity API integration | Batch SQLite-д хадгалагдаж summary-д зөв гарах | test_agent_to_db_and_summary амжилттай | PASS |
| Retry/idempotency | Network recovery болон давхардсан batch зөв ажиллах | retry/idempotency integration tests амжилттай | PASS |
| Төлөв 5 кадр тогтвортой байх | Нэг presence/absence event үүсэх | Кодод 5 кадрын debounce байна; бодит webcam demo хийгдээгүй | PENDING |
| Төлөв өөрчлөгдөх | Өөрчлөлт бүр API-д илгээгдэх | Түр зуурын алдаанд ажиллаж байх хугацаанд retry хийнэ | Код шалгасан, webcam/API smoke test pending |
| Camera unavailable | Default backend руу fallback; нөөцийг суллах | Кодын fallback болон finally cleanup байна | Код шалгасан |
| QA label бичих | P/N дарахад CSV-д нэг мөр нэмэгдэх | Кодод хэрэгжсэн; GUI дээр гараар шалгаагүй | PENDING |
| Full project regression | Автомат тестүүд амжилттай дуусах | 20 тест амжилттай | PASS |
| Privacy | Зураг/видео дискэнд үүсэхгүй | Camera code frame хадгалдаггүй | Код шалгасан; consent бүртгэл тусдаа |

## Нээлттэй асуудал

1. 12 мөрийн тайлан болон 10 мөрийн qa_samples.csv-ийн зөрүүг эх өгөгдлөөр шийдэх.
2. Зөвшөөрөлтэй хэрэглэгч, бодит webcam ашиглан presence/absence, гэрэлтүүлэг, зай, окклюзийн smoke test хийх.
3. Бодит live demo-г боломжтой төхөөрөмж дээр хийх; энэ орчны 20 автомат тест webcam hardware-ийг хамрахгүй.
4. Random Forest-д хоёр class-ийг төлөөлөхүйц илүү олон шошголсон дээж цуглуулах.
5. Сүлжээ тасарч байхад event-ийн queue зөвхөн програм ажиллаж байх үед санах ойд байна; програмыг хаавал амжаагүй event хадгалагдахгүй.
6. Байгууллагын privacy/retention шаардлагыг demo-оос өмнө эрх бүхий хүнээр батлуулах.

## QA ажиллуулах

    python camera_ai/evaluate_detection.py
    python camera_ai/ai_experiment.py
    python -m unittest discover -s tests -v