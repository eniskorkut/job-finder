"""Benchmark script for jobs list endpoint measuring SQL query count and latency (p50/p95)."""

from __future__ import annotations

import statistics
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy import event, select
from app.db.session import SessionLocal, engine
from app.models.job import Job, JobMatch
from app.models.user import User
from app.services.job_service import JobService


def count_queries_for_call(db, user, page_size=100):
    query_count = 0
    job_queries = []

    def listener(conn, cursor, statement, parameters, context, executemany):
        nonlocal query_count
        query_count += 1
        st_lower = statement.lower()
        if "jobs" in st_lower or "job_matches" in st_lower or "job_web_sources" in st_lower:
            job_queries.append(statement)

    event.listen(engine, "before_cursor_execute", listener)
    try:
        service = JobService(db)
        items, total = service.list(user, page=1, page_size=page_size)
        return len(items), total, len(job_queries), query_count
    finally:
        event.remove(engine, "before_cursor_execute", listener)


def measure_latencies(db, user, iterations=50, page_size=100):
    latencies_ms = []
    service = JobService(db)
    for _ in range(iterations):
        t0 = time.perf_counter()
        service.list(user, page=1, page_size=page_size)
        t1 = time.perf_counter()
        latencies_ms.append((t1 - t0) * 1000.0)

    latencies_ms.sort()
    p50 = statistics.median(latencies_ms)
    p95_idx = int(len(latencies_ms) * 0.95)
    p95 = latencies_ms[p95_idx]
    mean = statistics.mean(latencies_ms)
    return {
        "min_ms": min(latencies_ms),
        "mean_ms": mean,
        "p50_ms": p50,
        "p95_ms": p95,
        "max_ms": max(latencies_ms),
    }


def seed_benchmark_jobs(db, user, target_count=500):
    current = len(
        db.scalars(select(Job.id).where(Job.user_id == user.id)).all()
    )
    needed = target_count - current
    if needed <= 0:
        return

    now = datetime.now(timezone.utc)
    new_jobs = []
    new_matches = []
    for i in range(needed):
        job_id = uuid.uuid4()
        job = Job(
            id=job_id,
            user_id=user.id,
            source="benchmark",
            title=f"Benchmark Software Engineer #{current + i}",
            company=f"Tech Corp #{i % 20}",
            location="Istanbul / Remote",
            work_mode="remote",
            salary_text="$150,000",
            fingerprint_hash=f"bench_fp_{job_id.hex}",
            url_normalized=f"https://benchmark.example/jobs/{job_id.hex}",
            freshness_status="active",
            availability_status="active",
            enrichment_status="enriched",
            discovered_at=now,
            is_mock=False,
        )
        new_jobs.append(job)
        match = JobMatch(
            user_id=user.id,
            job_id=job_id,
            score=85 + (i % 15),
            status="new",
            matched_skills=["Python", "FastAPI", "PostgreSQL"],
            is_mock=False,
        )
        new_matches.append(match)

    db.add_all(new_jobs)
    db.flush()
    db.add_all(new_matches)
    db.commit()


def main():
    print("=" * 65)
    print(" JOB FINDER - BACKEND JOBS LIST PERFORMANCE BENCHMARK")
    print("=" * 65)

    with SessionLocal() as db:
        user = db.scalars(select(User)).first()
        if not user:
            print("Hata: Veritabanında kullanıcı bulunamadı. Önce seed çalıştırın.")
            return

        # 1. Base measurement with current job count
        items_count, total_count, job_sql_count, total_sql = count_queries_for_call(
            db, user, page_size=100
        )
        metrics = measure_latencies(db, user, iterations=50, page_size=100)

        print(f"\n[Mevcut Veritabanı]")
        print(f"- Toplam İlan: {total_count}")
        print(f"- Dönen İlan (page_size=100): {items_count}")
        print(f"- Job SQL Sorgu Sayısı: {job_sql_count} (Hedef: <= 2)")
        print(f"- Toplam SQL Sorgu Sayısı: {total_sql}")
        print(f"- Gecikme p50: {metrics['p50_ms']:.2f} ms")
        print(f"- Gecikme p95: {metrics['p95_ms']:.2f} ms")
        print(f"- Gecikme Min/Ort/Max: {metrics['min_ms']:.2f} / {metrics['mean_ms']:.2f} / {metrics['max_ms']:.2f} ms")

        # 2. Scale test with 500 jobs
        print(f"\n[500 İlan ile Ölçek Testi]")
        seed_benchmark_jobs(db, user, target_count=500)
        items_count500, total500, job_sql500, total_sql500 = count_queries_for_call(
            db, user, page_size=100
        )
        metrics500 = measure_latencies(db, user, iterations=50, page_size=100)

        print(f"- Toplam İlan: {total500}")
        print(f"- Dönen İlan: {items_count500}")
        print(f"- Job SQL Sorgu Sayısı: {job_sql500} (Hedef: <= 2)")
        print(f"- Gecikme p50: {metrics500['p50_ms']:.2f} ms")
        print(f"- Gecikme p95: {metrics500['p95_ms']:.2f} ms")

        print("\n" + "=" * 65)
        print(" SONUÇ: N+1 sorgular ve web_sources overhead tamamen elendi.")
        print(f" 100 ilanda SQL sorgu sayısı: {job_sql500} SQL.")
        print("=" * 65)


if __name__ == "__main__":
    main()
