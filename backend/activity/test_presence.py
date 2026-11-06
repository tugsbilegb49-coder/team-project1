from datetime import date, datetime, time, timedelta
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import CameraPresence
from users.models import User, Department, Device, ConsentRecord


class CameraPresenceTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.payload = {'timestamp': (timezone.now()-timedelta(seconds=1)).isoformat(), 'present': True, 'confidence': .83}

    def grant(self):
        response = self.client.post('/api/consents/grant/', {'policy_version': 'camera-presence-v1'}, format='json')
        self.assertEqual(response.status_code, 201)

    def test_five_test_users_require_grant_and_stop_after_revoke(self):
        # These five users exist only in Django's disposable test database.
        for number in range(1, 6):
            with self.subTest(test_user=f'qa-camera-{number}'):
                user = User.objects.create_user(f'qa-camera-{number}')
                self.client.force_authenticate(user)
                self.assertFalse(self.client.get('/api/consents/status/').data['active'])
                self.assertEqual(self.client.post('/api/camera-presence/ingest/', self.payload, format='json').status_code, 403)
                self.grant()
                self.assertTrue(self.client.get('/api/consents/status/').data['active'])
                self.assertEqual(self.client.post('/api/camera-presence/ingest/', self.payload, format='json').status_code, 201)
                self.assertEqual(self.client.post('/api/camera-presence/ingest/', self.payload, format='json').status_code, 200)
                response = self.client.get('/api/camera-presence/').data
                self.assertEqual(len(response['results'] if isinstance(response, dict) else response), 1)
                self.assertEqual(self.client.post('/api/consents/revoke/').status_code, 200)
                self.assertFalse(self.client.get('/api/consents/status/').data['active'])
                self.assertEqual(self.client.post('/api/camera-presence/ingest/', self.payload, format='json').status_code, 403)
        self.assertEqual(CameraPresence.objects.count(), 5)

    def test_metadata_validation_ownership_replay_and_device(self):
        user = User.objects.create_user('presence-owner')
        other = User.objects.create_user('presence-other')
        self.client.force_authenticate(user)
        self.grant()
        foreign = Device.objects.create(employee=other, name='Other device', platform='test')
        invalid = [{'confidence': float('nan')}, {'confidence': 2}, {'present': 'yes'}, {'image': 'forbidden'},
                   {'employee': other.pk}, {'timestamp': (timezone.now()+timedelta(days=1)).isoformat()}]
        for change in invalid:
            with self.subTest(change=change):
                # NaN needs a literal JSON body because DRF's test encoder rejects it.
                import json
                response = self.client.post('/api/camera-presence/ingest/', json.dumps({**self.payload, **change}), content_type='application/json')
                self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.post('/api/camera-presence/ingest/', {**self.payload, 'device_id': str(foreign.pk)}, format='json').status_code, 403)
        self.assertEqual(self.client.post('/api/camera-presence/ingest/', self.payload, format='json').status_code, 201)
        self.assertEqual(self.client.post('/api/camera-presence/ingest/', {**self.payload, 'confidence': .2}, format='json').status_code, 400)
        self.client.force_authenticate(other)
        self.assertEqual(self.client.get(f'/api/camera-presence/{CameraPresence.objects.get().pk}/').status_code, 404)

    def test_manager_scope_and_unauthenticated_request(self):
        self.assertEqual(self.client.post('/api/camera-presence/ingest/', self.payload, format='json').status_code, 401)
        department = Department.objects.create(name='QA')
        managed = User.objects.create_user('managed', department=department)
        foreign = User.objects.create_user('foreign')
        manager = User.objects.create_user('presence-manager', role='MANAGER', department=department)
        for user in (managed, foreign):
            CameraPresence.objects.create(employee=user, **{**self.payload, 'timestamp': timezone.now()})
        self.client.force_authenticate(manager)
        response = self.client.get('/api/camera-presence/').data
        rows = response['results'] if isinstance(response, dict) else response
        self.assertEqual([row['employee'] for row in rows], [managed.pk])

    def test_dashboard_presence_is_scoped_to_employee_and_ulanbaatar_day(self):
        user = User.objects.create_user('dashboard-presence-owner')
        other = User.objects.create_user('dashboard-presence-other')
        day = date(2026, 11, 5)
        start = timezone.make_aware(datetime.combine(day, time.min))
        for stamp, present, confidence in [(start, True, .9), (start+timedelta(hours=1), False, 0),
                                           (start-timedelta(seconds=1), True, .8), (start+timedelta(days=1), True, .8)]:
            CameraPresence.objects.create(employee=user, timestamp=stamp, present=present, confidence=confidence)
        CameraPresence.objects.create(employee=other, timestamp=start, present=True, confidence=.99)
        self.client.force_authenticate(user)
        response = self.client.get('/api/scores/dashboard/', {'date': str(day)})
        self.assertEqual(response.status_code, 200)
        summary = response.data['presence']
        self.assertEqual(summary['samples'], 2)
        self.assertEqual(summary['present_samples'], 1)
        self.assertEqual(summary['absent_samples'], 1)
        self.assertEqual(summary['present_percent'], 50)
        self.assertIs(summary['latest_present'], False)
        self.assertEqual(summary['latest_confidence'], 0)
        self.assertEqual(self.client.get('/api/scores/dashboard/', {'date': str(day), 'employee_id': other.pk}).status_code, 403)
        empty = self.client.get('/api/scores/dashboard/', {'date': '2026-11-03'}).data['presence']
        self.assertEqual(empty['samples'], 0)
        self.assertIsNone(empty['present_percent'])
        self.assertIsNone(empty['latest_present'])

    def test_consent_is_rechecked_after_the_employee_write_lock(self):
        from unittest.mock import patch
        user = User.objects.create_user('concurrent-revoke-owner')
        self.client.force_authenticate(user)
        self.grant()
        def revoked_while_waiting(employee):
            ConsentRecord.objects.filter(employee=employee).update(revoked_at=timezone.now())
        with patch('activity.validation.lock_employee', side_effect=revoked_while_waiting):
            response = self.client.post('/api/camera-presence/ingest/', self.payload, format='json')
        self.assertEqual(response.status_code, 403)
        self.assertFalse(CameraPresence.objects.exists())
