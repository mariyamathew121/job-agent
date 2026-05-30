# scraper/multi_scraper.py
# Scrapes jobs from multiple platforms simultaneously.
# Uses direct HTTP/API calls — much faster than Selenium.

import os
import sys
import json
import httpx
import feedparser
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import (
    SEARCH_ROLES, SEARCH_LOCATIONS,
    MAX_JOBS, JOBS_PER_SEARCH
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Keywords to filter relevant tech jobs
TECH_KEYWORDS = [
    "python", "ai", "machine learning", "data", "software",
    "engineer", "developer", "ml", "backend", "llm", "nlp",
    "deep learning", "data science", "analytics", "cloud",
    "devops", "fullstack", "full stack", "api", "django",
    "fastapi", "flask", "tensorflow", "pytorch", "scikit"
]

# Keywords to skip clearly irrelevant jobs
SKIP_KEYWORDS = [
    "video editor", "paid media", "marketing manager",
    "lawn", "sales executive", "graphic designer", "content writer",
    "accountant", "hr manager", "recruiter", "seo specialist",
    "social media", "customer support", "business development"
]


# ── Helpers ────────────────────────────────────────────────────────────

def clean_text(text: str) -> str:
    if not text:
        return ""
    return " ".join(text.split()).strip()


def make_job_id(platform: str, identifier: str) -> str:
    clean = str(identifier)[:60].replace("/", "_").replace("?", "_")
    return f"{platform}_{clean}"


def is_relevant(title: str) -> bool:
    """Check if job title is relevant to tech/AI roles."""
    title_lower = title.lower()
    if any(skip in title_lower for skip in SKIP_KEYWORDS):
        return False
    return True


def empty_job_template(platform: str) -> dict:
    return {
        "job_id":          "",
        "job_title":       "",
        "company":         "",
        "location":        "",
        "job_url":         "",
        "job_description": "",
        "platform":        platform,
        "status":          "scraped",
        "salary":          "",
        "posted_date":     "",
        "experience":      "",
        "jd_analysis":     None,
        "match":           None,
        "company_intel":   None,
        "should_apply":    None,
        "tailored_resume": None,
        "ats_result":      None,
        "cover_letter":    None,
        "pdf_path":        None,
        "custom_answers":  None,
        "error":           None,
        "submitted_at":    None,
    }


# ── Platform 1: LinkedIn ───────────────────────────────────────────────

def get_linkedin_description(job_url: str) -> str:
    """Fetch full job description from LinkedIn job page."""
    try:
        resp = httpx.get(job_url, headers=HEADERS,
                         timeout=10, follow_redirects=True)
        if resp.status_code != 200:
            return ""

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "html.parser")

        for cls in [
            "description__text",
            "show-more-less-html__markup",
            "jobs-description-content__text",
        ]:
            el = soup.find(class_=lambda c: c and cls in c)
            if el:
                return clean_text(el.get_text())

        return ""
    except Exception:
        return ""


def scrape_linkedin_api(role: str, location: str,
                        limit: int = 10) -> list:
    """
    LinkedIn public job search — no login required.
    Uses the guest jobs API endpoint.
    """
    jobs = []

    try:
        params = {
            "keywords": role,
            "location": location,
            "start":    0,
            "count":    limit,
            "f_E":      "2,3",       # Entry + Associate = 0-2 years
            "f_TPR":    "r604800",   # Last 7 days
            "sortBy":   "DD",        # Newest first
        }

        url  = ("https://www.linkedin.com/jobs-guest/jobs/api"
                "/seeMoreJobPostings/search")
        resp = httpx.get(url, params=params,
                         headers=HEADERS, timeout=15,
                         follow_redirects=True)

        if resp.status_code != 200:
            return []

        from bs4 import BeautifulSoup
        soup  = BeautifulSoup(resp.text, "html.parser")
        cards = soup.find_all("div", class_="base-card")

        for card in cards[:limit]:
            try:
                title_el   = card.find("h3", class_="base-search-card__title")
                company_el = card.find("h4", class_="base-search-card__subtitle")
                loc_el     = card.find("span", class_="job-search-card__location")
                link_el    = card.find("a", class_="base-card__full-link")
                date_el    = card.find("time")

                title   = clean_text(title_el.text)   if title_el   else ""
                company = clean_text(company_el.text) if company_el else ""
                loc     = clean_text(loc_el.text)     if loc_el     else location
                url_str = link_el["href"].split("?")[0] if link_el  else ""
                date    = date_el.get("datetime", "")  if date_el   else ""

                if not title or not url_str:
                    continue
                if not is_relevant(title):
                    continue

                desc = get_linkedin_description(url_str)

                job                    = empty_job_template("linkedin")
                job["job_id"]          = make_job_id(
                    "linkedin", url_str.split("/")[-1]
                )
                job["job_title"]       = title
                job["company"]         = company
                job["location"]        = loc
                job["job_url"]         = url_str
                job["job_description"] = desc
                job["posted_date"]     = date

                if desc and len(desc) > 100:
                    jobs.append(job)

            except Exception:
                continue

    except Exception as e:
        print(f"    LinkedIn error: {e}")

    return jobs


# ── Platform 2: Indeed ─────────────────────────────────────────────────

def scrape_indeed(role: str, location: str,
                  limit: int = 10) -> list:
    """
    Indeed via RSS feed — most reliable method.
    Falls back to HTML scraping if RSS fails.
    """
    jobs = []

    try:
        role_enc = role.replace(" ", "+")
        loc_enc  = location.replace(" ", "+")

        # Try RSS first (most reliable)
        rss_urls = [
            f"https://in.indeed.com/rss?q={role_enc}&l={loc_enc}&fromage=7&sort=date",
            f"https://www.indeed.com/rss?q={role_enc}&l={loc_enc}&fromage=7&sort=date",
        ]

        for rss_url in rss_urls:
            feed = feedparser.parse(rss_url)
            if not feed.entries:
                continue

            for entry in feed.entries[:limit]:
                try:
                    title   = clean_text(entry.get("title", ""))
                    url_str = entry.get("link", "")
                    summary = clean_text(entry.get("summary", ""))
                    date    = entry.get("published", "")

                    # Clean title — Indeed often adds " - Company - Location"
                    if " - " in title:
                        parts = title.split(" - ")
                        title = parts[0].strip()

                    # Get company from source
                    company = ""
                    if hasattr(entry, "source") and entry.source:
                        company = entry.source.get("title", "")

                    if not title or not is_relevant(title):
                        continue

                    job                    = empty_job_template("indeed")
                    job["job_id"]          = make_job_id("indeed", url_str)
                    job["job_title"]       = title
                    job["company"]         = company
                    job["location"]        = location
                    job["job_url"]         = url_str
                    job["job_description"] = summary if len(summary) > 50 \
                                             else f"{title} role in {location}"
                    job["posted_date"]     = date

                    if title:
                        jobs.append(job)

                except Exception:
                    continue

            if jobs:
                break

        # Fallback: HTML scraping if RSS returned nothing
        if not jobs:
            html_url = (
                f"https://in.indeed.com/jobs"
                f"?q={role_enc}&l={loc_enc}&fromage=7&sort=date"
            )
            resp = httpx.get(html_url, headers=HEADERS,
                             timeout=15, follow_redirects=True)

            if resp.status_code == 200:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "html.parser")

                # Multiple selectors — Indeed changes these often
                cards = (
                    soup.find_all("div", class_=lambda c: c and
                                  "job_seen_beacon" in c) or
                    soup.find_all("td", class_=lambda c: c and
                                  "resultContent" in c) or
                    soup.find_all("div", attrs={"data-jk": True})
                )

                for card in cards[:limit]:
                    try:
                        title_el   = (
                            card.find("h2", class_=lambda c: c and
                                      "jobTitle" in c) or
                            card.find("a", attrs={"data-jk": True})
                        )
                        company_el = card.find(
                            "span", class_=lambda c: c and
                            "companyName" in c
                        )
                        loc_el     = card.find(
                            "div", class_=lambda c: c and
                            "companyLocation" in c
                        )
                        link_el    = card.find("a", href=True)

                        title   = clean_text(title_el.get_text()) \
                                  if title_el else ""
                        company = clean_text(company_el.get_text()) \
                                  if company_el else ""
                        loc     = clean_text(loc_el.get_text()) \
                                  if loc_el else location
                        href    = link_el["href"] if link_el else ""

                        if not title or not is_relevant(title):
                            continue

                        job_url = f"https://in.indeed.com{href}" \
                                  if href.startswith("/") else href

                        job                    = empty_job_template("indeed")
                        job["job_id"]          = make_job_id("indeed", job_url or title)
                        job["job_title"]       = title
                        job["company"]         = company
                        job["location"]        = loc
                        job["job_url"]         = job_url
                        job["job_description"] = (
                            f"{title} position at {company}. Location: {loc}. "
                            f"Apply now on Indeed."
                        )

                        jobs.append(job)

                    except Exception:
                        continue

    except Exception as e:
        print(f"    Indeed error: {e}")

    return jobs


# ── Platform 3: Remotive ───────────────────────────────────────────────

def scrape_remotive(role: str, limit: int = 10) -> list:
    """
    Remotive free API — best source for remote tech jobs globally.
    Filtered to only return relevant tech roles.
    """
    jobs = []

    TECH_CATEGORIES = [
        "software-dev",
        "data",
        "devops-sysadmin",
    ]

    try:
        for category in TECH_CATEGORIES:
            if len(jobs) >= limit:
                break

            resp = httpx.get(
                "https://remotive.com/api/remote-jobs",
                params={
                    "search":   role,
                    "limit":    limit,
                    "category": category
                },
                timeout=10
            )

            if resp.status_code != 200:
                continue

            for item in resp.json().get("jobs", []):
                if len(jobs) >= limit:
                    break

                try:
                    from bs4 import BeautifulSoup
                    title = item.get("title", "")

                    if not is_relevant(title):
                        continue

                    desc = clean_text(
                        BeautifulSoup(
                            item.get("description", ""),
                            "html.parser"
                        ).get_text()
                    )

                    if not desc or len(desc) < 100:
                        continue

                    job                    = empty_job_template("remotive")
                    job["job_id"]          = make_job_id(
                        "remotive", str(item.get("id", ""))
                    )
                    job["job_title"]       = title
                    job["company"]         = item.get("company_name", "")
                    job["location"]        = item.get(
                        "candidate_required_location", "Remote"
                    )
                    job["job_url"]         = item.get("url", "")
                    job["job_description"] = desc
                    job["salary"]          = item.get("salary", "")
                    job["posted_date"]     = item.get("publication_date", "")

                    jobs.append(job)

                except Exception:
                    continue

    except Exception as e:
        print(f"    Remotive error: {e}")

    return jobs


# ── Platform 4: Naukri ─────────────────────────────────────────────────

def scrape_naukri(role: str, location: str,
                  limit: int = 10) -> list:
    """
    Naukri — best platform for Indian job market.
    Uses their internal JSON API.
    """
    jobs = []

    try:
        # Method 1: JSON API
        url = "https://www.naukri.com/jobapi/v3/search"
        params = {
            "noOfResults": limit,
            "urlType":     "search_by_key_loc",
            "searchType":  "adv",
            "keyword":     role,
            "location":    location,
            "experience":  0,
            "experienceDD":2,
            "jobAge":      7,
        }
        headers = {
            **HEADERS,
            "appid":    "109",
            "systemid": "109",
            "Referer":  "https://www.naukri.com/",
        }

        resp = httpx.get(url, params=params,
                         headers=headers, timeout=15,
                         follow_redirects=True)

        if resp.status_code == 200:
            data     = resp.json()
            job_list = data.get("jobDetails", [])

            for item in job_list[:limit]:
                try:
                    title   = item.get("title", "")
                    company = item.get("companyName", "")
                    jd_url  = item.get("jdURL", "")

                    if not title or not is_relevant(title):
                        continue

                    # Extract location from placeholders
                    loc    = location
                    salary = ""
                    for ph in item.get("placeholders", []):
                        if ph.get("type") == "location":
                            loc = ph.get("label", location)
                        if ph.get("type") == "salary":
                            salary = ph.get("label", "")

                    # Description from tags and skills
                    desc = clean_text(
                        item.get("jobDescription", "") or
                        item.get("tagsAndSkills", "") or
                        f"{title} at {company} in {loc}"
                    )

                    full_url = (
                        "https://www.naukri.com" + jd_url
                        if jd_url.startswith("/") else jd_url
                    )

                    job                    = empty_job_template("naukri")
                    job["job_id"]          = make_job_id(
                        "naukri", str(item.get("jobId", jd_url or title))
                    )
                    job["job_title"]       = title
                    job["company"]         = company
                    job["location"]        = loc
                    job["job_url"]         = full_url
                    job["job_description"] = desc
                    job["salary"]          = salary

                    jobs.append(job)

                except Exception:
                    continue

        # Method 2: HTML scraping fallback
        if not jobs:
            role_slug = role.lower().replace(" ", "-")
            loc_slug  = location.lower().replace(" ", "-")
            html_url  = (
                f"https://www.naukri.com/"
                f"{role_slug}-jobs-in-{loc_slug}"
            )

            resp = httpx.get(html_url, headers=HEADERS,
                             timeout=15, follow_redirects=True)

            if resp.status_code == 200:
                from bs4 import BeautifulSoup
                soup  = BeautifulSoup(resp.text, "html.parser")

                cards = (
                    soup.find_all("article", class_=lambda c: c and
                                  "jobTuple" in c) or
                    soup.find_all("div", class_=lambda c: c and
                                  "srp-jobtuple" in c) or
                    soup.find_all("div", class_=lambda c: c and
                                  "cust-job-tuple" in c)
                )

                for card in cards[:limit]:
                    try:
                        title_el   = (
                            card.find("a", class_=lambda c: c and
                                      "title" in c) or
                            card.find("a", attrs={"title": True})
                        )
                        company_el = (
                            card.find("a", class_=lambda c: c and
                                      "subTitle" in c) or
                            card.find("span", class_=lambda c: c and
                                      "comp-name" in c)
                        )

                        title   = clean_text(title_el.get_text()) \
                                  if title_el else ""
                        company = clean_text(company_el.get_text()) \
                                  if company_el else ""
                        job_url = title_el.get("href", "") \
                                  if title_el else ""

                        if not title or not is_relevant(title):
                            continue

                        job                    = empty_job_template("naukri")
                        job["job_id"]          = make_job_id(
                            "naukri", job_url or title
                        )
                        job["job_title"]       = title
                        job["company"]         = company
                        job["location"]        = location
                        job["job_url"]         = job_url
                        job["job_description"] = (
                            f"{title} position at {company}. "
                            f"Location: {location}."
                        )

                        jobs.append(job)

                    except Exception:
                        continue

    except Exception as e:
        print(f"    Naukri error: {e}")

    return jobs


# ── Platform 5: Wellfound ──────────────────────────────────────────────

def scrape_wellfound(role: str, limit: int = 10) -> list:
    """
    Wellfound (AngelList) — best for AI/tech startup jobs.
    Uses their role listing pages.
    """
    jobs = []

    try:
        role_slug = role.lower().replace(" ", "-")

        # Try role-specific pages
        urls = [
            f"https://wellfound.com/role/l/{role_slug}",
            f"https://wellfound.com/jobs?q%5Bkeywords%5D={role.replace(' ', '+')}",
        ]

        for url in urls:
            resp = httpx.get(url, headers=HEADERS,
                             timeout=12, follow_redirects=True)

            if resp.status_code != 200:
                continue

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "html.parser")

            # Try multiple card selectors
            cards = (
                soup.find_all("div", attrs={"data-test": "StartupResult"}) or
                soup.find_all("div", class_=lambda c: c and
                              "styles_component" in " ".join(c)
                              if isinstance(c, list) else
                              "styles_component" in str(c)) or
                soup.find_all("a", href=lambda h: h and "/jobs/" in str(h))
            )

            for card in cards[:limit]:
                try:
                    # Handle both card types
                    if card.name == "a":
                        title   = clean_text(card.get_text())
                        url_str = ("https://wellfound.com" + card["href"]
                                   if card["href"].startswith("/")
                                   else card["href"])
                        company = "Startup"
                        loc     = "Remote"
                        desc    = f"{title} position at a tech startup"
                    else:
                        title_el   = (
                            card.find("a", attrs={"data-test": "job-title"}) or
                            card.find("h2") or card.find("h3")
                        )
                        company_el = (
                            card.find("a", attrs={"data-test": "startup-link"}) or
                            card.find("span", class_=lambda c: c and
                                      "company" in str(c).lower())
                        )
                        loc_el  = card.find(
                            "span", attrs={"data-test": "location"}
                        )
                        desc_el = card.find(
                            "div", attrs={"data-test": "job-description"}
                        )

                        title   = clean_text(title_el.get_text()) \
                                  if title_el else ""
                        company = clean_text(company_el.get_text()) \
                                  if company_el else "Startup"
                        loc     = clean_text(loc_el.get_text()) \
                                  if loc_el else "Remote"
                        desc    = clean_text(desc_el.get_text()) \
                                  if desc_el else ""

                        href    = (title_el.get("href", "")
                                   if title_el else "")
                        url_str = ("https://wellfound.com" + href
                                   if href.startswith("/") else href)

                    if not title or not is_relevant(title):
                        continue

                    job                    = empty_job_template("wellfound")
                    job["job_id"]          = make_job_id("wellfound", url_str or title)
                    job["job_title"]       = title
                    job["company"]         = company
                    job["location"]        = loc
                    job["job_url"]         = url_str
                    job["job_description"] = desc or (
                        f"{title} position at {company}. "
                        f"Apply on Wellfound."
                    )

                    jobs.append(job)

                except Exception:
                    continue

            if jobs:
                break

    except Exception as e:
        print(f"    Wellfound error: {e}")

    return jobs


# ── Run all platforms in parallel ─────────────────────────────────────

def scrape_all_platforms(progress_callback=None) -> list:
    """
    Scrapes all 5 platforms simultaneously using threads.
    Returns deduplicated, relevance-filtered job list.
    """
    all_jobs = []
    seen_ids = set()

    # Build all search tasks
    tasks = []
    for role in SEARCH_ROLES:
        for location in SEARCH_LOCATIONS:
            tasks.append(("linkedin", role, location))
            tasks.append(("indeed",   role, location))
            tasks.append(("naukri",   role, location))
        tasks.append(("remotive",  role, None))
        tasks.append(("wellfound", role, None))

    def run_task(task):
        platform, role, location = task
        try:
            if platform == "linkedin":
                return platform, scrape_linkedin_api(
                    role, location, JOBS_PER_SEARCH
                )
            elif platform == "indeed":
                return platform, scrape_indeed(
                    role, location, JOBS_PER_SEARCH
                )
            elif platform == "naukri":
                return platform, scrape_naukri(
                    role, location, JOBS_PER_SEARCH
                )
            elif platform == "remotive":
                return platform, scrape_remotive(
                    role, JOBS_PER_SEARCH
                )
            elif platform == "wellfound":
                return platform, scrape_wellfound(
                    role, JOBS_PER_SEARCH
                )
        except Exception as e:
            print(f"    {platform} task error: {e}")
            return platform, []

    results_by_platform = {
        "linkedin":  0,
        "indeed":    0,
        "naukri":    0,
        "remotive":  0,
        "wellfound": 0,
    }

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(run_task, t): t for t in tasks}

        for future in as_completed(futures):
            platform, jobs = future.result()

            for job in jobs:
                if job["job_id"] not in seen_ids:
                    seen_ids.add(job["job_id"])
                    all_jobs.append(job)
                    results_by_platform[platform] += 1

            if progress_callback:
                progress_callback(
                    platform, results_by_platform[platform]
                )

    return all_jobs


# ── Save ───────────────────────────────────────────────────────────────

def save_jobs(jobs: list, filename="data/all_jobs.json"):
    os.makedirs("data", exist_ok=True)

    existing = []
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            existing = json.load(f)

    existing_ids = {j["job_id"] for j in existing}
    new_jobs     = [j for j in jobs if j["job_id"] not in existing_ids]
    all_jobs     = existing + new_jobs

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(all_jobs, f, indent=2, ensure_ascii=False)

    return len(new_jobs), len(all_jobs)


# ── Run ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\nMulti-Platform Job Scraper")
    print("=" * 55)
    print(f"Roles:     {', '.join(SEARCH_ROLES)}")
    print(f"Locations: {', '.join(SEARCH_LOCATIONS)}")
    print(f"Platforms: LinkedIn · Indeed · Naukri · Remotive · Wellfound")
    print("=" * 55)
    print("\nScraping all platforms simultaneously...\n")

    platform_counts = {}

    def on_progress(platform, count):
        platform_counts[platform] = count
        counts_str = " | ".join([
            f"{p}: {c}" for p, c in platform_counts.items()
        ])
        print(f"  Progress → {counts_str}", end="\r")

    start   = time.time()
    jobs    = scrape_all_platforms(progress_callback=on_progress)
    elapsed = time.time() - start

    print(f"\n\nCompleted in {elapsed:.1f} seconds")

    if jobs:
        new_count, total = save_jobs(jobs)

        print(f"\n── Results ───────────────────────────────────────")
        print(f"  Total jobs found:  {len(jobs)}")
        print(f"  New jobs saved:    {new_count}")
        print(f"  Total in file:     {total}")
        print(f"  File:              data/all_jobs.json")

        print(f"\n── By platform ───────────────────────────────────")
        by_platform = {}
        for job in jobs:
            p = job["platform"]
            by_platform[p] = by_platform.get(p, 0) + 1
        for platform, count in sorted(
            by_platform.items(), key=lambda x: x[1], reverse=True
        ):
            bar = "█" * min(count, 30)
            print(f"  {platform:<12} {bar} {count}")

        print(f"\n── Sample jobs ───────────────────────────────────")
        shown = 0
        for job in jobs:
            if shown >= 5:
                break
            if len(job["job_description"]) > 80:
                print(f"\n  [{job['platform'].upper()}]")
                print(f"  {job['job_title']} at {job['company']}")
                print(f"  {job['location']}")
                if job["salary"]:
                    print(f"  Salary: {job['salary']}")
                print(f"  {job['job_description'][:120]}...")
                shown += 1
    else:
        print("\nNo jobs found — check your internet connection")
