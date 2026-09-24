import unittest

import numpy as np

from tools.synthetic_benchmark import CASES, make_scene, score_instances, validate_scene


STYLE = {"background": 1000.0, "signal": 9000.0, "read_noise": 100.0,
         "source_sha256": None}


class SyntheticBenchmarkTests(unittest.TestCase):
    def test_scene_is_reproducible_with_exact_3d_truth(self):
        first = make_scene((12, 128, 128), 5, "crossing", True, 31, STYLE)
        second = make_scene((12, 128, 128), 5, "crossing", True, 31, STYLE)
        for left, right in zip(first[:3], second[:3]):
            np.testing.assert_array_equal(left, right)
        image, labels, owners, truth = first
        self.assertEqual(image.shape, (12, 128, 128))
        self.assertEqual(set(np.unique(labels)), set(range(6)))
        self.assertEqual(owners.shape, (5, 12, 128, 128))
        self.assertTrue(all(owner.any() for owner in owners))
        self.assertEqual([body["id"] for body in truth["body_centers_zyx"]], list(range(1, 6)))

    def test_matching_penalizes_split_and_missing_candidates(self):
        truth = np.array([[1, 1, 0, 2, 2]], dtype=np.uint16)
        predicted = np.array([[1, 1, 0, 0, 0]], dtype=np.uint16)
        score = score_instances(truth, predicted)
        self.assertEqual(score["truth_count"], 2)
        self.assertEqual(score["candidate_count"], 1)
        self.assertEqual(score["matched_iou_0_3"], 1)
        self.assertEqual(score["recall_iou_0_3"], .5)

    def test_every_case_has_valid_truth_across_seeds(self):
        for seed in (17, 31, 53):
            for name, shape, count, challenge, neurons in CASES:
                with self.subTest(seed=seed, case=name):
                    image, labels, owners, truth = make_scene(shape, count, challenge,
                                                               neurons, seed, STYLE)
                    self.assertEqual(image.shape, labels.shape)
                    self.assertEqual(image.dtype, np.uint16)
                    validate_scene(labels, owners, truth)
                    self.assertEqual(score_instances(labels, labels)["f1_iou_0_3"], 1)

    def test_empty_controls_penalize_false_positives(self):
        _, labels, owners, truth = make_scene((12, 128, 128), 0, "empty", False, 17, STYLE)
        self.assertEqual(truth['body_count'], 0)
        self.assertEqual(owners.shape[0], 0)
        self.assertTrue(score_instances(labels, labels)['empty_scene_correct'])
        predicted = labels.copy()
        predicted[3, 30:35, 30:35] = 1
        score = score_instances(labels, predicted)
        self.assertFalse(score['empty_scene_correct'])
        self.assertEqual(score['false_positive_objects'], 1)
        self.assertEqual(score['f1_iou_0_3'], 0)
        from app.processing import process
        params = dict(method='watershed', scope='volume', units='grid', sigma=.5,
                      background=0, min_size=15, min_final_size=10,
                      distance=7, threshold=4)
        image, _, _, _ = make_scene((1, 128, 128), 0, 'empty', False, 17, STYLE)
        _, prediction, _, _, _ = process(image, params,
                                         dict(spacing=[1, 1, 2], calibrated=True), 1)
        self.assertEqual(score_instances(np.zeros_like(prediction), prediction)['candidate_count'], 0)

    def test_edge_truth_checks_partial_objects(self):
        _, labels, owners, truth = make_scene((12, 128, 128), 2, "edge", False, 19, STYLE)
        validate_scene(labels, owners, truth)
        altered = labels.copy()
        altered[:, :, 0] = 0
        with self.assertRaisesRegex(ValueError, 'truncated'):
            validate_scene(altered, owners, truth)

    def test_validator_rejects_false_touching_claim(self):
        _, labels, owners, truth = make_scene((1, 128, 128), 10, "touching", False, 17, STYLE)
        labels[labels == 2] = 0
        with self.assertRaisesRegex(ValueError, "missing"):
            validate_scene(labels, owners, truth)


if __name__ == "__main__":
    unittest.main()
