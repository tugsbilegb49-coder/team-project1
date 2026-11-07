"""Admin page data about the server itself: backups and (office server) how employees connect."""

import os
from pathlib import Path
import tempfile

from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from activity.backup_status import backup_dir, copy_dir_setting, problems, read_status
from .models import MonitoringSettings
from .operations import StrictSerializer, audit_event, current_settings
from .permissions import IsSystemAdmin

STATUS_FIELDS = ('checked_at', 'last_success_at', 'last_backup', 'last_copy_at', 'copy_dir', 'error')


def server_data():
    status = read_status()
    copy_dir, source = copy_dir_setting()
    share = None
    if os.environ.get('WORKTRACK_SHARE_ADDRESSES'):
        # Set by the launcher of an office server (worktrack.py --share).
        share = {
            'addresses': os.environ['WORKTRACK_SHARE_ADDRESSES'].split(','),
            'code': os.environ.get('WORKTRACK_SHARE_CODE', ''),
        }
    return {
        'backup': {
            'status': {name: status.get(name) for name in STATUS_FIELDS} if status else None,
            'problems': problems(status),
            'copy_dir': copy_dir,
            'copy_dir_source': source,
        },
        'share': share,
    }


class CopyDirInput(StrictSerializer):
    backup_copy_dir = serializers.CharField(max_length=500, allow_blank=True, trim_whitespace=True)

    def validate_backup_copy_dir(self, value):
        if not value:
            return ''
        path = Path(value).expanduser()
        if not path.is_absolute():
            raise serializers.ValidationError(
                'Бүтэн замыг оруулна уу (жишээ нь D:\\WorkTrack-backup эсвэл /Volumes/USB).'
            )
        if not path.is_dir():
            raise serializers.ValidationError('Энэ хавтас серверийн компьютер дээр олдсонгүй. USB/дискээ холбоно уу.')
        if path.resolve() == backup_dir().resolve():
            raise serializers.ValidationError('Энгийн backup-ийн хавтаснаас өөр газрыг сонгоно уу.')
        try:
            with tempfile.NamedTemporaryFile(dir=path, prefix='.worktrack-check-'):
                pass
        except OSError as exc:
            raise serializers.ValidationError('Энэ хавтсанд бичих эрхгүй байна.') from exc
        return str(path)


class ServerStatusView(APIView):
    permission_classes = [IsSystemAdmin]

    def get(self, request):
        return Response(server_data())

    def patch(self, request):
        if copy_dir_setting()[1] == 'environment':
            return Response(
                {'detail': 'Хуулбарын хавтсыг серверийн тохиргоо (BACKUP_COPY_DIR) тодорхойлж байна.'}, status=409
            )
        serializer = CopyDirInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        value = serializer.validated_data['backup_copy_dir']
        before = current_settings().backup_copy_dir
        MonitoringSettings.objects.filter(pk=1).update(backup_copy_dir=value)
        if before != value:
            audit_event(request.user, 'backup', 1, 'configure', {'backup_copy_dir': {'before': before, 'after': value}})
        return Response(server_data())
