"""
In-process pipeline scheduler.

Runs inside the same container as the Flask app (not a separate Railway
service) so it reads/writes the exact same output/ folder the web UI reads
from. Railway does not support sharing a volume across multiple services, so
this has to live in-process rather than as standalone cron services.

Enabled only when ENABLE_PIPELINE_SCHEDULER=true — off by default so running
the app locally on your laptop doesn't also fire the automated pipeline.
"""
import os
from apscheduler.schedulers.background import BackgroundScheduler

_scheduler = None


def start_scheduler():
    global _scheduler
    if os.environ.get('ENABLE_PIPELINE_SCHEDULER', '').lower() != 'true':
        print("[Scheduler] ENABLE_PIPELINE_SCHEDULER not set to true — pipeline scheduler not started.")
        return
    if _scheduler is not None:
        return  # already running, don't double-start

    from run_pipeline import discover_only, generate

    discover_hours = int(os.environ.get('PIPELINE_DISCOVER_INTERVAL_HOURS', '4'))
    generate_times = os.environ.get('PIPELINE_GENERATE_TIMES', '08:00,16:00')  # local tz, comma-separated HH:MM
    tz = os.environ.get('PIPELINE_TIMEZONE', 'Australia/Sydney')

    _scheduler = BackgroundScheduler(timezone=tz)

    _scheduler.add_job(
        _safe(discover_only), 'interval', hours=discover_hours,
        id='discover', next_run_time=None,  # first run waits one interval; call discover_only() manually to seed immediately
    )

    for t in [t.strip() for t in generate_times.split(',') if t.strip()]:
        hh, mm = t.split(':')
        _scheduler.add_job(
            _safe(generate), 'cron', hour=int(hh), minute=int(mm), id=f'generate-{t}',
        )

    _scheduler.start()
    print(f"[Scheduler] Started. Discover every {discover_hours}h. Generate at {generate_times} ({tz}).")


def _safe(fn):
    """Wrap pipeline jobs so one bad run never kills the scheduler thread."""
    def wrapped():
        try:
            fn()
        except Exception as e:
            print(f"[Scheduler] Job {fn.__name__} failed: {e}")
    wrapped.__name__ = fn.__name__
    return wrapped
