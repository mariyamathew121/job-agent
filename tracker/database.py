# tracker/database.py
# All database operations — save, update, query applications.
# Uses SQLite for now (zero setup). Switch to PostgreSQL for production.

import os
import sys
import json
from datetime import datetime
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
from tracker.models import Base, Application

# ── Database setup ─────────────────────────────────────────────────────
DB_PATH = "data/applications.db"
os.makedirs("data", exist_ok=True)

engine  = create_engine(
    f"sqlite:///{DB_PATH}",
    echo=False   # set True to see SQL queries in terminal
)

# Create tables if they don't exist
Base.metadata.create_all(engine)

Session = sessionmaker(bind=engine)


# ── Save a new application ─────────────────────────────────────────────

def save_application(state: dict) -> Application:
    """
    Saves a completed pipeline state to the database.
    Called by node_track() at the end of every job.
    """
    session = Session()

    try:
        # Check if this job already exists (avoid duplicates)
        existing = session.query(Application).filter_by(
            job_id=state["job_id"]
        ).first()

        if existing:
            # Update existing record
            app = existing
        else:
            # Create new record
            app = Application(job_id=state["job_id"])
            session.add(app)

        # ── Fill in all fields ─────────────────────────────────────────
        app.job_title  = state.get("job_title", "")
        app.company    = state.get("company", "")
        app.job_url    = state.get("job_url", "")
        app.platform   = state.get("platform", "")
        app.status     = state.get("status", "scraped")
        app.error      = state.get("error")

        # Match data
        match = state.get("match") or {}
        app.match_score     = match.get("match_score", 0.0)
        app.match_verdict   = match.get("recommendation", "")
        app.missing_skills  = ", ".join(
            match.get("missing_skills", [])
        )
        app.matching_skills = ", ".join(
            match.get("matching_skills", [])
        )

        # ATS data
        ats = state.get("ats_result") or {}
        app.ats_score   = ats.get("ats_score", 0)
        app.ats_verdict = ats.get("verdict", "")

        # JD data
        jd = state.get("jd_analysis") or {}
        app.required_skills = ", ".join(
            jd.get("required_skills", [])
        )

        # Documents
        app.cover_letter = state.get("cover_letter", "")
        app.pdf_path     = state.get("pdf_path", "")

        # Timestamps
        if state.get("status") == "submitted":
            submitted = state.get("submitted_at")
            if submitted:
                app.submitted_at = datetime.fromisoformat(submitted)

        session.commit()
        print(f"  Saved to database: {app}")
        return app

    except Exception as e:
        session.rollback()
        print(f"  Database error: {e}")
        raise
    finally:
        session.close()


# ── Update response (when email comes in) ──────────────────────────────

def record_response(job_id: str, response_type: str):
    """
    Call this when you receive a response email.
    response_type: "interview" / "rejection" / "assessment" / "ghosted"
    """
    session = Session()
    try:
        app = session.query(Application).filter_by(
            job_id=job_id
        ).first()

        if app:
            app.got_response  = True
            app.response_type = response_type
            app.responded_at  = datetime.now()
            app.status        = response_type
            session.commit()
            print(f"  Response recorded: {job_id} → {response_type}")
    finally:
        session.close()


# ── Analytics queries ──────────────────────────────────────────────────

def get_stats() -> dict:
    """
    Returns a full summary of all applications.
    This powers the tracking dashboard.
    """
    session = Session()
    try:
        total      = session.query(Application).count()
        submitted  = session.query(Application).filter_by(
            status="submitted").count()
        skipped    = session.query(Application).filter_by(
            status="skipped").count()
        failed     = session.query(Application).filter_by(
            status="failed").count()
        interviews = session.query(Application).filter_by(
            response_type="interview").count()
        rejections = session.query(Application).filter_by(
            response_type="rejection").count()
        responses  = session.query(Application).filter_by(
            got_response=True).count()

        avg_match = session.query(
            func.avg(Application.match_score)
        ).scalar() or 0

        avg_ats = session.query(
            func.avg(Application.ats_score)
        ).scalar() or 0

        response_rate = (
            (responses / submitted * 100) if submitted > 0 else 0
        )

        return {
            "total":         total,
            "submitted":     submitted,
            "skipped":       skipped,
            "failed":        failed,
            "interviews":    interviews,
            "rejections":    rejections,
            "responses":     responses,
            "response_rate": round(response_rate, 1),
            "avg_match":     round(avg_match * 100, 1),
            "avg_ats":       round(avg_ats, 1),
        }
    finally:
        session.close()


def get_recent_applications(limit: int = 20) -> list:
    """Returns the most recent applications."""
    session = Session()
    try:
        apps = session.query(Application)\
            .order_by(Application.scraped_at.desc())\
            .limit(limit).all()
        return [
            {
                "job_id":    a.job_id,
                "job_title": a.job_title,
                "company":   a.company,
                "status":    a.status,
                "match":     a.match_score,
                "ats":       a.ats_score,
                "submitted": str(a.submitted_at or ""),
                "response":  a.response_type or "none"
            }
            for a in apps
        ]
    finally:
        session.close()


def get_missing_skills_report() -> dict:
    """
    Innovative feature — analyses all skipped/failed applications
    and surfaces the top skills causing low match scores.
    Tells you exactly what to learn to unlock more jobs.
    """
    session = Session()
    try:
        # Get all missing skills from low-scoring applications
        low_score_apps = session.query(Application).filter(
            Application.match_score < 0.6
        ).all()

        skill_counts = {}
        for app in low_score_apps:
            if app.missing_skills:
                for skill in app.missing_skills.split(", "):
                    skill = skill.strip()
                    if skill:
                        skill_counts[skill] = \
                            skill_counts.get(skill, 0) + 1

        # Sort by frequency
        sorted_skills = sorted(
            skill_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )

        return {
            "top_missing_skills": sorted_skills[:10],
            "insight": (
                f"Adding these skills would unlock "
                f"{len(low_score_apps)} more job matches"
            )
        }
    finally:
        session.close()


# ── Test it ────────────────────────────────────────────────────────────

if __name__ == "__main__":

    print("Testing database...\n")

    # Simulate a completed pipeline state
    test_state = {
        "job_id":      "test_001",
        "job_title":   "Python Developer",
        "company":     "TechStartup Inc",
        "job_url":     "https://linkedin.com/jobs/123",
        "platform":    "linkedin",
        "status":      "submitted",
        "submitted_at": datetime.now().isoformat(),
        "error":       None,
        "match": {
            "match_score":    0.80,
            "recommendation": "apply",
            "missing_skills": ["Docker", "AWS"],
            "matching_skills":["Python", "FastAPI", "SQL"]
        },
        "ats_result": {
            "ats_score": 85,
            "verdict":   "strong"
        },
        "jd_analysis": {
            "required_skills": ["Python", "FastAPI", "PostgreSQL"]
        },
        "cover_letter": "Sample cover letter text...",
        "pdf_path":     "data/resumes/resume_test.pdf"
    }

    # Save it
    app = save_application(test_state)
    print(f"\nSaved: {app}")

    # Add a second application
    test_state2 = {**test_state,
        "job_id":    "test_002",
        "company":   "BigCorp",
        "job_title": "Backend Engineer",
        "status":    "skipped",
        "match": {
            "match_score":    0.35,
            "recommendation": "skip",
            "missing_skills": ["Java", "Spring", "Kubernetes"],
            "matching_skills":["Python"]
        },
        "ats_result":  {"ats_score": 40, "verdict": "weak"},
        "submitted_at": None
    }
    save_application(test_state2)

    # Show stats
    print("\n── Dashboard Stats ──────────────────────────────")
    stats = get_stats()
    for key, val in stats.items():
        print(f"  {key:<20} {val}")

    # Show recent applications
    print("\n── Recent Applications ──────────────────────────")
    for app in get_recent_applications():
        print(f"  {app['job_title']:<25} {app['company']:<20} "
              f"{app['status']:<12} match:{app['match']:.0%} "
              f"ats:{app['ats']}")

    # Show skill gap report
    print("\n── Skill Gap Report ─────────────────────────────")
    report = get_missing_skills_report()
    print(f"  {report['insight']}")
    print("  Top missing skills:")
    for skill, count in report["top_missing_skills"]:
        bar = "█" * count
        print(f"    {skill:<20} {bar} ({count} jobs)")