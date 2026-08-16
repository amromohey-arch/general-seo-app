import uuid
from datetime import datetime
from modules import store_backend as sb

ARTICLES_INDEX_KEY = 'articles_index.json'
DRAFTS_INDEX_KEY = 'drafts_index.json'
LEARNINGS_KEY = 'learnings.json'
SC_TOKEN_KEY = 'sc_token.json'
PENDING_INDEX_KEY = 'pending_index.json'
IDEAS_LOG_KEY = 'ideas_log.json'


def _article_key(filename: str) -> str:
    return f'articles/{filename}'


def _article_data_key(filename: str) -> str:
    """Sidecar JSON holding the structured pieces (body/table/faq/cluster/image)
    behind a saved article — the flat .html fragment alone can't be re-edited
    without either this or reverse-parsing HTML, which is fragile."""
    return f'articles/{filename}.data.json'


# ── Articles ──────────────────────────────────────────────────────────────────

def get_articles() -> list:
    return sb.read_json(ARTICLES_INDEX_KEY, [])


def get_existing_titles() -> list:
    """Lightweight list of (seo_title, primary_keyword) for every published
    article — used to keep new articles genuinely distinct from old ones,
    both when scoring candidates and when writing the article itself."""
    articles = get_articles()
    out = []
    for a in articles:
        session = a.get('session', {}) or {}
        out.append({
            'seo_title': a.get('seo_title', ''),
            'primary_keyword': session.get('primary_keyword') or (a.get('keywords') or [''])[0],
        })
    return out


def save_article(result: dict, seo_title: str, seo_description: str, session_data: dict = None, cluster: dict = None, image_url: str = '', video_script: dict = None) -> dict:
    article_id = str(uuid.uuid4())[:8]
    slug = result.get('slug', article_id)
    filename = f"{article_id}_{slug}.html"

    sb.write_text(_article_key(filename), result.get('fragment', ''))
    sb.write_json(_article_data_key(filename), {
        'body': result.get('body', ''),
        'table': result.get('table'),
        'faq_items': result.get('faq_items', []),
        'cluster': cluster or {},
        'image_url': image_url or '',
        'content_type': result.get('content_type', 'article'),
        'sources': result.get('sources', []),
        'video_script': video_script or {},
    })

    articles = get_articles()
    meta = {
        'id': article_id,
        'slug': slug,
        'filename': filename,
        'seo_title': seo_title,
        'seo_description': seo_description,
        'keywords': result.get('keywords_used', []),
        'word_count': result.get('word_count', 0),
        'created_at': datetime.now().isoformat(),
        'rating': None,
        'rating_feedback': None,
        'session': session_data or {},
    }
    articles.append(meta)
    sb.write_json(ARTICLES_INDEX_KEY, articles)
    return meta


def get_articles_with_scripts() -> list:
    """Lightweight list for the Reels tab — every article that has a saved
    script, with just enough to show a title, funnel badge, and duration
    without loading the full body/table/faq for each one."""
    out = []
    for a in get_articles():
        data = sb.read_json(_article_data_key(a['filename']), {})
        script = data.get('video_script') or {}
        if script.get('sections'):
            out.append({
                'id': a['id'],
                'seo_title': a.get('seo_title', ''),
                'created_at': a.get('created_at', ''),
                'funnel_stage': script.get('funnel_stage', ''),
                'funnel_reason': script.get('funnel_reason', ''),
                'total_duration': script.get('total_duration', ''),
                'word_count': script.get('word_count', 0),
            })
    return out


def get_article_editable(article_id: str) -> dict | None:
    """Structured content for the edit UI — body/table/faq/cluster/image,
    plus the metadata (title, description) needed to re-run generation."""
    articles = get_articles()
    article = next((a for a in articles if a['id'] == article_id), None)
    if not article:
        return None
    data = sb.read_json(_article_data_key(article['filename']), {})
    return {
        'id': article['id'],
        'seo_title': article.get('seo_title', ''),
        'seo_description': article.get('seo_description', ''),
        'word_count': article.get('word_count', 0),
        'body': data.get('body', ''),
        'table': data.get('table'),
        'faq_items': data.get('faq_items', []),
        'cluster': data.get('cluster', {}),
        'image_url': data.get('image_url', ''),
        'content_type': data.get('content_type', 'article'),
        'sources': data.get('sources', []),
        'video_script': data.get('video_script', {}),
    }


def update_article_editable(article_id: str, fragment: str, body: str, table_data, faq_items: list,
                             word_count: int = None, image_url: str = '') -> bool:
    """Persists an edit — updates both the rendered .html and the structured
    sidecar, and the word count shown in the Articles list if it changed."""
    articles = get_articles()
    article = next((a for a in articles if a['id'] == article_id), None)
    if not article:
        return False

    sb.write_text(_article_key(article['filename']), fragment)
    existing_data = sb.read_json(_article_data_key(article['filename']), {})
    existing_data.update({'body': body, 'table': table_data, 'faq_items': faq_items, 'image_url': image_url})
    sb.write_json(_article_data_key(article['filename']), existing_data)

    if word_count is not None:
        article['word_count'] = word_count
        sb.write_json(ARTICLES_INDEX_KEY, articles)
    return True


def update_article_rating(article_id: str, rating: int, feedback: str = None):
    articles = get_articles()
    for a in articles:
        if a['id'] == article_id:
            a['rating'] = rating
            a['rating_feedback'] = feedback
            break
    sb.write_json(ARTICLES_INDEX_KEY, articles)

    if rating is not None:
        store_learning(article_id, rating, feedback, articles)


def get_article_file_path(article_id: str) -> str | None:
    """Returns a local filesystem path for send_file(). On GCS backend this
    returns None — callers must use get_article_content() instead."""
    articles = get_articles()
    article = next((a for a in articles if a['id'] == article_id), None)
    if not article:
        return None
    if sb.using_gcs():
        return None
    return sb._local_path(_article_key(article['filename']))


def get_article_content(article_id: str):
    """Returns (filename, html_content) regardless of backend — the portable
    way to serve an article's HTML on either local disk or GCS."""
    articles = get_articles()
    article = next((a for a in articles if a['id'] == article_id), None)
    if not article:
        return None
    content = sb.read_text(_article_key(article['filename']), '')
    return (article['filename'], content)


def update_article_content(article_id: str, html: str) -> bool:
    """Overwrites an article's saved HTML — used when a revision replaces the
    latest article. Works on either backend."""
    articles = get_articles()
    article = next((a for a in articles if a['id'] == article_id), None)
    if not article:
        return False
    sb.write_text(_article_key(article['filename']), html)
    return True


def check_duplicate(topic: str, new_keywords: list) -> dict:
    articles = get_articles()
    if not articles:
        return {'is_duplicate': False, 'similar_articles': []}
    similar = []
    topic_words = set(topic.lower().split())
    for article in articles:
        existing_kw = set(kw.lower() for kw in article.get('keywords', []))
        new_kw = set(kw.lower() for kw in new_keywords)
        kw_overlap = existing_kw & new_kw
        slug_words = set(article.get('slug', '').replace('-', ' ').split())
        topic_overlap = topic_words & slug_words
        if len(kw_overlap) >= 3 or len(topic_overlap) >= 2:
            similar.append({
                'id': article['id'],
                'slug': article['slug'],
                'seo_title': article.get('seo_title', article['slug']),
                'overlap_keywords': list(kw_overlap)[:5],
                'created_at': article.get('created_at', ''),
            })
    return {'is_duplicate': len(similar) > 0, 'similar_articles': similar}


# ── Drafts ────────────────────────────────────────────────────────────────────

def get_drafts() -> list:
    return sb.read_json(DRAFTS_INDEX_KEY, [])


def save_draft(draft_id: str, state: dict):
    drafts = get_drafts()
    existing = next((d for d in drafts if d['id'] == draft_id), None)
    now = datetime.now().isoformat()
    if existing:
        existing.update({
            'updated_at': now,
            'step': state.get('step', 1),
            'topic': state.get('topic', ''),
            'seo_title': state.get('seoTitle', ''),
            'state': state,
        })
    else:
        drafts.append({
            'id': draft_id,
            'created_at': now,
            'updated_at': now,
            'step': state.get('step', 1),
            'topic': state.get('topic', ''),
            'seo_title': state.get('seoTitle', ''),
            'state': state,
        })
    sb.write_json(DRAFTS_INDEX_KEY, drafts)


def delete_draft(draft_id: str):
    drafts = [d for d in get_drafts() if d['id'] != draft_id]
    sb.write_json(DRAFTS_INDEX_KEY, drafts)


# ── Search Console token persistence (for unattended cron use) ─────────────────

def save_sc_token(token_data: dict):
    sb.write_json(SC_TOKEN_KEY, token_data)


def load_sc_token() -> dict | None:
    return sb.read_json(SC_TOKEN_KEY, None)


# ── Pending queue (automated pipeline output, awaiting your review) ────────────

def get_pending() -> list:
    return sb.read_json(PENDING_INDEX_KEY, [])


def save_pending(entry: dict) -> dict:
    pending = get_pending()
    entry['id'] = entry.get('id') or str(uuid.uuid4())[:8]
    entry['created_at'] = entry.get('created_at') or datetime.now().isoformat()
    entry['status'] = entry.get('status', 'pending')
    pending.append(entry)
    sb.write_json(PENDING_INDEX_KEY, pending)
    return entry


def update_pending_status(pending_id: str, status: str):
    pending = get_pending()
    for p in pending:
        if p['id'] == pending_id:
            p['status'] = status
            p['reviewed_at'] = datetime.now().isoformat()
            break
    sb.write_json(PENDING_INDEX_KEY, pending)


def update_pending_article(pending_id: str, article: dict) -> bool:
    """Overwrites the article content on a still-pending entry — used when
    adding or changing an image before approving."""
    pending = get_pending()
    found = False
    for p in pending:
        if p['id'] == pending_id:
            p['article'] = article
            found = True
            break
    if found:
        sb.write_json(PENDING_INDEX_KEY, pending)
    return found


def log_ideas_run(candidates: list, generated_ids: list):
    log = sb.read_json(IDEAS_LOG_KEY, [])
    log.append({
        'run_at': datetime.now().isoformat(),
        'candidates_considered': len(candidates),
        'top_candidates': candidates[:10],
        'generated_ids': generated_ids,
    })
    log = log[-200:]
    sb.write_json(IDEAS_LOG_KEY, log)


# ── Learnings ─────────────────────────────────────────────────────────────────

def store_learning(article_id: str, rating: int, feedback: str, articles: list):
    learnings = sb.read_json(LEARNINGS_KEY, [])
    article = next((a for a in articles if a['id'] == article_id), {})
    learnings.append({
        'article_id': article_id,
        'seo_title': article.get('seo_title', ''),
        'rating': rating,
        'feedback': feedback,
        'keywords': article.get('keywords', []),
        'session_summary': _summarise_session(article.get('session', {})),
        'stored_at': datetime.now().isoformat(),
    })
    sb.write_json(LEARNINGS_KEY, learnings)


def get_learnings() -> list:
    return sb.read_json(LEARNINGS_KEY, [])


def get_learning_context() -> str:
    learnings = get_learnings()
    if not learnings:
        return ''

    good = [l for l in learnings if l.get('rating', 0) >= 7]
    bad = [l for l in learnings if l.get('rating', 0) is not None and l.get('rating', 0) < 7 and l.get('feedback')]

    lines = []
    if good:
        lines.append('ARTICLES THAT RATED WELL (7+/10) — use these as quality benchmarks:')
        for l in good[-3:]:
            lines.append(f'- "{l["seo_title"]}" (rated {l["rating"]}/10): {l["session_summary"]}')

    if bad:
        lines.append('\nARTICLES WITH NEGATIVE FEEDBACK — avoid these patterns:')
        for l in bad[-3:]:
            lines.append(f'- "{l["seo_title"]}" (rated {l["rating"]}/10): {l["feedback"]}')

    return '\n'.join(lines)


def _summarise_session(session: dict) -> str:
    parts = []
    if session.get('topic'):
        parts.append(f"Topic: {session['topic']}")
    if session.get('cluster_name'):
        parts.append(f"Cluster: {session['cluster_name']}")
    if session.get('copilot_answers'):
        answers = session['copilot_answers']
        if isinstance(answers, dict):
            for k, v in list(answers.items())[:2]:
                parts.append(f"{k}: {v}")
    return ' | '.join(parts)
