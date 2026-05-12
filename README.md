# NU Coop Connect

An anonymous, skill-based co-op review board for Northeastern students.
Built with Streamlit + SQLite. **Free to host** on Streamlit Community Cloud.

## Features
- Anonymous submission (no login, no email, no NUID)
- Per-skill 0–5 ratings grouped by every Northeastern college (Khoury, D'Amore-McKim, COE, Bouvé, COS, CSSH, CAMD, plus soft skills) — 0 = N/A
- Holland Code (RIASEC) interest alignment
- Interview process: # rounds, # technical, recruiter style, interview notes
- Perks checkboxes: paid co-op, paid holidays, health insurance, 401(k), relocation, hybrid, etc.
- Culture tags: company outings, coffee chat culture, NU alumni density, mentorship, etc.
- Tag-based filter on Browse: industry, role, skills, college
- Constructive-review filter (auto-rejects profanity, too-short, or all-caps rants)
- No single overall star rating (intentional — see About page)
- Northeastern red / black / white styling, with optional `logo.png` in the project root

## Run locally
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy free (Streamlit Community Cloud)
1. Push this repo to GitHub.
2. Go to https://share.streamlit.io and sign in with GitHub.
3. Click **New app** → pick your repo → main file `app.py` → **Deploy**.
4. You get a free URL like `https://nu-coop-connect.streamlit.app`.

## Embed in Squarespace
Add a **Code Block** to any Squarespace page:
```html
<iframe src="https://YOUR-APP.streamlit.app/?embed=true"
        width="100%" height="1100" style="border:0;"></iframe>
```
Or just link out to the Streamlit URL from a button.

## Database note
SQLite is used because it's zero-config and free. On Streamlit Community Cloud the
`reviews.db` file lives on the app container's disk, which **resets when the app
restarts/redeploys**. For long-term storage, swap to a free Postgres on
[Neon](https://neon.tech) or [Supabase](https://supabase.com) — only the
`get_conn()` function needs to change.
