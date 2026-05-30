# tailoring/ats_scorer.py
# Scores a tailored resume against a job description before submitting.
# This is your gate — only submit if ATS score is above threshold.
# Innovative feature: no existing tool gates submission on ATS score.

import os
import sys
import json
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_core.prompts import ChatPromptTemplate
from config.llm import llm_precise
from config.settings import MIN_ATS_SCORE


# ── Scoring prompt ─────────────────────────────────────────────────────

ATS_SCORE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are an ATS (Applicant Tracking System) simulator.
Score resumes against job descriptions exactly like real ATS software.
Return only a valid JSON object. No explanation."""),

    ("human", """Score this resume against the job description.

Job Description:
{job_description}

Resume Content:
Summary: {summary}
Skills: {skills}
Experience bullets: {bullets}
Projects: {projects}

Return exactly this JSON:
{{
  "ats_score":           0,
  "keyword_matches":     ["keywords", "found", "in", "resume"],
  "keyword_misses":      ["keywords", "missing", "from", "resume"],
  "score_breakdown": {{
    "keyword_match":     0,
    "skills_alignment":  0,
    "experience_match":  0,
    "overall_relevance": 0
  }},
  "improvements":        ["specific", "suggestions", "to", "improve"],
  "verdict":             "strong / good / weak / reject"
}}

ats_score must be an integer 0-100.
Each score_breakdown field must be an integer 0-25.""")
])


# ── Main scorer function ───────────────────────────────────────────────

def score_resume(tailored_resume: dict,
                 job_description: str) -> dict:
    """
    Scores the tailored resume against the raw job description.
    Returns detailed breakdown + improvement suggestions.
    Called after tailor.py, before submitting the application.
    """
    # Flatten resume into text fields for scoring
    skills  = " · ".join(tailored_resume.get("skills_ordered", []))
    bullets = " | ".join(
        tailored_resume["experience"][0]["bullets"]
    )
    projects = " | ".join([
        f"{p['name']}: {p['description']}"
        for p in tailored_resume.get("projects", [])
    ])

    chain  = ATS_SCORE_PROMPT | llm_precise
    result = chain.invoke({
        "job_description": job_description,
        "summary":         tailored_resume["summary"],
        "skills":          skills,
        "bullets":         bullets,
        "projects":        projects
    })

    try:
        return json.loads(result.content)
    except json.JSONDecodeError:
        content = result.content.strip()
        start   = content.find("{")
        end     = content.rfind("}") + 1
        return json.loads(content[start:end])


def should_submit(ats_result: dict) -> tuple[bool, str]:
    """
    Decision gate — should we submit this application?
    Returns (True/False, reason string)
    """
    score   = ats_result["ats_score"]
    verdict = ats_result["verdict"]

    if score >= MIN_ATS_SCORE:
        return True, f"ATS score {score}/100 — {verdict}"
    else:
        improvements = " | ".join(ats_result["improvements"][:2])
        return False, f"ATS score {score}/100 too low. Fix: {improvements}"


def score_and_decide(tailored_resume: dict,
                     job_description: str) -> dict:
    """
    Master function — scores resume and makes submit decision.
    Returns full scoring result + submit decision.
    """
    print("  Scoring resume against JD...")
    ats_result = score_resume(tailored_resume, job_description)

    submit, reason = should_submit(ats_result)

    return {
        **ats_result,
        "submit":        submit,
        "submit_reason": reason
    }


# ── Test it ────────────────────────────────────────────────────────────

if __name__ == "__main__":

    # Sample tailored resume (normally comes from tailor.py)
    sample_resume = {
        "summary": "Highly skilled Python developer with expertise in "
                   "designing scalable backend systems using FastAPI and "
                   "PostgreSQL. Proven experience containerising applications "
                   "with Docker and building robust REST APIs.",
        "skills_ordered": ["Python", "FastAPI", "PostgreSQL", "Docker",
                           "REST APIs", "Redis", "SQL", "Git"],
        "experience": [{
            "bullets": [
                "Streamlined backend workflows by automating manual tasks, "
                "resulting in 40% reduction in labour",
                "Designed and implemented scalable FastAPI-based backend "
                "APIs handling 10k+ daily requests",
                "Integrated external APIs and built efficient data "
                "processing pipelines"
            ]
        }],
        "projects": [{
            "name":        "AI Job Application Agent",
            "description": "Built scalable backend using FastAPI and "
                           "PostgreSQL, integrated with Redis for caching."
        }]
    }

    sample_jd = """
    We are looking for a Backend Python Developer.
    Requirements:
    - Strong Python skills
    - FastAPI or Django REST framework
    - PostgreSQL database experience
    - Docker containerisation
    - REST API design and development
    - Git version control
    Nice to have: Redis, AWS, CI/CD pipelines
    """

    print("Running ATS scorer...\n")
    result = score_and_decide(sample_resume, sample_jd)

    print(f"\n── ATS Score: {result['ats_score']}/100 ──────────────────")
    print(f"Verdict:  {result['verdict']}")
    print(f"Submit:   {result['submit']}")
    print(f"Reason:   {result['submit_reason']}")

    print(f"\n── Score Breakdown ──────────────────────────────")
    for category, score in result["score_breakdown"].items():
        bar = "█" * score + "░" * (25 - score)
        print(f"  {category:<22} {bar} {score}/25")

    print(f"\n── Keywords Matched ─────────────────────────────")
    print(" · ".join(result["keyword_matches"]))

    print(f"\n── Keywords Missing ─────────────────────────────")
    print(" · ".join(result["keyword_misses"]) or "None")

    print(f"\n── Improvements Suggested ───────────────────────")
    for i, tip in enumerate(result["improvements"], 1):
        print(f"  {i}. {tip}")