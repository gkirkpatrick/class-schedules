"""Admin configuration for core models."""

from django.contrib import admin

from .models import Group, Room, RoomFeature, School, Student, Teacher


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    """Admin for School model."""

    list_display = [
        "name",
        "cycle_days",
        "periods_per_day",
        "period_minutes",
        "created_at",
    ]
    search_fields = ["name"]
    list_filter = ["cycle_days", "periods_per_day"]


@admin.register(RoomFeature)
class RoomFeatureAdmin(admin.ModelAdmin):
    """Admin for RoomFeature model."""

    list_display = ["code", "school", "description"]
    search_fields = ["code", "description"]
    list_filter = ["school"]


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    """Admin for Room model."""

    list_display = ["name", "school", "capacity"]
    search_fields = ["name"]
    list_filter = ["school"]
    filter_horizontal = ["features"]


@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    """Admin for Teacher model."""

    list_display = ["last_name", "first_name", "email", "school", "effective_daily_cap"]
    search_fields = ["first_name", "last_name", "email"]
    list_filter = ["school"]


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    """Admin for Student model."""

    list_display = ["last_name", "first_name", "grade", "school"]
    search_fields = ["first_name", "last_name"]
    list_filter = ["school", "grade"]


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    """Admin for Group model."""

    list_display = ["name", "school"]
    search_fields = ["name"]
    list_filter = ["school"]
    filter_horizontal = ["students"]
