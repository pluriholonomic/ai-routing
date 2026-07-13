import duckdb

from orcap.analysis import data


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
