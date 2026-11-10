from django.contrib import admin

from .models import (
    CameraAnalytics,
    ComputerActivity,
    ConsentRecord,
    Department,
    Employee,
    Task,
)

admin.site.register([Department, Employee, Task, ConsentRecord,
                     ComputerActivity, CameraAnalytics])
