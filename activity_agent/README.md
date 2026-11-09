# Activity Agent

Энэ хавтас нь төслийн ажиллуулж болох код, camera AI, тест болон QA баримт бичгийг агуулна. Системийн overview, camera QA хэмжүүр, туршилтын одоогийн хязгаарлалтыг төслийн үндсэн README-ээс үзнэ.

## Хурдан эхлүүлэх

    python mock_server.py
    python camera_ai/person_detection.py

Гараар camera QA хийхдээ python camera_ai/evaluate_detection.py ажиллуулаад P, N товчоор бодит label-ийг оруулна. Random Forest туршилтыг python camera_ai/ai_experiment.py командаар ажиллуулна.

## Автомат шалгалт

    python -m unittest discover -s tests -v

Дэлгэрэнгүй consent checklist болон final QA тайлан: docs/camera_ai_qa.md.