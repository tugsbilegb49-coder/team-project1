import time
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, close_old_connections


class Command(BaseCommand):
    help = 'Run daily backup cycle at startup and check hourly; failures retry later.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true')

    def handle(self, *args, **options):
        try:
            while True:
                close_old_connections()
                try:
                    call_command('backup_cycle', stdout=self.stdout, stderr=self.stderr)
                    from users.operations import current_settings

                    policy = current_settings()
                    if policy.automatic_retention:
                        call_command(
                            'cleanup_activity',
                            days=policy.activity_retention_days,
                            apply=True,
                            backup=True,
                            stdout=self.stdout,
                            stderr=self.stderr,
                        )
                except (CommandError, DatabaseError, OSError) as exc:
                    if options['once']:
                        raise CommandError(str(exc)) from exc
                    self.stderr.write(f'Backup cycle failed; retry in one hour: {exc}')
                if options['once']:
                    return
                for _ in range(120):
                    time.sleep(30)
        except KeyboardInterrupt:
            self.stdout.write('Backup scheduler stopped.')
