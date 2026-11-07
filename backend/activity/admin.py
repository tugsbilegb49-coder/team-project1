from django.contrib import admin

from .models import ActivityEvent, ComputerActivity, CameraPresence


@admin.register(CameraPresence)
class CameraPresenceAdmin(admin.ModelAdmin):
    list_display = ('employee', 'timestamp', 'present', 'confidence')
    list_filter = ('present',)
    readonly_fields = ('employee', 'device', 'timestamp', 'present', 'confidence')

    def has_add_permission(self, request):
        return False


@admin.register(ActivityEvent)
class ActivityEventAdmin(admin.ModelAdmin):
    list_display = ('employee', 'timestamp', 'state', 'duration_seconds', 'source_person_id')
    list_filter = ('state',)
    search_fields = ('employee__username',)


@admin.register(ComputerActivity)
class ComputerActivityAdmin(admin.ModelAdmin):
    list_display = ('employee', 'application', 'category', 'started_at', 'duration_seconds')
    list_filter = ('category',)
    search_fields = ('employee__username', 'application')
