"""
Entry point for the two Railway cron services.

    python run_pipeline.py discover   -> every 3-4h: score and log ideas, generate nothing
    python run_pipeline.py generate   -> 1-2x/day: score, generate up to MAX_PER_RUN full
                                          articles + video scripts, drop them in the
                                          pending queue for review at 618media.com.au's
                                          tool (or wherever APP the app is running)

No copilot Q&A step — per your call, articles generate immediately with whatever the
brand rules / style reference / learning context already provide. Sharpen by editing
the generated article or script directly in the review queue.
"""
import os
import sys
from dotenv import load_dotenv
load_dotenv()

from modules.discovery import run_discovery
from modules.generator import generate_seo_title_description, generate_article_html
from modules.video_script import generate_video_script
from modules.spotlight import run_spotlight as _run_spotlight
from modules.storage import save_pending

MAX_PER_RUN = int(os.environ.get('PIPELINE_MAX_PER_RUN', '2'))
MIN_SCORE_TO_GENERATE = float(os.environ.get('PIPELINE_MIN_SCORE', '30'))
SPOTLIGHT_MAX_PER_RUN = int(os.environ.get('SPOTLIGHT_MAX_PER_RUN', '1'))


def discover_only():
    candidates = run_discovery(max_candidates=10)
    print(f"[Pipeline] Discover run: {len(candidates)} candidates logged.")
    for c in candidates:
        print(f"  score={c['_score']:>5}  {c.get('primary_keyword','')!r}  ({c.get('cluster_name','')})")
    return {
        'candidates_found': len(candidates),
        'top': [{'keyword': c.get('primary_keyword', ''), 'score': c['_score']} for c in candidates[:5]],
    }


def generate():
    candidates = run_discovery(max_candidates=MAX_PER_RUN * 3)  # headroom in case some fail generation
    eligible = [c for c in candidates if c['_score'] >= MIN_SCORE_TO_GENERATE][:MAX_PER_RUN]

    if not eligible:
        msg = f"No candidate cleared the score threshold ({MIN_SCORE_TO_GENERATE})."
        print(f"[Pipeline] {msg} Nothing generated this run — that's the scorer doing its job, not a failure.")
        return {'generated': 0, 'titles': [], 'note': msg}

    generated_titles = []
    for cluster in eligible:
        primary_kw = cluster.get('primary_keyword', '')
        print(f"[Pipeline] Generating: {primary_kw} (score {cluster['_score']})")
        try:
            seo = generate_seo_title_description(cluster, {})
            article = generate_article_html(
                cluster, {}, seo['seo_title'], seo['seo_description'],
            )
            if article.get('error'):
                print(f"[Pipeline]   Article generation failed: {article['error']}")
                continue

            script = generate_video_script(
                article_body_html=article.get('body', ''),
                cluster=cluster,
                seo_title=seo['seo_title'],
                article_slug=article.get('slug', ''),
            )

            entry = save_pending({
                'article': article,
                'cluster': cluster,
                'seo_title': seo['seo_title'],
                'seo_description': seo['seo_description'],
                'video_script': script,
                'score': cluster['_score'],
                'source': 'auto-pipeline',
                'session_data': {'topic': cluster.get('cluster_name', ''), 'auto_generated': True},
            })
            print(f"[Pipeline]   Saved to pending queue: {entry['id']}")
            generated_titles.append(seo['seo_title'])
        except Exception as e:
            print(f"[Pipeline]   Failed on '{primary_kw}': {e}")
            continue

    return {'generated': len(generated_titles), 'titles': generated_titles, 'note': None}


def spotlight():
    """Artist/video commentary content — search-grounded, separate accuracy
    bar from the service-page pipeline since it's about real people."""
    result = _run_spotlight(max_new=SPOTLIGHT_MAX_PER_RUN)
    print(f"[Pipeline] Spotlight run: {result}")
    return result


if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'discover'
    if mode == 'discover':
        discover_only()
    elif mode == 'generate':
        generate()
    elif mode == 'spotlight':
        spotlight()
    else:
        print(f"Unknown mode '{mode}'. Use 'discover', 'generate', or 'spotlight'.")
        sys.exit(1)
