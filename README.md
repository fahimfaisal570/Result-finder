# Result Finder PRO — Academic Intelligence Dashboard

Result Finder PRO is a database-backed academic results platform for Faridpur Engineering College. It turns a portal designed for one-student-at-a-time lookups into a reusable batch analytics workflow for students, teachers, advisors, and department leadership.

The current v2 branch is the analytics rewrite. It stores imported results in SQLite, recomputes academic metrics locally using syllabus credit mappings, understands retakes and improvements, and provides semester analytics, student planning, and operational monitoring.

## What the project solves

The university portal is the official source of results, but it has practical limitations:

- Results must normally be viewed student by student.
- A batch has no built-in GPA distribution, subject bottleneck, or progression view.
- Portal GPA/CGPA values are not sufficient for retake-aware academic planning.
- Re-admitted students may have historical results under another session or batch.
- Students and teachers need to know not only the current result, but the next useful action.

Result Finder addresses these problems with portal ingestion, a normalized local database, independent calculations, interactive analytics, and automated monitoring utilities.

## Product capabilities

### Batch and profile management

The main dashboard supports saved academic profiles containing a program, session, registration roster, and imported exams.

- Create a regular batch from a program/session and registration range.
- Create a provisional batch before results are published.
- Add individual students from another session when a student is re-admitted.
- Preserve the roster while refreshing individual exam scans.
- View stored exams, student counts, scan timestamps, and profile metadata.
- Delete an exam scan while preserving the student roster.

### Concurrent portal scanning

The portal integration and batch scanning engine live in cli_scraper.py.

- Concurrent worker threads scan many registration numbers in one operation.
- Program, session, and exam catalogues are discovered from the portal.
- AUTO session discovery tries relevant sessions for re-admitted students.
- Connection pre-warming reduces first-request latency.
- Retries, exponential backoff, jitter, and rotating browser user agents improve resilience.
- Scan progress can be displayed in Streamlit.
- Imported results are written idempotently to reduce duplicate records.

The scraper is designed around the current DUCMC portal workflow and may require maintenance if the portal changes its HTML or endpoints.

### Results and transcript views

The Results page supports single-exam and batch-oriented ingestion workflows. The Transcript page can perform a deeper portal scan for one student and display a chronological academic history.

The transcript workflow uses the student session and cohort scope to avoid mixing unrelated exams. It also supports students whose records span multiple portal sessions.

### Analytics dashboard

The Analytics page contains eight tabs.

#### Baseline Insight

- Current-semester GPA distribution.
- Batch mean, median GPA, median CGPA, active-student count, and honours roster.
- First-chance pass ratio based on subject grades in the selected main exam.
- Subject difficulty ranking using passing-grade performance.
- Grade distribution by subject, from A+ through F.
- Filters for batch, semester, subject, and CGPA range.

#### Trends

- Batch GPA trajectory across imported semesters.
- Batch median overlay.
- Individual student spotlight on the longitudinal chart.
- Peak, valley, consistency, and trajectory classification.
- Retake and improvement success statistics.
- Cross-batch benchmarking where comparable semester data exists.

#### Advanced Patterns

- Subject-level variance and distribution views.
- Performance personas based on current performance, movement, and promotion context.
- Strategic quadrant for high performers, improving students, declining students, and specialists.
- Subject dependency heatmap using Pearson correlation where enough complete data exists.

#### Cube Pivot

- Student-by-subject grade matrix.
- Subject-by-student transposed view.
- Useful for manual review, export, and classroom inspection.

#### Clearing List

- Semester-end list with GPA, CGPA, result status, improvement count, and retake count.
- CSV export for departmental processing.

#### Student follow-up records

Follow-up records are now managed inside each student’s Success Plan rather than in a separate intervention mode.

- Stores risk, action, advisor/owner, follow-up date, progress note, and status per student and exam.
- Builds a longitudinal advising timeline as new semester records are imported.
- Supports Open, In progress, and Resolved case states inside the Success Plan.

This is an operational note-taking workspace, not a replacement for the institution’s official student information system. It currently has no multi-user authentication or authorization layer.

#### GPA Projection and Graduation Planner

- Deep analysis of a selected student’s full portal history.
- Credit-weighted True CGPA calculation.
- Official versus locally recomputed CGPA comparison.
- Pending retake and improvement identification.
- Precise target GPA calculation for the next applicable semester.
- Graduation target calculator for a selected CGPA goal.
- Summary projection by semester GPA.
- Detailed projection by course grade with elective selection and credit-cap enforcement.
- Per-semester GPA/CGPA breakdown.
- Paginated student cards with portal-scan results cached during the session.

#### Student Personal Success Plan

The success-plan view presents the same academic data in a student-friendly format and combines current performance, longitudinal trends, and advisor follow-up.

- Current CGPA, current-semester GPA, batch percentile, and plan status.
- Promotion target gap where a promotion rule is available.
- GPA trajectory across all imported semesters.
- Improving, stable, or declining trend classification.
- Recent GPA movement, GPA volatility, and semesters tracked.
- An explicit baseline message when history is insufficient.
- Failed-course and borderline-course counts.
- Priority subjects ranked by current GP and credit weight.
- Strongest subjects to maintain.
- Plain-language next actions.
- Longitudinal advisor follow-up timeline across imported exams.
- Current-semester follow-up form with risk, action, owner, due date, status, and progress note.
- Downloadable text plan for personal use or advising.

Follow-up records are stored locally per student and exam, allowing new semester records to build a longitudinal advising history. A separate student login or private portal is not yet implemented.

### Strategic Analysis Mode

The optional Strategic Insights Mode provides a department-level summary above the tabs:

- Batch momentum against historical CGPA.
- Honours pipeline.
- Re-admission alerts.
- Failed-promotion and critical-risk groups.
- At-risk students close to a promotion threshold.
- Bottleneck subject detection.
- High-correlation subject pairs.
- Direct Deep Analysis actions for named students.

### Retake-aware academic calculations

The database layer does not simply copy portal summary values.

- Subject grades are stored per student, subject, exam, and session.
- Credit hours come from credit_mapping.json where available.
- Best recorded grade per subject is used for effective CGPA calculations.
- Retake and improvement attempts are classified separately.
- Failed subjects remain visible as pending until cleared.
- Portal GPA/CGPA values can be compared with locally recomputed values.
- Graduation projections use credit-weighted calculations rather than an unweighted semester average.

### Re-admitted student detection

The system detects likely re-admitted students using subject-overlap and academic-load fingerprints.

- Compares a student’s current subject pattern with the regular batch.
- Separates likely re-admissions from retake-only or improvement-only records.
- Flags incomplete histories when a student has fewer semester records than the profile expects.
- Offers a Scan and Fix workflow to retrieve missing history and recalculate analytics.

### Provisional batches

Provisional profiles allow a teacher to prepare a roster before results are released.

- Store the expected student roster early.
- Monitor for the first published result.
- Promote the profile when actual results arrive.
- Use the graduation simulator without contacting the portal.
- Enter semester-level expected GPA or detailed course-level expected grades.

### Monitoring and automation utilities

The repository also contains supporting automation components:

- exam_monitor/monitor.py checks for newly published exams.
- exam_monitor/find_latest.py locates the latest known exam.
- exam_monitor/auto_pdf_mailer.py generates print/PDF-oriented reports and can email them.
- v2_auto_sync.py synchronizes work queued by the legacy/main branch pipeline.
- portal_monitor/health_check.py checks portal availability and reports state changes.
- GitHub Actions can run scheduled monitoring workflows.

These utilities are deployment-specific and may require environment secrets, mail configuration, and a compatible portal connection.

## Architecture

```text
University portal
       |
       v
cli_scraper.py ---> SQLite result_finder.db
       |                    |
       |                    +-- profiles
       |                    +-- students
       |                    +-- exam_results
       |                    +-- subject_grades
       |                    +-- scan_log
       |                    +-- meta_cache
       |                    +-- student_interventions
       |
       +---------------> Streamlit pages
                              +-- app.py
                              +-- pages/results.py
                              +-- pages/transcript.py
                              +-- pages/analytics.py
```

### Core files

| File | Responsibility |
|---|---|
| app.py | Main Streamlit dashboard, profile creation, saved-profile workflows |
| pages/results.py | Result scanning and ingestion interface |
| pages/transcript.py | Deep individual academic-history view |
| pages/analytics.py | Interactive analytics, interventions, projections, and success plans |
| database.py | SQLite schema, migrations, queries, calculations, and projections |
| cli_scraper.py | Portal requests, parsing, concurrent scanning, and exam classification |
| ml_predictor.py | Trend/EMA-based future GPA projections when sufficient history exists |
| ui_components.py | Shared styling and reusable interface components |
| credit_mapping.json | Department- and semester-aware course credit mappings |
| v2_auto_sync.py | Synchronization worker for external scan tasks |
| tests/ | Database and end-to-end integration tests |

## Database model

The application uses SQLite with WAL mode, foreign keys, thread-local connections, busy-timeout handling, and idempotent migrations.

- profiles stores batch metadata.
- students stores the profile roster.
- exam_results stores one summary result per student and exam.
- subject_grades stores individual subject grades and credit hours.
- scan_log records scan timestamps and counts.
- meta_cache stores expiring metadata cache entries.
- student_interventions stores the current teacher follow-up record per student and exam.

The intervention table was added through a migration-safe schema update, so existing databases can start the new version without manual table creation.

## Installation

```bash
git clone https://github.com/fahimfaisal570/Result-finder.git
cd Result-finder
git checkout v2
python -m venv .venv
```

Activate the environment and install dependencies:

```bash
# Windows PowerShell
.\\.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
```

Launch the dashboard:

```bash
streamlit run app.py
```

On Windows, Launch_Dashboard.bat provides a one-click launch option when the expected Python environment is available.

## First-use workflow

1. Start the Streamlit application.
2. Create a provisional or portal-backed profile.
3. Add the student roster or registration range.
4. Scan one or more main-semester exams.
5. Open Analytics and select the profile and semester.
6. Review Baseline Insight and Trends.
7. Use GPA Projection for exact retake and graduation scenarios.
8. Use Success Plan for student-facing priorities, longitudinal trends, and advisor follow-up.

## Testing

Run the database and integration suites with:

```bash
python -m unittest tests/test_database.py -v
python -m unittest tests/test_full_system.py -v
```

For a lightweight syntax check:

```bash
python -m py_compile database.py pages/analytics.py
```

The test coverage focuses on database idempotency, migrations, foreign-key behavior, retake-aware CGPA calculations, projection mathematics, longitudinal parsing, and scraper/database integration.

## Important scope and limitations

- The portal remains the official source of academic results; local calculations are analytical and should be checked against institutional policy.
- Portal HTML, endpoints, availability, and anti-automation behavior can change.
- The current project does not collect attendance, assignment marks, continuous assessment, classroom activity, or instructor evaluation data.
- The current dashboard does not provide student authentication, role-based access, or institution-wide multi-user collaboration.
- Success-plan follow-up records are stored in the local SQLite database and should be backed up and access-controlled in deployment.
- GPA and promotion rules are based on configured department mappings and rules in the codebase; review them when university policy changes.

## Deployment notes

The v2 analytics application and the legacy/main monitoring pipeline can be deployed separately. The monitoring pipeline can discover new exams and queue work for the v2 database through the synchronization utility.

Before production deployment, configure:

- A persistent writable SQLite location or suitable database replacement.
- Portal access and any required network settings.
- Email credentials for automated PDF delivery, if enabled.
- GitHub Actions secrets and schedules, if scheduled monitoring is enabled.
- A backup policy for result_finder.db and related state files.

## License

This project is released under the MIT License. See LICENSE.

Developed by [Fahim Faisal](https://www.linkedin.com/in/fahimfaisal09).
