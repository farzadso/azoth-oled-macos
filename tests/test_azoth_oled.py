"""Unit tests for the parts of azoth-oled that don't need a keyboard."""

import importlib.machinery
import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "azoth-oled"
loader = importlib.machinery.SourceFileLoader("azoth_oled", str(SCRIPT))
spec = importlib.util.spec_from_loader("azoth_oled", loader)
az = importlib.util.module_from_spec(spec)
loader.exec_module(az)


def make_gif(frames, local_color_table=False):
    """Build a structurally valid GIF with the given number of frames."""
    data = bytearray(b"GIF89a")
    data += (2).to_bytes(2, "little") + (2).to_bytes(2, "little")
    data += bytes([0x80, 0, 0])  # global color table of 2 entries
    data += bytes(6)
    for _ in range(frames):
        data += bytes([0x21, 0xF9, 0x04, 0x00, 0x04, 0x00, 0x00, 0x00])  # 40 ms delay
        data += bytes([0x2C, 0, 0, 0, 0, 2, 0, 2, 0, 0x81 if local_color_table else 0])
        if local_color_table:
            data += bytes(12)
        data += bytes([0x02, 0x02, 0x4C, 0x01, 0x00])
    data += b"\x3B"
    return bytes(data)


def log_report(stamp, direction, payload):
    hex_bytes = " ".join(f"{b:02x}" for b in payload[:8]) + "  " + " ".join(f"{b:02x}" for b in payload[8:16])
    verb = "Write to 6975:" if direction == "W" else "Read from 6975:"
    return f"{stamp} DBG service/usb.go:128 > {verb}\n00000000  {hex_bytes}  |................|\n\n"


class CropAreaTest(unittest.TestCase):
    def test_exact_panel_size_is_untouched(self):
        self.assertEqual(az.crop_area(184, 97, "cover"), {"left": 0, "top": 0, "width": 184, "height": 97})

    def test_wide_image_keeps_full_width(self):
        self.assertEqual(az.crop_area(1920, 1080, "cover"), {"left": 0, "top": 34, "width": 1920, "height": 1012})

    def test_square_image_crops_top_and_bottom(self):
        crop = az.crop_area(500, 500, "cover")
        self.assertEqual((crop["width"], crop["left"]), (500, 0))
        self.assertAlmostEqual(crop["width"] / crop["height"], 184 / 97, places=2)

    def test_very_wide_image_crops_the_sides(self):
        crop = az.crop_area(1000, 100, "cover")
        self.assertEqual((crop["height"], crop["top"]), (100, 0))
        self.assertEqual(crop["left"], (1000 - crop["width"]) // 2)

    def test_stretch_uses_the_whole_image(self):
        self.assertEqual(az.crop_area(640, 480, "stretch"), {"left": 0, "top": 0, "width": 640, "height": 480})


class ImageFileTest(unittest.TestCase):
    def write(self, name, data):
        path = Path(self.tmp.name) / name
        path.write_bytes(data)
        return path

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_counts_gif_frames(self):
        self.assertEqual(az.gif_frame_count(self.write("a.gif", make_gif(3))), 3)

    def test_counts_frames_with_local_color_tables(self):
        self.assertEqual(az.gif_frame_count(self.write("b.gif", make_gif(5, local_color_table=True))), 5)

    def test_detects_formats_by_content(self):
        self.assertEqual(az.image_extension(self.write("x.bin", make_gif(1))), "gif")
        self.assertEqual(az.image_extension(self.write("x.png", b"\x89PNG\r\n\x1a\n0000")), "png")
        self.assertEqual(az.image_extension(self.write("x.jpg", b"\xff\xd8\xff\xe0" + bytes(8))), "jpeg")
        self.assertEqual(az.image_extension(self.write("x.bmp", b"BM" + bytes(10))), "bmp")

    def test_rejects_other_files(self):
        with self.assertRaises(az.ToolError):
            az.image_extension(self.write("x.txt", b"hello world!"))

    def test_multipart_body_holds_fields_and_file(self):
        path = self.write("a.gif", make_gif(1))
        body, content_type = az.multipart({"resizeWidth": 184}, "input", path)
        boundary = content_type.split("boundary=")[1]
        self.assertIn(b'name="resizeWidth"\r\n\r\n184\r\n', body)
        self.assertIn(b'name="input"; filename="a.gif"', body)
        self.assertIn(path.read_bytes(), body)
        self.assertTrue(body.endswith(f"--{boundary}--\r\n".encode()))


class EstimateTest(unittest.TestCase):
    def test_matches_a_measured_upload(self):
        # A 72-frame upload took 6:40 over USB.
        self.assertAlmostEqual(az.upload_eta_seconds(72), 400, delta=15)


class TransferProgressTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = Path(self.tmp.name) / "asus.service.log"
        self.original_log = az.SERVICE_LOG
        az.SERVICE_LOG = self.log

    def tearDown(self):
        az.SERVICE_LOG = self.original_log
        self.tmp.cleanup()

    def write_log(self, reports):
        self.log.write_text("".join(log_report(*r) for r in reports))

    def test_reads_total_and_remaining(self):
        self.write_log([
            ("2026-10-22T17:20:03-04:00", "W", bytes([0x61, 0x01, 0, 0, 0x00, 0xE2, 0, 0])),
            ("2026-10-22T17:20:04-04:00", "W", bytes([0x61, 0x02, 0xFF, 0xE1, 0, 0])),
            ("2026-10-22T17:20:05-04:00", "W", bytes([0x61, 0x02, 0x34, 0xC2, 0, 0])),
        ])
        progress = az.TransferProgress()
        self.assertTrue(progress.poll())
        self.assertEqual((progress.total, progress.remaining, progress.finished), (57856, 0xC234, False))
        self.assertIn("14%", az.progress_line(progress, 110))

    def test_finish_report_marks_the_transfer_done(self):
        self.write_log([
            ("2026-10-22T17:20:03-04:00", "W", bytes([0x61, 0x01, 0, 0, 0x05, 0, 0, 0])),
            ("2026-10-22T17:20:04-04:00", "W", bytes([0x61, 0x02, 0x00, 0x00, 0, 0])),
            ("2026-10-22T17:20:05-04:00", "W", bytes([0x61, 0x03])),
        ])
        progress = az.TransferProgress()
        progress.poll()
        self.assertTrue(progress.finished)
        self.assertIn("100%", az.progress_line(progress, 110))

    def test_ignores_packets_before_since(self):
        self.write_log([("2026-10-22T17:20:04-04:00", "W", bytes([0x61, 0x02, 0x10, 0x00, 0, 0]))])
        since = az.datetime.fromisoformat("2026-10-22T18:00:00-04:00")
        self.assertFalse(az.TransferProgress(since=since).poll())


if __name__ == "__main__":
    unittest.main()
