import json
import re
import string
from dataclasses import dataclass
from urllib.parse import urlparse

import argshell
import quickpool
from bs4 import BeautifulSoup, Tag
from gruel import request
from noiftimer import Timer
from pathier import Pathier
from printbuddies import ColorMap
from rich.console import Console
from typing_extensions import Any, Optional

console = Console(style="pink1")
color = ColorMap()
root = Pathier(__file__).parent


@dataclass
class Track:
    title: str
    number: int
    url: str

    @property
    def file_name(self) -> str:
        """This track's title suffixed with `.mp3`."""
        return f"{self.title}.mp3"

    @property
    def numbered_file_name(self) -> str:
        """This track's numbered title suffixed with `.mp3`."""
        return f"{self.numbered_title}.mp3"

    @property
    def numbered_title(self):
        num = str(self.number)
        if len(num) == 1:
            num = "0" + num
        return f"{num} - {self.title}"

    def download(self) -> bytes | None:
        """Download this track and return the data."""
        response = None
        try:
            response = request(self.url)
            response.raise_for_status()
            return response.content
        except Exception as e:
            fail_message = f"Download for {color.a1}{self.title}[/] failed"
            if response:
                console.print(
                    f"{fail_message} with status code {color.br}{response.status_code}."
                )
            else:
                console.print(f"{fail_message}:")
                console.print(e)


@dataclass
class Album:
    artist: str
    title: str
    tracks: list[Track]
    art_url: Optional[str] = None

    def __repr__(self):
        return f"{self.title} by {self.artist}"

    @property
    def art_file_name(self) -> str:
        """Returns the album title with `.jpg` suffixed to it."""
        return f"{self.title}.jpg"

    @property
    def rich_str(self) -> str:
        """A rich tagged string for `"{self.title} by {self.artist}"`."""
        return f"{color.a1}{self.title}[/] by {color.dp1}{self.artist}[/]"

    def download_art(self) -> bytes | None:
        """Download and return album art if this instance has an `art_url`."""
        if not self.art_url:
            console.print(f"No `art_url` provided for {self.rich_str}.")
            return None
        response = None
        try:
            response = request(self.art_url)
            response.raise_for_status()
            return response.content
        except Exception as e:
            fail_message = f"Downloading album art for {self.rich_str} failed"
            if response:
                console.print(
                    f"{fail_message} with status code {color.br}{response.status_code}."
                )
            else:
                console.print(f"{fail_message}:")
                console.print(e)


class AlbumParser:
    def __init__(self, html: str):
        """Parse album details from the html of a bandcamp album page."""
        self._soup = BeautifulSoup(html, "html.parser")

    @property
    def soup(self) -> BeautifulSoup:
        return self._soup

    def clean_string(self, text: str) -> str:
        """Remove punctuation and trailing spaces from text."""
        return re.sub(f"[{re.escape(string.punctuation)}]", "", text).strip()

    def get_album_art_url(self) -> str | None:
        """Returns the url for album art if there is one."""
        image_meta = self.soup.find("meta", attrs={"property": "og:image"})
        if isinstance(image_meta, Tag):
            image_meta_content = image_meta.get("content")
            if isinstance(image_meta_content, str):
                return image_meta_content
        return None

    def get_album_data(self) -> dict[str, Any] | None:
        """Returns a dictionary containing album data if it's present."""
        for script in self.soup.find_all("script"):
            if script.get("data-cart"):
                return json.loads(script.attrs["data-tralbum"])
        return None

    def parse(self) -> Album | None:
        """Parse album page and return `Album` object."""
        if data := self.get_album_data():
            artist = self.clean_string(data["artist"])
            title = self.clean_string(data["current"]["title"])
            tracks = [
                Track(
                    self.clean_string(track["title"]),
                    track["track_num"],
                    track["file"]["mp3-128"],
                )
                for track in data["trackinfo"]
                if track.get("file")
            ]
            art_url = self.get_album_art_url()
            return Album(artist, title, tracks, art_url)
        return None


class AlbumRipper:
    def __init__(
        self, album_url: str, no_track_number: bool = False, overwrite: bool = False
    ):
        """
        :param no_track_number: If True, don't add the track
        number to the front of the track title."""
        self.album_url = album_url
        self.no_track_number = no_track_number
        self.overwrite = overwrite
        self._save_path = None
        self._failed_rips: list[Track] = []

    @property
    def failed_rips(self) -> list[Track]:
        """Returns a list of `Track` objects that failed to download."""
        return self._failed_rips

    @property
    def save_path(self) -> Pathier | None:
        """The path to save tracks to.
        Returns `None` if `self.make_save_path()` hasn't been called on an `Album` instance.
        """
        return self._save_path

    class NoSavePathError(RuntimeError):
        def __init__(self, album: Album | None = None) -> None:
            end_message = "Pass an `Album` instance to `self.make_save_path()` before doing what you just did."
            if not album:
                message = f"No save path set for this album."
            else:
                message = f"No save path set for {album.title} by {album.artist}."
            super().__init__(" ".join([message, end_message]))

    def get_album_page(self) -> str:
        """Make a request to `self.album_url` and return the text content."""
        response = None
        try:
            response = request(self.album_url)
            response.raise_for_status()
        except Exception as e:
            console.print(f"Failed to retrieve page at {color.t2}{self.album_url}.")
            if response:
                console.print(
                    f"Failed with status code {color.br}{response.status_code}."
                )
            raise e
        return response.text

    def make_save_path(self, album: Album):
        """Create save path from album: `{current directory}/{artist}/{album}`"""
        self._save_path = Pathier.cwd() / album.artist / album.title
        self._save_path.mkdir(parents=True, exist_ok=True)

    def rip(self) -> Album:
        """Download and save the album tracks and album art."""
        album = AlbumParser(self.get_album_page()).parse()
        if not album:
            raise RuntimeError(f"No album data was found on {self.album_url}.")
        num_tracks = len(album.tracks)
        if num_tracks == 0:
            console.print(f"No public tracks available for {album.rich_str}.")
            return album
        self.make_save_path(album)
        assert self.save_path
        self.save_album_art(album)
        tracks_to_download = (
            album.tracks
            if self.overwrite
            else [track for track in album.tracks if not self.track_exists(track)]
        )
        num_tracks_to_download = len(tracks_to_download)
        pool = quickpool.ThreadPool(
            [self.save_track] * num_tracks_to_download,
            [(track,) for track in tracks_to_download],
            max_workers=5,
        )
        results = pool.execute(
            description=f"Downloading {color.bg}{num_tracks_to_download}[/] tracks from {album.rich_str}..."
        )
        console.print("Download complete.")
        if self.failed_rips:
            console.print("The following tracks failed to download:")
            for track in self.failed_rips:
                console.print(f"  {color.t2}{track.title}")
        return album

    def save_album_art(self, album: Album):
        """Download and save album art if it has any."""
        if not self.save_path:
            raise self.NoSavePathError(album)
        if album.art_url:
            art = album.download_art()
            if art:
                (self.save_path / album.art_file_name).write_bytes(art)
        else:
            console.print(f"No album art detected for {album.rich_str}.")

    def save_track(self, track: Track) -> bool:
        """Save `track`.
        Returns whether the download was successful or not."""
        if not self.save_path:
            raise self.NoSavePathError()
        file_path = self.save_path / (
            track.file_name if self.no_track_number else track.numbered_file_name
        )
        content = track.download()
        if content:
            file_path.write_bytes(content)
            return True
        self._failed_rips.append(track)
        return False

    def track_exists(self, track: Track) -> bool:
        """Return if a track already exists in `self.save_path`."""
        if not self.save_path:
            raise self.NoSavePathError()
        path = self.save_path / (
            track.file_name if self.no_track_number else track.numbered_file_name
        )
        return path.exists()


class BandRipper:
    def __init__(
        self,
        band_url: str,
        no_track_number: bool = False,
        overwrite: bool = False,
        discography_page_html: str | None = None,
    ):
        self.band_url = band_url
        self.no_track_number = no_track_number
        self.overwrite = overwrite
        self.album_rippers: list[AlbumRipper] = []
        self.discography_page_html = discography_page_html

    def get_album_urls(self) -> list[str]:
        """Get album urls from the main bandcamp url."""
        if not self.discography_page_html:
            self.discography_page_html = self.get_discography_page()
        soup = BeautifulSoup(self.discography_page_html, "html.parser")
        grid = soup.find("ol", attrs={"id": "music-grid"})
        assert isinstance(grid, Tag)
        parsed_url = urlparse(self.band_url)
        base_url = f"https://{parsed_url.netloc}"
        return [base_url + album.a.get("href") for album in grid.find_all("li")]

    def get_discography_page(self) -> str:
        url = f"{color.bb}{self.band_url}[/]"
        console.print(f"Fetching discography from {url}...")
        response = None
        try:
            response = request(self.band_url)
            response.raise_for_status()
        except Exception as e:
            console.print(f"Failed to access {url}.")
            if response:
                console.print(f"Status code: {color.br}{response.status_code}")
            raise e
        return response.text

    def rip(self) -> list[Album]:
        """Rip all publicly available albums from the discography page.
        Returns a list of `Album` objects that were ripped."""
        console.print(f"Searching {color.bb}{self.band_url}[/] for albums...")
        for url in self.get_album_urls():
            self.album_rippers.append(
                AlbumRipper(url, self.no_track_number, self.overwrite)
            )
        console.print(f"Found {color.bg}{len(self.album_rippers)}[/] albums.")
        console.print(f"Beginning rip...")
        timer = Timer(subsecond_resolution=True)
        timer.start()
        fails: list[tuple[AlbumRipper, Exception]] = []
        albums: list[Album] = []
        for ripper in self.album_rippers:
            try:
                album = ripper.rip()
                albums.append(album)
            except Exception as e:
                fails.append((ripper, e))
        timer.stop()
        console.print(
            f"Finished downloading {color.bg}{len(self.album_rippers)}[/] albums in {color.dp1}{timer.elapsed_str}."
        )
        if fails:
            print(f"The following downloads failed:")
            for fail in fails:
                print(f"{fail[0].album_url}: {fail[1]}")
        return albums


def page_is_discography(url: str) -> str | None:
    """Returns the page text if `url` is a discography page.
    `None` if it isn't."""
    response = request(url)
    response.raise_for_status()
    if '<ol id="music-grid"' in response.text:
        return response.text


def get_args() -> argshell.Namespace:
    parser = argshell.ArgumentParser()
    parser.add_argument(
        "urls",
        type=str,
        nargs="*",
        help=" The bandcamp url(s) for the album or artist.\n            If the url is to an artists main page, all albums will be downloaded.\n            The tracks will be saved to a subdirectory of your current directory.\n            If a track can't be streamed (i.e. private) it won't be downloaded. \n            Multiple urls can be passed.",
    )
    parser.add_argument(
        "-n",
        "--no_track_number",
        action="store_true",
        help=" By default the track number will be added to the front of the track title.\n        Pass this switch to disable the behavior.",
    )
    parser.add_argument(
        "-o",
        "--overwrite",
        action="store_true",
        help=" Pass this flag to overwrite existing files.\n        Otherwise tracks that already exist locally will not be downloaded.",
    )
    args = parser.parse_args()
    args.urls = [url.strip("/") for url in args.urls]
    return args


def main(args: argshell.Namespace | None = None):
    if not args:
        args = get_args()
    for url in args.urls:
        if discography_page := page_is_discography(url):
            ripper = BandRipper(
                url, args.no_track_number, args.overwrite, discography_page
            )
        else:
            ripper = AlbumRipper(url, args.no_track_number, args.overwrite)
        ripper.rip()


if __name__ == "__main__":
    main(get_args())
