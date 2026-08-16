# 618 Media SEO Article Tool — Setup Guide

## What this tool does

1. Pulls keywords from Google Autocomplete + your Search Console + AI expansion
2. Clusters them into distinct article opportunities
3. Asks you 3 copilot questions to personalise the article
4. Generates a complete HTML article matching the 618 Media template
5. Saves all articles locally so it never generates a duplicate

---

## Requirements

- Python 3.10 or higher
- An Anthropic API key (you already have this)
- Your Web3Forms access key (from your website build)
- Optionally: Google Cloud credentials for Search Console

---

## Step 1 — Install Python dependencies

Open Terminal in the project folder and run:

```bash
pip install -r requirements.txt
```

---

## Step 2 — Set up your .env file

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Then open `.env` and fill in:

**ANTHROPIC_API_KEY**
Get this from: https://console.anthropic.com → API Keys

**WEB3FORMS_ACCESS_KEY**
Find this in your Web3Forms dashboard, or check your 618 Media website config.

---

## Step 3 — Set up Google Search Console (optional but recommended)

This gives you real data on what people are already searching to find your site.
Without it, the tool still works — it just uses Autocomplete and AI only.

### 3a. Create a Google Cloud project

1. Go to https://console.cloud.google.com
2. Create a new project → name it "618 Media SEO Tool"
3. Go to APIs & Services → Enable APIs
4. Search for "Google Search Console API" → Enable it

### 3b. Create OAuth credentials

1. Go to APIs & Services → Credentials
2. Create Credentials → OAuth 2.0 Client ID
3. Application type: **Web application**
4. Name: "618 Media SEO Tool"
5. Authorised redirect URIs: add `http://localhost:5618/api/sc/callback`
6. Download the credentials
7. Copy the Client ID and Client Secret into your `.env` file

### 3c. Set up OAuth consent screen

1. Go to APIs & Services → OAuth consent screen
2. User type: External
3. Add your email as a test user
4. Scopes: add `https://www.googleapis.com/auth/webmasters.readonly`

---

## Step 4 — Run the app

```bash
python app.py
```

Open your browser at: **http://localhost:5618**

---

## How to use it

**1. Research**
Type a topic (e.g. "music video production", "corporate video", "event filming").
The tool fetches keywords from Google Autocomplete and expands them with AI.
If you've connected Search Console, it also pulls real impression data from your site.

**2. Clusters**
The AI groups all keywords into 4–6 article opportunities, ranked by priority.
Each shows: article angle, search intent, competition difficulty, PAA questions, and how it answers AI search queries.
Click one to select it, then click "Use This Cluster."

**3. Copilot**
Answer 3 questions to personalise the article to 618 Media's actual work.
Some questions have clickable options, others are free-text.
If none of the options fit, pick "Other" and type your answer.

**4. SEO Meta**
Set the SEO title (50–60 chars) and meta description (130–160 chars).
These go into the HTML file's `<head>` and into Squarespace's page SEO settings.
The tool tells you the character count as you type.

**5. Download & publish**
The article is saved to `output/articles/` as a full HTML file.
Download it. Then in Squarespace:
- Add your H1 title in the blog post title field
- Add your hero image at the top of the post
- Copy the SEO title and description into the page's SEO settings tab
- Paste the body content (between the comment markers) into the post editor

---

## Article storage

All generated articles are indexed in `output/articles_index.json`.
Before generating a new article, the tool automatically checks this index for duplicates.
If it finds a similar existing article (3+ overlapping keywords), it warns you before proceeding.

---

## Running on your website (optional)

To run this on your server instead of your laptop:

1. Deploy to any Python host (Railway, Render free tier, your own VPS)
2. Set the environment variables in the host's dashboard
3. Change `REDIRECT_URI` in `modules/search_console.py` to your live domain
4. Add that URI to your Google Cloud OAuth credentials

---

## Troubleshooting

**"Module not found" errors**
Run `pip install -r requirements.txt` again.

**Google OAuth not working**
Make sure `http://localhost:5618/api/sc/callback` is in your Google Cloud authorised redirect URIs.

**Article generation is slow**
The Anthropic API takes 20–40 seconds to write a full article. This is normal.
Switch `ANTHROPIC_MODEL=claude-sonnet-4-6` in `.env` for faster (but slightly lower quality) output.

**Keywords are thin without Search Console**
Connect Search Console — it's free and gives you the most accurate data for your site specifically.
