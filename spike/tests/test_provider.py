"""Current release dispatcher refuses absent/untrusted selection and keeps SDK4 identities."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
HERE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('primary_provider_test',HERE/'provider.py')
provider=importlib.util.module_from_spec(spec);spec.loader.exec_module(provider)
class ProviderTests(unittest.TestCase):
    def test_full_model_unavailable(self):self.assertFalse(provider.device_simulator()['available'])
    def test_actual_source_bound_release_is_functional_only(self):
        value=provider.experimental_functional_simulator()
        self.assertTrue(value['available'],value.get('reason'));self.assertEqual(value['native_device_abi'],4)
        self.assertFalse(value['timing_available']);self.assertFalse(value['rtl_certified'])
        self.assertNotEqual(value['binary_sha256'],value['native_binary_sha256'])
    def test_missing_current_refuses(self):
        with tempfile.TemporaryDirectory()as root,patch.object(provider,'HERE',Path(root)):
            self.assertFalse(provider.experimental_functional_simulator()['available'])
    def test_external_current_refuses_before_loading(self):
        with tempfile.TemporaryDirectory()as temporary:
            root=Path(temporary);(root/'releases').mkdir();(root/'current').symlink_to(HERE/'current',target_is_directory=True)
            with patch.object(provider,'HERE',root):self.assertFalse(provider.experimental_functional_simulator()['available'])
    def test_legacy_or_malformed_metadata_refuses(self):
        for text in ['{','{"schema":"old-abi1"}']:
            with self.subTest(text=text),tempfile.TemporaryDirectory()as temporary:
                root=Path(temporary);release=root/'releases/fixture';release.mkdir(parents=True);(root/'current').symlink_to('releases/fixture',target_is_directory=True)
                (release/'provenance.json').write_text(text)
                with patch.object(provider,'HERE',root):self.assertFalse(provider.experimental_functional_simulator()['available'])
if __name__=='__main__':unittest.main()
