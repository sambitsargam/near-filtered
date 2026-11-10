"""Tests for the cost guards.

These matter because they are the only thing standing between a typo and a
large BigQuery bill, and because they must not be satisfiable by accident —
a commented-out date filter has to fail.
"""

import pytest

from near_filtered.bq import QueryRejected, guard_sql, strip_sql_comments

GOOD = """
SELECT signer_account_id, COUNT(*) AS n
FROM `bigquery-public-data.crypto_near_mainnet_us.transactions`
WHERE block_date BETWEEN @start AND @end
GROUP BY signer_account_id
"""


def test_a_well_formed_query_passes():
    guard_sql(GOOD)


def test_single_partition_equality_passes():
    guard_sql("SELECT status, COUNT(*) AS n FROM t WHERE block_date = @day GROUP BY status")


def test_epoch_date_is_accepted_as_a_partition_column():
    guard_sql("SELECT account_id, liquid FROM b WHERE epoch_date = @day")


def test_select_star_is_rejected():
    with pytest.raises(QueryRejected, match="SELECT \\*"):
        guard_sql("SELECT * FROM t WHERE block_date >= @start")


def test_select_star_rejected_case_insensitively():
    with pytest.raises(QueryRejected):
        guard_sql("select   *  from t where block_date >= @start")


def test_missing_partition_column_is_rejected():
    with pytest.raises(QueryRejected, match="No partition column"):
        guard_sql("SELECT signer_account_id FROM t WHERE signer_account_id = 'x'")


def test_partition_column_selected_but_never_filtered_is_rejected():
    with pytest.raises(QueryRejected, match="never compared"):
        guard_sql("SELECT block_date, COUNT(*) AS n FROM t GROUP BY block_date")


def test_a_commented_out_date_filter_does_not_satisfy_the_guard():
    sql = """
    SELECT signer_account_id FROM t
    -- WHERE block_date BETWEEN @start AND @end
    """
    with pytest.raises(QueryRejected):
        guard_sql(sql)


def test_a_block_commented_date_filter_does_not_satisfy_the_guard():
    sql = """
    SELECT signer_account_id FROM t
    /* WHERE block_date >= @start */
    """
    with pytest.raises(QueryRejected):
        guard_sql(sql)


def test_strip_sql_comments_removes_both_styles():
    out = strip_sql_comments("a -- line\nb /* block */ c")
    assert "line" not in out and "block" not in out
    assert "a" in out and "b" in out and "c" in out


def test_every_shipped_sql_file_satisfies_the_guards():
    """Metadata queries are exempt by design; everything else must pass."""
    from near_filtered import config

    checked = 0
    for path in sorted(config.SQL_DIR.glob("*.sql")):
        sql = path.read_text()
        if "INFORMATION_SCHEMA" in sql or "__TABLES__" in sql:
            continue  # metadata: free, and has no partition column to filter
        guard_sql(sql)
        checked += 1
    assert checked > 0, "no non-metadata SQL files were checked"
