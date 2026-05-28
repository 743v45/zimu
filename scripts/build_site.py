"""
生成 GitHub Pages 站点数据
用法: python scripts/build_site.py [--output-dir <path>]
"""

import argparse
import json
from pathlib import Path

from utils import CAPTIONS_DIR, load_index, save_index


def rebuild_index(output_dir: Path):
    index = []
    for cap_file in sorted(CAPTIONS_DIR.glob("*.json")):
        data = json.loads(cap_file.read_text(encoding="utf-8"))
        index.append({
            "bv_id": data["bv_id"],
            "title": data.get("title", ""),
            "uploader": data.get("uploader", ""),
            "duration": data.get("duration", 0),
            "segments_count": len(data.get("segments", [])),
            "words_count": len(data.get("full_text", "")),
        })

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"索引已更新: {len(index)} 条 -> {output_dir / 'index.json'}")

    index_json_str = json.dumps(index, ensure_ascii=False)

    list_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>子幕 - B站视频字幕</title>
<link rel="stylesheet" href="style.css">
</head>
<body>
<header>
  <h1>子幕</h1>
  <p>B站视频语音转写字幕 · 点击视频查看详情</p>
</header>
<main>
  <section class="submit-bar">
    <textarea id="url-input" placeholder="粘贴 B站视频链接，每行一个，支持批量提交"></textarea>
    <button id="submit-btn">提交转写</button>
  </section>
  <section id="video-list"></section>
</main>
<script>
const INDEX = {index_json_str};
function render() {{
  const list = document.getElementById('video-list');
  if (INDEX.length === 0) {{
    list.innerHTML = '<p style="color:#999;padding:40px;text-align:center">暂无字幕，提交一个视频开始</p>';
    return;
  }}
  list.innerHTML = INDEX.map(v => `
    <a class="video-card" href="detail.html?bv=${{v.bv_id}}">
      <div class="card-body">
        <h3>${{v.title || '无标题'}}</h3>
        <div class="meta">
          <span>UP: ${{v.uploader || '未知'}}</span>
          <span>${{v.words_count || 0}} 字</span>
          <span>${{v.segments_count || 0}} 段</span>
        </div>
      </div>
    </a>
  `).join('');
}}
render();
document.getElementById('submit-btn').addEventListener('click', () => {{
  const urls = document.getElementById('url-input').value.trim();
  if (!urls) return;
  const lines = urls.split('\\n').filter(Boolean);
  const body = lines.map(u => `- ${{u}}`).join('\\n');
  window.open('https://github.com/YOUR_USER/YOUR_REPO/issues/new?template=submit.yaml&body=' + encodeURIComponent(body));
}});
</script>
</body>
</html>"""

    (output_dir / "index.html").write_text(list_html, encoding="utf-8")
    print(f"站点已生成: {output_dir / 'index.html'}")

    _copy_assets(output_dir)


def _copy_assets(output_dir: Path):
    src = Path("site")
    if src.exists():
        for f in src.iterdir():
            if f.is_file():
                dest = output_dir / f.name
                if not dest.exists():
                    dest.write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
                    print(f"  复制: {f.name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("."))
    args = parser.parse_args()
    rebuild_index(args.output_dir)
