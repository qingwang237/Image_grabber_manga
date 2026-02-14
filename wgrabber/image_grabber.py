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
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.table import Table

from .url_processor import URLProcessor

# Global console for rich output
console = Console()


class AsyncCloudScraper(cloudscraper.CloudScraper):
    """Async wrapper for CloudScraper using thread pool executor."""

    async def get_async(self, url, **kwargs):
        """
        Async GET request with Cloudflare bypass.
        Uses executor to run sync cloudscraper in background thread.
        """
        # Run the sync cloudscraper.get() in an executor to not block event loop
        # This properly handles Cloudflare challenges
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(None, lambda: self.get(url, **kwargs))
        return response

    def close(self):
        """Close the scraper session."""
        # CloudScraper cleanup is handled by its parent class
        super().close()


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
        self._failures_lock = asyncio.Lock()  # Protect consecutive_failures from race conditions

        # Adaptive delay mechanism
        self.current_delay = 3.0  # Start with 3 second base delay
        self.min_delay = 2.0  # Minimum delay between requests
        self.max_delay = 15.0  # Maximum delay between requests
        self.success_count = 0  # Track successful requests to gradually reduce delay

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
            self.scraper.close()

    async def _refresh_scraper(self):
        """Recreate the scraper session to get fresh cookies/session."""
        console.print("[yellow]🔄 Refreshing session to bypass security checks...[/yellow]")
        old_scraper = self.scraper
        owned_before = self._own_scraper

        # Create a new scraper that is now owned by this instance
        self.scraper = AsyncCloudScraper(
            browser={"browser": "chrome", "platform": "windows", "mobile": False}
        )
        self._own_scraper = True

        # Clean up the previous scraper only if we owned it
        if owned_before and old_scraper is not None and old_scraper is not self.scraper:
            old_scraper.close()

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
                    async with self._failures_lock:
                        self.consecutive_failures = 0
                    break
                elif r.status_code in (403, 503, 429):
                    wait_time = (2**attempt) * 2
                    if attempt < 2:
                        console.print(
                            f"[yellow]⏳ Security check during URL resolution. Waiting {wait_time}s...[/yellow]"
                        )
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
            console.print("[red]❌ The url is not set.[/red]")
            self.valid = False
            return

        try:
            result = await self.scraper.get_async(self.url)
            if result.status_code != 200:
                self.valid = False
                console.print(f"[red]❌ The url is not valid. Status: {result.status_code}[/red]")
                return
        except Exception as e:
            console.print(f"[red]❌ Failed to fetch URL: {e}[/red]")
            self.valid = False
            return

        soup = BeautifulSoup(result.content, "lxml")
        try:
            h2_tags = soup.find_all("h2")
            if not h2_tags or h2_tags[0].string is None:
                raise IndexError("No title found")
            self.title = h2_tags[0].string.strip()
        except IndexError:
            console.print("[red]❌ Please make sure the url is correct.[/red]")
            self.valid = False
            return

        # Check if pic_box elements exist before accessing
        pic_boxes = soup.find_all("div", attrs={"class": "pic_box"})
        if not pic_boxes:
            console.print("[red]❌ Cannot find any pic_box elements.[/red]")
            self.valid = False
            return

        # Get the last pic_box link
        last_pic_box_link = pic_boxes[-1].find("a")
        if last_pic_box_link is None:
            console.print("[red]❌ Cannot find link in last pic_box.[/red]")
            self.valid = False
            return

        # also save the first link
        first_pic_box = pic_boxes[0]
        if first_pic_box is None:
            console.print("[red]❌ Cannot find pic_box div.[/red]")
            self.valid = False
            return
        first_link = first_pic_box.find("a")
        if first_link is None:
            console.print("[red]❌ Cannot find link in pic_box.[/red]")
            self.valid = False
            return
        first_link = cast(Tag, first_link)
        href = first_link.get("href")
        if href is None:
            console.print("[red]❌ Link has no href attribute.[/red]")
            self.valid = False
            return
        self.img_link = href
        if last_pic_box_link:
            last_pic_box_link = cast(Tag, last_pic_box_link)
            data_url_href = last_pic_box_link.get("href")
            if data_url_href is None:
                console.print("[red]❌ Last pic_box link has no href.[/red]")
                self.valid = False
                return
            self.data_url = await self._url_resolver(data_url_href)
            patten = re.compile(r"頁數")
            label_tag = soup.find("label", text=patten)
            if label_tag is None:
                console.print("[red]❌ Cannot find page number.[/red]")
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
                console.print("[red]❌ Cannot find breadcrumb div.[/red]")
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
                console.print("[red]❌ Cannot determine category from breadcrumb tags.[/red]")
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
            console.print("[red]❌ Cannot find data url.[/red]")
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
            # Adaptive delay BEFORE request (except first page)
            if page_num > 0 and not self.disable_delays:
                # Add random jitter to appear more human
                jitter = random.uniform(-0.5, 0.5)
                actual_delay = max(self.min_delay, self.current_delay + jitter)
                await asyncio.sleep(actual_delay)

            # Retry logic for page fetching
            max_retries = 3
            result = None

            for attempt in range(max_retries):
                try:
                    result = await self.scraper.get_async(url)
                    if result.status_code == 200:
                        async with self._failures_lock:
                            self.consecutive_failures = 0  # Reset failure counter
                        self.success_count += 1

                        # Gradually decrease delay after consistent success (every 5 successful pages)
                        if self.success_count >= 5 and self.current_delay > self.min_delay:
                            self.current_delay = max(self.min_delay, self.current_delay * 0.9)
                            self.success_count = 0

                        break
                    elif result.status_code in (403, 503, 429):
                        async with self._failures_lock:
                            self.consecutive_failures += 1
                        self.success_count = 0  # Reset success counter

                        # Increase delay for future requests
                        self.current_delay = min(self.max_delay, self.current_delay * 1.5)

                        # Exponentially longer waits: 10s, 30s, 60s
                        wait_time = min(10 * (3**attempt), 60)

                        if attempt < max_retries - 1:
                            console.print(
                                f"[yellow]⚠️  Page {page_num + 1}: Security check detected (attempt {attempt + 1}). Waiting {wait_time}s... (adjusting delay to {self.current_delay:.1f}s)[/yellow]"
                            )
                            await asyncio.sleep(wait_time)

                            # Refresh session after 2nd attempt
                            async with self._failures_lock:
                                should_refresh = self.consecutive_failures > 2
                            if attempt == 1 and should_refresh:
                                await self._refresh_scraper()
                        else:
                            console.print(
                                f"[red]❌ Page {page_num + 1}: Failed after {max_retries} attempts. Skipping page.[/red]"
                            )
                            continue
                    else:
                        console.print(
                            f"[red]⚠️  Page {page_num + 1}: Unexpected status {result.status_code}[/red]"
                        )
                        break
                except Exception as e:
                    if attempt < max_retries - 1:
                        console.print(
                            f"[yellow]⚠️  Error fetching page {page_num + 1}: {e}. Retrying...[/yellow]"
                        )
                        await asyncio.sleep(5)
                    else:
                        console.print(f"[red]❌ Failed to fetch page {page_num + 1}: {e}[/red]")
                        continue

            if result is None or result.status_code != 200:
                continue

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
                    async with self._failures_lock:
                        self.consecutive_failures = 0
                    return r

                # Not found - try alternate extension
                elif r.status_code == 404:
                    return None

                # Security check or rate limiting
                elif r.status_code in (403, 503, 429):
                    async with self._failures_lock:
                        self.consecutive_failures += 1
                        current_failures = self.consecutive_failures
                    # Much longer waits: 15s, 45s, 90s
                    wait_time = min(15 * (3**attempt), 90)

                    if attempt < max_retries - 1:
                        console.print(
                            f"[yellow]⏳ Security check (status {r.status_code}, attempt {attempt + 1}). Waiting {wait_time}s...[/yellow]"
                        )
                        await asyncio.sleep(wait_time)

                        # Refresh session if we've had multiple failures
                        if current_failures > 3:
                            await self._refresh_scraper()
                            async with self._failures_lock:
                                self.consecutive_failures = 0
                        continue
                    else:
                        console.print(
                            f"[red]❌ Failed after {max_retries} attempts. Skipping this image.[/red]"
                        )
                        return None

                # Other error
                else:
                    console.print(
                        f"[red]⚠️  Unexpected status code {r.status_code} for {file_url}[/red]"
                    )
                    return None

            except Exception as e:
                if attempt < max_retries - 1:
                    console.print(f"[yellow]⚠️  Error downloading: {e}. Retrying...[/yellow]")
                    await asyncio.sleep(5)
                else:
                    console.print(f"[red]❌ Failed to download {file_url}: {e}[/red]")
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
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(
                    None,
                    lambda: Image.open(BytesIO(r.content)).save(os.path.join(new_folder, img_name)),
                )
                return (True, img_name, None)
            except OSError as e:
                console.print(f"[red]⚠️  Cannot save {effective_url}: {e}[/red]")
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
            # Async iterator - show progress during collection
            console.print(
                Panel.fit(
                    f"[cyan]📖 Collecting image URLs from {self.page_num} pages\n"
                    f"⚙️  Adaptive delay: {self.current_delay:.1f}s (range: {self.min_delay:.1f}s-{self.max_delay:.1f}s)\n"
                    f"🎯 Delay auto-adjusts based on rate limiting[/cyan]",
                    title="[bold cyan]URL Collection[/bold cyan]",
                    border_style="cyan",
                )
            )

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TextColumn("({task.completed}/{task.total} pages)"),
                console=console,
            ) as progress:
                crawl_task = progress.add_task("[cyan]Crawling pages...", total=self.page_num)
                async for url in url_iterator:
                    urls.append(url)
                    progress.update(crawl_task, advance=1)

            console.print(
                f"[green]✅ Collected {len(urls)} images (final delay: {self.current_delay:.1f}s)[/green]"
            )
        else:
            # Regular iterator
            urls = list(url_iterator)

        if not urls:
            return

        # Use a semaphore to limit concurrent downloads (max 3 at a time)
        semaphore = asyncio.Semaphore(3)

        # Shared rate limiter to avoid clustered requests across concurrent tasks
        rate_lock = asyncio.Lock()
        last_request_time = [0.0]  # Use list to allow mutation in nested function

        # Shared rate limiter to avoid clustered requests across concurrent tasks.
        # Ensures at least self.current_delay seconds between download starts.
        rate_lock = asyncio.Lock()
        last_request_time = 0.0

        async def download_with_semaphore(index, url):
            nonlocal last_request_time
            async with semaphore:
                # Global rate limiting across all download tasks
                async with rate_lock:
                    loop = asyncio.get_event_loop()
                    now = loop.time()
                    min_interval = max(getattr(self, "current_delay", 0.0), 0.0)
                    if last_request_time > 0.0 and min_interval > 0.0:
                        elapsed = now - last_request_time
                        wait_time = min_interval - elapsed
                        if wait_time > 0:
                            await asyncio.sleep(wait_time)
                    # Update last_request_time to the moment we start this download
                    last_request_time = loop.time()
                # Global rate limiting across all download tasks
                async with rate_lock:
                    loop = asyncio.get_running_loop()
                    now = loop.time()
                    min_interval = max(self.current_delay, 0.0) if not self.disable_delays else 0.0
                    if last_request_time[0] > 0.0 and min_interval > 0.0:
                        elapsed = now - last_request_time[0]
                        wait_time = min_interval - elapsed
                        if wait_time > 0:
                            await asyncio.sleep(wait_time)
                    # Update last_request_time to the moment we start this download
                    last_request_time[0] = loop.time()
                return await self._download_single_image(index, url, new_folder)

        # Download concurrently with rich progress bar
        tasks = [download_with_semaphore(index, url) for index, url in enumerate(urls)]

        # Process results as they complete with rich progress bar
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("({task.completed}/{task.total} images)"),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            download_task = progress.add_task("[cyan]Downloading images...", total=len(urls))

            for coro in asyncio.as_completed(tasks):
                success, img_name, error_info = await coro

                if success:
                    img_list.append(img_name)
                else:
                    if error_info:
                        failed_images.append(error_info)

                progress.update(download_task, advance=1)

        # Report results with rich table
        if failed_images:
            console.print()
            table = Table(title="Download Summary", show_header=True, header_style="bold magenta")
            table.add_column("Status", style="cyan", width=20)
            table.add_column("Count", justify="right", style="green")

            table.add_row("✅ Successfully downloaded", f"{len(img_list)}/{len(urls)}")
            table.add_row("❌ Failed", f"{len(failed_images)}", style="red")

            console.print(table)

            if len(failed_images) <= 10:
                console.print(
                    f"[yellow]Failed images: {[idx for idx, _ in failed_images]}[/yellow]"
                )

            if len(failed_images) > len(img_list) * 0.5:
                console.print(
                    Panel(
                        "[yellow]⚠️  More than 50% of images failed. You may need to:\n"
                        "   1. Wait a few minutes and try again\n"
                        "   2. Check your internet connection\n"
                        "   3. Verify the URL is still valid[/yellow]",
                        title="[bold yellow]Warning[/bold yellow]",
                        border_style="yellow",
                    )
                )

        # Sort img_list by index to maintain order for zip
        def _safe_sort_key(filename: str):
            # Extract the part before the first dot and try to interpret it as an integer.
            # If this fails (no dot or non-numeric prefix), place the file at the end.
            name, _sep, _ext = filename.partition(".")
            try:
                return int(name)
            except (TypeError, ValueError):
                return float("inf")

        img_list.sort(key=_safe_sort_key)

        # generate cbz file
        console.print("[cyan]📦 Creating CBZ archive...[/cyan]")
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._create_zip, new_folder, img_list)

    def _create_zip(self, new_folder, img_list):
        """Create zip file (run in thread pool to avoid blocking)."""
        # Use absolute paths to avoid os.chdir which is not thread-safe
        zip_path = os.path.join(new_folder, f"{self.title}.cbz")
        zipf = zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED)
        for img in img_list:
            img_path = os.path.join(new_folder, img)
            zipf.write(img_path, arcname=img, compress_type=zipfile.ZIP_DEFLATED)
        zipf.close()

        # Clean up individual images if zip_only is enabled
        if self.zip_only:
            for img in img_list:
                try:
                    os.remove(os.path.join(new_folder, img))
                except OSError as e:
                    console.print(f"[yellow]⚠️  Could not delete {img}: {e}[/yellow]")

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
