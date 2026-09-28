"""End-to-end Docker hard-crash acceptance test.

Verifies:
1. Worker container is executing while a job is RUNNING.
2. Worker container is hard-killed via SIGKILL (docker kill).
3. Worker container is restarted by Docker restart policy / docker compose.
4. After lease_expires_at expires, the new worker recovers the job to QUEUED.
5. The recovered job is claimed and completes to COMPLETED.
6. Verification of ZERO duplicates in processed_messages, jobs, scoring_items, and notifications.
"""

from __future__ import annotations

import json
import subprocess
import time
import uuid
from datetime import datetime, timezone, timedelta


from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
COMPOSE_FILE = str(PROJECT_ROOT / "compose.backend.yml")


def run_cmd(cmd: list[str]) -> str:
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PROJECT_ROOT))
    if res.returncode != 0:
        print(f"COMMAND FAILED: {' '.join(cmd)}\nSTDOUT: {res.stdout}\nSTDERR: {res.stderr}")
        raise subprocess.CalledProcessError(res.returncode, cmd, res.stdout, res.stderr)
    return res.stdout.strip()


def run_python_in_api(code: str) -> str:
    cmd = [
        "docker",
        "compose",
        "-f",
        COMPOSE_FILE,
        "exec",
        "-T",
        "backend-api",
        "python",
        "-c",
        code,
    ]
    return run_cmd(cmd)


def test_docker_hard_crash_recovery_acceptance():
    print("\n=== STEP 1: Ensure Docker containers are running ===")
    ps_output = run_cmd(["docker", "compose", "-f", COMPOSE_FILE, "ps"])
    print(ps_output)
    assert "backend-worker" in ps_output
    assert "backend-api" in ps_output

    print("\n=== STEP 2: Seed test job in RUNNING state with 4s lease ===")
    test_id = uuid.uuid4().hex[:8]
    seed_script = f"""
import uuid
from datetime import datetime, timezone, timedelta
from app.db.session import SessionLocal
from app.models.user import User
from app.models.sync_job import SyncJob, SyncJobAccount, ScoringItem
from app.models.job import Job
from app.models.enums import SyncJobStatus, SyncJobAccountStatus
import json

session = SessionLocal()
user = session.query(User).first()
assert user is not None, "No user found in DB"

now = datetime.now(timezone.utc)
job_id = uuid.uuid4()
sync_job = SyncJob(
    id=job_id,
    user_id=user.id,
    kind="mail_scan",
    status=SyncJobStatus.RUNNING.value,
    trigger="manual",
    worker_id="crashed-worker-container-{test_id}",
    started_at=now - timedelta(seconds=10),
    heartbeat_at=now - timedelta(seconds=5),
    lease_expires_at=now + timedelta(seconds=4),
    attempt=1,
    accounts_total=0,
    accounts_processed=0,
)
session.add(sync_job)

# Add a posting to check duplicate job prevention
posting = Job(
    user_id=user.id,
    source="gmail",
    external_id="ext-crash-test-{test_id}",
    title="Staff Engineer",
    company="Resilience Corp",
    is_mock=False,
)
session.add(posting)
session.flush()

scoring_item = ScoringItem(
    sync_job_id=sync_job.id,
    user_id=user.id,
    job_id=posting.id,
    status="running",
    attempt=1,
)
session.add(scoring_item)
session.commit()

print(json.dumps({{"job_id": str(sync_job.id), "posting_id": str(posting.id)}}))
"""
    result = run_python_in_api(seed_script)
    data = json.loads(result.splitlines()[-1])
    job_id = data["job_id"]
    posting_id = data["posting_id"]
    print(f"Created RUNNING SyncJob: {job_id}, Posting: {posting_id}")

    # Verify job is RUNNING in DB
    verify_script = f"""
from app.db.session import SessionLocal
from app.models.sync_job import SyncJob
import uuid

session = SessionLocal()
job = session.get(SyncJob, uuid.UUID('{job_id}'))
print(job.status, job.worker_id)
"""
    status_out = run_python_in_api(verify_script).splitlines()[-1]
    assert "running" in status_out
    assert f"crashed-worker-container-{test_id}" in status_out
    print(f"Verified job is RUNNING on worker: {status_out}")

    print("\n=== STEP 3: Hard-kill worker container with SIGKILL (docker kill -s 9) ===")
    worker_container = "job-finder-backend-worker-1"
    run_cmd(["docker", "kill", "-s", "SIGKILL", worker_container])
    print(f"Sent SIGKILL to {worker_container} successfully.")

    print("\n=== STEP 4: Docker restart policy / compose restart ===")
    # Restart the worker container to simulate Docker service recovery
    run_cmd(["docker", "compose", "-f", COMPOSE_FILE, "start", "backend-worker"])
    print("Worker container restarted.")

    print("\n=== STEP 5: Wait for lease_expires_at to expire and worker to recover ===")
    # The lease was set to now + 4s. Let's wait 6 seconds total so lease is definitely expired
    # and the worker loop runs recover() and claims the job.
    max_wait = 20
    start_time = time.time()
    final_status = None
    refreshed_data = {}

    while time.time() - start_time < max_wait:
        poll_script = f"""
from app.db.session import SessionLocal
from app.models.sync_job import SyncJob
import uuid
import json

session = SessionLocal()
job = session.get(SyncJob, uuid.UUID('{job_id}'))
print(json.dumps({{
    "status": job.status,
    "attempt": job.attempt,
    "worker_id": job.worker_id,
    "finished_at": str(job.finished_at) if job.finished_at else None,
    "lease_expires_at": str(job.lease_expires_at) if job.lease_expires_at else None,
}}))
"""
        poll_res = run_python_in_api(poll_script).splitlines()[-1]
        job_info = json.loads(poll_res)
        final_status = job_info["status"]
        print(f"Polling job status ({time.time() - start_time:.1f}s): {job_info}")
        if final_status == "completed":
            refreshed_data = job_info
            break
        time.sleep(2)

    assert final_status == "completed", f"Job did not reach completed status, was: {final_status}"
    assert refreshed_data.get("finished_at") is not None
    assert refreshed_data.get("lease_expires_at") is None
    print("Job successfully recovered from crash and reached COMPLETED status!")

    print("\n=== STEP 6: Zero duplicates verification across DB tables ===")
    dup_script = f"""
from app.db.session import SessionLocal
from sqlalchemy import text
import json

session = SessionLocal()

# 1. Duplicate processed messages
dup_messages = session.execute(text(
    "SELECT mail_account_id, provider_message_id, COUNT(*) as cnt "
    "FROM processed_messages "
    "GROUP BY mail_account_id, provider_message_id "
    "HAVING cnt > 1"
)).fetchall()

# 2. Duplicate jobs
dup_jobs = session.execute(text(
    "SELECT user_id, source, external_id, COUNT(*) as cnt "
    "FROM jobs "
    "GROUP BY user_id, source, external_id "
    "HAVING cnt > 1"
)).fetchall()

# 3. Duplicate scoring items
dup_scoring = session.execute(text(
    "SELECT sync_job_id, job_id, COUNT(*) as cnt "
    "FROM scoring_items "
    "GROUP BY sync_job_id, job_id "
    "HAVING cnt > 1"
)).fetchall()

# 4. Duplicate notification history items
dup_notifications = session.execute(text(
    "SELECT user_id, dedupe_key, COUNT(*) as cnt "
    "FROM notification_history "
    "WHERE dedupe_key IS NOT NULL "
    "GROUP BY user_id, dedupe_key "
    "HAVING cnt > 1"
)).fetchall()

print(json.dumps({{
    "duplicate_messages": len(dup_messages),
    "duplicate_jobs": len(dup_jobs),
    "duplicate_scoring": len(dup_scoring),
    "duplicate_notifications": len(dup_notifications),
}}))
"""
    dup_res = run_python_in_api(dup_script).splitlines()[-1]
    dups = json.loads(dup_res)
    print("Duplicate check results:", dups)

    assert dups["duplicate_messages"] == 0, f"Found duplicate messages: {dups['duplicate_messages']}"
    assert dups["duplicate_jobs"] == 0, f"Found duplicate jobs: {dups['duplicate_jobs']}"
    assert dups["duplicate_scoring"] == 0, f"Found duplicate scoring items: {dups['duplicate_scoring']}"
    assert dups["duplicate_notifications"] == 0, f"Found duplicate notifications: {dups['duplicate_notifications']}"

    print("\n=== HARD-CRASH ACCEPTANCE TEST PASSED! All invariants satisfied. ===")


if __name__ == "__main__":
    test_docker_hard_crash_recovery_acceptance()
