# rag/analyser.py
# Reads a job description and extracts structured information from it.
# This is the first thing that runs for every job in the pipeline.

import json
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_core.prompts import ChatPromptTemplate
from config.llm import llm_precise, llm_creative


# ── Prompt 1: extract skills and requirements from the JD ──────────────

JD_ANALYSIS_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are an expert job description analyst.
Your job is to read a job description and extract key information.
Always return a valid JSON object. Never return anything else.
No markdown, no explanation, just the raw JSON."""),

    ("human", """Analyse this job description and return a JSON object 
with exactly these fields:

{{
  "job_title":           "exact job title from the posting",
  "company_tone":        "startup / corporate / agency / nonprofit",
  "required_skills":     ["list", "of", "must-have", "skills"],
  "nice_to_have":        ["list", "of", "preferred", "skills"],
  "years_experience":    0,
  "key_responsibilities":["list", "of", "main", "duties"],
  "keywords_for_ats":    ["important", "keywords", "to", "include"],
  "remote_friendly":     true,
  "seniority_level":     "junior / mid / senior / lead"
}}

Job description:
{job_description}""")
])


# ── Prompt 2: score how well the candidate matches this job ────────────

MATCH_SCORE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are an expert recruiter who evaluates candidate fit.
Return a valid JSON object only. No explanation."""),

    ("human", """Score how well this candidate matches this job.

Candidate skills: {candidate_skills}
Candidate experience: {candidate_experience}
Candidate summary: {candidate_summary}

Job required skills: {required_skills}
Job years experience needed: {years_experience}
Job seniority: {seniority_level}

Return exactly this JSON:
{{
  "match_score":     0.0,
  "matching_skills": ["skills", "candidate", "has"],
  "missing_skills":  ["skills", "candidate", "lacks"],
  "recommendation":  "apply / skip / strong apply",
  "reason":          "one sentence explanation"
}}

match_score must be a float between 0.0 and 1.0.""")
])


# ── Prompt 3: company research summary ────────────────────────────────

COMPANY_INTEL_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a career advisor helping a job seeker 
evaluate whether a company is worth applying to.
Return a valid JSON object only."""),

    ("human", """Based on the job description below, infer what you can
about this company and role. Return this JSON:

{{
  "company_size":      "startup / smb / enterprise / unknown",
  "industry":          "industry sector",
  "growth_signals":    ["positive", "signals", "from", "jd"],
  "red_flags":         ["any", "warning", "signs"],
  "culture_keywords":  ["words", "describing", "culture"],
  "apply_recommended": true
}}

Job description:
{job_description}""")
])


# ── Main functions ─────────────────────────────────────────────────────

def analyse_jd(job_description: str) -> dict:
    """
    Step 1 — Read the JD and extract all structured information.
    Returns a dict with skills, tone, seniority, ATS keywords etc.
    """
    chain  = JD_ANALYSIS_PROMPT | llm_precise
    result = chain.invoke({"job_description": job_description})

    try:
        return json.loads(result.content)
    except json.JSONDecodeError:
        # Sometimes the model adds extra text — strip it
        content = result.content.strip()
        start   = content.find("{")
        end     = content.rfind("}") + 1
        return json.loads(content[start:end])


def score_match(jd_analysis: dict, resume: dict) -> dict:
    """
    Step 2 — Score how well the candidate matches the job.
    Uses the JD analysis from step 1 + resume data.
    Returns match score (0-1) + missing skills + recommendation.
    """
    all_skills = (
        resume["skills"]["languages"]  +
        resume["skills"]["frameworks"] +
        resume["skills"]["ai_ml"]      +
        resume["skills"]["tools"]
    )

    chain  = MATCH_SCORE_PROMPT | llm_precise
    result = chain.invoke({
        "candidate_skills":     ", ".join(all_skills),
        "candidate_experience": resume["experience"][0]["title"] +
                                " for " +
                                resume["experience"][0]["start"] +
                                " to "  +
                                resume["experience"][0]["end"],
        "candidate_summary":    resume["summary"],
        "required_skills":      ", ".join(jd_analysis["required_skills"]),
        "years_experience":     jd_analysis["years_experience"],
        "seniority_level":      jd_analysis["seniority_level"]
    })

    try:
        return json.loads(result.content)
    except json.JSONDecodeError:
        content = result.content.strip()
        start   = content.find("{")
        end     = content.rfind("}") + 1
        return json.loads(content[start:end])


def get_company_intel(job_description: str) -> dict:
    """
    Step 3 — Innovative feature: analyse the company from the JD.
    Infers size, culture, red flags, growth signals before applying.
    """
    chain  = COMPANY_INTEL_PROMPT | llm_precise
    result = chain.invoke({"job_description": job_description})

    try:
        return json.loads(result.content)
    except json.JSONDecodeError:
        content = result.content.strip()
        start   = content.find("{")
        end     = content.rfind("}") + 1
        return json.loads(content[start:end])


def run_full_analysis(job_description: str, resume: dict) -> dict:
    """
    Master function — runs all 3 analyses and returns everything.
    This is what the orchestrator calls for each job.
    """
    print("  Analysing job description...")
    jd_data = analyse_jd(job_description)

    print("  Scoring candidate match...")
    match    = score_match(jd_data, resume)

    print("  Running company intel...")
    company  = get_company_intel(job_description)

    return {
        "jd_analysis":    jd_data,
        "match":          match,
        "company_intel":  company,
        "should_apply":   (
            match["match_score"] >= 0.5 and
            company["apply_recommended"]
        )
    }


# ── Test it directly ───────────────────────────────────────────────────

if __name__ == "__main__":
    import json

    # A sample job description to test with
    SAMPLE_JD = """
    We are looking for a Python Developer to join our growing team.

    Requirements:
    - 2+ years of Python experience
    - Experience with FastAPI or Flask
    - Familiarity with REST APIs and SQL databases
    - Git version control
    - Nice to have: Docker, Redis, any cloud platform

    Responsibilities:
    - Build and maintain backend APIs
    - Write clean, tested Python code
    - Collaborate with frontend team on integrations
    - Participate in code reviews

    We are a fast-growing startup. Remote friendly.
    Salary: competitive, based on experience.
    """

    # Load your real resume
    with open("config/resume.json") as f:
        resume = json.load(f)

    print("Running full JD analysis...\n")
    result = run_full_analysis(SAMPLE_JD, resume)

    print("\n── JD Analysis ──────────────────────────────")
    print(json.dumps(result["jd_analysis"], indent=2))

    print("\n── Match Score ──────────────────────────────")
    print(json.dumps(result["match"], indent=2))

    print("\n── Company Intel ────────────────────────────")
    print(json.dumps(result["company_intel"], indent=2))

    print("\n── Decision ─────────────────────────────────")
    print("Should apply:", result["should_apply"])
    print("Match score: ", result["match"]["match_score"])
    print("Reason:      ", result["match"]["reason"])