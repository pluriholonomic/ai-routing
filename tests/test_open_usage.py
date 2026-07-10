from orcap.capture_open_usage import docker_runtime_rows, hf_open_model_rows, ollama_library_rows


def test_hf_open_models_preserves_download_definition_and_license():
    rows = hf_open_model_rows(
        [
            {
                "id": "org/model",
                "downloads": 123,
                "likes": 4,
                "gated": False,
                "private": False,
                "pipeline_tag": "text-generation",
                "tags": ["license:apache-2.0"],
            }
        ],
        "20260710T000000Z",
        "2026-07-10",
    )
    assert rows[0]["downloads_30d"] == 123
    assert rows[0]["license"] == "apache-2.0"
    assert rows[0]["public_ungated"]
    assert "not inference usage" in rows[0]["metric_definition"]


def test_ollama_library_parser_reads_ranked_cumulative_pulls():
    rows = ollama_library_rows(
        '<a href="/library/example">example 12.5M Pulls</a>'
        '<a href="/library/other">other 75K Pulls</a>',
        "20260710T000000Z",
        "2026-07-10",
    )
    assert [(r["model_id"], r["cumulative_pulls"], r["rank"]) for r in rows] == [
        ("example", 12_500_000, 1),
        ("other", 75_000, 2),
    ]


def test_docker_runtime_rows_are_not_model_consumption():
    rows = docker_runtime_rows(
        {"vllm/vllm-openai": {"name": "vllm-openai", "pull_count": 99, "star_count": 2}},
        "20260710T000000Z",
        "2026-07-10",
    )
    assert rows[0]["pull_count"] == 99
    assert "not model consumption" in rows[0]["metric_definition"]
