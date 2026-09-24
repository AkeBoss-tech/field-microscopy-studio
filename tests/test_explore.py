"""Display projections and bounded 3D sampling use native source coordinates."""
import io
import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

import numpy as np
import tifffile
from PIL import Image

os.environ.setdefault('STUDIO_ROOT', str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('STUDIO_STORE', tempfile.mkdtemp())
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import server as s
import external_results
from corrections import save as correct


class ExploreDisplayChecks(unittest.TestCase):
    def setUp(self):
        self.key = 'explore-' + uuid.uuid4().hex
        self.source = np.zeros((4, 1, 8, 12), np.uint16)
        self.source[:, 0] = 5
        self.source[1:3, 0, 2:6, 4:8] = 50
        self.source[2, 0, 3, 5] = 200
        self.path = s.STORE / (self.key + '.tif')
        tifffile.imwrite(self.path, self.source, metadata={'axes': 'ZCYX'})
        s.DATA[self.key] = dict(id=self.key, name='Explore fixture', path=str(self.path), axes='ZCYX', shape=[4, 1, 8, 12], spacing=[1, 1, 2], channels=['body'])

    def tearDown(self):
        s.DATA.pop(self.key, None)
        s.volume.cache_clear()
        s.run_array.cache_clear()

    def test_projection_modes_and_background(self):
        images = {}
        for method in ('max', 'mean', 'sum'):
            q = dict(dataset=self.key, channel='0', view='projection', projection=method)
            images[method] = np.asarray(Image.open(io.BytesIO(s.png_view(q))))
        self.assertGreater(images['mean'][3, 5], images['mean'][0, 0])
        self.assertGreater(images['max'][3, 5], images['max'][0, 0])
        self.assertFalse(np.array_equal(images['max'], images['mean']))
        normalized = np.asarray(Image.open(io.BytesIO(s.png_view(dict(dataset=self.key, channel='0', view='slice', z='2', background='local')))))
        self.assertGreater(normalized[3, 5], normalized[0, 0])
        with self.assertRaisesRegex(ValueError, 'projection'):
            s.png_view(dict(dataset=self.key, projection='median'))

    def test_3d_region_and_corrected_isolated_object(self):
        region = s.points_view(dict(dataset=self.key, channel='0', bounds='4,2,1,8,6,3'))
        self.assertEqual(region['bounds_native'], [[4, 2, 1], [8, 6, 3]])
        self.assertTrue(region['points'])
        self.assertTrue(all(4 <= p[0] < 8 and 2 <= p[1] < 6 and 1 <= p[2] < 3 for p in region['points']))
        atlas = np.asarray(Image.open(io.BytesIO(s.volume_atlas(dict(dataset=self.key, channel='0', bounds='4,2,1,8,6,3')))))
        self.assertEqual(atlas.shape, (8, 4))  # Two Z planes stacked vertically.
        self.assertGreater(int(atlas.max()), int(atlas.min()))
        with self.assertRaisesRegex(ValueError, 'bounds'):
            s.points_view(dict(dataset=self.key, bounds='8,2,1,4,6,3'))
        labels = np.zeros((4, 4, 6), np.uint16)
        labels[1:3, 1:3, 2:4] = 9
        labels[1, 1, 2] = 0  # A hole in the bounding box must stay hidden.
        raw = io.BytesIO()
        tifffile.imwrite(raw, labels, photometric='minisblack', metadata={'axes': 'ZYX'})
        run = external_results.import_labels(dict(dataset=self.key, channel='0', name='labels.tif', axes='ZYX', algorithm='Fixture', target='cell bodies', alignment_confirmed='yes'), raw.getvalue())
        selected = s.points_view(dict(dataset=self.key, channel='0', overlay=run['id'], object='1'))
        self.assertEqual(selected['bounds_native'], [[4, 2, 1], [8, 6, 3]])
        self.assertTrue(selected['points'])
        self.assertTrue(all(p[4] == 1 for p in selected['points']))
        isolated = np.asarray(Image.open(io.BytesIO(s.volume_atlas(dict(dataset=self.key, channel='0', overlay=run['id'], object='1')))))
        self.assertEqual(isolated.shape, (8, 4))
        self.assertGreater(int(isolated.max()), 0)
        self.assertEqual(int(isolated[0, 0]), 0)
        correct(dict(dataset=self.key, channel=0, run=run['id'], action='delete', object=1, expected_label_revision=None))
        with self.assertRaisesRegex(ValueError, 'absent'):
            s.points_view(dict(dataset=self.key, channel='0', overlay=run['id'], object='1'))


if __name__ == '__main__':
    unittest.main()
