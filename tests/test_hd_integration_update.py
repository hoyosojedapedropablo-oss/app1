import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('hd_update',Path(__file__).parents[1]/'services/cobalt/integrate_hd.py')
update=importlib.util.module_from_spec(spec);spec.loader.exec_module(update)

class HDUpdateTests(unittest.TestCase):
 def report(self,root):
  records=[]
  for ident in ('JCcuOv5y_9g','rcPWJKs5It4'):
   path=root/('data/cobalt/hd-validation/'+ident+'/download.mp4');path.parent.mkdir(parents=True);path.write_bytes(b'fixture')
   records.append({'video_id':ident,'success':True,'expected_duration':3624,'bytes':7,'path':str(path.relative_to(root)),'measured_width':1920,'measured_height':1080})
  report={'full_downloads_verified':True,'versions':{'yt_dlp':'2026.8.19','bgutil_plugin':'2.0.2'},'results':records}
  (root/'RESULTADO_DESCARGA_HD.json').write_text(json.dumps(report));return report
 def test_requires_both_hd_files_and_remeasures_geometry_before_activation(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);self.report(root);calls=[]
   with patch.object(update,'inspect_hd',return_value={'measured_width':1920,'measured_height':1080}) as measure:
    config=update.validated_config(root,lambda path,duration:calls.append((path,duration)))
   self.assertEqual(len(calls),2);self.assertEqual(measure.call_count,2)
   self.assertEqual(config['minimum_height'],720)
   self.assertEqual(config['quality_profile'],'hd')
 def test_source_claim_of_1080p_does_not_override_low_actual_resolution(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);self.report(root)
   with patch.object(update,'inspect_hd',side_effect=ValueError('360p')):
    with self.assertRaises(ValueError):update.validated_config(root,lambda *args:None)
 def test_report_for_low_quality_or_missing_source_cannot_enable_hd(self):
  for field,value in [('success',False),('measured_height',360),('path','../../outside/download.mp4')]:
   with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp);report=self.report(root);report['results'][0][field]=value
    (root/'RESULTADO_DESCARGA_HD.json').write_text(json.dumps(report))
    with patch.object(update,'inspect_hd',return_value={'measured_width':1920,'measured_height':1080}):
     with self.assertRaises((ValueError,OSError)):update.validated_config(root,lambda *args:None)
 def test_pinned_sources_install_idempotently_and_preserve_old_videos(self):
  source=Path(__file__).parents[1]
  files={name:(source/name).read_bytes() for name in update.FILES}
  self.assertTrue(files)
  self.assertTrue(all(update.digest(content)==update.FILES[name] for name,content in files.items()))
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);self.report(root)
   old=root/'data/old-360p.mp4';old.write_bytes(b'old saved video')
   update.apply_files(root,files,{'enabled':True,'minimum_height':720})
   update.apply_files(root,files,{'enabled':True,'minimum_height':720})
   self.assertEqual(old.read_bytes(),b'old saved video')
   self.assertEqual(json.loads((root/'data/youtube-native.json').read_text())['minimum_height'],720)
 def test_failed_config_write_rolls_back_source_and_prior_360p_configuration(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'data').mkdir();(root/'native_import.py').write_bytes(b'old source');(root/'data/youtube-native.json').write_bytes(b'old config')
   files={'native_import.py':b'new source','app.py':b'new app'}
   real=update.atomic_write
   def fail(path,data):
    if path.name=='youtube-native.json' and data!=b'old config':raise OSError('full disk')
    real(path,data)
   with patch.object(update,'FILES',{name:update.digest(content) for name,content in files.items()}),patch.object(update,'PREVIOUS',{'native_import.py':[update.digest(b'old source')]}),patch.object(update,'atomic_write',side_effect=fail):
    with self.assertRaises(OSError):update.apply_files(root,files,{'minimum_height':720})
   self.assertEqual((root/'native_import.py').read_bytes(),b'old source')
   self.assertEqual((root/'data/youtube-native.json').read_bytes(),b'old config')
   self.assertFalse((root/'app.py').exists())
