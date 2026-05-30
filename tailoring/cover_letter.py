# tailoring/cover_letter.py
# Generates a tailored cover letter for each specific job.
# Uses JD analysis + your resume to write something genuine,
# not a generic template that screams "AI wrote this".

import os
import sys
import json
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_core.prompts import ChatPromptTemplate
from config.llm import llm_creative


# ── Cover letter prompt ────────────────────────────────────────────────

COVER_LETTER_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are an expert cover letter writer.
You write genuine, specific cover letters that do not sound like AI.
Rules you must follow:
- 3 short paragraphs only — never more
- Never use: passionate, excited, dynamic, synergy, leverage
- Never start with: I am writing to apply / I am excited
- Always reference the specific company and role by name
- Ground every claim in the candidate's actual experience
- Write like a confident human, not a robot
- Total length: 150 to 200 words maximum"""),

    ("human", """Write a cover letter for this application.

Role: {job_title}
Company: {company}
Company tone: {company_tone}
Key requirements: {required_skills}

Candidate background:
{candidate_summary}

Most relevant experience:
{relevant_experience}

Most relevant project:
{relevant_project}

Structure:
Paragraph 1: Why this specific role at this specific company — one strong opening sentence, then connect their needs to candidate's background.
Paragraph 2: One specific achievement or project that directly proves they can do this job.
Paragraph 3: Brief, confident close — what they bring on day one.""")
])


# ── Main function ──────────────────────────────────────────────────────

def generate_cover_letter(resume: dict, jd_analysis: dict,
                          job_title: str, company: str) -> str:
    """
    Generates a tailored cover letter for one specific job.
    Called by the orchestrator after tailoring is complete.
    """

    # Pick the most relevant project based on required skills
    required_lower = [s.lower() for s in jd_analysis["required_skills"]]
    best_project   = resume["projects"][0]  # default to first

    for project in resume["projects"]:
        tech_lower = [t.lower() for t in project.get("tech", [])]
        if any(t in required_lower for t in tech_lower):
            best_project = project
            break

    # Build relevant experience string
    exp           = resume["experience"][0]
    relevant_exp  = f"{exp['title']} at {exp['company']} " \
                    f"({exp['start']} to {exp['end']}): " + \
                    " | ".join(exp["bullets"][:2])

    chain  = COVER_LETTER_PROMPT | llm_creative
    result = chain.invoke({
        "job_title":          job_title,
        "company":            company,
        "company_tone":       jd_analysis.get("company_tone", "professional"),
        "required_skills":    ", ".join(jd_analysis["required_skills"][:5]),
        "candidate_summary":  resume["summary"],
        "relevant_experience": relevant_exp,
        "relevant_project":   f"{best_project['name']}: "
                              f"{best_project['description']}"
    })

    return result.content.strip()


# ── Test it ────────────────────────────────────────────────────────────

if __name__ == "__main__":

    with open("config/resume.json") as f:
        resume = json.load(f)

    sample_jd_analysis = {
        "company_tone":    "startup",
        "required_skills": ["Python", "FastAPI", "PostgreSQL",
                            "Docker", "REST APIs"],
        "nice_to_have":    ["Redis", "AWS"]
    }

    print("Generating cover letter...\n")
    letter = generate_cover_letter(
        resume        = resume,
        jd_analysis   = sample_jd_analysis,
        job_title     = "Backend Python Developer",
        company       = "TechStartup Inc"
    )

    print("── Cover Letter ─────────────────────────────────")
    print(letter)
    print(f"\nWord count: {len(letter.split())}")