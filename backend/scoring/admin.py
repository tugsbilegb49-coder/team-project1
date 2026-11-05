from django.contrib import admin

from .models import ProductivityScore


@admin.register(ProductivityScore)
class ProductivityScoreAdmin(admin.ModelAdmin):
    list_display = ("employee", "date", "score", "category", "calculated_at")
    list_filter = ("category", "date")
    search_fields = ("employee__username",)

