"""
语音转写脚本
用法:
  python scripts/transcribe.py --url https://www.bilibili.com/video/BVxxx
  python scripts/transcribe.py --audio <path> --bv_id <BV123>
"""

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import time
import urllib.parse
from pathlib import Path

from utils import caption_path, srt_path, segments_to_srt

ASR_BACKEND = "faster-whisper"  # "sensevoice" | "faster-whisper"

# WBI 签名混淆表
MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 16, 20, 36, 34, 17, 6, 22, 48,
    44, 40, 21, 25, 13, 4, 52, 37, 26, 55, 1, 24, 51, 7, 56, 57, 30, 54, 11, 0,
]


def _get_mixin_key(orig: str) -> str:
    return "".join(orig[i] for i in MIXIN_KEY_ENC_TAB)[:32]


def _get_device_cookies() -> str:
    r = subprocess.run(
        ["curl", "-s", "https://api.bilibili.com/x/frontend/finger/spi"],
        capture_output=True, text=True,
    )
    data = json.loads(r.stdout)
    buvid3 = data["data"]["b_3"]
    buvid4 = data["data"]["b_4"]
    return f"buvid3={buvid3}; buvid4={buvid4}; b_nut={int(time.time())}"


def _get_wbi_keys(cookies: str) -> tuple[str, str]:
    r = subprocess.run(
        ["curl", "-s", "-H", f"Cookie: {cookies}", "https://api.bilibili.com/x/web-interface/nav"],
        capture_output=True, text=True,
    )
    data = json.loads(r.stdout)
    wbi = data["data"]["wbi_img"]
    img_key = wbi["img_url"].rsplit("/", 1)[-1].split(".")[0]
    sub_key = wbi["sub_url"].rsplit("/", 1)[-1].split(".")[0]
    return img_key, sub_key


def _sign_params(params: dict, img_key: str, sub_key: str) -> dict:
    mixin_key = _get_mixin_key(img_key + sub_key)
    params = {**params, "wts": str(int(time.time()))}
    query = urllib.parse.urlencode(sorted(params.items()))
    params["w_rid"] = hashlib.md5((query + mixin_key).encode()).hexdigest()
    return params


def _curl_get(url: str, cookies: str) -> str:
    r = subprocess.run(
        ["curl", "-s",
         "-H", "Referer: https://www.bilibili.com",
         "-H", "Origin: https://www.bilibili.com",
         "-H", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
         "-H", f"Cookie: {cookies}", url],
        capture_output=True, text=True,
    )
    return r.stdout


def get_video_info(bvid: str, cookies: str) -> dict:
    raw = _curl_get(f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}", cookies)
    data = json.loads(raw)
    if data.get("code") != 0:
        print(f"获取视频信息失败: {data.get('message')}")
        return {}
    v = data["data"]
    return {
        "aid": v["aid"],
        "cid": v["cid"],
        "title": v["title"],
        "uploader": v["owner"]["name"],
        "duration": v["duration"],
    }


def get_audio_url(aid: int, cid: int, cookies: str) -> str | None:
    img_key, sub_key = _get_wbi_keys(cookies)
    params = _sign_params(
        {"avid": aid, "cid": cid, "qn": 0, "fnver": 0, "fnval": 16, "fourk": 0, "platform": "pc"},
        img_key, sub_key,
    )
    url = "https://api.bilibili.com/x/player/wbi/playurl?" + urllib.parse.urlencode(params)
    raw = _curl_get(url, cookies)
    data = json.loads(raw)
    if data.get("code") != 0:
        print(f"获取音频 URL 失败: {data.get('message')}")
        return None
    audio_formats = data.get("data", {}).get("dash", {}).get("audio", [])
    if not audio_formats:
        print("无可用音频格式")
        return None
    best = audio_formats[0]
    print(f"音频: id={best['id']}, bandwidth={best.get('bandwidth', 0)}")
    return best["baseUrl"]


def download_audio_cdn(url: str, output: Path):
    subprocess.run(
        [
            "curl", "-s", "-L", "-o", str(output),
            "-H", "Referer: https://www.bilibili.com",
            "-H", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            url,
        ],
        check=True,
    )


def resample(input_path: Path, output_path: Path):
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(input_path), "-ar", "16000", "-ac", "1", str(output_path)],
        check=True, capture_output=True,
    )


def fetch_danmaku(aid: int, cid: int) -> list[dict]:
    """从 B站弹幕 API 提取弹幕，转为字幕格式。无需登录，无地域限制。"""
    r = subprocess.run(
        ["curl", "-s", "-H", "Referer: https://www.bilibili.com",
         f"https://api.bilibili.com/x/v2/dm/web/seg.so?type=1&oid={cid}&pid={aid}&segment_index=1"],
        capture_output=True,
    )
    data = r.stdout
    if len(data) < 10:
        return []

    def _varint(buf, p):
        v, s = 0, 0
        while p < len(buf):
            b = buf[p]; p += 1; v |= (b & 0x7f) << s
            if not (b & 0x80): break
            s += 7
        return v, p

    pos, danmakus = 0, []
    while pos < len(data):
        tag = data[pos]; fn = tag >> 3; wt = tag & 7; pos += 1
        if wt == 0:
            _, pos = _varint(data, pos)
        elif wt == 2:
            length, pos = _varint(data, pos)
            chunk = data[pos:pos+length]; pos += length
            if fn == 1:
                ip, dm = 0, {}
                while ip < len(chunk):
                    it = chunk[ip]; ifn = it >> 3; iwt = it & 7; ip += 1
                    if iwt == 0:
                        iv, ip = _varint(chunk, ip)
                        if ifn == 2: dm['time_ms'] = iv
                    elif iwt == 2:
                        il, ip = _varint(chunk, ip)
                        try: s = chunk[ip:ip+il].decode('utf-8')
                        except: s = ''
                        ip += il
                        if ifn == 7: dm['text'] = s
                if 'text' in dm and dm['text'].strip():
                    danmakus.append(dm)
        elif wt == 1: pos += 8
        elif wt == 5: pos += 4

    danmakus.sort(key=lambda d: d.get('time_ms', 0))
    segments = []
    for dm in danmakus:
        t = dm.get('time_ms', 0) / 1000
        segments.append({'start': round(t, 3), 'end': round(t + 3, 3), 'text': dm['text'].strip()})
    return segments


def transcribe_sensevoice(audio_path: Path) -> list[dict]:
    try:
        from funasr import AutoModel
    except ImportError:
        print("funasr 未安装，请运行: pip install funasr")
        sys.exit(1)

    model = AutoModel(
        model="iic/SenseVoiceSmall",
        vad_model="iic/speech_fsmn_vad_zh-cn-16k-common-pytorch",
        punc_model="iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch",
        disable_update=True,
    )
    result = model.generate(input=str(audio_path), language="zh")
    segments = []
    for item in result[0].get("text_info", []):
        segments.append({"start": round(item["start"], 3), "end": round(item["end"], 3), "text": item["text"].strip()})
    if not segments:
        full_text = result[0].get("text", "")
        if full_text:
            segments.append({"start": 0.0, "end": 0.0, "text": full_text.strip()})
    return segments


def transcribe_whisper(audio_path: Path) -> list[dict]:
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("faster-whisper 未安装，请运行: pip install faster-whisper")
        sys.exit(1)

    model = WhisperModel("small", device="cpu", compute_type="int8")
    segments_raw, info = model.transcribe(str(audio_path), language="zh")
    return [{"start": round(seg.start, 3), "end": round(seg.end, 3), "text": seg.text.strip()} for seg in segments_raw]


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

        cookies = _get_device_cookies()
        print(f"设备指纹已获取")

        info = get_video_info(bv_id, cookies)
        if not info:
            print("获取视频信息失败")
            sys.exit(1)

        metadata = {"title": info["title"], "uploader": info["uploader"], "duration": info["duration"]}
        print(f"视频: {info['title']} (aid={info['aid']}, cid={info['cid']})")

        # 路径一：优先提取弹幕（无需下载音频，无地域限制）
        print("尝试提取弹幕...")
        segments = fetch_danmaku(info["aid"], info["cid"])
        if segments:
            print(f"弹幕提取成功: {len(segments)} 条")
            transcript = build_transcript(segments, bv_id, metadata)
        else:
            # 路径二：ASR 转写
            print("无弹幕，尝试 ASR 转写...")
            audio_url = get_audio_url(info["aid"], info["cid"], cookies)
            if not audio_url:
                sys.exit(1)

            with tempfile.TemporaryDirectory() as tmp:
                tmp_dir = Path(tmp)
                m4s_path = tmp_dir / "audio.m4s"
                wav_path = tmp_dir / "audio.wav"

            print("下载音频...")
            download_audio_cdn(audio_url, m4s_path)
            size_mb = m4s_path.stat().st_size / 1024 / 1024
            print(f"下载完成: {size_mb:.1f} MB")

            print("降采样到 16kHz...")
            resample(m4s_path, wav_path)

            print(f"开始转写 (后端: {ASR_BACKEND})...")
            if ASR_BACKEND == "sensevoice":
                segments = transcribe_sensevoice(wav_path)
            else:
                segments = transcribe_whisper(wav_path)
            transcript = build_transcript(segments, bv_id, metadata)
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
