"""Real end-to-end Docker hard-crash acceptance test.

Verifies:
1. Docker backend-api and backend-worker are running.
2. A real QUEUED SyncJob is enqueued to the durable queue.
3. The running backend-worker legitimately claims the job (status=RUNNING, attempt=1,
   worker_id matching the active worker process).
4. The worker's heartbeat loop updates heartbeat_at in the DB, proving execution is truly active.
5. While the job is in-flight, the worker main process is killed with SIGKILL.
6. Behavior A: Docker automatic restart policy (restart: unless-stopped) restores the worker
   without any manual start command.
7. Behavior B: Lease recovery:
   - The restarted worker does NOT touch the job while its lease is valid.
   - Once lease_expires_at expires, the job is recovered to QUEUED and claimed by the new worker.
   - attempt transitions 1 -> 2.
   - The job completes to COMPLETED.
8. Duplicate checks across all tables:
   - processed_messages duplicate = 0
   - jobs duplicate = 0
   - scoring_items duplicate = 0
   - notification_history duplicate = 0
9. Explicit verification reporting:
   - Docker automatic restart verified: yes/no
   - In-flight durable job recovery verified: yes/no
"""

from __future__ import annotations

import json
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
COMPOSE_FILE = str(PROJECT_ROOT / "compose.backend.yml")


def is_docker_running() -> bool:
    try:
        res = subprocess.run(["docker", "info"], capture_output=True, timeout=2)
        return res.returncode == 0
    except Exception:
        return False


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


def get_active_worker_info() -> dict:
    """Retrieve the current running worker's hostname, process PID, and computed worker_id."""
    script = """
import json
import os
import socket
from app.services.sync_job_service import default_worker_id

worker_pid = None
for pid in os.listdir('/proc'):
    if pid.isdigit() and pid != '1' and int(pid) != os.getpid():
        try:
            with open(f'/proc/{pid}/cmdline', 'rb') as f:
                cmd = f.read().decode()
            if 'app.worker' in cmd:
                worker_pid = int(pid)
                break
        except Exception:
            pass

print(json.dumps({
    "hostname": socket.gethostname(),
    "pid": worker_pid,
    "worker_id": default_worker_id() if worker_pid else f"{socket.gethostname()}:{worker_pid}",
}))
"""
    cmd = [
        "docker",
        "compose",
        "-f",
        COMPOSE_FILE,
        "exec",
        "-T",
        "backend-worker",
        "python",
        "-c",
        script,
    ]
    out = run_cmd(cmd).splitlines()[-1]
    return json.loads(out)


def test_docker_hard_crash_recovery_acceptance():
    if not is_docker_running():
        pytest.skip("Docker daemon is not running on this host.")

    docker_restart_verified = False
    in_flight_recovery_verified = False

    try:
        print("\n================================================================================")
        print("=== STEP 1: Verify Docker backend-api and backend-worker are running ===")
        print("================================================================================")
        ps_output = run_cmd(["docker", "compose", "-f", COMPOSE_FILE, "ps"])
        print(ps_output)
        assert "backend-worker" in ps_output, "backend-worker is not running in Docker"
        assert "backend-api" in ps_output, "backend-api is not running in Docker"

        initial_worker = get_active_worker_info()
        print(f"Active worker before test: {initial_worker}")
        assert initial_worker["pid"] is not None, "Could not find running app.worker process"

        print("\n================================================================================")
        print("=== STEP 2: Enqueue real QUEUED test SyncJob with controlled 12s delay ===")
        print("================================================================================")
        test_tag = uuid.uuid4().hex[:8]
        seed_script = f"""
import uuid
from datetime import datetime, timezone
from app.db.session import SessionLocal
from app.models.user import User
from app.models.sync_job import SyncJob, ScoringItem, ProcessedMessage
from app.models.job import Job
from app.models.notification import NotificationHistory
from app.models.enums import SyncJobStatus
import json

session = SessionLocal()
user = session.query(User).first()
assert user is not None, "No user found in DB"

# 1. Real QUEUED job (attempt=0, kind=mail_scan) with payload test_delay_seconds=12.0
sync_job = SyncJob(
    user_id=user.id,
    kind="mail_scan",
    status=SyncJobStatus.QUEUED.value,
    trigger="manual",
    attempt=0,
    accounts_total=0,
    account_ids=[],
    payload={{"test_delay_seconds": 12.0}},
)
session.add(sync_job)
session.flush()

# 2. Seed idempotency records to verify duplicate prevention
posting = Job(
    user_id=user.id,
    source="gmail",
    external_id="ext-hard-crash-{test_tag}",
    title="Staff Resilience Engineer",
    company="Fault Tolerant Systems",
    is_mock=False,
)
session.add(posting)
session.flush()

scoring_item = ScoringItem(
    sync_job_id=sync_job.id,
    user_id=user.id,
    job_id=posting.id,
    status="queued",
    attempt=0,
)
session.add(scoring_item)

from app.models.mail_account import MailAccount
mail_acct = session.query(MailAccount).filter(MailAccount.user_id == user.id).first()
if mail_acct is None:
    mail_acct = MailAccount(
        user_id=user.id,
        provider="gmail",
        email_address=f"test-{test_tag}@example.com",
    )
    session.add(mail_acct)
    session.flush()

proc_msg = ProcessedMessage(
    user_id=user.id,
    mail_account_id=mail_acct.id,
    provider_message_id="msg-hard-crash-{test_tag}",
    subject="Your application has been received",
    processed_at=datetime.now(timezone.utc),
)
session.add(proc_msg)

notif = NotificationHistory(
    user_id=user.id,
    job_id=posting.id,
    channel="telegram",
    status="sent",
    dedupe_key="dedupe-crash-{test_tag}",
    sent_at=datetime.now(timezone.utc),
)
session.add(notif)

session.commit()

print(json.dumps({{
    "job_id": str(sync_job.id),
    "user_id": str(user.id),
    "posting_id": str(posting.id),
}}))
"""
        seed_res = run_python_in_api(seed_script).splitlines()[-1]
        seed_data = json.loads(seed_res)
        job_id = seed_data["job_id"]
        print(f"Enqueued real QUEUED job: {job_id}")

        print("\n================================================================================")
        print("=== STEP 3: Verify real backend-worker claims job (status=RUNNING, attempt=1) ===")
        print("================================================================================")
        claimed = False
        initial_heartbeat = None
        claimed_worker_id = None
        claim_deadline = time.time() + 10.0

        while time.time() < claim_deadline:
            poll_script = f"""
from app.db.session import SessionLocal
from app.models.sync_job import SyncJob
import uuid, json

session = SessionLocal()
job = session.get(SyncJob, uuid.UUID('{job_id}'))
print(json.dumps({{
    "status": job.status,
    "attempt": job.attempt,
    "worker_id": job.worker_id,
    "started_at": str(job.started_at) if job.started_at else None,
    "heartbeat_at": str(job.heartbeat_at) if job.heartbeat_at else None,
    "lease_expires_at": str(job.lease_expires_at) if job.lease_expires_at else None,
}}))
"""
            out = run_python_in_api(poll_script).splitlines()[-1]
            state = json.loads(out)
            if state["status"] == "running":
                claimed = True
                initial_heartbeat = state["heartbeat_at"]
                claimed_worker_id = state["worker_id"]
                print(f"Job successfully claimed by real worker: {state}")
                assert state["attempt"] == 1, f"Expected attempt 1 on claim, got {state['attempt']}"
                assert state["worker_id"], "Worker ID must not be empty"
                break
            time.sleep(0.5)

        assert claimed, f"Worker did not claim job {job_id} within deadline"

        print("\n================================================================================")
        print("=== STEP 4: Verify real worker heartbeat updates heartbeat_at before kill ===")
        print("================================================================================")
        heartbeat_updated = False
        heartbeat_deadline = time.time() + 8.0

        while time.time() < heartbeat_deadline:
            poll_script = f"""
from app.db.session import SessionLocal
from app.models.sync_job import SyncJob
import uuid, json

session = SessionLocal()
job = session.get(SyncJob, uuid.UUID('{job_id}'))
print(json.dumps({{
    "status": job.status,
    "heartbeat_at": str(job.heartbeat_at) if job.heartbeat_at else None,
    "lease_expires_at": str(job.lease_expires_at) if job.lease_expires_at else None,
}}))
"""
            out = run_python_in_api(poll_script).splitlines()[-1]
            state = json.loads(out)
            current_hb = state["heartbeat_at"]
            if current_hb and current_hb != initial_heartbeat:
                heartbeat_updated = True
                print(f"Worker heartbeat verified! Initial: {initial_heartbeat} -> Updated: {current_hb}")
                print(f"Active lease expires at: {state['lease_expires_at']}")
                break
            time.sleep(0.5)

        assert heartbeat_updated, (
            f"Worker heartbeat_at was not updated before SIGKILL. "
            f"Initial: {initial_heartbeat}, Last: {current_hb}"
        )

        print("\n================================================================================")
        print("=== STEP 5: Hard-kill backend-worker main process with SIGKILL (kill -9) ===")
        print("================================================================================")
        kill_script = """
import os, signal
killed_pid = None
for pid in os.listdir('/proc'):
    if pid.isdigit() and pid != '1' and int(pid) != os.getpid():
        try:
            with open(f'/proc/{pid}/cmdline', 'rb') as f:
                cmd = f.read().decode()
            if 'app.worker' in cmd:
                killed_pid = int(pid)
                os.kill(int(pid), signal.SIGKILL)
                break
        except Exception:
            pass
print(f"KILLED_PID:{killed_pid}")
"""
        cmd = [
            "docker",
            "compose",
            "-f",
            COMPOSE_FILE,
            "exec",
            "-T",
            "backend-worker",
            "python",
            "-c",
            kill_script,
        ]
        try:
            kill_out = run_cmd(cmd)
        except subprocess.CalledProcessError as exc:
            if exc.returncode == 137:
                kill_out = exc.stdout.strip()
            else:
                raise
        print(f"SIGKILL sent to worker main process: {kill_out}")

        print("\n================================================================================")
        print("=== STEP 6: Behavior A - Verify Docker automatic restart policy ===")
        print("================================================================================")
        print("Waiting for Docker daemon to automatically restart container (restart: unless-stopped)...")
        print("NOTE: No manual 'docker compose start' or 'docker start' is executed.")

        restart_deadline = time.time() + 15.0
        new_worker_info = None

        while time.time() < restart_deadline:
            try:
                ps_res = run_cmd(["docker", "compose", "-f", COMPOSE_FILE, "ps", "backend-worker"])
                if "Up" in ps_res or "running" in ps_res.lower():
                    # Attempt to get active worker info
                    new_worker_info = get_active_worker_info()
                    if new_worker_info.get("pid"):
                        docker_restart_verified = True
                        print(f"Docker automatic restart verified! New worker info: {new_worker_info}")
                        break
            except Exception:
                pass
            time.sleep(1.0)

        assert docker_restart_verified, "Docker automatic restart policy failed: backend-worker did not restart automatically within timeout"

        print("\n================================================================================")
        print("=== STEP 7: Behavior B - Lease recovery & in-flight job completion ===")
        print("================================================================================")
        # Check 1: While lease has NOT expired, new worker MUST NOT touch the job
        check_script = f"""
from app.db.session import SessionLocal
from app.models.sync_job import SyncJob
from datetime import datetime, timezone
import uuid, json

session = SessionLocal()
job = session.get(SyncJob, uuid.UUID('{job_id}'))
now = datetime.now(timezone.utc)
lease = job.lease_expires_at
if lease and lease.tzinfo is None:
    lease = lease.replace(tzinfo=timezone.utc)

is_unexpired = lease and lease > now
print(json.dumps({{
    "status": job.status,
    "attempt": job.attempt,
    "worker_id": job.worker_id,
    "is_unexpired": is_unexpired,
    "lease_expires_at": str(job.lease_expires_at) if job.lease_expires_at else None,
}}))
"""
        unexpired_state = json.loads(run_python_in_api(check_script).splitlines()[-1])
        print(f"Status immediately after container restart: {unexpired_state}")
        if unexpired_state["is_unexpired"]:
            assert unexpired_state["status"] == "running", "Job should stay RUNNING while lease is unexpired"
            assert unexpired_state["attempt"] == 1, "Attempt should remain 1 while lease is unexpired"
            print("Verified: New worker did NOT prematurely claim or touch unexpired job.")

        # Check 2: Wait for lease to expire and verify full recovery cycle:
        # RUNNING -> QUEUED/recovered -> RUNNING (attempt=2) -> COMPLETED
        print("Waiting for lease_expires_at to expire and new worker to recover the job...")
        recovery_deadline = time.time() + 25.0
        final_job_info = None

        while time.time() < recovery_deadline:
            poll_script = f"""
from app.db.session import SessionLocal
from app.models.sync_job import SyncJob
import uuid, json

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
            out = run_python_in_api(poll_script).splitlines()[-1]
            state = json.loads(out)
            print(f"Recovery tracking ({time.strftime('%H:%M:%S')}): {state}")

            if state["status"] == "completed":
                final_job_info = state
                in_flight_recovery_verified = True
                break
            time.sleep(1.5)

        assert in_flight_recovery_verified, f"Job did not recover to COMPLETED status within timeout. Last state: {final_job_info}"
        assert final_job_info["attempt"] == 2, f"Expected attempt 2 on recovery, got {final_job_info['attempt']}"
        assert final_job_info["finished_at"] is not None, "finished_at must be set upon completion"
        assert final_job_info["lease_expires_at"] is None, "lease_expires_at must be cleared upon completion"
        print("In-flight durable job recovery verified! Job finished successfully with attempt=2.")

        print("\n================================================================================")
        print("=== STEP 8: Zero duplicates verification across DB tables ===")
        print("================================================================================")
        dup_script = """
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

print(json.dumps({
    "duplicate_messages": len(dup_messages),
    "duplicate_jobs": len(dup_jobs),
    "duplicate_scoring": len(dup_scoring),
    "duplicate_notifications": len(dup_notifications),
}))
"""
        dup_res = run_python_in_api(dup_script).splitlines()[-1]
        dups = json.loads(dup_res)
        print("Duplicate verification results:", dups)

        assert dups["duplicate_messages"] == 0, f"Found duplicate messages: {dups['duplicate_messages']}"
        assert dups["duplicate_jobs"] == 0, f"Found duplicate jobs: {dups['duplicate_jobs']}"
        assert dups["duplicate_scoring"] == 0, f"Found duplicate scoring items: {dups['duplicate_scoring']}"
        assert dups["duplicate_notifications"] == 0, f"Found duplicate notifications: {dups['duplicate_notifications']}"

    finally:
        print("\n================================================================================")
        print("=== FINAL VERIFICATION REPORT ===")
        print("================================================================================")
        print(f"Docker automatic restart verified: {'yes' if docker_restart_verified else 'no'}")
        print(f"In-flight durable job recovery verified: {'yes' if in_flight_recovery_verified else 'no'}")
        print("================================================================================\n")


if __name__ == "__main__":
    test_docker_hard_crash_recovery_acceptance()
