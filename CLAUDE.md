# School Scheduling System - Project Specification

## System Overview

Production-ready Django app for K-12 school timetabling using CP-SAT (Google OR-Tools).

**Tech Stack:**
- Python 3.11+, Django 5+, PostgreSQL
- Google OR-Tools (CP-SAT solver)
- Celery + Redis (async task processing)
- HTMX + Tailwind CSS (frontend)
- Docker + Docker Compose

## High-Level Goals

1. **Splash/Setup Page**: Single form with all school configuration
   - Period lengths, days, lunch windows, teacher caps, course requirements
   - Room features, lab rules, etc.
   - Actions: Save, Run, Cancel

2. **Solver Execution**: Produces weekly Master Schedule
   - Sections placed in time slots
   - Teacher + room assignments

3. **Results Landing Page**: Multiple reports
   - Master schedule grid (day/period × room/teacher/course)
   - Per-teacher schedules
   - Per-student schedules (after second-stage assignment)
   - Constraint/feasibility diagnostics
   - Soft-penalty summary

4. **Persistence**: Store configurations and results for re-viewing, cloning, re-running

## Core Domain Model

### Apps Structure
- `core`: School, Room, RoomFeature, Teacher, Student, Group
- `timetable`: Course, Section, RequirementTemplate, Scenario, Placement, StudentEnrollment
- `solver`: Constraint solver engine

### Models

**School**
- name, timezone, cycle_days, periods_per_day
- period_minutes, recess_after_period
- lunch_window_start_period, lunch_window_span
- default_teacher_daily_cap
- notes

**Room**
- school (FK), name, capacity
- features (M2M RoomFeature)

**RoomFeature**
- school (FK), code, description

**Teacher**
- school (FK), first_name, last_name, email
- daily_teaching_cap
- available_mask (JSON)

**Student**
- school (FK), first_name, last_name, grade
- attributes (JSON) - IEP flags, ELL level

**Group**
- school (FK), name, predicate (JSON)
- students (M2M)

**Course**
- school (FK), code, name
- duration_periods, meets_per_week
- is_lab, base_course (self-FK)
- room_feature_required (FK RoomFeature)
- capacity

**RequirementTemplate**
- school (FK), name
- selector (JSON) - student predicates
- required_courses (JSON)
- lab_policy (JSON)

**Section**
- course (FK)
- teacher_candidates (M2M Teacher)
- room_candidates (M2M Room)
- planned_count_per_week
- lock_to_periods (JSON)

**Scenario**
- school (FK), name
- config (JSON snapshot)
- status: DRAFT | RUNNING | SOLVED | INFEASIBLE | FAILED
- logs

**Placement** (solver output)
- scenario (FK), section (FK)
- day, period, room (FK), teacher (FK)
- is_lab

**StudentEnrollment** (assignment output)
- scenario (FK), student (FK), section (FK)
- day, period

## Solver Design

### Stage A: Master Schedule (CP-SAT)
Place all Section occurrences as optional interval vars over (day, period).

**Hard Constraints:**
- No teacher/room conflicts (≤1 per slot via NoOverlap)
- Respect teacher daily cap (≤3 including labs)
- Room feature match (lab → LAB room)
- Lunch/recess blocks
- Lab frequency: 1-2 placements/week per base course
- Lab not concurrent with base course

**Soft Constraints (Objective):**
- Spread sections across week
- Discourage edge-stacking
- Honor preferred times
- Balance room/teacher load

### Stage B: Student Assignment (MIP/CP)
After Stage A succeeds, assign students to non-conflicting placed sections.

**Hard Constraints:**
- Fulfill RequirementTemplate requirements
- Enforce capacity
- No student overlaps
- Lunch rule: student free for ≥1 period in lunch window

**Soft Constraints:**
- Minimize gaps
- Keep cohorts together

**Feasibility Diagnostics:**
- Human-readable proof on failure
- Actionable messages (teacher capacity, lab room scarcity)

## URL Structure

- `/` → List Schools + "Create School"
- `/schools/<id>/scenario/new` → Splash Setup Form
- `/scenarios/<id>` → Scenario detail with Run action
- `/scenarios/<id>/results` → Results landing page
  - Master schedule grid
  - Teacher schedules tab
  - Student schedules tab
  - Diagnostics panel
  - Export CSV, Clone Scenario, Edit Config

## API Endpoints (minimal)

- `GET /api/scenarios/<id>/status` → {status, message}
- `POST /api/scenarios/<id>/run` → Enqueue Celery job
- `GET /api/scenarios/<id>/export` → JSON config/results

## Seed Data Requirements

**One School:**
- 5 days, 8 periods, 50 mins
- Recess after period 2
- Lunch window: start period 4, span=2

**Rooms:** 4 regular, 1 lab, 1 gym

**Teachers:** 8 with caps=3/day

**Students:** 60 across grades 9-10 (some with IEP=true)

**Courses:**
- ENG9, MATH1, HIST9, SCI9 (+ SCI9_LAB base=SCI9)
- PE, ART

**Sections:** 1-2 per course with teacher/room candidates

**RequirementTemplates:**
- Grade 9 → {ENG9, MATH1, HIST9, SCI9, PE}
- Lab policy for SCI9 (min 1 max 2/week)

## Project Structure

```
project/
  manage.py
  pyproject.toml (ruff, black, mypy)
  docker-compose.yml
  .env.example
  README.md
  server/ (settings, celery.py)
  core/ (School, Room, RoomFeature, Teacher, Student, Group)
  timetable/ (Course, Section, RequirementTemplate, Scenario, Placement, StudentEnrollment)
  solver/ (engine.py, assignment.py, diagnostics.py, tests)
  templates/
    base.html
    schools/
    scenarios/
    partials/
  static/
```

## Development Setup

**Docker Compose Services:**
- web (Django)
- worker (Celery)
- redis
- postgres

**Make Commands:**
- `make up`, `make down`, `make test`, `make fmt`, `make lint`

## Code Quality

- Type hints throughout (mypy --strict)
- Formatted with black
- Linted with ruff
- pytest with pytest-django
- All models include: created_at/updated_at, indexes, __str__

## Testing Requirements

Minimum 6 unit tests covering:
- Config validation (minutes, capacity)
- Solver tiny instances (3 teachers, 2 rooms, 6 students)
- Student assignment coverage
- Lunch rule
- Lab frequency rule
- Snapshot tests for HTML responses

## Nice-to-Haves

- Clone scenario (deep copy)
- CSV exports (teacher/student/master schedules)
- Constraint inspector ("why can't I move X?")

## Development Principles

1. Correctness over clever UI
2. Comment solver code thoroughly
3. Simple interval/block models over premature generalization
4. Maintainability and testability first
5. Keep first pass minimal but real
