from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView, TokenBlacklistView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from core import views

router = DefaultRouter()
router.register('users', views.UserViewSet, basename='user')
router.register('departments', views.DepartmentViewSet, basename='department')
router.register('employees', views.EmployeeViewSet, basename='employee')
router.register('tasks', views.TaskViewSet, basename='task')
router.register('workstations', views.WorkstationViewSet, basename='workstation')
router.register('consents', views.ConsentViewSet, basename='consent')
router.register('activity', views.ActivityViewSet, basename='activity')
router.register('camera/observations', views.ObservationViewSet, basename='observation')
router.register('scores', views.ScoreViewSet, basename='score')
urlpatterns = [
    path('admin/', admin.site.urls), path('api/health/', views.HealthView.as_view()),
    path('api/auth/login/', views.LoginView.as_view()), path('api/auth/refresh/', TokenRefreshView.as_view()),
    path('api/auth/logout/', TokenBlacklistView.as_view()), path('api/reports/', views.ReportView.as_view()),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema')), path('api/', include(router.urls)),
]
