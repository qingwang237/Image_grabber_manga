"""
Tests for ImageGrabber class.
"""

from io import BytesIO
from unittest.mock import MagicMock, Mock, patch

from PIL import Image

from wgrabber.image_grabber import ImageGrabber


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

    @patch("wgrabber.image_grabber.requests.get")
    def test_invalid_url_404(self, mock_get, capsys):
        """Test with invalid URL returning 404."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        grabber = ImageGrabber("https://example.com/invalid", "/tmp/manga/", "crawl")

        assert grabber.valid is False
        captured = capsys.readouterr()
        assert "The url is not valid" in captured.out

    @patch("wgrabber.image_grabber.requests.get")
    @patch("wgrabber.image_grabber.BeautifulSoup")
    def test_invalid_url_no_title(self, mock_bs, mock_get, capsys):
        """Test with URL that doesn't have proper manga structure."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"<html></html>"
        mock_get.return_value = mock_response

        mock_soup = MagicMock()
        # Simulate IndexError when finding h2
        mock_soup.find_all.return_value = []
        mock_bs.return_value = mock_soup

        grabber = ImageGrabber("https://example.com/invalid", "/tmp/manga/", "crawl")

        assert grabber.valid is False
        captured = capsys.readouterr()
        assert "Please make sure the url is correct" in captured.out

    def test_base_path_modifier(self):
        """Test _base_path_modifier method."""
        with patch.object(ImageGrabber, "validate"):
            grabber = ImageGrabber("https://example.com/manga/12345", "/tmp/manga/", "crawl")
            grabber.base_path = "/tmp/manga/"
            grabber.tag = "volume"
            grabber.subtag = "CN"

            result = grabber._base_path_modifier()

        assert result == "/tmp/manga/volume/CN/"

    @patch("wgrabber.image_grabber.requests.get")
    @patch("wgrabber.image_grabber.BeautifulSoup")
    def test_url_resolver(self, mock_bs, mock_get):
        """Test _url_resolver method."""
        mock_response = Mock()
        mock_response.content = b"<html></html>"
        mock_get.return_value = mock_response

        mock_soup = MagicMock()
        mock_img = MagicMock()
        mock_img.get.return_value = "//img.example.com/image.jpg"
        mock_soup.find.return_value = mock_img
        mock_bs.return_value = mock_soup

        with patch.object(ImageGrabber, "validate"):
            grabber = ImageGrabber("https://example.com/manga/12345", "/tmp/manga/", "crawl")
            grabber.base_url = "https://example.com"

            result = grabber._url_resolver("/page/1.html")

        assert result == "//img.example.com/image.jpg"
        mock_get.assert_called_with("https://example.com/page/1.html")


class TestImageGrabberValidation:
    """Tests for validation logic covering different tag combinations."""

    @patch("wgrabber.image_grabber.requests.get")
    @patch("wgrabber.image_grabber.BeautifulSoup")
    def test_validate_volume_cn(self, mock_bs, mock_get):
        """Test validation with volume/CN tags."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"<html></html>"
        mock_get.return_value = mock_response

        # First call for validation, second for _url_resolver
        soup1 = create_mock_soup_for_validation("Test Volume", "單行本", "漢化", 10)
        soup2 = MagicMock()
        img_tag = MagicMock()
        img_tag.get.return_value = "//img.example.com/data.jpg"
        soup2.find.return_value = img_tag

        mock_bs.side_effect = [soup1, soup2]

        grabber = ImageGrabber("https://example.com/manga/123", "/tmp/", "crawl")

        assert grabber.valid is True
        assert grabber.title == "Test Volume"
        assert grabber.tag == "volume"
        assert grabber.subtag == "CN"
        assert grabber.page_num == 10

    @patch("wgrabber.image_grabber.requests.get")
    @patch("wgrabber.image_grabber.BeautifulSoup")
    def test_validate_short_jp(self, mock_bs, mock_get):
        """Test validation with short/JP tags."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"<html></html>"
        mock_get.return_value = mock_response

        soup1 = create_mock_soup_for_validation("Short Manga", "雜誌&短篇", "日語", 5)
        soup2 = MagicMock()
        img_tag = MagicMock()
        img_tag.get.return_value = "//img.example.com/data.jpg"
        soup2.find.return_value = img_tag

        mock_bs.side_effect = [soup1, soup2]

        grabber = ImageGrabber("https://example.com/manga/456", "/tmp/", "crawl")

        assert grabber.valid is True
        assert grabber.tag == "short"
        assert grabber.subtag == "JP"

    @patch("wgrabber.image_grabber.requests.get")
    @patch("wgrabber.image_grabber.BeautifulSoup")
    def test_validate_doujin_cg(self, mock_bs, mock_get):
        """Test validation with doujin/CG tags."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"<html></html>"
        mock_get.return_value = mock_response

        soup1 = create_mock_soup_for_validation("Doujin", "同人誌", "CG畫集", 20)
        soup2 = MagicMock()
        img_tag = MagicMock()
        img_tag.get.return_value = "//img.example.com/data.jpg"
        soup2.find.return_value = img_tag

        mock_bs.side_effect = [soup1, soup2]

        grabber = ImageGrabber("https://example.com/manga/789", "/tmp/", "crawl")

        assert grabber.valid is True
        assert grabber.tag == "doujin"
        assert grabber.subtag == "CG"

    @patch("wgrabber.image_grabber.requests.get")
    @patch("wgrabber.image_grabber.BeautifulSoup")
    def test_validate_cosplay(self, mock_bs, mock_get):
        """Test validation with Cosplay tag."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"<html></html>"
        mock_get.return_value = mock_response

        soup1 = create_mock_soup_for_validation("Cosplay", "單行本", "Cosplay", 8)
        soup2 = MagicMock()
        img_tag = MagicMock()
        img_tag.get.return_value = "//img.example.com/data.jpg"
        soup2.find.return_value = img_tag

        mock_bs.side_effect = [soup1, soup2]

        grabber = ImageGrabber("https://example.com/manga/cos", "/tmp/", "crawl")

        assert grabber.valid is True
        assert grabber.subtag == "COS"

    @patch("wgrabber.image_grabber.requests.get")
    @patch("wgrabber.image_grabber.BeautifulSoup")
    def test_validate_unknown_tags(self, mock_bs, mock_get):
        """Test validation with unknown category and language tags."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"<html></html>"
        mock_get.return_value = mock_response

        soup1 = create_mock_soup_for_validation("Unknown", "Other", "Other Lang", 3)
        soup2 = MagicMock()
        img_tag = MagicMock()
        img_tag.get.return_value = "//img.example.com/data.jpg"
        soup2.find.return_value = img_tag

        mock_bs.side_effect = [soup1, soup2]

        grabber = ImageGrabber("https://example.com/manga/unk", "/tmp/", "crawl")

        assert grabber.valid is True
        assert grabber.tag == "unknown"
        assert grabber.subtag == "unknown"

    @patch("wgrabber.image_grabber.requests.get")
    @patch("wgrabber.image_grabber.BeautifulSoup")
    def test_validate_missing_subtag(self, mock_bs, mock_get):
        """Test validation when subtag is missing (IndexError)."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"<html></html>"
        mock_get.return_value = mock_response

        soup = MagicMock()

        # Mock h2 for title
        h2_tag = MagicMock()
        h2_tag.string = MagicMock()
        h2_tag.string.strip.return_value = "Test"
        soup.find_all.return_value = [h2_tag]

        # Mock pic_box
        pic_box = MagicMock()
        link = MagicMock()
        link.get.return_value = "/page.html"
        pic_box.find.return_value = link

        # Mock label for pages
        label = MagicMock()
        label.get_text.return_value = "頁數: 5頁"

        # Mock bread with only 2 tags (will cause IndexError on tags[2])
        bread = MagicMock()
        bread.find_all.return_value = [
            MagicMock(string="Cat"),
            MagicMock(string="單行本"),
            # Missing third element
        ]

        def find_side_effect(tag_name, attrs=None, text=None):
            if tag_name == "div" and attrs and attrs.get("class") == "pic_box":
                return pic_box
            elif tag_name == "label":
                return label
            elif tag_name == "div" and attrs and attrs.get("class") == "png bread":
                return bread
            return MagicMock()

        soup.find.side_effect = find_side_effect

        soup2 = MagicMock()
        img_tag = MagicMock()
        img_tag.get.return_value = "//img.example.com/data.jpg"
        soup2.find.return_value = img_tag

        mock_bs.side_effect = [soup, soup2]

        grabber = ImageGrabber("https://example.com/manga/missing", "/tmp/", "crawl")

        assert grabber.valid is True
        assert grabber.subtag == "unknown"

    @patch("wgrabber.image_grabber.requests.get")
    @patch("wgrabber.image_grabber.BeautifulSoup")
    def test_validate_no_data_url_link(self, mock_bs, mock_get, capsys):
        """Test when link for data URL is None."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"<html></html>"
        mock_get.return_value = mock_response

        soup = MagicMock()

        # Mock h2 for title
        h2_tag = MagicMock()
        h2_tag.string.strip.return_value = "Test"

        # Mock pic_box for first link
        first_pic_box = MagicMock()
        first_link = MagicMock()
        first_link.__getitem__.return_value = "/first.html"
        first_pic_box.find.return_value = first_link

        # Mock last pic_box with None link
        last_pic_box = MagicMock()
        last_pic_box.find.return_value = None

        def find_all_side_effect(tag, attrs=None):
            if tag == "h2":
                return [h2_tag]
            elif tag == "div" and attrs and attrs.get("class") == "pic_box":
                return [first_pic_box, last_pic_box]
            return []

        soup.find_all.side_effect = find_all_side_effect
        soup.find.return_value = first_pic_box

        mock_bs.return_value = soup

        grabber = ImageGrabber("https://example.com/manga/nolink", "/tmp/", "crawl")

        assert grabber.valid is False
        captured = capsys.readouterr()
        assert "Cannot find data url" in captured.out


class TestImageGrabberPageCrawl:
    """Tests for _page_crawl method."""

    @patch("wgrabber.image_grabber.requests.get")
    @patch("wgrabber.image_grabber.BeautifulSoup")
    def test_page_crawl(self, mock_bs, mock_get):
        """Test _page_crawl method."""
        # Create soups for each page
        urls = []
        for i in range(3):
            soup = MagicMock()

            # Mock imgarea -> a -> img
            img = MagicMock()
            img.get.return_value = f"//img.example.com/page{i}.jpg"

            a_tag = MagicMock()
            a_tag.find.return_value = img

            imgarea = MagicMock()
            imgarea.find.return_value = a_tag

            # Mock newpage -> links
            newpage = MagicMock()
            next_link = MagicMock()
            next_link.get.return_value = f"/page{i + 1}"
            newpage.find_all.return_value = [MagicMock(), next_link]

            def create_find(imgarea_val, newpage_val):
                def find_func(tag, attrs):
                    if tag == "span" and attrs.get("id") == "imgarea":
                        return imgarea_val
                    elif tag == "div" and attrs.get("class") == "newpage":
                        return newpage_val

                return find_func

            soup.find.side_effect = create_find(imgarea, newpage)
            urls.append(soup)

        mock_bs.side_effect = urls
        mock_get.return_value = Mock(content=b"<html></html>")

        with patch.object(ImageGrabber, "validate"):
            grabber = ImageGrabber("https://example.com/manga/123", "/tmp/", "crawl")
            grabber.base_url = "https://example.com"
            grabber.page_num = 3

            results = list(grabber._page_crawl("/start"))

        assert len(results) == 3
        assert all("page" in url and ".jpg" in url for url in results)
        # Verify requests were made
        assert mock_get.call_count == 3


class TestImageGrabberDownloadList:
    """Tests for _download_list method."""

    @patch("wgrabber.image_grabber.os.chdir")
    @patch("wgrabber.image_grabber.zipfile.ZipFile")
    @patch("wgrabber.image_grabber.Image.open")
    @patch("wgrabber.image_grabber.requests.get")
    @patch("wgrabber.image_grabber.click.progressbar")
    def test_download_list_success(
        self, mock_progressbar, mock_get, mock_img_open, mock_zipfile, mock_chdir
    ):
        """Test _download_list with successful downloads."""
        # Create a real image
        img = Image.new("RGB", (10, 10), color="red")
        img_bytes = BytesIO()
        img.save(img_bytes, format="JPEG")
        img_bytes.seek(0)

        # Setup progressbar
        urls = ["//img.example.com/1.jpg", "//img.example.com/2.jpg"]
        mock_progressbar.return_value.__enter__ = Mock(return_value=urls)
        mock_progressbar.return_value.__exit__ = Mock(return_value=False)

        # Setup response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = img_bytes.getvalue()
        mock_get.return_value = mock_response

        # Setup image mock
        mock_img = MagicMock()
        mock_img_open.return_value = mock_img

        # Setup zipfile
        mock_zip = MagicMock()
        mock_zipfile.return_value = mock_zip

        with patch.object(ImageGrabber, "validate"):
            grabber = ImageGrabber("https://example.com/manga/123", "/tmp/", "crawl")
            grabber.title = "Test"
            grabber.tag = "volume"
            grabber.subtag = "CN"
            grabber.base_path = "/tmp/"
            grabber.page_num = 2

            grabber._download_list(urls)

        # Verify downloads
        assert mock_get.call_count == 2
        assert mock_img.save.call_count == 2
        mock_zipfile.assert_called_once()
        assert mock_zip.write.call_count == 2

    @patch("wgrabber.image_grabber.os.chdir")
    @patch("wgrabber.image_grabber.zipfile.ZipFile")
    @patch("wgrabber.image_grabber.Image.open")
    @patch("wgrabber.image_grabber.requests.get")
    @patch("wgrabber.image_grabber.click.progressbar")
    def test_download_list_404_jpg_to_png(
        self, mock_progressbar, mock_get, mock_img_open, mock_zipfile, mock_chdir
    ):
        """Test _download_list retries with different extension on 404."""
        img = Image.new("RGB", (10, 10), color="blue")
        img_bytes = BytesIO()
        img.save(img_bytes, format="PNG")
        img_bytes.seek(0)

        urls = ["//img.example.com/1.jpg"]
        mock_progressbar.return_value.__enter__ = Mock(return_value=urls)
        mock_progressbar.return_value.__exit__ = Mock(return_value=False)

        # First request 404, second succeeds
        resp_404 = Mock()
        resp_404.status_code = 404

        resp_200 = Mock()
        resp_200.status_code = 200
        resp_200.content = img_bytes.getvalue()

        mock_get.side_effect = [resp_404, resp_200]

        mock_img = MagicMock()
        mock_img_open.return_value = mock_img

        mock_zip = MagicMock()
        mock_zipfile.return_value = mock_zip

        with patch.object(ImageGrabber, "validate"):
            grabber = ImageGrabber("https://example.com/manga/123", "/tmp/", "crawl")
            grabber.title = "Test"
            grabber.tag = "volume"
            grabber.subtag = "CN"
            grabber.base_path = "/tmp/"
            grabber.page_num = 1

            grabber._download_list(urls)

        # Should have made 2 requests (original jpg, then png)
        assert mock_get.call_count == 2
        # Verify second call was with .png
        second_call_url = mock_get.call_args_list[1][0][0]
        assert ".png" in second_call_url

    @patch("wgrabber.image_grabber.os.chdir")
    @patch("wgrabber.image_grabber.zipfile.ZipFile")
    @patch("wgrabber.image_grabber.Image.open")
    @patch("wgrabber.image_grabber.requests.get")
    @patch("wgrabber.image_grabber.click.progressbar")
    def test_download_list_404_png_to_jpg(
        self, mock_progressbar, mock_get, mock_img_open, mock_zipfile, mock_chdir
    ):
        """Test _download_list retries png to jpg on 404."""
        img = Image.new("RGB", (10, 10), color="green")
        img_bytes = BytesIO()
        img.save(img_bytes, format="JPEG")
        img_bytes.seek(0)

        urls = ["//img.example.com/1.png"]
        mock_progressbar.return_value.__enter__ = Mock(return_value=urls)
        mock_progressbar.return_value.__exit__ = Mock(return_value=False)

        resp_404 = Mock()
        resp_404.status_code = 404

        resp_200 = Mock()
        resp_200.status_code = 200
        resp_200.content = img_bytes.getvalue()

        mock_get.side_effect = [resp_404, resp_200]

        mock_img = MagicMock()
        mock_img_open.return_value = mock_img

        mock_zip = MagicMock()
        mock_zipfile.return_value = mock_zip

        with patch.object(ImageGrabber, "validate"):
            grabber = ImageGrabber("https://example.com/manga/123", "/tmp/", "crawl")
            grabber.title = "Test"
            grabber.tag = "volume"
            grabber.subtag = "CN"
            grabber.base_path = "/tmp/"
            grabber.page_num = 1

            grabber._download_list(urls)

        assert mock_get.call_count == 2
        second_call_url = mock_get.call_args_list[1][0][0]
        assert ".jpg" in second_call_url

    @patch("wgrabber.image_grabber.os.chdir")
    @patch("wgrabber.image_grabber.zipfile.ZipFile")
    @patch("wgrabber.image_grabber.Image.open")
    @patch("wgrabber.image_grabber.requests.get")
    @patch("wgrabber.image_grabber.click.progressbar")
    def test_download_list_oserror(
        self, mock_progressbar, mock_get, mock_img_open, mock_zipfile, mock_chdir, capsys
    ):
        """Test _download_list handles OSError when saving."""
        urls = ["//img.example.com/1.jpg"]
        mock_progressbar.return_value.__enter__ = Mock(return_value=urls)
        mock_progressbar.return_value.__exit__ = Mock(return_value=False)

        resp = Mock()
        resp.status_code = 200
        resp.content = b"fake image"
        mock_get.return_value = resp

        # Image.open raises OSError
        mock_img_open.side_effect = OSError("Cannot save")

        mock_zip = MagicMock()
        mock_zipfile.return_value = mock_zip

        with patch.object(ImageGrabber, "validate"):
            grabber = ImageGrabber("https://example.com/manga/123", "/tmp/", "crawl")
            grabber.title = "Test"
            grabber.tag = "volume"
            grabber.subtag = "CN"
            grabber.base_path = "/tmp/"
            grabber.page_num = 1

            grabber._download_list(urls)

        captured = capsys.readouterr()
        assert "cannot be saved" in captured.out

    @patch("wgrabber.image_grabber.os.chdir")
    @patch("wgrabber.image_grabber.zipfile.ZipFile")
    @patch("wgrabber.image_grabber.Image.open")
    @patch("wgrabber.image_grabber.requests.get")
    @patch("wgrabber.image_grabber.click.progressbar")
    def test_download_list_other_status(
        self, mock_progressbar, mock_get, mock_img_open, mock_zipfile, mock_chdir
    ):
        """Test _download_list with non-200/404 status codes."""
        urls = ["//img.example.com/1.jpg"]
        mock_progressbar.return_value.__enter__ = Mock(return_value=urls)
        mock_progressbar.return_value.__exit__ = Mock(return_value=False)

        # Return 500 error
        resp = Mock()
        resp.status_code = 500
        mock_get.return_value = resp

        mock_zip = MagicMock()
        mock_zipfile.return_value = mock_zip

        with patch.object(ImageGrabber, "validate"):
            grabber = ImageGrabber("https://example.com/manga/123", "/tmp/", "crawl")
            grabber.title = "Test"
            grabber.tag = "volume"
            grabber.subtag = "CN"
            grabber.base_path = "/tmp/"
            grabber.page_num = 1

            grabber._download_list(urls)

        # Should not call image operations for non-200/404
        mock_img_open.assert_not_called()

    @patch("wgrabber.image_grabber.os.remove")
    @patch("wgrabber.image_grabber.os.chdir")
    @patch("wgrabber.image_grabber.zipfile.ZipFile")
    @patch("wgrabber.image_grabber.Image.open")
    @patch("wgrabber.image_grabber.requests.get")
    @patch("wgrabber.image_grabber.click.progressbar")
    def test_download_list_with_zip_only(
        self, mock_progressbar, mock_get, mock_img_open, mock_zipfile, mock_chdir, mock_remove
    ):
        """Test _download_list with zip_only=True deletes images after zipping."""
        img = Image.new("RGB", (10, 10), color="red")
        img_bytes = BytesIO()
        img.save(img_bytes, format="JPEG")
        img_bytes.seek(0)

        urls = ["//img.example.com/1.jpg", "//img.example.com/2.jpg"]
        mock_progressbar.return_value.__enter__ = Mock(return_value=urls)
        mock_progressbar.return_value.__exit__ = Mock(return_value=False)

        resp = Mock()
        resp.status_code = 200
        resp.content = img_bytes.getvalue()
        mock_get.return_value = resp

        mock_img = MagicMock()
        mock_img_open.return_value = mock_img

        mock_zip = MagicMock()
        mock_zipfile.return_value = mock_zip

        with patch.object(ImageGrabber, "validate"):
            grabber = ImageGrabber(
                "https://example.com/manga/123", "/tmp/", "crawl", zip_only=True
            )
            grabber.title = "Test"
            grabber.tag = "volume"
            grabber.subtag = "CN"
            grabber.base_path = "/tmp/"
            grabber.page_num = 2

            grabber._download_list(urls)

        # Verify images were downloaded and saved
        assert mock_get.call_count == 2
        assert mock_img.save.call_count == 2

        # Verify zip was created
        mock_zipfile.assert_called_once()
        assert mock_zip.write.call_count == 2

        # Verify images were deleted after zipping
        assert mock_remove.call_count == 2

    @patch("wgrabber.image_grabber.os.remove")
    @patch("wgrabber.image_grabber.os.chdir")
    @patch("wgrabber.image_grabber.zipfile.ZipFile")
    @patch("wgrabber.image_grabber.Image.open")
    @patch("wgrabber.image_grabber.requests.get")
    @patch("wgrabber.image_grabber.click.progressbar")
    def test_download_list_without_zip_only(
        self, mock_progressbar, mock_get, mock_img_open, mock_zipfile, mock_chdir, mock_remove
    ):
        """Test _download_list with zip_only=False keeps images."""
        img = Image.new("RGB", (10, 10), color="red")
        img_bytes = BytesIO()
        img.save(img_bytes, format="JPEG")
        img_bytes.seek(0)

        urls = ["//img.example.com/1.jpg"]
        mock_progressbar.return_value.__enter__ = Mock(return_value=urls)
        mock_progressbar.return_value.__exit__ = Mock(return_value=False)

        resp = Mock()
        resp.status_code = 200
        resp.content = img_bytes.getvalue()
        mock_get.return_value = resp

        mock_img = MagicMock()
        mock_img_open.return_value = mock_img

        mock_zip = MagicMock()
        mock_zipfile.return_value = mock_zip

        with patch.object(ImageGrabber, "validate"):
            grabber = ImageGrabber(
                "https://example.com/manga/123", "/tmp/", "crawl", zip_only=False
            )
            grabber.title = "Test"
            grabber.tag = "volume"
            grabber.subtag = "CN"
            grabber.base_path = "/tmp/"
            grabber.page_num = 1

            grabber._download_list(urls)

        # Verify images were downloaded
        assert mock_get.call_count == 1
        assert mock_img.save.call_count == 1

        # Verify zip was created
        mock_zipfile.assert_called_once()

        # Verify images were NOT deleted
        mock_remove.assert_not_called()


class TestImageGrabberDownload:
    """Tests for download-related methods."""

    @patch("wgrabber.image_grabber.os.makedirs")
    @patch("wgrabber.image_grabber.URLProcessor")
    def test_download_normal_mode(self, mock_urlprocessor, mock_makedirs):
        """Test download method in normal mode."""
        mock_processor = MagicMock()
        mock_processor.normal_url_list.return_value = iter([])
        mock_processor.special_url_list.return_value = iter([])
        mock_urlprocessor.return_value = mock_processor

        with patch.object(ImageGrabber, "validate"):
            grabber = ImageGrabber("https://example.com/manga/12345", "/tmp/manga/", "normal")
            grabber.title = "Test Manga"
            grabber.tag = "volume"
            grabber.subtag = "CN"
            grabber.data_url = "//img.example.com/data.jpg"
            grabber.page_num = 5
            grabber.base_path = "/tmp/manga/"

            with patch.object(grabber, "_download_list") as mock_dl:
                grabber.download()

        # Should call _download_list 4 times (normal + 3 special variants)
        assert mock_dl.call_count == 4

        # Verify URLProcessor was called correctly
        mock_urlprocessor.assert_called_once_with("//img.example.com/data.jpg", 5)

    @patch("wgrabber.image_grabber.os.makedirs")
    def test_download_crawl_mode(self, mock_makedirs):
        """Test download method in crawl mode."""
        with patch.object(ImageGrabber, "validate"):
            grabber = ImageGrabber("https://example.com/manga/12345", "/tmp/manga/", "crawl")
            grabber.title = "Test Manga"
            grabber.tag = "volume"
            grabber.subtag = "CN"
            grabber.img_link = "/first"
            grabber.base_path = "/tmp/manga/"

            with patch.object(grabber, "_page_crawl", return_value=iter([])) as mock_crawl:
                with patch.object(grabber, "_download_list") as mock_dl:
                    grabber.download()

        mock_makedirs.assert_called_once()
        mock_crawl.assert_called_once_with("/first")
        mock_dl.assert_called_once()

    @patch("wgrabber.image_grabber.os.makedirs")
    def test_download_makedirs_oserror(self, mock_makedirs):
        """Test download when makedirs fails."""
        mock_makedirs.side_effect = OSError("Cannot create dir")

        with patch.object(ImageGrabber, "validate"):
            grabber = ImageGrabber("https://example.com/manga/12345", "/tmp/manga/", "crawl")
            grabber.title = "Test Manga"
            grabber.tag = "volume"
            grabber.subtag = "CN"
            grabber.img_link = "/first"
            grabber.base_path = "/tmp/manga/"

            with patch.object(grabber, "_page_crawl", return_value=iter([])):
                with patch.object(grabber, "_download_list"):
                    # Should not raise, just pass
                    grabber.download()
