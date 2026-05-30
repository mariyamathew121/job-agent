# scraper/linkedin.py

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
    LINKEDIN_EMAIL, LINKEDIN_PASSWORD,
    SEARCH_ROLES, SEARCH_LOCATIONS,
    EXPERIENCE_LEVELS, JOBS_PER_SEARCH, MAX_JOBS,
    DAYS_POSTED
)

COOKIES_FILE = "data/linkedin_cookies.pkl"


# ── Helpers ────────────────────────────────────────────────────────────

def pause(min_sec=1.5, max_sec=3.5):
    time.sleep(random.uniform(min_sec, max_sec))

def type_slowly(element, text):
    for char in text:
        element.send_keys(char)
        time.sleep(random.uniform(0.05, 0.15))


# ── Driver ─────────────────────────────────────────────────────────────

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
    print("  Session saved — next run skips login automatically")


def load_cookies(driver):
    if not os.path.exists(COOKIES_FILE):
        print("  No saved session found")
        return False

    driver.get("https://www.linkedin.com")
    pause(2, 3)

    with open(COOKIES_FILE, "rb") as f:
        cookies = pickle.load(f)

    for cookie in cookies:
        try:
            driver.add_cookie(cookie)
        except Exception:
            pass

    driver.refresh()
    pause(3, 4)

    if "feed"      in driver.current_url or \
       "mynetwork" in driver.current_url:
        print("  Logged in via saved session")
        return True

    return False


# ── Login ──────────────────────────────────────────────────────────────

def login(driver) -> bool:
    """
    Fully automatic login.
    Tries cookies first, then credentials.
    Auto-detects when phone verification is complete —
    no need to press Enter.
    """
    print("  Checking saved session...")
    if load_cookies(driver):
        return True

    print("  Logging in with credentials...")
    driver.get("https://www.linkedin.com/login")
    pause(3, 5)

    try:
        email_field = WebDriverWait(driver, 40).until(
            EC.presence_of_element_located((By.ID, "username"))
        )
        email_field.clear()
        type_slowly(email_field, LINKEDIN_EMAIL)
        pause(1, 2)

        pwd = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "password"))
        )
        type_slowly(pwd, LINKEDIN_PASSWORD)
        pause(1, 2)
        pwd.submit()

    except TimeoutException:
        print("  Login form not loading")
        return False

    # Auto-wait up to 2 minutes for login to complete
    # Works for phone verification too — script detects
    # when LinkedIn redirects to feed automatically
    print("  Waiting for login...")
    print("  If phone verification appears — approve it on your phone")

    for i in range(120):
        time.sleep(1)
        current = driver.current_url

        if i % 10 == 0 and i > 0:
            print(f"  Still waiting... ({i}s)")

        if "feed"          in current or \
           "mynetwork"     in current or \
           "jobs"          in current or \
           "linkedin.com/in/" in current:
            print(f"  Logged in after {i}s")
            save_cookies(driver)
            return True

    print("  Timed out waiting for login")
    return False


# ── Build search URL ───────────────────────────────────────────────────

def build_search_url(role: str, location: str) -> str:
    """
    Builds LinkedIn job search URL with all filters:
    - Role and location
    - Experience level (Entry + Associate = 0-2 years)
    - Posted within last N days
    - Sorted by newest
    """
    exp_param    = ",".join(str(e) for e in EXPERIENCE_LEVELS)
    days_seconds = DAYS_POSTED * 86400

    url = (
        f"https://www.linkedin.com/jobs/search/"
        f"?keywords={role.replace(' ', '%20')}"
        f"&location={location.replace(' ', '%20')}"
        f"&f_E={exp_param}"
        f"&f_TPR=r{days_seconds}"
        f"&sortBy=DD"
    )
    return url


# ── Scroll to load cards ───────────────────────────────────────────────

def scroll_and_load(driver, target_count):
    last_count   = 0
    no_new_count = 0

    while no_new_count < 8:
        cards = driver.find_elements(
            By.CSS_SELECTOR,
            "li.jobs-search-results__list-item"
        )
        current = len(cards)

        if current >= target_count:
            break

        if current == last_count:
            no_new_count += 1
            try:
                btn = driver.find_element(By.XPATH,
                    "//button[contains(@aria-label,'Load more')]"
                    "|//button[contains(text(),'See more')]"
                )
                driver.execute_script("arguments[0].click();", btn)
                pause(2, 3)
            except NoSuchElementException:
                pass
        else:
            no_new_count = 0

        driver.execute_script("window.scrollBy(0, 700)")
        pause(1.5, 2.5)
        last_count = current

    return driver.find_elements(
        By.CSS_SELECTOR,
        "li.jobs-search-results__list-item"
    )


# ── Extract one job ────────────────────────────────────────────────────

def extract_job(driver, card, index, seen_ids: set) -> dict | None:
    try:
        driver.execute_script("arguments[0].click();", card)
        pause(2.5, 4)

        soup = BeautifulSoup(driver.page_source, "html.parser")

        # Title
        title = "Unknown"
        for cls in [
            "job-details-jobs-unified-top-card__job-title",
            "topcard__title",
            "jobs-unified-top-card__job-title",
        ]:
            el = soup.find(class_=lambda c: c and cls in c)
            if el:
                title = el.get_text().strip()
                break

        # Company
        company = "Unknown"
        for cls in [
            "job-details-jobs-unified-top-card__company-name",
            "topcard__org-name-link",
            "jobs-unified-top-card__company-name",
        ]:
            el = soup.find(class_=lambda c: c and cls in c)
            if el:
                company = el.get_text().strip()
                break

        # Location
        location = "Unknown"
        for cls in [
            "job-details-jobs-unified-top-card__bullet",
            "topcard__flavor--bullet",
            "jobs-unified-top-card__bullet",
        ]:
            el = soup.find(class_=lambda c: c and cls in c)
            if el:
                location = el.get_text().strip()
                break

        # Description
        desc = ""
        for cls in [
            "jobs-description-content__text",
            "jobs-description__content",
            "description__text",
            "jobs-box__html-content",
        ]:
            el = soup.find(class_=lambda c: c and cls in c)
            if el:
                desc = el.get_text(separator="\n").strip()
                break

        # Skip if no real description loaded
        if not desc or len(desc) < 100:
            return None

        # URL and ID
        try:
            link    = card.find_element(By.TAG_NAME, "a")
            job_url = link.get_attribute("href").split("?")[0]
        except Exception:
            job_url = driver.current_url

        job_id = f"linkedin_{job_url.split('/')[-1]}" \
                 if job_url else f"linkedin_{index}"

        # Skip duplicates across searches
        if job_id in seen_ids:
            return None
        seen_ids.add(job_id)

        return {
            "job_id":          job_id,
            "job_title":       title,
            "company":         company,
            "location":        location,
            "job_url":         job_url,
            "job_description": desc,
            "platform":        "linkedin",
            "status":          "scraped",
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

    except Exception as e:
        print(f"    Error: {e}")
        return None


# ── Save jobs ──────────────────────────────────────────────────────────

def save_jobs(jobs, filename="data/linkedin_jobs.json"):
    os.makedirs("data", exist_ok=True)

    # Load existing to avoid duplicates
    existing = []
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            existing = json.load(f)

    existing_ids = {j["job_id"] for j in existing}
    new_jobs     = [j for j in jobs if j["job_id"] not in existing_ids]
    all_jobs     = existing + new_jobs

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(all_jobs, f, indent=2, ensure_ascii=False)

    print(f"  {len(new_jobs)} new jobs added")
    print(f"  {len(all_jobs)} total in {filename}")


# ── Main ───────────────────────────────────────────────────────────────

def scrape_linkedin_jobs() -> list:
    """
    Scrapes jobs across all role + location combinations.
    One login, multiple searches, deduplicates results.
    """
    driver   = get_driver()
    all_jobs = []
    seen_ids = set()

    try:
        # Login once — reused for all searches
        if not login(driver):
            print("Login failed")
            return []

        total_searches = len(SEARCH_ROLES) * len(SEARCH_LOCATIONS)
        search_num     = 0

        for role in SEARCH_ROLES:
            for location in SEARCH_LOCATIONS:

                if len(all_jobs) >= MAX_JOBS:
                    print(f"\n  Reached max {MAX_JOBS} jobs — stopping")
                    break

                search_num += 1
                remaining  = MAX_JOBS - len(all_jobs)
                target     = min(JOBS_PER_SEARCH, remaining)

                print(f"\n[Search {search_num}/{total_searches}]")
                print(f"  Role:     {role}")
                print(f"  Location: {location}")
                print(f"  Target:   {target} jobs")

                url = build_search_url(role, location)
                driver.get(url)
                pause(4, 6)

                cards = scroll_and_load(driver, target)
                print(f"  Cards found: {len(cards)}")

                found = 0
                for i, card in enumerate(cards[:target]):
                    print(f"  [{i+1}/{min(len(cards), target)}] ",
                          end="", flush=True)

                    job = extract_job(driver, card, i, seen_ids)

                    if job:
                        all_jobs.append(job)
                        found += 1
                        print(f"✓ {job['job_title']} "
                              f"at {job['company']}")
                    else:
                        print("✗ skipped")

                    pause(1, 2)

                print(f"  Got {found} jobs from this search")

            if len(all_jobs) >= MAX_JOBS:
                break

    except KeyboardInterrupt:
        print("\nStopped by user")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        driver.quit()

    return all_jobs


# ── Run ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("LinkedIn Job Scraper")
    print("=" * 55)
    print(f"Roles:      {', '.join(SEARCH_ROLES)}")
    print(f"Locations:  {', '.join(SEARCH_LOCATIONS)}")
    print(f"Exp levels: {EXPERIENCE_LEVELS} (2=Entry, 3=Associate)")
    print(f"Max jobs:   {MAX_JOBS}")
    print("=" * 55 + "\n")

    jobs = scrape_linkedin_jobs()

    if jobs:
        save_jobs(jobs)
        print(f"\n── Preview (first 3) ─────────────────────────────")
        for job in jobs[:3]:
            print(f"\n  {job['job_title']} at {job['company']}")
            print(f"  Location: {job['location']}")
            print(f"  Desc: {job['job_description'][:120]}...")
    else:
        print("\nNo jobs scraped")