# 微信读书导出工具

一个实验性的微信读书网页端导出工具，用于把当前账号在网页阅读器里可见的书籍内容导出为 Markdown。

它只采集登录账号本来就能阅读的内容，不绕过登录、购买、会员、试读或平台限制。

## 安装

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .[dev]
.\.venv\Scripts\python.exe -m playwright install chromium
```

## 命令

```powershell
weread-export export <reader-url-or-book-id>
weread-export resume <book-id>
weread-export inspect <book-id>
weread-export clean-locks
```

常用参数：

- `--profile <path>`：浏览器登录态目录，默认 `data/browser-profile`。
- `--output <path>`：导出根目录，默认 `output`。
- `--headless`：无界面运行浏览器；默认会显示浏览器，方便扫码登录和观察。
- `--max-pages <n>`：限制本次最多采集页数，适合调试。
- `--overwrite`：删除这本书已有导出后重新开始。

## 输出

每本书写入 `output/<book-id>/`：

- `manifest.json`：书籍元数据、目录、状态和断点摘要。
- `pages/*.json`：逐页采集检查点。
- `chapters/*.md`：按章节重建出的 Markdown。
- `<title>.md`：全书合并 Markdown，只在完整导出后生成。

## 注意事项

首次运行可能需要在弹出的 Chromium 窗口里扫码登录微信读书。登录态会保存在 `--profile` 指定的目录里。

如果浏览器异常退出后 profile 被占用，可以运行：

```powershell
weread-export clean-locks
```

当前版本优先保证可恢复性和可检查性，只导出 Markdown；epub、pdf、图片本地化下载可以后续再加。
