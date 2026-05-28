/**
 * 子幕浏览器插件 - B站字幕查询与提交
 *
 * 行为类似沉浸式翻译:
 * - 进入 B站视频页 → 自动检测 BV 号
 * - 查询 GitHub Pages index.json → 是否有字幕
 * - 有 → 显示「字幕」浮窗按钮，点击展开同步字幕
 * - 无 → 显示「提交转写」按钮
 */

const GITHUB_PAGES_BASE = 'https://YOUR_USER.github.io/zimu';
const GITHUB_REPO = 'YOUR_USER/YOUR_REPO';

let segments = [];
let currentBv = '';

async function main() {
  currentBv = getBV();
  if (!currentBv) return;

  const btn = createFloatingButton();
  document.body.appendChild(btn);

  try {
    const index = await fetchIndex();
    const found = index.find(v => v.bv_id === currentBv);

    if (found) {
      btn.textContent = '📝 字幕';
      btn.dataset.hasSubtitle = 'true';
      await loadSegments();
    } else {
      btn.textContent = '📝 提交转写';
      btn.dataset.hasSubtitle = 'false';
      btn.addEventListener('click', submitForTranscription);
    }
  } catch {
    btn.textContent = '📝 提交转写';
    btn.dataset.hasSubtitle = 'false';
    btn.addEventListener('click', submitForTranscription);
  }
}

function getBV() {
  const m = window.location.pathname.match(/\/video\/(BV\w+)/);
  return m ? m[1] : null;
}

async function fetchIndex() {
  const res = await fetch(`${GITHUB_PAGES_BASE}/index.json`);
  if (!res.ok) throw new Error('Failed to fetch index');
  return await res.json();
}

async function loadSegments() {
  const res = await fetch(`${GITHUB_PAGES_BASE}/captions/${currentBv}.json`);
  if (!res.ok) throw new Error('Failed to load captions');
  const data = await res.json();
  segments = data.segments || [];

  const btn = document.querySelector('.zimu-float-btn');
  if (btn) {
    btn.addEventListener('click', toggleSubtitlePanel);
  }
}

function toggleSubtitlePanel() {
  const existing = document.getElementById('zimu-panel');
  if (existing) {
    existing.remove();
    return;
  }

  const panel = document.createElement('div');
  panel.id = 'zimu-panel';
  panel.innerHTML = `
    <div class="zimu-panel-header">
      <span>字幕</span>
      <button id="zimu-close">✕</button>
    </div>
    <div class="zimu-panel-body">
      ${segments.map((s, i) => `
        <div class="zimu-segment" data-index="${i}" data-start="${s.start}" data-end="${s.end}">
          <span class="zimu-time">${fmt(s.start)}</span>
          <span class="zimu-text">${s.text}</span>
        </div>
      `).join('')}
    </div>
  `;
  document.body.appendChild(panel);

  document.getElementById('zimu-close').addEventListener('click', () => panel.remove());

  const video = document.querySelector('video');
  if (video) {
    video.addEventListener('timeupdate', () => {
      const current = segments.findIndex(
        s => s.start <= video.currentTime && s.end > video.currentTime
      );
      document.querySelectorAll('.zimu-segment').forEach((el, i) => {
        el.classList.toggle('zimu-active', i === current);
        if (i === current) el.scrollIntoView({ block: 'center', behavior: 'smooth' });
      });
    });

    panel.querySelectorAll('.zimu-segment').forEach(el => {
      el.addEventListener('click', () => {
        const start = parseFloat(el.dataset.start);
        video.currentTime = start;
        video.play();
      });
    });
  }
}

function submitForTranscription() {
  const body = `- https://www.bilibili.com/video/${currentBv}`;
  const url = `https://github.com/${GITHUB_REPO}/issues/new?template=submit.yaml&body=${encodeURIComponent(body)}`;
  window.open(url, '_blank');
}

function createFloatingButton() {
  const btn = document.createElement('div');
  btn.className = 'zimu-float-btn';
  btn.id = 'zimu-btn';
  return btn;
}

function fmt(s) {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = (s % 60).toFixed(1);
  return `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(4, '0')}`;
}

// 监听 SPA 路由变化
let lastUrl = location.href;
new MutationObserver(() => {
  if (location.href !== lastUrl) {
    lastUrl = location.href;
    document.getElementById('zimu-btn')?.remove();
    document.getElementById('zimu-panel')?.remove();
    main();
  }
}).observe(document.body, { childList: true, subtree: true });

// 启动
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', main);
} else {
  main();
}
