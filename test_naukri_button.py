# test_naukri_button.py
# Checks what buttons exist on a Naukri job page

import pickle
import time
from bs4 import BeautifulSoup
import undetected_chromedriver as uc

driver = uc.Chrome(version_main=147)

# Load Naukri session
driver.get("https://www.naukri.com")
with open("data/naukri_cookies.pkl", "rb") as f:
    for cookie in pickle.load(f):
        try:
            driver.add_cookie(cookie)
        except Exception:
            pass
driver.refresh()
time.sleep(3)

# Test on a failed job
url = "https://www.naukri.com/job-listings-ai-engineer-agentic-ai-leokraft-technologies-remote-2-to-5-years-220426501848"
print(f"Opening: {url}")
driver.get(url)
time.sleep(4)

soup = BeautifulSoup(driver.page_source, "html.parser")

# Find ALL buttons on the page
print("\nAll buttons found:")
for btn in soup.find_all("button"):
    text    = btn.get_text().strip()
    classes = " ".join(btn.get("class", []))
    if text:
        print(f"  Text: '{text}' | Class: '{classes[:60]}'")

# Find all links that look like apply
print("\nAll apply-related links:")
for a in soup.find_all("a"):
    text = a.get_text().strip()
    href = a.get("href", "")
    if any(w in text.lower() for w in ["apply", "submit"]):
        print(f"  Text: '{text}' | href: '{href[:60]}'")

# Find elements with apply in class/id
print("\nElements with 'apply' in class or id:")
for el in soup.find_all(class_=lambda c: c and "apply" in str(c).lower()):
    print(f"  Tag: {el.name} | Text: '{el.get_text().strip()[:40]}' | Class: '{str(el.get('class',''))[:60]}'")

driver.quit()
print("\nDone")