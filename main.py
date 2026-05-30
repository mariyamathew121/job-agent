# main.py
# Entry point for the entire AI job application agent.
# One command runs everything:
#   1. Scrape jobs from all platforms
#   2. Run each job through the full pipeline
#   3. Track all results to database
#   4. Show final stats

import os
import sys
import json
import time
from datetime import datetime
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from agent.graph        import pipeline
from tracker.database   import save_application, get_stats, get_missing_skills_report
from config.settings    import MAX_JOBS
from tracker.database import Session
from tracker.models   import Application

# ── Step 1: Load all scraped jobs ──────────────────────────────────────

def load_all_jobs() -> list:
    """
    Loads jobs from all platform JSON files.
    Merges and deduplicates them.
    """
    job_files = [
        "data/linkedin_jobs.json",
        "data/naukri_jobs.json",
        "data/indeed_jobs.json",
        "data/wellfound_jobs.json",
        "data/all_jobs.json",      # remotive + others
    ]

    all_jobs = []
    seen_ids = set()

    for filepath in job_files:
        if not os.path.exists(filepath):
            continue

        with open(filepath, "r", encoding="utf-8") as f:
            jobs = json.load(f)

        new_count = 0
        for job in jobs:
            if job["job_id"] not in seen_ids:
                seen_ids.add(job["job_id"])
                all_jobs.append(job)
                new_count += 1

        print(f"  {filepath:<35} → {new_count} jobs loaded")

    return all_jobs


# ── Step 2: Scrape fresh jobs ──────────────────────────────────────────

def scrape_fresh_jobs(platforms: list = None) -> list:
    """
    Runs scrapers for specified platforms.
    Default: all platforms.
    """
    if platforms is None:
        platforms = ["linkedin", "naukri", "indeed", "wellfound", "remotive"]

    all_new_jobs = []

    if "linkedin" in platforms or "remotive" in platforms:
        print("\n  Running multi-platform scraper (LinkedIn + Remotive)...")
        try:
            from scraper.multi_scraper import (
                scrape_all_platforms, save_jobs as save_multi
            )
            jobs = scrape_all_platforms()
            if jobs:
                save_multi(jobs)
                all_new_jobs.extend(jobs)
                print(f"  LinkedIn + Remotive: {len(jobs)} jobs")
        except Exception as e:
            print(f"  Multi-scraper error: {e}")

    if "naukri" in platforms:
        print("\n  Running Naukri scraper...")
        try:
            from scraper.naukri import scrape_naukri_jobs, save_jobs as save_naukri
            jobs = scrape_naukri_jobs()
            if jobs:
                save_naukri(jobs)
                all_new_jobs.extend(jobs)
                print(f"  Naukri: {len(jobs)} jobs")
        except Exception as e:
            print(f"  Naukri error: {e}")

    if "indeed" in platforms:
        print("\n  Running Indeed scraper...")
        try:
            from scraper.indeed import scrape_indeed_jobs, save_jobs as save_indeed
            jobs = scrape_indeed_jobs()
            if jobs:
                save_indeed(jobs)
                all_new_jobs.extend(jobs)
                print(f"  Indeed: {len(jobs)} jobs")
        except Exception as e:
            print(f"  Indeed error: {e}")

    if "wellfound" in platforms:
        print("\n  Running Wellfound scraper...")
        try:
            from scraper.wellfound import scrape_wellfound_jobs, save_jobs as save_wf
            jobs = scrape_wellfound_jobs()
            if jobs:
                save_wf(jobs)
                all_new_jobs.extend(jobs)
                print(f"  Wellfound: {len(jobs)} jobs")
        except Exception as e:
            print(f"  Wellfound error: {e}")

    return all_new_jobs


# ── Step 3: Run pipeline on jobs ───────────────────────────────────────

def run_pipeline(jobs: list, max_jobs: int = None) -> dict:
    """
    Runs every job through the full pipeline:
    analyse → match → tailor → ATS score → cover letter
    → PDF → answer questions → submit → track
    """
    max_jobs  = max_jobs or MAX_JOBS
    jobs      = jobs[:max_jobs]
    total     = len(jobs)

    session          = Session()
    processed_ids    = set(
        row.job_id for row in
        session.query(Application.job_id).all()
    )
    session.close()

    # Filter out already-processed jobs
    unprocessed = [j for j in jobs
                   if j["job_id"] not in processed_ids]
    
    skipped_count = len(jobs) - len(unprocessed)
    if skipped_count > 0:
        print(f"  Skipping {skipped_count} already-processed jobs")

    jobs  = unprocessed[:max_jobs]
    total = len(jobs)

    if total == 0:
        print("  All jobs already processed. Scrape fresh jobs first.")
        return {"submitted": 0, "skipped": 0, "failed": 0}
    
    results = {
        "submitted":  0,
        "skipped":    0,
        "failed":     0,
        "low_ats":    0,
    }

    print(f"\n  Processing {total} jobs through pipeline...\n")
    print("  " + "─" * 53)

    for i, job in enumerate(jobs):
        print(f"\n  Job {i+1}/{total}: {job['job_title']} "
              f"at {job['company']}")
        print(f"  Platform: {job['platform']} | "
              f"Location: {job['location']}")

        start = time.time()

        try:
            result = pipeline.invoke(job)
            elapsed = time.time() - start

            status = result.get("status", "unknown")
            results[status] = results.get(status, 0) + 1

            # Show result summary
            match = result.get("match") or {}
            ats   = result.get("ats_result") or {}

            print(f"  Status:  {status}")
            print(f"  Match:   {match.get('match_score', 0):.0%} | "
                  f"ATS: {ats.get('ats_score', 0)}/100 | "
                  f"Time: {elapsed:.1f}s")

            if status == "submitted":
                print(f"  PDF:     {result.get('pdf_path', 'N/A')}")

        except Exception as e:
            print(f"  Pipeline error: {e}")
            results["failed"] += 1

        # Rate limiting — pause between applications
        if i < total - 1:
            time.sleep(2)

    return results


# ── Step 4: Show final stats ───────────────────────────────────────────

def show_stats(results: dict):
    """Display final run statistics."""

    print("\n\n" + "="*55)
    print("  FINAL RESULTS")
    print("="*55)

    print(f"\n  This run:")
    print(f"    Submitted:   {results.get('submitted', 0)}")
    print(f"    Skipped:     {results.get('skipped', 0)}")
    print(f"    Low ATS:     {results.get('low_ats', 0)}")
    print(f"    Failed:      {results.get('failed', 0)}")

    print(f"\n  All time (from database):")
    try:
        stats = get_stats()
        print(f"    Total apps:    {stats['total']}")
        print(f"    Submitted:     {stats['submitted']}")
        print(f"    Responses:     {stats['responses']}")
        print(f"    Interviews:    {stats['interviews']}")
        print(f"    Response rate: {stats['response_rate']}%")
        print(f"    Avg match:     {stats['avg_match']}%")
        print(f"    Avg ATS:       {stats['avg_ats']}/100")
    except Exception:
        pass

    print(f"\n  Skill gap report:")
    try:
        report = get_missing_skills_report()
        print(f"    {report['insight']}")
        for skill, count in report["top_missing_skills"][:5]:
            print(f"    → {skill} (missing in {count} jobs)")
    except Exception:
        pass

    print("\n" + "="*55)


# ── Main entry point ───────────────────────────────────────────────────

def main(
    scrape:    bool = True,
    platforms: list = None,
    max_jobs:  int  = None,
    use_saved: bool = True,
):
    """
    Main function — runs the complete job application agent.

    Args:
        scrape:    Whether to scrape fresh jobs first
        platforms: Which platforms to scrape (default: all)
        max_jobs:  Max jobs to process through pipeline
        use_saved: Whether to include previously saved jobs
    """

    print("\n" + "="*55)
    print("  AI JOB APPLICATION AGENT")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("="*55)

    jobs = []

    # Step 1 — Scrape fresh jobs
    if scrape:
        print("\n[1/3] SCRAPING JOBS\n")
        scrape_fresh_jobs(platforms)

    # Step 2 — Load all saved jobs
    if use_saved:
        print("\n[2/3] LOADING SAVED JOBS\n")
        jobs = load_all_jobs()
        print(f"\n  Total unique jobs loaded: {len(jobs)}")

    if not jobs:
        print("\n  No jobs found. Run scrapers first.")
        return

    # Step 3 — Run pipeline
    print("\n[3/3] RUNNING PIPELINE\n")
    results = run_pipeline(jobs, max_jobs)

    # Step 4 — Show stats
    show_stats(results)


# ── Run modes ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="AI Job Application Agent"
    )
    parser.add_argument(
        "--mode",
        choices=["full", "pipeline-only", "scrape-only"],
        default="pipeline-only",
        help=(
            "full = scrape + pipeline | "
            "pipeline-only = use saved jobs | "
            "scrape-only = just scrape, don't apply"
        )
    )
    parser.add_argument(
        "--platforms",
        nargs="+",
        choices=["linkedin", "naukri", "indeed",
                 "wellfound", "remotive"],
        help="Which platforms to scrape"
    )
    parser.add_argument(
        "--max-jobs",
        type=int,
        default=10,
        help="Max jobs to process (default: 10)"
    )

    args = parser.parse_args()

    if args.mode == "full":
        main(
            scrape    = True,
            platforms = args.platforms,
            max_jobs  = args.max_jobs,
            use_saved = True,
        )
    elif args.mode == "pipeline-only":
        main(
            scrape    = False,
            platforms = None,
            max_jobs  = args.max_jobs,
            use_saved = True,
        )
    elif args.mode == "scrape-only":
        print("\nScraping jobs only — not submitting applications\n")
        scrape_fresh_jobs(args.platforms)
        jobs = load_all_jobs()
        print(f"\nTotal jobs ready: {len(jobs)}")