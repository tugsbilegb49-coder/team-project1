from django.core.management.base import BaseCommand, CommandError
from activity.backups import create_backup


class Command(BaseCommand):
    help = 'Create a consistent private backup (SQLite or PostgreSQL). Existing files are never overwritten.'

    def add_arguments(self, parser):
        parser.add_argument('--output', help='New backup file; default backend/backups/database-TIMESTAMP.*')

    def handle(self, *args, **options):
        try:
            path = create_backup(options.get('output'))
        except OSError as exc:
            raise CommandError(f'Cannot create backup: {exc}') from exc
        self.stdout.write(self.style.SUCCESS(f'Backup created: {path}'))
