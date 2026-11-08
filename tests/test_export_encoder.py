import unittest
from unittest.mock import patch
import app as backend


class ExportEncoderTests(unittest.TestCase):
 def setUp(self):
  previous=backend._nvenc;backend._nvenc=None
  self.addCleanup(setattr,backend,'_nvenc',previous)

 def test_gpu_failure_falls_back_to_cpu_and_stays_on_cpu(self):
  calls=[]
  def fake(args,cwd=None,env=None):
   calls.append(args)
   if 'h264_nvenc' in args:raise RuntimeError('No NVENC capable devices found')
   return ''
  backend._nvenc=True
  with patch.object(backend,'command',side_effect=fake):
   backend.encode(['ffmpeg','-i','in','out.mp4'])
   backend.encode(['ffmpeg','-i','in','out.mp4'])
  self.assertEqual([('h264_nvenc' in c,'libx264' in c) for c in calls],[(True,False),(False,True),(False,True)])
  self.assertTrue(all(c[-1]=='out.mp4' for c in calls))

 def test_cpu_can_be_forced(self):
  with patch.dict(backend.os.environ,{'CLIP_EXPORT_ENCODER':'cpu'}),patch.object(backend.subprocess,'run',side_effect=AssertionError('no probe')):
   self.assertFalse(backend.nvenc_available())

 def test_missing_ffmpeg_means_cpu(self):
  with patch.dict(backend.os.environ,{'CLIP_EXPORT_ENCODER':''}),patch.object(backend.subprocess,'run',side_effect=FileNotFoundError('ffmpeg')):
   self.assertFalse(backend.nvenc_available())


if __name__=='__main__':
 unittest.main()
