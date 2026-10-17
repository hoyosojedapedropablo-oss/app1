import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('quality_manage',Path(__file__).parents[1]/'services/cobalt/manage.py')
manage=importlib.util.module_from_spec(spec);spec.loader.exec_module(manage)

class QualityValidation(unittest.TestCase):
    def test_revalidate_cached_video_download_only_second_and_activate_fast_only(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{},clear=False):
            state=Path(tmp)
            folder=state/'validation'/'previous';folder.mkdir(parents=True)
            video=folder/'download.mp4'
            subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=size=320x180:rate=2','-f','lavfi','-i','sine=frequency=440','-t','1','-c:v','libx264','-c:a','aac',str(video)],check=True)
            config={'enabled':False,'endpoint':'http://127.0.0.1:9000/','api_key':'private fixture'}
            client=state/'client.json';client.write_text(json.dumps(config));(state/'keys.json').write_text('{}')
            first={'video_id':'JCcuOv5y_9g','mode':'fast','success':True,**manage.inspect_media(video,'fast')}
            validation=state/'validation.json';validation.write_text(json.dumps({'config_identity':manage.identity(config),'results':[first,{'video_id':'JCcuOv5y_9g','mode':'original','success':False}]}))
            def download(url,folder,*args,**kwargs):
                self.assertIn('rcPWJKs5It4',url);self.assertEqual(kwargs['mode'],'fast')
                path=folder/'download.mp4';shutil.copy2(video,path);return path,'fixture.mp4'
            with patch.object(manage,'STATE',state),patch.object(manage,'CLIENT',client),patch.object(manage,'VALIDATION',validation),patch('cobalt_import.download',side_effect=download) as transfer:
                self.assertTrue(manage.validate('fast',reuse=True))
                self.assertEqual(transfer.call_count,1)
                records=json.loads(validation.read_text())['results']
                self.assertTrue(next(r for r in records if r['video_id']=='JCcuOv5y_9g' and r['mode']=='fast')['reused'])
                with self.assertRaises(ValueError):manage.activate('all')
                manage.activate('fast')
                self.assertEqual(json.loads(client.read_text())['enabled_modes'],['fast'])

    def test_cached_path_cannot_escape_validation_folder(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(manage,'STATE',Path(tmp)/'state'):
            outside=Path(tmp)/'outside';outside.write_bytes(b'video')
            self.assertIsNone(manage.cached_file({'success':True,'bytes':5,'source_path':str(outside)}))
            with self.assertRaises(ValueError):manage.selected_pairs('invalid')
