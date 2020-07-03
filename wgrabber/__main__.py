import os
from os.path import expanduser

import click

from . import __version__
from .image_grabber import ImageGrabber

@click.command()
@click.option("--url", help="The starting url of the manga.")
@click.option("--folder", default="~/Hmanga/", help="The folder to save manga.")
@click.option("--mode", default="crawl", help="The mode for downloading")
@click.version_option(version=__version__, message='Wgrabber %(version)s')
def main(url, folder, mode):
    """
    Command line tool to download the manga from the website Wxxx.
    """
    path = expanduser(folder)
    if not path.endswith(os.path.sep):
        path += os.path.sep
    if url:
        manga = ImageGrabber(url, path, mode)
    else:
        click.echo("\nWarning:\n --url must be provided.\n")
        return
    if manga.valid:
        manga.download()
    else:
        click.echo("The start url is not recognized.")


if __name__ == "__main__":
    main()  # pylint: disable=no-value-for-parameter
