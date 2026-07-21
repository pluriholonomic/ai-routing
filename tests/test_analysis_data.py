import duckdb
import pandas as pd

from orcap.analysis import data
from orcap.analysis.market_scope import (
    is_free_model_id,
    paid_activity_mask,
    paid_model_mask,
    paid_model_sql,
)


def test_q_recovers_from_aborted_shared_transaction(monkeypatch):
    monkeypatch.setenv("ORCAP_ANALYSIS_SOURCE", "local")
    data.reset_connection()
    connection = data.connect()
    connection.sql("create table unique_values (id integer primary key)")
    connection.sql("begin transaction")
    connection.sql("insert into unique_values values (1)")
    try:
        connection.sql("insert into unique_values values (1)")
    except duckdb.ConstraintException:
        pass

    assert data.q("select 1").fetchone() == (1,)
    assert data.connect() is not connection
    data.reset_connection()


def test_paid_market_scope_excludes_only_free_routes():
    ids = pd.Series(
        [
            "openrouter/free",
            "vendor/model:free",
            "vendor/model",
            "vendor/model:nitro",
            "vendor/model:floor",
            None,
        ]
    )
    assert paid_model_mask(ids).tolist() == [False, False, True, True, True, False]
    assert is_free_model_id("VENDOR/MODEL:FREE")
    assert not is_free_model_id("vendor/model:nitro")

    frame = pd.DataFrame(
        {
            "model_permaslug": ["a/model", "b/model", "c/model:free"],
            "variant": ["standard", "free", "standard"],
        }
    )
    assert paid_activity_mask(frame).tolist() == [True, False, False]


def test_paid_market_sql_retains_paid_colon_variants_and_rejects_unsafe_identifiers():
    connection = duckdb.connect()
    values = connection.sql(
        f"""
        select model_id from (values
          ('vendor/model'), ('vendor/model:nitro'), ('vendor/model:free'),
          ('openrouter/free'), (null)
        ) as models(model_id)
        where {paid_model_sql("model_id")}
        order by model_id
        """
    ).fetchall()
    assert values == [("vendor/model",), ("vendor/model:nitro",)]

    try:
        paid_model_sql("model_id; drop table models")
    except ValueError:
        pass
    else:
        raise AssertionError("unsafe identifier was accepted")
