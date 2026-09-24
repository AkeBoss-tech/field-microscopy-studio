import csv
import io
import json
import unittest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor

import test_review
import measurements as m
import server as s


class MeasurementChecks(unittest.TestCase):
    def setUp(self):
        test_review.VolumeReviewChecks.setUp(self)

    def tearDown(self):
        m.geometry.cache_clear()
        test_review.VolumeReviewChecks.tearDown(self)

    def decision(self, **kwargs):
        return m.save(dict(self.q, object=3, status='accepted', note='checked XY/XZ/YZ', expected_revision=None, **kwargs))

    def test_sparse_ids_metrics_filter_and_page(self):
        data = m.table(self.q)
        self.assertEqual([o['id'] for o in data['rows']], [3, 7])
        self.assertEqual(data['rows'][0]['volume_um3'], 54)
        self.assertEqual(data['counts']['unreviewed'], 2)
        self.assertEqual(m.table(dict(self.q, boundary='interior'))['matched'], 1)
        page = m.table(dict(self.q, sort='size_desc', offset=1, limit=1))
        self.assertEqual(page['rows'][0]['id'], 7)
        self.assertEqual(m.table(dict(self.q, search='3'))['matched'], 1)
        stale=m.table(dict(self.q, boundary='interior', offset=50, limit=1))
        self.assertEqual(stale['offset'], 0)
        self.assertEqual(stale['rows'][0]['id'], 3)
        self.assertEqual(m.table(dict(self.q, status='accepted', offset=50))['offset'], 0)
        for values in [dict(status='bad'), dict(boundary='bad'), dict(offset=-1), dict(limit=0), dict(sort='bad')]:
            with self.assertRaises(ValueError):
                m.table(dict(self.q, **values))

    def test_locate_actual_label_and_scope_guards(self):
        for i in [3, 7]:
            p = m.locate(dict(self.q, object=i))['cursor']
            x, y, z = p
            self.assertEqual(int(self.labels[z, y//2, x//2]), i)
        for i in [0, 1, 3.5, 8]:
            with self.assertRaises(ValueError):m.locate(dict(self.q, object=i))
        with self.assertRaises(ValueError):m.table(dict(self.q, channel=0))
        for update in [dict(scope='projection'), dict(historical=True), dict(method='preprocess')]:
            s.atomic(s.STORE/'runs'/self.rid/'run.json', dict(self.run, **update))
            with self.assertRaises(ValueError):m.table(self.q)

    def test_revisions_status_and_immutable_labels(self):
        folder=s.STORE/'runs'/self.rid
        before=(folder/'labels.tif').read_bytes()
        saved=self.decision()
        first=(folder/'reviews'/(saved['revision']+'.json')).read_bytes()
        self.assertEqual(m.table(dict(self.q, status='accepted'))['matched'], 1)
        inspected=test_review.review.inspect_volume(self.q)['object']
        self.assertEqual(inspected['status'], 'accepted')
        with self.assertRaisesRegex(ValueError, 'changed elsewhere'):self.decision()
        again=m.save(dict(self.q, object=3, status='unreviewed', note='', expected_revision=saved['revision']))
        self.assertNotEqual(again['revision'], saved['revision'])
        self.assertEqual(m.table(self.q)['counts']['unreviewed'], 2)
        self.assertEqual((folder/'labels.tif').read_bytes(), before)
        self.assertEqual((folder/'reviews'/(saved['revision']+'.json')).read_bytes(), first)
        self.assertEqual(json.loads((folder/'reviews'/'latest.json').read_text())['parent'], saved['revision'])

    def test_conflicting_writers_only_one_commits(self):
        def attempt(_):
            try:return self.decision()['revision']
            except ValueError:return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(attempt, [1, 2]))
        self.assertEqual(sum(v is not None for v in results), 1)

    def test_export_exact_selection_revision_and_csv_safety(self):
        saved=m.save(dict(self.q, object=3, status='accepted', note='=SUM(1,2)\nreviewed', expected_revision=None))
        q=dict(self.q, status='accepted', boundary='interior', revision=saved['revision'])
        rows=list(csv.DictReader(io.StringIO(m.csv_export(q).decode('utf-8-sig'))))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['object_id'], '3')
        self.assertEqual(rows[0]['volume_um3'], '54.0')
        self.assertEqual(rows[0]['review_revision'], saved['revision'])
        self.assertTrue(rows[0]['note'].startswith("'="))
        self.assertEqual(rows[0]['boundary_policy'], 'interior')
        with self.assertRaisesRegex(ValueError, 'changed'):m.csv_export(dict(q, revision='stale'))
        self.assertEqual(len(list(csv.DictReader(io.StringIO(m.csv_export(dict(q, boundary='edge')).decode('utf-8-sig'))))), 0)

    def test_uncalibrated_never_reports_physical_volume(self):
        s.DATA[self.key]['calibrated']=False
        self.assertIsNone(m.table(self.q)['rows'][0]['volume_um3'])
        for values in [dict(object=0), dict(object=99), dict(status='verified_cell'), dict(note='x'*2001)]:
            with self.assertRaises(ValueError):
                m.save(dict(dict(self.q, object=3, status='accepted', expected_revision=None), **values))

    def test_failed_persistence_keeps_previous_review(self):
        with patch.object(s, 'persist', side_effect=RuntimeError('mirror unavailable')):
            with self.assertRaises(RuntimeError):self.decision()
        self.assertIsNone(m.table(self.q)['revision'])
        saved=self.decision()
        with patch.object(s, 'persist', side_effect=RuntimeError('mirror unavailable')):
            with self.assertRaises(RuntimeError):
                m.save(dict(self.q, object=7, status='rejected', expected_revision=saved['revision']))
        data=m.table(self.q)
        self.assertEqual(data['revision'], saved['revision'])
        self.assertEqual(data['counts']['rejected'], 0)

    def test_run_isolation_and_frozen_source_provenance(self):
        import shutil
        import uuid
        other=uuid.uuid4().hex
        folder=s.STORE/'runs'/other
        shutil.copytree(s.STORE/'runs'/self.rid, folder)
        s.atomic(folder/'run.json', dict(self.run, id=other, sha256='frozen-source-hash'))
        saved=self.decision()
        self.assertEqual(m.table(dict(self.q, run=other))['counts']['accepted'], 0)
        exported=m.csv_export(dict(self.q, run=other)).decode('utf-8-sig')
        self.assertIn('frozen-source-hash', exported)
        self.assertNotIn(saved['revision'], exported)
        with self.assertRaises(ValueError):m.table(dict(self.q, run='../outside'))


if __name__ == '__main__':unittest.main()
