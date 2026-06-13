# submitter/indeed_apply.py
# Fills and submits Indeed job applications automatically.

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
    fill_textarea, upload_file, click_button,
    check_for_errors, log_submission, type_into
)
from rag.retriever import smart_answer

COOKIES_FILE = "data/indeed_cookies.pkl"


def get_driver():
    options = uc.ChromeOptions()
    options.add_argument("--window-size=1920,1080")
    driver = uc.Chrome(options=options, version_main=147)
    return driver


def load_indeed_session(driver) -> bool:
    if not os.path.exists(COOKIES_FILE):
        return False
    driver.get("https://in.indeed.com")
    pause(2, 3)
    with open(COOKIES_FILE, "rb") as f:
        for cookie in pickle.load(f):
            try:
                driver.add_cookie(cookie)
            except Exception:
                pass
    driver.refresh()
    pause(2, 3)
    page = driver.page_source.lower()
    return "sign out" in page or "my account" in page


def fill_indeed_form(driver, job: dict,
                     resume: dict, user_qa: dict,
                     pdf_path: str) -> bool:
    """Fill Indeed application form — multi-step."""
    p = resume["personal"]
    max_steps = 6

    for step in range(max_steps):
        pause(1.5, 2)
        print(f"    Step {step + 1}...")

        # Fill name
        fill_text_field(driver, [
            (By.CSS_SELECTOR, "input[name='applicant.name']"),
            (By.CSS_SELECTOR, "input[id*='name']"),
            (By.XPATH, "//label[contains(text(),'Name')]/following::input[1]"),
        ], p["name"])

        # Fill email
        fill_text_field(driver, [
            (By.CSS_SELECTOR, "input[name='applicant.email']"),
            (By.CSS_SELECTOR, "input[type='email']"),
        ], p["email"])

        # Fill phone
        fill_text_field(driver, [
            (By.CSS_SELECTOR, "input[name='applicant.phoneNumber']"),
            (By.CSS_SELECTOR, "input[type='tel']"),
            (By.XPATH, "//label[contains(text(),'Phone')]/following::input[1]"),
        ], p["phone"].replace("+91-", ""))

        # Upload resume
        file_inputs = driver.find_elements(
            By.CSS_SELECTOR, "input[type='file']"
        )
        if file_inputs and pdf_path:
            try:
                file_inputs[0].send_keys(os.path.abspath(pdf_path))
                pause(2, 3)
                print("    Resume uploaded")
            except Exception:
                pass

        # Answer text questions
        questions = driver.find_elements(
            By.CSS_SELECTOR,
            "label.ia-Questions-item--label, "
            ".ia-Questions-item label, "
            "[class*='question'] label"
        )

        for q_label in questions:
            q_text = q_label.text.strip()
            if not q_text:
                continue

            answer = smart_answer(
                q_text, job.get("job_title", ""),
                job.get("company", ""), user_qa
            )

            try:
                label_for = q_label.get_attribute("for")
                if label_for:
                    inp = driver.find_element(By.ID, label_for)
                    if inp.tag_name == "textarea":
                        inp.clear()
                        inp.send_keys(answer)
                    elif inp.get_attribute("type") in ["text", "number"]:
                        inp.clear()
                        if inp.get_attribute("type") == "number":
                            num = "".join(filter(str.isdigit, answer)) or "1"
                            inp.send_keys(num)
                        else:
                            inp.send_keys(answer)
            except Exception:
                continue

        # Check for submit
        submit = find_element_safe(driver, [
            (By.CSS_SELECTOR, "button[type='submit']"),
            (By.XPATH, "//button[contains(text(),'Submit')]"),
            (By.XPATH, "//button[contains(text(),'Apply')]"),
            (By.CSS_SELECTOR, ".ia-continueButton"),
        ], timeout=3)

        if submit:
            submit_text = submit.text.lower()
            if any(w in submit_text for w in ["submit", "apply", "send"]):
                driver.execute_script("arguments[0].click();", submit)
                pause(2, 3)
                page = driver.page_source.lower()
                if any(w in page for w in
                       ["applied", "success", "thank", "submitted"]):
                    print("    Applied successfully")
                    return True
                print("    Applied (no confirmation)")
                return True

        # Click continue/next
        next_btn = find_element_safe(driver, [
            (By.XPATH, "//button[contains(text(),'Continue')]"),
            (By.XPATH, "//button[contains(text(),'Next')]"),
            (By.CSS_SELECTOR, ".ia-continueButton"),
            (By.CSS_SELECTOR, "button[data-testid='continue-button']"),
        ], timeout=3)

        if next_btn:
            driver.execute_script("arguments[0].click();", next_btn)
            pause(1, 2)
        else:
            break

    return False


def apply_indeed(job: dict, resume: dict,
                 user_qa: dict, pdf_path: str,
                 driver=None) -> bool:
    """Apply to an Indeed job. Returns True if successful."""
    own_driver = driver is None
    if own_driver:
        driver = get_driver()
        if not load_indeed_session(driver):
            print("    Indeed session expired")
            driver.quit()
            return False

    try:
        print(f"  Opening: {job['job_url']}")
        driver.get(job["job_url"])
        pause(2, 3)

        # Click Apply button
        apply_btn = find_element_safe(driver, [
            (By.CSS_SELECTOR, "button.ia-IndeedApplyButton"),
            (By.XPATH, "//button[contains(text(),'Apply now')]"),
            (By.XPATH, "//a[contains(text(),'Apply now')]"),
            (By.CSS_SELECTOR, "[data-testid='applyButton']"),
            (By.CSS_SELECTOR, ".jobsearch-IndeedApplyButton-newDesign"),
        ], timeout=8)

        if not apply_btn:
            print("    No Apply button found")
            log_submission(job, "SKIPPED", "No Apply button")
            return False

        driver.execute_script("arguments[0].click();", apply_btn)
        pause(2, 3)

        # Handle popup/new window
        if len(driver.window_handles) > 1:
            driver.switch_to.window(driver.window_handles[-1])
            pause(1, 2)

        success = fill_indeed_form(
            driver, job, resume, user_qa, pdf_path
        )

        if success:
            log_submission(job, "SUBMITTED", "Indeed Apply")
        else:
            log_submission(job, "FAILED", "Form incomplete")

        return success

    except Exception as e:
        print(f"    Error: {e}")
        log_submission(job, "ERROR", str(e)[:100])
        return False
    finally:
        if own_driver:
            try:
                driver.quit()
            except Exception:
                pass