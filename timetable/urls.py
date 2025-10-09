"""URL configuration for timetable app."""

from django.urls import path

from . import views

app_name = "timetable"

urlpatterns = [
    # School management
    path("", views.school_list, name="school_list"),
    path("schools/<int:school_id>/", views.school_detail, name="school_detail"),

    # Scenario management
    path(
        "schools/<int:school_id>/scenario/new/",
        views.scenario_create,
        name="scenario_create",
    ),
    path("scenarios/<int:scenario_id>/", views.scenario_detail, name="scenario_detail"),
    path(
        "scenarios/<int:scenario_id>/results/",
        views.scenario_results,
        name="scenario_results",
    ),

    # API endpoints
    path(
        "api/scenarios/<int:scenario_id>/status/",
        views.api_scenario_status,
        name="api_scenario_status",
    ),
    path(
        "api/scenarios/<int:scenario_id>/run/",
        views.api_scenario_run,
        name="api_scenario_run",
    ),
    path(
        "api/scenarios/<int:scenario_id>/export/",
        views.api_scenario_export,
        name="api_scenario_export",
    ),
    path(
        "api/teachers/<int:teacher_id>/update/",
        views.api_teacher_update,
        name="api_teacher_update",
    ),
    path(
        "api/schools/<int:school_id>/teachers/add/",
        views.api_teacher_add,
        name="api_teacher_add",
    ),
    path(
        "api/rooms/<int:room_id>/update/",
        views.api_room_update,
        name="api_room_update",
    ),
    path(
        "api/schools/<int:school_id>/rooms/add/",
        views.api_room_add,
        name="api_room_add",
    ),
    path(
        "api/teachers/<int:teacher_id>/delete/",
        views.api_teacher_delete,
        name="api_teacher_delete",
    ),
    path(
        "api/rooms/<int:room_id>/delete/",
        views.api_room_delete,
        name="api_room_delete",
    ),
    path(
        "api/schools/<int:school_id>/sections/add/",
        views.api_section_add,
        name="api_section_add",
    ),
    path(
        "api/sections/<int:section_id>/delete/",
        views.api_section_delete,
        name="api_section_delete",
    ),
    # Pre-check endpoints
    path(
        "api/scenarios/<int:scenario_id>/precheck/",
        views.api_scenario_precheck,
        name="api_scenario_precheck",
    ),
    path(
        "scenarios/<int:scenario_id>/precheck/",
        views.scenario_precheck_html,
        name="scenario_precheck",
    ),
    path(
        "scenarios/<int:scenario_id>/precheck/export/<str:format>/",
        views.scenario_precheck_export,
        name="precheck_export",
    ),
]
