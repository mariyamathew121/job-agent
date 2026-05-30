# test_platforms.py
import httpx
import feedparser

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

# Test 1 - Indeed RSS
print("Testing Indeed RSS...")
try:
    feed = feedparser.parse(
        "https://in.indeed.com/rss?q=Python+Developer&l=Bangalore&fromage=7"
    )
    print(f"  Entries: {len(feed.entries)}")
    if feed.entries:
        print(f"  First job: {feed.entries[0].title}")
    else:
        print("  No entries returned")
except Exception as e:
    print(f"  Error: {e}")

# Test 2 - Naukri API
print("\nTesting Naukri...")
try:
    r = httpx.get(
        "https://www.naukri.com/jobapi/v3/search",
        params={
            "noOfResults": 5,
            "keyword":     "Python Developer",
            "location":    "Bangalore",
            "experience":  0,
            "experienceDD":2,
        },
        headers={
            **HEADERS,
            "appid":    "109",
            "systemid": "109",
            "Referer":  "https://www.naukri.com/",
        },
        timeout=15,
        follow_redirects=True
    )
    print(f"  Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        jobs = data.get("jobDetails", [])
        print(f"  Jobs found: {len(jobs)}")
        if jobs:
            print(f"  First: {jobs[0].get('title')} at {jobs[0].get('companyName')}")
    else:
        print(f"  Response: {r.text[:200]}")
except Exception as e:
    print(f"  Error: {e}")

# Test 3 - Naukri HTML
print("\nTesting Naukri HTML page...")
try:
    r = httpx.get(
        "https://www.naukri.com/python-developer-jobs-in-bangalore",
        headers=HEADERS,
        timeout=15,
        follow_redirects=True
    )
    print(f"  Status: {r.status_code}")
    print(f"  Page size: {len(r.text)} chars")
    if "jobTuple" in r.text or "srp-jobtuple" in r.text or "job-title" in r.text:
        print("  Job cards found in HTML")
    else:
        print("  No job cards detected in HTML")
        print(f"  Page preview: {r.text[:300]}")
except Exception as e:
    print(f"  Error: {e}")

# Test 4 - Remotive
print("\nTesting Remotive...")
try:
    r = httpx.get(
        "https://remotive.com/api/remote-jobs",
        params={"search": "Python Developer", "limit": 5, "category": "software-dev"},
        timeout=10
    )
    print(f"  Status: {r.status_code}")
    if r.status_code == 200:
        jobs = r.json().get("jobs", [])
        print(f"  Jobs found: {len(jobs)}")
        for j in jobs:
            print(f"    - {j['title']} at {j['company_name']}")
except Exception as e:
    print(f"  Error: {e}")

# Test 5 - Wellfound
print("\nTesting Wellfound...")
try:
    r = httpx.get(
        "https://wellfound.com/role/l/python-developer",
        headers=HEADERS,
        timeout=12,
        follow_redirects=True
    )
    print(f"  Status: {r.status_code}")
    print(f"  Page size: {len(r.text)} chars")
    if "job" in r.text.lower():
        print("  Job content detected")
    else:
        print("  No job content found")
except Exception as e:
    print(f"  Error: {e}")

print("\nDone.")