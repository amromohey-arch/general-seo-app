"""
Storage backend abstraction.

Local disk (default): used whenever GCS_BUCKET_NAME is not set — this is what
runs on your laptop and keeps local testing exactly as it's always worked.

Google Cloud Storage: used when GCS_BUCKET_NAME is set — this is what runs on
Cloud Run, where the local filesystem is wiped every time the container scales
down to zero. Credentials are picked up automatically from Cloud Run's runtime
service account; no key file needed if deployed correctly.

Every function here takes a "key" — a relative path like 'articles_index.json'
or 'articles/abc123_slug.html' — so storage.py doesn't need to know or care
which backend is actually in use.
"""
import os
import json

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'output')
GCS_BUCKET_NAME = os.environ.get('GCS_BUCKET_NAME', '').strip()

_gcs_client = None
_gcs_bucket = None


def _get_bucket():
    global _gcs_client, _gcs_bucket
    if _gcs_bucket is None:
        from google.cloud import storage as gcs_storage
        _gcs_client = gcs_storage.Client()
        _gcs_bucket = _gcs_client.bucket(GCS_BUCKET_NAME)
    return _gcs_bucket


def _local_path(key: str) -> str:
    return os.path.abspath(os.path.join(OUTPUT_DIR, key))


def using_gcs() -> bool:
    return bool(GCS_BUCKET_NAME)


def exists(key: str) -> bool:
    if using_gcs():
        return _get_bucket().blob(key).exists()
    return os.path.exists(_local_path(key))


def read_text(key: str, default: str = None) -> str:
    if using_gcs():
        blob = _get_bucket().blob(key)
        if not blob.exists():
            return default
        return blob.download_as_text()
    path = _local_path(key)
    if not os.path.exists(path):
        return default
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def write_text(key: str, text: str):
    if using_gcs():
        _get_bucket().blob(key).upload_from_string(text, content_type='text/plain; charset=utf-8')
        return
    path = _local_path(key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


def read_json(key: str, default=None):
    text = read_text(key, None)
    if text is None:
        return default if default is not None else []
    return json.loads(text)


def write_json(key: str, data):
    write_text(key, json.dumps(data, indent=2))
