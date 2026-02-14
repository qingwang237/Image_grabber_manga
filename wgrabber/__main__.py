import asyncio
import os
from os.path import expanduser

import click

from . import __version__
from .image_grabber import ImageGrabber


@click.command()
@click.argument("url")
@click.option("--folder", default="~/Hmanga/", help="The folder to save manga.")
@click.option("--mode", default="crawl", help="The mode for downloading")
@click.option(
    "--zip-only",
    is_flag=True,
    default=False,
    help="Keep only the zip file and delete individual images after compression.",
)
@click.version_option(version=__version__, message="Wgrabber %(version)s")
def main(url, folder, mode, zip_only):
    """
    Command line tool to download the manga from the website Wxxx.
    """
    path = expanduser(folder)
    if not path.endswith(os.path.sep):
        path += os.path.sep

    # Run async operations
    asyncio.run(async_main(url, path, mode, zip_only))


async def async_main(url, path, mode, zip_only):
    """Async main function to handle the manga download."""
    manga = ImageGrabber(url, path, mode, zip_only=zip_only)
    try:
        await manga.validate()

        if manga.valid:
            await manga.download()
        else:
            click.echo("The start url is not recognized.")
    finally:
        # Ensure the scraper session is properly closed
        await manga._close_scraper()


if __name__ == "__main__":
    main()  # pylint: disable=no-value-for-parameter
