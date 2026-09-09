def retry_job(job, max_attempts=3):
    for attempt in range(max_attempts):
        try:
            return job.run()
        except ConnectionError:
            if attempt == max_attempts - 1:
                raise


def delete_expired_sessions(sessions, now):
    return sessions.delete_where_expires_before(now)


def export_report(rows, writer):
    for row in rows:
        writer.writerow(row)
