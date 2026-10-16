"""Filesystem storage for uploaded media (coffee images, shot videos, telemetry)."""

import uuid
from collections.abc import Collection
from pathlib import Path

from werkzeug.datastructures import FileStorage

IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif"})
VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".webm", ".avi", ".mkv"})
TELEMETRY_SUBDIR = "telemetry"
THUMBNAIL_SUFFIX = ".png"


def thumbnail_name(telemetry_filename: str) -> str:
    """Return the PNG thumbnail filename paired with a telemetry JSON file.

    Args:
        telemetry_filename: Stored telemetry filename (``<uuid>.json``).

    Returns:
        The sibling thumbnail filename (``<uuid>.png``).
    """
    return Path(telemetry_filename).with_suffix(THUMBNAIL_SUFFIX).name


class MediaStorage:
    """Saves and deletes uploaded files under a single media root directory."""

    def __init__(self, root: str | Path) -> None:
        """Create storage rooted at ``root``.

        Args:
            root: Media directory (created on first write).
        """
        self.root = Path(root)

    @property
    def telemetry_dir(self) -> Path:
        """Directory holding telemetry JSON files and their thumbnails."""
        return self.root / TELEMETRY_SUBDIR

    def save_upload(
        self, upload: FileStorage, allowed: Collection[str], default_ext: str
    ) -> str:
        """Save an upload under a fresh UUID filename.

        Args:
            upload: Uploaded file.
            allowed: Permitted lowercase extensions (with dot).
            default_ext: Extension used when the upload's is not allowed.

        Returns:
            The stored filename.
        """
        ext = Path(upload.filename or "").suffix.lower()
        if ext not in allowed:
            ext = default_ext
        filename = f"{uuid.uuid4()}{ext}"
        self.root.mkdir(parents=True, exist_ok=True)
        upload.save(self.root / filename)
        return filename

    def delete(self, filename: str) -> None:
        """Delete a stored file if it exists.

        Args:
            filename: Stored filename.
        """
        (self.root / filename).unlink(missing_ok=True)

    def save_telemetry(self, payload: bytes, thumbnail: bytes) -> str:
        """Atomically save telemetry JSON and its PNG thumbnail.

        Both files are written to temporaries and renamed into place; on any
        OS error every partial file is removed.

        Args:
            payload: Telemetry JSON bytes.
            thumbnail: Rendered PNG bytes.

        Returns:
            The stored telemetry filename.

        Raises:
            OSError: If either file cannot be written.
        """
        stem = str(uuid.uuid4())
        filename = f"{stem}.json"
        directory = self.telemetry_dir
        directory.mkdir(parents=True, exist_ok=True)
        json_path = directory / filename
        thumbnail_path = directory / f"{stem}{THUMBNAIL_SUFFIX}"
        json_temp = directory / f".{stem}.json.tmp"
        thumbnail_temp = directory / f".{stem}{THUMBNAIL_SUFFIX}.tmp"
        try:
            json_temp.write_bytes(payload)
            thumbnail_temp.write_bytes(thumbnail)
            json_temp.replace(json_path)
            thumbnail_temp.replace(thumbnail_path)
        except OSError:
            for path in (json_temp, thumbnail_temp, json_path, thumbnail_path):
                path.unlink(missing_ok=True)
            raise
        return filename

    def delete_telemetry(self, filename: str) -> None:
        """Delete a telemetry file and its thumbnail if they exist.

        Args:
            filename: Stored telemetry filename.
        """
        (self.telemetry_dir / filename).unlink(missing_ok=True)
        (self.telemetry_dir / thumbnail_name(filename)).unlink(missing_ok=True)
