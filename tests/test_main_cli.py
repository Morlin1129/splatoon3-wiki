import pytest

from pipeline import main


def test_parse_args_single_stage() -> None:
    args = main.parse_args(["--stage", "ingest"])
    assert args.stage == "ingest"
    assert args.all is False


def test_parse_args_all() -> None:
    args = main.parse_args(["--all"])
    assert args.all is True


def test_parse_args_requires_one(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(SystemExit):
        main.parse_args([])


def test_parse_args_rejects_unknown_stage() -> None:
    with pytest.raises(SystemExit):
        main.parse_args(["--stage", "bogus"])


def test_parse_args_accepts_index_stage() -> None:
    args = main.parse_args(["--stage", "index"])
    assert args.stage == "index"


def test_parse_args_accepts_consolidate_stage() -> None:
    args = main.parse_args(["--stage", "consolidate"])
    assert args.stage == "consolidate"


def test_stage_names_order_runs_consolidate_between_classify_and_cluster() -> None:
    names = main.STAGE_NAMES
    assert names.index("consolidate") == names.index("classify") + 1
    assert names.index("cluster") == names.index("consolidate") + 1
