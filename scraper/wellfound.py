# scraper/wellfound.py
# Scrapes startup jobs from Wellfound using Selenium + email login.

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
    WELLFOUND_EMAIL, WELLFOUND_PASSWORD,
    SEARCH_ROLES, JOBS_PER_SEARCH, MAX_JOBS
)

COOKIES_FILE = "data/wellfound_cookies.pkl"

SKIP_TITLES = [
    "customer", "sales", "marketing", "content writer",
    "accountant", "hr ", "recruiter", "graphic", "seo",
    "social media", "teacher", "tutor", "support"
]

REQUIRED_KEYWORDS = [
    "python", "ai ", "machine learning", "data scientist",
    "data engineer", "software engineer", "software developer",
    "backend", "full stack", "ml ", "llm", "nlp",
    "deep learning", "generative ai", "ai engineer",
    "data science", "devops", "cloud", "fastapi"
]


def is_relevant(title: str) -> bool:
    t = title.lower()
    if any(s in t for s in SKIP_TITLES):
        return False
    return any(r in t for r in REQUIRED_KEYWORDS)


def pause(min_sec=1.0, max_sec=2.5):
    time.sleep(random.uniform(min_sec, max_sec))


def get_driver():
    options = uc.ChromeOptions()
    options.add_argument("--window-size=1920,1080")
    driver = uc.Chrome(options=options, version_main=147)
    return driver


def save_cookies(driver):
    os.makedirs("data", exist_ok=True)
    with open(COOKIES_FILE, "wb") as f:
        pickle.dump(driver.get_cookies(), f)
    print("  Wellfound session saved")


def load_cookies(driver) -> bool:
    if not os.path.exists(COOKIES_FILE):
        return False

    driver.get("https://wellfound.com")
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
    if "sign out" in page or "log out" in page or \
       "dashboard" in page or "profile" in page:
        print("  Logged in via saved session")
        return True

    return False


def login(driver) -> bool:
    """Login to Wellfound with email and password."""
    print("  Checking saved Wellfound session...")
    if load_cookies(driver):
        return True

    print("  Opening Wellfound login...")
    driver.get("https://wellfound.com/login")
    pause(3, 4)

    try:
        # Try Google login first
        google_btn = WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable((
                By.XPATH,
                "//a[contains(text(),'Google')] | "
                "//button[contains(text(),'Google')] | "
                "//a[contains(@href,'google')]"
            ))
        )
        google_btn.click()
        print("  Clicked Google login")
        pause(2, 3)

    except TimeoutException:
        # Fall back to email/password
        print("  Using email/password login...")
        try:
            email_field = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located(
                    (By.XPATH,
                     "//input[@type='email'] | //input[@name='email']")
                )
            )
            email_field.clear()
            for char in WELLFOUND_EMAIL:
                email_field.send_keys(char)
                time.sleep(0.05)
            pause(1, 1.5)

            pwd_field = driver.find_element(
                By.XPATH,
                "//input[@type='password'] | //input[@name='password']"
            )
            for char in WELLFOUND_PASSWORD:
                pwd_field.send_keys(char)
                time.sleep(0.05)
            pause(1, 1.5)
            pwd_field.submit()

        except Exception as e:
            print(f"  Login form error: {e}")
            print("  Please log in manually in the browser")

    print("\n" + "="*55)
    print("  Complete login in the browser if needed.")
    print("  Script auto-detects when done.")
    print("="*55 + "\n")

    for i in range(120):
        time.sleep(1)
        page    = driver.page_source.lower()
        current = driver.current_url

        if i % 20 == 0 and i > 0:
            print(f"  Waiting... ({i}s)")

        if "wellfound.com" in current and "login" not in current:
            if "sign out" in page or "log out" in page or \
               "dashboard" in page or "jobs" in current:
                print(f"  Logged in after {i}s")
                save_cookies(driver)
                return True

    print("  Login timed out")
    return False


def search_and_extract(driver, role: str,
                       limit: int) -> list:
    """Search Wellfound for a role and extract relevant jobs."""
    jobs = []

    try:
        role_slug = role.lower().replace(" ", "-")
        urls = [
            f"https://wellfound.com/role/l/{role_slug}",
            f"https://wellfound.com/jobs?q%5Bkeywords%5D={role.replace(' ','+')}",
        ]

        print(f"  [{role}]", end=" → ", flush=True)

        for url in urls:
            driver.get(url)
            pause(2, 3)

            driver.execute_script("window.scrollTo(0, 1000)")
            pause(1, 1.5)

            soup  = BeautifulSoup(driver.page_source, "html.parser")

            # Try multiple card patterns
            cards = (
                soup.find_all("div", attrs={
                    "data-test": "StartupResult"
                }) or
                soup.find_all("div", class_=lambda c: c and
                              "job" in str(c).lower() and
                              "card" in str(c).lower()) or
                soup.find_all("a", href=lambda h: h and
                              "/jobs/" in str(h))
            )

            relevant_found = 0

            for card in cards[:limit * 3]:
                if relevant_found >= limit:
                    break

                try:
                    if card.name == "a":
                        title   = card.get_text().strip()
                        url_str = ("https://wellfound.com" + card["href"]
                                   if card["href"].startswith("/")
                                   else card["href"])
                        company = "Startup"
                        loc     = "Remote"
                        desc    = f"{title} at a tech startup"
                    else:
                        title_el   = (
                            card.find("a", attrs={
                                "data-test": "job-title"}) or
                            card.find("h2") or
                            card.find("h3") or
                            card.find("a", href=lambda h: h and
                                      "/jobs/" in str(h))
                        )
                        company_el = (
                            card.find("a", attrs={
                                "data-test": "startup-link"}) or
                            card.find("span", class_=lambda c: c and
                                      "startup" in str(c).lower())
                        )
                        loc_el  = card.find(
                            "span", attrs={"data-test": "location"}
                        )
                        desc_el = card.find(
                            "div", attrs={"data-test": "job-description"}
                        )

                        if not title_el:
                            continue

                        title   = title_el.get_text().strip()
                        company = company_el.get_text().strip() \
                                  if company_el else "Startup"
                        loc     = loc_el.get_text().strip() \
                                  if loc_el else "Remote"
                        desc    = desc_el.get_text().strip() \
                                  if desc_el else ""
                        href    = title_el.get("href", "")
                        url_str = ("https://wellfound.com" + href
                                   if href.startswith("/") else href)

                    if not title or not is_relevant(title):
                        continue

                    full_desc = (
                        f"{title} position at {company}. "
                        f"Location: {loc}. "
                        f"{desc}"
                    ).strip()

                    jobs.append({
                        "job_id":          f"wellfound_{url_str[-30:].replace('/','_')}",
                        "job_title":       title,
                        "company":         company,
                        "location":        loc,
                        "job_url":         url_str,
                        "job_description": full_desc,
                        "platform":        "wellfound",
                        "status":          "scraped",
                        "salary":          "",
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

            if jobs:
                break

        print(f"{len(jobs)} relevant jobs")

    except Exception as e:
        print(f"Error: {e}")

    return jobs


def scrape_wellfound_jobs() -> list:
    driver   = get_driver()
    all_jobs = []
    seen_ids = set()

    try:
        if not login(driver):
            print("Wellfound login failed")
            return []

        print(f"\nSearching {len(SEARCH_ROLES)} roles...\n")

        for role in SEARCH_ROLES:
            if len(all_jobs) >= MAX_JOBS:
                break

            remaining = MAX_JOBS - len(all_jobs)
            target    = min(JOBS_PER_SEARCH, remaining)

            jobs = search_and_extract(driver, role, target)

            for job in jobs:
                if job["job_id"] not in seen_ids:
                    seen_ids.add(job["job_id"])
                    all_jobs.append(job)

            pause(1, 2)

        print(f"\nTotal jobs found: {len(all_jobs)}")

    except KeyboardInterrupt:
        print("\nStopped")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        driver.quit()

    return all_jobs


def save_jobs(jobs, filename="data/wellfound_jobs.json"):
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

    print(f"  {len(new_jobs)} new jobs saved")
    return new_jobs


if __name__ == "__main__":
    print("Wellfound Job Scraper")
    print("=" * 55)
    print(f"Roles: {', '.join(SEARCH_ROLES)}")
    print("=" * 55 + "\n")

    jobs = scrape_wellfound_jobs()

    if jobs:
        save_jobs(jobs)
        print(f"\n── Sample jobs ─────────────────────────────")
        for job in jobs[:5]:
            print(f"\n  {job['job_title']} at {job['company']}")
            print(f"  {job['location']}")
    else:
        print("No jobs scraped")