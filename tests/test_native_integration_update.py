import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('native_update',Path(__file__).parents[1]/'services/cobalt/integrate_native.py')
update=importlib.util.module_from_spec(spec);spec.loader.exec_module(update)

class IntegrationUpdateTests(unittest.TestCase):
 def report(self,root):
  records=[]
  for ident in ('JCcuOv5y_9g','rcPWJKs5It4'):
   path=root/('data/cobalt/native-validation/'+ident+'/download.mp4');path.parent.mkdir(parents=True);path.write_bytes(b'fixture')
   records.append({'video_id':ident,'success':True,'expected_duration':3624,'bytes':7,'path':str(path.relative_to(root))})
  report={'full_downloads_verified':True,'versions':{'yt_dlp':'2026.8.19','bgutil_plugin':'2.0.2'},'results':records,'provider_counters':{'tokens':0}}
  (root/'RESULTADO_DESCARGA_NATIVA.json').write_text(json.dumps(report))
  return report
 def test_zero_token_report_requires_real_file_verification_for_both_sources(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);self.report(root);calls=[]
   config=update.validated_config(root,lambda path,duration:calls.append((path,duration)))
   self.assertEqual(len(calls),2);self.assertEqual(config['enabled_modes'],['fast'])
   self.assertTrue(config['enabled'])
   self.assertNotIn('provider_counters',config)
 def test_truncated_missing_or_escaping_proof_cannot_enable(self):
  for kind in ('partial','missing','outside'):
   with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp);report=self.report(root)
    if kind=='partial':report['results'][0]['success']=False
    elif kind=='missing':(root/report['results'][0]['path']).unlink()
    else:report['results'][0]['path']='../../outside/download.mp4'
    (root/'RESULTADO_DESCARGA_NATIVA.json').write_text(json.dumps(report))
    with self.assertRaises((ValueError,OSError)):update.validated_config(root,lambda *a:None)
 def test_atomic_failure_restores_existing_sources_and_configuration(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'data').mkdir();(root/'native_import.py').write_bytes(b'old');(root/'data/youtube-native.json').write_bytes(b'old config')
   files={'native_import.py':b'new','youtube_import.py':b'route'}
   expected={name:update.digest(data) for name,data in files.items()}
   real=update.atomic_write
   def fail(path,data):
    if path.name=='youtube-native.json' and data!=b'old config':raise OSError('disk failure')
    real(path,data)
   with patch.object(update,'FILES',expected),patch.object(update,'PREVIOUS',{'native_import.py':[update.digest(b'old')]}),patch.object(update,'atomic_write',side_effect=fail):
    with self.assertRaises(OSError):update.apply_files(root,files,{'enabled':True})
   self.assertEqual((root/'native_import.py').read_bytes(),b'old')
   self.assertEqual((root/'data/youtube-native.json').read_bytes(),b'old config')
   self.assertFalse((root/'youtube_import.py').exists())
 def test_unknown_local_edits_are_preserved(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'native_import.py').write_bytes(b'custom')
   with patch.object(update,'FILES',{'native_import.py':update.digest(b'new')}):
    with self.assertRaises(ValueError):update.apply_files(root,{'native_import.py':b'new'},{'enabled':True})
   self.assertEqual((root/'native_import.py').read_bytes(),b'custom')
 def test_manifest_matches_install_sources_and_repeat_update_keeps_proof_files(self):
  source=Path(__file__).parents[1]
  # This installer deliberately preserves the earlier 360p release. Its pinned
  # sources are immutable even when the working checkout develops HD support.
  import subprocess
  files={name:subprocess.check_output(['git','show',update.REVISION+':'+name],cwd=source) for name in update.FILES}
  self.assertTrue(files)
  self.assertTrue(all(update.digest(content)==update.FILES[name] for name,content in files.items()))
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);self.report(root)
   update.apply_files(root,files,{'enabled':True})
   update.apply_files(root,files,{'enabled':True})
   self.assertTrue((root/'data/cobalt/native-validation/JCcuOv5y_9g/download.mp4').exists())
   self.assertEqual((root/'native_import.py').read_bytes(),files['native_import.py'])
