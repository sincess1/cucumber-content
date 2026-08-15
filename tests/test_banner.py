import unittest
from unittest.mock import patch

from PIL import Image

import make_banner


class BannerTests(unittest.TestCase):
    def test_skips_broken_cover_when_another_cover_works(self):
        items = [{"img": "https://example.com/broken.jpg"}, {"img": "https://example.com/good.jpg"}]
        image = Image.new("RGB", (460, 215))
        with patch.object(make_banner, "load_img", side_effect=[OSError("404"), image]):
            loaded = make_banner.load_covers(items)
        self.assertEqual([item["img"] for item, _ in loaded], ["https://example.com/good.jpg"])

    def test_rejects_banner_when_every_cover_is_broken(self):
        with patch.object(make_banner, "load_img", side_effect=OSError("404")):
            with self.assertRaisesRegex(ValueError, "ни одной обложки"):
                make_banner.load_covers([{"img": "https://example.com/broken.jpg"}])


if __name__ == "__main__":
    unittest.main()
