"""Verify committed attempt constraints against disposable PostgreSQL."""
import os
import pathlib
import re
import psycopg

assert os.environ.get("FACTORY_CI_REPAIR_TEST_ISOLATED") == "true", "isolated PostgreSQL required"
sql = pathlib.Path("supabase/migrations/20261021213414_durable_ci_repair_requests.sql").read_text()
column = re.search(r"attempt integer not null check \(attempt between 1 and 4\)", sql)
constraint = re.search(r"constraint factory_ci_repair_attempt_bound check \((.*?)\n \),", sql, re.S)
assert column and constraint, "missing migration constraints"
with psycopg.connect(os.environ["FACTORY_CI_REPAIR_TEST_DSN"], autocommit=True) as conn:
    with conn.cursor() as cur:
        cur.execute("create temporary table repair_attempt_probe (attempt integer not null check (attempt between 1 and 4), max_attempts integer not null check (max_attempts between 1 and 3), status text not null, constraint factory_ci_repair_attempt_bound check (" + constraint.group(1) + "))")
        for max_attempts in (1, 2, 3):
            for attempt in range(1, max_attempts + 1):
                cur.execute("insert into repair_attempt_probe values (%s,%s,'queued')", (attempt, max_attempts))
            cur.execute("insert into repair_attempt_probe values (%s,%s,'exhausted')", (max_attempts + 1, max_attempts))
            for attempt, status in ((max_attempts + 1, "queued"), (max_attempts, "exhausted"), (max_attempts + 2, "exhausted")):
                try:
                    cur.execute("insert into repair_attempt_probe values (%s,%s,%s)", (attempt, max_attempts, status))
                except psycopg.errors.CheckViolation:
                    pass
                else:
                    raise AssertionError(f"unexpectedly accepted {attempt=} {max_attempts=} {status=}")
        cur.execute("select count(*) from repair_attempt_probe")
        assert cur.fetchone()[0] == 9
print("PASS: bounded attempts and exhausted sentinel in isolated PostgreSQL")
