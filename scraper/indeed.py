# scraper/indeed.py
# Scrapes jobs from Indeed using Selenium with Google login.
# Cookies saved after first login — subsequent runs skip login.

import os
import sys
import json
import time
import random
import pickle
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from bs4 import BeautifulSoup
from config.settings import (
    INDEED_EMAIL, SEARCH_ROLES,
    SEARCH_LOCATIONS, JOBS_PER_SEARCH, MAX_JOBS
)

COOKIES_FILE = "data/indeed_cookies.pkl"

# ── Relevance filters ──────────────────────────────────────────────────

SKIP_TITLES = [
    "customer care", "customer support", "bpo", "voice process",
    "content writer", "accountant", "sales executive", "field sales",
    "marketing", "teacher", "tutor", "faculty", "hr executive",
    "social media", "seo", "telecaller", "nurse", "doctor",
    "civil engineer", "mechanical", "electrical", "graphic designer"
]

REQUIRED_KEYWORDS = [
    "python", "ai ", "artificial intelligence", "machine learning",
    "data scientist", "data engineer", "data analyst", "ml ",
    "software developer", "software engineer", "backend",
    "full stack", "fullstack", "deep learning", "llm", "nlp",
    "generative ai", "ai engineer", "ai developer", "ai/ml",
    "data science", "devops", "cloud", "django", "fastapi",
    "flask", "tensorflow", "pytorch"
]


def is_relevant(title: str) -> bool:
    t = title.lower()
    if any(skip in t for skip in SKIP_TITLES):
        return False
    return any(req in t for req in REQUIRED_KEYWORDS)


# ── Helpers ────────────────────────────────────────────────────────────

def pause(min_sec=1.0, max_sec=2.5):
    time.sleep(random.uniform(min_sec, max_sec))


def get_driver():
    options = uc.ChromeOptions()
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    driver = uc.Chrome(options=options, version_main=147)
    return driver


# ── Cookie management ──────────────────────────────────────────────────

def save_cookies(driver):
    os.makedirs("data", exist_ok=True)
    with open(COOKIES_FILE, "wb") as f:
        pickle.dump(driver.get_cookies(), f)
    print("  Indeed session saved")


def load_cookies(driver) -> bool:
    if not os.path.exists(COOKIES_FILE):
        return False

    driver.get("https://in.indeed.com")
    pause(2, 3)

    with open(COOKIES_FILE, "rb") as f:
        cookies = pickle.load(f)

    for cookie in cookies:
        try:
            driver.add_cookie(cookie)
        except Exception:
            pass

    driver.refresh()
    pause(2, 3)

    page = driver.page_source.lower()
    if "sign out" in page or "my account" in page or \
       (INDEED_EMAIL and INDEED_EMAIL in driver.page_source):
        print("  Logged in via saved session")
        return True

    return False


# ── Login ──────────────────────────────────────────────────────────────

def login(driver) -> bool:
    """
    Login to Indeed using Google account.
    Auto-detects when login completes.
    """
    print("  Checking saved Indeed session...")
    if load_cookies(driver):
        return True

    print("  Opening Indeed login...")
    driver.get("https://in.indeed.com/account/login")
    pause(3, 4)

    # Try clicking Continue with Google
    try:
        google_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((
                By.XPATH,
                "//button[contains(text(),'Google')] | "
                "//a[contains(text(),'Google')] | "
                "//div[contains(@aria-label,'Google')] | "
                "//span[contains(text(),'Continue with Google')]"
            ))
        )
        google_btn.click()
        print("  Clicked Google login")
        pause(2, 3)
    except TimeoutException:
        print("  Please click Continue with Google in the browser")

    print("\n" + "="*55)
    print("  Complete Google login in the browser.")
    print(f"  Select: {INDEED_EMAIL}")
    print("  Script auto-detects when done.")
    print("="*55 + "\n")

    for i in range(180):
        time.sleep(1)
        current = driver.current_url
        page    = driver.page_source.lower()

        if i % 20 == 0 and i > 0:
            print(f"  Waiting... ({i}s)")

        if "indeed.com" in current and "login" not in current:
            if "sign out" in page or "my account" in page or \
               "resume" in page or "dashboard" in page:
                print(f"  Logged in after {i}s")
                save_cookies(driver)
                return True

    print("  Login timed out")
    return False


# ── Search and extract ─────────────────────────────────────────────────

def search_and_extract(driver, role: str,
                       location: str, limit: int) -> list:
    """Search Indeed and return only relevant tech jobs."""
    jobs = []

    try:
        role_enc = role.replace(" ", "+")
        loc_enc  = location.replace(" ", "+")

        url = (
            f"https://in.indeed.com/jobs"
            f"?q={role_enc}"
            f"&l={loc_enc}"
            f"&fromage=7"
            f"&sort=date"
            f"&explvl=entry_level"
        )

        print(f"  [{role}] in [{location}]", end=" → ", flush=True)
        driver.get(url)
        pause(2, 3)

        # Scroll to load more
        driver.execute_script("window.scrollTo(0, 1000)")
        pause(1, 1.5)

        soup  = BeautifulSoup(driver.page_source, "html.parser")

        # Indeed card selectors
        cards = (
            soup.find_all("div", class_=lambda c: c and
                          "job_seen_beacon" in str(c)) or
            soup.find_all("td", class_=lambda c: c and
                          "resultContent" in str(c)) or
            soup.find_all("div", attrs={"data-jk": True})
        )

        relevant_found = 0

        for card in cards:
            if relevant_found >= limit:
                break

            try:
                # Title
                title_el = (
                    card.find("h2", class_=lambda c: c and
                              "jobTitle" in str(c)) or
                    card.find("a", attrs={"data-jk": True}) or
                    card.find("h2")
                )

                if not title_el:
                    continue

                title = title_el.get_text().strip()
                # Clean "new" prefix Indeed sometimes adds
                title = title.replace("new\n", "").strip()

                if not title or not is_relevant(title):
                    continue
                # Extra filter for trainer/teaching roles
                if any(word in title.lower() for word in
                       ["trainer", "training", "teach", "php"]):
                    continue

                # Company
                # Company — Indeed uses multiple selectors
                company_el = (
                    card.find("span", class_=lambda c: c and
                              "companyName" in str(c)) or
                    card.find("a", class_=lambda c: c and
                              "companyName" in str(c)) or
                    card.find("span", attrs={"data-testid": "company-name"}) or
                    card.find("span", class_=lambda c: c and
                              "company" in str(c).lower())
                )

                # Location
                loc_el = card.find(
                    "div", class_=lambda c: c and
                    "companyLocation" in str(c)
                )

                # Salary
                sal_el = card.find(
                    "div", class_=lambda c: c and
                    "salary" in str(c).lower()
                )

                # Job link
                link_el = card.find("a", href=lambda h: h and
                                    "/rc/clk" in str(h) or
                                    "/pagead" in str(h))
                if not link_el:
                    link_el = card.find("a", href=True)

                company = company_el.get_text().strip() \
                          if company_el else "Unknown"
                loc     = loc_el.get_text().strip() \
                          if loc_el     else location
                salary  = sal_el.get_text().strip() \
                          if sal_el     else ""
                href    = link_el["href"] \
                          if link_el    else ""

                job_url = (
                    f"https://in.indeed.com{href}"
                    if href.startswith("/") else href
                )

                full_desc = (
                    f"{title} position at {company}. "
                    f"Location: {loc}. "
                    f"{'Salary: ' + salary + '. ' if salary else ''}"
                    f"Apply on Indeed."
                )

                job_id = f"indeed_{href.split('jk=')[-1][:20]}" \
                         if "jk=" in href else \
                         f"indeed_{title[:30].replace(' ','_')}"

                jobs.append({
                    "job_id":          job_id,
                    "job_title":       title,
                    "company":         company,
                    "location":        loc,
                    "job_url":         job_url,
                    "job_description": full_desc,
                    "platform":        "indeed",
                    "status":          "scraped",
                    "salary":          salary,
                    "experience":      "0-2 years",
                    "posted_date":     "",
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
                })

                relevant_found += 1

            except Exception:
                continue

        print(f"{relevant_found} relevant jobs")

    except Exception as e:
        print(f"Error: {e}")

    return jobs


# ── Main ───────────────────────────────────────────────────────────────

def scrape_indeed_jobs() -> list:
    driver   = get_driver()
    all_jobs = []
    seen_ids = set()

    try:
        if not login(driver):
            print("Indeed login failed")
            return []

        print(f"\nSearching {len(SEARCH_ROLES)} roles × "
              f"{len(SEARCH_LOCATIONS)} locations...\n")

        for role in SEARCH_ROLES:
            for location in SEARCH_LOCATIONS:
                if len(all_jobs) >= MAX_JOBS:
                    break

                remaining = MAX_JOBS - len(all_jobs)
                target    = min(JOBS_PER_SEARCH, remaining)

                jobs = search_and_extract(
                    driver, role, location, target
                )

                for job in jobs:
                    if job["job_id"] not in seen_ids:
                        seen_ids.add(job["job_id"])
                        all_jobs.append(job)

                pause(1, 2)

            if len(all_jobs) >= MAX_JOBS:
                break

        print(f"\nTotal relevant jobs: {len(all_jobs)}")

    except KeyboardInterrupt:
        print("\nStopped")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        driver.quit()

    return all_jobs


def save_jobs(jobs, filename="data/indeed_jobs.json"):
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

    print(f"  {len(new_jobs)} new jobs saved to {filename}")
    return new_jobs


if __name__ == "__main__":
    print("Indeed Job Scraper")
    print("=" * 55)
    print(f"Roles:     {', '.join(SEARCH_ROLES)}")
    print(f"Locations: {', '.join(SEARCH_LOCATIONS)}")
    print(f"Filter:    Tech/AI jobs only, 0-2 years exp")
    print("=" * 55 + "\n")

    jobs = scrape_indeed_jobs()

    if jobs:
        save_jobs(jobs)
        print(f"\n── Sample jobs ───────────────────────────────")
        for job in jobs[:5]:
            print(f"\n  {job['job_title']} at {job['company']}")
            print(f"  {job['location']}")
            if job["salary"]:
                print(f"  Salary: {job['salary']}")
    else:
        print("No jobs scraped")