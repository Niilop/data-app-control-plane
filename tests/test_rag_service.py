#!/usr/bin/env python3
"""
Integration tests for the RAG endpoints.
Requires a running server at BASE_URL and a valid API key in the environment.

Run with:  python tests/test_rag_service.py
"""
import json
import time
from typing import Optional
import requests
from datetime import datetime

BASE_URL = "http://127.0.0.1:8000"
TIMEOUT = 30   # seconds to wait for async job to finish
POLL_INTERVAL = 2

SAMPLE_TEXT = (
    "Photosynthesis is the process by which green plants and certain other organisms "
    "use sunlight to synthesize nutrients from carbon dioxide and water. "
    "The overall equation is: 6CO2 + 6H2O + light → C6H12O6 + 6O2. "
    "Chlorophyll in the chloroplasts absorbs the light energy needed for this reaction. "
    "Photosynthesis is the primary source of all the oxygen in Earth's atmosphere."
)


# ── helpers ────────────────────────────────────────────────────────────────────

def ok(label: str, response: requests.Response, expected_status: int = 200):
    passed = response.status_code == expected_status
    mark = "PASS" if passed else "FAIL"
    print(f"[{mark}] {label} — HTTP {response.status_code}")
    if not passed:
        try:
            print(f"       {json.dumps(response.json(), indent=6)}")
        except Exception:
            print(f"       {response.text[:300]}")
    return passed


def get_token() -> Optional[str]:
    ts = datetime.now().strftime("%Y%m%d%H%M%S%f")
    user = {"email": f"ragtest{ts}@example.com", "username": f"ragtest{ts}", "password": "pass123"}

    r = requests.post(f"{BASE_URL}/auth/register", json=user)
    if not ok("Register user", r):
        return None

    r = requests.post(f"{BASE_URL}/auth/login", data={"username": user["email"], "password": user["password"]})
    if not ok("Login user", r):
        return None

    return r.json().get("access_token")


# ── tests ──────────────────────────────────────────────────────────────────────

def test_ingest_sync(headers: dict) -> bool:
    """POST /rag/ingest — chunks and embeds inline, returns chunk count."""
    r = requests.post(
        f"{BASE_URL}/rag/ingest",
        json={"source": "photosynthesis.txt", "text": SAMPLE_TEXT},
        headers=headers,
    )
    if not ok("Sync ingest", r):
        return False

    body = r.json()
    assert body.get("source") == "photosynthesis.txt", f"Unexpected source: {body}"
    assert body.get("chunks_created", 0) >= 1, f"Expected >=1 chunk, got: {body}"
    print(f"       chunks_created={body['chunks_created']}")
    return True


def test_query(headers: dict) -> bool:
    """POST /rag/query — retrieves relevant chunks and returns an LLM answer."""
    r = requests.post(
        f"{BASE_URL}/rag/query",
        json={"question": "What is photosynthesis?", "top_k": 2},
        headers=headers,
    )
    if not ok("RAG query", r):
        return False

    body = r.json()
    assert "answer" in body, f"Missing 'answer': {body}"
    assert isinstance(body.get("sources"), list), f"Missing 'sources': {body}"
    assert isinstance(body.get("chunks"), list), f"Missing 'chunks': {body}"
    assert len(body["answer"]) > 10, "Answer looks too short"
    print(f"       answer (truncated): {body['answer'][:120]}...")
    return True


def test_query_no_docs() -> bool:
    """POST /rag/query without any ingested docs should return 404."""
    # Use a brand-new user who hasn't ingested anything
    ts = datetime.now().strftime("%Y%m%d%H%M%S%f")
    user = {"email": f"empty{ts}@example.com", "username": f"empty{ts}", "password": "pass123"}
    requests.post(f"{BASE_URL}/auth/register", json=user)
    r_login = requests.post(f"{BASE_URL}/auth/login", data={"username": user["email"], "password": user["password"]})
    empty_headers = {"Authorization": f"Bearer {r_login.json().get('access_token')}"}

    r = requests.post(
        f"{BASE_URL}/rag/query",
        json={"question": "What is photosynthesis?"},
        headers=empty_headers,
    )
    return ok("Query with no docs → 404", r, expected_status=404)


def test_ingest_async(headers: dict) -> bool:
    """POST /rag/ingest/async — returns job_id immediately, polls until complete."""
    r = requests.post(
        f"{BASE_URL}/rag/ingest/async",
        json={"source": "async_doc.txt", "text": SAMPLE_TEXT},
        headers=headers,
    )
    if not ok("Async ingest submit", r):
        return False

    body = r.json()
    job_id = body.get("job_id")
    assert job_id, f"Missing job_id in response: {body}"
    assert body.get("status") == "pending", f"Expected pending, got: {body}"
    print(f"       job_id={job_id}")

    # poll until done or timeout
    deadline = time.time() + TIMEOUT
    while time.time() < deadline:
        time.sleep(POLL_INTERVAL)
        poll = requests.get(f"{BASE_URL}/jobs/{job_id}", headers=headers)
        if not ok(f"  Poll job {job_id[:8]}…", poll):
            return False
        status = poll.json().get("status")
        print(f"       status={status}")
        if status == "completed":
            result = poll.json().get("result", {})
            assert result.get("chunks_created", 0) >= 1, f"Expected >=1 chunk in result: {result}"
            print(f"       chunks_created={result['chunks_created']}")
            return True
        if status == "failed":
            print(f"       error: {poll.json().get('error')}")
            print("[FAIL] Async ingest job failed")
            return False

    print("[FAIL] Async ingest timed out")
    return False


def test_ingest_empty_text(headers: dict) -> bool:
    """Ingesting empty text should return 0 chunks without crashing."""
    r = requests.post(
        f"{BASE_URL}/rag/ingest",
        json={"source": "empty.txt", "text": ""},
        headers=headers,
    )
    if not ok("Ingest empty text", r):
        return False
    body = r.json()
    assert body.get("chunks_created") == 0, f"Expected 0 chunks, got: {body}"
    return True


# ── main ───────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'='*55}")
    print("  RAG Integration Tests")
    print(f"{'='*55}\n")

    token = get_token()
    if not token:
        print("\nAborting: could not obtain auth token.")
        return

    headers = {"Authorization": f"Bearer {token}"}
    results = []

    results.append(test_ingest_sync(headers))
    results.append(test_query(headers))
    results.append(test_query_no_docs())
    results.append(test_ingest_async(headers))
    results.append(test_ingest_empty_text(headers))

    passed = sum(results)
    total = len(results)
    print(f"\n{'='*55}")
    print(f"  {passed}/{total} tests passed")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
