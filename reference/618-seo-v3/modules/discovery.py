"""
Idea discovery for the unattended pipeline.

Three signals, all free:
1. Google Search Console (topic=None) — real queries already reaching your site.
   Strongest signal: proven demand, not a guess.
2. Google Autocomplete (already in keywords.py) — seeded from your music-video
   service focus, catches real search phrasing for topics you don't rank for yet.
3. Google Trends (pytrends) — rising/falling direction, used as a tiebreaker,
   not a primary signal (Trends alone is too noisy for a small local business).

Seeds are deliberately music-video-led — that's the stated brand strategy
(lead positioning for Instagram and client acquisition), not an accident.
Other verticals aren't excluded outright but aren't seeded for either; they'll
only surface here if Search Console shows real demand for them.

Output: a ranked, deduped list of candidate clusters, same shape cluster_keywords()
already produces, ready to feed straight into generate_article_html.
"""
import json
import os
import time
from modules.keywords import get_autocomplete_suggestions, expand_keywords_with_ai, cluster_keywords
from modules.search_console import get_sc_keywords
from modules.storage import load_sc_token, check_duplicate, log_ideas_run, get_pending, get_existing_titles
from modules.gemini_client import gemini

_MODULES_DIR = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_CONFIG_PATH = os.path.normpath(os.path.join(_MODULES_DIR, '..', 'config', '618-media.json'))

_config_path_env = os.environ.get('CONFIG_PATH', '').strip()
if _config_path_env:
    CONFIG_PATH = (
        _config_path_env if os.path.isabs(_config_path_env)
        else os.path.normpath(os.path.join(_MODULES_DIR, _config_path_env))
    )
else:
    CONFIG_PATH = _DEFAULT_CONFIG_PATH

_REQUIRED_CONFIG_PATHS = [
    'tenant.business_name',
    'seed_topics.topics',
]


def _load_tenant_config(path: str) -> dict:
    if not os.path.exists(path):
        raise RuntimeError(f"Tenant config not found at '{path}'. Set the CONFIG_PATH env var "
                            f"to a valid config file, or check that the default config exists.")
    try:
        with open(path, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Tenant config at '{path}' is not valid JSON: {e}") from e

    for dotted_path in _REQUIRED_CONFIG_PATHS:
        node = cfg
        for part in dotted_path.split('.'):
            if not isinstance(node, dict) or part not in node:
                raise RuntimeError(f"Tenant config at '{path}' is missing '{dotted_path}'.")
            node = node[part]
        # A key can be present but hold null/[] (e.g. from a config author
        # leaving a placeholder) -- that's not a usable value, so treat it
        # the same as missing rather than letting it fail downstream with a
        # TypeError or silently degrade.
        if node is None or node == []:
            raise RuntimeError(f"Tenant config at '{path}' has '{dotted_path}' set to null/empty.")

    return cfg


TENANT_CONFIG = _load_tenant_config(CONFIG_PATH)

# Music video first, deliberately — this is 618 Media's lead positioning, not
# one vertical among equals. Covers the practical angles people actually
# search (cost, planning, style choice) alongside the format itself.
# (Comment describes 618's specific strategy; the actual seed list itself is
# now tenant data, read from config/618-media.json's seed_topics.topics.)
SEED_TOPICS = TENANT_CONFIG['seed_topics']['topics']

BUSINESS_NAME = TENANT_CONFIG['tenant']['business_name']


def _get_trend_scores(terms: list[str]) -> dict:
    """Returns {term: trend_score} where trend_score is 0-100 (recent relative
    interest) or None if pytrends fails — Trends' unofficial API is flaky by
    design, so this must never block the pipeline if it errors."""
    scores = {}
    try:
        from pytrends.request import TrendReq
        pytrends = TrendReq(hl='en-AU', tz=-600)  # AEST offset
        # pytrends caps at 5 terms per request
        for i in range(0, len(terms), 5):
            batch = terms[i:i + 5]
            try:
                pytrends.build_payload(batch, timeframe='today 3-m', geo='AU')
                df = pytrends.interest_over_time()
                if not df.empty:
                    for term in batch:
                        if term in df.columns:
                            recent = df[term].tail(4).mean()  # last ~4 weeks
                            scores[term] = float(recent)
                time.sleep(1)  # unofficial API — be gentle, avoid IP cooldowns
            except Exception as e:
                print(f"[Discovery] Trends batch error ({batch}): {e}")
                continue
    except Exception as e:
        print(f"[Discovery] Trends unavailable this run: {e}")
    return scores


def _score_cluster(cluster: dict, sc_impression_terms: set, trend_scores: dict) -> float:
    """Blend: cluster priority (from Gemini clustering) is the base signal.
    Add a boost if the primary/secondary keywords showed up in real Search
    Console queries (proven demand), and a smaller boost for trend direction."""
    base = cluster.get('priority', 3) * 10  # 10-50

    kw_pool = [cluster.get('primary_keyword', '')] + cluster.get('secondary_keywords', [])
    kw_pool_lower = set(k.lower() for k in kw_pool if k)

    sc_hits = len(kw_pool_lower & sc_impression_terms)
    sc_boost = min(sc_hits * 8, 30)  # real demand matters most, cap so one cluster can't hoard it

    trend_boost = 0
    for kw in kw_pool_lower:
        if kw in trend_scores:
            trend_boost += min(trend_scores[kw] / 10, 5)
    trend_boost = min(trend_boost, 15)

    return round(base + sc_boost + trend_boost, 1)


def _filter_semantic_overlap(candidates: list) -> list:
    """check_duplicate() only catches exact keyword/slug string overlap — it
    missed 'corporate video production cost' vs 'choosing a corporate video
    company' being the same article twice. This asks Gemini directly whether
    a candidate topic actually overlaps in angle with something you've already
    published, the way a human editor would judge it, not by string matching.
    One batched call for all candidates — cheap, and skipped entirely if
    there's nothing published yet or nothing left to check."""
    existing = get_existing_titles()
    if not existing or not candidates:
        return candidates

    existing_lines = '\n'.join(f"- {e['seo_title']} (keyword: {e['primary_keyword']})" for e in existing if e['seo_title'])
    candidate_lines = '\n'.join(f"{i}. {c.get('cluster_name', '')} — angle: {c.get('article_angle', '')}"
                                 for i, c in enumerate(candidates))

    prompt = (
        f"You are an editor for {BUSINESS_NAME}. Below is a list of "
        "ALREADY PUBLISHED articles, and a numbered list of CANDIDATE new article topics.\n\n"
        "For each candidate, decide if it substantially overlaps with an already-published article — "
        "meaning a reader would find them repetitive covering the same ground, even if the exact "
        "keywords differ. For example, 'corporate video production cost' and 'choosing a corporate "
        "video production company' overlap: both are generic corporate-video buying guides covering "
        "the same territory. A genuinely different angle, format, or specific use-case is NOT overlap.\n\n"
        f"ALREADY PUBLISHED:\n{existing_lines}\n\n"
        f"CANDIDATES:\n{candidate_lines}\n\n"
        "Return ONLY a JSON object: {\"overlapping_indices\": [list of candidate index numbers that "
        "overlap and should be skipped]}. Empty list if none overlap."
    )
    try:
        text = gemini(prompt).strip().replace('```json', '').replace('```', '').strip()
        result = json.loads(text)
        skip = set(result.get('overlapping_indices', []))
        return [c for i, c in enumerate(candidates) if i not in skip]
    except Exception as e:
        print(f"[Discovery] Semantic overlap check failed, continuing without it: {e}")
        return candidates


def run_discovery(max_candidates: int = 5) -> list[dict]:
    """Main entry point for the cron job. Returns top-scored, non-duplicate
    candidate clusters ready for the generation step."""
    all_candidates = []

    # 1. Real Search Console demand (topic=None = unfiltered top queries)
    sc_token = load_sc_token()
    sc_queries = []
    if sc_token:
        try:
            sc_queries = get_sc_keywords(sc_token, topic=None)
        except Exception as e:
            print(f"[Discovery] Search Console pull failed: {e}")
    else:
        print("[Discovery] No Search Console token saved yet — connect it in the "
              "web UI once (top of index page) so the pipeline can use real query data.")
    sc_terms_lower = set(q.lower() for q in sc_queries)

    # 2. Seed-based autocomplete + AI expansion + clustering (existing logic, reused as-is)
    for seed in SEED_TOPICS:
        try:
            autocomplete = get_autocomplete_suggestions(seed)
            # Fold in any SC queries that share a word with this seed — cheap way
            # to route real demand into the right seed's clustering pass.
            seed_words = set(seed.lower().split())
            related_sc = [q for q in sc_queries if seed_words & set(q.lower().split())]
            pool = list(set(autocomplete + related_sc))
            ai_kw = expand_keywords_with_ai(seed, pool)
            all_kw = list(set(pool + ai_kw))
            if not all_kw:
                continue
            clusters = cluster_keywords(all_kw, seed)
            for c in clusters:
                c['_seed'] = seed
                all_candidates.append(c)
        except Exception as e:
            print(f"[Discovery] Seed '{seed}' failed: {e}")
            continue

    # 3. Trend direction for scoring (best-effort, never blocks the run)
    top_kw_for_trends = list({c.get('primary_keyword', '') for c in all_candidates if c.get('primary_keyword')})[:15]
    trend_scores_raw = _get_trend_scores(top_kw_for_trends) if top_kw_for_trends else {}
    trend_scores = {k.lower(): v for k, v in trend_scores_raw.items()}

    # 4. Dedupe: string-level check first (cheap), then semantic overlap check
    #    against your actual published titles (catches near-duplicates the
    #    string check misses), then anything already sitting in the pending queue.
    pending_keywords = set()
    for p in get_pending():
        pending_keywords.add((p.get('cluster') or {}).get('primary_keyword', '').lower())
        pending_keywords.add((p.get('seo_title') or '').lower())

    string_filtered = []
    for c in all_candidates:
        dup = check_duplicate(c.get('cluster_name', ''), c.get('secondary_keywords', []) + [c.get('primary_keyword', '')])
        if dup.get('is_duplicate'):
            continue
        if c.get('primary_keyword', '').lower() in pending_keywords:
            continue
        string_filtered.append(c)

    fresh_candidates = _filter_semantic_overlap(string_filtered)
    for c in fresh_candidates:
        c['_score'] = _score_cluster(c, sc_terms_lower, trend_scores)

    # 5. Rank and cap
    fresh_candidates.sort(key=lambda x: x['_score'], reverse=True)
    top = fresh_candidates[:max_candidates]

    log_ideas_run(
        candidates=[{'cluster_name': c.get('cluster_name'), 'primary_keyword': c.get('primary_keyword'),
                     'score': c.get('_score'), 'seed': c.get('_seed')} for c in fresh_candidates],
        generated_ids=[],  # filled in by the pipeline runner after generation
    )

    return top
