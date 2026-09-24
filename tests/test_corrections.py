"""Correction revisions must preserve originals and invalidate stale decisions."""
import csv
import io
import unittest
from unittest.mock import patch

import numpy as np

import test_review
import corrections
import measurements as m
import review
import server as s


class CorrectionChecks(unittest.TestCase):
    def setUp(self):
        test_review.VolumeReviewChecks.setUp(self)

    def tearDown(self):
        m.geometry.cache_clear()
        corrections.label_array.cache_clear()
        test_review.VolumeReviewChecks.tearDown(self)

    def change(self, action, revision=None, **values):
        return corrections.save(dict(self.q, action=action,
            expected_label_revision=revision, **values))

    def test_split_preview_revision_and_decision_invalidation(self):
        folder = s.STORE / 'runs' / self.rid
        original = (folder / 'labels.tif').read_bytes()
        decided = m.save(dict(self.q, object=3, status='accepted', note='reviewed',
                              expected_revision=None))
        params = dict(self.q, action='split', object=3, axis='x', coordinate=6,
                      expected_label_revision=None)
        preview = corrections.preview(params)
        self.assertEqual(preview['candidate_count'], 3)
        self.assertTrue(all(preview['planes'][axis] for axis in ('xy', 'xz', 'yz')))
        self.assertFalse((folder / 'corrections' / 'latest.json').exists())
        saved = corrections.save(params)
        self.assertEqual((folder / 'labels.tif').read_bytes(), original)
        self.assertEqual(saved['candidate_count'], 3)
        data = m.table(self.q)
        self.assertEqual(data['label_revision'], saved['label_revision'])
        self.assertEqual(data['counts']['accepted'], 0)
        self.assertEqual(data['counts']['unreviewed'], 3)
        self.assertEqual([o['id'] for o in data['rows']], [3, 7, 8])
        self.assertEqual(review.inspect_volume(dict(self.q, x=8))['object']['id'], 8)
        with self.assertRaisesRegex(ValueError, 'Labels changed'):
            m.save(dict(self.q, object=3, status='rejected', expected_revision=decided['revision'],
                        expected_label_revision=None))
        with self.assertRaisesRegex(ValueError, 'changed elsewhere'):
            corrections.save(params)

    def test_add_merge_delete_undo_and_pinned_exports(self):
        original = self.labels.copy()
        add = self.change('add', x=10, y=6, z=4, radius_xy=2, radius_z=0)
        added_id = m.table(self.q)['rows'][-1]['id']
        self.assertEqual(added_id, 8)
        self.assertEqual(review.inspect_volume(dict(self.q, x=10, y=6, z=4))['object']['id'], 8)
        merged = self.change('merge', revision=add['label_revision'], object=8, target=7)
        self.assertEqual(merged['candidate_count'], 2)
        self.assertFalse(any(o['id'] == 8 for o in m.table(self.q)['rows']))
        deleted = self.change('delete', revision=merged['label_revision'], object=7)
        self.assertEqual(deleted['candidate_count'], 1)
        undone = self.change('undo', revision=deleted['label_revision'])
        self.assertEqual(undone['candidate_count'], 2)
        self.assertEqual(m.table(self.q)['label_revision'], undone['label_revision'])
        self.assertTrue(np.any(corrections.active(self.rid)[0] != original))
        q = dict(self.q, revision='', label_revision=undone['label_revision'], protocol_revision='')
        rows = list(csv.DictReader(io.StringIO(m.csv_export(q).decode('utf-8-sig'))))
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row['label_revision'] == undone['label_revision'] for row in rows))
        with self.assertRaisesRegex(ValueError, 'changed'):
            m.csv_export(dict(q, label_revision=deleted['label_revision']))

    def test_explicit_protocol_and_complete_reviewed_count(self):
        initial = m.table(self.q)
        self.assertFalse(initial['count']['ready'])
        protocol = m.save_protocol(dict(self.q, target='cell bodies', channel_role='body marker',
                                        edge_policy='exclude', expected_revision=None))
        first = m.save(dict(self.q, object=3, status='accepted', note='', expected_revision=None))
        counted = m.table(self.q)
        self.assertTrue(counted['count']['ready'])
        self.assertEqual(counted['count']['reviewed_count'], 1)
        self.assertEqual(counted['count']['excluded_edge_candidates'], 1)
        self.assertEqual(counted['protocol_revision'], protocol['revision'])
        q = dict(self.q, revision=first['revision'], label_revision='', protocol_revision=protocol['revision'])
        exported = m.summary_export(q).decode()
        self.assertIn('"reviewed_count": 1', exported)
        with self.assertRaisesRegex(ValueError, 'changed'):
            m.summary_export(dict(q, protocol_revision='stale'))
        updated = m.save_protocol(dict(self.q, target='cell bodies', channel_role='body marker',
                        edge_policy='include', expected_revision=protocol['revision']))
        self.assertFalse(m.table(self.q)['count']['ready'])
        second = m.save(dict(self.q, object=7, status='rejected', note='edge',
                             expected_revision=first['revision']))
        self.assertTrue(m.table(self.q)['count']['ready'])
        self.assertEqual(m.table(self.q)['count']['reviewed_count'], 1)
        self.assertNotEqual(second['revision'], first['revision'])
        self.assertNotEqual(updated['revision'], protocol['revision'])

    def test_failed_correction_persistence_restores_latest(self):
        params = dict(self.q, action='split', object=3, axis='x', coordinate=6,
                      expected_label_revision=None)
        with patch.object(s, 'persist', side_effect=RuntimeError('mirror unavailable')):
            with self.assertRaises(RuntimeError):
                corrections.save(params)
        self.assertIsNone(corrections.current(s.STORE/'runs'/self.rid)['revision'])
        self.assertEqual(m.table(self.q)['total'], 2)


if __name__ == '__main__':
    unittest.main()
