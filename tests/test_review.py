import base64
import io
import json
import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

import numpy as np
from PIL import Image

os.environ.setdefault('STUDIO_ROOT', str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('STUDIO_STORE', tempfile.mkdtemp())
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import server as s
import review


class VolumeReviewChecks(unittest.TestCase):
    def setUp(self):
        self.key = 'review-fixture-' + uuid.uuid4().hex
        self.rid = uuid.uuid4().hex
        self.source = np.arange(5 * 2 * 8 * 12, dtype=np.uint16).reshape(5, 2, 8, 12)
        source_path = s.STORE / (self.key + '.tif')
        s.tifffile.imwrite(source_path, self.source, metadata={'axes': 'ZCYX'})
        s.DATA[self.key] = dict(id=self.key, name='Coordinate fixture', path=str(source_path),
                               axes='ZCYX', shape=[5, 2, 8, 12], spacing=[.5, .75, 2],
                               channels=['one', 'two'], calibrated=True)
        self.labels = np.zeros((5, 4, 6), np.uint32)
        self.labels[1:4, 1:3, 2:5] = 3
        self.labels[0, 0, 0] = 7
        folder = s.STORE / 'runs' / self.rid
        folder.mkdir(parents=True)
        self.run = dict(id=self.rid, dataset=self.key, channel=1, factor=2, scope='volume',
                        shape=[5, 4, 6], method='watershed', objects=2, meaning='Candidate regions')
        s.atomic(folder / 'run.json', self.run)
        self.processed = s.block_reduce(self.source[:, 1].astype(np.float32), (1, 2, 2), np.mean)
        s.tifffile.imwrite(folder / 'processed.tif', self.processed)
        s.tifffile.imwrite(folder / 'labels.tif', self.labels)
        self.q = dict(dataset=self.key, channel=1, run=self.rid, layer='raw', x=5, y=3, z=2)

    def tearDown(self):
        s.volume.cache_clear()
        s.run_array.cache_clear()
        review.object_index.cache_clear()
        review.display_window.cache_clear()
        s.DATA.pop(self.key)

    def test_exact_planes_and_block_mapping(self):
        cursor = [5, 3, 2]
        np.testing.assert_array_equal(review.plane(self.labels, 'xy', cursor, 2), self.labels[2])
        np.testing.assert_array_equal(review.plane(self.labels, 'xz', cursor, 2), self.labels[:, 1, :])
        np.testing.assert_array_equal(review.plane(self.labels, 'yz', cursor, 2), self.labels[:, :, 2])
        # A whole block, including its far edge, selects the same native region.
        for factor in [1, 2, 4]:
            a = np.arange(5*8*12).reshape(5, 8, 12)
            np.testing.assert_array_equal(review.plane(a, 'xz', [7, 7, 2], factor), a[:, 7//factor])

    def test_physical_metrics_and_native_bounds(self):
        data = review.inspect_volume(self.q)
        obj = data['object']
        self.assertEqual(obj['id'], 3)
        self.assertEqual(obj['voxels'], 18)
        self.assertEqual(obj['volume_um3'], 54)
        self.assertEqual(obj['bounds_native'], [[4, 2, 1], [10, 6, 4]])
        self.assertEqual(obj['boundary_faces'], [])
        self.assertEqual(data['spacing'], [.5, .75, 2])
        self.assertEqual(data['source_intensity'], self.source[2, 1, 3, 5])
        self.assertEqual(data['planes']['xz']['size'], [12, 5])
        self.assertEqual(data['planes']['yz']['size'], [8, 5])
        im = Image.open(io.BytesIO(base64.b64decode(data['planes']['xz']['png'])))
        self.assertEqual(im.size, (12, 5))

    def test_boundary_and_uncalibrated(self):
        s.DATA[self.key]['calibrated'] = False
        obj = review.inspect_volume({**self.q, 'x': 0, 'y': 0, 'z': 0})['object']
        self.assertIsNone(obj['volume_um3'])
        self.assertEqual(set(obj['boundary_faces']), {'X start', 'Y start', 'Z start'})

    def test_scope_channel_and_layer_guards(self):
        with self.assertRaisesRegex(ValueError, 'Unknown dataset'):
            review.inspect_volume({**self.q, 'dataset': 'missing'})
        with self.assertRaisesRegex(ValueError, 'channel'):
            review.inspect_volume({**self.q, 'channel': 0})
        with self.assertRaisesRegex(ValueError, 'channel'):
            s.array_for(self.key, 0, self.rid, 'labels')
        with self.assertRaisesRegex(ValueError, 'ridge'):
            review.inspect_volume({**self.q, 'layer': 'ridge-response'})
        for scope in ['projection', 'slice']:
            s.atomic(s.STORE/'runs'/self.rid/'run.json', {**self.run, 'scope': scope})
            with self.assertRaisesRegex(ValueError, 'volume run'):
                review.inspect_volume(self.q)
        for bad in [-1, 12, .5, 'nan']:
            with self.assertRaises(ValueError):
                review.inspect_volume({**self.q, 'x': bad})

    def test_intensity_only_and_shared_window(self):
        s.atomic(s.STORE/'runs'/self.rid/'run.json', {**self.run, 'method': 'preprocess', 'objects': 0})
        data = review.inspect_volume({**self.q, 'layer': 'processed', 'contrast': 'raw'})
        self.assertIsNone(data['object'])
        self.assertEqual(data['source_window'], data['result_window'])
        self.assertEqual(data['result_value'], self.processed[2, 1, 2])
        raw = review.inspect_volume({**self.q, 'run': '', 'layer': 'raw'})
        self.assertIsNone(raw['object'])
        with self.assertRaisesRegex(ValueError, 'processing run'):
            review.inspect_volume({**self.q, 'run': '', 'layer': 'processed'})

    def test_ridge_response_is_a_separate_layer(self):
        s.atomic(s.STORE/'runs'/self.rid/'run.json', {**self.run, 'method': 'sato', 'ridge_response': True})
        s.tifffile.imwrite(s.STORE/'runs'/self.rid/'ridge-response.tif', self.processed / 1000)
        data = review.inspect_volume({**self.q, 'layer': 'ridge-response'})
        self.assertAlmostEqual(data['result_value'], self.processed[2, 1, 2]/1000, places=6)
        self.assertNotEqual(data['result_window'], data['source_window'])


if __name__ == '__main__':
    unittest.main()
