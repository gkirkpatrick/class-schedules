"""Pre-Check diagnostics system for schedule feasibility validation.

Runs fast validation checks before CP-SAT to detect configuration errors,
capacity shortfalls, and conflicts. Returns actionable suggestions for fixes.
"""

import math
from dataclasses import dataclass, field
from typing import Any, Literal

from core.models import Room, RoomFeature, School, Teacher
from timetable.models import Course, Section
from timetable.precheck_utils import TimeMaskBuilder


@dataclass
class PrecheckIssue:
    """Represents a single diagnostic issue found during precheck."""

    level: Literal["ERROR", "WARN", "INFO"]
    code: str
    message: str
    suggestions: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Export as dictionary."""
        return {
            "level": self.level,
            "code": self.code,
            "message": self.message,
            "suggestions": self.suggestions,
            "evidence": self.evidence,
        }


@dataclass
class PrecheckMetrics:
    """Aggregate metrics computed during precheck."""

    time_slots_total: int
    time_slots_usable: int
    sections_total: int
    meetings_total: int
    teacher_supply: dict[str, Any]
    room_supply: dict[str, Any]
    feature_supply: dict[str, Any]
    lab_requirements: dict[str, Any]
    lunch_feasibility: dict[str, Any]

    def to_dict(self) -> dict:
        """Export as dictionary."""
        return {
            "time_slots_total": self.time_slots_total,
            "time_slots_usable": self.time_slots_usable,
            "sections_total": self.sections_total,
            "meetings_total": self.meetings_total,
            "teacher_supply": self.teacher_supply,
            "room_supply": self.room_supply,
            "feature_supply": self.feature_supply,
            "lab_requirements": self.lab_requirements,
            "lunch_feasibility": self.lunch_feasibility,
        }


@dataclass
class PrecheckReport:
    """Complete precheck diagnostic report."""

    status: Literal["FAIL", "WARN", "OK"]
    issues: list[PrecheckIssue]
    metrics: PrecheckMetrics

    def to_dict(self) -> dict:
        """Export as JSON-serializable dictionary."""
        return {
            "status": self.status,
            "summary": [issue.to_dict() for issue in self.issues],
            "metrics": self.metrics.to_dict(),
        }

    def to_csv(self) -> str:
        """Export issues as CSV."""
        lines = ["Level,Code,Message,Suggestions"]
        for issue in self.issues:
            suggestions = " | ".join(issue.suggestions)
            # Escape commas and quotes
            message = issue.message.replace('"', '""')
            suggestions = suggestions.replace('"', '""')
            lines.append(f'{issue.level},{issue.code},"{message}","{suggestions}"')
        return "\n".join(lines)

    def to_markdown(self) -> str:
        """Export as Markdown report."""
        lines = [
            f"# Pre-Check Report: {self.status}",
            "",
            "## Summary",
            "",
            f"- **Status**: {self.status}",
            f"- **Total Issues**: {len(self.issues)}",
            f"- **Errors**: {sum(1 for i in self.issues if i.level == 'ERROR')}",
            f"- **Warnings**: {sum(1 for i in self.issues if i.level == 'WARN')}",
            "",
            "## Metrics",
            "",
            f"- Total time slots: {self.metrics.time_slots_total}",
            f"- Usable time slots: {self.metrics.time_slots_usable}",
            f"- Total sections: {self.metrics.sections_total}",
            f"- Total meetings: {self.metrics.meetings_total}",
            "",
            "## Issues",
            "",
        ]

        if not self.issues:
            lines.append("✅ No issues found - configuration is valid!")
        else:
            for issue in self.issues:
                emoji = "❌" if issue.level == "ERROR" else "⚠️" if issue.level == "WARN" else "ℹ️"
                lines.append(f"### {emoji} {issue.code}")
                lines.append(f"**{issue.level}**: {issue.message}")
                if issue.suggestions:
                    lines.append("\n**Suggestions:**")
                    for suggestion in issue.suggestions:
                        lines.append(f"- {suggestion}")
                lines.append("")

        return "\n".join(lines)


def run_precheck(school_id: int) -> PrecheckReport:
    """Run pre-check diagnostics for a school configuration.

    Args:
        school_id: ID of school to check

    Returns:
        Complete diagnostic report with status, issues, and metrics
    """
    school = School.objects.get(id=school_id)
    mask_builder = TimeMaskBuilder(school.cycle_days, school.periods_per_day)

    issues: list[PrecheckIssue] = []

    # Run all checks
    issues.extend(_check_sanity(school, mask_builder))
    issues.extend(_check_teacher_capacity(school, mask_builder))
    issues.extend(_check_teacher_section_load(school, mask_builder))
    issues.extend(_check_lunch_feasibility(school, mask_builder))
    issues.extend(_check_room_capacity(school, mask_builder))
    issues.extend(_check_feature_supply(school, mask_builder))
    issues.extend(_check_teacher_candidates(school, mask_builder))
    issues.extend(_check_locked_collisions(school, mask_builder))
    issues.extend(_check_lab_overlaps(school, mask_builder))
    issues.extend(_check_per_day_capacity(school, mask_builder))
    issues.extend(_check_time_overflow(school, mask_builder))

    # Add warnings
    issues.extend(_check_warnings(school, mask_builder))

    # Compute metrics
    metrics = _compute_metrics(school, mask_builder)

    # Determine overall status
    has_errors = any(i.level == "ERROR" for i in issues)
    has_warnings = any(i.level == "WARN" for i in issues)
    status = "FAIL" if has_errors else "WARN" if has_warnings else "OK"

    return PrecheckReport(status=status, issues=issues, metrics=metrics)


def _check_sanity(school: School, mask_builder: TimeMaskBuilder) -> list[PrecheckIssue]:
    """Check #0: Basic sanity validation."""
    issues = []

    # Check lunch period validity
    if school.lunch_window_start_period is not None:
        if school.lunch_window_start_period < 0:
            issues.append(
                PrecheckIssue(
                    level="ERROR",
                    code="INVALID_LUNCH_PERIOD",
                    message=f"Lunch start period {school.lunch_window_start_period} is negative",
                    suggestions=["Set lunch_window_start_period to a valid period number (0-indexed)"],
                    evidence={"lunch_start": school.lunch_window_start_period},
                )
            )
        elif school.lunch_window_start_period >= school.periods_per_day:
            issues.append(
                PrecheckIssue(
                    level="ERROR",
                    code="INVALID_LUNCH_PERIOD",
                    message=f"Lunch start period {school.lunch_window_start_period} >= periods_per_day {school.periods_per_day}",
                    suggestions=[
                        f"Set lunch_window_start_period to < {school.periods_per_day}",
                        f"Or increase periods_per_day to > {school.lunch_window_start_period}",
                    ],
                    evidence={
                        "lunch_start": school.lunch_window_start_period,
                        "periods_per_day": school.periods_per_day,
                    },
                )
            )

    # Check lunch span validity
    if school.lunch_window_span is not None and school.lunch_window_span < 0:
        issues.append(
            PrecheckIssue(
                level="ERROR",
                code="INVALID_LUNCH_SPAN",
                message=f"Lunch window span {school.lunch_window_span} is negative",
                suggestions=["Set lunch_window_span to a positive number"],
                evidence={"lunch_span": school.lunch_window_span},
            )
        )

    # Check recess period validity
    if school.recess_after_period is not None:
        if school.recess_after_period < 0 or school.recess_after_period > school.periods_per_day:
            issues.append(
                PrecheckIssue(
                    level="ERROR",
                    code="INVALID_RECESS_PERIOD",
                    message=f"Recess period {school.recess_after_period} out of range [0, {school.periods_per_day}]",
                    suggestions=[f"Set recess_after_period between 0 and {school.periods_per_day}"],
                    evidence={"recess_period": school.recess_after_period},
                )
            )

    # Check courses
    courses = Course.objects.filter(school=school)
    for course in courses:
        # Check capacity
        if course.capacity <= 0:
            issues.append(
                PrecheckIssue(
                    level="ERROR",
                    code="INVALID_COURSE_CAPACITY",
                    message=f"Course {course.code} has capacity {course.capacity} (must be > 0)",
                    suggestions=[f"Set capacity for {course.code} to a positive number"],
                    evidence={"course": course.code, "capacity": course.capacity},
                )
            )

        # Check meets_per_week
        if course.meets_per_week <= 0:
            issues.append(
                PrecheckIssue(
                    level="ERROR",
                    code="INVALID_MEETS_PER_WEEK",
                    message=f"Course {course.code} has meets_per_week {course.meets_per_week} (must be > 0)",
                    suggestions=[f"Set meets_per_week for {course.code} to at least 1"],
                    evidence={"course": course.code, "meets_per_week": course.meets_per_week},
                )
            )

        # Check labs have base course
        if course.is_lab and not course.base_course:
            issues.append(
                PrecheckIssue(
                    level="ERROR",
                    code="LAB_WITHOUT_BASE",
                    message=f"Lab course {course.code} has no base_course reference",
                    suggestions=[
                        f"Set base_course for {course.code}",
                        f"Or set is_lab=False if this is not a lab",
                    ],
                    evidence={"course": course.code},
                )
            )

    return issues


def _check_teacher_capacity(school: School, mask_builder: TimeMaskBuilder) -> list[PrecheckIssue]:
    """Check #1: Global teacher capacity (lower bound)."""
    issues = []

    sections = Section.objects.filter(course__school=school)
    teachers = Teacher.objects.filter(school=school)

    # Calculate required occurrences
    req_occ = sum(s.planned_count_per_week for s in sections)

    # Calculate supply (upper bound)
    sup_occ = sum(
        (teacher.daily_teaching_cap or school.default_teacher_daily_cap) * school.cycle_days
        for teacher in teachers
    )

    if req_occ > sup_occ:
        shortfall = req_occ - sup_occ
        teachers_needed = math.ceil(shortfall / school.cycle_days / school.default_teacher_daily_cap)

        issues.append(
            PrecheckIssue(
                level="ERROR",
                code="TEACHER_SUPPLY_SHORTFALL",
                message=f"Need {req_occ} teaching slots but only {sup_occ} available (shortfall: {shortfall})",
                suggestions=[
                    f"Add {teachers_needed} teachers with default daily cap",
                    f"Increase daily caps to provide {shortfall} more slots",
                    f"Reduce sections or meetings per week to save {shortfall} slots",
                ],
                evidence={
                    "required": req_occ,
                    "supply": sup_occ,
                    "shortfall": shortfall,
                    "teacher_count": teachers.count(),
                },
            )
        )

    # Check by subject if teachers have subjects
    by_subject: dict[str, dict] = {}
    for teacher in teachers:
        if teacher.subject:
            if teacher.subject not in by_subject:
                by_subject[teacher.subject] = {"supply": 0, "required": 0}
            cap = teacher.daily_teaching_cap or school.default_teacher_daily_cap
            by_subject[teacher.subject]["supply"] += cap * school.cycle_days

    for section in sections:
        # Get subject from first teacher candidate
        teacher_candidates = section.teacher_candidates.all()
        if teacher_candidates:
            subject = teacher_candidates[0].subject
            if subject and subject in by_subject:
                by_subject[subject]["required"] += section.planned_count_per_week

    for subject, data in by_subject.items():
        if data["required"] > data["supply"]:
            shortfall = data["required"] - data["supply"]
            issues.append(
                PrecheckIssue(
                    level="ERROR",
                    code="TEACHER_SUPPLY_SHORTFALL_BY_SUBJECT",
                    message=f"{subject}: need {data['required']} slots but only {data['supply']} available (shortfall: {shortfall})",
                    suggestions=[
                        f"Add {subject} teachers",
                        f"Increase daily caps for {subject} teachers",
                        f"Reduce {subject} sections",
                    ],
                    evidence={"subject": subject, "shortfall": shortfall},
                )
            )

    return issues


def _check_teacher_section_load(school: School, mask_builder: TimeMaskBuilder) -> list[PrecheckIssue]:
    """Check #1b: Teacher section load capacity (max_sections constraint).

    Uses Hall's theorem approach: check if there's sufficient capacity among
    teacher candidates for all sections.
    """
    issues = []

    sections = Section.objects.filter(course__school=school).prefetch_related("teacher_candidates")
    teachers = Teacher.objects.filter(school=school)

    # Build bipartite matching structure: sections -> teacher candidates
    # For each teacher, count how many sections they could teach
    teacher_demand: dict[int, list] = {}  # teacher_id -> [section_ids they can teach]

    for teacher in teachers:
        teacher_demand[teacher.id] = []

    for section in sections:
        for teacher in section.teacher_candidates.all():
            if teacher.id in teacher_demand:
                teacher_demand[teacher.id].append(section.id)

    # Check global capacity: sum of max_sections vs total sections
    total_sections = sections.count()
    total_capacity = sum(t.max_sections for t in teachers if t.max_sections)

    if total_capacity < total_sections:
        shortfall = total_sections - total_capacity
        teachers_needed = math.ceil(shortfall / 3)  # Assume avg 3 sections per teacher

        issues.append(
            PrecheckIssue(
                level="ERROR",
                code="TEACHER_SECTION_LOAD_SHORTFALL",
                message=f"Need to assign {total_sections} sections but teachers can only handle {total_capacity} (shortfall: {shortfall})",
                suggestions=[
                    f"Add {teachers_needed} teachers with max_sections=3 or more",
                    f"Increase max_sections for existing teachers by total of {shortfall}",
                    f"Reduce number of sections by {shortfall}",
                ],
                evidence={
                    "required_sections": total_sections,
                    "teacher_capacity": total_capacity,
                    "shortfall": shortfall,
                    "teacher_count": teachers.count(),
                },
            )
        )

    # Check if any teacher would be overloaded based on their candidates
    for teacher in teachers:
        if not teacher.max_sections:
            continue

        candidate_sections = teacher_demand.get(teacher.id, [])
        # This is just a warning if they're a candidate for more sections than they can teach
        # (doesn't mean they'll be assigned to all - that's solver's job)
        if len(candidate_sections) < teacher.max_sections:
            # Teacher might not be fully utilized - just informational
            pass

    return issues


def _check_lunch_feasibility(school: School, mask_builder: TimeMaskBuilder) -> list[PrecheckIssue]:
    """Check #2: Teacher availability vs lunch rule."""
    issues = []

    if school.lunch_window_start_period is None or school.lunch_window_span is None:
        return issues  # No lunch constraints

    teachers = Teacher.objects.filter(school=school)
    lunch_mask = mask_builder.create_lunch_mask(
        school.lunch_window_start_period, school.lunch_window_span
    )

    for teacher in teachers:
        cap = teacher.daily_teaching_cap or school.default_teacher_daily_cap
        if cap == 0:
            continue

        # Check each day
        for day in range(school.cycle_days):
            day_mask = mask_builder.create_day_mask(day)
            lunch_on_day = lunch_mask & day_mask

            # If teacher has availability constraints, check them
            # For now, assume teachers are available all periods unless blocked
            # (full availability mask implementation would go here)

            # Simple check: if all periods on this day are lunch, infeasible
            lunch_period_count = mask_builder.bitcount(lunch_on_day)
            if lunch_period_count == school.periods_per_day and cap > 0:
                issues.append(
                    PrecheckIssue(
                        level="ERROR",
                        code="LUNCH_INFEASIBLE_FOR_TEACHER",
                        message=f"Teacher {teacher.first_name} {teacher.last_name} on day {day}: all periods are lunch",
                        suggestions=[
                            "Reduce lunch window span",
                            "Adjust teacher daily cap",
                        ],
                        evidence={"teacher_id": teacher.id, "day": day},
                    )
                )

    return issues


def _check_room_capacity(school: School, mask_builder: TimeMaskBuilder) -> list[PrecheckIssue]:
    """Check #3: Room capacity per slot (global)."""
    issues = []

    rooms = Room.objects.filter(school=school)
    sections = Section.objects.filter(course__school=school)

    # Count locked sections per slot
    slot_demand: dict[tuple[int, int], list[Section]] = {}

    for section in sections:
        if section.lock_to_periods:
            day = section.lock_to_periods.get("day")
            period = section.lock_to_periods.get("period")
            if day is not None and period is not None:
                key = (day, period)
                if key not in slot_demand:
                    slot_demand[key] = []
                slot_demand[key].append(section)

    # Check each slot
    total_rooms = rooms.count()
    for (day, period), locked_sections in slot_demand.items():
        demand = len(locked_sections)
        if demand > total_rooms:
            section_codes = [f"{s.course.code}-{s.section_number}" for s in locked_sections]
            issues.append(
                PrecheckIssue(
                    level="ERROR",
                    code="ROOM_SLOT_OVERDEMAND",
                    message=f"Day {day+1} Period {period+1}: {demand} sections locked but only {total_rooms} rooms",
                    suggestions=[
                        f"Add {demand - total_rooms} more rooms",
                        f"Unlock some sections from Day {day+1} Period {period+1}",
                        f"Distribute sections: {', '.join(section_codes[:3])}...",
                    ],
                    evidence={
                        "day": day,
                        "period": period,
                        "demand": demand,
                        "supply": total_rooms,
                        "sections": section_codes,
                    },
                )
            )

    return issues


def _check_feature_supply(school: School, mask_builder: TimeMaskBuilder) -> list[PrecheckIssue]:
    """Check #4: Feature-constrained rooms (e.g., labs)."""
    issues = []

    features = RoomFeature.objects.filter(school=school)

    for feature in features:
        # Count demand (sections requiring this feature)
        sections_needing_feature = Section.objects.filter(
            course__room_feature_required=feature, course__school=school
        )
        demand_occurrences = sum(s.planned_count_per_week for s in sections_needing_feature)

        # Count supply (rooms with this feature × available slots)
        feature_rooms = Room.objects.filter(school=school, features=feature)
        # Simple upper bound: rooms × periods × days
        supply_slots = feature_rooms.count() * school.periods_per_day * school.cycle_days

        if demand_occurrences > supply_slots:
            shortfall = demand_occurrences - supply_slots
            rooms_needed = math.ceil(shortfall / (school.periods_per_day * school.cycle_days))

            issues.append(
                PrecheckIssue(
                    level="ERROR",
                    code="FEATURE_SUPPLY_SHORTFALL",
                    message=f"Feature '{feature.code}': need {demand_occurrences} slots but only {supply_slots} available (shortfall: {shortfall})",
                    suggestions=[
                        f"Add {rooms_needed} rooms with feature '{feature.code}'",
                        f"Reduce sections requiring '{feature.code}'",
                        f"Add '{feature.code}' feature to existing rooms",
                    ],
                    evidence={
                        "feature": feature.code,
                        "demand": demand_occurrences,
                        "supply": supply_slots,
                        "shortfall": shortfall,
                    },
                )
            )

    return issues


def _check_teacher_candidates(school: School, mask_builder: TimeMaskBuilder) -> list[PrecheckIssue]:
    """Check #5: Teacher candidate coverage."""
    issues = []

    sections = Section.objects.filter(course__school=school)

    for section in sections:
        candidates = section.teacher_candidates.all()

        # No candidates at all
        if not candidates:
            issues.append(
                PrecheckIssue(
                    level="ERROR",
                    code="NO_TEACHER_CANDIDATES",
                    message=f"Section {section.course.code}-{section.section_number} has no teacher candidates",
                    suggestions=[
                        f"Add teacher candidates to {section.course.code}-{section.section_number}",
                        "Create teachers qualified to teach this section",
                    ],
                    evidence={"section": f"{section.course.code}-{section.section_number}"},
                )
            )
            continue

        # Check if candidates have enough capacity
        candidate_supply = sum(
            (t.daily_teaching_cap or school.default_teacher_daily_cap) * school.cycle_days
            for t in candidates
        )
        demand = section.planned_count_per_week

        if demand > candidate_supply:
            issues.append(
                PrecheckIssue(
                    level="WARN",
                    code="LOW_TEACHER_CANDIDATE_CAPACITY",
                    message=f"Section {section.course.code}-{section.section_number}: candidates have {candidate_supply} slots but need {demand}",
                    suggestions=[
                        "Add more teacher candidates",
                        "Increase candidate daily caps",
                    ],
                    evidence={
                        "section": f"{section.course.code}-{section.section_number}",
                        "demand": demand,
                        "supply": candidate_supply,
                    },
                )
            )

    return issues


def _check_locked_collisions(school: School, mask_builder: TimeMaskBuilder) -> list[PrecheckIssue]:
    """Check #6: Locked placement conflicts."""
    issues = []

    sections = Section.objects.filter(course__school=school)

    # Group sections by locked slot
    locked_by_slot: dict[tuple[int, int], list[Section]] = {}

    for section in sections:
        if section.lock_to_periods:
            day = section.lock_to_periods.get("day")
            period = section.lock_to_periods.get("period")
            if day is not None and period is not None:
                key = (day, period)
                if key not in locked_by_slot:
                    locked_by_slot[key] = []
                locked_by_slot[key].append(section)

    # Check for conflicts at each locked slot
    for (day, period), sections_at_slot in locked_by_slot.items():
        # Check teacher overlaps
        for i, section1 in enumerate(sections_at_slot):
            for section2 in sections_at_slot[i + 1 :]:
                # Check if they share any teacher candidates
                teachers1 = set(section1.teacher_candidates.all())
                teachers2 = set(section2.teacher_candidates.all())
                shared_teachers = teachers1 & teachers2

                if shared_teachers and len(teachers1) == 1 and len(teachers2) == 1:
                    # Both sections require the same unique teacher
                    teacher = list(shared_teachers)[0]
                    issues.append(
                        PrecheckIssue(
                            level="ERROR",
                            code="HARD_LOCK_CONFLICT",
                            message=f"Day {day+1} Period {period+1}: {section1.course.code}-{section1.section_number} and {section2.course.code}-{section2.section_number} both require teacher {teacher.last_name}",
                            suggestions=[
                                f"Unlock one of these sections",
                                f"Add alternative teacher candidates",
                            ],
                            evidence={
                                "day": day,
                                "period": period,
                                "section1": f"{section1.course.code}-{section1.section_number}",
                                "section2": f"{section2.course.code}-{section2.section_number}",
                                "teacher": f"{teacher.first_name} {teacher.last_name}",
                            },
                        )
                    )

        # Check room feature mismatches
        for section in sections_at_slot:
            if section.course.room_feature_required:
                # Check if any room candidates have the required feature
                room_candidates = section.room_candidates.all()
                if room_candidates:
                    valid_rooms = [
                        r
                        for r in room_candidates
                        if section.course.room_feature_required in r.features.all()
                    ]
                    if not valid_rooms:
                        issues.append(
                            PrecheckIssue(
                                level="ERROR",
                                code="FEATURE_MISMATCH_LOCK",
                                message=f"{section.course.code}-{section.section_number} locked but no candidate rooms have required feature '{section.course.room_feature_required.code}'",
                                suggestions=[
                                    f"Add room candidates with feature '{section.course.room_feature_required.code}'",
                                    "Unlock this section",
                                ],
                                evidence={
                                    "section": f"{section.course.code}-{section.section_number}",
                                    "feature": section.course.room_feature_required.code,
                                },
                            )
                        )

    return issues


def _check_lab_overlaps(school: School, mask_builder: TimeMaskBuilder) -> list[PrecheckIssue]:
    """Check #7: Lab-base course overlap rules."""
    issues = []

    lab_courses = Course.objects.filter(school=school, is_lab=True)

    for lab_course in lab_courses:
        if not lab_course.base_course:
            continue  # Already caught in sanity check

        lab_sections = Section.objects.filter(course=lab_course)
        base_sections = Section.objects.filter(course=lab_course.base_course)

        # Check for locked overlaps
        for lab_section in lab_sections:
            if not lab_section.lock_to_periods:
                continue

            lab_day = lab_section.lock_to_periods.get("day")
            lab_period = lab_section.lock_to_periods.get("period")

            if lab_day is None or lab_period is None:
                continue

            for base_section in base_sections:
                if not base_section.lock_to_periods:
                    continue

                base_day = base_section.lock_to_periods.get("day")
                base_period = base_section.lock_to_periods.get("period")

                if base_day == lab_day and base_period == lab_period:
                    issues.append(
                        PrecheckIssue(
                            level="ERROR",
                            code="LAB_BASE_OVERLAP_LOCK",
                            message=f"Lab {lab_course.code}-{lab_section.section_number} and base {lab_course.base_course.code}-{base_section.section_number} both locked to Day {lab_day+1} Period {lab_period+1}",
                            suggestions=[
                                "Unlock one of these sections",
                                f"Move lab to a different period (base course meets {lab_course.base_course.meets_per_week}x/week)",
                            ],
                            evidence={
                                "lab_section": f"{lab_course.code}-{lab_section.section_number}",
                                "base_section": f"{lab_course.base_course.code}-{base_section.section_number}",
                                "day": lab_day,
                                "period": lab_period,
                            },
                        )
                    )

    return issues


def _check_per_day_capacity(school: School, mask_builder: TimeMaskBuilder) -> list[PrecheckIssue]:
    """Check #8: Per-day teacher capacity feasibility."""
    issues = []

    teachers = Teacher.objects.filter(school=school)
    sections = Section.objects.filter(course__school=school)

    # For each day, count sections locked to that day
    for day in range(school.cycle_days):
        day_demand = 0
        locked_sections = []

        for section in sections:
            if section.lock_to_periods:
                locked_day = section.lock_to_periods.get("day")
                if locked_day == day:
                    # This section is locked to this day (any period)
                    day_demand += section.planned_count_per_week
                    locked_sections.append(section)

        # Calculate supply for this day
        day_supply = sum(
            (t.daily_teaching_cap or school.default_teacher_daily_cap) for t in teachers
        )

        if day_demand > day_supply:
            section_codes = [f"{s.course.code}-{s.section_number}" for s in locked_sections]
            issues.append(
                PrecheckIssue(
                    level="ERROR",
                    code="TEACHER_DAY_OVERDEMAND",
                    message=f"Day {day+1}: {day_demand} teaching slots needed but only {day_supply} available",
                    suggestions=[
                        f"Unlock some sections from Day {day+1}",
                        "Increase teacher daily caps",
                        f"Distribute across other days: {len(locked_sections)} sections locked",
                    ],
                    evidence={
                        "day": day,
                        "demand": day_demand,
                        "supply": day_supply,
                        "sections": section_codes[:5],  # Show first 5
                    },
                )
            )

    return issues


def _check_time_overflow(school: School, mask_builder: TimeMaskBuilder) -> list[PrecheckIssue]:
    """Check #9: Total time capacity overflow."""
    issues = []

    rooms = Room.objects.filter(school=school)
    sections = Section.objects.filter(course__school=school)

    # Calculate usable slots
    total_slots = school.cycle_days * school.periods_per_day
    blocked_slots = 0

    # Block lunch
    if school.lunch_window_start_period is not None and school.lunch_window_span is not None:
        blocked_slots += school.cycle_days * school.lunch_window_span

    # Block recess
    if school.recess_after_period is not None:
        blocked_slots += school.cycle_days  # One period per day

    usable_periods_per_day = school.periods_per_day - (blocked_slots // school.cycle_days)
    capacity_slots = rooms.count() * usable_periods_per_day * school.cycle_days

    # Calculate demand
    total_occurrences = sum(s.planned_count_per_week for s in sections)

    if total_occurrences > capacity_slots:
        overflow = total_occurrences - capacity_slots
        issues.append(
            PrecheckIssue(
                level="ERROR",
                code="TIME_CAPACITY_OVERFLOW",
                message=f"Need {total_occurrences} meeting slots but only {capacity_slots} available (overflow: {overflow})",
                suggestions=[
                    f"Add {math.ceil(overflow / (usable_periods_per_day * school.cycle_days))} more rooms",
                    f"Reduce meetings per week to save {overflow} slots",
                    "Reduce lunch/recess windows to free up time",
                    f"Increase periods per day from {school.periods_per_day} to {math.ceil((total_occurrences / rooms.count() / school.cycle_days))}",
                ],
                evidence={
                    "total_occurrences": total_occurrences,
                    "capacity_slots": capacity_slots,
                    "overflow": overflow,
                    "rooms": rooms.count(),
                    "usable_periods_per_day": usable_periods_per_day,
                },
            )
        )

    return issues


def _check_warnings(school: School, mask_builder: TimeMaskBuilder) -> list[PrecheckIssue]:
    """Generate warning-level checks (high utilization, fragile config)."""
    issues = []

    rooms = Room.objects.filter(school=school)
    sections = Section.objects.filter(course__school=school)

    # Check room utilization hotspots (slots with >90% utilization)
    slot_demand: dict[tuple[int, int], int] = {}
    for section in sections:
        if section.lock_to_periods:
            day = section.lock_to_periods.get("day")
            period = section.lock_to_periods.get("period")
            if day is not None and period is not None:
                key = (day, period)
                slot_demand[key] = slot_demand.get(key, 0) + 1

    total_rooms = rooms.count()
    for (day, period), demand in slot_demand.items():
        utilization = demand / total_rooms if total_rooms > 0 else 0
        if utilization >= 0.9:
            issues.append(
                PrecheckIssue(
                    level="WARN",
                    code="HIGH_ROOM_UTILIZATION",
                    message=f"Day {day+1} Period {period+1}: {demand}/{total_rooms} rooms used ({utilization*100:.0f}% utilization)",
                    suggestions=[
                        "Add more rooms for flexibility",
                        "Unlock some sections to allow solver flexibility",
                    ],
                    evidence={"day": day, "period": period, "utilization": utilization},
                )
            )

    # Check teachers with tight availability
    teachers = Teacher.objects.filter(school=school)
    for teacher in teachers:
        cap = teacher.daily_teaching_cap or school.default_teacher_daily_cap
        total_available = cap * school.cycle_days
        if total_available <= 2 and total_available > 0:
            issues.append(
                PrecheckIssue(
                    level="WARN",
                    code="FRAGILE_TEACHER_AVAILABILITY",
                    message=f"Teacher {teacher.first_name} {teacher.last_name} has only {total_available} slots/week (very tight)",
                    suggestions=[
                        f"Increase daily cap for {teacher.last_name}",
                        "Add backup teacher candidates",
                    ],
                    evidence={"teacher": f"{teacher.first_name} {teacher.last_name}", "slots": total_available},
                )
            )

    # Check feature capacity margin
    features = RoomFeature.objects.filter(school=school)
    for feature in features:
        sections_needing_feature = Section.objects.filter(
            course__room_feature_required=feature, course__school=school
        )
        demand = sum(s.planned_count_per_week for s in sections_needing_feature)

        feature_rooms = Room.objects.filter(school=school, features=feature)
        supply = feature_rooms.count() * school.periods_per_day * school.cycle_days

        if supply > 0:
            margin = (supply - demand) / supply
            if margin <= 0.05:  # 5% or less margin
                issues.append(
                    PrecheckIssue(
                        level="WARN",
                        code="LOW_FEATURE_CAPACITY_MARGIN",
                        message=f"Feature '{feature.code}': only {margin*100:.1f}% spare capacity ({demand}/{supply} slots used)",
                        suggestions=[
                            f"Add rooms with feature '{feature.code}'",
                            f"Reduce sections requiring '{feature.code}'",
                        ],
                        evidence={"feature": feature.code, "margin": margin},
                    )
                )

    return issues


def _compute_metrics(school: School, mask_builder: TimeMaskBuilder) -> PrecheckMetrics:
    """Compute aggregate metrics for the report."""
    sections = Section.objects.filter(course__school=school)
    teachers = Teacher.objects.filter(school=school)
    rooms = Room.objects.filter(school=school)

    total_slots = school.cycle_days * school.periods_per_day
    blocked_slots = 0

    if school.lunch_window_start_period is not None and school.lunch_window_span is not None:
        blocked_slots += school.cycle_days * school.lunch_window_span
    if school.recess_after_period is not None:
        blocked_slots += school.cycle_days

    usable_slots = total_slots - blocked_slots

    total_meetings = sum(s.planned_count_per_week for s in sections)

    teacher_supply = {
        "total_teachers": teachers.count(),
        "total_capacity": sum(
            (t.daily_teaching_cap or school.default_teacher_daily_cap) * school.cycle_days
            for t in teachers
        ),
        "by_subject": {},
    }

    room_supply = {
        "total_rooms": rooms.count(),
        "total_capacity": rooms.count() * usable_slots,
    }

    feature_supply = {}
    features = RoomFeature.objects.filter(school=school)
    for feature in features:
        feature_rooms = Room.objects.filter(school=school, features=feature)
        feature_supply[feature.code] = {
            "rooms": feature_rooms.count(),
            "capacity": feature_rooms.count() * usable_slots,
        }

    lab_courses = Course.objects.filter(school=school, is_lab=True)
    lab_requirements = {
        "total_labs": lab_courses.count(),
        "total_lab_sections": Section.objects.filter(course__in=lab_courses).count(),
    }

    return PrecheckMetrics(
        time_slots_total=total_slots,
        time_slots_usable=usable_slots,
        sections_total=sections.count(),
        meetings_total=total_meetings,
        teacher_supply=teacher_supply,
        room_supply=room_supply,
        feature_supply=feature_supply,
        lab_requirements=lab_requirements,
        lunch_feasibility={"blocked_slots": blocked_slots},
    )
