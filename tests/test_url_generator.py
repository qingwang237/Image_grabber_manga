"""Tests for URLProcessor class."""

from wgrabber.url_processor import URLProcessor


def test_normal_urls():
    """
    Test generation of normal urls.
    """
    url = "img2.wxxx.download/data/1017/49/15937042073157.jpg"
    page_num = 5
    url_generator = URLProcessor(url, page_num)
    generated = list(url_generator.normal_url_list())
    assert generated == [
        "img2.wxxx.download/data/1017/49/00000000000000.jpg",
        "img2.wxxx.download/data/1017/49/00000000000001.jpg",
        "img2.wxxx.download/data/1017/49/00000000000002.jpg",
        "img2.wxxx.download/data/1017/49/00000000000003.jpg",
        "img2.wxxx.download/data/1017/49/00000000000004.jpg",
        "img2.wxxx.download/data/1017/49/00000000000005.jpg",
    ]


def test_special_urls():
    """
    Test generation of special urls.
    """
    url = "img2.wxxx.download/data/1017/49/15937042073157.jpg"
    page_num = 5
    url_generator = URLProcessor(url, page_num)
    generated = list(url_generator.special_url_list())
    assert generated == [
        "img2.wxxx.download/data/1017/49/00000000000000a.jpg",
        "img2.wxxx.download/data/1017/49/00000000000000b.jpg",
        "img2.wxxx.download/data/1017/49/00000000000000c.jpg",
        "img2.wxxx.download/data/1017/49/00000000000000d.jpg",
        "img2.wxxx.download/data/1017/49/00000000000000e.jpg",
        "img2.wxxx.download/data/1017/49/00000000000000f.jpg",
        "img2.wxxx.download/data/1017/49/00000000000000g.jpg",
        "img2.wxxx.download/data/1017/49/00000000000000A.jpg",
        "img2.wxxx.download/data/1017/49/00000000000000B.jpg",
        "img2.wxxx.download/data/1017/49/00000000000000C.jpg",
        "img2.wxxx.download/data/1017/49/00000000000000D.jpg",
        "img2.wxxx.download/data/1017/49/00000000000000E.jpg",
        "img2.wxxx.download/data/1017/49/00000000000000F.jpg",
        "img2.wxxx.download/data/1017/49/00000000000000G.jpg",
        "img2.wxxx.download/data/1017/49/000000000000000.jpg",
        "img2.wxxx.download/data/1017/49/000000000000001.jpg",
        "img2.wxxx.download/data/1017/49/000000000000002.jpg",
        "img2.wxxx.download/data/1017/49/000000000000003.jpg",
        "img2.wxxx.download/data/1017/49/000000000000004.jpg",
        "img2.wxxx.download/data/1017/49/000000000000005.jpg",
        "img2.wxxx.download/data/1017/49/000000000000006.jpg",
    ]


def test_special_urls_with_separator():
    """
    Test generation of special urls with separator.
    """
    url = "img2.wxxx.download/data/1017/49/15937042073157.jpg"
    page_num = 5
    url_generator = URLProcessor(url, page_num)
    generated = list(url_generator.special_url_list(sep="-"))
    assert len(generated) == 21
    # Check that separator is used
    assert "img2.wxxx.download/data/1017/49/00000000000000-a.jpg" in generated
    assert "img2.wxxx.download/data/1017/49/00000000000000-A.jpg" in generated
    assert "img2.wxxx.download/data/1017/49/00000000000000-0.jpg" in generated


def test_special_urls_with_underscore():
    """
    Test generation of special urls with underscore separator.
    """
    url = "img2.wxxx.download/data/1017/49/15937042073157.jpg"
    page_num = 5
    url_generator = URLProcessor(url, page_num)
    generated = list(url_generator.special_url_list(sep="_"))
    assert len(generated) == 21
    # Check that separator is used
    assert "img2.wxxx.download/data/1017/49/00000000000000_a.jpg" in generated
