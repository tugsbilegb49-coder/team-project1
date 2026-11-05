import uuid
from datetime import timedelta
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase
from .models import User, Department, Employee, Workstation, ConsentRecord, Task, ComputerActivity, CameraObservation, ProductivityScore
from .services import weighted_score, calculate_score

class BackendTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dep = Department.objects.create(name='Engineering')
        cls.other_dep = Department.objects.create(name='Sales')
        cls.admin = User.objects.create_user('admin', password='A-long-test-password!', role='admin')
        cls.worker = User.objects.create_user('worker', password='A-long-test-password!')
        cls.manager = User.objects.create_user('manager', password='A-long-test-password!', role='manager')
        cls.outsider = User.objects.create_user('outsider', password='A-long-test-password!')
        cls.employee = Employee.objects.create(user=cls.worker, department=cls.dep)
        cls.manager_employee = Employee.objects.create(user=cls.manager, department=cls.dep)
        cls.other = Employee.objects.create(user=cls.outsider, department=cls.other_dep)
        cls.station = Workstation.objects.create(code='ENG-01', employee=cls.employee)
        cls.other_station = Workstation.objects.create(code='SALES-01', employee=cls.other)
        cls.consent = ConsentRecord.objects.create(employee=cls.employee, activity_allowed=True, camera_allowed=True)
        ConsentRecord.objects.filter(pk=cls.consent.pk).update(recorded_at=timezone.now()-timedelta(days=10))

    def auth(self, user):
        self.client.force_authenticate(user)

    def event(self, **kwargs):
        # Stable previous-day interval avoids midnight-sensitive tests.
        start = timezone.now().replace(hour=2, minute=0, second=0, microsecond=0)-timedelta(days=1)
        payload = {'event_id': str(uuid.uuid4()), 'employee': self.employee.pk, 'workstation': self.station.pk,
                   'started_at': start.isoformat(), 'ended_at': (start+timedelta(minutes=10)).isoformat(),
                   'application': 'VS Code', 'category': 'development', 'active_seconds': 500}
        payload.update(kwargs)
        return payload

    def test_health_and_authentication(self):
        self.assertEqual(self.client.get('/api/health/').status_code, 200)
        self.assertEqual(self.client.get('/api/employees/').status_code, 401)
        result = self.client.post('/api/auth/login/', {'username': 'worker', 'password': 'A-long-test-password!'})
        self.assertEqual(result.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION='Bearer '+result.data['access'])
        self.assertEqual(self.client.get('/api/users/me/').data['role'], 'employee')
        refreshed = self.client.post('/api/auth/refresh/', {'refresh': result.data['refresh']})
        self.assertEqual(refreshed.status_code, 200)
        self.assertEqual(self.client.post('/api/auth/refresh/', {'refresh': result.data['refresh']}).status_code, 401)
        self.assertEqual(self.client.post('/api/auth/logout/', {'refresh': refreshed.data['refresh']}).status_code, 200)
        self.assertEqual(self.client.post('/api/auth/refresh/', {'refresh': refreshed.data['refresh']}).status_code, 401)

    def test_role_scoping(self):
        self.auth(self.worker)
        self.assertEqual(self.client.get('/api/employees/').data['count'], 1)
        self.assertEqual(self.client.get(f'/api/employees/{self.other.pk}/').status_code, 404)
        self.assertEqual(self.client.post('/api/departments/', {'name': 'Blocked'}).status_code, 403)
        self.auth(self.manager)
        self.assertEqual(self.client.get('/api/employees/').data['count'], 2)
        self.assertEqual(self.client.get(f'/api/employees/{self.other.pk}/').status_code, 404)
        self.auth(self.admin)
        self.assertEqual(self.client.get('/api/employees/').data['count'], 3)

    def test_user_creation_and_password_validation(self):
        self.auth(self.admin)
        self.assertEqual(self.client.post('/api/users/', {'username': 'new', 'password': '123'}).status_code, 400)
        r = self.client.post('/api/users/', {'username': 'new', 'password': 'Another-long-password!', 'role': 'employee'})
        self.assertEqual(r.status_code, 201)
        self.assertNotIn('password', r.data)
        self.assertTrue(User.objects.get(username='new').check_password('Another-long-password!'))
        self.auth(self.worker)
        self.assertEqual(self.client.post('/api/users/', {'username': 'evil', 'password': 'Another-long-password!', 'role': 'admin'}).status_code, 403)

    def test_crud_and_protected_delete(self):
        self.auth(self.admin)
        response = self.client.post('/api/departments/', {'name': 'Research'})
        self.assertEqual(response.status_code, 201)
        url = f"/api/departments/{response.data['id']}/"
        self.assertEqual(self.client.patch(url, {'name': 'R&D'}).status_code, 200)
        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertEqual(self.client.delete(f'/api/departments/{self.dep.pk}/').status_code, 400)
        self.assertEqual(self.client.patch(f'/api/workstations/{self.station.pk}/', {'employee': self.other.pk}).status_code, 400)

    def test_task_validation_and_permissions(self):
        self.auth(self.admin)
        now = timezone.now()
        data = {'employee': self.employee.pk, 'title': 'API', 'started_at': (now-timedelta(days=2)).isoformat(),
                'due_at': now.isoformat(), 'status': 'done'}
        self.assertEqual(self.client.post('/api/tasks/', data).status_code, 400)
        data['completed_at'] = (now-timedelta(hours=1)).isoformat()
        data['quality_score'] = 101
        self.assertEqual(self.client.post('/api/tasks/', data).status_code, 400)
        data['quality_score'] = 90
        r = self.client.post('/api/tasks/', data)
        self.assertEqual(r.status_code, 201)
        self.auth(self.worker)
        self.assertEqual(self.client.patch(f"/api/tasks/{r.data['id']}/", {'quality_score': 100}).status_code, 403)
        self.auth(self.outsider)
        self.assertEqual(self.client.get(f"/api/tasks/{r.data['id']}/").status_code, 404)

    def test_activity_batch_duplicate_and_atomic_validation(self):
        self.auth(self.worker)
        event = self.event()
        response = self.client.post('/api/activity/batch/', {'events': [event]})
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(self.client.post('/api/activity/batch/', {'events': [event]}).status_code, 400)
        ComputerActivity.objects.all().delete()
        invalid = self.event(active_seconds=601)
        self.assertEqual(self.client.post('/api/activity/batch/', {'events': [event, invalid]}).status_code, 400)
        self.assertEqual(ComputerActivity.objects.count(), 0)
        self.assertEqual(self.client.post('/api/activity/batch/', {'events': [event, event]}).status_code, 400)
        self.assertEqual(self.client.post('/api/activity/batch/', {'events': []}).status_code, 400)

    def test_activity_overlap(self):
        self.auth(self.worker)
        first, second = self.event(), self.event()
        self.assertEqual(self.client.post('/api/activity/batch/', {'events': [first, second]}).status_code, 400)
        self.assertEqual(ComputerActivity.objects.count(), 0)
        self.assertEqual(self.client.post('/api/activity/batch/', {'events': [first]}).status_code, 201)
        self.assertEqual(self.client.post('/api/activity/batch/', {'events': [second]}).status_code, 400)

    def test_activity_consent_and_ownership(self):
        self.auth(self.outsider)
        self.assertEqual(self.client.post('/api/activity/batch/', {'events': [self.event()]}).status_code, 400)
        self.auth(self.worker)
        self.assertEqual(self.client.post('/api/activity/batch/', {'events': [self.event(workstation=self.other_station.pk)]}).status_code, 400)
        ConsentRecord.objects.create(employee=self.employee, activity_allowed=False)
        self.assertEqual(self.client.post('/api/activity/batch/', {'events': [self.event()]}).status_code, 400)
        self.assertEqual(ComputerActivity.objects.count(), 0)

    def test_cannot_backfill_before_consent(self):
        self.auth(self.worker)
        ConsentRecord.objects.filter(pk=self.consent.pk).update(recorded_at=timezone.now())
        self.assertEqual(self.client.post('/api/activity/batch/', {'events': [self.event()]}).status_code, 400)

    def test_consent_only_self_append_only(self):
        self.auth(self.admin)
        self.assertEqual(self.client.post('/api/consents/', {'employee': self.employee.pk, 'activity_allowed': True}).status_code, 403)
        self.auth(self.worker)
        r = self.client.post('/api/consents/', {'employee': self.employee.pk, 'activity_allowed': False})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(self.client.patch(f"/api/consents/{r.data['id']}/", {'activity_allowed': True}).status_code, 405)
        self.assertEqual(self.client.delete(f"/api/consents/{r.data['id']}/").status_code, 405)

    def test_camera_validation_and_permissions(self):
        data = {'event_id': str(uuid.uuid4()), 'employee': self.employee.pk, 'workstation': self.station.pk,
                'observed_at': (timezone.now()-timedelta(minutes=1)).isoformat(), 'person_count': 1, 'confidence': .95}
        self.auth(self.worker)
        self.assertEqual(self.client.post('/api/camera/observations/', data).status_code, 403)
        self.auth(self.admin)
        bad = {**data, 'confidence': 1.5}
        self.assertEqual(self.client.post('/api/camera/observations/', bad).status_code, 400)
        self.assertEqual(self.client.post('/api/camera/observations/', data).status_code, 201)
        self.assertEqual(self.client.post('/api/camera/observations/', data).status_code, 400)
        self.auth(self.outsider)
        self.assertEqual(self.client.get('/api/camera/observations/').data['count'], 0)

    def test_score_calculation_and_idempotency(self):
        start = timezone.now().replace(hour=2, minute=0, second=0, microsecond=0)-timedelta(days=1)
        due = start+timedelta(hours=5)
        day = timezone.localdate(due)
        Task.objects.create(employee=self.employee, title='done', started_at=start, due_at=due,
                            completed_at=start+timedelta(hours=1), status='done', quality_score=80)
        Task.objects.create(employee=self.employee, title='pending', started_at=start, due_at=due)
        ComputerActivity.objects.create(employee=self.employee, workstation=self.station, started_at=start,
                                       ended_at=start+timedelta(hours=8), application='IDE', category='development', active_seconds=14400)
        self.auth(self.admin)
        response = self.client.post('/api/scores/calculate/', {'employee': self.employee.pk, 'date': str(day)})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(Decimal(response.data['p']), Decimal('59.00'))
        self.assertEqual(response.data['level'], 'Low')
        self.client.post('/api/scores/calculate/', {'employee': self.employee.pk, 'date': str(day)})
        self.assertEqual(ProductivityScore.objects.count(), 1)
        before = ProductivityScore.objects.get().p
        CameraObservation.objects.create(employee=self.employee, workstation=self.station, observed_at=start, person_count=0, confidence=.99)
        self.assertEqual(calculate_score(self.employee, day).p, before)
        self.auth(self.worker)
        self.assertEqual(self.client.post('/api/scores/calculate/', {'employee': self.employee.pk, 'date': str(day)}).status_code, 403)

    def test_unreviewed_and_future_scores(self):
        now = timezone.now()
        Task.objects.create(employee=self.employee, title='unreviewed', started_at=now-timedelta(hours=1), due_at=now, completed_at=now, status='done')
        self.auth(self.admin)
        self.assertEqual(self.client.post('/api/scores/calculate/', {'employee': self.employee.pk, 'date': str(timezone.localdate())}).status_code, 400)
        self.assertEqual(self.client.post('/api/scores/calculate/', {'employee': self.employee.pk, 'date': str(timezone.localdate()+timedelta(days=1))}).status_code, 400)

    def test_reports_scope_and_date_validation(self):
        today = timezone.localdate()
        for employee, p in [(self.employee, 90), (self.other, 10)]:
            ProductivityScore.objects.create(employee=employee, date=today, t=p, q=p, d=p, w=p, p=p, level='High' if p == 90 else 'Low')
        self.auth(self.worker)
        r = self.client.get('/api/reports/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['employee_count'], 1)
        self.assertEqual(r.data['average_score'], Decimal(90))
        self.assertEqual(len(r.data['weekly']), 1)
        self.assertEqual(self.client.get('/api/scores/').data['count'], 1)
        self.assertEqual(self.client.get('/api/reports/?start=invalid').status_code, 400)
        self.assertEqual(self.client.get('/api/reports/?start=2026-11-05&end=2026-01-01').status_code, 400)
        self.assertEqual(self.client.get('/api/reports/?department='+str(self.other_dep.pk)).data['employee_count'], 0)
        self.auth(self.manager)
        self.assertEqual(self.client.get('/api/reports/').data['employee_count'], 2)
        self.auth(self.admin)
        self.assertEqual(self.client.get('/api/reports/').data['score_count'], 2)

    def test_schema(self):
        self.assertEqual(self.client.get('/api/schema/').status_code, 200)

class ScoreBoundaryTests(TestCase):
    def test_thresholds_and_rounding(self):
        for value, expected in [(0, 'Low'), (64, 'Low'), (64.99, 'Low'), (65, 'Medium'), (84.99, 'Medium'), (85, 'High'), (100, 'High')]:
            p, level = weighted_score(value, value, value, value)
            self.assertEqual(level, expected)
            self.assertEqual(p, Decimal(str(value)).quantize(Decimal('.01')))
