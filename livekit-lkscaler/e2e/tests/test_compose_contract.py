from pathlib import Path


def test_compose_declares_required_services() -> None:
    compose_file = Path(__file__).resolve().parents[1] / "compose.yaml"
    text = compose_file.read_text(encoding="utf-8")

    for service in ["zk1:", "zk2:", "zk3:", "livekit:", "agent1:", "agent2:"]:
        assert service in text
