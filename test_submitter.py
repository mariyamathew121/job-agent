# test_submitter.py
import json
import os
from submitter.engine import submit_application

# Load jobs
with open("data/naukri_jobs.json") as f:
    jobs = json.load(f)

# Find a job that already has a PDF generated
found = False
for job in jobs[:10]:
    company_clean = job["company"].lower().replace(" ", "_")
    title_clean   = job["job_title"].lower().replace(" ", "_")
    pdf = f"data/resumes/resume_{company_clean}_{title_clean}.pdf"

    if os.path.exists(pdf):
        job["pdf_path"] = pdf
        print(f"Testing with: {job['job_title']} at {job['company']}")
        print(f"Platform: {job['platform']}")
        print(f"PDF: {pdf}")
        print(f"URL: {job['job_url']}")
        print()

        result = submit_application(job)
        print(f"\nResult: {result['status']}")
        if result.get("error"):
            print(f"Error: {result['error']}")
        found = True
        break

if not found:
    print("No jobs with PDFs found.")
    print("Run this first to generate PDFs:")
    print("  python main.py --mode pipeline-only --max-jobs 5")

    # Show what PDFs exist
    if os.path.exists("data/resumes"):
        pdfs = os.listdir("data/resumes")
        print(f"\nExisting PDFs ({len(pdfs)}):")
        for p in pdfs[:5]:
            print(f"  {p}")