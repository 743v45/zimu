"""
语音转写脚本
用法: python scripts/transcribe.py --audio <path> --bv_id <BV123>
"""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from utils import caption_path, srt_path, segments_to_srt

# 默认使用 SenseVoice，回退到 faster-whisper
ASR_BACKEND = "sensevoice"  # "sensevoice" | "faster-whisper"


def download_audio(url: str, output: Path):
    """使用 yt-dlp 下载音频"""
    subprocess.run(
        [
            "yt-dlp",
            "-x",
            "--audio-format", "m4a",
            "--audio-quality", "0",
            "-o", str(output),
            url,
        ],
        check=True,
    )


def resample(input_path: Path, output_path: Path):
    """降采样到 16kHz 单声道 wav"""
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i", str(input_path),
            "-ar", "16000",
            "-ac", "1",
            str(output_path),
        ],
        check=True,
        capture_output=True,
    )


def transcribe_sensevoice(audio_path: Path) -> list[dict]:
    """使用 SenseVoice-Small 转写"""
    try:
        from funasr import AutoModel
    except ImportError:
        print("funasr 未安装，请运行: pip install funasr")
        sys.exit(1)

    model = AutoModel(
        model="iic/SenseVoiceSmall",
        vad_model="iic/speech_fsmn_vad_zh-cn_16k-common-pytorch",
        punc_model="iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch",
        disable_update=True,
    )

    result = model.generate(input=str(audio_path), language="zh")

    segments = []
    for item in result[0].get("text_info", []):
        segments.append({
            "start": round(item["start"], 3),
            "end": round(item["end"], 3),
            "text": item["text"].strip(),
        })

    # fallback: if no segments with timestamps, split full text
    if not segments:
        full_text = result[0].get("text", "")
        if full_text:
            segments.append({"start": 0.0, "end": 0.0, "text": full_text.strip()})

    return segments


def transcribe_whisper(audio_path: Path) -> list[dict]:
    """使用 faster-whisper 转写"""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("faster-whisper 未安装，请运行: pip install faster-whisper")
        sys.exit(1)

    model = WhisperModel("small", device="cpu", compute_type="int8")
    segments_raw, info = model.transcribe(str(audio_path), language="zh")

    segments = []
    for seg in segments_raw:
        segments.append({
            "start": round(seg.start, 3),
            "end": round(seg.end, 3),
            "text": seg.text.strip(),
        })

    return segments


def build_transcript(segments: list[dict], bv_id: str, metadata: dict = None) -> dict:
    full_text = " ".join(s["text"] for s in segments)
    return {
        "bv_id": bv_id,
        "title": (metadata or {}).get("title", ""),
        "uploader": (metadata or {}).get("uploader", ""),
        "duration": (metadata or {}).get("duration", 0),
        "segments": segments,
        "full_text": full_text,
    }


def get_metadata(url: str) -> dict:
    """获取视频元数据"""
    import json as _json
    result = subprocess.run(
        ["yt-dlp", "--dump-json", url],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return {}
    try:
        data = _json.loads(result.stdout.strip().split("\n")[0])
        return {
            "title": data.get("title", ""),
            "uploader": data.get("uploader", ""),
            "duration": data.get("duration", 0),
        }
    except _json.JSONDecodeError:
        return {}


def main():
    parser = argparse.ArgumentParser(description="B站视频转写")
    parser.add_argument("--url", help="B站视频链接")
    parser.add_argument("--bv_id", help="BV 号")
    parser.add_argument("--audio", type=Path, help="本地音频文件路径")
    args = parser.parse_args()

    if not args.url and not args.audio:
        parser.error("需要 --url 或 --audio")

    if args.url:
        from utils import extract_bv_id
        bv_id = args.bv_id or extract_bv_id(args.url)
        if not bv_id:
            print(f"无法解析 BV 号: {args.url}")
            sys.exit(1)

        metadata = get_metadata(args.url)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            m4a_path = tmp_dir / "audio.m4a"
            wav_path = tmp_dir / "audio.wav"

            print(f"下载音频: {args.url}")
            download_audio(args.url, m4a_path)

            print("降采样到 16kHz...")
            resample(m4a_path, wav_path)

            print(f"开始转写 (后端: {ASR_BACKEND})...")
            if ASR_BACKEND == "sensevoice":
                segments = transcribe_sensevoice(wav_path)
            else:
                segments = transcribe_whisper(wav_path)
    else:
        bv_id = args.bv_id or args.audio.stem
        wav_path = args.audio
        metadata = {}

        print(f"转写本地音频: {wav_path}")
        if ASR_BACKEND == "sensevoice":
            segments = transcribe_sensevoice(wav_path)
        else:
            segments = transcribe_whisper(wav_path)

    transcript = build_transcript(segments, bv_id, metadata)
    print(f"转写完成: {bv_id}, {len(segments)} 段, {len(transcript['full_text'])} 字")

    cap_dir = Path("captions")
    cap_dir.mkdir(exist_ok=True)
    (cap_dir / f"{bv_id}.json").write_text(
        json.dumps(transcript, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (cap_dir / f"{bv_id}.srt").write_text(
        segments_to_srt(segments), encoding="utf-8"
    )
    print(f"结果已保存到 captions/{bv_id}.json / .srt")


if __name__ == "__main__":
    main()
