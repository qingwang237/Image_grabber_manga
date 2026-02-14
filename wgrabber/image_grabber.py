import asyncio
import os
import random
import re
import zipfile
from io import BytesIO
from typing import cast
from urllib.parse import urlparse

import cloudscraper
from bs4 import BeautifulSoup, Tag
from PIL import Image

from .url_processor import URLProcessor


class AsyncCloudScraper(cloudscraper.CloudScraper):
    """Async wrapper for CloudScraper using aiohttp."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aio_session = None

    async def get_async(self, url, **kwargs):
        """
        Async GET request with Cloudflare bypass.
        Uses executor to run sync cloudscraper in background thread.
        """
        # Run the sync cloudscraper.get() in an executor to not block event loop
        # This properly handles Cloudflare challenges
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: self.get(url, **kwargs))
        return response

    async def close(self):
        """Close the aiohttp session."""
        if self.aio_session:
            await self.aio_session.close()
            self.aio_session = None


class ImageGrabber:
    """
    the image grabber class.
    """

    def __init__(
        self, start_url, base_path, mode, zip_only=False, scraper=None, disable_delays=False
    ):
        """
        The constructor func.
        """
        self.url = start_url
        self.base_path = base_path
        # Use urllib.parse to properly construct base_url from scheme + netloc
        parsed_url = urlparse(self.url)
        self.base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        self.mode = mode
        self.zip_only = zip_only
        self.disable_delays = disable_delays  # Allow disabling delays for tests
        self.consecutive_failures = 0  # Track consecutive security check failures

        # Allow injecting a custom scraper for testing, otherwise create async cloudscraper
        if scraper is None:
            self.scraper = AsyncCloudScraper(
                browser={"browser": "chrome", "platform": "windows", "mobile": False}
            )
            self._own_scraper = True
        else:
            self.scraper = scraper
            self._own_scraper = False

        # Initialize as invalid until validation succeeds
        self.valid = False

    async def _close_scraper(self):
        """Close the scraper session if we own it."""
        if self._own_scraper and hasattr(self.scraper, "close"):
            await self.scraper.close()

    async def _refresh_scraper(self):
        """Recreate the scraper session to get fresh cookies/session."""
        print("\nRefreshing session to bypass security checks...")
        if self._own_scraper:
            await self.scraper.close()
        self.scraper = AsyncCloudScraper(
            browser={"browser": "chrome", "platform": "windows", "mobile": False}
        )

    async def _url_resolver(self, next_url):
        """
        Get the data url from passed url.
        """
        url = self.base_url + next_url

        # Retry logic for URL resolution
        r = None
        for attempt in range(3):
            try:
                r = await self.scraper.get_async(url)
                if r.status_code == 200:
                    break
                elif r.status_code in (403, 503, 429):
                    wait_time = (2**attempt) * 2
                    if attempt < 2:
                        print(f"\nSecurity check during URL resolution. Waiting {wait_time}s...")
                        await asyncio.sleep(wait_time)
                    else:
                        raise ValueError(f"Failed to resolve URL after retries: {url}")
                else:
                    raise ValueError(f"Unexpected status {r.status_code} for {url}")
            except Exception as e:
                if attempt < 2:
                    await asyncio.sleep(2)
                else:
                    raise ValueError(f"Failed to get data URL from {url}: {e}") from e

        if r is None:
            raise ValueError(f"Failed to get response from {url}")
        soup = BeautifulSoup(r.content, "lxml")
        img_tag = soup.find("img", attrs={"id": "picarea"})
        if img_tag is None:
            raise ValueError(f"Could not find image tag in {url}")
        img_tag = cast(Tag, img_tag)
        src = img_tag.get("src")
        if src is None:
            raise ValueError(f"Image tag has no src attribute in {url}")
        return src

    async def validate(self):
        """
        Validate the url and content.
        """
        if not self.url:
            print("The url is not set.")
            self.valid = False
            return

        try:
            result = await self.scraper.get_async(self.url)
            if result.status_code != 200:
                self.valid = False
                print(f"The url is not valid. Status: {result.status_code}")
                return
        except Exception as e:
            print(f"Failed to fetch URL: {e}")
            self.valid = False
            return

        soup = BeautifulSoup(result.content, "lxml")
        try:
            h2_tags = soup.find_all("h2")
            if not h2_tags or h2_tags[0].string is None:
                raise IndexError("No title found")
            self.title = h2_tags[0].string.strip()
        except IndexError:
            print("Please make sure the url is correct.")
            self.valid = False
            return

        # Check if pic_box elements exist before accessing
        pic_boxes = soup.find_all("div", attrs={"class": "pic_box"})
        if not pic_boxes:
            print("Cannot find any pic_box elements.")
            self.valid = False
            return

        # Get the last pic_box link
        last_pic_box_link = pic_boxes[-1].find("a")
        if last_pic_box_link is None:
            print("Cannot find link in last pic_box.")
            self.valid = False
            return

        # also save the first link
        first_pic_box = pic_boxes[0]
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
        if last_pic_box_link:
            last_pic_box_link = cast(Tag, last_pic_box_link)
            data_url_href = last_pic_box_link.get("href")
            if data_url_href is None:
                print("Last pic_box link has no href.")
                self.valid = False
                return
            self.data_url = await self._url_resolver(data_url_href)
            patten = re.compile(r"頁數")
            label_tag = soup.find("label", text=patten)
            if label_tag is None:
                print("Cannot find page number.")
                self.valid = False
                return
            label_string = (
                label_tag.get_text() if hasattr(label_tag, "get_text") else str(label_tag)
            )
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

            # Category mapping - add new categories here
            category_mapping = {
                "單行本": "volume",
                "雜誌&短篇": "short",
                "同人誌": "doujin",
                "AI圖集": "AI",
                "3D&漫畫": "3D",
                "寫真&Cosplay": "photo",
                "韓漫": "Korean",
            }
            if len(tags) > 1:
                self.tag = category_mapping.get(tags[1].string, "unknown")
            else:
                print("Cannot determine category from breadcrumb tags.")
                self.tag = "unknown"
                self.valid = False
                return

            # Language/type mapping - add new languages here
            language_mapping = {
                "漢化": "CN",
                "日語": "JP",
                "CG畫集": "CG",
                "Cosplay": "COS",
                "English": "EN",
                "生肉": "Other",
            }
            try:
                self.subtag = language_mapping.get(tags[2].string, "unknown")
            except IndexError:
                self.subtag = "unknown"
            self.valid = True
        else:
            print("Cannot find data url.")
            self.valid = False

    def _base_path_modifier(self):
        """
        Generate the new path based on the tags.
        """
        return self.base_path + self.tag + "/" + self.subtag + "/"

    async def _page_crawl(self, start):
        """
        The page crawler async generator.
        """
        url = self.base_url + start
        for page_num in range(self.page_num):
            # Retry logic for page fetching
            max_retries = 3
            result = None

            for attempt in range(max_retries):
                try:
                    result = await self.scraper.get_async(url)
                    if result.status_code == 200:
                        self.consecutive_failures = 0  # Reset failure counter
                        break
                    elif result.status_code in (403, 503, 429):
                        self.consecutive_failures += 1

                        # Exponentially longer waits: 10s, 30s, 60s
                        wait_time = min(10 * (3**attempt), 60)

                        if attempt < max_retries - 1:
                            print(
                                f"\nPage {page_num + 1}: Security check detected (attempt {attempt + 1}). Waiting {wait_time}s..."
                            )
                            await asyncio.sleep(wait_time)

                            # Refresh session after 2nd attempt
                            if attempt == 1 and self.consecutive_failures > 2:
                                await self._refresh_scraper()
                        else:
                            print(
                                f"\nPage {page_num + 1}: Failed after {max_retries} attempts. Skipping page."
                            )
                            continue
                    else:
                        print(f"\nPage {page_num + 1}: Unexpected status {result.status_code}")
                        break
                except Exception as e:
                    if attempt < max_retries - 1:
                        print(f"\nError fetching page {page_num + 1}: {e}. Retrying...")
                        await asyncio.sleep(5)
                    else:
                        print(f"\nFailed to fetch page {page_num + 1}: {e}")
                        continue

            if result is None or result.status_code != 200:
                continue

            # Random delay between page requests (1-3 seconds) to appear more human
            if page_num > 0 and not self.disable_delays:
                delay = random.uniform(1.0, 3.0)
                await asyncio.sleep(delay)

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

    async def _download_image_with_retry(self, file_url, max_retries=3):
        """
        Download an image with retry logic for handling security checks.

        Args:
            file_url: URL of the image to download
            max_retries: Maximum number of retry attempts

        Returns:
            Response object if successful, None otherwise
        """
        for attempt in range(max_retries):
            try:
                r = await self.scraper.get_async(file_url)

                # Success
                if r.status_code == 200:
                    self.consecutive_failures = 0
                    return r

                # Not found - try alternate extension
                elif r.status_code == 404:
                    return None

                # Security check or rate limiting
                elif r.status_code in (403, 503, 429):
                    self.consecutive_failures += 1
                    # Much longer waits: 15s, 45s, 90s
                    wait_time = min(15 * (3**attempt), 90)

                    if attempt < max_retries - 1:
                        print(
                            f"\nSecurity check (status {r.status_code}, attempt {attempt + 1}). Waiting {wait_time}s..."
                        )
                        await asyncio.sleep(wait_time)

                        # Refresh session if we've had multiple failures
                        if self.consecutive_failures > 3:
                            await self._refresh_scraper()
                            self.consecutive_failures = 0
                        continue
                    else:
                        print(f"\nFailed after {max_retries} attempts. Skipping this image.")
                        return None

                # Other error
                else:
                    print(f"\nUnexpected status code {r.status_code} for {file_url}")
                    return None

            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"\nError downloading: {e}. Retrying...")
                    await asyncio.sleep(5)
                else:
                    print(f"\nFailed to download {file_url}: {e}")
                    return None

        return None

    async def _download_single_image(self, index, url, new_folder):
        """
        Download a single image.

        Args:
            index: Image index
            url: Image URL
            new_folder: Folder to save the image

        Returns:
            Tuple of (success: bool, img_name: str or None, error_info: tuple or None)
        """
        # Rate limiting: random delay between requests (1-2 seconds) to appear more human
        if index > 0 and not self.disable_delays:
            delay = random.uniform(1.0, 2.5)
            await asyncio.sleep(delay)

        file_url = "https:" + url
        r = await self._download_image_with_retry(file_url)

        # Track the effective URL and extension after fallback
        effective_url = file_url
        effective_extension = file_url.split(".")[-1]

        # Try alternate extension if 404
        if r is None or r.status_code == 404:
            if effective_extension == "jpg":
                alt_url = file_url.replace("jpg", "png")
                effective_extension = "png"
            else:
                alt_url = file_url.replace("png", "jpg")
                effective_extension = "jpg"
            r = await self._download_image_with_retry(alt_url)
            if r and r.status_code == 200:
                effective_url = alt_url

        if r and r.status_code == 200:
            img_name = f"{index}.{effective_extension}"
            try:
                # Run PIL operations in thread pool to avoid blocking
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None,
                    lambda: Image.open(BytesIO(r.content)).save(os.path.join(new_folder, img_name)),
                )
                return (True, img_name, None)
            except OSError as e:
                print(f"\nCannot save {effective_url}: {e}")
                return (False, None, (index, effective_url))
        else:
            return (False, None, (index, effective_url))

    async def _download_list(self, url_iterator):
        """
        Download files from the iterator with concurrent downloads.
        """
        new_folder = os.path.join(self._base_path_modifier(), self.title)
        img_list = []
        failed_images = []

        # Collect all URLs first
        urls = []
        if hasattr(url_iterator, "__aiter__"):
            # Async iterator
            async for url in url_iterator:
                urls.append(url)
        else:
            # Regular iterator
            urls = list(url_iterator)

        if not urls:
            return

        # Use a semaphore to limit concurrent downloads (max 3 at a time)
        semaphore = asyncio.Semaphore(3)

        async def download_with_semaphore(index, url):
            async with semaphore:
                return await self._download_single_image(index, url, new_folder)

        # Create progress bar
        print(f"\nDownloading {len(urls)} images...")

        # Download concurrently
        tasks = [download_with_semaphore(index, url) for index, url in enumerate(urls)]

        # Process results as they complete
        completed = 0
        for coro in asyncio.as_completed(tasks):
            success, img_name, error_info = await coro
            completed += 1

            # Update progress
            progress = (completed / len(urls)) * 100
            print(f"\rProgress: {completed}/{len(urls)} ({progress:.1f}%)", end="", flush=True)

            if success:
                img_list.append(img_name)
            else:
                if error_info:
                    failed_images.append(error_info)

        print()  # New line after progress

        # Report results
        if failed_images:
            print("\n\nDownload Summary:")
            print(f"  Successfully downloaded: {len(img_list)}/{len(urls)} images")
            print(f"  Failed: {len(failed_images)} images")
            if len(failed_images) <= 10:
                print(f"  Failed images: {[idx for idx, _ in failed_images]}")
            if len(failed_images) > len(img_list) * 0.5:
                print("\n⚠️  Warning: More than 50% of images failed. You may need to:")
                print("     1. Wait a few minutes and try again")
                print("     2. Check your internet connection")
                print("     3. Verify the URL is still valid")

        # Sort img_list by index to maintain order for zip
        img_list.sort(key=lambda x: int(x.split(".")[0]))

        # generate cbz file
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._create_zip, new_folder, img_list)

    def _create_zip(self, new_folder, img_list):
        """Create zip file (run in thread pool to avoid blocking)."""
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

    async def download(self):
        """
        Download images.
        """
        new_folder = os.path.join(self._base_path_modifier(), self.title)
        try:
            os.makedirs(new_folder, mode=0o755, exist_ok=True)
        except OSError:
            pass

        try:
            # handle normal image naming rules
            if self.mode == "crawl":
                await self._download_list(self._page_crawl(self.img_link))
            else:
                url_parsed = URLProcessor(self.data_url, self.page_num)
                await self._download_list(url_parsed.normal_url_list())
                await self._download_list(url_parsed.special_url_list())
                await self._download_list(url_parsed.special_url_list(sep="-"))
                await self._download_list(url_parsed.special_url_list(sep="_"))
        finally:
            # Always close the scraper when done
            await self._close_scraper()
