from pathlib import Path

from helomi_common.fs.text import TextFile


def test_text_file_read_write(tmp_path: Path) -> None:
    tf = TextFile(tmp_path / "sample.txt")
    tf.write("Hello, World!")
    assert tf.read() == "Hello, World!"
