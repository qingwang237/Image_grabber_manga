import asyncio
import os
from os.path import expanduser

import click
from rich.console import Console
from rich.panel import Panel

from . import __version__
from .image_grabber import ImageGrabber

console = Console()


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

    console.print(
        Panel.fit(
            f"[cyan]🔍 Validating URL...[/cyan]\n[dim]{url}[/dim]",
            title="[bold cyan]Manga Downloader[/bold cyan]",
            border_style="cyan",
        )
    )

    await manga.validate()

    if manga.valid:
        console.print(
            Panel.fit(
                f"[green]✅ Validation successful![/green]\n"
                f"[cyan]📖 Title:[/cyan] {manga.title}\n"
                f"[cyan]📄 Pages:[/cyan] {manga.page_num}\n"
                f"[cyan]🏷️  Category:[/cyan] {manga.tag}/{manga.subtag}",
                title="[bold green]Ready to Download[/bold green]",
                border_style="green",
            )
        )
        await manga.download()
        console.print("[bold green]✅ Download complete![/bold green]")
    else:
        console.print("[bold red]❌ The start url is not recognized.[/bold red]")


if __name__ == "__main__":
    main()  # pylint: disable=no-value-for-parameter
