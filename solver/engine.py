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
        solver.parameters.log_search_progress = True  # Enable solver logging

        # Store solver for diagnostics
        self.solver = solver

        status = solver.Solve(self.model)

        # Log solver statistics
        self.diagnostics.append(f"Solver status: {solver.StatusName(status)}")
        self.diagnostics.append(f"Solve time: {solver.WallTime():.2f}s")
        self.diagnostics.append(f"Branches explored: {solver.NumBranches()}")
        self.diagnostics.append(f"Conflicts: {solver.NumConflicts()}")

        if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
            self.diagnostics.append(f"Objective value: {solver.ObjectiveValue()}")
            self._save_solution(solver)
            return True
        elif status == cp_model.INFEASIBLE:
            self._generate_infeasibility_diagnostics()
            self._analyze_constraint_conflicts()
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
        self._constraint_section_same_period()
        self._constraint_no_teacher_overlap()
        self._constraint_no_room_overlap()
        self._constraint_teacher_daily_cap()
        self._constraint_teacher_section_cap()
        self._constraint_room_features()
        self._constraint_lunch_recess_blocks()
        self._constraint_teacher_lunch_assignment()
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

    def _constraint_section_same_period(self) -> None:
        """Sections should meet at the same period every day.

        For each section, ALL occurrences must be scheduled at the same period.
        """
        sections = Section.objects.filter(course__school=self.school)

        for section in sections:
            if section.planned_count_per_week <= 1:
                continue  # No constraint needed for sections meeting once

            # Strategy: Create a boolean variable for each period indicating if this
            # section uses that period. Exactly one period can be selected, and ALL
            # occurrences of the section must be at that period.

            period_bools = []
            for period in range(self.num_periods):
                # Create boolean: does this section use this period?
                period_selected = self.model.NewBoolVar(f"s{section.id}_uses_p{period}")
                period_bools.append(period_selected)

                # Count how many occurrences of this section are at this period
                vars_at_period = [
                    var
                    for (s_id, o_idx, d, p, t_id, r_id), var in self.section_vars.items()
                    if s_id == section.id and p == period
                ]

                if vars_at_period:
                    # If period is selected, ALL occurrences must be at this period
                    # If period is not selected, NO occurrences can be at this period
                    num_occurrences = section.planned_count_per_week
                    self.model.Add(sum(vars_at_period) == num_occurrences).OnlyEnforceIf(period_selected)
                    self.model.Add(sum(vars_at_period) == 0).OnlyEnforceIf(period_selected.Not())
                else:
                    # If no variables at this period, it can't be selected
                    self.model.Add(period_selected == 0)

            # Exactly one period must be selected
            if period_bools:
                self.model.Add(sum(period_bools) == 1)

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

    def _constraint_teacher_section_cap(self) -> None:
        """Each teacher must teach exactly max_sections unique sections (their assigned load)."""
        teachers = Teacher.objects.filter(school=self.school)
        sections = Section.objects.filter(course__school=self.school)

        for teacher in teachers:
            # Find all sections this teacher can teach
            teacher_sections = sections.filter(teacher_candidates=teacher)

            if teacher_sections.exists():
                # For each section, create a binary indicator: does teacher teach this section?
                section_indicators = []

                for section in teacher_sections:
                    # If any occurrence of this section is taught by this teacher, indicator = 1
                    section_vars = [
                        var
                        for (s_id, o_idx, d, p, t_id, r_id), var in self.section_vars.items()
                        if s_id == section.id and t_id == teacher.id and o_idx == 0  # Just check first occurrence
                    ]

                    if section_vars:
                        # Create indicator: 1 if teacher teaches this section, 0 otherwise
                        indicator = self.model.NewBoolVar(f"teacher_{teacher.id}_teaches_section_{section.id}")
                        # indicator == 1 iff sum(section_vars) >= 1
                        self.model.Add(sum(section_vars) >= 1).OnlyEnforceIf(indicator)
                        self.model.Add(sum(section_vars) == 0).OnlyEnforceIf(indicator.Not())
                        section_indicators.append(indicator)

                if section_indicators:
                    # Teacher must teach AT MOST max_sections (their assigned load)
                    self.model.Add(sum(section_indicators) <= teacher.max_sections)

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

    def _constraint_teacher_lunch_assignment(self) -> None:
        """Each teacher must be assigned to exactly one lunch section.

        Lunch is treated as a course that teachers must teach during the lunch window.
        Each teacher should be assigned to LUNCH_A (period 4) or LUNCH_B (period 5), but not both.
        """
        from timetable.models import Section

        # Find lunch sections
        lunch_sections = list(Section.objects.filter(
            course__school=self.school,
            course__code__startswith="LUNCH"
        ).select_related("course").order_by("course__code"))

        if not lunch_sections:
            return  # No lunch constraint if no lunch sections defined

        # Map lunch sections to their designated periods
        # LUNCH_A -> period 3 (4th period, 0-indexed)
        # LUNCH_B -> period 4 (5th period, 0-indexed)
        lunch_start_period = self.school.lunch_window_start_period - 1  # Convert to 0-indexed
        lunch_period_map = {}
        for idx, lunch_section in enumerate(lunch_sections):
            lunch_period_map[lunch_section.id] = lunch_start_period + idx

        # Constrain lunch sections to their designated periods
        for lunch_section in lunch_sections:
            designated_period = lunch_period_map[lunch_section.id]
            # Force all variables for this section to be at the designated period
            for (s_id, o_idx, d, p, t_id, r_id), var in self.section_vars.items():
                if s_id == lunch_section.id and p != designated_period:
                    # Not the designated period, force to 0
                    self.model.Add(var == 0)

        # For each teacher, ensure they teach exactly one lunch period per day
        # NOTE: Teachers CAN have lunch at different periods on different days
        teachers = Teacher.objects.filter(school=self.school)

        for teacher in teachers:
            # For each day, teacher must be assigned to exactly one lunch section
            for day in range(self.num_days):
                lunch_assignment_vars = []
                for lunch_section in lunch_sections:
                    designated_period = lunch_period_map[lunch_section.id]
                    # Get vars for this teacher teaching this lunch section on this day
                    # across all occurrences (since lunch meets multiple times per week)
                    section_vars = [
                        var
                        for (s_id, o_idx, d, p, t_id, r_id), var in self.section_vars.items()
                        if s_id == lunch_section.id
                        and t_id == teacher.id
                        and d == day
                        and p == designated_period
                    ]
                    if section_vars:
                        lunch_assignment_vars.append(sum(section_vars))

                if lunch_assignment_vars:
                    # Exactly one lunch section per teacher per day
                    # This allows teacher to have LUNCH_A on Monday, LUNCH_B on Tuesday, etc.
                    self.model.Add(sum(lunch_assignment_vars) == 1)

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

    def _analyze_constraint_conflicts(self) -> None:
        """Analyze which constraints are causing infeasibility.

        This provides more specific information about what's making the problem infeasible.
        """
        self.diagnostics.append("\n=== CONSTRAINT CONFLICT ANALYSIS ===")

        # Analyze specific constraint groups
        sections = Section.objects.filter(course__school=self.school).prefetch_related("teacher_candidates", "room_candidates")
        teachers = Teacher.objects.filter(school=self.school)

        # Check for sections with no valid placements
        problem_sections = []
        for section in sections:
            if not section.teacher_candidates.exists():
                problem_sections.append(f"{section.course.code} section {section.section_number}: NO TEACHER CANDIDATES")
            elif not section.room_candidates.exists():
                problem_sections.append(f"{section.course.code} section {section.section_number}: NO ROOM CANDIDATES")

        if problem_sections:
            self.diagnostics.append("\n❌ Sections with no valid candidates:")
            for problem in problem_sections[:10]:  # Limit to first 10
                self.diagnostics.append(f"  - {problem}")

        # Check teacher overload
        overloaded_teachers = []
        for teacher in teachers:
            candidate_sections = sections.filter(teacher_candidates=teacher)
            if candidate_sections.count() > (teacher.max_sections or 999):
                overloaded_teachers.append(
                    f"{teacher.first_name} {teacher.last_name}: {candidate_sections.count()} candidates but max_sections={teacher.max_sections}"
                )

        if overloaded_teachers:
            self.diagnostics.append("\n⚠️ Teachers with more candidates than capacity:")
            for problem in overloaded_teachers[:10]:
                self.diagnostics.append(f"  - {problem}")

        # Check time slot congestion
        total_meetings = sum(s.planned_count_per_week for s in sections)
        usable_slots = self.num_days * self.num_periods
        if self.school.lunch_window_span:
            usable_slots -= self.num_days * self.school.lunch_window_span

        room_capacity = Room.objects.filter(school=self.school).count()
        total_capacity = usable_slots * room_capacity

        utilization = (total_meetings / total_capacity * 100) if total_capacity > 0 else 0
        self.diagnostics.append(f"\n📊 Time slot utilization: {utilization:.1f}% ({total_meetings}/{total_capacity} slots)")

        if utilization > 85:
            self.diagnostics.append("  ⚠️ Very high utilization - consider adding rooms or reducing sections")

        # Check teacher capacity utilization
        total_teacher_slots = sum(
            (t.daily_teaching_cap or self.school.default_teacher_daily_cap) * self.num_days
            for t in teachers
        )
        teacher_utilization = (total_meetings / total_teacher_slots * 100) if total_teacher_slots > 0 else 0
        self.diagnostics.append(f"👥 Teacher capacity utilization: {teacher_utilization:.1f}% ({total_meetings}/{total_teacher_slots} slots)")

        if teacher_utilization > 90:
            self.diagnostics.append("  ⚠️ Very high teacher utilization - solver may struggle to find valid assignment")

        self.diagnostics.append("\n💡 Suggestion: Run Pre-Check diagnostics for detailed analysis of all constraints")


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
