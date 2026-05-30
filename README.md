# AI Job Application Agent

An end-to-end agentic AI system that automates the entire job application pipeline — from scraping real job listings across multiple platforms, to analysing unstructured job descriptions using NLP and LLMs, to tailoring resumes and generating cover letters per role, scoring ATS compatibility, and tracking all outcomes in a structured database.

**Status:** Live, actively developing

---

## What it does

```
Scrape jobs from 5 platforms simultaneously
        ↓
Analyse each job description with LLMs
Extract: required skills · seniority · ATS keywords · company tone
        ↓
Score candidate-job match (0-1)
Skip low matches automatically
        ↓
5-layer resume tailoring per job
Summary rewrite · skills reorder · bullet reframe · project selection · ATS injection
        ↓
ATS score gate — only submit if score ≥ 70/100
        ↓
Generate tailored PDF resume + cover letter
        ↓
Answer custom application questions using RAG
        ↓
Submit application (Selenium form filler)
        ↓
Track everything in SQLite database
```

---

## Architecture

```
job-agent/
├── config/
│   ├── settings.py          # job preferences, thresholds, credentials
│   ├── llm.py               # OpenRouter LLM connection (single source)
│   ├── resume.json          # structured resume data
│   ├── resume.txt           # plain text resume for RAG indexing
│   └── user_qa.json         # pre-written answers to common questions
│
├── scraper/
│   ├── multi_scraper.py     # LinkedIn + Remotive (parallel HTTP)
│   ├── naukri.py            # Naukri (Selenium + Google login)
│   ├── indeed.py            # Indeed (Selenium + Google login)
│   └── wellfound.py         # Wellfound (Selenium + email login)
│
├── rag/
│   ├── indexer.py           # resume → chunks → embeddings → ChromaDB
│   ├── retriever.py         # question → vector search → LLM answer
│   └── analyser.py          # JD → structured JSON + match score + company intel
│
├── tailoring/
│   ├── tailor.py            # 5-layer resume tailoring engine
│   ├── ats_scorer.py        # ATS compatibility scoring (0-100)
│   ├── cover_letter.py      # per-job cover letter generation
│   └── resume_pdf.py        # professional PDF generation (ReportLab)
│
├── agent/
│   ├── state.py             # TypedDict state object
│   ├── nodes.py             # one function per pipeline step
│   └── graph.py             # LangGraph orchestrator
│
├── tracker/
│   ├── models.py            # SQLAlchemy database models
│   └── database.py          # save, query, analytics, skill gap report
│
├── submitter/               # Selenium form filler (in progress)
│
├── data/                    # scraped jobs, PDFs, database (gitignored)
│
└── main.py                  # entry point — one command runs everything
```

---

## Innovative features

### 1. Multi-platform parallel scraping
Scrapes LinkedIn, Naukri, Indeed, Wellfound, and Remotive simultaneously using threads. All 5 platforms in under 30 seconds. Deduplicates across platforms — same job appearing on multiple sites counted once.

### 2. LLM-powered JD analysis
Extracts structured information from any unstructured job description text:
- Required skills and nice-to-have skills
- Seniority level and years of experience
- ATS keywords for resume optimisation
- Company tone (startup / corporate / agency)
- Remote-friendliness signal

### 3. Company intelligence layer
Before applying, infers company size, growth signals, red flags, and culture keywords purely from the job description text. No existing auto-apply tool does pre-application company research.

### 4. RAG pipeline over candidate resume
Converts resume into searchable vector embeddings in ChromaDB. Given any job application question, retrieves the most semantically relevant resume chunks and generates grounded, accurate answers — no hallucination.

### 5. 5-layer resume tailoring
Every job gets a uniquely tailored resume:
- **Layer 1** — Summary rewrite matching JD tone and keywords
- **Layer 2** — Skills reordered with required skills first (ATS weighted)
- **Layer 3** — Experience bullets reworded in JD language
- **Layer 4** — Most relevant projects selected and rewritten
- **Layer 5** — Missing ATS keywords injected as safety net

### 6. ATS score gate
Scores the tailored resume against the JD (0-100) before submitting. If score < 70, the application is held back. No existing auto-apply tool gates on ATS score — competitors submit everything regardless of quality.

### 7. Skill gap report
After processing hundreds of jobs, analyses all low-scoring applications and surfaces the top skills causing failed matches — tells you exactly what to learn to unlock more opportunities.

---

## Tech stack

| Layer | Technology |
|---|---|
| Orchestration | LangGraph + LangChain |
| LLM | OpenRouter API (Llama 3.1, configurable) |
| Embeddings | OpenAI text-embedding-3-small via OpenRouter |
| Vector store | ChromaDB (persistent) |
| Scraping | Selenium + undetected-chromedriver + httpx + feedparser |
| PDF generation | ReportLab |
| Database | SQLite + SQLAlchemy |
| Parallelism | ThreadPoolExecutor |
| Language | Python 3.10+ |

---

## Setup

### 1. Clone and create virtual environment

```bash
git clone https://github.com/mariyamathew121/job-agent.git
cd job-agent
python -m venv venv

# Windows
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install langchain langchain-openai langchain-chroma langchain-text-splitters
pip install langgraph chromadb openai
pip install selenium undetected-chromedriver beautifulsoup4 httpx feedparser
pip install reportlab sqlalchemy python-dotenv
```

### 3. Configure credentials

Create a `.env` file in the project root:

```
OPENROUTER_API_KEY=your-openrouter-api-key
LINKEDIN_EMAIL=your@email.com
LINKEDIN_PASSWORD=yourpassword
NAUKRI_EMAIL=your@email.com
WELLFOUND_EMAIL=your@email.com
WELLFOUND_PASSWORD=yourpassword
INDEED_EMAIL=your@email.com
```

Get a free OpenRouter API key at [openrouter.ai](https://openrouter.ai)

### 4. Fill in your resume

Edit `config/resume.json` with your real details — name, experience, skills, projects, education.

Edit `config/resume.txt` with your full resume as plain text — this is what the RAG agent reads.

Edit `config/user_qa.json` with your answers to common job application questions.

### 5. Build the RAG index

```bash
python rag/indexer.py
```

---

## Usage

### Scrape fresh jobs only

```bash
python main.py --mode scrape-only
```

### Run pipeline on saved jobs (no new scraping)

```bash
python main.py --mode pipeline-only --max-jobs 10
```

### Full run — scrape then apply

```bash
python main.py --mode full --max-jobs 20
```

### Scrape specific platforms only

```bash
python main.py --mode full --platforms linkedin naukri --max-jobs 10
```

---

## How the pipeline works — one job end to end

```python
# Every job goes through this state machine

state = {
    "job_title":       "Data Engineer",
    "company":         "TechCorp",
    "job_description": "We are looking for...",
    "platform":        "naukri",
}

# Node 1: Analyse JD
state["jd_analysis"]  = extract_skills_and_keywords(state["job_description"])
state["match"]        = score_candidate_match(state["jd_analysis"], resume)
state["company_intel"]= analyse_company(state["job_description"])

# Conditional: skip if match < 0.5
if state["match"]["match_score"] < 0.5:
    state["status"] = "skipped"
    return

# Node 2: Tailor resume (5 layers)
state["tailored_resume"] = tailor_resume(resume, state["jd_analysis"])
state["ats_result"]      = score_ats(state["tailored_resume"], state["job_description"])

# Node 3: Generate documents
state["cover_letter"] = generate_cover_letter(resume, state["jd_analysis"])
state["pdf_path"]     = generate_pdf(state["tailored_resume"])

# Node 4: Answer questions
state["custom_answers"] = answer_questions_from_resume(application_questions)

# Node 5: Submit
submit_application(state)

# Node 6: Track
save_to_database(state)
```

---

## Configuration

All preferences are set in `config/settings.py`:

```python
# Target roles to search for
SEARCH_ROLES = [
    "Data Engineer",
    "AI Engineer",
    "Data Scientist",
    "Machine Learning Engineer",
    "Python Developer",
]

# Locations
SEARCH_LOCATIONS = ["Kochi", "Bangalore", "Trivandrum", "Remote"]

# Experience level filter (2=Entry, 3=Associate)
EXPERIENCE_LEVELS = [2, 3]

# Quality thresholds
MIN_MATCH_SCORE = 0.5   # skip jobs below this
MIN_ATS_SCORE   = 70    # don't submit if ATS score below this

# LLM model (change to switch models instantly)
LLM_MODEL = "meta-llama/llama-3.1-8b-instruct"
```

---

## Database and tracking

Every application is saved to `data/applications.db` with full details.

View stats anytime:

```bash
python tracker/database.py
```

Output:
```
── Dashboard Stats ───────────────────────────────
  total                12
  submitted            11
  skipped              1
  response_rate        0.0%
  avg_match            69.5%
  avg_ats              80.5/100

── Skill gap report ──────────────────────────────
  Adding these skills would unlock N more job matches
  → Docker (missing in 3 jobs)
  → Kubernetes (missing in 2 jobs)
```

---

## Comparison with existing tools

| Feature | LazyApply | Sonara | LoopCV | This project |
|---|---|---|---|---|
| Multi-platform scraping | ✓ | ✓ | ✓ | ✓ |
| Resume tailoring per job | ✗ | Partial | ✗ | ✓ 5 layers |
| JD analysis with LLM | ✗ | ✗ | ✗ | ✓ |
| RAG question answering | ✗ | ✗ | ✗ | ✓ |
| ATS score gate | ✗ | ✗ | ✗ | ✓ |
| Company intel before applying | ✗ | ✗ | ✗ | ✓ |
| Match scoring | ✗ | Basic | ✗ | ✓ |
| Skill gap report | ✗ | ✗ | ✗ | ✓ |
| Open source | ✗ | ✗ | ✗ | ✓ |

---

## Current status

- [x] Multi-platform scraper (LinkedIn, Naukri, Indeed, Wellfound, Remotive)
- [x] LLM-powered JD analysis and match scoring
- [x] Company intelligence layer
- [x] RAG pipeline over candidate resume
- [x] 5-layer resume tailoring engine
- [x] ATS scoring gate
- [x] Cover letter generation
- [x] Professional PDF generation
- [x] LangGraph orchestrator
- [x] Application tracking database
- [ ] Selenium form filler (in progress)
- [ ] Auto follow-up emails
- [ ] Interview prep agent
- [ ] Web dashboard

---

## Author

**Mariya Mathew**
Data Engineer at LTIMindtree
B.Tech in Artificial Intelligence and Data Science — Rajagiri School of Engineering and Technology (2025)

[LinkedIn](https://linkedin.com/in/mariya-mathew-03297525b) · [GitHub](https://github.com/mariyamathew121)

---

## License

MIT License — free to use, modify, and distribute.