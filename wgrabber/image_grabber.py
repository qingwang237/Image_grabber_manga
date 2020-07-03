import os
import re
import zipfile
from io import BytesIO

import click
import requests
from bs4 import BeautifulSoup
from PIL import Image

from .url_processor import URLProcessor


class ImageGrabber(object):
    """
    the image grabber class.
    """

    def __init__(self, start_url, base_path, mode):
        """
        The constructor func.
        """
        self.url = start_url
        self.base_path = base_path
        self.base_url = "https://" + (self.url.split("/"))[-2]
        self.mode = mode
        self.validate()

    def _url_resolver(self, next_url):
        """
        Get the data url from passed url.
        """
        url = self.base_url + next_url
        r = requests.get(url)
        soup = BeautifulSoup(r.content, "lxml")
        src = soup.find("img", {"id": "picarea"})["src"]
        return src

    def validate(self):
        """
        Validate the url and content.
        """
        if self.url:
            self.result = requests.get(self.url)
            if self.result.status_code == 200:
                soup = BeautifulSoup(self.result.content, "lxml")
                try:
                    self.title = soup.find_all("h2")[0].string.strip()
                except IndexError:
                    print("Please make sure the url is correct.")
                    self.valid = False
                    return
                link = soup.find_all("div", {"class": "pic_box"})[-1].find("a")
                # also save the first link
                self.img_link = soup.find("div", {"class": "pic_box"}).find("a")["href"]
                if link:
                    self.data_url = self._url_resolver(link["href"])
                    patten = re.compile(r"頁數")
                    pages = re.findall(r"\d+", soup.find("label", text=patten).string)
                    self.page_num = int(pages[0])
                    # find the catagory and lang tags
                    tags = soup.find("div", {"class": "png bread"}).find_all("a")
                    if tags[1].string == "單行本":
                        self.tag = "volume"
                    elif tags[1].string == "雜誌&短篇":
                        self.tag = "short"
                    elif tags[1].string == "同人誌":
                        self.tag = "doujin"
                    else:
                        self.tag = "unknown"
                    try:
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
                    except IndexError:
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
        """
        Generate the new path based on the tags.
        """
        return self.base_path + self.tag + "/" + self.subtag + "/"

    def _page_crawl(self, start):
        """
        The page crawler iterator.
        """
        url = self.base_url + start
        for _i in range(self.page_num):
            result = requests.get(url)
            soup = BeautifulSoup(result.content, "lxml")
            img_url = soup.find("span", {"id": "imgarea"}).find("a").find("img")["src"]
            url = (
                self.base_url
                + soup.find("div", {"class": "newpage"}).find_all("a")[-1]["href"]
            )
            yield img_url

    def _download_list(self, iter_list):
        """
        Download files in the list.
        """
        new_folder = os.path.join(self._base_path_modifier(), self.title)
        img_list = []
        with click.progressbar(iter_list, length=self.page_num) as bar:
            for index, url in enumerate(bar):
                # TODO may need better url generator since it may change.
                file_url = "https:" + url
                r = requests.get(file_url)
                if r.status_code == 404:
                    if file_url.split(".")[-1] == "jpg":
                        file_url = file_url.replace("jpg", "png")
                    else:
                        file_url = file_url.replace("png", "jpg")
                    r = requests.get(file_url)
                elif r.status_code == 200:
                    img_name = str(index) + "." + file_url.split(".")[-1]
                    try:
                        img = Image.open(BytesIO(r.content))
                        img.save(new_folder + "/" + img_name)
                        img_list.append(img_name)
                    except OSError:
                        print(file_url + "  cannot be saved.")
                else:
                    pass
        # generate cbz file
        os.chdir(new_folder)
        zipf = zipfile.ZipFile(f"{self.title}.cbz", "w", zipfile.ZIP_DEFLATED)
        for img in img_list:
            zipf.write(img, compress_type=zipfile.ZIP_DEFLATED)
        zipf.close()

    def download(self):
        """
        Download images.
        """
        new_folder = os.path.join(self._base_path_modifier(), self.title)
        try:
            os.makedirs(new_folder, mode=0o755, exist_ok=True)
        except OSError:
            pass
        # handle normal image naming rules
        if self.mode == "crawl":
            self._download_list(self._page_crawl(self.img_link))
        else:
            url_parsed = URLProcessor(self.data_url, self.page_num)
            self._download_list(url_parsed.normal_url_list())
            self._download_list(url_parsed.special_url_list())
            self._download_list(url_parsed.special_url_list(sep="-"))
            self._download_list(url_parsed.special_url_list(sep="_"))
