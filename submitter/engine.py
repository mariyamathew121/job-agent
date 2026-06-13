# submitter/engine.py
# Routes each job to the correct platform submitter.
# This is what the orchestrator calls — it handles everything.

import os
import sys
import json
import pickle
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import undetected_chromedriver as uc
from submitter.base import pause, log_submission
from submitter.linkedin_apply import apply_linkedin, load_linkedin_session
from submitter.naukri_apply  import apply_naukri,  load_naukri_session
from submitter.indeed_apply  import apply_indeed,   load_indeed_session


def get_shared_driver():
    """One browser instance reused across all submissions."""
    options = uc.ChromeOptions()
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    driver = uc.Chrome(options=options, version_main=147)
    return driver


def load_sessions(driver) -> dict:
    """Load all platform sessions into shared driver."""
    sessions = {}

    try:
        sessions["linkedin"] = load_linkedin_session(driver)
        print(f"  LinkedIn session: {'✓' if sessions['linkedin'] else '✗'}")
    except Exception:
        sessions["linkedin"] = False

    try:
        sessions["naukri"] = load_naukri_session(driver)
        print(f"  Naukri session:   {'✓' if sessions['naukri'] else '✗'}")
    except Exception:
        sessions["naukri"] = False

    try:
        sessions["indeed"] = load_indeed_session(driver)
        print(f"  Indeed session:   {'✓' if sessions['indeed'] else '✗'}")
    except Exception:
        sessions["indeed"] = False

    return sessions


def submit_application(state: dict) -> dict:
    """
    Main entry point — called by the LangGraph orchestrator.
    Routes to correct platform submitter based on job platform.
    Returns updated state with submission result.
    """
    job      = state
    platform = job.get("platform", "").lower()
    pdf_path = state.get("pdf_path", "")

    # Load resume and QA
    with open("config/resume.json") as f:
        resume = json.load(f)
    with open("config/user_qa.json") as f:
        user_qa = json.load(f)

    print(f"\n  Submitting: {job['job_title']} at {job['company']}")
    print(f"  Platform: {platform}")
    print(f"  Resume: {os.path.basename(pdf_path) if pdf_path else 'N/A'}")

    success = False

    try:
        if platform == "linkedin":
            success = apply_linkedin(job, resume, user_qa, pdf_path)

        elif platform == "naukri":
            success = apply_naukri(job, resume, user_qa, pdf_path)

        elif platform == "indeed":
            success = apply_indeed(job, resume, user_qa, pdf_path)

        elif platform in ["remotive", "wellfound"]:
            # These redirect to company sites — log for manual follow-up
            print(f"  {platform} redirects to company site")
            print(f"  Job URL: {job.get('job_url', '')}")
            log_submission(job, "MANUAL_REQUIRED",
                           f"{platform} external application")
            return {
                **state,
                "status": "manual_required",
                "error":  f"{platform} requires external application"
            }

        else:
            print(f"  Unknown platform: {platform}")
            log_submission(job, "SKIPPED", f"Unknown platform: {platform}")
            return {**state, "status": "skipped"}

    except Exception as e:
        print(f"  Submission error: {e}")
        log_submission(job, "ERROR", str(e)[:100])
        success = False

    if success:
        from datetime import datetime
        return {
            **state,
            "status":       "submitted",
            "submitted_at": datetime.now().isoformat()
        }
    else:
        return {
            **state,
            "status": "failed",
            "error":  "Submission unsuccessful"
        }


# ── Batch submission with one shared browser ───────────────────────────

def submit_batch(jobs: list, max_submit: int = 50) -> dict:
    """
    Submit multiple jobs using one shared browser instance.
    Much faster than opening a new browser for each job.
    """
    with open("config/resume.json") as f:
        resume = json.load(f)
    with open("config/user_qa.json") as f:
        user_qa = json.load(f)

    results = {
        "submitted": 0,
        "failed":    0,
        "skipped":   0,
        "manual":    0
    }

    print("\nLoading browser sessions...")
    driver   = get_shared_driver()
    sessions = load_sessions(driver)

    print(f"\nProcessing {min(len(jobs), max_submit)} jobs...\n")

    try:
        for i, job in enumerate(jobs[:max_submit]):
            platform = job.get("platform", "").lower()
            pdf_path = job.get("pdf_path", "")

            print(f"[{i+1}/{min(len(jobs), max_submit)}] "
                  f"{job['job_title']} at {job['company']} ({platform})")

            if not sessions.get(platform, False):
                print(f"  No session for {platform} — skipping")
                results["skipped"] += 1
                log_submission(job, "SKIPPED", "No session")
                continue

            if not pdf_path or not os.path.exists(pdf_path):
                print(f"  No PDF found — skipping")
                results["skipped"] += 1
                continue

            try:
                if platform == "linkedin":
                    success = apply_linkedin(
                        job, resume, user_qa, pdf_path, driver
                    )
                elif platform == "naukri":
                    success = apply_naukri(
                        job, resume, user_qa, pdf_path, driver
                    )
                elif platform == "indeed":
                    success = apply_indeed(
                        job, resume, user_qa, pdf_path, driver
                    )
                else:
                    results["manual"] += 1
                    continue

                if success:
                    results["submitted"] += 1
                else:
                    results["failed"] += 1

            except Exception as e:
                print(f"  Error: {e}")
                results["failed"] += 1
                log_submission(job, "ERROR", str(e)[:100])

            # Small pause between applications
            pause(3, 6)

    finally:
        driver.quit()

    print(f"\n── Submission Results ────────────────────────────")
    print(f"  Submitted: {results['submitted']}")
    print(f"  Failed:    {results['failed']}")
    print(f"  Skipped:   {results['skipped']}")
    print(f"  Manual:    {results['manual']}")
    print(f"\nFull log: data/submissions.log")

    return results