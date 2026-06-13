# main.py
# Entry point for the entire AI job application agent.
# One command runs everything:
#   1. Scrape jobs from all platforms
#   2. Run each job through the full pipeline
#   3. Track all results to database
#   4. Show final stats
#
# Usage:
#   python main.py --mode pipeline-only --max-jobs 10
#   python main.py --mode fast --max-jobs 20
#   python main.py --mode full --max-jobs 50
#   python main.py --mode scrape-only
#   python main.py --mode full --platforms linkedin remotive --max-jobs 10

import os
import sys
import json
import time
from datetime import datetime
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from agent.graph      import pipeline
from tracker.database import save_application, get_stats, get_missing_skills_report
from config.settings  import MAX_JOBS


# ── Step 1: Load all scraped jobs ──────────────────────────────────────

def load_all_jobs() -> list:
    """
    Loads jobs from all platform JSON files.
    Merges and deduplicates across files.
    """
    job_files = [
        "data/naukri_jobs.json",
        "data/indeed_jobs.json",
        "data/wellfound_jobs.json",
        "data/all_jobs.json",       # linkedin + remotive
        "data/linkedin_jobs.json",  # fallback
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

        if new_count > 0:
            print(f"  {filepath:<35} → {new_count} jobs loaded")

    return all_jobs


# ── Step 2: Scrape fresh jobs ──────────────────────────────────────────

def scrape_fresh_jobs(platforms: list = None) -> list:
    """
    Runs scrapers for specified platforms.

    Fast scrapers (HTTP, no browser):
      linkedin, remotive — runs in ~30 seconds

    Selenium scrapers (need browser, ~2 min each):
      naukri, indeed, wellfound

    Use --mode fast for quick runs (linkedin + remotive only).
    Use --mode full for all platforms.
    """
    if platforms is None:
        platforms = ["linkedin", "remotive",
                     "naukri", "indeed", "wellfound"]

    all_new_jobs = []

    # ── Fast scrapers — no browser needed ─────────────────────────────
    run_linkedin  = "linkedin"  in platforms
    run_remotive  = "remotive"  in platforms

    if run_linkedin or run_remotive:
        print("\n  Running fast scrapers (LinkedIn + Remotive)...")
        print("  This takes ~30 seconds...")
        try:
            from scraper.multi_scraper import (
                scrape_all_platforms, save_jobs as save_multi
            )
            jobs = scrape_all_platforms()
            if jobs:
                new_count, total = save_multi(jobs)
                all_new_jobs.extend(jobs)
                by_platform = {}
                for j in jobs:
                    p = j["platform"]
                    by_platform[p] = by_platform.get(p, 0) + 1
                for p, c in by_platform.items():
                    print(f"    {p}: {c} jobs")
                print(f"  Total new: {new_count}")
        except Exception as e:
            print(f"  Fast scraper error: {e}")

    # ── Selenium scrapers — need browser login ─────────────────────────
    if "naukri" in platforms:
        print("\n  Running Naukri scraper (~2 min)...")
        try:
            from scraper.naukri import (
                scrape_naukri_jobs, save_jobs as save_naukri
            )
            jobs = scrape_naukri_jobs()
            if jobs:
                new_count, total = save_naukri(jobs)
                all_new_jobs.extend(jobs)
                print(f"  Naukri: {len(jobs)} scraped, {new_count} new")
        except Exception as e:
            print(f"  Naukri error: {e}")

    if "indeed" in platforms:
        print("\n  Running Indeed scraper (~2 min)...")
        try:
            from scraper.indeed import (
                scrape_indeed_jobs, save_jobs as save_indeed
            )
            jobs = scrape_indeed_jobs()
            if jobs:
                new_count, total = save_indeed(jobs)
                all_new_jobs.extend(jobs)
                print(f"  Indeed: {len(jobs)} scraped, {new_count} new")
        except Exception as e:
            print(f"  Indeed error: {e}")

    if "wellfound" in platforms:
        print("\n  Running Wellfound scraper (~1 min)...")
        try:
            from scraper.wellfound import (
                scrape_wellfound_jobs, save_jobs as save_wf
            )
            jobs = scrape_wellfound_jobs()
            if jobs:
                new_count, total = save_wf(jobs)
                all_new_jobs.extend(jobs)
                print(f"  Wellfound: {len(jobs)} scraped, {new_count} new")
        except Exception as e:
            print(f"  Wellfound error: {e}")

    return all_new_jobs


# ── Step 3: Run pipeline on jobs ───────────────────────────────────────

def run_pipeline(jobs: list, max_jobs: int = None) -> dict:
    """
    Runs jobs through the full pipeline:
    analyse → match score → tailor (5 layers) → ATS score
    → cover letter → PDF → answer questions → submit → track
    """
    max_jobs = max_jobs or MAX_JOBS

    # ── Get already-processed job IDs from database ────────────────────
    try:
        from tracker.database import Session
        from tracker.models   import Application

        session       = Session()
        processed_ids = set(
            row.job_id for row in
            session.query(Application.job_id).all()
        )
        session.close()
    except Exception:
        processed_ids = set()

    # ── Filter to only unprocessed jobs ───────────────────────────────
    unprocessed   = [j for j in jobs
                     if j["job_id"] not in processed_ids]
    already_done  = len(jobs) - len(unprocessed)

    print(f"  Total loaded:     {len(jobs)}")
    print(f"  Already done:     {already_done}")
    print(f"  New to process:   {len(unprocessed)}")

    if not unprocessed:
        print("\n  No new jobs to process.")
        print(f"  Database has {len(processed_ids)} processed jobs.")
        print("  Tip: Run --mode fast or --mode full to scrape new jobs.")
        return {"submitted": 0, "skipped": 0, "failed": 0, "low_ats": 0}

    # Take up to max_jobs from unprocessed
    batch = unprocessed[:max_jobs]
    total = len(batch)

    results = {
        "submitted": 0,
        "skipped":   0,
        "failed":    0,
        "low_ats":   0,
    }

    print(f"\n  Processing {total} jobs...\n")
    print("  " + "─" * 53)

    for i, job in enumerate(batch):
        print(f"\n  Job {i+1}/{total}: {job['job_title']} "
              f"at {job['company']}")
        print(f"  Platform: {job['platform']} | "
              f"Location: {job.get('location', 'N/A')}")

        start = time.time()

        try:
            result  = pipeline.invoke(job)
            elapsed = time.time() - start
            status  = result.get("status", "unknown")

            # Count result
            results[status] = results.get(status, 0) + 1

            # Show summary
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

        # Pause between jobs — rate limiting
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

    print(f"\n  Log file: data/submissions.log")
    print("\n" + "="*55)


# ── Main entry point ───────────────────────────────────────────────────

def main(
    scrape:    bool = True,
    platforms: list = None,
    max_jobs:  int  = None,
    use_saved: bool = True,
):
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


# ── Argument parser ────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="AI Job Application Agent",
        formatter_class=argparse.RawTextHelpFormatter
    )

    parser.add_argument(
        "--mode",
        choices=["full", "fast", "pipeline-only", "scrape-only"],
        default="pipeline-only",
        help=(
            "full         = all scrapers + pipeline\n"
            "fast         = LinkedIn + Remotive only (~30s) + pipeline\n"
            "pipeline-only= use saved jobs, no scraping\n"
            "scrape-only  = just scrape, don't run pipeline"
        )
    )

    parser.add_argument(
        "--platforms",
        nargs="+",
        choices=["linkedin", "naukri", "indeed", "wellfound", "remotive"],
        default=None,
        help="Which platforms to scrape (default: all)"
    )

    parser.add_argument(
        "--max-jobs",
        type=int,
        default=10,
        help="Max jobs to process through pipeline (default: 10)"
    )

    args = parser.parse_args()

    if args.mode == "full":
        main(
            scrape    = True,
            platforms = args.platforms,
            max_jobs  = args.max_jobs,
            use_saved = True,
        )

    elif args.mode == "fast":
        # Only LinkedIn + Remotive — no browser, ~30 seconds
        main(
            scrape    = True,
            platforms = ["linkedin", "remotive"],
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
        print("\nScraping jobs only — pipeline will not run\n")
        scrape_fresh_jobs(args.platforms)
        print("\n[Loading saved jobs]\n")
        jobs = load_all_jobs()
        print(f"\nTotal jobs ready for pipeline: {len(jobs)}")
        print("Run pipeline with:")
        print(f"  python main.py --mode pipeline-only --max-jobs {args.max_jobs}")