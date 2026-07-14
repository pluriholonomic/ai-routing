from orcap.analysis.h19_text import _provider_homepage_frame


def test_provider_homepage_frame_handles_unavailable_directory() -> None:
    frame = _provider_homepage_frame(None)

    assert frame.empty
    assert frame.columns.tolist() == [
        "slug",
        "provider",
        "homepage",
        "pricing_strategy",
        "byok_enabled",
    ]


def test_provider_homepage_frame_extracts_favicon_target() -> None:
    frame = _provider_homepage_frame(
        {
            "data": [
                {
                    "slug": "example",
                    "displayName": "Example",
                    "icon": {"url": "https://favicon.test/?url=https%3A%2F%2Fexample.com"},
                    "pricingStrategy": "cost_based",
                    "byokEnabled": True,
                }
            ]
        }
    )

    assert frame.to_dict("records") == [
        {
            "slug": "example",
            "provider": "Example",
            "homepage": "https://example.com",
            "pricing_strategy": "cost_based",
            "byok_enabled": True,
        }
    ]
