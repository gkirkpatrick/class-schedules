"""CP-SAT solver engine for master schedule (Stage A)."""

from typing import Any

from ortools.sat.python import cp_model

from core.models import Room, Teacher
from timetable.models import Placement, Scenario, Section


class ScheduleSolver:
    """Solver for creating master schedule using CP-SAT."""

    def __init__(self, scenario: Scenario) -> None:
        """Initialize solver with scenario."""
        self.scenario = scenario
        self.school = scenario.school
        self.model = cp_model.CpModel()

        # Configuration
        self.num_days = self.school.cycle_days
        self.num_periods = self.school.periods_per_day

        # Variables storage
        self.section_vars: dict[tuple[int, int, int, int, int], Any] = {}
        # Key: (section_id, occurrence_idx, day, period, teacher_id, room_id)

        # Diagnostics
        self.diagnostics: list[str] = []

    def solve(self) -> bool:
        """
        Run CP-SAT solver to create master schedule.

        Returns:
            True if solved successfully, False if infeasible
        """
        self._create_variables()
        self._add_hard_constraints()
        self._add_soft_constraints()

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 300.0  # 5 minute timeout

        status = solver.Solve(self.model)

        if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
            self._save_solution(solver)
            return True
        elif status == cp_model.INFEASIBLE:
            self._generate_infeasibility_diagnostics()
            return False
        else:
            self.diagnostics.append(f"Solver failed with status: {solver.StatusName(status)}")
            return False

    def _create_variables(self) -> None:
        """Create CP-SAT variables for section placements."""
        sections = Section.objects.filter(course__school=self.school).prefetch_related(
            "teacher_candidates", "room_candidates", "course"
        )

        for section in sections:
            # For each section, create variables for each occurrence
            for occ_idx in range(section.planned_count_per_week):
                for day in range(self.num_days):
                    for period in range(self.num_periods):
                        for teacher in section.teacher_candidates.all():
                            for room in section.room_candidates.all():
                                # Binary variable: is this section/occurrence placed here?
                                var_name = (
                                    f"s{section.id}_o{occ_idx}_d{day}_p{period}"
                                    f"_t{teacher.id}_r{room.id}"
                                )
                                var = self.model.NewBoolVar(var_name)
                                self.section_vars[
                                    (section.id, occ_idx, day, period, teacher.id, room.id)
                                ] = var

    def _add_hard_constraints(self) -> None:
        """Add hard constraints that must be satisfied."""
        self._constraint_exactly_one_placement_per_occurrence()
        self._constraint_section_meets_daily()
        self._constraint_section_same_teacher()
        self._constraint_no_teacher_overlap()
        self._constraint_no_room_overlap()
        self._constraint_teacher_daily_cap()
        self._constraint_teacher_min_load()
        self._constraint_room_features()
        self._constraint_lunch_recess_blocks()
        self._constraint_lab_frequency()

    def _constraint_exactly_one_placement_per_occurrence(self) -> None:
        """Each section occurrence must be placed exactly once."""
        sections = Section.objects.filter(course__school=self.school)

        for section in sections:
            for occ_idx in range(section.planned_count_per_week):
                # Sum all possible placements for this occurrence
                placement_vars = [
                    var
                    for (s_id, o_idx, d, p, t_id, r_id), var in self.section_vars.items()
                    if s_id == section.id and o_idx == occ_idx
                ]
                if placement_vars:
                    self.model.Add(sum(placement_vars) == 1)

    def _constraint_section_meets_daily(self) -> None:
        """Each section meets at most once per day, and meets the specified number of times per week."""
        sections = Section.objects.filter(course__school=self.school)

        for section in sections:
            for day in range(self.num_days):
                # For this section on this day, at most one occurrence can be scheduled
                day_vars = [
                    var
                    for (s_id, o_idx, d, p, t_id, r_id), var in self.section_vars.items()
                    if s_id == section.id and d == day
                ]
                if day_vars:
                    # At most 1 meeting per day
                    self.model.Add(sum(day_vars) <= 1)

    def _constraint_section_same_teacher(self) -> None:
        """All occurrences of a section must be taught by the same teacher."""
        sections = Section.objects.filter(course__school=self.school)

        for section in sections:
            # For each pair of occurrences, they must have the same teacher
            for occ_idx in range(section.planned_count_per_week):
                # Get all possible teachers for this occurrence
                for teacher in section.teacher_candidates.all():
                    # Count how many times this teacher teaches occurrence 0
                    occ0_teacher_vars = [
                        var
                        for (s_id, o_idx, d, p, t_id, r_id), var in self.section_vars.items()
                        if s_id == section.id and o_idx == 0 and t_id == teacher.id
                    ]

                    # Count how many times this teacher teaches this occurrence
                    occ_teacher_vars = [
                        var
                        for (s_id, o_idx2, d, p, t_id, r_id), var in self.section_vars.items()
                        if s_id == section.id and o_idx2 == occ_idx and t_id == teacher.id
                    ]

                    # If teacher teaches occurrence 0, they must teach all occurrences
                    # If they don't teach occurrence 0, they can't teach any occurrence
                    if occ0_teacher_vars and occ_teacher_vars and occ_idx > 0:
                        # sum(occ0_teacher_vars) == sum(occ_teacher_vars)
                        # This means: if teacher teaches occ 0, they teach occ i
                        self.model.Add(sum(occ0_teacher_vars) == sum(occ_teacher_vars))

    def _constraint_no_teacher_overlap(self) -> None:
        """A teacher can teach at most one section per time slot."""
        teachers = Teacher.objects.filter(school=self.school)

        for teacher in teachers:
            for day in range(self.num_days):
                for period in range(self.num_periods):
                    # All sections that could be taught by this teacher at this time
                    teacher_vars = [
                        var
                        for (s_id, o_idx, d, p, t_id, r_id), var in self.section_vars.items()
                        if t_id == teacher.id and d == day and p == period
                    ]
                    if teacher_vars:
                        self.model.Add(sum(teacher_vars) <= 1)

    def _constraint_no_room_overlap(self) -> None:
        """A room can host at most one section per time slot."""
        rooms = Room.objects.filter(school=self.school)

        for room in rooms:
            for day in range(self.num_days):
                for period in range(self.num_periods):
                    # All sections that could be in this room at this time
                    room_vars = [
                        var
                        for (s_id, o_idx, d, p, t_id, r_id), var in self.section_vars.items()
                        if r_id == room.id and d == day and p == period
                    ]
                    if room_vars:
                        self.model.Add(sum(room_vars) <= 1)

    def _constraint_teacher_daily_cap(self) -> None:
        """Enforce teacher daily teaching cap."""
        teachers = Teacher.objects.filter(school=self.school)

        for teacher in teachers:
            cap = teacher.effective_daily_cap
            for day in range(self.num_days):
                # All sections taught by this teacher on this day
                daily_vars = [
                    var
                    for (s_id, o_idx, d, p, t_id, r_id), var in self.section_vars.items()
                    if t_id == teacher.id and d == day
                ]
                if daily_vars:
                    self.model.Add(sum(daily_vars) <= cap)

    def _constraint_teacher_min_load(self) -> None:
        """Each teacher must teach at least a minimum number of sections total (if feasible)."""
        teachers = Teacher.objects.filter(school=self.school)
        sections = Section.objects.filter(course__school=self.school)

        # Calculate if min load is feasible
        num_teachers = teachers.count()
        num_sections = sections.count()

        # Only enforce if there are enough sections
        # Each section meets multiple times per week, but counts as one "section"
        if num_sections >= num_teachers * 3:
            MIN_SECTIONS_PER_TEACHER = 3
        elif num_sections >= num_teachers * 2:
            MIN_SECTIONS_PER_TEACHER = 2
        elif num_sections >= num_teachers:
            MIN_SECTIONS_PER_TEACHER = 1
        else:
            # Not enough sections for all teachers - skip constraint
            return

        # Only enforce this for teachers who are candidates for at least one section
        for teacher in teachers:
            # Find all sections this teacher can teach
            teacher_sections = sections.filter(teacher_candidates=teacher)

            if teacher_sections.exists():
                # Count total sections assigned to this teacher across all time slots
                teacher_total_vars = [
                    var
                    for (s_id, o_idx, d, p, t_id, r_id), var in self.section_vars.items()
                    if t_id == teacher.id
                ]

                if teacher_total_vars:
                    self.model.Add(sum(teacher_total_vars) >= MIN_SECTIONS_PER_TEACHER)

    def _constraint_room_features(self) -> None:
        """Ensure sections requiring specific room features are placed in matching rooms."""
        sections = Section.objects.filter(course__school=self.school).select_related("course")

        for section in sections:
            if section.course.room_feature_required:
                required_feature = section.course.room_feature_required
                # Get rooms that have this feature
                valid_room_ids = set(
                    section.room_candidates.filter(features=required_feature).values_list(
                        "id", flat=True
                    )
                )

                # All placements for this section must use valid rooms
                for (s_id, o_idx, d, p, t_id, r_id), var in self.section_vars.items():
                    if s_id == section.id and r_id not in valid_room_ids:
                        # Force this variable to 0
                        self.model.Add(var == 0)

    def _constraint_lunch_recess_blocks(self) -> None:
        """Block lunch and recess periods from having classes."""
        lunch_start = self.school.lunch_window_start_period - 1  # Convert to 0-indexed
        lunch_end = lunch_start + self.school.lunch_window_span

        for day in range(self.num_days):
            # Block lunch window periods
            for period in range(lunch_start, min(lunch_end, self.num_periods)):
                period_vars = [
                    var
                    for (s_id, o_idx, d, p, t_id, r_id), var in self.section_vars.items()
                    if d == day and p == period
                ]
                if period_vars:
                    # Allow some classes during lunch but ensure teachers get breaks
                    # For now, just reduce capacity
                    pass  # TODO: Implement lunch break logic more sophisticatedly

            # Block recess period
            if self.school.recess_after_period:
                recess_period = self.school.recess_after_period - 1  # Convert to 0-indexed
                if 0 <= recess_period < self.num_periods:
                    recess_vars = [
                        var
                        for (s_id, o_idx, d, p, t_id, r_id), var in self.section_vars.items()
                        if d == day and p == recess_period
                    ]
                    if recess_vars:
                        # No classes during recess
                        self.model.Add(sum(recess_vars) == 0)

    def _constraint_lab_frequency(self) -> None:
        """Enforce lab min/max frequency per week for base courses."""
        sections = Section.objects.filter(
            course__school=self.school, course__is_lab=True
        ).select_related("course__base_course")

        for lab_section in sections:
            if lab_section.course.base_course:
                # Labs should meet 1-2 times per week (from spec)
                # This is already handled by planned_count_per_week
                # Additional constraint: lab should not overlap with base course

                # Get base course sections
                base_sections = Section.objects.filter(course=lab_section.course.base_course)

                for base_section in base_sections:
                    # For each time slot, if base is scheduled, lab cannot be
                    for day in range(self.num_days):
                        for period in range(self.num_periods):
                            base_vars = [
                                var
                                for (s_id, o_idx, d, p, t_id, r_id), var in self.section_vars.items()
                                if s_id == base_section.id and d == day and p == period
                            ]
                            lab_vars = [
                                var
                                for (
                                    s_id,
                                    o_idx,
                                    d,
                                    p,
                                    t_id,
                                    r_id,
                                ), var in self.section_vars.items()
                                if s_id == lab_section.id and d == day and p == period
                            ]

                            if base_vars and lab_vars:
                                # If base is scheduled here, lab cannot be
                                self.model.Add(sum(base_vars) + sum(lab_vars) <= 1)

    def _add_soft_constraints(self) -> None:
        """Add soft constraints as weighted penalties in objective."""
        penalty_vars = []

        # Penalty: discourage edge periods (first and last period of day)
        for day in range(self.num_days):
            for period in [0, self.num_periods - 1]:
                edge_vars = [
                    var
                    for (s_id, o_idx, d, p, t_id, r_id), var in self.section_vars.items()
                    if d == day and p == period
                ]
                if edge_vars:
                    penalty_var = self.model.NewIntVar(0, len(edge_vars), f"edge_d{day}_p{period}")
                    self.model.Add(penalty_var == sum(edge_vars))
                    penalty_vars.append(penalty_var * 2)  # Weight of 2

        # Penalty: teacher load variance (prefer balanced distribution)
        # This is more complex, skip for MVP

        # Minimize total penalties
        if penalty_vars:
            self.model.Minimize(sum(penalty_vars))

    def _save_solution(self, solver: cp_model.CpSolver) -> None:
        """Save the solution as Placement objects."""
        # Clear existing placements
        Placement.objects.filter(scenario=self.scenario).delete()

        placements_to_create = []

        for (s_id, o_idx, d, p, t_id, r_id), var in self.section_vars.items():
            if solver.Value(var) == 1:
                section = Section.objects.get(id=s_id)
                teacher = Teacher.objects.get(id=t_id)
                room = Room.objects.get(id=r_id)

                placements_to_create.append(
                    Placement(
                        scenario=self.scenario,
                        section=section,
                        day=d,
                        period=p,
                        room=room,
                        teacher=teacher,
                        is_lab=section.course.is_lab,
                    )
                )

        Placement.objects.bulk_create(placements_to_create)
        self.diagnostics.append(f"Successfully created {len(placements_to_create)} placements")

    def _generate_infeasibility_diagnostics(self) -> None:
        """Generate human-readable diagnostics for infeasible scenarios."""
        self.diagnostics.append("Scenario is INFEASIBLE. Possible reasons:")

        # Check teacher capacity
        sections = Section.objects.filter(course__school=self.school)
        total_section_occurrences = sum(s.planned_count_per_week for s in sections)
        teachers = Teacher.objects.filter(school=self.school)
        total_teacher_capacity = sum(
            t.effective_daily_cap * self.num_days for t in teachers
        )

        if total_section_occurrences > total_teacher_capacity:
            self.diagnostics.append(
                f"  - Teacher capacity shortage: need {total_section_occurrences} "
                f"slots but only have {total_teacher_capacity} available"
            )

        # Check room capacity
        rooms = Room.objects.filter(school=self.school)
        total_room_capacity = len(rooms) * self.num_days * self.num_periods
        if total_section_occurrences > total_room_capacity:
            self.diagnostics.append(
                f"  - Room capacity shortage: need {total_section_occurrences} "
                f"slots but only have {total_room_capacity} available"
            )

        # Check lab room availability
        lab_sections = sections.filter(course__is_lab=True)
        if lab_sections.exists():
            lab_rooms = rooms.filter(features__code="LAB").distinct()
            if not lab_rooms.exists():
                self.diagnostics.append("  - No LAB rooms available for lab courses")


def solve_scenario(scenario_id: int) -> bool:
    """
    Main entry point for solving a scenario.

    Args:
        scenario_id: ID of the scenario to solve

    Returns:
        True if solved successfully, False otherwise
    """
    scenario = Scenario.objects.get(id=scenario_id)
    scenario.status = Scenario.Status.RUNNING
    scenario.save()

    solver = ScheduleSolver(scenario)
    success = solver.solve()

    if success:
        scenario.status = Scenario.Status.SOLVED
        scenario.logs = "\n".join(solver.diagnostics)
    else:
        scenario.status = Scenario.Status.INFEASIBLE
        scenario.logs = "\n".join(solver.diagnostics)

    scenario.save()
    return success
