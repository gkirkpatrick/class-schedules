# School Scheduling System

A production-ready Django application for K-12 school timetabling using CP-SAT (Google OR-Tools) constraint programming solver.

## Overview

This system solves the complex problem of scheduling classes, teachers, rooms, and students for a school. It uses a two-stage approach:

1. **Stage A (Master Schedule)**: Uses CP-SAT to place all course sections into time slots with assigned teachers and rooms
2. **Stage B (Student Assignment)**: Uses MIP (Mixed Integer Programming) to assign students to sections while respecting constraints

## Features

- ✅ Constraint-based scheduling with Google OR-Tools CP-SAT
- ✅ Two-stage solving: master schedule + student assignment
- ✅ Hard constraints: no conflicts, capacity limits, teacher daily caps, room features, lunch/recess blocks
- ✅ Soft constraints: balanced distribution, minimize gaps, edge period penalties
- ✅ Async task processing with Celery
- ✅ Web UI with Tailwind CSS and HTMX
- ✅ Comprehensive diagnostics and feasibility reporting
- ✅ Seed data for testing

## Tech Stack

- **Backend**: Python 3.11+, Django 5+
- **Solver**: Google OR-Tools (CP-SAT), PuLP (MIP)
- **Task Queue**: Celery with Redis
- **Database**: SQLite (dev) / PostgreSQL (production)
- **Frontend**: Django Templates, Tailwind CSS, HTMX
- **Development**: ruff, black, mypy, pytest

## Project Structure

```
school_schedules/
├── core/                   # Core models (School, Room, Teacher, Student)
├── timetable/              # Scheduling models (Course, Section, Scenario, Placement)
├── solver/                 # CP-SAT and MIP solver engines
│   ├── engine.py          # Stage A: Master schedule solver
│   ├── assignment.py      # Stage B: Student assignment solver
│   ├── diagnostics.py     # Feasibility reporting
│   └── tasks.py           # Celery tasks
├── templates/             # Django templates with Tailwind CSS
├── server/                # Django settings and configuration
└── manage.py
```

## Quick Start

### 1. Set up virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Set up environment

```bash
cp .env.example .env
# Edit .env if needed (defaults work for development)
```

### 4. Run migrations

```bash
python manage.py migrate
```

### 5. Seed test data

```bash
python manage.py seed_data
```

This creates:
- 1 school (Lincoln High School)
- 6 rooms (4 regular, 1 lab, 1 gym)
- 8 teachers
- 60 students (grades 9-10)
- 7 courses (ENG9, MATH1, HIST9, SCI9, SCI9_LAB, PE, ART)
- 13 sections
- 2 requirement templates

### 6. Create a superuser

```bash
python manage.py createsuperuser
```

### 7. Run the development server

```bash
python manage.py runserver
```

Visit: http://127.0.0.1:8000

## Usage

### Creating and Running a Scenario

#### Via Django Admin

1. Go to http://127.0.0.1:8000/admin
2. Create a new **Scenario** for your school
3. Set status to "DRAFT"
4. Save the scenario

#### Via Django Shell

```python
python manage.py shell

from core.models import School
from timetable.models import Scenario

school = School.objects.first()
scenario = Scenario.objects.create(
    school=school,
    name="Fall 2024 Schedule",
    status="DRAFT"
)
```

#### Running the Solver

**Option 1: Via Web UI**
1. Navigate to the school detail page
2. Click on your scenario
3. Click "Run Solver"
4. Wait for completion (status will auto-refresh)

**Option 2: Via Django Shell**

```python
from solver.engine import solve_scenario
from solver.assignment import assign_students

# Run master schedule solver
solve_scenario(scenario.id)

# Run student assignment
assign_students(scenario.id)
```

**Option 3: With Celery (Async)**

Start Celery worker first:
```bash
# Make sure Redis is running
celery -A server worker -l info
```

Then trigger via shell:
```python
from solver.tasks import run_scenario_task
task = run_scenario_task.delay(scenario.id)
```

### Viewing Results

After a scenario is solved:

1. Navigate to scenario detail page
2. Click "View Results"
3. Explore tabs:
   - **Master Schedule**: All section placements
   - **Teacher Schedules**: Per-teacher views (coming soon)
   - **Student Schedules**: Per-student views (coming soon)
   - **Diagnostics**: Solver logs and feasibility info

## Architecture

### Domain Model

**Core Entities**:
- `School`: Configuration (days, periods, timing)
- `Room`: Physical spaces with features (LAB, GYM)
- `Teacher`: Instructors with daily caps
- `Student`: Students with grade and attributes (IEP, etc.)

**Timetable Entities**:
- `Course`: Subject offerings (code, capacity, lab requirements)
- `Section`: Course instances with teacher/room candidates
- `RequirementTemplate`: Student course requirements by grade/attributes
- `Scenario`: A scheduling attempt with config snapshot
- `Placement`: Solved section placement (day, period, teacher, room)
- `StudentEnrollment`: Student-section assignments

### Solver Algorithm

#### Stage A: Master Schedule (CP-SAT)

**Variables**: Binary variables for each (section, occurrence, day, period, teacher, room) combination

**Hard Constraints**:
- Each section occurrence placed exactly once
- No teacher/room conflicts (≤1 per slot)
- Teacher daily caps enforced
- Room features matched (lab courses → lab rooms)
- Lunch/recess periods blocked
- Lab courses meet 1-2x/week, not concurrent with base course

**Soft Constraints** (minimized in objective):
- Discourage edge periods (first/last of day)
- Balance teacher loads
- Spread sections across week

**Solver**: OR-Tools CP-SAT with 5-minute timeout

#### Stage B: Student Assignment (MIP)

**Variables**: Binary variables for each (student, placement) pair

**Hard Constraints**:
- No student time conflicts
- Section capacity limits
- Lunch requirement (≥1 free period in lunch window)
- Course requirements met (from RequirementTemplate)

**Soft Constraints**:
- Minimize schedule gaps
- Keep cohorts together

**Solver**: PuLP MIP solver

### Diagnostics

On infeasibility, the system reports:
- Teacher capacity shortages
- Room capacity issues
- Lab room availability
- Specific constraint violations

## Configuration

### School Settings

- `cycle_days`: Number of days in schedule cycle (e.g., 5 for weekly)
- `periods_per_day`: Periods per day (e.g., 8)
- `period_minutes`: Length of each period
- `recess_after_period`: Period after which recess occurs
- `lunch_window_start_period`: When lunch window begins (1-indexed)
- `lunch_window_span`: How many periods in lunch window
- `default_teacher_daily_cap`: Max periods per teacher per day

### Requirement Templates

Define which courses students need based on predicates:

```json
{
  "selector": {"grade": 9},
  "required_courses": [
    {"course_code": "ENG9", "count": 1},
    {"course_code": "MATH1", "count": 1}
  ],
  "lab_policy": {
    "SCI9": {"min_labs": 1, "max_labs": 2}
  }
}
```

## Development

### Code Quality

Format code:
```bash
black .
ruff check --fix .
```

Type check:
```bash
mypy .
```

### Testing

```bash
pytest
```

## API Endpoints

- `GET /api/scenarios/<id>/status/` - Get scenario status for polling
- `POST /api/scenarios/<id>/run/` - Trigger solver run
- `GET /api/scenarios/<id>/export/` - Export scenario as JSON

## Future Enhancements

- [ ] Full HTMX-powered scenario configuration form
- [ ] Grid-based master schedule view (day × period matrix)
- [ ] Per-teacher and per-student schedule views
- [ ] CSV export for all schedule types
- [ ] Scenario cloning
- [ ] Constraint inspector ("why can't I move X?")
- [ ] Multi-week rotating schedules
- [ ] Student preferences and cohort constraints
- [ ] More sophisticated soft constraints

## Troubleshooting

### Solver shows INFEASIBLE

Check diagnostics for:
- Not enough teachers (increase daily caps or add teachers)
- Not enough rooms (add rooms or reduce sections)
- Missing lab rooms (add rooms with LAB feature)
- Conflicting requirements (adjust requirement templates)

### Celery worker not processing

1. Make sure Redis is running: `redis-cli ping` (should return PONG)
2. Check Celery worker logs
3. Verify CELERY_BROKER_URL in .env

### No sections showing in schedule

1. Ensure sections have teacher_candidates and room_candidates set
2. Check that `planned_count_per_week` matches `course.meets_per_week`
3. Verify sections exist: `python manage.py shell` → `Section.objects.count()`

## License

MIT License (or your preferred license)

## Credits

Built for school scheduling interview project. Demonstrates:
- Constraint programming with CP-SAT
- Complex domain modeling
- Async task processing
- Modern web UI patterns
- Production-ready Django architecture
