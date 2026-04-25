from pipeline.slug import slugify


def test_slugify_ascii() -> None:
    assert slugify("Hello World") == "hello-world"


def test_slugify_preserves_japanese_but_strips_punctuation() -> None:
    assert slugify("海女美術大学 ガチエリア") == "海女美術大学-ガチエリア"
    assert slugify("2 落ち!!") == "2-落ち"


def test_slugify_collapses_whitespace() -> None:
    assert slugify("  a   b  c ") == "a-b-c"


def test_slugify_empty_raises() -> None:
    import pytest

    with pytest.raises(ValueError):
        slugify("   ")
