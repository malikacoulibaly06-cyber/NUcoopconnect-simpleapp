"""
NU Coop Connect — Anonymous Northeastern co-op review board.
Skill-based, anonymous, free to host on Streamlit Community Cloud.
"""

import base64
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
import streamlit as st

# ---------- CONFIG ----------
BASE_DIR = Path(__file__).parent

def _find_logo() -> Path | None:
    """Find the best logo file in the project folder.

    Rules:
    - Any .png / .jpg / .jpeg / .webp / .svg in BASE_DIR is a candidate.
    - Skip obviously-tiny placeholder files (< 4 KB).
    - Prefer files whose name contains 'logo', 'coop', 'co-op',
      'husky', 'platform', 'network'.
    - Among matches, prefer the largest file (real logos are usually heftier).
    - Last resort: any image file at all.
    """
    exts = {".png", ".jpg", ".jpeg", ".webp", ".svg"}
    keywords = ("logo", "coop", "co-op", "husky", "platform", "network")
    try:
        all_imgs = [p for p in BASE_DIR.iterdir()
                    if p.is_file() and p.suffix.lower() in exts]
    except FileNotFoundError:
        return None
    if not all_imgs:
        return None

    # Filter out tiny placeholders
    substantial = [p for p in all_imgs if p.stat().st_size >= 4_000]
    pool = substantial or all_imgs

    # Prefer keyword matches
    matches = [p for p in pool if any(kw in p.stem.lower() for kw in keywords)]
    pool = matches or pool

    # Largest wins
    pool.sort(key=lambda p: p.stat().st_size, reverse=True)
    return pool[0]

LOGO_PATH = _find_logo()

def _detect_mime(path: Path) -> str:
    """Detect image MIME from magic bytes — ignores the file extension."""
    try:
        head = path.read_bytes()[:32]
    except Exception:
        return "image/png"
    if head.startswith(b"\x89PNG"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head.lstrip().startswith((b"<?xml", b"<svg")):
        return "image/svg+xml"
    return "image/png"  # safe default

# Light, refined palette — no pure black
NU_RED = "#C8102E"
NU_RED_SOFT = "#E63E55"
NU_RED_DARK = "#A00D24"
NU_RED_TINT = "#FCEEF0"   # very faint red wash for accents
INK = "#0F0F0F"          # primary text (near-black for max mobile readability)
INK_SOFT = "#2B2B2B"     # secondary text (still dark)
INK_FAINT = "#525252"    # captions (medium-dark)
SURFACE = "#FFFFFF"      # card surface (white pops against the grey page)
PAGE_BG = "#F0EFEC"      # warm light grey for whole page
PAGE_BG_2 = "#E8E6E2"    # slightly darker accent for gradient
SURFACE_2 = "#F8F8F8"    # secondary
SURFACE_3 = "#F2F2F2"    # dividers
BORDER = "#D5D3CE"       # warm border that matches page
BORDER_RED = "#F2CFD4"   # soft red border

st.set_page_config(
    page_title="NU Coop Connect",
    page_icon="N",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------- GLOBAL STYLES ----------
st.markdown(
    f"""
    <style>
      :root {{
        --red: {NU_RED};
        --ink: {INK};
        --ink-soft: {INK_SOFT};
        --surface: {SURFACE};
        --surface-2: {SURFACE_2};
        --border: {BORDER};
      }}
      .stApp {{
        background: linear-gradient(180deg, {PAGE_BG} 0%, {PAGE_BG_2} 100%);
        background-attachment: fixed;
        color: {INK};
      }}
      /* Make ALL text default to near-black so it's legible on mobile */
      .stApp, .stApp p, .stApp span, .stApp div, .stApp label,
      .stApp .stMarkdown, .stApp [data-testid="stMarkdownContainer"] {{
        color: {INK};
      }}
      /* Form labels especially crisp */
      .stApp label, .stApp .stCheckbox label, .stApp [data-baseweb="radio"] label,
      .stApp [data-baseweb="form-control-label"] {{
        color: {INK} !important;
        font-weight: 500;
      }}
      /* Captions slightly lighter but still readable */
      .stApp .stCaption, .stApp [data-testid="stCaptionContainer"] {{
        color: {INK_SOFT} !important;
      }}
      /* Red top accent strip across the whole app */
      .stApp::before {{
        content: ""; position: fixed; top: 0; left: 0; right: 0;
        height: 4px;
        background: linear-gradient(90deg, {NU_RED} 0%, {NU_RED_DARK} 50%, {NU_RED} 100%);
        z-index: 999;
      }}
      .block-container {{ padding-top: 2.5rem !important; }}
      h1, h2, h3, h4 {{ color: {INK}; font-weight: 600; letter-spacing: -0.01em; }}

      /* Hero — rich red & grey card */
      .hero {{
        position: relative;
        display: flex; align-items: center; gap: 22px;
        padding: 20px 26px 22px 32px;
        margin-bottom: 26px;
        background: linear-gradient(135deg, {SURFACE} 0%, {NU_RED_TINT} 100%);
        border: 1px solid {BORDER};
        border-radius: 14px;
        overflow: hidden;
        box-shadow: 0 4px 16px rgba(0,0,0,0.04);
      }}
      .hero::before {{
        content: "";
        position: absolute; left: 0; top: 0; bottom: 0;
        width: 6px;
        background: linear-gradient(180deg, {NU_RED} 0%, {NU_RED_DARK} 100%);
      }}
      .hero::after {{
        content: "";
        position: absolute; right: -50px; top: -50px;
        width: 220px; height: 220px;
        background: radial-gradient(circle, rgba(200, 16, 46, 0.12) 0%, transparent 70%);
        pointer-events: none;
      }}
      .hero img {{
        height: 72px; width: 72px;
        border-radius: 14px;
        background: {SURFACE_2};
        object-fit: cover;
        box-shadow: 0 2px 8px rgba(200, 16, 46, 0.12);
      }}
      .hero .title {{
        color: {INK}; margin: 0; font-size: 30px;
        font-weight: 800; letter-spacing: -0.02em;
      }}
      .hero .title .dot {{ color: {NU_RED}; }}
      .hero .subtitle {{
        color: {INK}; margin-top: 6px; font-size: 14px;
        font-weight: 500;
        display: flex; align-items: center; gap: 10px;
        flex-wrap: wrap;
      }}
      .hero .tag {{
        display: inline-block; padding: 3px 10px;
        background: {NU_RED}; color: white;
        border-radius: 4px; font-size: 11px; font-weight: 600;
        letter-spacing: 0.6px; text-transform: uppercase;
      }}

      /* Section card — white pops against page grey */
      .section {{
        position: relative;
        background: {SURFACE};
        border: 1px solid {BORDER};
        border-radius: 12px;
        padding: 22px 26px 22px 32px;
        margin-bottom: 16px;
        transition: border-color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease;
        box-shadow: 0 2px 8px rgba(0,0,0,0.03);
      }}
      .section::before {{
        content: "";
        position: absolute; left: 0; top: 0; bottom: 0;
        width: 5px;
        background: linear-gradient(180deg, {NU_RED} 0%, {NU_RED_DARK} 100%);
        border-radius: 12px 0 0 12px;
      }}
      .section:hover {{
        border-color: {NU_RED_SOFT};
        box-shadow: 0 6px 20px rgba(200, 16, 46, 0.08);
        transform: translateY(-1px);
      }}
      .section h3 {{
        margin: 0 0 4px 0; font-size: 18px; font-weight: 800;
        color: {INK};
        display: flex; align-items: center; gap: 10px;
      }}
      .section h3 .num {{
        display: inline-flex; align-items: center; justify-content: center;
        width: 26px; height: 26px;
        background: {NU_RED}; color: white;
        border-radius: 6px; font-size: 13px; font-weight: 700;
        font-variant-numeric: tabular-nums;
      }}
      .section h3 .marker {{
        color: {NU_RED}; font-size: 14px;
      }}
      .section .help {{
        color: {INK_SOFT}; font-size: 14px; margin-bottom: 16px;
        padding-left: 36px; font-weight: 500;
      }}
      .section .sublabel {{
        font-size: 13px; font-weight: 800; text-transform: uppercase;
        letter-spacing: 0.8px; color: {NU_RED}; margin: 16px 0 8px;
        display: flex; align-items: center; gap: 6px;
      }}
      .section .sublabel::before {{
        content: "▎"; color: {NU_RED}; font-size: 14px;
      }}

      /* Review card */
      .review-card {{
        position: relative;
        border: 1px solid {BORDER};
        border-left: 5px solid {NU_RED};
        padding: 20px 22px;
        margin-bottom: 14px;
        border-radius: 12px;
        background: linear-gradient(180deg, {SURFACE} 0%, {SURFACE} 88%, {NU_RED_TINT} 100%);
        box-shadow: 0 2px 10px rgba(0,0,0,0.04);
        transition: box-shadow 0.22s ease, transform 0.22s ease, border-color 0.22s ease;
      }}
      .review-card:hover {{
        box-shadow: 0 6px 20px rgba(200, 16, 46, 0.08);
        transform: translateY(-2px);
        border-color: {NU_RED_SOFT};
      }}
      .review-card .role {{
        font-size: 18px; font-weight: 800; color: {INK}; margin: 0;
      }}
      .review-card .company {{ color: {NU_RED}; font-weight: 800; }}
      .review-card .meta {{
        color: {INK_SOFT}; font-size: 13px; margin: 4px 0 14px;
        font-weight: 500;
      }}
      .review-card .meta .sep {{ color: {NU_RED}; margin: 0 6px; opacity: 0.7; }}
      .review-card .label {{
        font-size: 12px; font-weight: 800; text-transform: uppercase;
        letter-spacing: 0.7px; color: {NU_RED}; margin: 16px 0 6px;
        display: flex; align-items: center; gap: 6px;
      }}
      .review-card .label::before {{
        content: "◆"; color: {NU_RED}; font-size: 9px;
      }}
      .review-card p {{
        margin: 4px 0 8px; color: {INK}; line-height: 1.6;
        font-size: 15px; font-weight: 500;
      }}

      /* Skill bar */
      .skill-row {{
        display: flex; align-items: center; justify-content: space-between;
        padding: 6px 0; gap: 14px;
      }}
      .skill-name {{
        font-size: 14px; color: {INK}; min-width: 200px; font-weight: 600;
      }}
      .skill-name::before {{
        content: "▸"; color: {NU_RED}; margin-right: 6px; font-size: 11px;
      }}
      .skill-bar-wrap {{
        flex: 1; height: 7px; background: {SURFACE_3}; border-radius: 999px; overflow: hidden;
        position: relative;
      }}
      .skill-bar {{
        height: 100%;
        background: linear-gradient(90deg, {NU_RED} 0%, {NU_RED_SOFT} 100%);
        border-radius: 999px;
        transition: width 0.5s cubic-bezier(0.4, 0, 0.2, 1);
        box-shadow: 0 0 6px rgba(200, 16, 46, 0.25);
      }}
      .skill-score {{
        font-size: 13px; color: {INK}; min-width: 110px; text-align: right;
        font-variant-numeric: tabular-nums; font-weight: 600;
      }}

      /* Tag chips — slightly nicer with subtle markers */
      .chip {{
        display: inline-flex; align-items: center; gap: 5px;
        padding: 5px 12px; margin: 3px 4px 3px 0;
        border-radius: 6px; font-size: 13px; font-weight: 600;
        background: {SURFACE_2}; color: {INK}; border: 1px solid {BORDER};
        transition: background 0.15s ease, transform 0.1s ease;
      }}
      .chip:hover {{ transform: translateY(-1px); }}
      .chip-skill {{
        background: linear-gradient(135deg, {NU_RED} 0%, {NU_RED_DARK} 100%);
        color: white; border-color: {NU_RED_DARK};
        font-weight: 700;
        box-shadow: 0 1px 2px rgba(200, 16, 46, 0.25);
      }}
      .chip-skill::before {{ content: "◆"; font-size: 8px; opacity: 0.85; }}
      .chip-course {{
        background: {SURFACE_3}; color: {INK}; border-color: {BORDER};
      }}
      .chip-course::before {{ content: "▸"; color: {NU_RED}; font-size: 10px; }}
      .chip-club {{
        background: {SURFACE_2}; color: {INK}; border: 1px solid {INK_SOFT};
      }}
      .chip-club::before {{ content: "●"; color: {INK_SOFT}; font-size: 8px; }}
      .chip-perk {{
        background: #ECFDF5; color: #065F46; border-color: #BBF7D0;
      }}
      .chip-perk::before {{ content: "✓"; font-size: 10px; font-weight: 700; }}
      .chip-culture {{
        background: {NU_RED_TINT}; color: {NU_RED_DARK}; border-color: {BORDER_RED};
      }}
      .chip-culture::before {{ content: "◇"; font-size: 9px; }}
      .chip-meta {{
        background: #EEF2FF; color: #3730A3; border-color: #C7D2FE;
      }}
      .chip-meta::before {{ content: "▸"; font-size: 9px; }}

      /* Buttons */
      .stButton > button {{
        background: linear-gradient(135deg, {NU_RED} 0%, {NU_RED_DARK} 100%);
        color: white; border: none; font-weight: 600;
        padding: 11px 26px; border-radius: 8px;
        letter-spacing: 0.2px;
        transition: filter 0.15s ease, transform 0.08s ease, box-shadow 0.15s ease;
        box-shadow: 0 2px 6px rgba(200, 16, 46, 0.25);
      }}
      .stButton > button:hover {{
        filter: brightness(1.08);
        box-shadow: 0 4px 12px rgba(200, 16, 46, 0.35);
      }}
      .stButton > button:active {{ transform: translateY(1px); }}

      /* Sidebar — warm grey with red accent */
      section[data-testid="stSidebar"] {{
        background: linear-gradient(180deg, #EAE7E1 0%, #DEDAD3 100%);
        border-right: 2px solid {NU_RED};
      }}
      section[data-testid="stSidebar"] * {{ color: {INK} !important; }}
      section[data-testid="stSidebar"] [data-baseweb="radio"] label {{ font-weight: 500; }}
      section[data-testid="stSidebar"] [data-baseweb="radio"] label:hover {{ color: {NU_RED} !important; }}

      /* Filter bar */
      .filter-bar {{
        background: linear-gradient(135deg, {SURFACE} 0%, {NU_RED_TINT} 100%);
        padding: 16px 18px; border-radius: 10px;
        border: 1px solid {BORDER}; margin-bottom: 18px;
        border-left: 4px solid {NU_RED};
        box-shadow: 0 2px 8px rgba(0,0,0,0.03);
      }}
      hr {{ border-color: {BORDER}; }}

      /* Metric cards (Stats page) */
      [data-testid="stMetricValue"] {{
        color: {NU_RED} !important;
        font-weight: 700 !important;
      }}
      [data-testid="stMetricLabel"] {{
        color: {INK_SOFT} !important;
        font-weight: 600 !important;
        text-transform: uppercase;
        letter-spacing: 0.6px;
        font-size: 11px !important;
      }}

      /* Tighter form spacing */
      .stMultiSelect, .stTextInput, .stSelectbox, .stTextArea, .stNumberInput {{ margin-bottom: 8px; }}

      /* Hide Streamlit menu/footer for cleaner look */
      #MainMenu {{ visibility: hidden; }}
      footer {{ visibility: hidden; }}
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------- CONSTANTS ----------
NU_COLLEGES = [
    "Khoury College of Computer Sciences",
    "D'Amore-McKim School of Business",
    "College of Engineering",
    "Bouvé College of Health Sciences",
    "College of Science",
    "College of Social Sciences & Humanities",
    "College of Arts, Media & Design",
    "College of Professional Studies",
    "School of Law",
    "Other / Cross-college",
]

INDUSTRIES = [
    "Technology / Software", "Finance / Banking", "Consulting", "Healthcare / Biotech",
    "Engineering / Manufacturing", "Marketing / Advertising", "Government / Non-profit",
    "Media / Entertainment", "Education / Research", "Law / Policy", "Arts / Design",
    "Retail / E-commerce", "Energy / Utilities", "Architecture / Real Estate", "Other",
]

# Comprehensive skill catalog — covers every Northeastern college and major.
SKILL_CATEGORIES: dict[str, list[str]] = {
    "Khoury — Computer Sciences": [
        "Python", "JavaScript / TypeScript", "Java", "C / C++", "Go", "Rust",
        "Swift / iOS", "Kotlin / Android", "SQL", "NoSQL (MongoDB, Redis)",
        "React / Frontend", "Vue / Angular", "Node.js / Backend", "Django / Flask",
        "REST / GraphQL API Design", "Data Structures & Algorithms", "System Design",
        "Cloud (AWS)", "Cloud (GCP)", "Cloud (Azure)", "Docker", "Kubernetes",
        "Terraform / IaC", "Git / Version Control", "CI/CD", "DevOps", "Linux / Shell",
        "Machine Learning", "Deep Learning", "NLP", "Computer Vision",
        "AI / LLMs / Prompt Engineering", "RAG / Vector DBs",
        "Cybersecurity", "Penetration Testing", "Cryptography",
        "Database Design", "Distributed Systems", "Networking", "Testing / QA",
        "Accessibility (a11y)", "Game Dev (Unity / Unreal)",
    ],
    "D'Amore-McKim — Business": [
        "Excel (Advanced)", "Excel Macros / VBA", "PowerPoint / Pitch Decks",
        "Financial Modeling", "Valuation / DCF", "M&A Analysis", "LBO Modeling",
        "Accounting (GAAP)", "Auditing", "Tax Preparation",
        "Bloomberg Terminal", "FactSet / Capital IQ",
        "Tableau", "Power BI", "Looker", "Google Analytics",
        "Marketing Strategy", "Brand Management", "Content Marketing",
        "SEO / SEM", "Social Media Marketing",
        "Salesforce / CRM", "HubSpot",
        "Operations / Supply Chain", "Six Sigma / Lean",
        "Project Management", "Agile / Scrum", "Jira / Asana",
        "Business Development", "B2B / B2C Sales", "Customer Success",
        "Negotiation", "Stakeholder Management",
        "Investment / Equity Research", "Fixed Income / FX",
        "Entrepreneurship / Founding", "Investor Pitching",
        "International Business", "Cross-cultural Management",
    ],
    "College of Engineering": [
        "SolidWorks", "AutoCAD", "CATIA", "Fusion 360", "Revit", "Inventor",
        "MATLAB", "Simulink", "LabVIEW",
        "Circuit Design", "PCB Design (Altium / Eagle / KiCad)", "VHDL / Verilog",
        "Embedded Systems (Arduino / RPi)", "Microcontroller Firmware",
        "FEA / Finite Element Analysis", "CFD", "ANSYS", "Abaqus",
        "Robotics / ROS", "Motion Planning", "Sensor Integration",
        "CNC / 3D Printing / Prototyping", "Lean Manufacturing",
        "Chemical Engineering (Aspen)", "Process Design",
        "Mechanical Design", "Thermodynamics", "Materials Science",
        "Civil / Structural Analysis", "Geotechnical Engineering",
        "Environmental Engineering", "Water Resources", "GIS Mapping",
        "Industrial Engineering", "Simulation Modeling (Arena / AnyLogic)",
        "Bioengineering", "Medical Device Design",
        "HVAC / Building Systems", "Power Systems", "Control Systems",
    ],
    "Bouvé — Health Sciences": [
        "Patient Care / Assessment", "Vital Signs", "IV Insertion / Phlebotomy",
        "Medication Administration", "Nursing Process / Care Plans", "Triage",
        "EHR — Epic", "EHR — Cerner", "EHR — Other",
        "Pharmacy Compounding", "Prescription Verification",
        "Pharmacology Calculations", "Drug Interaction Review",
        "Patient Counseling", "Health Education",
        "Physical Therapy — Manual", "Gait / Movement Analysis",
        "Therapeutic Exercise Programming", "Modalities (ultrasound, e-stim)",
        "Speech-Language Therapy", "Swallowing Assessment", "Articulation Therapy",
        "Behavioral Therapy (CBT / ABA)", "Clinical Interviewing",
        "Counseling Techniques", "Psychological Assessment Tools",
        "Public Health Methods", "Epidemiology", "Biostatistics",
        "Health Data Analytics", "SPSS / SAS for Health",
        "Medical Coding (ICD-10, CPT)", "Health Information Management",
        "HIPAA Compliance",
        "Behavioral Neuroscience Lab Methods", "EEG / fMRI Analysis",
    ],
    "College of Science": [
        "Wet-lab Techniques (PCR, gels, blots)", "Cell Culture", "Microscopy",
        "Specimen Preparation",
        "Bioinformatics (BLAST, Biopython)", "Genomic Data Analysis",
        "Chemistry Lab Methods (NMR, HPLC, MS, GC)", "Organic Synthesis",
        "Analytical Chemistry",
        "Physics Modeling", "Computational Physics", "Quantum Computing",
        "Numerical Methods / Math Modeling", "Proof Writing",
        "Statistics — R / RStudio", "Statistics — SPSS / SAS / Stata",
        "Field Research / Ecology Sampling", "Marine Specimen Handling",
        "Environmental Sampling (water, soil, air)", "GIS / Remote Sensing",
        "Linguistics (corpus, phonetics, syntax)",
        "Scientific Writing", "Peer Review", "Grant Writing",
    ],
    "College of Social Sciences & Humanities": [
        "Qualitative Research (interviews, ethnography)",
        "Quantitative Research / Survey Design",
        "Policy Analysis", "Government Relations / Lobbying",
        "Econometrics", "Economic Modeling", "Stata for Econ",
        "Political Science Research", "International Relations",
        "Psychology Research", "Psychometrics",
        "Sociology / Demographic Analysis",
        "Criminology / Forensic Analysis", "Criminal Investigation Methods",
        "Historical / Archival Research",
        "Philosophy / Ethical Analysis",
        "Investigative Journalism", "AP Style Writing", "Fact-checking",
        "Editorial Writing / Copyediting",
        "Translation (Spanish)", "Translation (French)",
        "Translation (Mandarin)", "Translation (Arabic)",
        "Translation (Other Languages)",
        "Cross-cultural Communication / Diplomacy",
        "Advocacy / Community Organizing", "Non-profit Management",
        "Cultural Anthropology Methods",
        "Critical Race / Africana Studies Analysis",
        "Religious / Theological Analysis",
    ],
    "Arts, Media & Design (CAMD)": [
        "Figma", "Sketch", "Adobe XD", "UI / UX Design",
        "UX Research", "User Interviews", "Usability Testing",
        "Adobe Photoshop", "Adobe Illustrator", "Adobe InDesign",
        "Adobe Premiere", "After Effects / Motion", "DaVinci Resolve",
        "Blender", "Maya", "3D Modeling / Animation",
        "Photography (studio, photojournalism, product)",
        "Video Production / Cinematography", "Sound Design / Audio Engineering",
        "Music Production (Logic, Pro Tools, Ableton)", "Composition",
        "Music Performance", "Music Theory",
        "Theatre — Stage Management", "Theatre — Dramaturgy",
        "Theatre — Directing", "Acting",
        "Costume / Set / Lighting Design",
        "Architecture — Revit", "Architecture — Rhino", "Architecture — SketchUp",
        "Architectural Visualization / Rendering", "Model-making",
        "Game Design", "Level Design", "Game Writing",
        "Graphic Design / Brand Identity", "Typography",
        "Copywriting", "Content Strategy",
        "Journalism / Multimedia Storytelling", "Broadcast Journalism",
        "Public Relations / Communication Strategy",
        "Studio Art / Drawing / Painting", "Sculpture",
        "Fashion / Textile Design",
    ],
    "Cross-functional / Soft Skills": [
        "Written Communication", "Verbal Communication",
        "Presentation Skills", "Public Speaking",
        "Client / Customer Relations", "Stakeholder Management",
        "Cross-team Collaboration", "Remote Team Collaboration",
        "Leadership", "Team Management", "Mentorship / Coaching",
        "Project Management", "Agile / Scrum (general)",
        "Time Management", "Prioritization", "Self-direction",
        "Critical Thinking", "Problem-solving", "Decision-making",
        "Conflict Resolution", "Negotiation (general)",
        "Active Listening", "Empathy",
        "Adaptability", "Learning Agility",
        "Technical Writing / Documentation",
        "Teaching / Training",
        "DEI / Cultural Competency",
        "Data Storytelling",
    ],
}

LEVEL_OPTIONS = ["N/A", "Beginner", "Adv. Beginner", "Intermediate", "Advanced", "Expert"]
LEVEL_TO_NUM = {"N/A": 0, "Beginner": 1, "Adv. Beginner": 2, "Intermediate": 3, "Advanced": 4, "Expert": 5}
LEVEL_HELP = (
    "Beginner = first exposure · Adv. Beginner = used a few times · "
    "Intermediate = comfortable independently · Advanced = could lead a project · "
    "Expert = could teach it"
)

RIASEC = [
    ("R - Realistic", "Hands-on, technical work"),
    ("I - Investigative", "Research, analysis"),
    ("A - Artistic", "Creative, expressive"),
    ("S - Social", "Helping, teaching people"),
    ("E - Enterprising", "Leading, persuading"),
    ("C - Conventional", "Organizing, structured"),
]

PERKS_LIST = [
    "Paid co-op (hourly or salary)", "Paid holidays",
    "Health insurance", "Dental / vision insurance",
    "401(k) / retirement match", "Relocation stipend",
    "Housing stipend", "Commuter / transit benefits",
    "Free meals or snacks", "Gym / wellness benefits",
    "Hybrid / remote flexibility", "Equipment provided",
    "Stock / equity", "Sign-on bonus", "Performance bonus",
]

CULTURE_TAGS = [
    "Company outings / team events", "Coffee chat culture",
    "High Northeastern alumni density", "Strong mentorship program",
    "Active intern / co-op cohort", "Inclusive environment",
    "Flexible hours", "Work-life balance",
    "Fast-paced / startup energy", "Structured / corporate environment",
    "Open to co-op ideas", "Frequent feedback / 1:1s",
]

COURSES = [
    "CS2500 Fundamentals of CS 1", "CS2510 Fundamentals of CS 2",
    "CS3500 OO Design", "CS3700 Networks", "CS3200 Databases",
    "CS4100 AI", "CS4800 Software Engineering",
    "DS2000 Programming with Data", "DS3000 Foundations of Data Science",
    "DS4400 Machine Learning", "MATH2331 Linear Algebra",
    "FINA2201 Financial Management", "ACCT1201 Financial Accounting",
    "MKTG2201 Intro to Marketing", "MGMT2206 Innovation",
    "EECE2150 Circuits", "ME2350 Statics", "ENGW1111 First-Year Writing",
    "Other / Not listed",
]

# ---------- DB (Supabase Postgres) ----------
def _get_db_url() -> str:
    """Find the Postgres URL in Streamlit secrets under any common key."""
    # 1. Recommended layout: [connections.supabase] url = "..."
    try:
        return st.secrets["connections"]["supabase"]["url"]
    except Exception:
        pass
    # 2. Bare [supabase] url = "..."
    try:
        return st.secrets["supabase"]["url"]
    except Exception:
        pass
    # 3. Common bare keys
    for key in ("DATABASE_URL", "postgres_url", "POSTGRES_URL", "SUPABASE_URL"):
        try:
            v = st.secrets[key]
            if isinstance(v, str) and v.startswith("postgres"):
                return v
        except Exception:
            continue
    return ""

@st.cache_resource(show_spinner=False)
def _get_pool() -> ConnectionPool:
    url = _get_db_url()
    if not url:
        raise RuntimeError(
            "No Supabase connection string found. In your Streamlit app's "
            "Settings → Secrets, add:\n\n"
            '[connections.supabase]\n'
            'url = "postgresql://postgres.xxxxx:PASSWORD@aws-0-region.pooler.supabase.com:6543/postgres"'
        )
    return ConnectionPool(
        conninfo=url,
        min_size=1, max_size=5,
        kwargs={"row_factory": dict_row, "autocommit": True},
        open=True,
    )

def get_conn():
    """Borrow a connection from the pool. Use as a context manager."""
    return _get_pool().connection()

def init_db():
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reviews (
                id SERIAL PRIMARY KEY,
                created_at TEXT NOT NULL,
                company TEXT NOT NULL,
                role TEXT NOT NULL,
                industry TEXT NOT NULL,
                semester TEXT,
                rating INTEGER,
                skills TEXT,
                courses TEXT,
                clubs TEXT,
                prior_experience TEXT,
                what_you_did TEXT NOT NULL,
                what_you_learned TEXT NOT NULL,
                advice TEXT
            )
            """
        )
        # Add new columns if missing (idempotent migration)
        new_cols = {
            "college": "TEXT",
            "skill_ratings": "TEXT",
            "interest_alignment": "TEXT",
            "custom_skills": "TEXT",
            "interview_rounds": "INTEGER",
            "technical_interviews": "INTEGER",
            "recruiter_style": "TEXT",
            "interview_notes": "TEXT",
            "perks": "TEXT",
            "culture_tags": "TEXT",
            "coop_count": "INTEGER",
            "return_offer": "TEXT",
        }
        for col, type_ in new_cols.items():
            conn.execute(f"ALTER TABLE reviews ADD COLUMN IF NOT EXISTS {col} {type_}")

# Run schema setup, with a friendly UI error if Supabase isn't reachable
try:
    init_db()
except Exception as _db_err:
    st.error("Couldn't connect to the database.")
    st.code(str(_db_err), language="text")
    st.info(
        "On Streamlit Cloud: open your app → Settings → Secrets and add your "
        "Supabase connection string. Format:\n\n"
        '[connections.supabase]\nurl = "postgresql://postgres.xxxxx:PASSWORD@aws-0-..."\n\n'
        "Use the **Transaction pooler** URL (port 6543) from Supabase → Connect → URI."
    )
    st.stop()

# ---------- FILTER ----------
BANNED_WORDS = {
    "fuck", "shit", "bitch", "asshole", "dumbass", "idiot", "moron", "retard",
    "stupid", "loser", "trash", "garbage", "sucks", "worst", "hate",
}

def is_constructive(*texts: str) -> tuple[bool, str]:
    combined = " ".join(t for t in texts if t).strip()
    if len(combined) < 80:
        return False, "Your review is too short — please write at least a few sentences (80+ characters total)."
    lowered = combined.lower()
    hits = [w for w in BANNED_WORDS if re.search(rf"\b{re.escape(w)}\b", lowered)]
    if hits:
        return False, (
            f"Your review uses language that doesn't feel constructive (e.g. '{hits[0]}'). "
            "Please reframe with specific, helpful feedback instead."
        )
    letters = [c for c in combined if c.isalpha()]
    if letters and sum(1 for c in letters if c.isupper()) / len(letters) > 0.6:
        return False, "Please avoid writing in all caps — it reads as shouting."
    if len(combined.split()) < 20:
        return False, "Please add more detail — at least 20 words across your responses."
    return True, ""

# ---------- HERO ----------
def render_hero():
    logo_html = ""
    if LOGO_PATH is not None and LOGO_PATH.exists():
        mime = _detect_mime(LOGO_PATH)
        b64 = base64.b64encode(LOGO_PATH.read_bytes()).decode()
        logo_html = f'<img src="data:{mime};base64,{b64}" alt="NU Coop Connect"/>'
    st.markdown(
        f"""
        <div class="hero">
          {logo_html}
          <div>
            <div class="title">NU Coop Connect<span class="dot"> ●</span></div>
            <div class="subtitle">
              <span class="tag">Anonymous</span>
              <span>Skill-based co-op reviews — by Huskies, for Huskies.</span>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

render_hero()

# ---------- SIDEBAR ----------
st.sidebar.markdown(
    f"<div style='padding:10px 0 8px; font-weight:700; color:{INK};'>NU Coop Connect</div>"
    f"<hr style='border-color:{BORDER}; margin: 0 0 14px;'>",
    unsafe_allow_html=True,
)
page = st.sidebar.radio(
    "Navigate",
    ["Browse reviews", "Submit a review", "Stats", "About"],
    label_visibility="collapsed",
)

# ---------- HELPERS ----------
def chip(text: str, kind: str = "") -> str:
    cls = f"chip {kind}".strip()
    return f'<span class="{cls}">{text}</span>'

def skill_bar_html(name: str, score: int, label: str | None = None) -> str:
    width = max(0, min(100, int(score) * 20))
    label_text = label or f"{score}/5"
    return (
        f'<div class="skill-row">'
        f'  <div class="skill-name">{name}</div>'
        f'  <div class="skill-bar-wrap"><div class="skill-bar" style="width:{width}%"></div></div>'
        f'  <div class="skill-score">{label_text}</div>'
        f'</div>'
    )

def safe_json(s):
    if not s:
        return {}
    try:
        return json.loads(s)
    except Exception:
        return {}

def has_col(row, col: str) -> bool:
    # row is a dict (psycopg dict_row) — `in row` checks keys
    try:
        return col in row
    except Exception:
        return False

NUM_TO_LEVEL = {v: k for k, v in LEVEL_TO_NUM.items()}

def render_review_card(row: dict):
    skill_ratings = safe_json(row["skill_ratings"]) if has_col(row, "skill_ratings") else {}
    if isinstance(skill_ratings, dict):
        skill_ratings = {k: int(v) for k, v in skill_ratings.items() if v and int(v) > 0}
    else:
        skill_ratings = {}
    top_skills = sorted(skill_ratings.items(), key=lambda kv: -kv[1])
    skills_bars = "".join(
        skill_bar_html(k, v, f"{NUM_TO_LEVEL.get(v, '')} ({v}/5)")
        for k, v in top_skills
    )

    skills_legacy = ""
    if row["skills"] and not skill_ratings:
        skills_legacy = "".join(
            chip(s.strip(), "chip-skill")
            for s in (row["skills"] or "").split(",") if s.strip()
        )

    custom_chips = ""
    if has_col(row, "custom_skills") and row["custom_skills"]:
        custom_chips = "".join(
            chip(s.strip(), "chip-skill")
            for s in row["custom_skills"].split(",") if s.strip()
        )

    courses_html = "".join(
        chip(c.strip(), "chip-course")
        for c in (row["courses"] or "").split(",") if c.strip()
    )
    clubs_html = "".join(
        chip(c.strip(), "chip-club")
        for c in (row["clubs"] or "").split(",") if c.strip()
    )
    prior = (
        chip(f"Prior — {row['prior_experience']}", "chip-culture")
        if row["prior_experience"] else ""
    )

    interview_bits = []
    if has_col(row, "interview_rounds") and row["interview_rounds"]:
        interview_bits.append(f"{row['interview_rounds']} rounds")
    if has_col(row, "technical_interviews") and row["technical_interviews"]:
        interview_bits.append(f"{row['technical_interviews']} technical")
    if has_col(row, "return_offer") and row["return_offer"]:
        interview_bits.append(f"Return offer: {row['return_offer']}")
    if has_col(row, "coop_count") and row["coop_count"]:
        interview_bits.append(f"{row['coop_count']} co-ops at company")
    interview_html = " · ".join(interview_bits)

    perks = safe_json(row["perks"]) if has_col(row, "perks") else []
    culture = safe_json(row["culture_tags"]) if has_col(row, "culture_tags") else []
    if not isinstance(perks, list): perks = []
    if not isinstance(culture, list): culture = []
    perks_html = "".join(chip(p, "chip-perk") for p in perks)
    culture_html = "".join(chip(c, "chip-culture") for c in culture)

    interest = safe_json(row["interest_alignment"]) if has_col(row, "interest_alignment") else {}
    if not isinstance(interest, dict): interest = {}
    interest_bars = "".join(
        skill_bar_html(k, int(v), f"{int(v)}/5") for k, v in interest.items() if v
    )

    college_chip = chip(row['college'], "chip-meta") if has_col(row, "college") and row["college"] else ""

    advice_block = (
        f'<div class="label">Advice for future co-ops</div><p>{row["advice"]}</p>'
        if row["advice"] else ""
    )
    prep_chips = courses_html + clubs_html + prior
    prep_block = (
        f'<div class="label">What prepared me</div><div>{prep_chips}</div>'
        if prep_chips else ""
    )

    recruiter_block = (
        f'<div class="label">Recruiter / interview style</div><p>{row["recruiter_style"]}</p>'
        if has_col(row, "recruiter_style") and row["recruiter_style"] else ""
    )
    interview_notes_block = (
        f'<div class="label">Interview notes</div><p>{row["interview_notes"]}</p>'
        if has_col(row, "interview_notes") and row["interview_notes"] else ""
    )

    st.markdown(
        f"""
        <div class="review-card">
          <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:12px;">
            <div>
              <p class="role">{row["role"]} <span style="color:{INK_FAINT}; font-weight:400;">at</span> <span class="company">{row["company"]}</span></p>
              <p class="meta">{row["industry"]}<span class="sep">◆</span>{row["semester"] or "Semester N/A"}<span class="sep">◆</span>Posted {row["created_at"][:10]}</p>
              {('<div style="margin: 6px 0;">' + college_chip + '</div>') if college_chip else ''}
            </div>
          </div>

          {('<div class="label">Skills earned</div>' + skills_bars) if skills_bars else ''}
          {('<div class="label">Skills</div><div>' + skills_legacy + '</div>') if skills_legacy else ''}
          {('<div class="label">Other skills mentioned</div><div>' + custom_chips + '</div>') if custom_chips else ''}

          {('<div class="label">Interest alignment (Holland Code)</div>' + interest_bars) if interest_bars else ''}

          <div class="label">What I did</div>
          <p>{row["what_you_did"]}</p>

          <div class="label">What I learned</div>
          <p>{row["what_you_learned"]}</p>

          {recruiter_block}
          {interview_notes_block}
          {('<div class="label">Interview / hiring</div><p>' + interview_html + '</p>') if interview_html else ''}

          {('<div class="label">Perks & compensation</div><div>' + perks_html + '</div>') if perks_html else ''}
          {('<div class="label">Culture</div><div>' + culture_html + '</div>') if culture_html else ''}

          {advice_block}
          {prep_block}
        </div>
        """,
        unsafe_allow_html=True,
    )

# ================ BROWSE ================
if page == "Browse reviews":
    st.subheader("Browse co-op reviews")

    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM reviews ORDER BY created_at DESC").fetchall()
    rows = list(rows)

    if not rows:
        st.info("No reviews yet — be the first to share your co-op.")
    else:
        industries_available = sorted({r["industry"] for r in rows})
        all_skills_set = set()
        for r in rows:
            for s in (r["skills"] or "").split(","):
                s = s.strip()
                if s:
                    all_skills_set.add(s)
            sr = safe_json(r["skill_ratings"]) if has_col(r, "skill_ratings") else {}
            if isinstance(sr, dict):
                for k, v in sr.items():
                    if v and int(v) > 0:
                        all_skills_set.add(k)
        all_skills = sorted(all_skills_set)

        st.markdown('<div class="filter-bar">', unsafe_allow_html=True)
        c1, c2, c3, c4 = st.columns([1.2, 1.2, 1.4, 1.2])
        with c1:
            ind_filter = st.multiselect("Industry", industries_available)
        with c2:
            role_filter = st.text_input("Role contains", "", placeholder="e.g. data, SWE")
        with c3:
            skill_filter = st.multiselect("Skills earned", all_skills)
        with c4:
            college_filter = st.multiselect("College", NU_COLLEGES)
        st.markdown('</div>', unsafe_allow_html=True)

        def keep(r):
            if ind_filter and r["industry"] not in ind_filter:
                return False
            if role_filter and role_filter.lower() not in (r["role"] or "").lower():
                return False
            if college_filter and (r["college"] if has_col(r, "college") else None) not in college_filter:
                return False
            if skill_filter:
                row_skills = {s.strip() for s in (r["skills"] or "").split(",") if s.strip()}
                sr = safe_json(r["skill_ratings"]) if has_col(r, "skill_ratings") else {}
                if isinstance(sr, dict):
                    row_skills.update(k for k, v in sr.items() if v and int(v) > 0)
                if not all(sk in row_skills for sk in skill_filter):
                    return False
            return True

        filtered = [r for r in rows if keep(r)]
        st.caption(f"Showing **{len(filtered)}** of {len(rows)} reviews")
        if not filtered:
            st.warning("No reviews match those filters. Try loosening them.")
        for row in filtered:
            render_review_card(row)

# ================ SUBMIT ================
elif page == "Submit a review":
    st.subheader("Share your co-op")
    st.caption(
        "100% anonymous — no name, email, or NUID is stored. "
        "Takes about 3–5 minutes."
    )

    # ---------- SECTION 1: BASICS ----------
    st.markdown('<div class="section">', unsafe_allow_html=True)
    st.markdown(
        f'<h3><span class="num">1</span> Co-op basics</h3>'
        f'<div class="help">The company, your role, and which Northeastern college you\'re in.</div>',
        unsafe_allow_html=True,
    )
    c1, c2 = st.columns(2)
    with c1:
        company = st.text_input("Company *", placeholder="e.g. Wayfair, Liberty Mutual")
        industry = st.selectbox("Industry *", INDUSTRIES, index=0)
        my_colleges = st.multiselect(
            "Your Northeastern college(s) *",
            NU_COLLEGES,
            help="Pick all that apply if you're cross-college.",
        )
    with c2:
        role = st.text_input("Co-op role / title *", placeholder="e.g. Software Engineer Co-op")
        semester = st.selectbox(
            "Co-op semester",
            ["", "Spring 2024", "Summer 2024", "Fall 2024",
             "Spring 2025", "Summer 2025", "Fall 2025",
             "Spring 2026", "Summer 2026", "Fall 2026", "Other"],
        )
        coop_count = st.number_input(
            "How many co-ops did the company have? (best guess)",
            min_value=0, max_value=200, value=0, step=1,
        )
    st.markdown('</div>', unsafe_allow_html=True)

    # ---------- SECTION 2: SKILLS (dynamic) ----------
    st.markdown('<div class="section">', unsafe_allow_html=True)
    st.markdown(
        f'<h3><span class="num">2</span> Skills you used on this co-op</h3>'
        f'<div class="help">Filter the list by college, check the skills you used, then rate each one. '
        f'<em>{LEVEL_HELP}</em></div>',
        unsafe_allow_html=True,
    )

    # Default skill colleges = whatever the student picked in step 1; fallback to common ones
    if my_colleges:
        default_skill_cats = []
        match_map = {
            "Khoury College of Computer Sciences": "Khoury — Computer Sciences",
            "D'Amore-McKim School of Business": "D'Amore-McKim — Business",
            "College of Engineering": "College of Engineering",
            "Bouvé College of Health Sciences": "Bouvé — Health Sciences",
            "College of Science": "College of Science",
            "College of Social Sciences & Humanities": "College of Social Sciences & Humanities",
            "College of Arts, Media & Design": "Arts, Media & Design (CAMD)",
        }
        for c in my_colleges:
            cat = match_map.get(c)
            if cat:
                default_skill_cats.append(cat)
        default_skill_cats.append("Cross-functional / Soft Skills")
        default_skill_cats = list(dict.fromkeys(default_skill_cats))  # unique, preserve order
    else:
        default_skill_cats = ["Cross-functional / Soft Skills"]

    skill_categories_shown = st.multiselect(
        "Show skills from these colleges / categories",
        list(SKILL_CATEGORIES.keys()),
        default=default_skill_cats,
        help="Pick the colleges relevant to your role — soft skills are always available below.",
    )

    # Render checkboxes (3-col grid) per shown category.
    # Key is scoped to (category, skill) so the same skill appearing in
    # multiple categories doesn't collide. We dedupe afterwards.
    checked_skills_raw: list[str] = []
    for cat in skill_categories_shown:
        st.markdown(
            f"<div style='font-size:13px; font-weight:600; color:{INK}; margin: 14px 0 6px;'>{cat}</div>",
            unsafe_allow_html=True,
        )
        skills = SKILL_CATEGORIES[cat]
        cols = st.columns(3)
        for i, sk in enumerate(skills):
            with cols[i % 3]:
                # category prefix prevents duplicate-key crashes
                key = f"chk__{cat[:20]}__{sk}"
                if st.checkbox(sk, key=key):
                    checked_skills_raw.append(sk)
    # dedupe while preserving order
    checked_skills = list(dict.fromkeys(checked_skills_raw))

    # Sliders only for checked skills (this is the dynamic part)
    skill_ratings: dict[str, int] = {}
    if checked_skills:
        st.markdown(
            f"<div style='margin: 18px 0 4px; font-weight:600;'>"
            f"Rate the {len(checked_skills)} skill{'s' if len(checked_skills) != 1 else ''} you picked</div>"
            f"<div style='color:{INK_SOFT}; font-size:12px; margin-bottom:8px;'>"
            f"Use the labeled scale. Slide to <b>N/A</b> if you change your mind.</div>",
            unsafe_allow_html=True,
        )
        for sk in checked_skills:
            lvl = st.select_slider(
                sk,
                options=LEVEL_OPTIONS,
                value="Intermediate",
                key=f"lvl__{sk}",
            )
            skill_ratings[sk] = LEVEL_TO_NUM[lvl]
    else:
        st.caption("Check skills above and sliders will appear here.")

    custom_skills = st.text_input(
        "Other skills not listed (comma-separated)",
        placeholder="e.g. Salesforce, Adobe XD, ROS",
        key="custom_skills_input",
    )
    st.markdown('</div>', unsafe_allow_html=True)

    # ---------- SECTION 3: INTERVIEW ----------
    st.markdown('<div class="section">', unsafe_allow_html=True)
    st.markdown(
        f'<h3><span class="num">3</span> Interview process</h3>'
        f'<div class="help">Help future applicants know what to expect.</div>',
        unsafe_allow_html=True,
    )
    c1, c2 = st.columns(2)
    with c1:
        interview_rounds = st.number_input(
            "Total rounds (including behavioral)",
            min_value=0, max_value=15, value=0, step=1,
        )
    with c2:
        technical_interviews = st.number_input(
            "Of those, how many were technical?",
            min_value=0, max_value=15, value=0, step=1,
        )
    recruiter_style = st.text_area(
        "Recruiter style / vibe",
        placeholder="e.g. responsive, friendly, ghosted for 3 weeks, very formal",
        height=70,
    )
    interview_notes = st.text_area(
        "Interview format & topics (optional)",
        placeholder="e.g. 1 HR phone screen, 2 coding rounds (LeetCode medium), system design, behavioral",
        height=80,
    )
    st.markdown('</div>', unsafe_allow_html=True)

    # ---------- SECTION 4: PERKS + CULTURE ----------
    st.markdown('<div class="section">', unsafe_allow_html=True)
    st.markdown(
        f'<h3><span class="num">4</span> Compensation, perks & culture</h3>'
        f'<div class="help">Check anything that applied. Skip what didn\'t.</div>',
        unsafe_allow_html=True,
    )
    st.markdown('<div class="sublabel">Perks & compensation</div>', unsafe_allow_html=True)
    perks: list[str] = []
    for i in range(0, len(PERKS_LIST), 3):
        cc = st.columns(3)
        for j, c in enumerate(cc):
            if i + j < len(PERKS_LIST):
                p = PERKS_LIST[i + j]
                with c:
                    if st.checkbox(p, key=f"perk__{p}"):
                        perks.append(p)

    st.markdown('<div class="sublabel">Culture & connections</div>', unsafe_allow_html=True)
    culture_tags: list[str] = []
    for i in range(0, len(CULTURE_TAGS), 3):
        cc = st.columns(3)
        for j, c in enumerate(cc):
            if i + j < len(CULTURE_TAGS):
                t = CULTURE_TAGS[i + j]
                with c:
                    if st.checkbox(t, key=f"culture__{t}"):
                        culture_tags.append(t)

    return_offer = st.selectbox(
        "Did you get / expect a return offer?",
        ["Prefer not to say", "Yes — got one", "Yes — pending", "No", "Unsure"],
    )
    st.markdown('</div>', unsafe_allow_html=True)

    # ---------- SECTION 5: EXPERIENCE ----------
    st.markdown('<div class="section">', unsafe_allow_html=True)
    st.markdown(
        f'<h3><span class="num">5</span> Your experience</h3>'
        f'<div class="help">Short, specific, helpful. Profanity / all-caps will be auto-rejected.</div>',
        unsafe_allow_html=True,
    )
    what_you_did = st.text_area(
        "What did you do day-to-day? *",
        height=110,
        placeholder="Describe your projects, tools, team size, typical week.",
    )
    what_you_learned = st.text_area(
        "What did you learn? *",
        height=110,
        placeholder="Technical skills, soft skills, how the industry actually works.",
    )
    advice = st.text_area(
        "Advice for future co-ops (optional)",
        height=80,
        placeholder="What would you tell yourself before starting?",
    )
    st.markdown('</div>', unsafe_allow_html=True)

    # ---------- SECTION 6: WHAT PREPARED YOU + OPTIONAL RIASEC ----------
    st.markdown('<div class="section">', unsafe_allow_html=True)
    st.markdown(
        f'<h3><span class="num">6</span> What prepared you (optional)</h3>'
        f'<div class="help">Help juniors pick the right courses and clubs.</div>',
        unsafe_allow_html=True,
    )
    courses = st.multiselect("Courses that helped", COURSES)
    custom_courses = st.text_input(
        "Other courses (comma-separated)",
        placeholder="e.g. PHIL1145, BIOL2299",
    )
    clubs = st.text_input(
        "Clubs / organizations (comma-separated)",
        placeholder="e.g. NU Blueprint, Oasis, Sandbox",
    )
    prior_experience = st.text_input(
        "Prior experience",
        placeholder="e.g. previous co-op as data analyst, summer research",
    )

    with st.expander("Optional: How well did this match your interests? (Holland Code)"):
        st.caption("Rate fit, 0 = N/A, 5 = perfect fit.")
        interest_alignment: dict[str, int] = {}
        for i in range(0, len(RIASEC), 2):
            cc1, cc2 = st.columns(2)
            with cc1:
                code, desc = RIASEC[i]
                interest_alignment[code] = st.slider(
                    f"{code}", 0, 5, 0, key=f"riasec_{code}", help=desc,
                )
            if i + 1 < len(RIASEC):
                with cc2:
                    code, desc = RIASEC[i + 1]
                    interest_alignment[code] = st.slider(
                        f"{code}", 0, 5, 0, key=f"riasec_{code}", help=desc,
                    )
    st.markdown('</div>', unsafe_allow_html=True)

    # ---------- CONFIRMATION + SUBMIT ----------
    st.markdown('<div class="section" style="background:#FFFBEA; border-color:#F5E6A8;">', unsafe_allow_html=True)
    agree_rules = st.checkbox(
        "I confirm this review is honest, anonymous, and constructive — no names, NUIDs, or insults."
    )
    agree_confidential = st.checkbox(
        "I confirm I'm not sharing protected company-confidential info."
    )
    st.markdown('</div>', unsafe_allow_html=True)

    submitted = st.button("Submit review")

    if submitted:
        missing = [n for n, v in [
            ("Company", company), ("Role", role), ("Industry", industry),
            ("What you did", what_you_did), ("What you learned", what_you_learned),
        ] if not (v or "").strip()]
        if not my_colleges:
            missing.append("College(s)")
        if missing:
            st.error(f"Please fill in: {', '.join(missing)}")
        elif not agree_rules or not agree_confidential:
            st.error("Please check both confirmation boxes above.")
        else:
            rated_skills = {k: v for k, v in skill_ratings.items() if v > 0}
            if not rated_skills and not custom_skills.strip():
                st.error("Please check at least one skill (or add a custom one).")
            else:
                ok, reason = is_constructive(
                    what_you_did, what_you_learned, advice, recruiter_style, interview_notes,
                )
                if not ok:
                    st.error(f"Review not posted — {reason}")
                else:
                    all_courses = ", ".join(
                        [*[c for c in courses if c != "Other / Not listed"],
                         *[c.strip() for c in custom_courses.split(",") if c.strip()]]
                    )
                    skills_flat = ", ".join(rated_skills.keys())
                    college_value = " · ".join(my_colleges)
                    with get_conn() as conn:
                        conn.execute(
                            """INSERT INTO reviews
                               (created_at, company, role, industry, semester,
                                college, skill_ratings, custom_skills, interest_alignment,
                                interview_rounds, technical_interviews, recruiter_style, interview_notes,
                                perks, culture_tags, coop_count, return_offer,
                                skills, courses, clubs, prior_experience,
                                what_you_did, what_you_learned, advice)
                               VALUES (%s,%s,%s,%s,%s, %s,%s,%s,%s, %s,%s,%s,%s, %s,%s,%s,%s, %s,%s,%s,%s, %s,%s,%s)""",
                            (
                                datetime.utcnow().isoformat(),
                                company.strip(), role.strip(), industry, semester,
                                college_value,
                                json.dumps(rated_skills),
                                custom_skills.strip(),
                                json.dumps({k: v for k, v in interest_alignment.items() if v > 0}),
                                int(interview_rounds) if interview_rounds else None,
                                int(technical_interviews) if technical_interviews else None,
                                recruiter_style.strip(),
                                interview_notes.strip(),
                                json.dumps(perks),
                                json.dumps(culture_tags),
                                int(coop_count) if coop_count else None,
                                return_offer if return_offer != "Prefer not to say" else None,
                                skills_flat,
                                all_courses,
                                clubs.strip(),
                                prior_experience.strip(),
                                what_you_did.strip(),
                                what_you_learned.strip(),
                                advice.strip(),
                            ),
                        )
                    st.success("Thanks — your review is live on the Browse page.")

# ================ STATS ================
elif page == "Stats":
    st.subheader("Community stats")
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM reviews").fetchall()
    rows = list(rows)
    if not rows:
        st.info("Stats will appear once reviews are posted.")
    else:
        total = len(rows)
        unique_companies = len({r["company"] for r in rows})
        c1, c2, c3 = st.columns(3)
        c1.metric("Total reviews", total)
        c2.metric("Unique companies", unique_companies)
        c3.metric("Industries covered", len({r["industry"] for r in rows}))

        st.markdown("### Reviews by industry")
        st.bar_chart(dict(Counter(r["industry"] for r in rows)))

        st.markdown("### Reviews by college")
        college_counts = Counter()
        for r in rows:
            if has_col(r, "college") and r["college"]:
                for c in r["college"].split(" · "):
                    college_counts[c.strip()] += 1
        if college_counts:
            st.bar_chart(dict(college_counts))

        st.markdown("### Top skills (by # of reviews mentioning them)")
        skill_counts: Counter = Counter()
        for r in rows:
            sr = safe_json(r["skill_ratings"]) if has_col(r, "skill_ratings") else {}
            if isinstance(sr, dict):
                for k, v in sr.items():
                    if v and int(v) > 0:
                        skill_counts[k] += 1
            for sk in (r["skills"] or "").split(","):
                sk = sk.strip()
                if sk and sk not in skill_counts:
                    skill_counts[sk] += 1
        if skill_counts:
            st.bar_chart(dict(skill_counts.most_common(15)))

# ================ ABOUT ================
else:
    st.subheader("About NU Coop Connect")
    st.write(
        "NU Coop Connect is a free, anonymous review board built by and for "
        "Northeastern students. The mission: help Huskies pick co-ops by sharing "
        "**which skills you actually built**, the **interview process**, "
        "**real perks and culture**, and **what prepared you** — without a single "
        "overall star rating that could unfairly tank a company."
    )
    st.markdown("### Why no single overall rating")
    st.write(
        "One 1–5 number can mislead. Instead, we show **per-skill ratings**, "
        "**culture tags**, and **honest written feedback** so future students "
        "get a fuller picture and pick what matters to them."
    )
    st.markdown("### Community rules")
    st.markdown(
        "- Reviews are anonymous — never share names, NUIDs, or contact info.\n"
        "- Be constructive — describe specifics, not insults.\n"
        "- Don't share company-confidential info.\n"
        "- Profanity, slurs, all-caps rants, and ultra-short reviews are auto-rejected.\n"
        "- Spot something off? Use the contact form on the main Squarespace site."
    )
    st.caption("Made with care by Huskies — not affiliated with Northeastern University.")

st.markdown(
    f"<hr><div style='text-align:center; color:{INK_FAINT}; font-size:12px; padding:8px 0;'>"
    f"Built by Huskies, for Huskies · Not affiliated with Northeastern University"
    f"</div>",
    unsafe_allow_html=True,
)
