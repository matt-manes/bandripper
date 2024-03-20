from pathier import Pathier

root = Pathier(__file__).parent

from bandripper import bandripper

url = "https://cusptunes.bandcamp.com/album/spill-ep"
url2 = "https://cusptunes.bandcamp.com/"


def assert_album(album: bandripper.Album):
    assert album.artist == "Cusp"
    assert album.title == "Spill EP"
    assert len(album.tracks) == 5
    assert album.art_url


def test__albumripper__rip():
    root.mkcwd()
    ripper = bandripper.AlbumRipper(url)
    album = ripper.rip()
    assert_album(album)
    album_path = root / "Cusp" / "Spill EP"
    assert (album_path).exists()
    assert len(list(album_path.glob("*.mp3"))) == 5
    assert len(list(album_path.glob("*.jpg"))) == 1
    album_path.parent.delete()


def test_page_is_discography():
    assert not bandripper.page_is_discography(url)
    assert bandripper.page_is_discography(url2)


def test_track_exists():
    root.mkcwd()
    ripper = bandripper.AlbumRipper(url)
    album = ripper.rip()
    for track in album.tracks:
        assert ripper.track_exists(track)
    assert ripper.save_path
    ripper.save_path.delete()


def test__bandripper__rip():
    root.mkcwd()
    ripper = bandripper.BandRipper(url2)
    albums = ripper.rip()
    assert len(albums) > 1
    assert len(albums) == len(ripper.album_rippers)
    save_path = ripper.album_rippers[0].save_path
    assert save_path
    save_path.parent.delete()
