# -*- coding: utf-8 -*-
"""This use requests to download images in a series mode."""

import os
import re
import requests
from bs4 import BeautifulSoup

from PIL import Image
from io import BytesIO
from url_processor import URLProcessor

url_start = "https://www.wnacg.com/photos-index-aid-35876.html"
base_path = "/home/qing/Hmanga/"


class ImageGrabber(object):
    """the image grabber class."""

    def __init__(self, start_url):
        """The constructor func."""
        self.url = start_url
        self.base_url = "https://" + (self.url.split('/'))[-2]
        self.validate()

    def _url_resolver(self, next_url):
        """Get the data url from passed url."""
        url = self.base_url + next_url
        r = requests.get(url)
        soup = BeautifulSoup(r.content, 'lxml')
        src = soup.find("img", {"id": "picarea"})['src']
        return src

    def validate(self):
        """Validate the url and content."""
        if self.url:
            self.result = requests.get(self.url)
            if self.result.status_code == 200:
                soup = BeautifulSoup(self.result.content, 'lxml')
                self.title = soup.find_all("h2")[0].string.strip()
                link = soup.find_all("div", {"class": "pic_box"})[-1].find('a')
                if link:
                    self.data_url = self._url_resolver(link['href'])
                    patten = re.compile(r'頁數')
                    pages = re.findall(
                        r'\d+', soup.find("label", text=patten).string)
                    self.page_num = int(pages[0])
                    # find the catagory and lang tags
                    tags = soup.find(
                        "div", {"class": "png bread"}).find_all('a')
                    if tags[1].string == "單行本":
                        self.tag = "volume"
                    elif tags[1].string == "雜誌&短篇":
                        self.tag = "short"
                    elif tags[1].string == "同人誌":
                        self.tag = "doujin"
                    else:
                        self.tag = "unknown"
                    if tags[2].string == "漢化":
                        self.subtag = "CN"
                    elif tags[2].string == "日語":
                        self.subtag = "JP"
                    elif tags[2].string == "CG畫集":
                        self.subtag = "CG"
                    elif tags[2].string == "Cosplay":
                        self.subtag = "COS"
                    else:
                        self.subtag = "unknown"
                    self.valid = True
                else:
                    print("Cannot find data url.")
                    self.valid = False
            else:
                self.valid = False
                print("The url is not valid.")
        else:
            print("The url is not set.")
            self.valid = False

    def _base_path_modifier(self):
        """Generate the new path based on the tags."""
        return base_path + self.tag + '/' + self.subtag + '/'

    def _download_list(self, iter_list):
        """Download files in the list."""
        new_folder = os.path.join(self._base_path_modifier(), self.title)
        for url in iter_list:
            file_url = self.base_url + url
            r = requests.get(file_url)
            if r.status_code == 404:
                if file_url.split('.')[-1] == 'jpg':
                    file_url = file_url.replace('jpg', 'png')
                else:
                    file_url = file_url.replace('png', 'jpg')
                r = requests.get(file_url)
            if r.status_code == 200:
                try:
                    img = Image.open(BytesIO(r.content))
                    img.save(new_folder + '/' + file_url.split('/')[-1])
                    print(file_url + '  downloaded.')
                except OSError:
                    print(file_url + '  cannot be saved.')

    def download(self):
        """Download images."""
        new_folder = os.path.join(self._base_path_modifier(), self.title)
        try:
            os.makedirs(new_folder, mode=0o755, exist_ok=True)
        except OSError:
            pass
        # handle normal image naming rules
        url_parsed = URLProcessor(self.data_url, self.page_num)
        self._download_list(url_parsed.normal_url_list())
        self._download_list(url_parsed.special_url_list())
        self._download_list(url_parsed.special_url_list(dash=True))


manga = ImageGrabber(url_start)
if manga.valid:
    manga.download()
else:
    print("The start url is not recognized.")
