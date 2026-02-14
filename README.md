# 自动漫画下载器

![CI Status](https://github.com/qingwang237/Image_grabber_manga/workflows/CI/badge.svg)

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

# To only keep the cbz file and delete all images
uv run python -m wgrabber --zip-only http://www.xxxx.org/photos-index-aid-37288.html

# See all available options
uv run wgrabber --help
```

### Development

```bash
# Using Makefile (recommended)
make test          # Run tests
make lint          # Run linter
make format        # Format code
make check         # Run both lint and format check
make fix           # Auto-fix issues and format
make help          # Show all available commands

# Or using uv directly
uv run pytest
uv run ruff check .
uv run ruff format .
```
