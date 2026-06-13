# scraper/naukri.py
# Scrapes jobs from Naukri using Selenium.
# Uses Google login — you approve once, cookies saved for next run.
# Only fetches relevant tech jobs — filters out irrelevant results.

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
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from bs4 import BeautifulSoup
from config.settings import (
    NAUKRI_EMAIL, SEARCH_ROLES,
    SEARCH_LOCATIONS, JOBS_PER_SEARCH, MAX_JOBS
)

COOKIES_FILE = "data/naukri_cookies.pkl"

# ── Relevance filters ──────────────────────────────────────────────────

# Jobs with these words in title get skipped
SKIP_TITLES = [
    "customer care", "customer support", "customer service",
    "bpo", "voice process", "non voice", "content writer",
    "accountant", "gold loan", "medical officer", "safety officer",
    "marketing executive", "sales executive", "field sales",
    "branch coordinator", "faculty", "tutor", "instructor",
    "subtitle writer", "fire fighting", "human resource",
    "chat support", "email support", "junior associate ar",
    "edu performance", "robotics instructor", "english tutor",
    "inside sales", "copywriter", "graphic designer",
    "office assistant", "business development", "seo",
    "social media", "telecaller", "loan officer", "finance",
    "operations executive", "hr executive", "legal",
    "civil engineer", "mechanical engineer", "electrical engineer",
    "nursing", "pharmacy", "doctor", "teacher", "professor" , "senior ai", "lead ai", "principal ai", "sr. ai",
    "senior engineer", "lead engineer", "senior developer",
    "8 to 13", "5 to 8", "7 to", "10 to", "12 to", "15 to", "20 to", "25 to", "30+"
]

# At least one of these must appear in job title
REQUIRED_KEYWORDS = [
    "python", "ai ", "artificial intelligence",
    "machine learning", "data scientist", "data engineer",
    "data analyst", "ml ", "software developer",
    "software engineer", "backend", "full stack", "fullstack",
    "deep learning", "llm", "nlp", "generative ai",
    "ai engineer", "ai developer", "ai/ml", "data science",
    "analytics engineer", "computer vision", "mlops",
    "devops", "cloud engineer", "django", "fastapi",
    "flask", "tensorflow", "pytorch", "spark", "hadoop",
    "aws engineer", "azure engineer", "gcp engineer"
]


def is_relevant(title: str) -> bool:
    """Return True only if job is relevant to tech/AI roles."""
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
    print("  Naukri session saved — next run skips login")


def load_cookies(driver) -> bool:
    if not os.path.exists(COOKIES_FILE):
        return False

    driver.get("https://www.naukri.com")
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
    if (NAUKRI_EMAIL and NAUKRI_EMAIL in driver.page_source) or \
       "logout" in page or "my profile" in page or \
       "naukri.com/mnjuser" in driver.current_url:
        print("  Logged in via saved session")
        return True

    return False


# ── Login ──────────────────────────────────────────────────────────────

def login(driver) -> bool:
    """
    Login to Naukri using Google account.
    Tries cookies first — skips login entirely if session exists.
    Otherwise opens browser for Google login once.
    Auto-detects when login completes — no Enter needed.
    """
    print("  Checking saved Naukri session...")
    if load_cookies(driver):
        return True

    print("  Opening Naukri login page...")
    driver.get("https://www.naukri.com/nlogin/login")
    pause(3, 4)

    # Try auto-clicking Google button
    try:
        google_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((
                By.XPATH,
                "//button[contains(text(),'Google')] | "
                "//a[contains(text(),'Google')] | "
                "//div[contains(@class,'google')] | "
                "//span[contains(text(),'Google')]"
            ))
        )
        google_btn.click()
        pause(2, 3)
        print("  Clicked Google login — please select your account")
    except TimeoutException:
        print("  Please click 'Login with Google' in the browser")

    print("\n" + "="*55)
    print("  Complete Google login in the browser window.")
    print("  Select: mariya.mathew103@gmail.com")
    print("  Script will auto-detect when you are logged in.")
    print("="*55 + "\n")

    # Auto-detect login completion
    for i in range(180):
        time.sleep(1)
        current = driver.current_url

        if i % 20 == 0 and i > 0:
            print(f"  Waiting for login... ({i}s)")

        if ("naukri.com" in current and
                "login"  not in current and
                "nlogin" not in current):

            page = driver.page_source.lower()
            if ("logout"     in page or
                "my profile" in page or
                "dashboard"  in page or
                "mnjuser"    in current):
                print(f"  Logged in after {i}s")
                save_cookies(driver)
                return True

    print("  Login timed out after 3 minutes")
    return False


# ── Search and extract ─────────────────────────────────────────────────

def search_and_extract(driver, role: str,
                       location: str, limit: int) -> list:
    """
    Search Naukri for a role in a location.
    Returns only relevant tech jobs — filters everything else out.
    """
    jobs = []

    try:
        role_enc = role.replace(" ", "%20")
        loc_enc  = location.replace(" ", "%20")

        # Use Naukri search with keyword + location + experience filter
        url = (
            f"https://www.naukri.com/jobs-in-india"
            f"?k={role_enc}"
            f"&l={loc_enc}"
            f"&experience=0"
            f"&experienceDD=2"
            f"&jobAge=7"
            f"&sort=1"  # sort by relevance
        )

        print(f"  [{role}] in [{location}]", end=" → ", flush=True)
        driver.get(url)
        pause(2, 3)

        # Single scroll to load more cards
        driver.execute_script("window.scrollTo(0, 1200)")
        pause(1, 1.5)

        soup = BeautifulSoup(driver.page_source, "html.parser")

        # Try multiple card selectors — Naukri changes these often
        cards = (
            soup.find_all("article", class_=lambda c:
                          "jobTuple" in str(c)) or
            soup.find_all("div", class_=lambda c:
                          "srp-jobtuple" in str(c)) or
            soup.find_all("div", class_=lambda c:
                          "cust-job-tuple" in str(c)) or
            soup.find_all("li", class_=lambda c:
                          "srp-jobtuple" in str(c)) or
            soup.find_all("div", attrs={"data-job-id": True})
        )

        relevant_found = 0

        for card in cards:
            if relevant_found >= limit:
                break

            try:
                # Title element
                title_el = (
                    card.find("a", class_=lambda c: c and
                              "title" in str(c)) or
                    card.find("a", attrs={"title": True}) or
                    card.find("h2")
                )

                if not title_el:
                    continue

                title = title_el.get_text().strip()

                # Filter — skip irrelevant jobs
                if not title or not is_relevant(title):
                    continue

                # Company
                company_el = (
                    card.find("a", class_=lambda c: c and
                              "comp-name" in str(c)) or
                    card.find("span", class_=lambda c: c and
                              "comp-name" in str(c)) or
                    card.find("a", class_=lambda c: c and
                              "company" in str(c).lower())
                )

                # Experience
                exp_el = (
                    card.find(class_=lambda c: c and
                              "expwdth" in str(c)) or
                    card.find(class_=lambda c: c and
                              "exp" in str(c).lower() and
                              "experience" in str(c).lower())
                )

                # Salary
                sal_el = (
                    card.find(class_=lambda c: c and
                              "salary" in str(c).lower()) or
                    card.find(class_=lambda c: c and
                              "sal" in str(c).lower())
                )

                # Location
                loc_el = (
                    card.find(class_=lambda c: c and
                              "locWdth" in str(c)) or
                    card.find(class_=lambda c: c and
                              "location" in str(c).lower() and
                              "color" not in str(c).lower())
                )

                # Job description snippet
                desc_el = (
                    card.find(class_=lambda c: c and
                              "job-desc" in str(c).lower()) or
                    card.find("ul", class_=lambda c: c and
                              "tags" in str(c).lower())
                )

                company = company_el.get_text().strip() \
                          if company_el else "Unknown"
                exp     = exp_el.get_text().strip() \
                          if exp_el     else "0-2 Yrs"
                salary  = sal_el.get_text().strip() \
                          if sal_el     else "Not disclosed"
                loc     = loc_el.get_text().strip() \
                          if loc_el     else location
                desc    = desc_el.get_text().strip() \
                          if desc_el    else ""
                job_url = title_el.get("href", "") \
                          if title_el   else ""

                # Skip jobs requiring more than 4 years experience
                exp_text = exp.lower()
                if any(x in exp_text for x in [
                    "5-", "6-", "7-", "8-", "9-", "10-",
                    "5 to", "6 to", "7 to", "8 to",
                    "5+ yr", "6+ yr", "7+ yr"
                ]):
                    continue
                
                # Clean up loc — remove extra text
                loc = loc.split("|")[0].strip()[:60]

                # Build a meaningful description
                full_desc = (
                    f"{title} position at {company}. "
                    f"Location: {loc}. "
                    f"Experience required: {exp}. "
                    f"Salary: {salary}. "
                    f"{desc}"
                ).strip()

                # Generate unique job ID
                job_id_raw = job_url.split("?")[0].split("/")[-1] \
                             if job_url else title[:30].replace(" ", "_")
                job_id = f"naukri_{job_id_raw}"

                jobs.append({
                    "job_id":          job_id,
                    "job_title":       title,
                    "company":         company,
                    "location":        loc,
                    "job_url":         job_url,
                    "job_description": full_desc,
                    "platform":        "naukri",
                    "status":          "scraped",
                    "salary":          salary,
                    "experience":      exp,
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

def scrape_naukri_jobs() -> list:
    """
    Main function — logs in once, searches all roles and locations,
    returns only relevant tech jobs.
    """
    driver   = get_driver()
    all_jobs = []
    seen_ids = set()

    try:
        if not login(driver):
            print("Naukri login failed")
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

                pause(1, 2)  # short pause between searches

            if len(all_jobs) >= MAX_JOBS:
                break

        print(f"\nTotal relevant jobs found: {len(all_jobs)}")

    except KeyboardInterrupt:
        print("\nStopped by user")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        driver.quit()

    return all_jobs


def save_jobs(jobs, filename="data/naukri_jobs.json"):
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
    print("Naukri Job Scraper")
    print("=" * 55)
    print(f"Roles:     {', '.join(SEARCH_ROLES)}")
    print(f"Locations: {', '.join(SEARCH_LOCATIONS)}")
    print(f"Filter:    Only relevant tech/AI jobs")
    print("=" * 55 + "\n")

    jobs = scrape_naukri_jobs()

    if jobs:
        save_jobs(jobs)

        print(f"\n── Sample jobs ───────────────────────────────────")
        for job in jobs[:5]:
            print(f"\n  {job['job_title']} at {job['company']}")
            print(f"  {job['location']} | {job['salary']}")
            print(f"  {job['job_description'][:100]}...")
    else:
        print("No relevant jobs scraped")
