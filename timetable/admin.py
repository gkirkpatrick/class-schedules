"""Admin configuration for timetable models."""

from django.contrib import admin

from .models import (
    Course,
    Placement,
    RequirementTemplate,
    Scenario,
    Section,
    StudentEnrollment,
)


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    """Admin for Course model."""

    list_display = [
        "code",
        "name",
        "school",
        "meets_per_week",
        "is_lab",
        "capacity",
    ]
    search_fields = ["code", "name"]
    list_filter = ["school", "is_lab"]


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    """Admin for Section model."""

    list_display = ["course", "planned_count_per_week"]
    search_fields = ["course__code", "course__name"]
    list_filter = ["course__school"]
    filter_horizontal = ["teacher_candidates", "room_candidates"]


@admin.register(RequirementTemplate)
class RequirementTemplateAdmin(admin.ModelAdmin):
    """Admin for RequirementTemplate model."""

    list_display = ["name", "school"]
    search_fields = ["name"]
    list_filter = ["school"]


@admin.register(Scenario)
class ScenarioAdmin(admin.ModelAdmin):
    """Admin for Scenario model."""

    list_display = ["name", "school", "status", "created_at"]
    search_fields = ["name"]
    list_filter = ["school", "status", "created_at"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(Placement)
class PlacementAdmin(admin.ModelAdmin):
    """Admin for Placement model."""

    list_display = [
        "scenario",
        "section",
        "day",
        "period",
        "room",
        "teacher",
        "is_lab",
    ]
    search_fields = ["section__course__code", "room__name", "teacher__last_name"]
    list_filter = ["scenario", "day", "is_lab"]


@admin.register(StudentEnrollment)
class StudentEnrollmentAdmin(admin.ModelAdmin):
    """Admin for StudentEnrollment model."""

    list_display = ["scenario", "student", "section", "day", "period"]
    search_fields = ["student__last_name", "section__course__code"]
    list_filter = ["scenario", "day"]
