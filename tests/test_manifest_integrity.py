import unittest

import pandas as pd

from eval.evaluate_test import DATA, MANIFEST


class ManifestIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = pd.read_csv(MANIFEST, dtype=str).fillna("")

    def test_every_manifest_recording_exists(self):
        missing = [
            filename
            for filename in self.manifest["file"]
            if not (DATA / filename).is_file()
        ]

        self.assertEqual(missing, [])

    def test_held_out_test_set_size_is_preserved(self):
        test_runs = self.manifest[self.manifest["role"] == "test"]

        self.assertEqual(len(test_runs), 8)
        self.assertEqual(test_runs["file"].nunique(), 8)

    def test_healthy_baselines_are_training_only_and_partial_is_excluded(self):
        healthy_files = {
            "data_healthy_pages.csv",
            "data_healthy_pages_2_complete.csv",
        }
        healthy_rows = self.manifest[self.manifest["file"].isin(healthy_files)]

        self.assertEqual(set(healthy_rows["file"]), healthy_files)
        self.assertTrue((healthy_rows["role"] == "train").all())
        self.assertFalse(
            self.manifest["file"].eq("data_healthy_pages_2.csv").any()
        )


if __name__ == "__main__":
    unittest.main()
