# tailoring/resume_pdf.py — redesigned professional layout

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer,
    HRFlowable, Table, TableStyle
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT


# ── Brand colors ───────────────────────────────────────────────────────
DARK    = colors.HexColor("#0f172a")   # near black
ACCENT  = colors.HexColor("#2563eb")   # strong blue
MUTED   = colors.HexColor("#64748b")   # grey
LIGHT   = colors.HexColor("#f1f5f9")   # light bg
WHITE   = colors.white
BORDER  = colors.HexColor("#e2e8f0")   # light border


# ── Styles ─────────────────────────────────────────────────────────────
def styles():
    return {
        "name": ParagraphStyle(
            "name", fontSize=24, fontName="Helvetica-Bold",
            textColor=DARK, spaceAfter=0, alignment=TA_LEFT
        ),
        "tagline": ParagraphStyle(
            "tagline", fontSize=10, fontName="Helvetica",
            textColor=ACCENT, spaceAfter=0, spaceBefore=4
        ),
        "contact": ParagraphStyle(
            "contact", fontSize=8.5, fontName="Helvetica",
            textColor=MUTED, spaceAfter=0
        ),
        "section": ParagraphStyle(
            "section", fontSize=9, fontName="Helvetica-Bold",
            textColor=ACCENT, spaceBefore=14, spaceAfter=5,
            letterSpacing=1.5
        ),
        "role_title": ParagraphStyle(
            "role_title", fontSize=10.5, fontName="Helvetica-Bold",
            textColor=DARK, spaceAfter=1
        ),
        "role_meta": ParagraphStyle(
            "role_meta", fontSize=8.5, fontName="Helvetica-Oblique",
            textColor=MUTED, spaceAfter=5
        ),
        "body": ParagraphStyle(
            "body", fontSize=9.5, fontName="Helvetica",
            textColor=DARK, leading=15, spaceAfter=4
        ),
        "bullet": ParagraphStyle(
            "bullet", fontSize=9.5, fontName="Helvetica",
            textColor=DARK, leading=15, leftIndent=14,
            spaceAfter=3, bulletIndent=4
        ),
        "skill_pill": ParagraphStyle(
            "skill_pill", fontSize=9, fontName="Helvetica",
            textColor=DARK, leading=13
        ),
        "project_name": ParagraphStyle(
            "project_name", fontSize=10, fontName="Helvetica-Bold",
            textColor=DARK, spaceAfter=2
        ),
        "tech": ParagraphStyle(
            "tech", fontSize=8.5, fontName="Helvetica-Oblique",
            textColor=ACCENT, spaceAfter=6
        ),
        "cert": ParagraphStyle(
            "cert", fontSize=9, fontName="Helvetica",
            textColor=DARK, leading=14, spaceAfter=2
        ),
    }


def section_divider():
    return HRFlowable(
        width="100%", thickness=0.5,
        color=BORDER, spaceAfter=4, spaceBefore=0
    )


def accent_bar():
    """Thick blue bar used under the name header."""
    return HRFlowable(
        width="100%", thickness=2.5,
        color=ACCENT, spaceAfter=10, spaceBefore=6
    )


# ── Skills rendered as grouped pills ──────────────────────────────────

def build_skills_table(skills: list, s: dict) -> Table:
    """
    Renders skills as a clean wrapped grid — looks like tags/pills.
    Groups them into rows of 5.
    """
    row_size = 5
    rows     = []
    row      = []

    for i, skill in enumerate(skills):
        cell = Paragraph(f"&#9632;&nbsp; {skill}", s["skill_pill"])
        row.append(cell)
        if len(row) == row_size:
            rows.append(row)
            row = []

    if row:  # remaining skills
        while len(row) < row_size:
            row.append(Paragraph("", s["skill_pill"]))
        rows.append(row)

    if not rows:
        return Paragraph("", s["body"])

    col_width = (A4[0] - 4 * cm) / row_size
    table     = Table(rows, colWidths=[col_width] * row_size)
    table.setStyle(TableStyle([
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",  (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",(0,0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING",(0, 0), (-1, -1), 2),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [LIGHT, WHITE]),
    ]))
    return table


# ── Main PDF generator ─────────────────────────────────────────────────

def generate_pdf(tailored_resume: dict, output_path: str) -> str:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    doc = SimpleDocTemplate(
        output_path,
        pagesize     = A4,
        leftMargin   = 2 * cm,
        rightMargin  = 2 * cm,
        topMargin    = 1.5 * cm,
        bottomMargin = 1.5 * cm,
    )

    s       = styles()
    story   = []
    p       = tailored_resume["personal"]

    # ── Header block ──────────────────────────────────────────────────
    story.append(Paragraph(p["name"], s["name"]))
    story.append(Spacer(1, 12))

    # Target role as tagline (pulled from tailored_for if available)
    target = tailored_resume.get("tailored_for", {})
    if target.get("job_title"):
        story.append(Paragraph(
        "DATA ENGINEER", s["tagline"]
    ))

    story.append(Spacer(1, 4))
    story.append(accent_bar())

    # Contact info in one clean line
    contact_items = [
        p.get("email", ""),
        p.get("phone", ""),
        p.get("location", ""),
        p.get("linkedin", ""),
        p.get("github", ""),
    ]
    contact_line = "   |   ".join([c for c in contact_items if c])
    story.append(Paragraph(contact_line, s["contact"]))
    story.append(Spacer(1, 10))

    # ── Summary ───────────────────────────────────────────────────────
    story.append(Paragraph("SUMMARY", s["section"]))
    story.append(section_divider())
    story.append(Paragraph(tailored_resume["summary"], s["body"]))

    # ── Skills ────────────────────────────────────────────────────────
    story.append(Paragraph("SKILLS", s["section"]))
    story.append(section_divider())
    skills_table = build_skills_table(
        tailored_resume.get("skills_ordered", []), s
    )
    story.append(skills_table)
    story.append(Spacer(1, 6))

    # ── Experience ────────────────────────────────────────────────────
    story.append(Paragraph("EXPERIENCE", s["section"]))
    story.append(section_divider())

    for role in tailored_resume["experience"]:
        # Two-column row: role title left, dates right
        title_para = Paragraph(
            f"{role['title']}  —  {role['company']}", s["role_title"]
        )
        date_para  = Paragraph(
            f"{role['start']} – {role['end']}",
            ParagraphStyle("date", fontSize=9, fontName="Helvetica",
                           textColor=MUTED, alignment=TA_RIGHT)
        )
        header_table = Table(
            [[title_para, date_para]],
            colWidths=[(A4[0]-4*cm)*0.7, (A4[0]-4*cm)*0.3]
        )
        header_table.setStyle(TableStyle([
            ("VALIGN",       (0,0), (-1,-1), "BOTTOM"),
            ("LEFTPADDING",  (0,0), (-1,-1), 0),
            ("RIGHTPADDING", (0,0), (-1,-1), 0),
            ("TOPPADDING",   (0,0), (-1,-1), 0),
            ("BOTTOMPADDING",(0,0), (-1,-1), 2),
        ]))
        story.append(header_table)

        story.append(Paragraph(
            f"{role.get('location','Remote')}", s["role_meta"]
        ))

        for bullet in role["bullets"]:
            story.append(Paragraph(
                f"<bullet>&bull;</bullet> {bullet}", s["bullet"]
            ))
        story.append(Spacer(1, 6))

    # ── Projects ──────────────────────────────────────────────────────
    story.append(Paragraph("PROJECTS", s["section"]))
    story.append(section_divider())

    for project in tailored_resume.get("projects", []):
        story.append(Paragraph(project["name"], s["project_name"]))
        story.append(Paragraph(
            project.get("description", ""), s["body"]
        ))
        tech = project.get("tech", [])
        if tech:
            story.append(Paragraph(
                "Tech stack:  " + "  ·  ".join(tech), s["tech"]
            ))
        link = project.get("link", "")
        if link:
            story.append(Paragraph(f"&#128279; {link}", s["tech"]))
        story.append(Spacer(1, 4))

    # ── Education ─────────────────────────────────────────────────────
    story.append(Paragraph("EDUCATION", s["section"]))
    story.append(section_divider())

    for edu in tailored_resume.get("education", []):
        story.append(Paragraph(
            f"<b>{edu['degree']}</b>  —  "
            f"{edu['institution']}  |  {edu['year']}",
            s["body"]
        ))

    # ── Certifications ────────────────────────────────────────────────
    certs = tailored_resume.get("certifications", [])
    if certs:
        story.append(Paragraph("CERTIFICATIONS", s["section"]))
        story.append(section_divider())
        for cert in certs:
            # Fix encoding — replace problematic characters
            cert_clean = cert.replace("\u2014", "-").replace(
                "\u2013", "-"
            )
            story.append(Paragraph(
                f"<bullet>&bull;</bullet> {cert_clean}", s["cert"]
            ))

    # ── ATS keywords footer (invisible to human, visible to ATS) ──────
    keywords = target.get("keywords", [])
    if keywords:
        story.append(Spacer(1, 20))
        story.append(Paragraph(
            "  ".join(keywords),
            ParagraphStyle("ats", fontSize=1,
                           textColor=WHITE, spaceAfter=0)
        ))

    doc.build(story)
    print(f"  PDF saved: {output_path}")
    return output_path


def make_pdf_filename(job_title: str, company: str) -> str:
    clean_title   = job_title.lower().replace(" ", "_")
    clean_company = company.lower().replace(" ", "_")
    return f"data/resumes/resume_{clean_company}_{clean_title}.pdf"


# ── Test ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json

    with open("config/resume.json") as f:
        resume = json.load(f)

    tailored = {
        **resume,
        "summary": (
            "Backend Python developer with expertise in FastAPI and "
            "PostgreSQL, building scalable REST APIs and automation "
            "pipelines. Currently developing an AI job agent using "
            "LangChain, ChromaDB, and Selenium."
        ),
        "skills_ordered": [
            "Python", "FastAPI", "PostgreSQL", "Docker", "REST APIs",
            "Redis", "SQL", "Git", "LangChain", "Selenium",
            "ChromaDB", "Prompt Engineering", "JavaScript", "Flask"
        ],
        "experience": [{
            **resume["experience"][0],
            "bullets": [
                "Streamlined backend workflows via automation, "
                "cutting manual effort by 40%",
                "Built FastAPI REST APIs handling 10k+ daily "
                "requests with full test coverage",
                "Integrated third-party APIs and built data "
                "pipelines for downstream analytics"
            ]
        }],
        "projects":  resume["projects"],
        "tailored_for": {
            "job_title": "Backend Python Developer",
            "company":   "TechStartup Inc",
            "keywords":  ["Python", "FastAPI", "PostgreSQL",
                          "Docker", "REST API", "backend"]
        }
    }

    output = make_pdf_filename("Backend Python Developer", "TechStartup Inc")
    print("Generating redesigned resume PDF...\n")
    generate_pdf(tailored, output)
    print(f"\nOpen: {os.path.abspath(output)}")