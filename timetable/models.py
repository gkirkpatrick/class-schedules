"""Timetable models for courses, sections, scenarios, and results."""

from django.db import models

from core.models import Room, School, Student, Teacher, TimestampedModel


class Course(TimestampedModel):
    """Represents a course offering."""

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="courses")
    code = models.CharField(max_length=50, help_text="Course code (e.g., ENG9)")
    name = models.CharField(max_length=255)
    duration_periods = models.IntegerField(
        default=1, help_text="Number of consecutive periods per meeting"
    )
    meets_per_week = models.IntegerField(help_text="Number of times course meets per week")
    is_lab = models.BooleanField(default=False, help_text="Whether this is a lab course")
    base_course = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="labs",
        help_text="Base course if this is a lab",
    )
    room_feature_required = models.ForeignKey(
        "core.RoomFeature",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="courses",
        help_text="Required room feature (e.g., LAB)",
    )
    capacity = models.IntegerField(help_text="Maximum students per section")

    class Meta:
        ordering = ["school", "code"]
        unique_together = [["school", "code"]]
        indexes = [
            models.Index(fields=["school", "code"]),
            models.Index(fields=["school", "is_lab"]),
        ]

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"


class Section(TimestampedModel):
    """Represents a section of a course with specific teacher/room candidates."""

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="sections")
    teacher_candidates = models.ManyToManyField(
        Teacher, related_name="candidate_sections", help_text="Teachers who can teach this section"
    )
    room_candidates = models.ManyToManyField(
        Room, related_name="candidate_sections", help_text="Rooms where this section can be held"
    )
    planned_count_per_week = models.IntegerField(
        help_text="Number of times this section should be scheduled per week"
    )
    lock_to_periods = models.JSONField(
        default=dict,
        blank=True,
        help_text="Optional admin locks (e.g., {day: 1, period: 3})",
    )

    class Meta:
        ordering = ["course"]

    def __str__(self) -> str:
        return f"Section of {self.course.code}"


class RequirementTemplate(TimestampedModel):
    """Defines course requirements for groups of students."""

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="requirement_templates"
    )
    name = models.CharField(max_length=255)
    selector = models.JSONField(
        default=dict,
        help_text="JSON predicates for which students this applies to (e.g., grade==9)",
    )
    required_courses = models.JSONField(
        default=list,
        help_text="List of required courses (e.g., [{course_code: 'ENG9', count: 1}])",
    )
    lab_policy = models.JSONField(
        default=dict,
        help_text="Lab policy (e.g., {course_code: 'SCI9', min_labs: 1, max_labs: 2})",
    )

    class Meta:
        ordering = ["school", "name"]
        unique_together = [["school", "name"]]
        indexes = [
            models.Index(fields=["school", "name"]),
        ]

    def __str__(self) -> str:
        return f"{self.school.name} - {self.name}"


class Scenario(TimestampedModel):
    """Represents a scheduling scenario with configuration and status."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        RUNNING = "RUNNING", "Running"
        SOLVED = "SOLVED", "Solved"
        INFEASIBLE = "INFEASIBLE", "Infeasible"
        FAILED = "FAILED", "Failed"

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="scenarios")
    name = models.CharField(max_length=255)
    config = models.JSONField(
        default=dict,
        help_text="Immutable snapshot of configuration for this scenario",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    logs = models.TextField(blank=True, help_text="Solver logs and diagnostics")

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["school", "status"]),
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.school.name} - {self.name} ({self.status})"


class Placement(TimestampedModel):
    """Represents a scheduled section placement (solver output)."""

    scenario = models.ForeignKey(Scenario, on_delete=models.CASCADE, related_name="placements")
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name="placements")
    day = models.IntegerField(help_text="Day number (0-indexed)")
    period = models.IntegerField(help_text="Period number (0-indexed)")
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="placements")
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE, related_name="placements")
    is_lab = models.BooleanField(default=False)

    class Meta:
        ordering = ["scenario", "day", "period"]
        indexes = [
            models.Index(fields=["scenario", "day", "period"]),
            models.Index(fields=["scenario", "teacher"]),
            models.Index(fields=["scenario", "room"]),
            models.Index(fields=["scenario", "section"]),
        ]

    def __str__(self) -> str:
        return f"{self.section.course.code} - Day {self.day} P{self.period} - {self.room.name}"


class StudentEnrollment(TimestampedModel):
    """Represents a student's enrollment in a section (assignment stage output)."""

    scenario = models.ForeignKey(Scenario, on_delete=models.CASCADE, related_name="enrollments")
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="enrollments")
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name="enrollments")
    day = models.IntegerField(help_text="Day number (0-indexed)")
    period = models.IntegerField(help_text="Period number (0-indexed)")

    class Meta:
        ordering = ["scenario", "student", "day", "period"]
        indexes = [
            models.Index(fields=["scenario", "student"]),
            models.Index(fields=["scenario", "section"]),
            models.Index(fields=["scenario", "day", "period"]),
        ]
        unique_together = [["scenario", "student", "day", "period"]]

    def __str__(self) -> str:
        return f"{self.student} - {self.section.course.code} - Day {self.day} P{self.period}"
