from .database import Job, StatusEvent, now

STATUSES = {"unknown", "active", "suspected_expired", "closed"}


def set_status(db, key, status, reason):
    if status not in STATUSES or not reason.strip():
        raise ValueError("Valid status and nonempty evidence/reason required")
    with db.session.begin() as session:
        job = session.get(Job, key, with_for_update=True)
        if job is None:
            raise KeyError(key)
        stamp = now()
        session.add(StatusEvent(job_key=key, old_status=job.job_status,
                                new_status=status, reason=reason, created_at=stamp))
        job.job_status, job.status_reason = status, reason
        if status in {"active", "closed"}:
            job.last_verified_at = stamp
