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

    def test_validator_rejects_false_touching_claim(self):
        _, labels, owners, truth = make_scene((1, 128, 128), 10, "touching", False, 17, STYLE)
        labels[labels == 2] = 0
        with self.assertRaisesRegex(ValueError, "missing"):
            validate_scene(labels, owners, truth)


if __name__ == "__main__":
    unittest.main()
