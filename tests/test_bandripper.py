import os
import shutil
from pathlib import Path

import pytest

root = Path(__file__).parent

from bandripper import bandripper

url = "https://cusptunes.bandcamp.com/album/spill-ep"
url2 = "https://cusptunes.bandcamp.com/"


def assert_album(album: bandripper.Album):
    assert album.url == url
    assert album.artist == "Cusp"
    assert album.title == "Spill EP"
    assert len(album.tracks) == 5
    assert album.art_url


def test__albumripper__Album():
    album = bandripper.Album(url)
    assert_album(album)


def test__albumripper__rip():
    os.chdir(root)
    ripper = bandripper.AlbumRipper(url)
    assert_album(ripper.album)
    ripper.rip()
    album_path = root / "Cusp" / "Spill EP"
    assert (album_path).exists()
    assert len(list(album_path.glob("*.mp3"))) == 5
    assert len(list(album_path.glob("*.jpg"))) == 1
    shutil.rmtree(album_path.parent)


def test_clean_string():
    text = "\s.ome / title \\."
    assert bandripper.clean_string(text) == "some  title"


def test_page_is_discography():
    assert not bandripper.page_is_discography(url)
    assert bandripper.page_is_discography(url2)


def test_track_exists():
    os.chdir(root)
    ripper = bandripper.AlbumRipper(url)
    assert_album(ripper.album)
    ripper.rip()
    for track in ripper.album.tracks:
        assert ripper.track_exists(track)
    shutil.rmtree((root / "Cusp"))
