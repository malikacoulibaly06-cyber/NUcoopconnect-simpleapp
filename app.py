"""
NU Coop Connect — Anonymous Northeastern co-op review board.
Skill-based, anonymous, free to host on Streamlit Community Cloud.
"""

import sqlite3
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

# ---------- CONFIG ----------
DB_PATH = Path(__file__).parent / "reviews.db"

NU_RED = "#C8102E"
NU_BLACK = "#000000"
NU_WHITE = "#FFFFFF"

st.set_page_config(
    page_title="NU Coop Connect",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------- THEMING (red / black / white) ----------
st.markdown(
    f"""
    <style>
      .stApp {{
        background-color: {NU_WHITE};
        color: {NU_BLACK};
      }}
      h1, h2, h3, h4 {{
        color: {NU_BLACK};
        font-weight: 700;
      }}
      .nu-banner {{
        background: {NU_RED};
        color: {NU_WHITE};
        padding: 18px 24px;
        border-radius: 8px;
        margin-bottom: 18px;
      }}
      .nu-banner h1 {{
        color: {NU_WHITE};
        margin: 0;
        font-size: 28px;
      }}
      .nu-banner p {{ color: {NU_WHITE}; margin: 4px 0 0 0; opacity: 0.95; }}
      .review-card {{
        border: 1px solid #e5e5e5;
        border-left: 6px solid {NU_RED};
        padding: 16px 18px;
        margin-bottom: 14px;
        border-radius: 6px;
        background: {NU_WHITE};
      }}
      .review-card h4 {{ margin: 0 0 6px 0; color: {NU_BLACK}; }}
      .tag {{
        display: inline-block;
        background: {NU_BLACK};
        color: {NU_WHITE};
        padding: 3px 10px;
        margin: 3px 4px 3px 0;
        border-radius: 999px;
        font-size: 12px;
      }}
      .tag-red {{ background: {NU_RED}; }}
      .stButton > button {{
        background-color: {NU_RED};
        color: {NU_WHITE};
        border: none;
        font-weight: 600;
      }}
      .stButton > button:hover {{
        background-color: {NU_BLACK};
        color: {NU_WHITE};
      }}
      section[data-testid="stSidebar"] {{
        background-color: {NU_BLACK};
      }}
      section[data-testid="stSidebar"] * {{ color: {NU_WHITE} !important; }}
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------- DB ----------
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                company TEXT NOT NULL,
                role TEXT NOT NULL,
                industry TEXT NOT NULL,
                semester TEXT,
                rating INTEGER NOT NULL,
                skills TEXT NOT NULL,        -- comma-separated
                courses TEXT,                -- comma-separated
                clubs TEXT,                  -- comma-separated
                prior_experience TEXT,
                what_you_did TEXT NOT NULL,
                what_you_learned TEXT NOT NULL,
                advice TEXT
            )
            """
        )
        conn.commit()

init_db()

# ---------- CONSTANTS ----------
INDUSTRIES = [
    "Technology / Software", "Finance / Banking", "Consulting", "Healthcare / Biotech",
    "Engineering", "Marketing / Advertising", "Government / Non-profit",
    "Media / Entertainment", "Education / Research", "Manufacturing", "Other",
]

SKILLS = [
    "Python", "JavaScript", "React", "SQL", "Java", "C++", "Excel", "Tableau",
    "Power BI", "Figma", "Public Speaking", "Project Management", "Data Analysis",
    "Machine Learning", "Cloud (AWS/GCP/Azure)", "Git/GitHub", "Agile/Scrum",
    "Client Communication", "Technical Writing", "CAD", "Lab Techniques",
    "Financial Modeling", "Marketing Strategy", "UX Research", "Leadership",
]

# A small starter list — students can also type their own
COURSES = [
    "CS2500 Fundamentals of CS 1", "CS2510 Fundamentals of CS 2",
    "CS3500 OO Design", "CS3700 Networks", "CS3200 Databases",
    "DS2000 Programming with Data", "DS3000 Foundations of Data Science",
    "MATH2331 Linear Algebra", "FINA2201 Financial Management",
    "ENGW1111 First-Year Writing", "ENTR2206 Innovation", "Other",
]

# ---------- CONSTRUCTIVE-REVIEW FILTER ----------
BANNED_WORDS = {
    # crude profanity / slurs — kept short on purpose; the filter is just a guard
    "fuck", "shit", "bitch", "asshole", "dumbass", "idiot", "moron", "retard",
    "stupid", "loser", "trash", "garbage", "sucks", "worst", "hate",
}

def is_constructive(*texts: str) -> tuple[bool, str]:
    """Returns (ok, reason)."""
    combined = " ".join(t for t in texts if t).strip()
    if len(combined) < 80:
        return False, "Please write at least a couple of sentences (80+ characters total)."
    # Avoid pure rants
    lowered = combined.lower()
    hits = [w for w in BANNED_WORDS if re.search(rf"\b{re.escape(w)}\b", lowered)]
    if hits:
        return False, (
            "Your review uses language that doesn't feel constructive "
            f"(e.g. '{hits[0]}'). Please reframe with specific, helpful feedback."
        )
    # Discourage ALL-CAPS shouting
    letters = [c for c in combined if c.isalpha()]
    if letters and sum(1 for c in letters if c.isupper()) / len(letters) > 0.6:
        return False, "Please avoid writing in all caps."
    # Require some substance words ("I", verbs, etc.)
    if len(combined.split()) < 20:
        return False, "Please add more detail — at least 20 words."
    return True, ""

# ---------- HEADER ----------
st.markdown(
    """
    <div class="nu-banner">
      <h1>🎓 NU Coop Connect</h1>
      <p>Anonymous, skill-based co-op reviews by Northeastern students, for Northeastern students.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------- SIDEBAR NAV ----------
page = st.sidebar.radio(
    "Navigate",
    ["Browse Reviews", "Submit a Review", "Stats", "About"],
    index=0,
)

# ---------- BROWSE ----------
def render_review_card(row: sqlite3.Row):
    skills_html = "".join(
        f'<span class="tag tag-red">{s.strip()}</span>'
        for s in (row["skills"] or "").split(",") if s.strip()
    )
    courses_html = "".join(
        f'<span class="tag">📘 {c.strip()}</span>'
        for c in (row["courses"] or "").split(",") if c.strip()
    )
    clubs_html = "".join(
        f'<span class="tag">🎯 {c.strip()}</span>'
        for c in (row["clubs"] or "").split(",") if c.strip()
    )
    prior = (
        f'<span class="tag">💼 Prior: {row["prior_experience"]}</span>'
        if row["prior_experience"] else ""
    )
    stars = "★" * int(row["rating"]) + "☆" * (5 - int(row["rating"]))

    st.markdown(
        f"""
        <div class="review-card">
          <h4>{row["role"]} @ {row["company"]} <span style="color:{NU_RED}">{stars}</span></h4>
          <div style="color:#555; font-size: 13px; margin-bottom: 8px;">
            {row["industry"]} · {row["semester"] or "Semester not specified"} · Posted {row["created_at"][:10]}
          </div>
          <div style="margin: 6px 0;"><b>Skills earned:</b><br>{skills_html or '<i>None listed</i>'}</div>
          <div style="margin: 6px 0;"><b>What I did:</b> {row["what_you_did"]}</div>
          <div style="margin: 6px 0;"><b>What I learned:</b> {row["what_you_learned"]}</div>
          {f'<div style="margin: 6px 0;"><b>Advice:</b> {row["advice"]}</div>' if row["advice"] else ''}
          <div style="margin-top: 8px;">{courses_html}{clubs_html}{prior}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

if page == "Browse Reviews":
    st.subheader("Browse co-op reviews")

    with get_conn() as conn:
        df = pd.read_sql_query("SELECT * FROM reviews ORDER BY created_at DESC", conn)

    if df.empty:
        st.info("No reviews yet — be the first to share!")
    else:
        c1, c2, c3 = st.columns(3)
        with c1:
            ind_filter = st.multiselect("Industry", sorted(df["industry"].unique()))
        with c2:
            role_filter = st.text_input("Role contains", "")
        with c3:
            all_skills = sorted({
                s.strip() for row in df["skills"].dropna() for s in row.split(",") if s.strip()
            })
            skill_filter = st.multiselect("Skills earned", all_skills)

        filtered = df.copy()
        if ind_filter:
            filtered = filtered[filtered["industry"].isin(ind_filter)]
        if role_filter:
            filtered = filtered[filtered["role"].str.contains(role_filter, case=False, na=False)]
        if skill_filter:
            filtered = filtered[
                filtered["skills"].fillna("").apply(
                    lambda s: all(sk in [x.strip() for x in s.split(",")] for sk in skill_filter)
                )
            ]

        st.caption(f"Showing **{len(filtered)}** of {len(df)} reviews")
        for _, row in filtered.iterrows():
            render_review_card(row)

# ---------- SUBMIT ----------
elif page == "Submit a Review":
    st.subheader("Share your co-op experience")
    st.caption("100% anonymous. We don't collect your name, email, or NUID.")

    with st.form("review_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            company = st.text_input("Company *", max_chars=100)
            role = st.text_input("Co-op role / title *", max_chars=100)
            industry = st.selectbox("Industry *", INDUSTRIES)
        with c2:
            semester = st.selectbox(
                "Co-op semester",
                ["", "Spring 2024", "Summer 2024", "Fall 2024",
                 "Spring 2025", "Summer 2025", "Fall 2025",
                 "Spring 2026", "Summer 2026", "Fall 2026", "Other"],
            )
            rating = st.slider("Overall rating *", 1, 5, 4)

        st.markdown("**Skills you earned / strengthened on this co-op**")
        skills = st.multiselect("Pick all that apply", SKILLS)
        custom_skills = st.text_input("Other skills (comma-separated)", "")

        st.markdown("**What helped prepare you?**")
        courses = st.multiselect("Courses that helped", COURSES)
        custom_courses = st.text_input("Other courses (comma-separated)", "")
        clubs = st.text_input("Clubs / organizations (comma-separated)", "")
        prior_experience = st.text_input("Prior experience (e.g., previous co-op, internship, project)", "")

        what_you_did = st.text_area("What did you do day-to-day? *", height=120)
        what_you_learned = st.text_area("What did you learn? *", height=120)
        advice = st.text_area("Advice for future co-ops (optional)", height=80)

        submitted = st.form_submit_button("Submit review")

        if submitted:
            # Required fields
            missing = [n for n, v in [
                ("Company", company), ("Role", role), ("Industry", industry),
                ("What you did", what_you_did), ("What you learned", what_you_learned),
            ] if not v.strip()]
            if missing:
                st.error(f"Please fill in: {', '.join(missing)}")
            elif not (skills or custom_skills.strip()):
                st.error("Please list at least one skill you earned.")
            else:
                ok, reason = is_constructive(what_you_did, what_you_learned, advice)
                if not ok:
                    st.error(f"Review not posted — {reason}")
                else:
                    all_skills = ", ".join(
                        [*skills, *[s.strip() for s in custom_skills.split(",") if s.strip()]]
                    )
                    all_courses = ", ".join(
                        [*[c for c in courses if c != "Other"],
                         *[c.strip() for c in custom_courses.split(",") if c.strip()]]
                    )
                    with get_conn() as conn:
                        conn.execute(
                            """INSERT INTO reviews
                               (created_at, company, role, industry, semester, rating,
                                skills, courses, clubs, prior_experience,
                                what_you_did, what_you_learned, advice)
                               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (
                                datetime.utcnow().isoformat(),
                                company.strip(), role.strip(), industry,
                                semester, int(rating),
                                all_skills, all_courses, clubs.strip(),
                                prior_experience.strip(),
                                what_you_did.strip(), what_you_learned.strip(),
                                advice.strip(),
                            ),
                        )
                        conn.commit()
                    st.success("Thanks! Your review is live on the Browse page.")
                    st.balloons()

# ---------- STATS ----------
elif page == "Stats":
    st.subheader("Community stats")
    with get_conn() as conn:
        df = pd.read_sql_query("SELECT * FROM reviews", conn)
    if df.empty:
        st.info("Stats will appear once reviews are posted.")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("Total reviews", len(df))
        c2.metric("Unique companies", df["company"].nunique())
        c3.metric("Average rating", f"{df['rating'].mean():.2f} / 5")

        st.markdown("### Reviews by industry")
        st.bar_chart(df["industry"].value_counts())

        st.markdown("### Top skills earned")
        skill_counts: dict[str, int] = {}
        for s in df["skills"].dropna():
            for sk in s.split(","):
                sk = sk.strip()
                if sk:
                    skill_counts[sk] = skill_counts.get(sk, 0) + 1
        if skill_counts:
            skill_df = (
                pd.DataFrame(skill_counts.items(), columns=["Skill", "Count"])
                .sort_values("Count", ascending=False).head(15)
            )
            st.bar_chart(skill_df.set_index("Skill"))

# ---------- ABOUT ----------
else:
    st.subheader("About NU Coop Connect")
    st.write(
        "NU Coop Connect is a free, anonymous review board built by and for "
        "Northeastern students. The goal is simple: help each other pick co-ops "
        "by sharing the **skills you actually built**, the **courses, clubs and prior "
        "experience that prepared you**, and **honest, constructive feedback**."
    )
    st.markdown("**Community rules**")
    st.markdown(
        "- Reviews are anonymous — never share names, NUIDs, or contact info.\n"
        "- Be constructive: describe specifics, not insults.\n"
        "- Reviews that use slurs, profanity, or that are too short are auto-rejected.\n"
        "- Report bad-faith content via Squarespace contact form."
    )

st.markdown(
    f"<hr><div style='text-align:center; color:#777; font-size:12px;'>"
    f"Built by Huskies, for Huskies · Not affiliated with Northeastern University"
    f"</div>",
    unsafe_allow_html=True,
)
