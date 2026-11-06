from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from users.auth import LoginView, LogoutView
from users.health import HealthView

from activity.batch import ActivityBatchView
from users.views import ConsentRecordViewSet, DeviceViewSet, UserViewSet
from workforce.views import DepartmentViewSet, TaskViewSet
from activity.views import (
    ActivityEventViewSet,
    ComputerActivityViewSet,
    WebsiteActivityViewSet,
)
from scoring.views import ProductivityScoreViewSet


router = DefaultRouter()
router.register("users", UserViewSet, basename="user")
router.register("consents", ConsentRecordViewSet, basename="consent")
router.register("devices", DeviceViewSet, basename="device")
router.register("departments", DepartmentViewSet, basename="department")
router.register("tasks", TaskViewSet, basename="task")
router.register("activity-events", ActivityEventViewSet, basename="activity-event")
router.register("computer-activity", ComputerActivityViewSet, basename="computer-activity")
router.register("website-activity", WebsiteActivityViewSet, basename="website-activity")
router.register("scores", ProductivityScoreViewSet, basename="score")

urlpatterns = [
    path("api/health/", HealthView.as_view()),
    path("api/v1/activity", ActivityBatchView.as_view()),
    path("admin/", admin.site.urls),
    path("api/auth/login/", LoginView.as_view(), name="token-obtain-pair"),
    path("api/auth/logout/", LogoutView.as_view(), name="token-logout"),
    path("api/auth/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("api/", include(router.urls)),
]

