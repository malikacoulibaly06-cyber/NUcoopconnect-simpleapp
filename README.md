# NU Coop Connect

An anonymous, skill-based co-op review board for Northeastern students.
Built with Streamlit + SQLite. **Free to host** on Streamlit Community Cloud.

## Features
- Anonymous submission (no login, no email, no NUID)
- Skill-based reviews: students tag the **skills they earned**, the **courses that helped**, **clubs**, and **prior experience**
- Browse by **industry**, **co-op role**, and **skills**
- Constructive-review filter (auto-rejects profanity, too-short, or all-caps rants)
- Stats dashboard (industries, top skills)
- Northeastern red / black / white styling

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

## Embed in your Squarespace site
Add a **Code Block** to any Squarespace page:
```html
<iframe src="https://YOUR-APP.streamlit.app/?embed=true"
        width="100%" height="900" style="border:0;"></iframe>
```
Or just link to the Streamlit URL from a button.

## Note on the database
SQLite is used because it's zero-config and free. On Streamlit Community Cloud the
`reviews.db` file lives on the app container's disk, which **resets when the app
restarts/redeploys**. For long-term storage, swap to a free Postgres on
[Neon](https://neon.tech) or [Supabase](https://supabase.com) — only the
`get_conn()` function needs to change.
