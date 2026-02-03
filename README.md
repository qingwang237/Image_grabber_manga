# 自动漫画下载器

![Wgrabber](https://github.com/qingwang237/Image_grabber_manga/workflows/Wgrabber/badge.svg?branch=master)

The automated images downloader.
漫画下载

## Getting Started

This project uses [uv](https://github.com/astral-sh/uv) for dependency management.

### Installation

```bash
# Install dependencies
uv sync

# Or install with development tools (includes ruff linter and pytest)
uv sync --dev
```

### Usage

```bash
# Run the tool
uv run wgrabber http://www.xxxx.org/photos-index-aid-37288.html

# Or with options
uv run wgrabber http://www.xxxx.org/photos-index-aid-37288.html --folder ~/manga/ --mode crawl

# See all available options
uv run wgrabber --help
```

### Development

```bash
# Run tests
uv run pytest

# Run linter
uv run ruff check .

# Format code
uv run ruff format .
```
