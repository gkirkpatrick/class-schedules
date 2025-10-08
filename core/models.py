"""Core models for school scheduling system."""

from django.db import models


class TimestampedModel(models.Model):
    """Abstract base model with created_at and updated_at timestamps."""

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class School(TimestampedModel):
    """Represents a school with its scheduling configuration."""

    name = models.CharField(max_length=255, unique=True)
    timezone = models.CharField(max_length=63, default="UTC")
    cycle_days = models.IntegerField(default=5, help_text="Number of days in cycle (e.g., 5)")
    periods_per_day = models.IntegerField(
        default=8, help_text="Number of periods per day (e.g., 8)"
    )
    period_minutes = models.IntegerField(
        default=50, help_text="Length of each period in minutes"
    )
    recess_after_period = models.IntegerField(
        null=True,
        blank=True,
        help_text="Period number after which recess occurs (null if no recess)",
    )
    lunch_window_start_period = models.IntegerField(
        default=4, help_text="Period number when lunch window starts (1-indexed)"
    )
    lunch_window_span = models.IntegerField(
        default=2, help_text="Number of periods in lunch window"
    )
    default_teacher_daily_cap = models.IntegerField(
        default=3, help_text="Default max periods per teacher per day"
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["name"]),
        ]

    def __str__(self) -> str:
        return self.name


class RoomFeature(TimestampedModel):
    """Represents a feature/amenity that a room can have (e.g., LAB, GYM)."""

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="room_features")
    code = models.CharField(max_length=50)
    description = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["school", "code"]
        unique_together = [["school", "code"]]
        indexes = [
            models.Index(fields=["school", "code"]),
        ]

    def __str__(self) -> str:
        return f"{self.school.name} - {self.code}"


class Room(TimestampedModel):
    """Represents a physical room in a school."""

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="rooms")
    name = models.CharField(max_length=100)
    capacity = models.IntegerField(help_text="Maximum number of students")
    features = models.ManyToManyField(RoomFeature, blank=True, related_name="rooms")

    class Meta:
        ordering = ["school", "name"]
        unique_together = [["school", "name"]]
        indexes = [
            models.Index(fields=["school", "name"]),
        ]

    def __str__(self) -> str:
        return f"{self.school.name} - {self.name}"


class Teacher(TimestampedModel):
    """Represents a teacher in a school."""

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="teachers")
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    daily_teaching_cap = models.IntegerField(
        null=True,
        blank=True,
        help_text="Max periods per day (overrides school default if set)",
    )
    available_mask = models.JSONField(
        default=dict,
        blank=True,
        help_text="Optional per-day/per-period availability restrictions",
    )

    class Meta:
        ordering = ["school", "last_name", "first_name"]
        indexes = [
            models.Index(fields=["school", "last_name", "first_name"]),
            models.Index(fields=["email"]),
        ]

    def __str__(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @property
    def effective_daily_cap(self) -> int:
        """Get effective daily teaching cap (own or school default)."""
        if self.daily_teaching_cap is not None:
            return self.daily_teaching_cap
        return self.school.default_teacher_daily_cap


class Student(TimestampedModel):
    """Represents a student in a school."""

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="students")
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    grade = models.IntegerField(help_text="Grade level (e.g., 9, 10, 11, 12)")
    attributes = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional attributes like IEP, ELL level, etc.",
    )

    class Meta:
        ordering = ["school", "grade", "last_name", "first_name"]
        indexes = [
            models.Index(fields=["school", "grade"]),
            models.Index(fields=["school", "last_name", "first_name"]),
        ]

    def __str__(self) -> str:
        return f"{self.first_name} {self.last_name} (Grade {self.grade})"


class Group(TimestampedModel):
    """Represents a group of students based on predicates."""

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="groups")
    name = models.CharField(max_length=255)
    predicate = models.JSONField(
        default=dict,
        help_text="JSON predicate for selecting students (e.g., grade==9 or IEP==true)",
    )
    students = models.ManyToManyField(Student, blank=True, related_name="groups")

    class Meta:
        ordering = ["school", "name"]
        unique_together = [["school", "name"]]
        indexes = [
            models.Index(fields=["school", "name"]),
        ]

    def __str__(self) -> str:
        return f"{self.school.name} - {self.name}"
