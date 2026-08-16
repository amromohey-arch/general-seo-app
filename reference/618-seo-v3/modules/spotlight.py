"""
Artist and music video spotlight content.

Deliberately separate from discovery.py's service-page pipeline — this is a
different content type (commentary on real people and real releases, not a
buying guide for 618's own services) with a different accuracy bar. Both the
candidate search and the actual writing go through gemini_grounded(), which
pulls in live Google Search results instead of relying on the model's static
training knowledge — critical here, since "new and upcoming" is exactly where
an ungrounded model would confidently invent details about real people.

Sources listed on the finished article come from the model's actual search
results (GroundingChunkWeb), not from asking the model to remember or invent
a URL.
"""
import json
from datetime import datetime
from modules.gemini_client import gemini_grounded
from modules.storage import get_existing_titles, check_duplicate


def find_spotlight_candidates(max_candidates: int = 3) -> list:
    """Search-grounded discovery of real, current artists/videos worth
    covering — a mix of notable new releases and established/trending names,
    per your call on scope. Returns structured candidates, not prose."""
    existing = get_existing_titles()
    existing_lines = '\n'.join(f"- {e['seo_title']}" for e in existing if e['seo_title'])[-2000:]

    prompt = (
        "Search for real, current music videos and artists worth writing commentary about, from a "
        "video production company's perspective (618 Media, based in Sydney/NSW, covers music video "
        "production). Mix genuinely new/emerging releases with established or currently trending artists "
        "and videos, whatever is real and notable right now, any country, any genre. Prioritise videos "
        "with genuinely interesting visual/creative direction, since the angle is a filmmaker's take on "
        "what makes the video work, not just music fandom.\n\n"
        f"Already covered recently, avoid repeating: {existing_lines if existing_lines else 'nothing yet'}\n\n"
        f"Find {max_candidates + 2} real candidates (a couple extra in case some get filtered later). "
        "For each, you must have found it via search just now, do not include anything you're not "
        "currently seeing confirmed in search results.\n\n"
        "Return ONLY a JSON object: {\"candidates\": [{\"artist\": \"...\", \"video_or_song_title\": \"...\", "
        "\"why_notable\": \"one sentence, specific\", \"visual_hook\": \"what's visually or creatively "
        "interesting about it, one sentence\"}]}"
    )
    try:
        result = gemini_grounded(prompt)
        text = result['text'].strip().replace('```json', '').replace('```', '').strip()
        parsed = json.loads(text)
        candidates = parsed.get('candidates', [])[:max_candidates + 2]
        for c in candidates:
            c['_sources'] = result.get('sources', [])
            c['_search_queries'] = result.get('search_queries', [])
        return candidates
    except Exception as e:
        print(f"[Spotlight] Candidate search failed: {e}")
        return []


def _filter_spotlight_duplicates(candidates: list) -> list:
    fresh = []
    for c in candidates:
        title_guess = f"{c.get('artist', '')} {c.get('video_or_song_title', '')}"
        dup = check_duplicate(title_guess, [c.get('artist', ''), c.get('video_or_song_title', '')])
        if not dup.get('is_duplicate'):
            fresh.append(c)
    return fresh


def generate_spotlight_html(candidate: dict) -> dict:
    """Writes the actual article. Grounded the same way as discovery, every
    specific claim about the artist or video must trace back to what the
    search actually returned, not the model's memory. Lighter structure than
    the service-page template (no forced FAQ/factors table) since this is
    commentary, not a buying guide."""
    year = datetime.now().year
    artist = candidate.get('artist', '')
    title = candidate.get('video_or_song_title', '')

    prompt = (
        "Search for current, real information about this artist and video/song, then write a short "
        "commentary article about it for 618 Media (a Sydney/NSW video production company covering "
        "music videos).\n\n"
        f"Artist: {artist}\n"
        f"Video/song: {title}\n"
        f"Why it's notable: {candidate.get('why_notable', '')}\n"
        f"Visual hook: {candidate.get('visual_hook', '')}\n\n"
        "RULES — read carefully, these are hard constraints:\n"
        "- Every factual claim about the artist, the release, or the video must come from what you "
        "actually find in search results just now. If you're not sure of a detail, leave it out, never "
        "guess or fill in a plausible-sounding fact.\n"
        "- NEVER invent a quote and attribute it to the artist. Only include a quote if you find it "
        "verbatim in a real source, and keep any quote under 15 words.\n"
        "- NEVER reproduce song lyrics, even a fragment.\n"
        "- Do not describe specific shots or frames from the video in detail, describe the overall "
        "creative and visual approach and style, not a shot-by-shot account, since you have not watched "
        "the actual video, only search results about it.\n"
        "- Perspective: a video production company's take on what makes the visual approach work, not "
        "music journalism or fandom. This is 618 Media's expertise on display.\n"
        "- One short paragraph near the end should softly connect this to what 618 Media does, for "
        "example if an artist planning something like this wants to talk, without a hard sell or generic "
        "CTA language such as 'take your brand to the next level'.\n"
        "- No em dashes. No AI-tell phrases (delve, leverage, robust, testament to, seamless, captivating, "
        "in today's landscape).\n"
        f"- THE CURRENT YEAR IS {year}.\n\n"
        "CRITICAL HTML RULES:\n"
        "- body contains ONLY: p, h2, h3, ul, ol, li, strong, a\n"
        "- NO h1, NO tables, NO forms\n"
        "- 400-700 words, this is commentary, not a full guide, keep it tight\n"
        "- 2-4 H2 sections\n"
        "- Start with a hook, not a summary of what the article will cover\n\n"
        "Return ONLY a JSON object with these exact keys:\n"
        "- seo_title: string, under 60 chars, ends with | 618 Media\n"
        "- seo_description: string, 130-160 chars\n"
        "- body: HTML string\n"
        "- slug: kebab-case, max 6 words\n"
        "- word_count: integer\n"
    )
    try:
        result = gemini_grounded(prompt)
        text = result['text'].strip().replace('```json', '').replace('```', '').strip()
        parsed = json.loads(text)
        sources = result.get('sources', [])[:6]
        parsed['sources'] = sources
        parsed['content_type'] = 'spotlight'
        from modules.generator import assemble_spotlight_html
        parsed['fragment'] = assemble_spotlight_html(parsed.get('body', ''), sources, parsed.get('seo_title', ''), year)
        parsed['keywords_used'] = [artist, title]
        return parsed
    except Exception as e:
        print(f"[Spotlight] Article generation failed: {e}")
        return {'error': str(e)}


def run_spotlight(max_new: int = 1) -> dict:
    """Entry point for the pipeline. Finds candidates, filters duplicates,
    writes up to max_new articles, saves to the same pending review queue as
    everything else, nothing publishes without your approval, same as the
    service-page content, which matters more here given real people are
    involved."""
    from modules.storage import save_pending
    from modules.video_script import generate_video_script

    candidates = find_spotlight_candidates(max_candidates=max_new + 2)
    candidates = _filter_spotlight_duplicates(candidates)

    if not candidates:
        return {'generated': 0, 'note': 'No fresh candidates found this run.'}

    generated = []
    for c in candidates[:max_new]:
        result = generate_spotlight_html(c)
        if result.get('error'):
            print(f"[Spotlight] Skipping '{c.get('artist')}': {result['error']}")
            continue
        cluster = {'cluster_name': f"{c.get('artist')} - {c.get('video_or_song_title')}",
                   'primary_keyword': c.get('artist', '')}
        try:
            script = generate_video_script(
                article_body_html=result.get('body', ''), cluster=cluster,
                seo_title=result.get('seo_title', ''), article_slug=result.get('slug', ''),
            )
        except Exception as e:
            script = {'error': str(e)}
        entry = save_pending({
            'article': result,
            'cluster': cluster,
            'seo_title': result.get('seo_title', ''),
            'seo_description': result.get('seo_description', ''),
            'score': None,
            'source': 'spotlight-pipeline',
            'content_type': 'spotlight',
            'video_script': script,
            'session_data': {'topic': f"Spotlight: {c.get('artist')}", 'auto_generated': True},
        })
        generated.append(result.get('seo_title', ''))

    return {'generated': len(generated), 'titles': generated,
            'note': None if generated else 'Candidates found but all failed to generate.'}
