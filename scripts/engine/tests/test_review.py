from pathlib import Path
import shutil
import tempfile
import unittest

from PIL import Image, ImageChops

from product_video.common import VideoError, run
from product_video.review import extract_frames


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg is required')
class EncodedReviewTests(unittest.TestCase):
    def test_large_selection_extracts_exact_encoded_frames(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            movie = root/'sample.mp4'
            run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=160x90:rate=30',
                 '-t', '4', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', movie])
            frames = list(range(115))
            index = extract_frames(movie, frames, root/'review')
            self.assertEqual([x['frame'] for x in index], frames)
            run(['ffmpeg', '-v', 'error', '-i', movie, '-vf', "select='eq(n,113)'", '-frames:v', '1', root/'reference.png'])
            with Image.open(root/'review'/index[113]['file']) as actual, Image.open(root/'reference.png') as reference:
                self.assertIsNone(ImageChops.difference(actual, reference).getbbox())
            with self.assertRaisesRegex(VideoError, '超出视频范围'):
                extract_frames(movie, [0, 500], root/'bad')
            self.assertFalse(list((root/'bad').glob('frame-*.png')))

    def test_invalid_frame_does_not_run_decoder(self):
        for frames in [[], [-1], [True], [1.5]]:
            with self.assertRaises(VideoError):
                extract_frames('/missing.mp4', frames, '/missing')
