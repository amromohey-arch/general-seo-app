import os
import json
import requests
from modules.gemini_client import gemini


def get_autocomplete_suggestions(topic: str) -> list[str]:
    suggestions = set()
    seed_variants = [
        topic,
        f"{topic} sydney",
        f"{topic} australia",
        f"how to {topic}",
        f"best {topic}",
        f"{topic} cost",
        f"{topic} company",
        f"hire {topic}",
    ]
    for seed in seed_variants:
        try:
            r = requests.get(
                'https://suggestqueries.google.com/complete/search',
                params={'q': seed, 'client': 'firefox', 'hl': 'en-AU'},
                timeout=4,
                headers={'User-Agent': 'Mozilla/5.0'},
            )
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list) and len(data) > 1:
                    for s in data[1]:
                        suggestions.add(s)
        except Exception:
            pass
        try:
            r = requests.get(
                'https://duckduckgo.com/ac/',
                params={'q': seed, 'type': 'list'},
                timeout=4,
                headers={'User-Agent': 'Mozilla/5.0'},
            )
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list) and len(data) > 1:
                    for item in data[1]:
                        suggestions.add(item)
        except Exception:
            pass
    return list(suggestions)[:80]


def expand_keywords_with_ai(topic: str, existing: list[str]) -> list[str]:
    prompt = f"""You are an SEO strategist for 618 Media, a video production company in Sydney and NSW, Australia.
Services: music videos, corporate video, event coverage, real estate video, social media content, brand video.

Topic: "{topic}"
Already found keywords: {json.dumps(existing[:20])}

Generate 30 additional SEO keyword phrases that:
- People in Australia realistically search for related to this topic
- Match 618 Media's services
- Include question-format keywords ("how much does...", "what is...", "do I need...")
- Include location variants (Sydney, NSW, Australia)
- Include comparison keywords ("vs", "vs agency", "freelance vs")

Return ONLY a JSON array of keyword strings. No other text."""
    try:
        text = gemini(prompt).strip().replace('```json', '').replace('```', '').strip()
        return json.loads(text)
    except Exception as e:
        print(f"[Keywords] Expand error: {e}")
        return []


def cluster_keywords(keywords: list[str], topic: str) -> list[dict]:
    prompt = f"""You are an SEO strategist for 618 Media, a video production company in Sydney and NSW, Australia.

Topic seed: "{topic}"
Keywords to analyse: {json.dumps(keywords)}

Group these into 4-6 distinct article clusters. Each cluster represents ONE article.

For each cluster return:
- "cluster_name": short name (3-5 words)
- "article_angle": one sentence describing the specific angle
- "primary_keyword": the single most important keyword
- "secondary_keywords": array of 6-10 supporting keywords
- "search_intent": "informational" or "commercial" or "comparison"
- "ai_search_angle": one sentence on how this answers an AI search query
- "paa_questions": array of 5 People Also Ask questions
- "difficulty": "low" or "medium" or "high"
- "priority": integer 1-5 (5 = most valuable for 618 Media)

Return ONLY a JSON array. No markdown, no other text."""
    try:
        text = gemini(prompt).strip().replace('```json', '').replace('```', '').strip()
        clusters = json.loads(text)
        return sorted(clusters, key=lambda x: x.get('priority', 0), reverse=True)
    except Exception as e:
        print(f"[Keywords] Clustering error: {e}")
        return []
