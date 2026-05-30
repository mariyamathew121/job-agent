# agent/state.py
# The state object that travels through the entire pipeline.
# Every node reads from this and adds to it.
# By the end it contains everything about one job application.

from typing import TypedDict, Optional

class JobState(TypedDict):

    # ── Set at the start (from scraper) ───────────────────────────────
    job_id:          str
    job_title:       str
    company:         str
    job_url:         str
    job_description: str
    platform:        str          # "linkedin" / "indeed" / "naukri"

    # ── Added by analyse node ──────────────────────────────────────────
    jd_analysis:     Optional[dict]   # skills, tone, keywords, seniority
    match:           Optional[dict]   # score, matching/missing skills
    company_intel:   Optional[dict]   # size, culture, red flags
    should_apply:    Optional[bool]   # True / False decision

    # ── Added by tailor node ───────────────────────────────────────────
    tailored_resume: Optional[dict]   # full tailored resume dict
    ats_result:      Optional[dict]   # score, verdict, improvements
    cover_letter:    Optional[str]    # generated cover letter text
    pdf_path:        Optional[str]    # path to generated PDF file

    # ── Added by retriever node ────────────────────────────────────────
    custom_answers:  Optional[dict]   # {question: answer} pairs

    # ── Added by submit node ───────────────────────────────────────────
    status:          str   # scraped→analysed→tailored→submitted→failed
    error:           Optional[str]    # error message if something fails
    submitted_at:    Optional[str]    # timestamp of submission