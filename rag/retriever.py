# rag/retriever.py
# Answers job application questions using your resume as the source.
# This is how the agent fills "describe your experience with X" fields
# accurately from YOUR real experience — not making things up.

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_core.prompts import ChatPromptTemplate
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from config.settings import OPENROUTER_API_KEY, OPENROUTER_BASE_URL
from config.llm import llm_precise, llm_creative
import json

VECTORSTORE_PATH = "data/vectorstore"


# ── Load the vector store ──────────────────────────────────────────────

def get_vectorstore():
    """Load the ChromaDB vector store built by indexer.py"""
    return Chroma(
        persist_directory  = VECTORSTORE_PATH,
        embedding_function = OpenAIEmbeddings(
            model           = "text-embedding-3-small",
            openai_api_key  = OPENROUTER_API_KEY,
            openai_api_base = OPENROUTER_BASE_URL,
        )
    )


# ── Core answer function ───────────────────────────────────────────────

ANSWER_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are helping a job seeker answer application questions.
You must answer ONLY using the information provided from their resume.
Never invent experience they don't have.
Keep answers concise, professional, and specific.
Write in first person as the candidate."""),

    ("human", """Answer this job application question using the 
resume information below.

Question: {question}

Job context (what role they are applying for):
{job_context}

Relevant resume information:
{resume_chunks}

Write a direct, honest answer in 2-4 sentences maximum.
Do not start with 'I am' or 'As a'.
Do not use buzzwords like passionate, dynamic, or synergy.""")
])


def answer_question(question: str, job_context: str = "") -> str:
    """
    Takes a job application question + the job context,
    searches your resume for relevant info,
    returns a grounded, accurate answer.

    This is called for every custom question on an application form.
    """
    vectorstore = get_vectorstore()

    # Find the most relevant resume chunks for this question
    relevant_chunks = vectorstore.similarity_search(question, k=4)
    resume_context  = "\n\n".join([
        chunk.page_content for chunk in relevant_chunks
    ])

    # Generate the answer grounded in those chunks
    chain  = ANSWER_PROMPT | llm_creative
    result = chain.invoke({
        "question":      question,
        "job_context":   job_context,
        "resume_chunks": resume_context
    })

    return result.content.strip()


def answer_all_questions(questions: list, job_title: str,
                         company: str) -> dict:
    """
    Answers a list of questions from one job application.
    Returns a dict of {question: answer} pairs.
    Called by the orchestrator for each job.
    """
    job_context = f"{job_title} role at {company}"
    answers     = {}

    for question in questions:
        print(f"  Answering: {question[:60]}...")
        answers[question] = answer_question(question, job_context)

    return answers


# ── Pre-loaded answers for common questions ────────────────────────────
# These bypass the LLM for standard questions to save API calls

def get_standard_answer(question: str, user_qa: dict) -> str | None:
    """
    Check if this is a standard question we already have an answer for.
    Returns the pre-written answer or None if not found.
    """
    question_lower = question.lower()

    mappings = {
        "salary":         user_qa.get("salary_expectation"),
        "notice":         user_qa.get("notice_period"),
        "relocat":        user_qa.get("willing_to_relocate"),
        "authoriz":       user_qa.get("work_authorization"),
        "authoris":       user_qa.get("work_authorization"),
        "years":          user_qa.get("years_of_experience"),
        "experience":     user_qa.get("years_of_experience"),
        "why do you want":user_qa.get("why_this_role"),
        "why are you":    user_qa.get("why_leaving"),
        "strength":       user_qa.get("greatest_strength"),
        "weakness":       user_qa.get("greatest_weakness"),
        "tell us about":  user_qa.get("describe_yourself"),
        "describe yours": user_qa.get("describe_yourself"),
    }

    for keyword, answer in mappings.items():
        if keyword in question_lower and answer:
            return answer

    return None  # no pre-written answer — use RAG


def smart_answer(question: str, job_title: str,
                 company: str, user_qa: dict) -> str:
    """
    Smart routing — checks pre-written answers first,
    falls back to RAG for anything custom.
    Saves API calls for standard questions.
    """
    # Try pre-written answer first
    standard = get_standard_answer(question, user_qa)
    if standard:
        return standard

    # Fall back to RAG for custom questions
    return answer_question(question, f"{job_title} at {company}")


# ── Test it ────────────────────────────────────────────────────────────

if __name__ == "__main__":

    # Load pre-written Q&A
    with open("config/user_qa.json") as f:
        user_qa = json.load(f)

    # Simulate questions from a real job application form
    test_questions = [
        "Describe your experience with Python and backend development",
        "What is your experience with REST APIs?",
        "Why do you want to work here?",
        "What is your notice period?",
        "Tell us about a project you built from scratch",
        "What is your salary expectation?",
        "Are you comfortable working in a remote team?",
    ]

    job_title = "Python Developer"
    company   = "TechStartup Inc"

    print("Testing RAG question answering...\n")
    print(f"Role: {job_title} at {company}\n")
    print("=" * 55)

    for question in test_questions:
        print(f"\nQ: {question}")
        answer = smart_answer(question, job_title, company, user_qa)
        print(f"A: {answer}")
        print("-" * 55)