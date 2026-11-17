"""Read-only native evidence and adversarial acceptance-receipt tests; no game."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import pulse_review as P

ROOT=P.ROOT
CURRENT=ROOT/'private/work/linux_build/stage2c_pulse_native_evidence_20261109/pulse-private-evidence.zip'
PREVIOUS=ROOT/'private/work/linux_build/stage2c_visible_native_evidence_20261109/visible-private-evidence.zip'


class Tests(unittest.TestCase):
    def test_complete_authenticated_native_comparison(self):
        r=P.review(CURRENT,PREVIOUS)
        self.assertEqual(r['child_exit'],0)
        self.assertEqual(r['historical_wrapper_verdict'],'FAIL; unchanged')
        self.assertEqual(r['sole_failed_acceptance_criterion'],'M11 pacing series=host_present')
        self.assertEqual(r['gpu_present_path_records'],858)
        self.assertEqual(r['audio_endpoint_opens'],2)
        self.assertFalse(r['R6025_or_KeBugCheck_recurrence'])

    def test_altered_archive_and_member_lock_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/CURRENT.name;p.write_bytes(CURRENT.read_bytes()+b'edit')
            with self.assertRaisesRegex(ValueError,'hash mismatch'):P.authenticated(p)
        members=dict(P.LOCK['members']);members['exit.json']='0'*64
        with patch.dict(P.LOCK,members=members),self.assertRaisesRegex(ValueError,'Pulse member'):P.authenticated(CURRENT)

    def test_semantic_receipt_tampering_rejected_even_after_envelope_validation(self):
        original=P.authenticated(CURRENT)
        for name,key,value in [('exit','exit',-5),('exit','timed_out_or_interrupted_or_remaining_group',True),
            ('result','status','PASS'),('result','human_saw_game_content','no'),
            ('attempt','timeout_seconds',300),('audio-route','SDL_AUDIO_DRIVER','alsa')]:
            data=copy.deepcopy(original);record=json.loads(data[name+'.json']);record[key]=value
            data[name+'.json']=json.dumps(record).encode()
            with self.subTest(name=name,key=key),patch.object(P,'authenticated',return_value=data),patch.object(P,'sources'),self.assertRaises(ValueError):
                P.review(CURRENT,PREVIOUS)

    def test_new_runtime_failure_not_hidden_by_visible_content_or_exit_zero(self):
        original=P.authenticated(CURRENT)
        for token in ('[error] other failure','(service trap) R6025','import=__imp__KeBugCheck','VK_ERROR_DEVICE_LOST'):
            data=dict(original);data['runtime.log']+=('\n'+token).encode()
            with self.subTest(token=token),patch.object(P,'authenticated',return_value=data),patch.object(P,'sources'),self.assertRaises(ValueError):
                P.review(CURRENT,PREVIOUS)

    def test_old_criteria_still_fail_and_no_marker_is_fabricated(self):
        data=P.authenticated(CURRENT);text=data['process.log'].decode()+'\n'+data['runtime.log'].decode()
        result=P.A.BASE_JUDGE(0,False,text,'yes')
        self.assertEqual(result['status'],'FAIL')
        self.assertFalse(result['milestones']['M11 pacing series=host_present'])
        self.assertNotIn('M11 pacing series=host_present',text)
        self.assertEqual(result['natural_exit_zero'],True)


if __name__=='__main__':unittest.main()
