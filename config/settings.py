import os
from dotenv import load_dotenv
load_dotenv()

# ── OpenRouter ─────────────────────────────────────────────────────────
OPENROUTER_API_KEY  = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
LLM_MODEL = "meta-llama/llama-3.1-8b-instruct"

# ── LinkedIn credentials ───────────────────────────────────────────────
LINKEDIN_EMAIL    = os.getenv("LINKEDIN_EMAIL")
LINKEDIN_PASSWORD = os.getenv("LINKEDIN_PASSWORD")

# Naukri
NAUKRI_EMAIL    = os.getenv("NAUKRI_EMAIL")

# Wellfound
WELLFOUND_EMAIL    = os.getenv("WELLFOUND_EMAIL")
WELLFOUND_PASSWORD = os.getenv("WELLFOUND_PASSWORD")

# Indeed
INDEED_EMAIL = os.getenv("INDEED_EMAIL")
# ── Your job preferences ───────────────────────────────────────────────

# All roles you want to apply for
# AI-related roles are listed first — scraper prioritises top of list
SEARCH_ROLES = [
    "AI Engineer",
    "Machine Learning Engineer",
    "Data Scientist",
    "Data Engineer",
    "Python Developer",
    "Software Developer",
]

# Your preferred locations
SEARCH_LOCATIONS = [
    "Kochi",
    "Bangalore",
    "Trivandrum",
    "Remote",
]

# Experience level filter for LinkedIn
# 1 = Internship
# 2 = Entry level     (0-1 year)
# 3 = Associate       (1-3 years)
# We use both 2 and 3 to catch all 0-2 year experience jobs
EXPERIENCE_LEVELS = [2, 3]

# ── Search volume ──────────────────────────────────────────────────────

# Jobs to collect per role+location combination
# 6 roles × 4 locations × 10 = up to 240 jobs
JOBS_PER_SEARCH = 10

# Hard limit — total jobs across all searches
# Keep at 50 while testing — raise to 500+ for real run
MAX_JOBS = 50

# Only keep jobs posted in last N days
DAYS_POSTED = 7

# ── Quality filters ────────────────────────────────────────────────────

# Skip job if match score below this (0.0 to 1.0)
MIN_MATCH_SCORE = 0.5

# Skip submission if ATS score below this (0 to 100)
MIN_ATS_SCORE = 70

# ── Timing — keeps behaviour human-like ───────────────────────────────

# Seconds to wait between each application submission
APPLY_DELAY_MIN = 45
APPLY_DELAY_MAX = 90

# Days to wait before sending follow-up email
FOLLOWUP_DAYS = 7

# ── Your profile summary for context ──────────────────────────────────
# Used by the LLM when making decisions — keep this accurate

CANDIDATE_PROFILE = {
    "experience_years": 1,
    "target_field":     "AI and Machine Learning",
    "preferred_roles":  SEARCH_ROLES,
    "locations":        SEARCH_LOCATIONS,
    "exp_range":        "0-2 years",   # jobs to target
}