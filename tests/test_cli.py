import json
from pathlib import Path

import pytest

from ticket_automation.cli import main


def test_cli_processes_text_without_echoing_sensitive_input(
    tmp_path: Path, capsys
) -> None:
    audit_path = tmp_path / "audit.jsonl"
    card_number = "4111 1111 1111 1111"

    exit_code = main(
        [
            "process",
            "--text",
            f"С карты {card_number} дважды списали деньги",
            "--audit",
            str(audit_path),
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert '"action": "escalate"' in output
    assert card_number not in output
    assert card_number not in audit_path.read_text(encoding="utf-8")


def test_cli_processes_ticket_file(tmp_path: Path, capsys) -> None:
    input_path = tmp_path / "tickets.json"
    audit_path = tmp_path / "audit.jsonl"
    input_path.write_text(
        json.dumps(
            {
                "id": "file-1",
                "channel": "chat",
                "subject": "",
                "text": "Опять не работает.",
                "created_at": "2026-07-25T12:00:00Z",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    main(
        [
            "process",
            "--file",
            str(input_path),
            "--audit",
            str(audit_path),
        ]
    )

    assert '"reason": "low_classification_confidence"' in capsys.readouterr().out


def test_cli_rejects_malformed_ticket_file_without_traceback(
    tmp_path: Path,
    capsys,
) -> None:
    input_path = tmp_path / "tickets.json"
    input_path.write_text("", encoding="utf-8")

    with pytest.raises(SystemExit) as error:
        main(["process", "--file", str(input_path)])

    assert error.value.code == 2
    assert "cannot load tickets" in capsys.readouterr().err


def test_cli_rejects_unknown_classifier_from_environment(
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("TICKET_CLASSIFIER", "bogus")

    with pytest.raises(SystemExit) as error:
        main(["process", "--text", "Общий сбой"])

    assert error.value.code == 2
    assert "TICKET_CLASSIFIER must be one of" in capsys.readouterr().err


def test_cli_rejects_corrupted_classifier_artifact(
    tmp_path: Path,
    capsys,
) -> None:
    model_path = tmp_path / "model.joblib"
    model_path.write_bytes(b"not a joblib artifact")

    with pytest.raises(SystemExit) as error:
        main(
            [
                "process",
                "--text",
                "Общий сбой",
                "--classifier",
                "ml",
                "--classifier-model",
                str(model_path),
            ]
        )

    assert error.value.code == 2
    assert "cannot load classifier artifact" in capsys.readouterr().err


def test_cli_prints_application_version(capsys) -> None:
    with pytest.raises(SystemExit) as error:
        main(["--version"])

    assert error.value.code == 0
    assert capsys.readouterr().out.strip().endswith("0.3.0")
