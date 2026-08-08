from __future__ import annotations

import os
import sys
from pathlib import Path


CONFIG_DIR = Path(os.environ.get("APPDATA", Path.home())) / "PhotoRawSync"
LANGUAGE_FILE = CONFIG_DIR / "language.txt"


def selected_language(argv: list[str] | None = None) -> str:
    arguments = list(sys.argv if argv is None else argv)
    try:
        index = arguments.index("--language")
        if index + 1 < len(arguments) and arguments[index + 1] in {"en", "zh"}:
            return arguments[index + 1]
    except ValueError:
        pass
    try:
        language = LANGUAGE_FILE.read_text(encoding="utf-8").strip()
        return "zh" if language == "zh" else "en"
    except OSError:
        return "en"


def main() -> None:
    language = selected_language()
    if language == "zh":
        from photo_organizer_v3 import PhotoOrganizerApp
    else:
        from photo_organizer_en import PhotoOrganizerApp
    app = PhotoOrganizerApp()
    if "--self-test" in sys.argv:
        app.withdraw()
        app.update_idletasks()
        app.destroy()
        return
    app.mainloop()


if __name__ == "__main__":
    main()
