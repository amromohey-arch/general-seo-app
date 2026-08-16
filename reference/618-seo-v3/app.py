import os
import json
import threading
import time
from functools import wraps
from flask import Flask, render_template, request, jsonify, session, send_file, redirect, url_for
from werkzeug.security import check_password_hash
from dotenv import load_dotenv
load_dotenv()

from modules.gemini_client import get_progress
from modules.keywords import get_autocomplete_suggestions, expand_keywords_with_ai, cluster_keywords
from modules.generator import generate_copilot_questions, generate_article_html, revise_article, build_prompt_summary, reassemble_article_html
from modules.storage import (
    get_articles, save_article, check_duplicate, get_article_content, update_article_content,
    update_article_rating, get_drafts, save_draft, delete_draft,
    save_sc_token, get_pending, update_pending_status,
    get_article_editable, update_article_editable, update_pending_article,
    get_articles_with_scripts
)
from modules.search_console import get_auth_url, exchange_code, get_sc_keywords

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-618media-seo-2024')

APP_LOGIN_EMAIL = os.environ.get('APP_LOGIN_EMAIL', '')
APP_LOGIN_PASSWORD_HASH = os.environ.get('APP_LOGIN_PASSWORD_HASH', '')

EXEMPT_PATHS = {'/login', '/static'}


@app.before_request
def require_login():
    if not APP_LOGIN_EMAIL or not APP_LOGIN_PASSWORD_HASH:
        return  # login not configured yet — don't lock you out mid-setup
    if request.path.startswith('/static') or request.path == '/login':
        return
    if request.path.startswith('/api/cron/'):
        return  # authenticated separately via CRON_SECRET, not a browser session
    if not session.get('logged_in'):
        return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        if email == APP_LOGIN_EMAIL.strip().lower() and check_password_hash(APP_LOGIN_PASSWORD_HASH, password):
            session['logged_in'] = True
            return redirect(url_for('index'))
        error = 'Wrong email or password.'
    return render_template('login.html', error=error)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/')
def index():
    return render_template('index.html', sc_connected=bool(session.get('sc_token')))

@app.route('/api/progress')
def progress():
    return jsonify(get_progress())



# Search Console
@app.route('/api/sc/auth')
def sc_auth():
    if not os.environ.get('GOOGLE_CLIENT_ID'):
        return jsonify({'error': 'Google credentials not configured.'}), 400
    auth_url, state = get_auth_url()
    session['oauth_state'] = state
    return jsonify({'auth_url': auth_url})

@app.route('/api/sc/callback')
def sc_callback():
    code = request.args.get('code')
    state = request.args.get('state')
    if not code:
        return '<script>window.location="/?sc=error"</script>'
    try:
        token = exchange_code(code, state)
        session['sc_token'] = token
        save_sc_token(token)  # persist for the unattended pipeline (cron has no browser session)
        return '<script>window.location="/?sc=connected"</script>'
    except Exception as e:
        print(f'OAuth error: {e}')
        return '<script>window.location="/?sc=error"</script>'

@app.route('/api/sc/disconnect')
def sc_disconnect():
    session.pop('sc_token', None)
    return jsonify({'ok': True})


# Keywords
@app.route('/api/keywords/research', methods=['POST'])
def research():
    data = request.json or {}
    topic = data.get('topic', '').strip()
    if not topic:
        return jsonify({'error': 'Topic required'}), 400
    autocomplete = get_autocomplete_suggestions(topic)
    sc_keywords = []
    if session.get('sc_token'):
        sc_keywords = get_sc_keywords(session['sc_token'], topic)
    all_so_far = list(set(autocomplete + sc_keywords))
    ai_keywords = expand_keywords_with_ai(topic, all_so_far)
    all_keywords = list(set(all_so_far + ai_keywords))
    return jsonify({'keywords': all_keywords, 'sources': {
        'autocomplete': len(autocomplete),
        'search_console': len(sc_keywords),
        'ai_generated': len(ai_keywords),
        'total': len(all_keywords),
    }})

@app.route('/api/keywords/cluster', methods=['POST'])
def cluster():
    data = request.json or {}
    keywords = data.get('keywords', [])
    topic = data.get('topic', '')
    if not keywords:
        return jsonify({'error': 'Keywords required'}), 400
    clusters = cluster_keywords(keywords, topic)
    return jsonify({'clusters': clusters})


# Article Pipeline
@app.route('/api/article/questions', methods=['POST'])
def questions():
    data = request.json or {}
    cluster = data.get('cluster', {})
    if not cluster:
        return jsonify({'error': 'Cluster required'}), 400
    qs = generate_copilot_questions(cluster)
    return jsonify({'questions': qs})

@app.route('/api/article/suggest-seo', methods=['POST'])
def suggest_seo():
    from modules.generator import generate_seo_title_description
    data = request.json or {}
    cluster = data.get('cluster', {})
    answers = data.get('answers', {})
    if not cluster:
        return jsonify({'error': 'Cluster required'}), 400
    try:
        result = generate_seo_title_description(cluster, answers)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/article/prompt-summary', methods=['POST'])
def prompt_summary():
    data = request.json or {}
    cluster = data.get('cluster', {})
    answers = data.get('answers', {})
    seo_title = data.get('seo_title', '')
    seo_description = data.get('seo_description', '')
    blueprint_sections = data.get('blueprint_sections', [])
    summary = build_prompt_summary(cluster, answers, seo_title, seo_description, blueprint_sections)
    return jsonify({'summary': summary})

@app.route('/api/article/check-duplicate', methods=['POST'])
def check_dup():
    data = request.json or {}
    result = check_duplicate(data.get('topic', ''), data.get('keywords', []))
    return jsonify(result)

@app.route('/api/article/generate', methods=['POST'])
def generate():
    from modules.video_script import generate_video_script
    data = request.json or {}
    cluster = data.get('cluster', {})
    answers = data.get('answers', {})
    seo_title = data.get('seo_title', '').strip()
    seo_description = data.get('seo_description', '').strip()
    image_url = data.get('image_url', '').strip() or None
    image_data = data.get('image_data', '').strip() or None
    prompt_edits = data.get('prompt_edits')
    session_data = data.get('session_data', {})
    if not cluster or not seo_title:
        return jsonify({'error': 'Cluster and SEO title required'}), 400
    result = generate_article_html(
        cluster, answers, seo_title, seo_description,
        image_url=image_url, image_data=image_data, prompt_edits=prompt_edits
    )
    if result.get('error'):
        return jsonify({'error': result['error']}), 500
    try:
        script = generate_video_script(
            article_body_html=result.get('body', ''), cluster=cluster,
            seo_title=seo_title, article_slug=result.get('slug', ''),
        )
    except Exception as e:
        script = {'error': str(e)}
    meta = save_article(result, seo_title, seo_description, session_data, cluster=cluster, image_url=(image_url or ''), video_script=script)
    return jsonify({'article': result, 'meta': meta, 'video_script': script})

@app.route('/api/article/revise', methods=['POST'])
def revise():
    try:
        data = request.json or {}
        article_id = data.get('article_id', '').strip()
        result = revise_article(
            body=data.get('body', ''),
            table_data=data.get('table_data'),
            faq_items=data.get('faq_items', []),
            feedback=data.get('feedback', '').strip(),
            target_section=data.get('target_section', '').strip() or None,
            cluster=data.get('cluster', {}),
            seo_title=data.get('seo_title', ''),
            image_url=data.get('image_url', '').strip() or None,
            image_data=data.get('image_data', '').strip() or None,
        )
        if result.get('error'):
            return jsonify({'error': result['error']}), 500
        if article_id:
            # Editing a specific saved article — persist by its actual id, never guess.
            update_article_editable(
                article_id, fragment=result['fragment'], body=result['body'],
                table_data=data.get('table_data'), faq_items=result['faq_items'],
                word_count=result.get('word_count'), image_url=data.get('image_url', '').strip(),
            )
        else:
            # Wizard's live Step 7 session — no article_id yet in older frontend calls.
            try:
                articles = get_articles()
                if articles:
                    latest = articles[-1]
                    update_article_content(latest['id'], result['fragment'])
            except Exception:
                pass
        return jsonify({'article': result})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/articles/<article_id>/edit')
def get_article_edit_data(article_id):
    data = get_article_editable(article_id)
    if not data:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(data)

@app.route('/api/articles/<article_id>/set-image', methods=['POST'])
def set_article_image(article_id):
    """No AI call — adding a picture is a structural edit, not a rewrite."""
    data = request.json or {}
    image_url = data.get('image_url', '').strip()
    image_data = data.get('image_data', '').strip()
    editable = get_article_editable(article_id)
    if not editable:
        return jsonify({'error': 'Not found'}), 404
    fragment = reassemble_article_html(
        body=editable['body'], table_data=editable['table'], faq_items=editable['faq_items'],
        seo_title=editable['seo_title'], image_url=image_url or None, image_data=image_data or None,
    )
    update_article_editable(
        article_id, fragment=fragment, body=editable['body'], table_data=editable['table'],
        faq_items=editable['faq_items'], image_url=image_url,
    )
    return jsonify({'ok': True, 'fragment': fragment})

@app.route('/api/pending/<pending_id>/set-image', methods=['POST'])
def set_pending_image(pending_id):
    """Same idea for an item still sitting in the review queue."""
    data = request.json or {}
    image_url = data.get('image_url', '').strip()
    image_data = data.get('image_data', '').strip()
    pending_list = get_pending()
    entry = next((p for p in pending_list if p['id'] == pending_id), None)
    if not entry:
        return jsonify({'error': 'Not found'}), 404
    article = entry.get('article', {})
    fragment = reassemble_article_html(
        body=article.get('body', ''), table_data=article.get('table'), faq_items=article.get('faq_items', []),
        seo_title=entry.get('seo_title', ''), image_url=image_url or None, image_data=image_data or None,
    )
    article['fragment'] = fragment
    article['image_url'] = image_url
    update_pending_article(pending_id, article)
    return jsonify({'ok': True, 'fragment': fragment})

@app.route('/api/article/rate', methods=['POST'])
def rate():
    data = request.json or {}
    article_id = data.get('article_id', '')
    rating = data.get('rating')
    feedback = data.get('feedback', '')
    if not article_id or rating is None:
        return jsonify({'error': 'article_id and rating required'}), 400
    update_article_rating(article_id, int(rating), feedback)
    return jsonify({'ok': True})


# Articles & Downloads
@app.route('/api/articles')
def list_articles():
    return jsonify(get_articles())

@app.route('/api/articles/<article_id>/preview')
def preview_article(article_id):
    result = get_article_content(article_id)
    if not result:
        return 'Not found', 404
    _filename, content = result
    return f'<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Preview</title></head><body style="margin:0;background:#F4F3F0">{content}</body></html>'

@app.route('/api/articles/<article_id>/download')
def download_article(article_id):
    from flask import Response
    result = get_article_content(article_id)
    if not result:
        return jsonify({'error': 'Not found'}), 404
    _filename, content = result
    articles = get_articles()
    article = next((a for a in articles if a['id'] == article_id), {})
    filename = article.get('slug', article_id) + '.html'
    return Response(
        content, mimetype='text/html',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )

@app.route('/api/articles/<article_id>/script-download')
def download_article_script(article_id):
    from flask import Response
    from modules.video_script import format_script_text
    editable = get_article_editable(article_id)
    if not editable:
        return jsonify({'error': 'Not found'}), 404
    script = editable.get('video_script') or {}
    if not script or not script.get('sections'):
        return jsonify({'error': 'No script saved for this article'}), 404
    text = format_script_text(script, article_title=editable.get('seo_title', ''))
    slug = next((a.get('slug', article_id) for a in get_articles() if a['id'] == article_id), article_id)
    return Response(
        text, mimetype='text/plain',
        headers={'Content-Disposition': f'attachment; filename="{slug}-reel-script.txt"'}
    )

@app.route('/api/reels')
def list_reels():
    return jsonify(get_articles_with_scripts())

@app.route('/api/reels/download-all')
def download_all_reels():
    import io
    import zipfile
    from flask import Response
    from modules.video_script import format_script_text
    reels = get_articles_with_scripts()
    if not reels:
        return jsonify({'error': 'No scripts saved yet'}), 404
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for r in reels:
            editable = get_article_editable(r['id'])
            if not editable:
                continue
            text = format_script_text(editable['video_script'], article_title=editable.get('seo_title', ''))
            slug = next((a.get('slug', r['id']) for a in get_articles() if a['id'] == r['id']), r['id'])
            zf.writestr(f"{slug}-reel-script.txt", text)
    buf.seek(0)
    return Response(
        buf.read(), mimetype='application/zip',
        headers={'Content-Disposition': 'attachment; filename="618-media-reel-scripts.zip"'}
    )

@app.route('/api/articles/<article_id>/summary-download')
def download_summary(article_id):
    articles = get_articles()
    article = next((a for a in articles if a['id'] == article_id), None)
    if not article:
        return jsonify({'error': 'Not found'}), 404
    session_data = article.get('session', {})
    lines = [
        '618 MEDIA — ARTICLE PROMPT SUMMARY',
        '=' * 50,
        '',
        'Article ID: ' + article_id,
        'Generated: ' + article.get('created_at', ''),
        'Rating: ' + str(article.get('rating', 'Not rated')),
        '',
        'SEO DETAILS',
        '-' * 30,
        'Title: ' + article.get('seo_title', ''),
        'Description: ' + article.get('seo_description', ''),
        'Slug: ' + article.get('slug', ''),
        'Word count: ' + str(article.get('word_count', '')),
        '',
        'KEYWORDS USED',
        '-' * 30,
    ]
    for kw in article.get('keywords', []):
        lines.append('  - ' + kw)
    lines += ['', 'SESSION DETAILS', '-' * 30]
    if session_data:
        for k, v in session_data.items():
            if isinstance(v, (str, int, float)):
                lines.append(str(k) + ': ' + str(v))
            elif isinstance(v, dict):
                lines.append(str(k) + ':')
                for sk, sv in v.items():
                    lines.append('  ' + str(sk) + ': ' + str(sv))
            elif isinstance(v, list):
                lines.append(str(k) + ': ' + ', '.join(str(i) for i in v))
    if article.get('rating_feedback'):
        lines += ['', 'FEEDBACK', '-' * 30, article['rating_feedback']]
    content = '\n'.join(lines)
    import tempfile
    tmp_path = os.path.join(tempfile.gettempdir(), 'summary_' + article_id + '.txt')
    with open(tmp_path, 'w', encoding='utf-8') as f:
        f.write(content)
    return send_file(tmp_path, as_attachment=True, download_name='summary_' + article.get('slug', article_id) + '.txt')


# Pending (from the automated pipeline, awaiting your review)

# A plain Lock has no way to expire, so if a run ever genuinely hung (network
# stall, unhandled edge case), every future scheduled run would be silently
# blocked forever with nobody watching to notice and redeploy. This version
# self-clears after STALE_AFTER_SECONDS — generously longer than any real run
# should take, short enough that a genuine hang doesn't lock things out for days.
_state_lock = threading.Lock()  # only ever held briefly, to check-and-set — never during the actual pipeline run
_pipeline_state = {'running': False, 'started_at': None}
STALE_AFTER_SECONDS = 480  # 8 minutes


def _try_start_pipeline() -> bool:
    with _state_lock:
        now = time.time()
        if _pipeline_state['running'] and _pipeline_state['started_at'] and (now - _pipeline_state['started_at']) < STALE_AFTER_SECONDS:
            return False
        _pipeline_state['running'] = True
        _pipeline_state['started_at'] = now
        return True


def _finish_pipeline():
    with _state_lock:
        _pipeline_state['running'] = False
        _pipeline_state['started_at'] = None


def _run_pipeline_job(job_name):
    from run_pipeline import discover_only, generate, spotlight
    fn = {'discover': discover_only, 'generate': generate, 'spotlight': spotlight}[job_name]
    return fn()


VALID_JOBS = ('discover', 'generate', 'spotlight')


@app.route('/api/pipeline/run/<job_name>', methods=['POST'])
def trigger_pipeline(job_name):
    """Manual trigger from the browser buttons. Session-authenticated via the
    normal login gate. Runs synchronously — the request just takes 10s-2min to
    return, rather than using a background thread, since Cloud Run can freeze
    a container's CPU between requests and silently stall background work."""
    if job_name not in VALID_JOBS:
        return jsonify({'error': f'job must be one of {VALID_JOBS}'}), 400
    if not _try_start_pipeline():
        return jsonify({'error': 'A pipeline run is already in progress — wait for it to finish.'}), 409
    try:
        result = _run_pipeline_job(job_name)
        return jsonify({'ok': True, 'job': job_name, 'result': result})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        _finish_pipeline()


@app.route('/api/cron/<job_name>', methods=['POST'])
def cron_pipeline(job_name):
    """Called by Cloud Scheduler (or Railway cron, if you ever go back), never
    by a browser. Authenticated with a shared secret instead of a session,
    since Scheduler can't log in. Set CRON_SECRET in your environment and
    configure Scheduler to send it as a header: X-Cron-Secret: <value>."""
    expected = os.environ.get('CRON_SECRET', '')
    provided = request.headers.get('X-Cron-Secret', '')
    if not expected or provided != expected:
        return jsonify({'error': 'unauthorized'}), 401
    if job_name not in VALID_JOBS:
        return jsonify({'error': f'job must be one of {VALID_JOBS}'}), 400
    if not _try_start_pipeline():
        return jsonify({'error': 'A pipeline run is already in progress.'}), 409
    try:
        result = _run_pipeline_job(job_name)
        return jsonify({'ok': True, 'job': job_name, 'result': result})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        _finish_pipeline()


@app.route('/api/pending')
def list_pending():
    return jsonify(get_pending())

@app.route('/api/pending/<pending_id>')
def get_pending_item(pending_id):
    pending = next((p for p in get_pending() if p['id'] == pending_id), None)
    if not pending:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(pending)

@app.route('/api/pending/<pending_id>/script-download')
def download_pending_script(pending_id):
    from flask import Response
    from modules.video_script import format_script_text
    pending = next((p for p in get_pending() if p['id'] == pending_id), None)
    if not pending:
        return jsonify({'error': 'Not found'}), 404
    script = pending.get('video_script') or {}
    if not script or not script.get('sections'):
        return jsonify({'error': 'No script for this item'}), 404
    text = format_script_text(script, article_title=pending.get('seo_title', ''))
    return Response(
        text, mimetype='text/plain',
        headers={'Content-Disposition': f'attachment; filename="reel-script-{pending_id}.txt"'}
    )

@app.route('/api/pending/<pending_id>/preview')
def preview_pending(pending_id):
    pending = next((p for p in get_pending() if p['id'] == pending_id), None)
    if not pending:
        return 'Not found', 404
    fragment = (pending.get('article') or {}).get('fragment', '')
    return f'<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Preview</title></head><body style="margin:0;background:#F4F3F0">{fragment}</body></html>'

@app.route('/api/pending/<pending_id>/revise', methods=['POST'])
def revise_pending(pending_id):
    data = request.json or {}
    feedback = data.get('feedback', '').strip()
    if not feedback:
        return jsonify({'error': 'Feedback required'}), 400
    entry = next((p for p in get_pending() if p['id'] == pending_id), None)
    if not entry:
        return jsonify({'error': 'Not found'}), 404
    article = entry.get('article', {})
    result = revise_article(
        body=article.get('body', ''),
        table_data=article.get('table'),
        faq_items=article.get('faq_items', []),
        feedback=feedback,
        target_section=data.get('target_section', '').strip() or None,
        cluster=entry.get('cluster', {}),
        seo_title=entry.get('seo_title', ''),
        image_url=article.get('image_url', '') or None,
    )
    if result.get('error'):
        return jsonify({'error': result['error']}), 500
    article.update({
        'fragment': result['fragment'], 'body': result['body'],
        'faq_items': result['faq_items'], 'word_count': result.get('word_count', article.get('word_count', 0)),
    })
    update_pending_article(pending_id, article)
    return jsonify({'ok': True, 'article': article})


@app.route('/api/pending/<pending_id>/approve', methods=['POST'])
def approve_pending(pending_id):
    pending = next((p for p in get_pending() if p['id'] == pending_id), None)
    if not pending:
        return jsonify({'error': 'Not found'}), 404
    result = pending.get('article', {})
    meta = save_article(
        result, pending.get('seo_title', ''), pending.get('seo_description', ''), pending.get('session_data', {}),
        cluster=pending.get('cluster', {}), video_script=pending.get('video_script', {}),
    )
    update_pending_status(pending_id, 'approved')
    return jsonify({'ok': True, 'article_meta': meta})

@app.route('/api/pending/<pending_id>/reject', methods=['POST'])
def reject_pending(pending_id):
    update_pending_status(pending_id, 'rejected')
    return jsonify({'ok': True})


# Drafts
@app.route('/api/drafts')
def list_drafts():
    return jsonify(get_drafts())

@app.route('/api/drafts/save', methods=['POST'])
def save_draft_route():
    data = request.json or {}
    draft_id = data.get('draft_id', '')
    state = data.get('state', {})
    if not draft_id:
        return jsonify({'error': 'draft_id required'}), 400
    try:
        save_draft(draft_id, state)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/drafts/<draft_id>/delete', methods=['POST'])
def delete_draft_route(draft_id):
    delete_draft(draft_id)
    return jsonify({'ok': True})


# Run
if __name__ == '__main__':
    os.makedirs('output/articles', exist_ok=True)
    from modules.scheduler import start_scheduler
    start_scheduler()
    print('\n' + '=' * 50)
    print('  618 Media SEO Tool v3')
    print('  Running at: http://localhost:5618')
    print('=' * 50 + '\n')
    port = int(os.environ.get('PORT', 5618))
    app.run(debug=False, port=port, host='0.0.0.0', threaded=True)