from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from activity.backups import restore_backup, verify_backup


class Command(BaseCommand):
    help = 'Verify a backup by default; restore only with --apply --confirm-stopped. Creates a pre-restore safety backup.'

    def add_arguments(self, parser):
        parser.add_argument('backup')
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--confirm-stopped', action='store_true', help='Confirm backend, scheduler and agents have been stopped.')

    def handle(self, *args, **options):
        path = Path(options['backup']).expanduser().resolve()
        verify_backup(path)
        if not options['apply']:
            self.stdout.write(f'Verified only; database unchanged: {path}')
            return
        if not options['confirm_stopped']:
            raise CommandError('Stop backend, scheduler and agents first, then use --apply --confirm-stopped.')
        try:
            safety = restore_backup(path)
        except OSError as exc:
            raise CommandError(f'Restore failed: {exc}') from exc
        self.stdout.write(self.style.SUCCESS(f'Restored. Previous database backup: {safety}'))
