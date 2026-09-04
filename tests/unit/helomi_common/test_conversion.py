from helomi_common.conversion import to_snake_case


def test_to_snake_case() -> None:
    assert to_snake_case("CamelCase") == "camel_case"
    assert to_snake_case("PipelineService") == "pipeline_service"
    assert to_snake_case("STTWorker") == "stt_worker"
    assert to_snake_case("already_snake") == "already_snake"
    assert to_snake_case("TrayApp") == "tray_app"
