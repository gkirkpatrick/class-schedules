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
- ✅ **Pre-Check diagnostics**: Fast validation before running solver (<200ms)
- ✅ **10 validation checks**: Sanity, capacity, lunch, rooms, features, candidates, locks, labs, daily limits, overflow
- ✅ **Actionable suggestions**: Specific fixes for each detected issue
- ✅ **Export formats**: JSON, CSV, Markdown for pre-check reports
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
│   ├── precheck.py        # Pre-solver validation system
│   ├── precheck_utils.py  # Bitmask utilities for time slots
│   └── tests/
│       ├── test_precheck.py              # Unit tests (26 checks)
│       └── test_precheck_performance.py  # Performance benchmarks
├── solver/                 # CP-SAT and MIP solver engines
│   ├── engine.py          # Stage A: Master schedule solver
│   ├── assignment.py      # Stage B: Student assignment solver
│   ├── diagnostics.py     # Post-solve feasibility reporting
│   └── tasks.py           # Celery tasks
├── templates/             # Django templates with Tailwind CSS
│   └── scenarios/
│       ├── detail.html           # Scenario page with Pre-Check button
│       └── precheck_report.html  # Pre-check results display
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

### Pre-Check Diagnostics

**Before running the solver**, use the Pre-Check feature to validate your configuration and detect potential issues:

**Via Web UI**:
1. Navigate to scenario detail page
2. Click "🔍 Pre-Check" button
3. Review the report:
   - **OK** ✅ - Ready to run solver
   - **WARN** ⚠️ - Can run but may struggle
   - **FAIL** ❌ - Must fix errors before running

**Via API**:
```bash
curl http://localhost:8000/api/scenarios/1/precheck/
```

**Via Django Shell**:
```python
from timetable.precheck import run_precheck

report = run_precheck(school_id=1)
print(report.status)  # "OK", "WARN", or "FAIL"
print(f"Issues: {len(report.issues)}")

# Export formats
report.to_dict()      # JSON-serializable
report.to_csv()       # CSV format
report.to_markdown()  # Markdown report
```

**What Pre-Check Validates**:

✅ **Check #0: Sanity** - Invalid configurations (lunch periods, meeting counts)
✅ **Check #1: Teacher Capacity** - Global teacher supply vs demand
✅ **Check #2: Lunch Feasibility** - Teachers can get lunch breaks
✅ **Check #3: Room Capacity** - Enough rooms per time slot
✅ **Check #4: Feature Supply** - Specialized rooms (labs, gyms)
✅ **Check #5: Teacher Candidates** - Each section has qualified teachers
✅ **Check #6: Locked Collisions** - Pre-locked placements don't conflict
✅ **Check #7: Lab Overlaps** - Labs don't overlap with base courses
✅ **Check #8: Per-Day Capacity** - Daily teacher limits are feasible
✅ **Check #9: Time Overflow** - Total time demand vs supply
⚠️ **Warnings** - Utilization hotspots that may cause solver struggles

**Export Options**:
- JSON: `/api/scenarios/<id>/precheck/`
- CSV: `/scenarios/<id>/precheck/export/csv/`
- Markdown: `/scenarios/<id>/precheck/export/markdown/`

**Performance**: Pre-check runs in < 200ms for typical schools (100 sections, 60 teachers, 40 time slots)

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

### Pre-Check Diagnostics System

**Before the solver runs**, the Pre-Check system performs fast feasibility validation using bitmask operations and vectorized counting (O(S + R + M + T) complexity).

**Validation Checks**:

0. **Sanity**: Detects invalid configurations (lunch periods out of range, invalid meeting counts, orphan labs)
1. **Teacher Capacity**: Global lower bound check (required slots vs total teacher capacity)
2. **Lunch Feasibility**: Ensures teachers can get lunch breaks given section meetings
3. **Room Capacity**: Per-slot room availability check
4. **Feature Supply**: Validates specialized room availability (labs, gyms)
5. **Teacher Candidates**: Hall-type necessary condition for teacher assignment
6. **Locked Collisions**: Detects conflicts in pre-locked placements
7. **Lab Overlaps**: Ensures labs don't overlap with base courses
8. **Per-Day Capacity**: Checks daily teacher limits are feasible
9. **Time Overflow**: Detects if total time demand exceeds supply

**Output Structure**:
```python
@dataclass
class PrecheckReport:
    status: Literal["FAIL", "WARN", "OK"]
    issues: list[PrecheckIssue]
    metrics: PrecheckMetrics
```

**Each issue includes**:
- Level: ERROR, WARN, or INFO
- Code: Machine-readable error code
- Message: Human-readable description
- Suggestions: Actionable fixes
- Evidence: Supporting data (counts, shortfalls, etc.)

**Performance**: Runs in < 200ms for 100 sections, 60 teachers, 40 time slots using bitmask operations.

### Post-Solve Diagnostics

On solver infeasibility, the system reports:
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

### Scenario Management
- `GET /api/scenarios/<id>/status/` - Get scenario status for polling
- `POST /api/scenarios/<id>/run/` - Trigger solver run
- `GET /api/scenarios/<id>/export/` - Export scenario as JSON

### Pre-Check Diagnostics
- `GET /api/scenarios/<id>/precheck/` - Run pre-check and return JSON report
- `GET /scenarios/<id>/precheck/` - Get HTML partial for HTMX
- `GET /scenarios/<id>/precheck/export/json/` - Export as JSON
- `GET /scenarios/<id>/precheck/export/csv/` - Export as CSV
- `GET /scenarios/<id>/precheck/export/markdown/` - Export as Markdown

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

**First, run Pre-Check** to get actionable diagnostics:

1. Click "🔍 Pre-Check" on scenario detail page
2. Review specific issues with suggestions
3. Fix errors before running solver

Common issues and fixes:
- **TEACHER_SUPPLY_SHORTFALL**: Add teachers or increase daily caps
- **ROOM_CAPACITY_EXCEEDED**: Add rooms or reduce sections per slot
- **MISSING_LAB_ROOMS**: Add rooms with required features
- **NO_TEACHER_CANDIDATES**: Assign teacher candidates to sections
- **LUNCH_INFEASIBLE**: Adjust lunch window or reduce teacher loads

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
