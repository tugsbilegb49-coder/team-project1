from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command, CommandError
from django.db import OperationalError
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from users.models import User
from workforce.models import Task
from .models import ProductivityScore
from .management.commands.run_score_scheduler import Command


class SchedulerTimingTests(SimpleTestCase):
    def test_retries_both_dates_and_uses_local_calendar(self):
        day=timezone.localdate()
        command=Command(stdout=StringIO(),stderr=StringIO())
        with patch('scoring.management.commands.run_score_scheduler.call_command') as calculate, \
             patch('scoring.management.commands.run_score_scheduler.close_old_connections'):
            self.assertEqual(command.refresh(),[])
        self.assertEqual([call.kwargs['date'] for call in calculate.call_args_list],[(day-timedelta(days=1)).isoformat(),day.isoformat()])

    def test_db_failure_does_not_skip_other_date_and_is_retryable(self):
        command=Command(stdout=StringIO(),stderr=StringIO())
        with patch('scoring.management.commands.run_score_scheduler.call_command',side_effect=[OperationalError('busy'),None,None,None]) as calculate, \
             patch('scoring.management.commands.run_score_scheduler.close_old_connections'):
            self.assertEqual(len(command.refresh()),1)
            self.assertEqual(command.refresh(),[])
        self.assertEqual(calculate.call_count,4)
        self.assertIn('Will retry',command.stderr._out.getvalue())

    def test_once_reports_db_failure_with_nonzero_command_error(self):
        command=Command(stdout=StringIO(),stderr=StringIO())
        with patch.object(command,'refresh',return_value=[timezone.localdate()]):
            with self.assertRaises(CommandError):
                command.handle(interval=60,once=True)

    def test_new_cycle_recomputes_dates_after_midnight(self):
        command=Command(stdout=StringIO(),stderr=StringIO())
        day=timezone.localdate()
        with patch('scoring.management.commands.run_score_scheduler.timezone.localdate',side_effect=[day,day+timedelta(days=1)]), \
             patch('scoring.management.commands.run_score_scheduler.call_command') as calculate, \
             patch('scoring.management.commands.run_score_scheduler.close_old_connections'):
            command.refresh()
            command.refresh()
        self.assertEqual([call.kwargs['date'] for call in calculate.call_args_list],[(day-timedelta(days=1)).isoformat(),day.isoformat(),day.isoformat(),(day+timedelta(days=1)).isoformat()])

    def test_shutdown_interrupts_scheduler_without_traceback(self):
        command=Command(stdout=StringIO(),stderr=StringIO())
        with patch.object(command,'refresh',return_value=[]) as refresh, \
             patch('scoring.management.commands.run_score_scheduler.time.sleep',side_effect=KeyboardInterrupt):
            command.handle(interval=60,once=False)
        refresh.assert_called_once()


class SchedulerDataTests(TestCase):
    def test_startup_refreshes_two_days_and_later_quality_is_picked_up(self):
        user=User.objects.create_user('scheduled-worker')
        today=timezone.localdate()
        completed=timezone.now()-timedelta(seconds=5)
        task=Task.objects.create(employee=user,title='Review',due_date=today,status='DONE',completed_at=completed)
        out,errors=StringIO(),StringIO()
        # Do not close the enclosing TestCase transaction during this in-process test.
        with patch('scoring.management.commands.run_score_scheduler.close_old_connections'):
            call_command('run_score_scheduler',once=True,stdout=out,stderr=errors)
            self.assertFalse(ProductivityScore.objects.filter(employee=user,date=today).exists())
            self.assertTrue(ProductivityScore.objects.filter(employee=user,date=today-timedelta(days=1)).exists())
            task.quality_score=90
            task.save()
            call_command('run_score_scheduler',once=True,stdout=out,stderr=errors)
            score=ProductivityScore.objects.get(employee=user,date=today)
            self.assertEqual(float(score.score),87)
            call_command('run_score_scheduler',once=True,stdout=out,stderr=errors)
        self.assertEqual(ProductivityScore.objects.filter(employee=user).count(),2)
