# -*- coding: utf-8 -*-
import time
from pathlib import Path
from datetime import datetime


class GeneralFileStorage:
    def __init__(self, root: str):
        self.root = Path(root)
        self.logs_dir    = self.root / "logs"
        self.reports_dir = self.root / "reports"
        self.tmp_dir     = self.root / "tmp"
        for d in (self.logs_dir, self.reports_dir, self.tmp_dir):
            d.mkdir(parents=True, exist_ok=True)

    def new_session(self) -> "Session":
        return Session(self)

    def cleanup(self, days: int = 30):
        cutoff = time.time() - days * 86400
        for d in (self.logs_dir, self.reports_dir, self.tmp_dir):
            for f in d.glob("*"):
                try:
                    if f.is_file() and f.stat().st_mtime < cutoff:
                        f.unlink()
                except OSError:
                    pass


class Session:
    def __init__(self, storage: GeneralFileStorage):
        self.storage = storage
        self.ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = storage.logs_dir / f"run_{self.ts}.log"
        self.report_file = storage.reports_dir / f"run_{self.ts}.txt"
        self._fh = None

    def open(self):
        self._fh = open(self.log_file, "w", encoding="utf-8")

    def log(self, line: str):
        if self._fh:
            self._fh.write(line + "\n")
            self._fh.flush()

    def close(self):
        if self._fh:
            self._fh.close()
            self._fh = None

    def save_report(self, content: str):
        self.report_file.write_text(content, encoding="utf-8")
        return str(self.report_file)

    def tmp_path(self, name: str) -> Path:
        return self.storage.tmp_dir / f"{self.ts}_{name}"

    def __enter__(self):
        self.open(); return self

    def __exit__(self, exc_type, exc, tb):
        self.close()