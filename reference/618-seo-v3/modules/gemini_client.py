import os
import time
from google import genai
from google.genai.errors import ServerError

# Models to try in order of preference — updated April 2026
MODELS = [
    'gemini-3-flash-preview',
    'gemini-2.5-flash-lite',
    'gemini-2.5-flash',
    'gemini-2.5-pro',
    'gemini-3.1-flash-lite-preview',
]

# Override with .env if set
_env_model = os.environ.get('GEMINI_MODEL', '').strip()
if _env_model and _env_model not in MODELS:
    MODELS.insert(0, _env_model)
elif _env_model and _env_model in MODELS:
    # Move preferred model to front
    MODELS.remove(_env_model)
    MODELS.insert(0, _env_model)

MAX_RETRIES = 10
RETRY_DELAY = 7  # seconds between retries
MAX_TOTAL_SECONDS = 90  # hard ceiling — never let one call block the whole pipeline indefinitely


_client = None
def get_client():
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.environ.get('GEMINI_API_KEY', ''))
    return _client

# ── Live progress tracking (polled by frontend) ────────────────────────────────
import threading
_progress_lock = threading.Lock()
_progress = {'status': '', 'model': '', 'attempt': 0, 'max': MAX_RETRIES, 'active': False}

def set_progress(status: str, model: str = '', attempt: int = 0):
    with _progress_lock:
        _progress.update({'status': status, 'model': model, 'attempt': attempt, 'active': True})

def clear_progress():
    with _progress_lock:
        _progress.update({'status': '', 'model': '', 'attempt': 0, 'active': False})

def get_progress() -> dict:
    with _progress_lock:
        return dict(_progress)


def gemini(prompt: str) -> str:
    """
    Try each model in order. For each model, retry up to MAX_RETRIES times
    with RETRY_DELAY seconds between attempts on 503. Move to next model on
    persistent failure. Bounded overall by MAX_TOTAL_SECONDS so a single call
    can never block the pipeline indefinitely, however many retries remain.
    """
    last_error = None
    start_time = time.time()

    for model in MODELS:
        for attempt in range(1, MAX_RETRIES + 1):
            if time.time() - start_time > MAX_TOTAL_SECONDS:
                clear_progress()
                raise Exception(f"Gemini call exceeded {MAX_TOTAL_SECONDS}s overall — giving up rather than hang. Last error: {last_error}")
            try:
                msg = f"Trying {model} — attempt {attempt}/{MAX_RETRIES}..."
                print(f"[Gemini] {msg}")
                set_progress(msg, model, attempt)
                response = get_client().models.generate_content(
                    model=model,
                    contents=prompt,
                )
                set_progress(f"✓ Got response from {model}", model, attempt)
                print(f"[Gemini] ✓ Success with {model}")
                clear_progress()
                return response.text

            except ServerError as e:
                last_error = e
                if attempt < MAX_RETRIES:
                    msg = f"{model} is busy — waiting {RETRY_DELAY}s then retry {attempt+1}/{MAX_RETRIES}..."
                    print(f"[Gemini] {msg}")
                    set_progress(msg, model, attempt)
                    time.sleep(RETRY_DELAY)
                else:
                    msg = f"{model} failed after {MAX_RETRIES} attempts — trying next model..."
                    print(f"[Gemini] {msg}")
                    set_progress(msg, model, attempt)

            except Exception as e:
                last_error = e
                err_str = str(e)
                if '404' in err_str or 'NOT_FOUND' in err_str or 'deprecated' in err_str.lower():
                    msg = f"{model} not available — skipping..."
                    print(f"[Gemini] {msg}")
                    set_progress(msg, model, attempt)
                    break
                if attempt < MAX_RETRIES:
                    msg = f"{model} error — waiting {RETRY_DELAY}s then retry {attempt+1}/{MAX_RETRIES}..."
                    print(f"[Gemini] {msg}")
                    set_progress(msg, model, attempt)
                    time.sleep(RETRY_DELAY)
                else:
                    print(f"[Gemini] {model} failed after {MAX_RETRIES} attempts.")

    clear_progress()
    raise Exception(f"All Gemini models failed. Last error: {last_error}")


def gemini_grounded(prompt: str) -> dict:
    """
    Same retry/timeout behavior as gemini(), but with Google Search grounding
    turned on — the model can pull in live, current search results instead of
    relying only on what it learned during training. Use this for anything
    that needs to be factually current about the real world (new/upcoming
    artists, recent releases) — the plain gemini() function has no way to
    know about anything recent and will confidently invent details instead
    of saying it doesn't know.

    Returns {'text': ..., 'sources': [{'title','uri','domain'}, ...],
    'search_queries': [...]} — sources come from the model's actual search
    results, not from asking it to remember or invent URLs.
    """
    from google.genai import types
    last_error = None
    start_time = time.time()
    search_tool = types.Tool(google_search=types.GoogleSearch())
    config = types.GenerateContentConfig(tools=[search_tool])

    for model in MODELS:
        for attempt in range(1, MAX_RETRIES + 1):
            if time.time() - start_time > MAX_TOTAL_SECONDS:
                clear_progress()
                raise Exception(f"Gemini grounded call exceeded {MAX_TOTAL_SECONDS}s overall — giving up rather than hang. Last error: {last_error}")
            try:
                msg = f"Searching with {model} — attempt {attempt}/{MAX_RETRIES}..."
                print(f"[Gemini] {msg}")
                set_progress(msg, model, attempt)
                response = get_client().models.generate_content(
                    model=model,
                    contents=prompt,
                    config=config,
                )
                sources = []
                search_queries = []
                candidate = response.candidates[0] if response.candidates else None
                gm = getattr(candidate, 'grounding_metadata', None) if candidate else None
                if gm:
                    for chunk in (gm.grounding_chunks or []):
                        web = getattr(chunk, 'web', None)
                        if web:
                            sources.append({'title': web.title, 'uri': web.uri, 'domain': web.domain})
                    search_queries = list(gm.web_search_queries or [])
                set_progress(f"✓ Got grounded response from {model}", model, attempt)
                print(f"[Gemini] ✓ Success with {model} ({len(sources)} sources)")
                clear_progress()
                return {'text': response.text, 'sources': sources, 'search_queries': search_queries}

            except ServerError as e:
                last_error = e
                if attempt < MAX_RETRIES:
                    msg = f"{model} is busy — waiting {RETRY_DELAY}s then retry {attempt+1}/{MAX_RETRIES}..."
                    print(f"[Gemini] {msg}")
                    set_progress(msg, model, attempt)
                    time.sleep(RETRY_DELAY)
                else:
                    msg = f"{model} failed after {MAX_RETRIES} attempts — trying next model..."
                    print(f"[Gemini] {msg}")
                    set_progress(msg, model, attempt)

            except Exception as e:
                last_error = e
                err_str = str(e)
                if '404' in err_str or 'NOT_FOUND' in err_str or 'deprecated' in err_str.lower():
                    msg = f"{model} not available — skipping..."
                    print(f"[Gemini] {msg}")
                    set_progress(msg, model, attempt)
                    break
                if attempt < MAX_RETRIES:
                    msg = f"{model} error — waiting {RETRY_DELAY}s then retry {attempt+1}/{MAX_RETRIES}..."
                    print(f"[Gemini] {msg}")
                    set_progress(msg, model, attempt)
                    time.sleep(RETRY_DELAY)
                else:
                    print(f"[Gemini] {model} failed after {MAX_RETRIES} attempts.")

    clear_progress()
    raise Exception(f"All Gemini models failed (grounded). Last error: {last_error}")
