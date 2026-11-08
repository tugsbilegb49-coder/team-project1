"""Fill an empty demo database with a month of believable example data (`worktrack.py --demo`).

Two departments, an admin, a manager and five employees with different working styles; for the
last 30 days: computer activity, tasks with due dates and quality ratings, shared tasks, task time,
camera samples for two people, each day's own rating, devices and their status. Scores are worked
out by the real scoring code, so every chart and report shows what the product really computes.

It refuses to run unless WORKTRACK_DEMO=1 and the database has no users: it never mixes example
data into real data.
"""

from datetime import datetime, time, timedelta
from decimal import Decimal
import random
import uuid

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from activity.models import CameraPresence, ComputerActivity
from scoring.services import ScoreNotReady, calculate_daily_score
from users.models import (
    AgentHeartbeat,
    ConsentRecord,
    DailySelfRating,
    Department,
    Device,
    LauncherInterval,
    User,
)
from users.operations import audit_event
from workforce.models import Task, TaskContribution, TaskTransfer, TaskWorkSession

PASSWORD = 'demo1234'
DAYS = 30
SEGMENT = 5 * 60  # Seconds per recorded activity segment.

DEPARTMENTS = ('Хөгжүүлэлт', 'Борлуулалт')
# username, first name, last name, role, department, focus (share of work programs), on-time rate, quality
PEOPLE = (
    ('demo-admin', 'Болд', 'Админ', 'ADMIN', None, None, None, None),
    ('demo-manager', 'Ганаа', 'Менежер', 'MANAGER', 'Хөгжүүлэлт', 0.7, 0.85, 85),
    ('bat', 'Бат', 'Эрдэнэ', 'EMPLOYEE', 'Хөгжүүлэлт', 0.78, 0.85, 84),
    ('saraa', 'Сараа', 'Дорж', 'EMPLOYEE', 'Хөгжүүлэлт', 0.86, 0.95, 92),
    ('tuya', 'Туяа', 'Ганболд', 'EMPLOYEE', 'Борлуулалт', 0.58, 0.7, 76),
    ('temuulen', 'Тэмүүлэн', 'Батаа', 'EMPLOYEE', 'Борлуулалт', 0.66, 0.8, 80),
    ('anu', 'Ану', 'Сүхээ', 'EMPLOYEE', 'Борлуулалт', 0.48, 0.55, 68),
)
WORK_APPS = {
    'Хөгжүүлэлт': ('Visual Studio Code', 'Figma', 'Terminal'),
    'Борлуулалт': ('Microsoft Excel', 'Microsoft Word', 'Microsoft PowerPoint'),
}
TASKS = {
    'Хөгжүүлэлт': (
        'Нэвтрэх хуудасны алдаа засах',
        'Тайлангийн API нэмэх',
        'Нүүр хуудасны загвар',
        'Тест бичих',
        'Код шалгах (review)',
        'Өгөгдлийн сангийн шилжилт',
        'Гар утасны дэлгэц тааруулах',
    ),
    'Борлуулалт': (
        'Сарын борлуулалтын тайлан',
        'Шинэ харилцагчтай уулзалт бэлдэх',
        'Үнийн санал илгээх',
        'Гэрээний төсөл',
        'Харилцагчийн жагсаалт шинэчлэх',
        'Танилцуулга бэлдэх',
        'Нөөцийн тооллого',
    ),
}
CAMERA_USERS = ('bat', 'saraa')


def at(day, hour, minute=0):
    return timezone.make_aware(datetime.combine(day, time(hour, minute)))


class Command(BaseCommand):
    help = 'Seed an empty demo database (only with WORKTRACK_DEMO=1).'

    def handle(self, *args, **options):
        if not getattr(settings, 'WORKTRACK_DEMO', False):
            raise CommandError('Demo data goes only into the demo database: start it with worktrack.py --demo.')
        if User.objects.exists():
            raise CommandError('This database already has users; demo data is never mixed into real data.')
        self.random = random.Random(2026)
        self.now = timezone.now()
        today = timezone.localdate()
        self.days = [today - timedelta(days=back) for back in range(DAYS - 1, -1, -1)]
        self.workdays = [day for day in self.days if day.weekday() < 5]
        with transaction.atomic():
            people = self.people()
            for person, profile in people:
                if profile:
                    self.computer_days(person, profile)
                    self.tasks(person, profile)
            self.shared_work(people)
            self.camera(people)
        # Scores and ratings after everything they are computed from exists.
        scores = 0
        for person, profile in people:
            if not profile:
                continue
            for day in self.workdays:
                try:
                    score = calculate_daily_score(person, day)
                except ScoreNotReady:
                    continue
                scores += 1
                if day < today and self.random.random() < 0.9:
                    value = float(score.score) + self.random.gauss(0, 8)
                    label = 'HIGH' if value >= 78 else 'MEDIUM' if value >= 58 else 'LOW'
                    DailySelfRating.objects.create(employee=person, date=day, label=label)
        self.audit(people)
        self.stdout.write(
            f'Demo data: {User.objects.count()} people, {Task.objects.count()} tasks, '
            f'{ComputerActivity.objects.count()} activity segments, {scores} daily scores. '
            f'Password for every account: {PASSWORD}'
        )

    def people(self):
        departments = {name: Department.objects.create(name=name) for name in DEPARTMENTS}
        result = []
        for username, first, last, role, department, *profile in PEOPLE:
            person = User.objects.create_user(
                username,
                password=PASSWORD,
                first_name=first,
                last_name=last,
                role=role,
                department=departments.get(department),
                is_staff=role == 'ADMIN',
                is_superuser=role == 'ADMIN',
            )
            if role != 'ADMIN':
                ConsentRecord.objects.create(employee=person, granted=True, policy_version='2026-11')
                platform = 'Windows' if self.random.random() < 0.5 else 'Darwin'
                person.demo_device = Device.objects.create(
                    employee=person, name=f'{first}ийн компьютер', platform=platform, last_seen_at=self.now
                )
            result.append((person, dict(zip(('focus', 'on_time', 'quality'), profile)) if profile[0] else None))
        self.admin = result[0][0]
        return result

    def computer_days(self, person, profile):
        work_apps = WORK_APPS[person.department.name]
        rows, intervals = [], []
        for day in self.workdays:
            start = at(day, 8, 45) + timedelta(minutes=self.random.randint(0, 40))
            end = at(day, 17, 30) + timedelta(minutes=self.random.randint(0, 60))
            if day == self.days[-1]:
                end = min(end, self.now)  # Today: only up to now.
            if end <= start:
                continue
            focus = min(0.95, max(0.2, profile['focus'] + self.random.gauss(0, 0.06)))
            cursor = start
            while cursor + timedelta(seconds=SEGMENT) <= end:
                if at(day, 13) <= cursor < at(day, 14):  # Lunch: nobody at the computer.
                    cursor = at(day, 14)
                    continue
                roll = self.random.random()
                if roll < focus:
                    application, category = self.random.choice(work_apps), 'WORK'
                elif roll < focus + (1 - focus) * 0.35:
                    application, category = self.random.choice(('Slack', 'Microsoft Teams')), 'COMMUNICATION'
                elif roll < focus + (1 - focus) * 0.8:
                    application, category = 'Google Chrome', 'BROWSER'
                else:
                    application, category = 'Idle', 'OTHER'
                rows.append(
                    ComputerActivity(
                        employee=person,
                        device=person.demo_device,
                        started_at=cursor,
                        duration_seconds=SEGMENT,
                        application=application,
                        category=category,
                    )
                )
                cursor += timedelta(seconds=SEGMENT)
            intervals.append(
                LauncherInterval(
                    employee=person, device=person.demo_device, event_id=uuid.uuid4(), started_at=start, ended_at=end
                )
            )
        ComputerActivity.objects.bulk_create(rows, batch_size=2000)
        LauncherInterval.objects.bulk_create(intervals)
        online = self.random.choice(('online', 'online', 'paused', 'offline'))
        seen = self.now - (timedelta(hours=3) if online == 'offline' else timedelta(seconds=20))
        AgentHeartbeat.objects.create(
            device=person.demo_device,
            kind='computer',
            seen_at=seen,
            paused=online == 'paused',
            last_upload_at=seen,
            queue_count=0 if online != 'offline' else 12,
            agent_version='1.0.0',
            settings_version=1,
        )

    def tasks(self, person, profile):
        """Two tasks due each working day, so a late one lowers the day instead of zeroing it."""
        titles = TASKS[person.department.name]
        today = self.days[-1]
        number = 0
        for day in self.workdays:
            for slot in range(2):
                number += 1
                task = Task.objects.create(
                    employee=person,
                    assigned_by=self.admin,
                    title=f'{titles[number % len(titles)]} #{number}',
                    due_date=day,
                    status=Task.Status.TODO,
                )
                if day == today:
                    if slot == 0:  # This morning's task is done; the other is under way.
                        self.done(task, person, profile, max(at(day, 8, 30), self.now - timedelta(minutes=40)))
                    else:
                        task.status = Task.Status.IN_PROGRESS
                        task.save(update_fields=['status'])
                    continue
                if self.random.random() < profile['on_time']:
                    self.done(task, person, profile, at(day, 15 + slot, self.random.randint(0, 59)))
                elif self.random.random() < 0.6:  # Late: finished a day or three after it was due.
                    late = min(today, day + timedelta(days=self.random.randint(1, 3)))
                    self.done(task, person, profile, at(late, 11, self.random.randint(0, 59)))
                # Otherwise still open: it shows up as overdue.
        for offset, status in ((2, Task.Status.IN_PROGRESS), (4, Task.Status.TODO), (7, Task.Status.TODO)):
            Task.objects.create(
                employee=person,
                assigned_by=self.admin,
                title=f'{self.random.choice(titles)} (дараагийн)',
                due_date=today + timedelta(days=offset),
                status=status,
            )

    def done(self, task, person, profile, finished):
        task.status = Task.Status.DONE
        task.completed_at = min(finished, self.now)
        task.quality_score = Decimal(max(40, min(100, round(self.random.gauss(profile['quality'], 7)))))
        task.save(update_fields=['status', 'completed_at', 'quality_score'])
        share = TaskContribution.objects.create(
            task=task, employee=person, employee_name=person.username, percent=Decimal(100)
        )
        end = task.completed_at
        begin = end - timedelta(minutes=self.random.randint(40, 150))
        TaskWorkSession.objects.create(
            contribution=share, employee=person, started_at=begin, last_heartbeat=end, ended_at=end
        )

    def shared_work(self, people):
        """A few tasks shared by two people (40% + 25% done so far) and one handover waiting for an answer."""
        by_name = {person.username: person for person, _ in people}
        for owner, helper in (('bat', 'saraa'), ('tuya', 'temuulen'), ('anu', 'tuya')):
            owner, helper = by_name[owner], by_name[helper]
            task = Task.objects.create(
                employee=owner,
                assigned_by=self.admin,
                title='Хамтын төсөл: ' + ('шинэ модуль' if owner.username == 'bat' else 'улирлын тайлан'),
                due_date=self.days[-1] + timedelta(days=5),
                status=Task.Status.IN_PROGRESS,
            )
            for person, percent in ((owner, 40), (helper, 25)):
                share = TaskContribution.objects.create(
                    task=task, employee=person, employee_name=person.username, percent=Decimal(percent)
                )
                begin = at(self.workdays[-2], 11)
                finish = begin + timedelta(minutes=90 if person == owner else 50)
                TaskWorkSession.objects.create(
                    contribution=share, employee=person, started_at=begin, last_heartbeat=finish, ended_at=finish
                )
        handover = Task.objects.create(
            employee=by_name['saraa'],
            assigned_by=self.admin,
            title='Хэрэглэгчийн гарын авлага',
            due_date=self.days[-1] + timedelta(days=3),
        )
        TaskTransfer.objects.create(
            task=handover,
            from_employee=by_name['saraa'],
            to_employee=by_name['bat'],
            requested_by=by_name['saraa'],
            from_name='saraa',
            to_name='bat',
            note='Би энэ долоо хоногт амралттай.',
        )

    def camera(self, people):
        rows = []
        for person, _ in people:
            if person.username not in CAMERA_USERS:
                continue
            for day in self.workdays[-7:]:
                moment = at(day, 9)
                while moment < min(at(day, 18), self.now):
                    lunch = at(day, 13) <= moment < at(day, 14)
                    away = lunch or self.random.random() < 0.08
                    rows.append(
                        CameraPresence(
                            employee=person,
                            timestamp=moment,
                            present=not away,
                            confidence=0.0 if away else round(self.random.uniform(0.62, 0.95), 3),
                        )
                    )
                    moment += timedelta(minutes=1)
        CameraPresence.objects.bulk_create(rows, batch_size=2000)

    def audit(self, people):
        for person, profile in people:
            if not profile:
                continue
            done = Task.objects.filter(employee=person, status=Task.Status.DONE).order_by('-completed_at').first()
            if done:
                audit_event(
                    self.admin,
                    'task',
                    done.pk,
                    'update',
                    {'quality_score': {'before': None, 'after': str(done.quality_score)}},
                    person,
                )
