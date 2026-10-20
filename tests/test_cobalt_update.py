import importlib.util
from pathlib import Path
import tempfile
import subprocess
import unittest

spec=importlib.util.spec_from_file_location('media_update',Path(__file__).parents[1]/'services/cobalt/apply_media_fix.py')
update=importlib.util.module_from_spec(spec);spec.loader.exec_module(update)

class UpdateTests(unittest.TestCase):
    def test_verified_update_is_idempotent_and_preserves_private_data(self):
        root_source=Path(__file__).parents[1]
        # Frozen installers are checked against their pinned release, not current code.
        files={name:subprocess.check_output(['git','show',update.REVISION+':'+update.target(root_source,name).relative_to(root_source).as_posix()],cwd=root_source) for name in update.FILES}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);service=root/'services/cobalt';service.mkdir(parents=True)
            data=root/'data/cobalt';data.mkdir(parents=True)
            (data/'keys.json').write_text('private fixture')
            backup,previous=update.apply_files(root,files)
            self.assertEqual((service/'compose.yaml').read_bytes(),files['compose.yaml'])
            self.assertEqual((root/'cobalt_import.py').read_bytes(),files['cobalt_import.py'])
            self.assertEqual((data/'keys.json').read_text(),'private fixture')
            update.apply_files(root,files)
            update.restore_files(root,backup,previous)
            self.assertFalse((service/'compose.yaml').exists())
            self.assertFalse((root/'cobalt_import.py').exists())
            self.assertTrue((data/'keys.json').exists())

    def test_corrupt_package_and_local_edits_are_preserved(self):
        source=Path(__file__).parents[1]
        files={name:subprocess.check_output(['git','show',update.REVISION+':'+update.target(source,name).relative_to(source).as_posix()],cwd=source) for name in update.FILES}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);service=root/'services/cobalt';service.mkdir(parents=True)
            original=service/'compose.yaml';original.write_text('local changes')
            with self.assertRaises(ValueError):update.apply_files(root,files)
            self.assertEqual(original.read_text(),'local changes')
            with self.assertRaises(ValueError):update.apply_files(root,{**files,'media-probe.mjs':b'corrupted'})
            self.assertEqual(original.read_text(),'local changes')
