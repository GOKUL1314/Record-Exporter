from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import threading
import time
import uuid

from app.config import SESSION_TTL_SECONDS, UPLOADS_DIR
from app.schemas import PageDetails
from app.services.excel_reader import SheetData, inspect_workbook, read_sheet


@dataclass
class SessionData:
    session_id: str
    filename: str
    file_path: Path
    sheets: list[str]
    default_sheet: str
    parsed_sheets: dict[str, SheetData] = field(default_factory=dict)
    page_details_cache: dict[str, PageDetails] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)


class SessionStore:
    def __init__(
        self,
        uploads_dir: Path = UPLOADS_DIR,
        ttl_seconds: int = SESSION_TTL_SECONDS,
    ) -> None:
        self.uploads_dir = uploads_dir
        self.ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
        self._sessions: dict[str, SessionData] = {}
        self.uploads_dir.mkdir(parents=True, exist_ok=True)

    def create_session(self, filename: str, file_path: Path) -> SessionData:
        self.cleanup_expired()
        wb_info = inspect_workbook(file_path)
        session_id = uuid.uuid4().hex
        now = time.time()
        session = SessionData(
            session_id=session_id,
            filename=filename,
            file_path=file_path,
            sheets=wb_info.sheets,
            default_sheet=wb_info.default_sheet,
            parsed_sheets={wb_info.default_sheet: wb_info.active_sheet_data},
            created_at=now,
            last_accessed=now,
        )
        with self._lock:
            self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> SessionData:
        self.cleanup_expired()
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise KeyError("Session not found or expired. Please upload your file again.")
            session.last_accessed = time.time()
            return session

    def get_sheet_data(self, session_id: str, sheet_name: str) -> SheetData:
        session = self.get_session(session_id)
        with self._lock:
            cached = session.parsed_sheets.get(sheet_name)
        if cached is not None:
            return cached

        sheet_data = read_sheet(session.file_path, sheet_name)
        with self._lock:
            session.parsed_sheets[sheet_name] = sheet_data
        return sheet_data

    def get_cached_page_details(self, session_id: str, url: str) -> PageDetails | None:
        session = self.get_session(session_id)
        with self._lock:
            return session.page_details_cache.get(url)

    def set_cached_page_details(
        self, session_id: str, url: str, details: PageDetails
    ) -> None:
        session = self.get_session(session_id)
        with self._lock:
            session.page_details_cache[url] = details

    def cleanup_expired(self) -> int:
        now = time.time()
        removed = 0
        to_delete_files: list[Path] = []

        with self._lock:
            expired_ids = [
                sid
                for sid, sess in self._sessions.items()
                if (now - sess.last_accessed) > self.ttl_seconds
            ]
            for sid in expired_ids:
                sess = self._sessions.pop(sid)
                to_delete_files.append(sess.file_path)
                removed += 1
            active_paths = {sess.file_path.resolve() for sess in self._sessions.values()}

        for path in to_delete_files:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass

        # Clean up orphaned files in uploads_dir older than TTL.
        if self.uploads_dir.exists():
            for entry in self.uploads_dir.iterdir():
                if entry.name == ".gitkeep" or not entry.is_file():
                    continue
                try:
                    if entry.resolve() in active_paths:
                        continue
                    if (now - entry.stat().st_mtime) > self.ttl_seconds:
                        entry.unlink(missing_ok=True)
                except OSError:
                    pass

        return removed


session_store = SessionStore()
