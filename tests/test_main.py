"""
Tests for __main__.py CLI.
"""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from wgrabber.__main__ import main


def test_main_help():
    """Test the help command."""
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "Command line tool to download the manga" in result.output
    assert "--folder" in result.output
    assert "--mode" in result.output


def test_main_version():
    """Test the version command."""
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "Wgrabber" in result.output


@patch("wgrabber.__main__.ImageGrabber")
def test_main_with_valid_url(mock_image_grabber):
    """Test main with a valid URL."""
    mock_manga = MagicMock()
    mock_manga.valid = True
    mock_image_grabber.return_value = mock_manga

    runner = CliRunner()
    result = runner.invoke(main, ["http://example.com/manga/123"])

    assert result.exit_code == 0
    mock_image_grabber.assert_called_once()
    mock_manga.download.assert_called_once()


@patch("wgrabber.__main__.ImageGrabber")
def test_main_with_invalid_url(mock_image_grabber):
    """Test main with an invalid URL."""
    mock_manga = MagicMock()
    mock_manga.valid = False
    mock_image_grabber.return_value = mock_manga

    runner = CliRunner()
    result = runner.invoke(main, ["http://example.com/invalid"])

    assert result.exit_code == 0
    assert "The start url is not recognized" in result.output
    mock_manga.download.assert_not_called()


@patch("wgrabber.__main__.ImageGrabber")
def test_main_with_custom_folder(mock_image_grabber):
    """Test main with custom folder option."""
    mock_manga = MagicMock()
    mock_manga.valid = True
    mock_image_grabber.return_value = mock_manga

    runner = CliRunner()
    result = runner.invoke(main, ["http://example.com/manga/123", "--folder", "/custom/path/"])

    assert result.exit_code == 0
    # Check that ImageGrabber was called with the custom path
    call_args = mock_image_grabber.call_args
    assert call_args[0][1] == "/custom/path/"


@patch("wgrabber.__main__.ImageGrabber")
def test_main_with_custom_mode(mock_image_grabber):
    """Test main with custom mode option."""
    mock_manga = MagicMock()
    mock_manga.valid = True
    mock_image_grabber.return_value = mock_manga

    runner = CliRunner()
    result = runner.invoke(main, ["http://example.com/manga/123", "--mode", "normal"])

    assert result.exit_code == 0
    # Check that ImageGrabber was called with the custom mode
    call_args = mock_image_grabber.call_args
    assert call_args[0][2] == "normal"


@patch("wgrabber.__main__.ImageGrabber")
def test_main_with_folder_without_trailing_slash(mock_image_grabber):
    """Test main adds trailing slash to folder path."""
    mock_manga = MagicMock()
    mock_manga.valid = True
    mock_image_grabber.return_value = mock_manga

    runner = CliRunner()
    result = runner.invoke(main, ["http://example.com/manga/123", "--folder", "/custom/path"])

    assert result.exit_code == 0
    # Check that trailing slash was added
    call_args = mock_image_grabber.call_args
    assert call_args[0][1] == "/custom/path/"


@patch("wgrabber.__main__.ImageGrabber")
def test_main_with_all_options(mock_image_grabber):
    """Test main with all options specified."""
    mock_manga = MagicMock()
    mock_manga.valid = True
    mock_image_grabber.return_value = mock_manga

    runner = CliRunner()
    result = runner.invoke(
        main, ["http://example.com/manga/123", "--folder", "~/manga/", "--mode", "normal"]
    )

    assert result.exit_code == 0
    call_args = mock_image_grabber.call_args
    # expanduser should expand ~
    assert "~/manga/" not in call_args[0][1] or call_args[0][1] == "~/manga/"
    assert call_args[0][2] == "normal"
    mock_manga.download.assert_called_once()
