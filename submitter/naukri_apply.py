# submitter/naukri_apply.py
# Fills and submits Naukri job applications automatically.

import os
import sys
import time
import pickle
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from submitter.base import (
    pause, find_element_safe, fill_text_field,
    upload_file, click_button, check_for_errors,
    log_submission
)
from rag.retriever import smart_answer
import json

COOKIES_FILE = "data/naukri_cookies.pkl"


def get_driver():
    options = uc.ChromeOptions()
    options.add_argument("--window-size=1920,1080")
    driver = uc.Chrome(options=options, version_main=147)
    return driver


def load_naukri_session(driver) -> bool:
    if not os.path.exists(COOKIES_FILE):
        return False
    driver.get("https://www.naukri.com")
    pause(1, 2)
    with open(COOKIES_FILE, "rb") as f:
        for cookie in pickle.load(f):
            try:
                driver.add_cookie(cookie)
            except Exception:
                pass
    driver.refresh()
    pause(1, 2)
    page = driver.page_source.lower()
    return "logout" in page or "my profile" in page


def handle_naukri_questions(driver, job: dict,
                             user_qa: dict) -> dict:
    """Answer custom questions on Naukri application form."""
    answers = {}

    # Find all question containers
    question_containers = driver.find_elements(
        By.CSS_SELECTOR,
        ".chatbot_InputContainer, .bot-message, "
        ".naukri-chatbot-question, [class*='question']"
    )

    for container in question_containers:
        try:
            q_text = container.text.strip().lower()
            if not q_text:
                continue

            answer = None
            if any(w in q_text for w in ["experience", "year"]):
                answer = "1"
            elif any(w in q_text for w in ["notice", "join"]):
                answer = "2 weeks"
            elif any(w in q_text for w in ["salary", "ctc"]):
                answer = user_qa.get("salary_expectation", "Open to discussion")
            elif any(w in q_text for w in ["relocat"]):
                answer = "Yes"
            elif any(w in q_text for w in ["current location", "location"]):
                answer = "Kottayam, Kerala"
            else:
                answer = smart_answer(
                    q_text, job.get("job_title", ""),
                    job.get("company", ""), user_qa
                )

            if answer:
                # Find input near this container
                inputs = container.find_elements(
                    By.CSS_SELECTOR, "input, textarea"
                )
                for inp in inputs:
                    inp_type = inp.get_attribute("type", "").lower()
                    if inp_type not in ["hidden", "submit", "button"]:
                        inp.clear()
                        inp.send_keys(str(answer))
                        answers[q_text[:50]] = answer
                        break

        except Exception:
            continue

    return answers


def apply_naukri(job: dict, resume: dict,
                 user_qa: dict, pdf_path: str,
                 driver=None) -> bool:
    """Apply to a Naukri job. Handles both native and external apply."""
    own_driver = driver is None
    if own_driver:
        driver = get_driver()
        if not load_naukri_session(driver):
            print("    Naukri session expired")
            driver.quit()
            return False

    try:
        print(f"  Opening: {job['job_url']}")
        driver.get(job["job_url"])
        pause(2, 3)

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(driver.page_source, "html.parser")

        # ── Detect apply type ──────────────────────────────────────────

        # Check for "Apply on company site" button
        company_site_btn = (
            soup.find("button", class_=lambda c: c and
                      "company-site-button" in str(c)) or
            soup.find("button", string=lambda t: t and
                      "company site" in t.lower()) or
            soup.find("a", string=lambda t: t and
                      "company site" in t.lower())
        )

        if company_site_btn:
            print("    External apply (company site) — logging for manual follow-up")
            log_submission(job, "EXTERNAL",
                           "Redirects to company site — manual apply needed")
            # Save the job URL for manual review
            _save_external_job(job)
            return False

        # ── Native Naukri apply ────────────────────────────────────────

        apply_btn = find_element_safe(driver, [
            (By.CSS_SELECTOR, "button#apply-button"),
            (By.CSS_SELECTOR, "button.apply-button"),
            (By.CSS_SELECTOR, "button[class*='apply-button']"),
            (By.CSS_SELECTOR, "a.apply-button"),
            (By.XPATH, "//button[contains(text(),'Apply')]"),
            (By.XPATH, "//a[contains(text(),'Apply')]"),
            (By.CSS_SELECTOR, "[class*='apply-btn']"),
            (By.CSS_SELECTOR, "[class*='applyBtn']"),
        ], timeout=6)

        if not apply_btn:
            print("    No native Apply button found")
            log_submission(job, "SKIPPED", "No Apply button")
            return False

        driver.execute_script("arguments[0].click();", apply_btn)
        pause(2, 3)
        print("    Apply form opened")

        # Answer questions
        handle_naukri_questions(driver, job, user_qa)
        pause(1, 2)

        # Upload resume
        upload_file(driver, [
            (By.CSS_SELECTOR, "input[type='file']"),
            (By.CSS_SELECTOR, "input[accept*='pdf']"),
        ], pdf_path)
        pause(1, 2)

        # Submit
        submit_btn = find_element_safe(driver, [
            (By.XPATH, "//button[contains(text(),'Submit')]"),
            (By.XPATH, "//button[contains(text(),'Apply')]"),
            (By.CSS_SELECTOR, "button[type='submit']"),
            (By.CSS_SELECTOR, ".submit-btn"),
            (By.CSS_SELECTOR, "button.waves-effect"),
            (By.XPATH, "//button[contains(@class,'apply')]"),
        ], timeout=5)

        if submit_btn:
            driver.execute_script("arguments[0].click();", submit_btn)
            pause(2, 3)
            page = driver.page_source.lower()
            if any(w in page for w in
                   ["applied", "success", "thank you", "submitted"]):
                print("    Applied successfully")
                log_submission(job, "SUBMITTED", "Naukri Native Apply")
                return True
            else:
                print("    Applied (no confirmation detected)")
                log_submission(job, "SUBMITTED", "Naukri Native Apply")
                return True
        else:
            print("    No submit button found")
            log_submission(job, "FAILED", "No submit button")
            return False

    except Exception as e:
        print(f"    Error: {e}")
        log_submission(job, "ERROR", str(e)[:100])
        return False
    finally:
        if own_driver:
            driver.quit()


def _save_external_job(job: dict):
    """Save external apply jobs to a separate file for manual review."""
    import json
    import os

    filepath = "data/external_apply_jobs.json"
    existing = []
    if os.path.exists(filepath):
        with open(filepath) as f:
            existing = json.load(f)

    existing_ids = {j["job_id"] for j in existing}
    if job["job_id"] not in existing_ids:
        existing.append({
            "job_id":    job["job_id"],
            "job_title": job["job_title"],
            "company":   job["company"],
            "job_url":   job["job_url"],
            "platform":  job["platform"],
        })
        with open(filepath, "w") as f:
            json.dump(existing, f, indent=2)