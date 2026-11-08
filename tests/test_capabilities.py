import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import capabilities


class CapabilitiesTests(unittest.TestCase):
 def setUp(self):
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
  patcher=patch.object(capabilities,'SETTINGS',Path(tmp.name)/'performance.json');patcher.start();self.addCleanup(patcher.stop)
  capabilities._cache=None;self.addCleanup(setattr,capabilities,'_cache',None)

 def ready(self,cuda=True,free=6000):
  return patch.object(capabilities,'whisper_cuda_ready',return_value=(cuda,'motivo')),patch.object(capabilities,'free_vram_mb',return_value=free),patch.object(capabilities,'nvidia_gpu',return_value=None)

 def test_gpu_chosen_only_with_cuda_and_free_vram(self):
  a,b,c=self.ready(True,6000)
  with a,b,c:self.assertEqual(capabilities.transcription_plan()[0],'cuda')
  capabilities._cache=None;a,b,c=self.ready(True,900)
  with a,b,c:device,reason=capabilities.transcription_plan()
  self.assertEqual(device,'cpu');self.assertIn('900 MB',reason)
  capabilities._cache=None;a,b,c=self.ready(False)
  with a,b,c:self.assertEqual(capabilities.transcription_plan()[0],'cpu')

 def test_user_can_force_cpu(self):
  capabilities.save_settings({'transcription':'cpu','export':'cpu','bogus':'gpu'})
  self.assertEqual(capabilities.read_settings(),{'transcription':'cpu','export':'cpu'})
  a,b,c=self.ready(True,6000)
  with a,b,c:self.assertEqual(capabilities.transcription_plan()[0],'cpu')

 def test_invalid_saved_modes_fall_back_to_auto(self):
  capabilities.SETTINGS.write_text('{"transcription":"turbo"}',encoding='utf-8')
  self.assertEqual(capabilities.read_settings()['transcription'],'auto')

 def test_nvidia_smi_parsing_and_absence(self):
  out=subprocess.CompletedProcess([],0,stdout='NVIDIA GeForce RTX 5060 Ti, 610.88, 8151, 6200\n')
  self.assertEqual(capabilities.nvidia_gpu(run=lambda *a,**k:out),{'name':'NVIDIA GeForce RTX 5060 Ti','driver':'610.88','vram_total_mb':8151,'vram_free_mb':6200})
  self.assertIsNone(capabilities.nvidia_gpu(run=lambda *a,**k:(_ for _ in ()).throw(FileNotFoundError())))

 def test_memory_reports_numbers(self):
  info=capabilities.memory();self.assertGreater(info['total_gb'],0)


class TranscriptionFallbackTests(unittest.TestCase):
 def test_cuda_failure_retries_on_cpu(self):
  import app as backend,threading
  used=[]
  class Fake:
   def __init__(self,device):self.device=device
   def transcribe(self,audio,**kw):
    used.append(self.device)
    if self.device=='cuda':raise RuntimeError('CUDA out of memory')
    class S:start=0.;end=1.;text=' hola';words=[]
    return iter([S()]),None
  job={'duration':10,'timings':{}}
  with patch.object(capabilities,'transcription_plan',return_value=('cuda','ok')),patch.object(backend,'whisper_model',side_effect=Fake):
   transcript,device=backend.transcribe_audio(None,job,threading.Event())
  self.assertEqual(used,['cuda','cpu']);self.assertEqual(device,'cpu');self.assertEqual(transcript[0]['text'],' hola')


if __name__=='__main__':
 unittest.main()


class ReclaimableVramTests(unittest.TestCase):
 def test_vram_freed_by_ollama_counts_for_the_plan(self):
  capabilities._cache=None;self.addCleanup(setattr,capabilities,'_cache',None)
  with tempfile.TemporaryDirectory() as tmp,patch.object(capabilities,'SETTINGS',Path(tmp)/'p.json'),patch.object(capabilities,'whisper_cuda_ready',return_value=(True,'ok')),patch.object(capabilities,'free_vram_mb',return_value=1100),patch.object(capabilities,'nvidia_gpu',return_value=None):
   self.assertEqual(capabilities.transcription_plan()[0],'cpu')
   self.assertEqual(capabilities.transcription_plan(reclaimable_mb=4700)[0],'cuda')
