from __future__ import annotations

from app.modules.research.product import images
from .conftest import make_jpeg, make_png


def test_sniff_png_and_jpeg():
    p = images.sniff_image(make_png(800, 600))
    assert p and p.fmt == "png" and (p.width, p.height) == (800, 600)
    j = images.sniff_image(make_jpeg(1080, 1920))
    assert j and j.fmt == "jpeg" and (j.width, j.height) == (1080, 1920)


def test_sniff_rejects_html_as_image():
    assert images.sniff_image(b"<!DOCTYPE html><html>404 not found</html>") is None


def _fetcher_map(mapping):
    def fetch(url):
        return mapping[url], "image/png"
    return fetch


def test_download_validates_dedupes_and_drops_small(tmp_path):
    big_a = make_png(800, 600, salt=b"A")
    big_a_dup = make_png(800, 600, salt=b"A")   # identical bytes → dedupe
    big_b = make_png(800, 600, salt=b"B")       # distinct
    small = make_png(100, 100, salt=b"C")       # below min short side → drop
    html = b"<html>error</html>"               # not an image → reject
    urls = ["u_a", "u_a2", "u_b", "u_small", "u_html"]
    mapping = {"u_a": big_a, "u_a2": big_a_dup, "u_b": big_b, "u_small": small, "u_html": html}

    out = images.download_images(
        urls, "job1", fetcher=_fetcher_map(mapping), media_root=str(tmp_path),
    )
    # only big_a and big_b survive (dup, small, html filtered)
    assert len(out) == 2
    fmts = {o.fmt for o in out}
    assert fmts == {"png"}
    for o in out:
        assert o.local_path.startswith(str(tmp_path))


def test_download_tolerates_fetch_errors(tmp_path):
    def boom(url):
        raise RuntimeError("network down")

    out = images.download_images(["x"], "job2", fetcher=boom, media_root=str(tmp_path))
    assert out == []
