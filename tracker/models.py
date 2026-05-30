# tracker/models.py
# Defines the database table structure.
# Every job application gets one row in this table.

from sqlalchemy import (
    Column, String, Float, Integer,
    Boolean, Text, DateTime, create_engine
)
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()


class Application(Base):
    """
    One row per job application.
    Gets created when job is scraped.
    Gets updated as it moves through the pipeline.
    """
    __tablename__ = "applications"

    # ── Identity ───────────────────────────────────────────────────────
    id           = Column(Integer, primary_key=True, autoincrement=True)
    job_id       = Column(String(100), unique=True, nullable=False)
    job_title    = Column(String(200))
    company      = Column(String(200))
    job_url      = Column(String(500))
    platform     = Column(String(50))   # linkedin / indeed / naukri

    # ── Analysis results ───────────────────────────────────────────────
    match_score  = Column(Float,   default=0.0)
    ats_score    = Column(Integer, default=0)
    match_verdict= Column(String(50))   # strong apply / apply / skip
    ats_verdict  = Column(String(50))   # strong / good / weak

    # ── Skills data ────────────────────────────────────────────────────
    required_skills  = Column(Text)   # stored as comma-separated string
    missing_skills   = Column(Text)
    matching_skills  = Column(Text)

    # ── Generated documents ────────────────────────────────────────────
    cover_letter = Column(Text)
    pdf_path     = Column(String(500))

    # ── Status tracking ────────────────────────────────────────────────
    status       = Column(String(50), default="scraped")
    # scraped → analysed → tailored → submitted → responded → interview

    error        = Column(Text, nullable=True)

    # ── Timestamps ─────────────────────────────────────────────────────
    scraped_at   = Column(DateTime, default=datetime.now)
    submitted_at = Column(DateTime, nullable=True)
    responded_at = Column(DateTime, nullable=True)

    # ── Response tracking (updated when email arrives) ─────────────────
    got_response    = Column(Boolean, default=False)
    response_type   = Column(String(50), nullable=True)
    # "interview" / "rejection" / "assessment" / "ghosted"

    # ── A/B testing (innovative feature) ──────────────────────────────
    resume_version  = Column(String(10), default="A")
    # track which resume version got better responses

    def __repr__(self):
        return (f"<Application {self.job_id} | "
                f"{self.job_title} at {self.company} | "
                f"{self.status}>")