# -*- coding: utf-8 -*-
"""This use requests to download images in a series mode."""

import os
import re
import requests
from bs4 import BeautifulSoup

from PIL import Image
from io import BytesIO

url_start = "https://www.wnacg.com/photos-index-aid-35979.html"
base_path = "/home/qing/Hmanga/"


class ImageGrabber(object):
    """the image grabber class."""

    def __init__(self, start_url):
        """The constructor func."""
        self.url = start_url
        self.validate()

    def _url_resolver(self, next_url):
        """Get the data url from passed url."""
        url = "https://" + (self.url.split('/'))[-2] + next_url
        r = requests.get(url)
        soup = BeautifulSoup(r.content, 'lxml')
        src = soup.find("img", {"id": "picarea"})['src']
        url_list = src.split('/')
        # get filename format
        self.format = url_list[-1]
        self.digit_index = re.findall(r'\d+', self.format)[0]
        self.n_digits = len(self.digit_index)
        self.fn_template = url_list[-1].split('.')[0]
        self.index_location = self.fn_template.find(self.digit_index)
        self.img_format = url_list[-1].split('.')[-1]
        return "https://" + (self.url.split('/'))[-2] + '/'.join(url_list[:4]) + '/'

    def _download_list(self, c_list, dash=False):
        """Download the special naming files."""
        for index in c_list:
            new_folder = os.path.join(self._base_path_modifier(), self.title)
            if dash:
                filename = self.fn_template.replace(self.digit_index, '0'.zfill(self.n_digits)) + '-' + index + '.' + self.img_format
            else:
                filename = self.fn_template.replace(self.digit_index, '0'.zfill(self.n_digits)) + index + '.' + self.img_format
            r = requests.get(self.data_url + filename)
            if r.status_code == 200:
                try:
                    img = Image.open(BytesIO(r.content))
                    img.save(new_folder + '/' + filename)
                    print(self.data_url + filename + '  downloaded.')
                except OSError:
                    pass

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

    def download(self):
        """Download images."""
        new_folder = os.path.join(self._base_path_modifier(), self.title)
        try:
            os.makedirs(new_folder, mode=0o755, exist_ok=True)
        except OSError:
            pass
        # handle normal image naming rules
        for index in range(0, self.page_num + 1):
            filename = self.fn_template.replace(self.digit_index, str(index).zfill(self.n_digits)) + '.' + self.img_format
            r = requests.get(self.data_url + filename)
            if r.status_code == 404:
                filename = self.fn_template.replace(self.digit_index, str(index).zfill(self.n_digits)) + '.' + 'png'
                r = requests.get(self.data_url + filename)
            if r.status_code == 200:
                try:
                    img = Image.open(BytesIO(r.content))
                    img.save(new_folder + '/' + filename)
                    print(self.data_url + filename + '  downloaded.')
                except OSError:
                    print(self.data_url + filename + '  not existing.')
        # handle special naming rules
        lower_list = ['a', 'b', 'c', 'd', 'e', 'f', 'g']
        capital_list = ['A', 'B', 'C', 'D', 'E', 'F', 'G']
        number_list = ['0', '1', '2', '3', '4', '5', '6']
        self._download_list(lower_list)
        self._download_list(capital_list)
        self._download_list(number_list, dash=True)


manga = ImageGrabber(url_start)
if manga.valid:
    manga.download()
else:
    print("The start url is not recognized.")
