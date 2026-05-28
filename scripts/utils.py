import re
import json
from pathlib import Path
from typing import Optional

BILIBILI_RE = re.compile(
    r'https?://(?:www\.)?bilibili\.com/video/([A-Za-z0-9]+)'
)

CAPTIONS_DIR = Path("captions")


def extract_bv_id(url: str) -> Optional[str]:
    m = BILIBILI_RE.search(url.strip())
    return m.group(1) if m else None


def extract_urls(text: str) -> list[str]:
    return list(set(BILIBILI_RE.findall(text)))


def caption_path(bv_id: str) -> Path:
    return CAPTIONS_DIR / f"{bv_id}.json"


def srt_path(bv_id: str) -> Path:
    return CAPTIONS_DIR / f"{bv_id}.srt"


def segments_to_srt(segments: list[dict]) -> str:
    lines = []
    for i, seg in enumerate(segments, 1):
        start = _fmt_time(seg["start"])
        end = _fmt_time(seg["end"])
        lines.append(f"{i}\n{start} --> {end}\n{seg['text']}\n")
    return "\n".join(lines)


def _fmt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
