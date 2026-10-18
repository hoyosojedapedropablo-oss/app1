import importlib.util
import json
from pathlib import Path
import subprocess
import unittest

spec=importlib.util.spec_from_file_location('access',Path(__file__).parents[1]/'services/cobalt/diagnose_access.py')
access=importlib.util.module_from_spec(spec);spec.loader.exec_module(access)

class AccessTests(unittest.TestCase):
    def execute(self,ready):
        script=access.PROBE.replace('__CLIP_VARIANTS__',json.dumps(access.VARIANTS))
        script=script.replace("const {fetch,EnvHttpProxyAgent}=await import('undici');",'''const EnvHttpProxyAgent=class{};
const fetch=async(url,options)=>{
 const [,a,b]=/^bytes=(\\d+)-(\\d+)$/.exec(options.headers.Range);const start=Number(a),end=Number(b);
 if(url.searchParams.get('mode')==='IOS'&&start>0)return new Response('PRIVATE',{status:403});
 return new Response(new Uint8Array(end-start+1),{status:206,headers:{'content-type':'video/mp4','content-range':`bytes ${start}-${end}/918741081`}});
};''')
        script=script.replace("const {env}=await import('./src/config.js');","const env={};")
        script=script.replace("const session=await import('./src/processing/helpers/youtube-session.js');",f"const session={{setup(){{}},getYouTubeSession:()=>({{potoken:{'true' if ready else 'false'}}})}};")
        script=script.replace('i<100','i<1')
        script=script.replace("const {default:extract}=await import('./src/processing/services/youtube.js');",'''const extract=async input=>{
 if(input.quality==='1080'&&env.ytSessionInnertubeClient)throw Error('WRONG_ORDER');
 const mode=input.quality==='1080'?'IOS':env.ytSessionInnertubeClient;
 const urls=[0,1].map(i=>`https://media.googlevideo.com/private?secret=PRIVATE&mode=${mode}&pot=PRIVATE`);
 return {urls,originalRequest:{expectedDuration:3624}};
};''')
        script=script.replace("const {getHeaders}=await import('./src/stream/shared.js');","const getHeaders=()=>({});")
        result=subprocess.run(['node','--input-type=module'],input=script,capture_output=True,text=True,timeout=5,check=True)
        self.assertNotIn('PRIVATE',result.stdout+result.stderr)
        return access.parse_output(result.stdout)

    def test_nonzero_samples_distinguish_rejection_from_attested_access(self):
        report=self.execute(True)
        self.assertTrue(report['session_ready'])
        self.assertEqual(len(report['cases']),3)
        self.assertEqual(report['cases'][0]['tracks'][0]['samples'][1]['http_status'],403)
        for case in report['cases'][1:]:
            for track in case['tracks']:
                self.assertEqual(len(track['samples']),3)
                self.assertTrue(all(sample['complete'] for sample in track['samples']))
                self.assertEqual(track['samples'][1]['start'],15274496)
                self.assertEqual(track['samples'][2]['start'],918741081//2)

    def test_missing_session_skips_attested_clients(self):
        report=self.execute(False)
        self.assertFalse(report['session_ready'])
        self.assertEqual([case['error'] for case in report['cases'][1:]],['SESSION_UNAVAILABLE']*2)

    def test_unstructured_extractor_output_is_not_a_report(self):
        with self.assertRaises(ValueError):access.parse_output('PRIVATE invalid output')

    def test_main_isolates_client_sessions_and_writes_only_structured_results(self):
        import tempfile
        from types import SimpleNamespace
        from unittest.mock import patch
        calls=[]
        def run(command,**kwargs):
            calls.append(kwargs['input'])
            return SimpleNamespace(stdout='CLIP_ACCESS_JSON:'+json.dumps({'schema':1,'session_ready':True,'cases':[{'name':access.VARIANTS[len(calls)-1]['name'],'tracks':[]}]}),stderr='PRIVATE discarded log')
        with tempfile.TemporaryDirectory() as tmp,patch.object(access,'ROOT',Path(tmp)),patch.object(access.subprocess,'run',side_effect=run):
            self.assertEqual(access.main(),0)
            saved=(Path(tmp)/'DIAGNOSTICO_ACCESO.json').read_text()
            self.assertNotIn('PRIVATE',saved)
            self.assertEqual(len(json.loads(saved)['cases']),3)
        self.assertEqual(len(calls),3)
        for script in calls:
            line=next(line for line in script.splitlines() if line.strip().startswith('const variants='))
            self.assertEqual(len(json.loads(line.split('=',1)[1].strip().removesuffix(';'))),1)
