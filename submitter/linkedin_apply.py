# submitter/linkedin_apply.py
# Fills and submits LinkedIn Easy Apply forms automatically.
# Handles multi-step forms, custom questions, file upload.

import os
import sys
import time
import pickle
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from submitter.base import (
    pause, type_into, find_element_safe, find_elements_safe,
    fill_text_field, fill_textarea, select_dropdown,
    upload_file, click_button, check_for_errors,
    click_yes_radio, log_submission
)
from rag.retriever import smart_answer
import json


COOKIES_FILE = "data/linkedin_cookies.pkl"


def get_driver():
    options = uc.ChromeOptions()
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    driver = uc.Chrome(options=options, version_main=147)
    return driver


def load_linkedin_session(driver) -> bool:
    """Load saved LinkedIn cookies."""
    if not os.path.exists(COOKIES_FILE):
        return False

    driver.get("https://www.linkedin.com")
    pause(2, 3)

    with open(COOKIES_FILE, "rb") as f:
        for cookie in pickle.load(f):
            try:
                driver.add_cookie(cookie)
            except Exception:
                pass

    driver.refresh()
    pause(2, 3)
    return "feed" in driver.current_url or \
           "mynetwork" in driver.current_url


def fill_contact_info(driver, resume: dict) -> dict:
    """Fill basic contact info fields."""
    filled = {}
    p = resume["personal"]

    # First name
    if fill_text_field(driver, [
        (By.CSS_SELECTOR, "input[id*='firstName']"),
        (By.CSS_SELECTOR, "input[name*='firstName']"),
        (By.XPATH, "//label[contains(text(),'First')]/following::input[1]"),
    ], p["name"].split()[0]):
        filled["first_name"] = p["name"].split()[0]

    # Last name
    last_name = " ".join(p["name"].split()[1:]) if len(p["name"].split()) > 1 else ""
    if fill_text_field(driver, [
        (By.CSS_SELECTOR, "input[id*='lastName']"),
        (By.CSS_SELECTOR, "input[name*='lastName']"),
        (By.XPATH, "//label[contains(text(),'Last')]/following::input[1]"),
    ], last_name):
        filled["last_name"] = last_name

    # Phone
    if fill_text_field(driver, [
        (By.CSS_SELECTOR, "input[id*='phoneNumber']"),
        (By.CSS_SELECTOR, "input[name*='phone']"),
        (By.XPATH, "//label[contains(text(),'Phone')]/following::input[1]"),
        (By.XPATH, "//label[contains(text(),'Mobile')]/following::input[1]"),
    ], p["phone"].replace("+91-", "").replace("+91", "")):
        filled["phone"] = p["phone"]

    return filled


def upload_resume(driver, pdf_path: str) -> bool:
    """Upload the tailored resume PDF."""
    result = upload_file(driver, [
        (By.CSS_SELECTOR, "input[type='file']"),
        (By.CSS_SELECTOR, "input[name*='resume']"),
        (By.CSS_SELECTOR, "input[accept*='pdf']"),
    ], pdf_path)

    if result:
        pause(2, 3)  # wait for upload to process
        print(f"    Resume uploaded: {os.path.basename(pdf_path)}")
    return result


def handle_custom_questions(driver, job: dict,
                            resume: dict, user_qa: dict) -> dict:
    """
    Find and answer all custom questions on the form.
    Uses pre-written answers first, RAG for anything custom.
    """
    answers_given = {}

    # Find all question labels
    question_labels = driver.find_elements(
        By.CSS_SELECTOR, "label.artdeco-text-input--label, "
        "span.fb-form-element__label, "
        "legend.fb-form-element__label"
    )

    for label in question_labels:
        question_text = label.text.strip()
        if not question_text or len(question_text) < 3:
            continue

        question_lower = question_text.lower()

        # Standard answers — no LLM needed
        answer = None

        if any(w in question_lower for w in ["year", "experience"]):
            answer = user_qa.get("years_of_experience", "1")
        elif any(w in question_lower for w in ["notice", "join", "available"]):
            answer = user_qa.get("notice_period", "2 weeks")
        elif any(w in question_lower for w in ["salary", "ctc", "compensation"]):
            answer = user_qa.get("salary_expectation", "Open to discussion")
        elif any(w in question_lower for w in ["relocat"]):
            answer = user_qa.get("willing_to_relocate", "Open to Bangalore and Kochi")
        elif any(w in question_lower for w in ["authoriz", "authoris", "eligible", "permit"]):
            answer = "Yes"
        elif any(w in question_lower for w in ["remote", "work from home", "wfh"]):
            answer = "Yes"
        elif any(w in question_lower for w in ["currently employed", "working"]):
            answer = "Yes"
        else:
            # Use RAG for custom questions
            try:
                answer = smart_answer(
                    question_text,
                    job.get("job_title", ""),
                    job.get("company", ""),
                    user_qa
                )
            except Exception:
                answer = user_qa.get("describe_yourself", "")

        if answer:
            # Try to find associated input and fill it
            try:
                # Look for input near this label
                label_for = label.get_attribute("for")
                if label_for:
                    input_el = driver.find_element(By.ID, label_for)
                    tag = input_el.tag_name.lower()
                    input_type = input_el.get_attribute("type", "").lower()

                    if tag == "textarea" or input_type == "text":
                        input_el.clear()
                        input_el.send_keys(str(answer))
                        answers_given[question_text] = answer
                    elif input_type == "number":
                        # Extract just the number
                        num = "".join(filter(str.isdigit, str(answer))) or "1"
                        input_el.clear()
                        input_el.send_keys(num)
                        answers_given[question_text] = num
            except Exception:
                pass

    # Handle radio buttons for yes/no questions
    yes_no_questions = driver.find_elements(
        By.CSS_SELECTOR, "fieldset.fb-form-element"
    )
    for fieldset in yes_no_questions:
        try:
            legend = fieldset.find_element(By.TAG_NAME, "legend")
            q_text = legend.text.strip().lower()

            if any(w in q_text for w in [
                "authoriz", "authoris", "eligible", "citizen",
                "legally", "remote", "comfortable", "willing"
            ]):
                # Click Yes
                yes_options = fieldset.find_elements(
                    By.CSS_SELECTOR, "input[type='radio']"
                )
                for radio in yes_options:
                    label_id = radio.get_attribute("id")
                    try:
                        lbl = fieldset.find_element(
                            By.CSS_SELECTOR, f"label[for='{label_id}']"
                        )
                        if "yes" in lbl.text.lower():
                            driver.execute_script(
                                "arguments[0].click();", radio
                            )
                            answers_given[legend.text] = "Yes"
                            break
                    except Exception:
                        continue
        except Exception:
            continue

    return answers_given


def handle_multi_step(driver, job: dict, resume: dict,
                      user_qa: dict, pdf_path: str) -> bool:
    """
    Navigate through multi-step Easy Apply forms.
    Fills each page and clicks Next until Submit appears.
    Returns True if submitted successfully.
    """
    max_steps = 8  # LinkedIn rarely has more than 8 steps

    for step in range(max_steps):
        pause(1.5, 2.5)
        print(f"    Step {step + 1}...")

        # Fill contact info on first step
        if step == 0:
            fill_contact_info(driver, resume)
            pause(0.5, 1)

        # Try to upload resume on any step
        file_inputs = driver.find_elements(
            By.CSS_SELECTOR, "input[type='file']"
        )
        if file_inputs and pdf_path:
            try:
                file_inputs[0].send_keys(os.path.abspath(pdf_path))
                pause(2, 3)
                print(f"    Uploaded resume")
            except Exception:
                pass

        # Answer questions on this step
        handle_custom_questions(driver, job, resume, user_qa)
        pause(0.5, 1)

        # Check for errors before proceeding
        errors = check_for_errors(driver)
        if errors:
            print(f"    Errors on step {step + 1}: {errors[:2]}")

        # Look for Submit button first
        submit_btn = find_element_safe(driver, [
            (By.CSS_SELECTOR, "button[aria-label*='Submit']"),
            (By.XPATH, "//button[contains(text(),'Submit application')]"),
            (By.XPATH, "//button[contains(text(),'Submit')]"),
            (By.CSS_SELECTOR, "button.artdeco-button--primary[type='submit']"),
        ], timeout=3)

        if submit_btn:
            print(f"    Submitting application...")
            driver.execute_script("arguments[0].click();", submit_btn)
            pause(2, 3)

            # Check for success
            success_indicators = [
                "application was sent",
                "applied",
                "your application",
                "successfully"
            ]
            page_text = driver.page_source.lower()
            if any(ind in page_text for ind in success_indicators):
                print(f"    Submitted successfully")
                return True
            else:
                print(f"    Submitted (no confirmation detected)")
                return True

        # Look for Next button
        next_btn = find_element_safe(driver, [
            (By.CSS_SELECTOR, "button[aria-label='Continue to next step']"),
            (By.CSS_SELECTOR, "button[aria-label*='next']"),
            (By.XPATH, "//button[contains(text(),'Next')]"),
            (By.XPATH, "//button[contains(text(),'Continue')]"),
            (By.XPATH, "//button[contains(text(),'Review')]"),
        ], timeout=3)

        if next_btn:
            driver.execute_script("arguments[0].click();", next_btn)
            pause(1, 2)
            continue

        # No next or submit found — form might be done
        print(f"    No next/submit button found on step {step + 1}")
        break

    return False


def apply_linkedin(job: dict, resume: dict,
                   user_qa: dict, pdf_path: str,
                   driver=None) -> bool:
    """
    Main function — applies to one LinkedIn job via Easy Apply.
    Returns True if application submitted successfully.
    """
    own_driver = driver is None
    if own_driver:
        driver = get_driver()
        if not load_linkedin_session(driver):
            print("    LinkedIn session expired — need to re-login")
            driver.quit()
            return False

    try:
        print(f"  Opening: {job['job_url']}")
        driver.get(job["job_url"])
        pause(2, 3)

        # Find and click Easy Apply button
        easy_apply_btn = find_element_safe(driver, [
            (By.CSS_SELECTOR, "button.jobs-apply-button"),
            (By.CSS_SELECTOR, "button[aria-label*='Easy Apply']"),
            (By.XPATH, "//button[contains(text(),'Easy Apply')]"),
            (By.CSS_SELECTOR, ".jobs-apply-button--top-card"),
        ], timeout=8)

        if not easy_apply_btn:
            print(f"    No Easy Apply button — skipping")
            log_submission(job, "SKIPPED", "No Easy Apply button")
            return False

        driver.execute_script("arguments[0].click();", easy_apply_btn)
        pause(1.5, 2.5)
        print(f"    Easy Apply form opened")

        # Handle the multi-step form
        success = handle_multi_step(
            driver, job, resume, user_qa, pdf_path
        )

        if success:
            log_submission(job, "SUBMITTED", "LinkedIn Easy Apply")
        else:
            log_submission(job, "FAILED", "Form submission unsuccessful")

        return success

    except Exception as e:
        print(f"    Error: {e}")
        log_submission(job, "ERROR", str(e)[:100])
        return False

    finally:
        if own_driver:
            driver.quit()