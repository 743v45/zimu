# 子幕 - B站视频语音转写字幕

用 yt-dlp + SenseVoice/faster-whisper 自动转写 B站视频，通过 GitHub Pages 展示，浏览器插件即查即用。

## 架构

```
用户提交 Issue (含B站链接)
        ↓
GitHub Actions 解析 → Matrix 分派 → 并行转写
        ↓
gh-pages 分支: index.json + captions/{BV}.json/.srt
        ↓
GitHub Pages → 列表页 + 详情页（含内嵌播放器+时间轴字幕）
        ↓
浏览器插件 → B站视频页浮窗查询字幕，一键提交
```

## 快速开始

### 1. Fork 本仓库

### 2. 启用 GitHub Pages

Settings → Pages → 部署源选 **GitHub Actions**

### 3. 开启 Issues

Settings → General → Issues → 勾选

### 4. 配置站点地址

在三个文件中替换 `YOUR_USER/YOUR_REPO` 为你的实际信息：

- `site/detail.html` (fetch path)
- `scripts/build_site.py` (issue submit URL)
- `extension/content.js` (GITHUB_PAGES_BASE + GITHUB_REPO)

### 5. 提交视频

创建 Issue，使用模板「提交视频转写字幕」，填入 B站链接。

## 浏览器扩展

### 手动安装（开发模式）

1. 打开 Chrome → `chrome://extensions`
2. 开启「开发者模式」
3. 加载已解压的扩展 → 选择 `extension/` 目录
4. 打开任意 B站视频页，右侧出现浮窗按钮

### 行为

- **已有字幕** → 显示「📝字幕」，点击展开面板，字幕随视频播放同步高亮
- **无字幕** → 显示「📝提交转写」，点击跳转 GitHub 创建 Issue
- 支持 SPA 路由切换

## 技术栈

| 环节 | 选型 |
|------|------|
| 视频下载 | yt-dlp |
| 音频处理 | ffmpeg |
| 语音识别 | SenseVoice-Small (funasr) / faster-whisper |
| CI/CD | GitHub Actions |
| 展示 | GitHub Pages (纯静态) |
| 扩展 | Chrome Extension MV3 |

## 项目结构

```
zimu/
├── .github/
│   ├── workflows/transcribe.yml     # 自动转写流水线
│   └── ISSUE_TEMPLATE/submit.yaml   # Issue 模板
├── scripts/
│   ├── transcribe.py                # 转写主逻辑
│   ├── build_site.py                # 站点构建
│   └── utils.py                     # 工具函数
├── site/
│   ├── index.html                   # 视频列表页
│   ├── detail.html                  # 字幕详情页
│   └── style.css                    # 样式
├── extension/
│   ├── manifest.json                # 插件配置
│   ├── content.js                   # 核心脚本
│   └── style.css                    # 插件样式
└── README.md
```

## 开发

```bash
# 安装依赖
pip install -U yt-dlp funasr faster-whisper

# 本地测试转写
python scripts/transcribe.py --url https://www.bilibili.com/video/BVxxx

# 构建站点
python scripts/build_site.py
```
