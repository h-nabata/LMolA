from pathlib import Path

def write_log(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
