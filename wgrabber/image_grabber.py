import os
import re
import zipfile
from io import BytesIO
from typing import cast

import click
import requests
from bs4 import BeautifulSoup, Tag
from PIL import Image

from .url_processor import URLProcessor


class ImageGrabber:
    """
    the image grabber class.
    """

    def __init__(self, start_url, base_path, mode, zip_only=False):
        """
        The constructor func.
        """
        self.url = start_url
        self.base_path = base_path
        self.base_url = "https://" + (self.url.split("/"))[-2]
        self.mode = mode
        self.zip_only = zip_only
        self.validate()

    def _url_resolver(self, next_url):
        """
        Get the data url from passed url.
        """
        url = self.base_url + next_url
        r = requests.get(url)
        soup = BeautifulSoup(r.content, "lxml")
        img_tag = soup.find("img", attrs={"id": "picarea"})
        if img_tag is None:
            raise ValueError(f"Could not find image tag in {url}")
        img_tag = cast(Tag, img_tag)
        src = img_tag.get("src")
        if src is None:
            raise ValueError(f"Image tag has no src attribute in {url}")
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
                    h2_tags = soup.find_all("h2")
                    if not h2_tags or h2_tags[0].string is None:
                        raise IndexError("No title found")
                    self.title = h2_tags[0].string.strip()
                except IndexError:
                    print("Please make sure the url is correct.")
                    self.valid = False
                    return
                link = soup.find_all("div", attrs={"class": "pic_box"})[-1].find("a")
                # also save the first link
                first_pic_box = soup.find("div", attrs={"class": "pic_box"})
                if first_pic_box is None:
                    print("Cannot find pic_box div.")
                    self.valid = False
                    return
                first_link = first_pic_box.find("a")
                if first_link is None:
                    print("Cannot find link in pic_box.")
                    self.valid = False
                    return
                first_link = cast(Tag, first_link)
                href = first_link.get("href")
                if href is None:
                    print("Link has no href attribute.")
                    self.valid = False
                    return
                self.img_link = href
                if link:
                    self.data_url = self._url_resolver(link["href"])
                    patten = re.compile(r"頁數")
                    label_tag = soup.find("label", text=patten)
                    if label_tag is None:
                        print("Cannot find page number.")
                        self.valid = False
                        return
                    label_string = label_tag.get_text() if hasattr(label_tag, "get_text") else str(label_tag)
                    pages = re.findall(r"\d+", label_string)
                    self.page_num = int(pages[0])
                    # find the catagory and lang tags
                    bread_div = soup.find("div", attrs={"class": "png bread"})
                    if bread_div is None or not hasattr(bread_div, "find_all"):
                        print("Cannot find breadcrumb div.")
                        self.valid = False
                        return
                    bread_div = cast(Tag, bread_div)
                    tags = bread_div.find_all("a")
                    if tags[1].string == "單行本":
                        self.tag = "volume"
                    elif tags[1].string == "雜誌&短篇":
                        self.tag = "short"
                    elif tags[1].string == "同人誌":
                        self.tag = "doujin"
                    elif tags[1].string == "AI圖集":
                        self.tag = "AI"
                    elif tags[1].string == "3D&漫畫":
                        self.tag = "3D"
                    elif tags[1].string == "寫真&Cosplay":
                        self.tag = "photo"
                    elif tags[1].string == "韓漫":
                        self.tag = "Korean"
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
                        elif tags[2].string == "English":
                            self.subtag = "EN"
                        elif tags[2].string == "生肉":
                            self.subtag = "Other"
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
            imgarea_span = soup.find("span", attrs={"id": "imgarea"})
            if imgarea_span is None:
                continue
            imgarea_span = cast(Tag, imgarea_span)
            img_link = imgarea_span.find("a")
            if img_link is None:
                continue
            img_link = cast(Tag, img_link)
            img_tag = img_link.find("img")
            if img_tag is None:
                continue
            img_tag = cast(Tag, img_tag)
            img_url = img_tag.get("src")
            if img_url is None:
                continue
            newpage_div = soup.find("div", attrs={"class": "newpage"})
            if newpage_div is None:
                continue
            newpage_div = cast(Tag, newpage_div)
            next_links = newpage_div.find_all("a")
            if not next_links:
                continue
            url = self.base_url + next_links[-1]["href"]
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

        # Clean up individual images if zip_only is enabled
        if self.zip_only:
            for img in img_list:
                try:
                    os.remove(os.path.join(new_folder, img))
                except OSError as e:
                    print(f"Could not delete {img}: {e}")

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
