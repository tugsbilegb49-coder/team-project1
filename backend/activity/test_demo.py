from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from scoring.models import ProductivityScore
from users.models import AgentHeartbeat, DailySelfRating, User
from workforce.models import Task, TaskTransfer
from .models import CameraPresence, ComputerActivity


class DemoSeedTests(TestCase):
    def test_refuses_outside_the_demo_database_or_with_real_users(self):
        with self.assertRaisesMessage(CommandError, 'worktrack.py --demo'):
            call_command('seed_demo', stdout=StringIO())
        User.objects.create_user('real-person')
        with override_settings(WORKTRACK_DEMO=True), self.assertRaisesMessage(CommandError, 'never mixed'):
            call_command('seed_demo', stdout=StringIO())

    @override_settings(WORKTRACK_DEMO=True)
    def test_a_month_of_example_data_fills_every_page(self):
        output = StringIO()
        call_command('seed_demo', stdout=output)
        self.assertIn('Password for every account: demo1234', output.getvalue())
        self.assertEqual(User.objects.count(), 7)
        bat = User.objects.get(username='bat')
        self.assertTrue(bat.check_password('demo1234'))
        self.assertGreater(ComputerActivity.objects.filter(employee=bat).count(), 500)
        self.assertGreater(ProductivityScore.objects.filter(employee=bat).count(), 15)  # The 30-day line.
        self.assertTrue(Task.objects.filter(status=Task.Status.DONE, quality_score__isnull=False).exists())
        self.assertTrue(Task.objects.filter(contributions__percent=25).exists())  # Shared work.
        self.assertTrue(TaskTransfer.objects.filter(status='PENDING').exists())
        self.assertTrue(CameraPresence.objects.filter(employee=bat).exists())
        self.assertEqual(set(DailySelfRating.objects.values_list('label', flat=True)), {'LOW', 'MEDIUM', 'HIGH'})
        self.assertEqual(AgentHeartbeat.objects.count(), 6)
        client = APIClient()
        health = client.get('/api/health/').data
        self.assertEqual(health['demo']['password'], 'demo1234')
        login = client.post('/api/auth/login/', {'username': 'demo-admin', 'password': 'demo1234'}, format='json')
        self.assertEqual(login.status_code, 200)

    def test_real_servers_do_not_advertise_demo_accounts(self):
        self.assertNotIn('demo', APIClient().get('/api/health/').data)
