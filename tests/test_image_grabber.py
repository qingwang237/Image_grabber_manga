"""
Tests for async ImageGrabber class.
"""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from wgrabber.image_grabber import ImageGrabber


def create_mock_scraper(status_code=200, content=b"<html></html>"):
    """Helper to create a mock async scraper for testing."""
    mock_scraper = MagicMock()
    mock_response = Mock()
    mock_response.status_code = status_code
    mock_response.content = content
    # Make get_async() return an awaitable
    mock_scraper.get_async = AsyncMock(return_value=mock_response)
    mock_scraper.close = AsyncMock()
    return mock_scraper, mock_response


def create_mock_soup_for_validation(title="Test Manga", tag="單行本", subtag="漢化", pages=5):
    """Helper to create a properly mocked BeautifulSoup for validation."""
    soup = MagicMock()

    # Mock h2 for title
    h2_tag = MagicMock()
    h2_tag.string = MagicMock()
    h2_tag.string.strip.return_value = title
    soup.find_all.return_value = [h2_tag]

    # Mock pic_box elements
    pic_box = MagicMock()
    link = MagicMock()
    link.get.return_value = "/page.html"
    pic_box.find.return_value = link

    # Mock find for pic_box (both indexed and direct)
    soup.find.return_value = pic_box

    # Mock label for page count
    label = MagicMock()
    label.get_text.return_value = f"頁數: {pages}頁"

    # Mock bread crumb for tags
    bread = MagicMock()
    tag_list = [
        MagicMock(string="Category"),
        MagicMock(string=tag),
        MagicMock(string=subtag),
    ]
    bread.find_all.return_value = tag_list

    # Setup find to return appropriate elements
    def find_side_effect(tag_name, attrs=None, text=None):
        if tag_name == "div" and attrs and attrs.get("class") == "pic_box":
            return pic_box
        elif tag_name == "label" and text:
            return label
        elif tag_name == "div" and attrs and attrs.get("class") == "png bread":
            return bread
        return MagicMock()

    soup.find.side_effect = find_side_effect
    return soup


class TestImageGrabberBasics:
    """Basic tests for ImageGrabber."""

    async def test_invalid_url_404(self, capsys):
        """Test with invalid URL returning 404."""
        mock_scraper, _ = create_mock_scraper(status_code=404)

        grabber = ImageGrabber(
            "https://example.com/invalid", "/tmp/manga/", "crawl", scraper=mock_scraper
        )
        await grabber.validate()

        assert grabber.valid is False
        captured = capsys.readouterr()
        assert "The url is not valid" in captured.out

    @patch("wgrabber.image_grabber.BeautifulSoup")
    async def test_invalid_url_no_title(self, mock_bs, capsys):
        """Test with URL that doesn't have proper manga structure."""
        mock_scraper, _ = create_mock_scraper(status_code=200)

        mock_soup = MagicMock()
        # Simulate IndexError when finding h2
        mock_soup.find_all.return_value = []
        mock_bs.return_value = mock_soup

        grabber = ImageGrabber(
            "https://example.com/invalid", "/tmp/manga/", "crawl", scraper=mock_scraper
        )
        await grabber.validate()

        assert grabber.valid is False
        captured = capsys.readouterr()
        assert "Please make sure the url is correct" in captured.out

    def test_base_path_modifier(self):
        """Test _base_path_modifier method."""
        mock_scraper, _ = create_mock_scraper()
        grabber = ImageGrabber(
            "https://example.com/manga/12345", "/tmp/manga/", "crawl", scraper=mock_scraper
        )
        grabber.base_path = "/tmp/manga/"
        grabber.tag = "volume"
        grabber.subtag = "CN"

        result = grabber._base_path_modifier()

        assert result == "/tmp/manga/volume/CN/"

    @patch("wgrabber.image_grabber.BeautifulSoup")
    async def test_url_resolver(self, mock_bs):
        """Test _url_resolver method."""
        mock_scraper, mock_response = create_mock_scraper()

        mock_soup = MagicMock()
        mock_img = MagicMock()
        mock_img.get.return_value = "//img.example.com/image.jpg"
        mock_soup.find.return_value = mock_img
        mock_bs.return_value = mock_soup

        grabber = ImageGrabber(
            "https://example.com/manga/12345", "/tmp/manga/", "crawl", scraper=mock_scraper
        )
        grabber.base_url = "https://example.com"

        result = await grabber._url_resolver("/page/1.html")

        assert result == "//img.example.com/image.jpg"
        mock_scraper.get_async.assert_called_with("https://example.com/page/1.html")


class TestImageGrabberValidation:
    """Tests for validation logic covering different tag combinations."""

    @patch("wgrabber.image_grabber.BeautifulSoup")
    async def test_validate_volume_cn(self, mock_bs):
        """Test validation with volume/CN tags."""
        mock_scraper, mock_response = create_mock_scraper(status_code=200, content=b"<html></html>")

        # First call for validation, second for _url_resolver
        soup1 = create_mock_soup_for_validation("Test Volume", "單行本", "漢化", 10)
        soup2 = MagicMock()
        img_tag = MagicMock()
        img_tag.get.return_value = "//img.example.com/data.jpg"
        soup2.find.return_value = img_tag

        mock_bs.side_effect = [soup1, soup2]

        grabber = ImageGrabber(
            "https://example.com/manga/123", "/tmp/", "crawl", scraper=mock_scraper
        )
        await grabber.validate()

        assert grabber.valid is True
        assert grabber.title == "Test Volume"
        assert grabber.tag == "volume"
        assert grabber.subtag == "CN"
        assert grabber.page_num == 10

    @patch("wgrabber.image_grabber.BeautifulSoup")
    async def test_validate_short_jp(self, mock_bs):
        """Test validation with short/JP tags."""
        mock_scraper, mock_response = create_mock_scraper(status_code=200, content=b"<html></html>")

        soup1 = create_mock_soup_for_validation("Short Manga", "雜誌&短篇", "日語", 5)
        soup2 = MagicMock()
        img_tag = MagicMock()
        img_tag.get.return_value = "//img.example.com/data.jpg"
        soup2.find.return_value = img_tag

        mock_bs.side_effect = [soup1, soup2]

        grabber = ImageGrabber(
            "https://example.com/manga/456", "/tmp/", "crawl", scraper=mock_scraper
        )
        await grabber.validate()

        assert grabber.valid is True
        assert grabber.tag == "short"
        assert grabber.subtag == "JP"


class TestImageGrabberDownload:
    """Tests for download functionality."""

    @patch("wgrabber.image_grabber.os.makedirs")
    async def test_download_creates_directory(self, mock_makedirs):
        """Test that download creates necessary directories."""
        mock_scraper, _ = create_mock_scraper()

        grabber = ImageGrabber(
            "https://example.com/manga/123", "/tmp/", "crawl", scraper=mock_scraper
        )
        grabber.title = "Test"
        grabber.tag = "volume"
        grabber.subtag = "CN"
        grabber.img_link = "/first"
        grabber.base_path = "/tmp/"
        grabber.valid = True

        with patch.object(grabber, "_page_crawl", return_value=iter([])):
            with patch.object(grabber, "_download_list", new_callable=AsyncMock):
                await grabber.download()

        mock_makedirs.assert_called_once()


