# BAA Commission Engine — Agent Rules of Engagement

You are building a **proof-of-concept** called the BAA Long-Tail Commission Engine.
Read this file completely before doing anything else.
The task list is in `TASKS.md`. Execute tasks from there only.

---

## YOUR ENVIRONMENT — READ THIS FIRST

You are running **inside a Docker container** called `baa_app`.
This is your working environment. Everything happens in here.

- Your working directory is `/app` — this is the project root
- Python is already installed — use `python3`
- All Python packages are already installed — do not pip install anything
- PostgreSQL is running in a separate container called `baa_postgres`
- Connect to Postgres using hostname `db`, not `localhost`
- Do NOT install Docker, do NOT create virtual environments
- Do NOT run any `sudo apt` commands — you are not root
- Do NOT run any `docker` commands — you are inside a container

The `.env` file at `/app/.env` already has all database credentials.
Python scripts load it automatically via `python-dotenv`.

---

## YOUR OPERATING MODE

You work in **one task at a time** mode. This is not negotiable.

- Read the current task in `TASKS.md`
- Do exactly what it says — nothing more
- Run the verification command at the end of the task
- Print the result to the terminal
- Write your status to `STATUS.md` (format below)
- **STOP. Do not proceed to the next task automatically.**

The human will read your output, confirm it looks correct, and tell you
to proceed to the next task. You wait for that instruction.

---

## HARD RULES — NEVER BREAK THESE

**1. One task per session.**
Complete one numbered task from `TASKS.md`. When done, stop.
Do not chain into the next task unless explicitly told to.

**2. Verify before declaring done.**
Every task has a VERIFY block. Run it. If it fails, stop and report
the failure. Do not attempt to silently fix and retry more than once.
If a fix attempt fails, write the error to `STATUS.md` and stop.

**3. Never modify anything outside /app.**
Do not touch system files, other directories, or container config.

**4. Never commit the `.env` file.**
Before any git commit, confirm `.env` is in `.gitignore`:
`cat .gitignore | grep .env`

**5. Database connection uses hostname `db`.**
The Postgres container is reachable at hostname `db` port `5432`.
Never use `localhost` for the DB connection inside this container.

---

## STATUS.md FORMAT

After every task write or overwrite `STATUS.md` with this structure:

```
TASK: [task number and title]
STATUS: [COMPLETE / FAILED / BLOCKED]
VERIFY OUTPUT:
[paste exact terminal output of the verification command]
NOTES:
[anything unexpected, errors, decisions made]
NEXT TASK: [number and title — do not start it]
```

---

## IF YOU GET STUCK

If a command fails and your one fix attempt does not resolve it:

1. Stop immediately
2. Write the full error to `STATUS.md`
3. Print this to the terminal:

```
AGENT STOPPED — human intervention required.
See STATUS.md for details.
Do not restart this session until the issue is resolved.
```

Do not loop. One fix attempt only, then stop.

---

## WHAT THIS PROJECT IS

A PostgreSQL + Python system that models multi-year profit commission
calculations for specialty insurance Binding Authority Agreements (BAAs).

A policy bound in 2023 may generate claims through 2029. The commission
must be recalculated at 12, 24, 36, 48, 60+ month intervals using actuarial
IBNR estimates, on a sliding commission scale, with an immutable audit trail
per carrier per underwriting year.

Personal portfolio project. Correctness and auditability matter most.

Full specification: `docs/BAA_Commission_Engine_Project_Spec.docx`
