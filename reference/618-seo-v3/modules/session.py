import os
import json
from datetime import datetime

SESSION_FILE = os.path.join(os.path.dirname(__file__), '..', 'output', 'session.json')


def save_session(data: dict):
    """Save current progress so it can be resumed."""
    path = os.path.abspath(SESSION_FILE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data['saved_at'] = datetime.now().isoformat()
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    print(f"[Session] Progress saved at step: {data.get('step', '?')}")


def load_session() -> dict | None:
    """Load saved session if it exists."""
    path = os.path.abspath(SESSION_FILE)
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def clear_session():
    """Clear session after successful article generation."""
    path = os.path.abspath(SESSION_FILE)
    if os.path.exists(path):
        os.remove(path)
    print("[Session] Session cleared.")
