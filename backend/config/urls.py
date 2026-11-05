from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from users.views import ConsentRecordViewSet, DeviceViewSet, UserViewSet
from workforce.views import DepartmentViewSet, TaskViewSet
from activity.views import ActivityEventViewSet, ComputerActivityViewSet
from scoring.views import ProductivityScoreViewSet


router = DefaultRouter()
router.register("users", UserViewSet, basename="user")
router.register("consents", ConsentRecordViewSet, basename="consent")
router.register("devices", DeviceViewSet, basename="device")
router.register("departments", DepartmentViewSet, basename="department")
router.register("tasks", TaskViewSet, basename="task")
router.register("activity-events", ActivityEventViewSet, basename="activity-event")
router.register("computer-activity", ComputerActivityViewSet, basename="computer-activity")
router.register("scores", ProductivityScoreViewSet, basename="score")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/login/", TokenObtainPairView.as_view(), name="token-obtain-pair"),
    path("api/auth/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("api/", include(router.urls)),
]

