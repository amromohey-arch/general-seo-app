"""
Video script generation — one full, word-for-word Reels script per article.

Changed by explicit decision: earlier this was a loose beat sheet (quick to
shoot, nothing memorized). That traded depth for speed, and it was coming out
thin — three one-breath lines can't cover real information. This version
writes an actual script meant to be read close to verbatim, built to cover
several genuinely specific points from the article in depth, not a hook and
a tease. Visual suggestions are still included per section, but the spoken
line is now the real content, not a cue.
"""
import json
import re
from modules.gemini_client import gemini

APPROVED_HOOKS = [
    "Nobody mentions this.",
    "I wish I knew this earlier.",
    "Pause for a second.",
    "Ever noticed this pattern?",
    "Here's the real truth.",
    "Let me save you hours.",
    "This may surprise you.",
    "You need this now.",
    "You may not agree with this.",
    "I just figured this out.",
]

_TAG_RE = re.compile(r'<[^>]+>')


def _strip_html(html: str) -> str:
    text = _TAG_RE.sub(' ', html or '')
    return re.sub(r'\s+', ' ', text).strip()


FUNNEL_DEFINITIONS = """
TOFU (Top of Funnel) — job: get a stranger to stop scrolling. No pitch, no CTA push.
Raw talking head, reaction/hot-take, or "reacting to something already popular then
redirecting to what's realistic for our ICP." Builds pure awareness, nothing sold.

MOFU (Middle of Funnel) — job: show how we actually work. Mechanism breakdown or
process walkthrough — a real piece of the process shown, not just the finished result.
Sells the thinking, not the gear. Builds trust through transparency.

BOFU (Bottom of Funnel) — job: prove it worked, get the message. Requires REAL proof —
an actual client testimonial in their own words, or real results/analytics shown on
screen. Never fabricate this. If the content has no genuine client proof behind it,
it is not BOFU, even if it's persuasive — default to TOFU or MOFU instead.
"""


def generate_video_script(article_body_html: str, cluster: dict, seo_title: str, article_slug: str = '') -> dict:
    """Returns a single full, word-for-word Reels script, JSON-shaped for the
    review queue. Always exactly one script — no variants."""
    body_text = _strip_html(article_body_html)[:6000]  # more context than before — the script now needs real substance, not just the gist

    prompt = (
        "You are writing a full, word-for-word Reels script for 618 Media, a video production company "
        "in Sydney and NSW, Australia. This is meant to be read close to verbatim on camera — not a loose "
        "beat sheet, not vague cues. It needs to actually teach the viewer something real, using specific "
        "points pulled from the article below, not generic filler that could apply to any video production "
        "company.\n\n"
        f"ARTICLE TITLE: {seo_title}\n"
        f"ARTICLE CONTENT (pull 4-6 genuinely specific, concrete points from this — numbers, real "
        f"process detail, real trade-offs — not the vaguest summary of each section):\n{body_text}\n\n"
        "RULES:\n"
        "- Format: Instagram Reels. Vertical, 60-90 seconds total when read at a natural speaking pace "
        "(roughly 150 words per minute). One script — no alternate cuts.\n"
        "- Open with a hook line, adapted from ONE of these approved hooks to fit the topic naturally "
        f"(don't force it verbatim if it doesn't fit): {json.dumps(APPROVED_HOOKS)}\n"
        "- The body must be full sentences, written exactly as they'll be spoken — not notes, not bullet "
        "fragments. Plain, direct, spoken language, not written-for-reading prose.\n"
        "- Structure it into 4-6 sections, each covering ONE specific, real point from the article in enough "
        "depth to actually be useful — a number, a concrete example, a real trade-off, not a restated title.\n"
        "- Close with one soft CTA line, no hard sell. Never 'click the link' or 'link in bio' as an "
        "instruction to physically click anything (Reels aren't clickable) — phrase it as a pointer, "
        "e.g. 'Full breakdown is up on the site if you want the numbers.'\n"
        "- No em dashes anywhere.\n"
        "- No AI-tell phrases: delve, leverage, robust, testament to, in today's fast-paced world, game-changing.\n"
        "- Each section gets a loose visual suggestion, achievable with existing footage — never demand a "
        "shot that doesn't exist yet — but the visual is secondary to the actual spoken content this time.\n\n"
        f"FUNNEL CLASSIFICATION — this is 618 Media's real funnel system, not a generic marketing framework:\n"
        f"{FUNNEL_DEFINITIONS}\n"
        "Decide which stage this specific script actually fits, based on what it does, not what would be "
        "nice. Most article-derived scripts land TOFU or MOFU — only classify BOFU if the script genuinely "
        "includes real client proof (it should not invent any).\n\n"
        "Return ONLY a JSON object with these exact keys:\n"
        "- sections: array of objects, each with 'label' (e.g. 'Hook', 'Point 1', 'Point 2', 'Close'), "
        "'script' (the full word-for-word text for this section, real sentences), 'visual' (loose B-roll/shot "
        "suggestion)\n"
        "- total_duration: string estimate e.g. '75s'\n"
        "- word_count: integer, total words across all sections\n"
        "- funnel_stage: one of 'TOFU', 'MOFU', 'BOFU'\n"
        "- funnel_reason: one sentence, why this stage fits, in plain terms\n"
        "- caption: ready-to-post Instagram caption for this Reel. Structure: 1-2 line hook that sets up the "
        "video without repeating it verbatim, then one soft CTA line, then the line '618 Media, video "
        "production across Sydney & NSW.', then 10-15 relevant hashtags mixing location "
        "(#videoproductionsydney #sydneyvideographer #nswbusiness), service-specific, audience "
        "(#smallbusinessaustralia #videomarketing), and #618media. No em dashes in the caption. No "
        "generic/bot hashtags.\n"
    )

    try:
        text = gemini(prompt).strip().replace('```json', '').replace('```', '').strip()
        result = json.loads(text)
        result['seo_title'] = seo_title
        result['article_slug'] = article_slug
        result['status'] = 'not_started'  # not_started | shot | posted | linked_back
        return result
    except Exception as e:
        print(f"[VideoScript] Error: {e}")
        return {'error': str(e), 'sections': [], 'caption': '', 'total_duration': ''}


def format_script_text(script: dict, article_title: str = '') -> str:
    """Plain-text, downloadable version — what actually gets read on shoot day."""
    if script.get('error'):
        return f"Script generation failed: {script['error']}"

    lines = [
        f"618 MEDIA — REEL SCRIPT",
        f"Article: {article_title or script.get('seo_title', '')}",
        f"Funnel stage: {script.get('funnel_stage', 'Unclassified')} — {script.get('funnel_reason', '')}",
        f"Estimated length: {script.get('total_duration', '')}  |  {script.get('word_count', '')} words",
        "=" * 60,
        "",
    ]
    for s in script.get('sections', []):
        lines.append(f"[{s.get('label', '').upper()}]")
        lines.append(s.get('script', ''))
        lines.append(f"(Visual: {s.get('visual', '')})")
        lines.append("")
    lines.append("=" * 60)
    lines.append("CAPTION")
    lines.append("-" * 60)
    lines.append(script.get('caption', ''))
    return '\n'.join(lines)
