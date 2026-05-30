# agent/nodes.py
# Each function here is one node in the LangGraph pipeline.
# They run in order: analyse → decide → tailor → score → answer → submit → track

import sys
import os
import json
from datetime import datetime
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rag.analyser      import run_full_analysis
from rag.retriever     import smart_answer
from tailoring.tailor  import tailor_resume
from tailoring.ats_scorer   import score_and_decide
from tailoring.cover_letter import generate_cover_letter
from tailoring.resume_pdf   import generate_pdf, make_pdf_filename
from config.settings import (
    MIN_MATCH_SCORE, MIN_ATS_SCORE, CANDIDATE_PROFILE
)


# ── Load resume + QA once at startup ──────────────────────────────────

with open("config/resume.json") as f:
    BASE_RESUME = json.load(f)

with open("config/user_qa.json") as f:
    USER_QA = json.load(f)


# ── Node 1: Analyse the job description ───────────────────────────────

def node_analyse(state: dict) -> dict:
    """
    Reads the job description.
    Extracts skills, scores match, runs company intel.
    Decides whether to proceed or skip.
    """
    print(f"\n[1/6] Analysing: {state['job_title']} at {state['company']}")

    try:
        result = run_full_analysis(
            state["job_description"], BASE_RESUME
        )
        return {
            **state,
            "jd_analysis":   result["jd_analysis"],
            "match":         result["match"],
            "company_intel": result["company_intel"],
            "should_apply":  result["should_apply"],
            "status":        "analysed"
        }
    except Exception as e:
        return {**state, "status": "failed", "error": str(e)}


# ── Node 2: Decision gate ──────────────────────────────────────────────

def node_decide(state: dict) -> str:
    """
    Conditional node — returns which node to go to next.
    Returns "tailor" if we should apply, "skip" if not.
    This is a router — not a regular node.
    """
    if state.get("status") == "failed":
        return "skip"

    match_score = state.get("match", {}).get("match_score", 0)

    if match_score >= MIN_MATCH_SCORE and state.get("should_apply"):
        print(f"  Match score: {match_score:.0%} — proceeding")
        return "tailor"
    else:
        print(f"  Match score: {match_score:.0%} — skipping")
        return "skip"


# ── Node 3: Tailor the resume ──────────────────────────────────────────

def node_tailor(state: dict) -> dict:
    """
    Runs 5-layer resume tailoring.
    Scores the result with ATS scorer.
    If ATS score too low — marks as failed so we don't submit weak apps.
    """
    print(f"[2/6] Tailoring resume...")

    try:
        # 5-layer tailoring
        tailored = tailor_resume(
            BASE_RESUME,
            state["jd_analysis"],
            state["job_title"],
            state["company"]
        )

        # ATS score gate
        ats = score_and_decide(tailored, state["job_description"])
        print(f"  ATS score: {ats['ats_score']}/100 — {ats['verdict']}")

        if not ats["submit"]:
            print(f"  ATS score too low — skipping submission")
            return {
                **state,
                "tailored_resume": tailored,
                "ats_result":      ats,
                "status":          "low_ats_score"
            }

        return {
            **state,
            "tailored_resume": tailored,
            "ats_result":      ats,
            "status":          "tailored"
        }

    except Exception as e:
        return {**state, "status": "failed", "error": str(e)}


# ── Node 4: Generate cover letter + PDF ───────────────────────────────

def node_generate_docs(state: dict) -> dict:
    """
    Generates the cover letter and PDF resume.
    These are the actual files that get submitted.
    """
    print(f"[3/6] Generating cover letter and PDF...")

    try:
        # Cover letter
        cover = generate_cover_letter(
            BASE_RESUME,
            state["jd_analysis"],
            state["job_title"],
            state["company"]
        )

        # Strip "Here is a cover letter..." prefix if model adds it
        if cover.lower().startswith("here is"):
            cover = cover[cover.find("\n") + 1:].strip()

        # PDF resume
        pdf_path = make_pdf_filename(
            state["job_title"], state["company"]
        )
        generate_pdf(state["tailored_resume"], pdf_path)

        return {
            **state,
            "cover_letter": cover,
            "pdf_path":     pdf_path,
            "status":       "docs_ready"
        }

    except Exception as e:
        return {**state, "status": "failed", "error": str(e)}


# ── Node 5: Answer custom questions ───────────────────────────────────

def node_answer_questions(state: dict) -> dict:
    """
    Answers custom questions from the job application form.
    Uses pre-written answers first, RAG for anything custom.
    In real usage, these questions come from scraping the form.
    For now we use common questions as placeholder.
    """
    print(f"[4/6] Answering application questions...")

    # Common questions most applications ask
    # In the real pipeline these come from the form scraper
    common_questions = [
        "How many years of Python experience do you have?",
        "Why do you want to work here?",
        "What is your notice period?",
        "Are you comfortable working remotely?",
        "What is your salary expectation?",
    ]

    answers = {}
    for q in common_questions:
        answers[q] = smart_answer(
            q,
            state["job_title"],
            state["company"],
            USER_QA
        )

    return {
        **state,
        "custom_answers": answers,
        "status":         "ready_to_submit"
    }


# ── Node 6: Submit application ────────────────────────────────────────

def node_submit(state: dict) -> dict:
    """
    Submits the application via Selenium form filler.
    For now this is a placeholder — real Selenium code comes
    in the submitter module (next module we build).
    """
    print(f"[5/6] Submitting application...")

    # TODO: replace with real Selenium submission
    # from submitter.engine import submit_application
    # result = submit_application(state)

    # Placeholder — simulates successful submission
    print(f"  [SIMULATED] Application submitted to {state['company']}")

    return {
        **state,
        "status":       "submitted",
        "submitted_at": datetime.now().isoformat()
    }


# ── Node 7: Track result ───────────────────────────────────────────────

def node_track(state: dict) -> dict:
    """
    Saves the final application result to the database.
    For now prints a summary — real DB code comes in tracker module.
    """
    print(f"[6/6] Tracking result...")

    from tracker.database import save_application
    save_application(state)

    # TODO: replace with real DB save
    # from tracker.database import save_application
    # save_application(state)

    print(f"\n{'='*55}")
    print(f"  Job:     {state['job_title']} at {state['company']}")
    print(f"  Status:  {state['status']}")
    print(f"  Match:   {state['match']['match_score']:.0%}")
    print(f"  ATS:     {state['ats_result']['ats_score']}/100")
    print(f"  PDF:     {state.get('pdf_path', 'N/A')}")
    print(f"{'='*55}")

    return state


# ── Node: Skip ─────────────────────────────────────────────────────────

def node_skip(state: dict) -> dict:
    """Called when match score is too low or company intel says skip."""
    reason = state.get("error", "low match score or company red flags")
    print(f"  Skipped: {state['job_title']} — {reason}")
    return {**state, "status": "skipped"}