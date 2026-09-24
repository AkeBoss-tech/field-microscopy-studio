import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import tifffile

from tools.score_expert_benchmark import score


class ExpertBenchmarkChecks(unittest.TestCase):
    def test_provenance_and_specimen_split(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            labels = np.zeros((2, 8, 8), np.uint16)
            labels[1, 2:5, 2:5] = 1
            tifffile.imwrite(root/'prediction.tif', labels)
            tifffile.imwrite(root/'truth.tif', labels)
            digest = hashlib.sha256((root/'prediction.tif').read_bytes()).hexdigest()
            (root/'run.json').write_text(json.dumps(dict(id='run', method='watershed', scope='volume',
                sha256='source', channel=0, shape=[2, 8, 8])))
            (root/'count.json').write_text(json.dumps(dict(run_id='run', source_sha256='source',
                label_sha256=digest, count=dict(ready=True, target='cell bodies', edge_policy='include'))))
            field = dict(id='field-a', specimen_id='specimen-a', split='development',
                         truth_status='expert_adjudicated', expert_reviewers=['fixture reviewer'],
                         run_json='run.json', count_summary_json='count.json',
                         source_sha256='source', channel_0based=0, count_target='cell bodies',
                         edge_policy='include', corrected_labels='prediction.tif', expert_labels='truth.tif')
            manifest = root/'manifest.json'
            manifest.write_text(json.dumps(dict(version=1, fields=[field])))
            result = score(manifest)
            self.assertEqual(result['fields'][0]['f1_iou_0_3'], 1)
            self.assertEqual(result['splits']['development']['fields'], 1)
            second = dict(field, id='field-b', split='holdout')
            manifest.write_text(json.dumps(dict(version=1, fields=[field, second])))
            with self.assertRaisesRegex(ValueError, 'both development and holdout'):
                score(manifest)
            second['specimen_id'] = 'specimen-b'
            second['truth_status'] = 'assistant_guess'
            manifest.write_text(json.dumps(dict(version=1, fields=[field, second])))
            with self.assertRaisesRegex(ValueError, 'adjudicated expert truth'):
                score(manifest)


if __name__ == '__main__':
    unittest.main()
