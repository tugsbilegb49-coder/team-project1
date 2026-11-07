from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from users.auth import LoginView, LogoutView
from users.first_run import FirstRunView
from users.health import HealthView
from users.self_service import PasswordChangeView, DesktopLinkView, MyTodayView
from users.monthly import LauncherUsageView, MonthlyReportView
from users.weekly import MyWeekView

from activity.batch import ActivityBatchView
from users.views import ConsentRecordViewSet, DeviceViewSet, UserViewSet
from workforce.views import DepartmentViewSet, TaskViewSet
from activity.views import ActivityEventViewSet, ComputerActivityViewSet, CameraPresenceViewSet
from scoring.views import ProductivityScoreViewSet
from users.operations import (
    AgentStatusViewSet,
    AuditViewSet,
    MonitoringSettingsView,
    NotificationsView,
    ReportExportView,
)


router = DefaultRouter()
router.register('users', UserViewSet, basename='user')
router.register('consents', ConsentRecordViewSet, basename='consent')
router.register('devices', DeviceViewSet, basename='device')
router.register('departments', DepartmentViewSet, basename='department')
router.register('tasks', TaskViewSet, basename='task')
router.register('activity-events', ActivityEventViewSet, basename='activity-event')
router.register('camera-presence', CameraPresenceViewSet, basename='camera-presence')
router.register('computer-activity', ComputerActivityViewSet, basename='computer-activity')
router.register('scores', ProductivityScoreViewSet, basename='score')
router.register('agent-status', AgentStatusViewSet, basename='agent-status')
router.register('audit', AuditViewSet, basename='audit')

urlpatterns = [
    path('api/launcher-usage/', LauncherUsageView.as_view()),
    path('api/reports/monthly/', MonthlyReportView.as_view()),
    path('api/me/today/', MyTodayView.as_view()),
    path('api/me/week/', MyWeekView.as_view()),
    path('api/me/password/', PasswordChangeView.as_view()),
    path('api/desktop/link/', DesktopLinkView.as_view()),
    path('api/monitoring-settings/', MonitoringSettingsView.as_view()),
    path('api/notifications/', NotificationsView.as_view()),
    path('api/reports/export/', ReportExportView.as_view()),
    path('api/health/', HealthView.as_view()),
    path('api/setup/', FirstRunView.as_view()),
    path('api/v1/activity', ActivityBatchView.as_view()),
    path('admin/', admin.site.urls),
    path('api/auth/login/', LoginView.as_view(), name='token-obtain-pair'),
    path('api/auth/logout/', LogoutView.as_view(), name='token-logout'),
    path('api/auth/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('api/', include(router.urls)),
]
