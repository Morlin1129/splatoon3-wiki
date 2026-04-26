from crawler import main as cli


def test_parse_args_defaults() -> None:
    args = cli.parse_args([])
    assert args.config is None
    assert args.week is None
    assert args.server is None
    assert args.channel is None
    assert args.force is False


def test_parse_args_force_flag() -> None:
    args = cli.parse_args(["--force"])
    assert args.force is True


def test_parse_args_week_filter() -> None:
    args = cli.parse_args(["--week", "2026-W15"])
    assert args.week == "2026-W15"


def test_parse_args_server_channel_filter() -> None:
    args = cli.parse_args(["--server", "Splatoon道場", "--channel", "戦術談義"])
    assert args.server == "Splatoon道場"
    assert args.channel == "戦術談義"


def test_parse_args_custom_config_path(tmp_path) -> None:
    args = cli.parse_args(["--config", str(tmp_path / "x.yaml")])
    assert args.config == tmp_path / "x.yaml"
