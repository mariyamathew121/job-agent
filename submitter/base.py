# submitter/base.py
# Shared form filling logic used by all platform submitters.
# Handles: typing, clicking, uploading, dropdowns, radio buttons.

import os
import sys
import time
import random
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException,
    ElementNotInteractableException
)


# ── Timing ─────────────────────────────────────────────────────────────

def pause(min_sec=0.5, max_sec=1.5):
    time.sleep(random.uniform(min_sec, max_sec))


def type_into(element, text: str):
    """Type text character by character — human-like."""
    element.clear()
    for char in str(text):
        element.send_keys(char)
        time.sleep(random.uniform(0.03, 0.08))


# ── Field finders ──────────────────────────────────────────────────────

def find_element_safe(driver, selectors: list, timeout: int = 5):
    """
    Try multiple selectors in order — returns first found element.
    Returns None if nothing found.
    """
    for by, value in selectors:
        try:
            el = WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((by, value))
            )
            return el
        except TimeoutException:
            continue
    return None


def find_elements_safe(driver, selectors: list) -> list:
    """Try multiple selectors, return all found elements."""
    for by, value in selectors:
        try:
            els = driver.find_elements(by, value)
            if els:
                return els
        except Exception:
            continue
    return []


# ── Field fillers ──────────────────────────────────────────────────────

def fill_text_field(driver, selectors: list, value: str) -> bool:
    """Find a text input and fill it. Returns True if successful."""
    el = find_element_safe(driver, selectors)
    if not el:
        return False
    try:
        el.click()
        pause(0.3, 0.6)
        type_into(el, value)
        return True
    except Exception:
        return False


def fill_textarea(driver, selectors: list, value: str) -> bool:
    """Fill a textarea field."""
    el = find_element_safe(driver, selectors)
    if not el:
        return False
    try:
        el.click()
        pause(0.3, 0.6)
        el.clear()
        el.send_keys(value)
        return True
    except Exception:
        return False


def select_dropdown(driver, selectors: list, value: str) -> bool:
    """Select option from a dropdown by visible text or value."""
    el = find_element_safe(driver, selectors)
    if not el:
        return False
    try:
        select = Select(el)
        # Try exact match first
        try:
            select.select_by_visible_text(value)
            return True
        except Exception:
            pass
        # Try partial match
        for option in select.options:
            if value.lower() in option.text.lower():
                option.click()
                return True
        # Try first non-empty option as fallback
        for option in select.options:
            if option.text.strip() and option.text != "Select":
                option.click()
                return True
        return False
    except Exception:
        return False


def click_radio(driver, label_text: str) -> bool:
    """Click a radio button by its label text."""
    try:
        # Try finding label containing the text
        labels = driver.find_elements(By.TAG_NAME, "label")
        for label in labels:
            if label_text.lower() in label.text.lower():
                label.click()
                pause(0.3, 0.6)
                return True

        # Try by xpath
        el = driver.find_element(
            By.XPATH,
            f"//label[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ',"
            f"'abcdefghijklmnopqrstuvwxyz'),'{label_text.lower()}')]"
        )
        el.click()
        return True
    except Exception:
        return False


def click_yes_radio(driver) -> bool:
    """Click Yes on any yes/no radio button."""
    for text in ["Yes", "yes", "YES"]:
        if click_radio(driver, text):
            return True
    return False


def upload_file(driver, selectors: list, file_path: str) -> bool:
    """Upload a file to a file input field."""
    if not os.path.exists(file_path):
        print(f"    File not found: {file_path}")
        return False

    abs_path = os.path.abspath(file_path)
    el = find_element_safe(driver, selectors)
    if not el:
        # Try finding any file input
        inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
        if inputs:
            el = inputs[0]

    if not el:
        return False

    try:
        el.send_keys(abs_path)
        pause(1, 2)  # wait for upload
        return True
    except Exception:
        return False


def click_button(driver, selectors: list) -> bool:
    """Click a button."""
    el = find_element_safe(driver, selectors)
    if not el:
        return False
    try:
        driver.execute_script("arguments[0].click();", el)
        pause(0.5, 1)
        return True
    except Exception:
        return False


# ── Form validation ────────────────────────────────────────────────────

def check_for_errors(driver) -> list:
    """
    Check if the form has any error messages.
    Returns list of error texts found.
    """
    error_selectors = [
        ".error", ".form-error", ".field-error",
        "[class*='error']", "[class*='invalid']",
        ".alert-danger", ".validation-error"
    ]

    errors = []
    for selector in error_selectors:
        els = driver.find_elements(By.CSS_SELECTOR, selector)
        for el in els:
            text = el.text.strip()
            if text and len(text) < 200:
                errors.append(text)

    return list(set(errors))  # deduplicate


def is_form_complete(driver) -> bool:
    """
    Check if all required fields appear filled.
    Returns True if safe to submit.
    """
    errors = check_for_errors(driver)
    if errors:
        print(f"    Form errors found: {errors}")
        return False
    return True


# ── Answer custom questions ────────────────────────────────────────────

def answer_custom_question(driver, question_el,
                           answer_text: str) -> bool:
    """
    Given a question element on a form, find its input
    and fill it with the answer.
    """
    try:
        # Look for input/textarea near the question
        parent = question_el.find_element(By.XPATH, "./..")

        # Try textarea
        textarea = None
        try:
            textarea = parent.find_element(By.TAG_NAME, "textarea")
        except Exception:
            pass

        if textarea:
            textarea.clear()
            textarea.send_keys(answer_text)
            return True

        # Try text input
        text_input = None
        try:
            text_input = parent.find_element(
                By.CSS_SELECTOR, "input[type='text']"
            )
        except Exception:
            pass

        if text_input:
            type_into(text_input, answer_text)
            return True

        return False

    except Exception:
        return False


# ── Application log ────────────────────────────────────────────────────

def log_submission(job: dict, status: str,
                   details: str = "", log_file: str = "data/submissions.log"):
    """Log every submission attempt with timestamp."""
    os.makedirs("data", exist_ok=True)
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = (
        f"{timestamp} | {status} | "
        f"{job.get('job_title')} at {job.get('company')} | "
        f"{job.get('platform')} | {details}\n"
    )
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(line)