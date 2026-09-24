import io
import json
import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

import numpy as np
import tifffile

os.environ.setdefault('STUDIO_ROOT', str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('STUDIO_STORE', tempfile.mkdtemp())
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import server as s
import external_results
import measurements
import trace_links


class ExternalResultChecks(unittest.TestCase):
    def setUp(self):
        self.key = 'external-' + uuid.uuid4().hex
        self.source = np.arange(4 * 2 * 8 * 12, dtype=np.uint16).reshape(4, 2, 8, 12)
        path = s.STORE / (self.key + '.tif')
        tifffile.imwrite(path, self.source, metadata={'axes': 'ZCYX'})
        s.DATA[self.key] = dict(id=self.key, name='External fixture', path=str(path), axes='ZCYX',
                                shape=[4, 2, 8, 12], spacing=[.5, .75, 2],
                                channels=['process', 'body'], calibrated=True)
        self.labels = np.zeros((4, 4, 6), np.uint16)
        self.labels[1:3, 1:3, 2:4] = 11
        self.labels[0, 0, 0] = 255
        self.q = dict(dataset=self.key, channel='1', name='lab-mask.tif', axes='ZYX',
                      algorithm='Lab model', target='cell bodies', alignment_confirmed='yes')

    def tearDown(self):
        s.DATA.pop(self.key, None)
        s.volume.cache_clear()
        s.run_array.cache_clear()
        s.checksum.cache_clear()
        measurements.geometry.cache_clear()

    def raw(self, labels=None):
        output = io.BytesIO()
        tifffile.imwrite(output, self.labels if labels is None else labels,
                         photometric='minisblack', metadata={'axes': 'ZYX'})
        return output.getvalue()

    def test_import_sparse_ids_review_and_3d_boxes(self):
        raw = self.raw()
        run = external_results.import_labels(self.q, raw)
        folder = s.STORE / 'runs' / run['id']
        self.assertEqual(run['method'], 'external')
        self.assertEqual((run['factor'], run['channel'], run['objects']), (2, 1, 2))
        self.assertEqual((folder / 'submitted-labels.tif').read_bytes(), raw)
        self.assertEqual(json.loads((folder / 'original-ids.json').read_text()), {'1': 11, '2': 255})
        normalized = tifffile.imread(folder / 'labels.tif')
        self.assertEqual(set(np.unique(normalized)), {0, 1, 2})
        q = dict(dataset=self.key, channel=1, run=run['id'], revision='',
                 label_revision='', protocol_revision='')
        table = measurements.table(q)
        self.assertEqual(table['total'], 2)
        boxes = json.loads(measurements.boxes_export(q))['boxes']
        self.assertEqual(boxes[0]['bounds_xyz_end_exclusive'], [[4, 2, 1], [8, 6, 3]])
        self.assertEqual(boxes[0]['bounds_um_xyz_end_exclusive'], [[2, 1.5, 2], [4, 4.5, 6]])
        self.assertEqual(boxes[0]['submitted_object_id'], 11)
        self.assertFalse(table['count']['ready'])
        protocol = measurements.save_protocol({**q, 'target': 'cell bodies', 'channel_role': 'synthetic body',
                                              'edge_policy': 'include', 'expected_revision': None})
        self.assertEqual(protocol['target'], 'cell bodies')

    def test_reject_misalignment_and_noninstance_masks(self):
        with self.assertRaisesRegex(ValueError, 'Confirm'):
            external_results.import_labels({**self.q, 'alignment_confirmed': ''}, self.raw())
        with self.assertRaisesRegex(ValueError, 'Mask Z'):
            external_results.import_labels(self.q, self.raw(self.labels[:2]))
        with self.assertRaisesRegex(ValueError, 'integer IDs'):
            external_results.import_labels(self.q, self.raw(self.labels.astype(np.float32)))
        signed = self.labels.astype(np.int32)
        self.assertEqual(external_results.import_labels(self.q, self.raw(signed))['objects'], 2)
        signed[0, 0, 0] = -1
        with self.assertRaisesRegex(ValueError, 'nonnegative'):
            external_results.import_labels(self.q, self.raw(signed))

    def test_3d_trace_link_across_channels_and_revision(self):
        run = external_results.import_labels(self.q, self.raw())
        proposal = trace_links.nearby(dict(dataset=self.key, run=run['id'],
                                           x=4, y=3, z=1, x2=6, y2=5, z2=2))
        self.assertEqual(proposal['candidates'][0]['object_id'], 1)
        trace = dict(id='trace', type='polyline', domain='volume', channel=0, z=1,
                     points=[[4, 3, 1], [6, 5, 2]], status='unreviewed', label='neurite',
                     owner=dict(run_id=run['id'], object_id=1, label_revision=None,
                                assessment='tentative'))
        saved = s.save_annotations(dict(dataset=self.key, author='QA', items=[trace], base_revision=None))
        owner = saved['items'][0]['owner']
        self.assertEqual((owner['channel_0based'], owner['object_id']), (1, 1))
        csv_text = (s.STORE/'annotations'/self.key/saved['revision']/'measurements.csv').read_text()
        self.assertIn('owner_object_id', csv_text)
        from corrections import save as correct
        correct(dict(dataset=self.key, channel=1, run=run['id'], action='delete', object=1,
                     expected_label_revision=None))
        with self.assertRaisesRegex(ValueError, 'mask changed'):
            s.save_annotations(dict(dataset=self.key, author='QA', items=[trace],
                                    base_revision=saved['revision']))


if __name__ == '__main__':
    unittest.main()
