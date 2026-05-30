# agent/graph.py
# Wires all nodes into a LangGraph pipeline.
# This is the single entry point for processing any job.

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langgraph.graph import StateGraph, END
from agent.state import JobState
from agent.nodes import (
    node_analyse,
    node_decide,
    node_tailor,
    node_generate_docs,
    node_answer_questions,
    node_submit,
    node_track,
    node_skip
)


def build_graph():
    """
    Builds and compiles the full job application pipeline.
    Returns a compiled graph ready to invoke.
    """

    graph = StateGraph(JobState)

    # ── Register all nodes ─────────────────────────────────────────────
    graph.add_node("analyse",         node_analyse)
    graph.add_node("tailor",          node_tailor)
    graph.add_node("generate_docs",   node_generate_docs)
    graph.add_node("answer_questions",node_answer_questions)
    graph.add_node("submit",          node_submit)
    graph.add_node("track",           node_track)
    graph.add_node("skip",            node_skip)

    # ── Entry point ────────────────────────────────────────────────────
    graph.set_entry_point("analyse")

    # ── Conditional edge after analyse ────────────────────────────────
    # node_decide returns "tailor" or "skip" based on match score
    graph.add_conditional_edges(
        "analyse",
        node_decide,
        {
            "tailor": "tailor",
            "skip":   "skip"
        }
    )

    # ── Linear path for good matches ──────────────────────────────────
    graph.add_edge("tailor",           "generate_docs")
    graph.add_edge("generate_docs",    "answer_questions")
    graph.add_edge("answer_questions", "submit")
    graph.add_edge("submit",           "track")

    # ── Both paths end here ────────────────────────────────────────────
    graph.add_edge("track", END)
    graph.add_edge("skip",  END)

    return graph.compile()


# ── Compiled graph — import this everywhere ────────────────────────────
pipeline = build_graph()


# ── Test: run one job through the full pipeline ────────────────────────

if __name__ == "__main__":

    # Sample job — normally comes from the scraper
    sample_job = {
        "job_id":      "job_001",
        "job_title":   "Python Developer",
        "company":     "TechStartup Inc",
        "job_url":     "https://linkedin.com/jobs/view/123456",
        "platform":    "linkedin",
        "status":      "scraped",

        "job_description": """
        We are looking for a Python Developer to join our team.

        Requirements:
        - 2+ years Python experience
        - FastAPI or Flask for REST API development
        - PostgreSQL or MySQL database experience
        - Git version control
        - Nice to have: Docker, Redis, LangChain

        Responsibilities:
        - Build and maintain backend APIs
        - Write clean tested Python code
        - Collaborate in a remote-first team

        We are a fast-growing remote-first startup.
        Competitive salary based on experience.
        """,

        # Optional fields start as None
        "jd_analysis":     None,
        "match":           None,
        "company_intel":   None,
        "should_apply":    None,
        "tailored_resume": None,
        "ats_result":      None,
        "cover_letter":    None,
        "pdf_path":        None,
        "custom_answers":  None,
        "error":           None,
        "submitted_at":    None,
    }

    print("Starting job application pipeline...\n")
    result = pipeline.invoke(sample_job)

    print(f"\nFinal status: {result['status']}")

    if result["status"] == "submitted":
        print(f"\nCover letter preview:")
        print("-" * 55)
        print(result["cover_letter"][:300] + "...")