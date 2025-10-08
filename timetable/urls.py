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
]
