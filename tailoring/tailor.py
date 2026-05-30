# tailoring/tailor.py
# The resume tailoring engine — rewrites your resume for each specific job.
# 5 layers of tailoring:
#   1. Summary rewrite     — matches JD tone and keywords
#   2. Skills reordering   — puts matching skills first
#   3. Bullet reframing    — rewords achievements in JD language
#   4. Project selection   — picks most relevant 2-3 projects
#   5. ATS keyword inject  — ensures critical keywords appear

import os
import sys
import json
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_core.prompts import ChatPromptTemplate
from config.llm import llm_precise, llm_creative


# ── Prompt 1: rewrite summary ──────────────────────────────────────────

SUMMARY_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are an expert resume writer.
Rewrite resume summaries to match specific job descriptions.
Rules you must follow:
- Never invent experience the candidate does not have
- Keep all facts true
- Maximum 3 sentences
- Do not start with 'I'
- No buzzwords: passionate, dynamic, synergy, guru, ninja
- Mirror the tone and language of the job description
Return only the rewritten summary. Nothing else."""),

    ("human", """Rewrite this resume summary for the role below.

Job title: {job_title}
Company tone: {company_tone}
Required skills to emphasise: {required_skills}
ATS keywords to naturally include: {ats_keywords}

Original summary:
{original_summary}

Rewritten summary:""")
])


# ── Prompt 2: reframe bullet points ───────────────────────────────────

BULLETS_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are an expert resume writer.
Reframe experience bullet points to match a target role.
Rules:
- Never change the actual achievement or numbers
- Use language and keywords from the job description
- Start each bullet with a strong action verb
- Keep each bullet to one line
- Return a JSON array of strings only. No explanation."""),

    ("human", """Reframe these bullet points for a {job_title} role.

Keywords to naturally use: {keywords}
Company tone: {company_tone}

Original bullets:
{bullets}

Return only a JSON array like: ["bullet 1", "bullet 2", "bullet 3"]""")
])


# ── Prompt 3: rewrite project descriptions ────────────────────────────

PROJECT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are an expert resume writer.
Rewrite project descriptions to highlight relevance to a target role.
Rules:
- Keep all technical facts true
- Emphasise aspects most relevant to the job
- 2 sentences maximum per project
- Return a JSON array of objects only."""),

    ("human", """Rewrite these project descriptions for a {job_title} role.

Required skills for the role: {required_skills}

Projects:
{projects}

Return a JSON array like:
[{{"name": "project name", "description": "rewritten description", "tech": ["tech1"]}}]""")
])


# ── Layer 1: rewrite summary ───────────────────────────────────────────

def rewrite_summary(original_summary: str, jd_analysis: dict,
                    job_title: str) -> str:
    """Rewrites the resume summary to match this specific job."""

    content = result.content.strip()

    # Strip LLM narration prefixes if model adds them
    prefixes_to_remove = [
        "here is a rewritten summary",
        "here's a rewritten summary",
        "rewritten summary:",
        "here is the rewritten summary",
        "here is a summary",
        "here's the summary",
    ]
    content_lower = content.lower()
    for prefix in prefixes_to_remove:
        if content_lower.startswith(prefix):
            # Remove everything up to and including the first colon
            if ":" in content:
                content = content[content.index(":") + 1:].strip()
            break

    return content


# ── Layer 2: reorder skills ────────────────────────────────────────────

def reorder_skills(resume: dict, jd_analysis: dict) -> list:
    """
    Reorders your skills list so matching skills appear first.
    ATS systems weight skills listed earlier more heavily.
    """
    all_skills = (
        resume["skills"]["languages"]  +
        resume["skills"]["frameworks"] +
        resume["skills"]["ai_ml"]      +
        resume["skills"]["tools"]      +
        resume["skills"]["other"]
    )

    required_lower    = [s.lower() for s in jd_analysis["required_skills"]]
    nice_lower        = [s.lower() for s in jd_analysis["nice_to_have"]]
    keywords_lower    = [s.lower() for s in jd_analysis["keywords_for_ats"]]

    tier1 = []  # exact match with required
    tier2 = []  # match with nice-to-have or keywords
    tier3 = []  # everything else

    for skill in all_skills:
        skill_lower = skill.lower()
        if any(skill_lower in r or r in skill_lower
               for r in required_lower):
            tier1.append(skill)
        elif any(skill_lower in n or n in skill_lower
                 for n in nice_lower + keywords_lower):
            tier2.append(skill)
        else:
            tier3.append(skill)

    return tier1 + tier2 + tier3


# ── Layer 3: reframe bullet points ────────────────────────────────────

def reframe_bullets(bullets: list, jd_analysis: dict,
                    job_title: str) -> list:
    """Rewords experience bullets in the language of the target job."""

    chain  = BULLETS_PROMPT | llm_precise
    result = chain.invoke({
        "job_title":    job_title,
        "keywords":     ", ".join(jd_analysis["keywords_for_ats"]),
        "company_tone": jd_analysis.get("company_tone", "professional"),
        "bullets":      json.dumps(bullets)
    })

    try:
        return json.loads(result.content)
    except json.JSONDecodeError:
        content = result.content.strip()
        start   = content.find("[")
        end     = content.rfind("]") + 1
        return json.loads(content[start:end])


# ── Layer 4: select best projects ─────────────────────────────────────

def select_best_projects(projects: list, jd_analysis: dict,
                         job_title: str) -> list:
    """
    Picks the 2-3 most relevant projects and rewrites their
    descriptions to emphasise what this specific job cares about.
    """
    required_lower = [s.lower() for s in jd_analysis["required_skills"]]

    # Score each project by how many required skills it uses
    scored = []
    for project in projects:
        tech_lower = [t.lower() for t in project.get("tech", [])]
        score      = sum(
            1 for t in tech_lower
            if any(t in r or r in t for r in required_lower)
        )
        scored.append((score, project))

    # Sort by relevance, take top 3
    scored.sort(key=lambda x: x[0], reverse=True)
    top_projects = [p for _, p in scored[:3]]

    # Rewrite descriptions to emphasise relevance
    chain  = PROJECT_PROMPT | llm_precise
    result = chain.invoke({
        "job_title":       job_title,
        "required_skills": ", ".join(jd_analysis["required_skills"]),
        "projects":        json.dumps(top_projects)
    })

    try:
        return json.loads(result.content)
    except json.JSONDecodeError:
        content = result.content.strip()
        start   = content.find("[")
        end     = content.rfind("]") + 1
        return json.loads(content[start:end])


# ── Layer 5: ATS keyword injection ────────────────────────────────────

def inject_ats_keywords(tailored_resume: dict,
                        jd_analysis: dict) -> dict:
    """
    Checks that critical ATS keywords appear somewhere in the resume.
    If a keyword is missing, adds it naturally to the skills list.
    This is the final safety net before scoring.
    """
    keywords     = jd_analysis["keywords_for_ats"]
    skills_text  = " ".join(tailored_resume["skills_ordered"]).lower()
    summary_text = tailored_resume["summary"].lower()
    full_text    = skills_text + " " + summary_text

    missing_keywords = [
        kw for kw in keywords
        if kw.lower() not in full_text
    ]

    # Add missing keywords to skills list
    if missing_keywords:
        tailored_resume["skills_ordered"] = (
            tailored_resume["skills_ordered"] + missing_keywords
        )

    return tailored_resume


# ── Master tailoring function ──────────────────────────────────────────

def tailor_resume(resume: dict, jd_analysis: dict,
                  job_title: str, company: str) -> dict:
    """
    Master function — runs all 5 tailoring layers in sequence.
    Input:  your base resume dict + JD analysis from analyser.py
    Output: fully tailored resume dict ready for PDF generation
    """
    print(f"\n  Tailoring resume for: {job_title} at {company}")

    # Layer 1 — rewrite summary
    print("  Layer 1: Rewriting summary...")
    tailored_summary = rewrite_summary(
        resume["summary"], jd_analysis, job_title
    )

    # Layer 2 — reorder skills
    print("  Layer 2: Reordering skills...")
    ordered_skills = reorder_skills(resume, jd_analysis)

    # Layer 3 — reframe bullets
    print("  Layer 3: Reframing experience bullets...")
    tailored_bullets = reframe_bullets(
        resume["experience"][0]["bullets"],
        jd_analysis,
        job_title
    )

    # Layer 4 — select and rewrite projects
    print("  Layer 4: Selecting best projects...")
    best_projects = select_best_projects(
        resume["projects"], jd_analysis, job_title
    )

    # Assemble tailored resume
    tailored = {
        **resume,
        "summary":        tailored_summary,
        "skills_ordered": ordered_skills,
        "experience": [{
            **resume["experience"][0],
            "bullets": tailored_bullets
        }],
        "projects":       best_projects,
        "tailored_for": {
            "job_title": job_title,
            "company":   company,
            "keywords":  jd_analysis["keywords_for_ats"]
        }
    }

    # Layer 5 — ATS keyword safety net
    print("  Layer 5: ATS keyword injection...")
    tailored = inject_ats_keywords(tailored, jd_analysis)

    print("  Tailoring complete.")
    return tailored


# ── Test it ────────────────────────────────────────────────────────────

if __name__ == "__main__":

    # Load resume
    with open("config/resume.json") as f:
        resume = json.load(f)

    # Sample JD analysis (normally comes from analyser.py)
    sample_jd_analysis = {
        "job_title":            "Backend Python Developer",
        "company_tone":         "startup",
        "required_skills":      ["Python", "FastAPI", "PostgreSQL",
                                 "Docker", "REST APIs"],
        "nice_to_have":         ["Redis", "AWS", "Kubernetes"],
        "years_experience":     2,
        "key_responsibilities": ["Build APIs", "Write tests",
                                 "Code reviews"],
        "keywords_for_ats":     ["Python", "FastAPI", "PostgreSQL",
                                 "Docker", "backend", "API"],
        "remote_friendly":      True,
        "seniority_level":      "mid"
    }

    print("Running 5-layer resume tailoring...\n")
    tailored = tailor_resume(
        resume,
        sample_jd_analysis,
        job_title = "Backend Python Developer",
        company   = "TechStartup Inc"
    )

    print("\n── Original Summary ─────────────────────────────")
    print(resume["summary"])

    print("\n── Tailored Summary ─────────────────────────────")
    print(tailored["summary"])

    print("\n── Skills (ordered for this job) ────────────────")
    print(" · ".join(tailored["skills_ordered"]))

    print("\n── Tailored Bullets ─────────────────────────────")
    for b in tailored["experience"][0]["bullets"]:
        print(f"  • {b}")

    print("\n── Selected Projects ────────────────────────────")
    for p in tailored["projects"]:
        print(f"  {p['name']}: {p['description']}")

    print("\n── ATS Keywords confirmed in resume ─────────────")
    print(" · ".join(tailored["tailored_for"]["keywords"]))