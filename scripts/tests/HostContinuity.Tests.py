"""验证宿主策略、平台隔离、睡眠证据与有界进程清理；不修改能源设置。"""
import datetime as dt
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import os
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('host',ROOT/'scripts/maintenance/host_continuity.py')
host=importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)


class HostTests(unittest.TestCase):
    def reader(self,command):
        return {('pmset','-g','custom'):'Battery Power:\n sleep 1\nAC Power:\n sleep 0\n displaysleep 10\n',
                ('pmset','-g','batt'):"Now drawing from 'AC Power'\n",
                ('pmset','-g','assertions'):' PreventUserIdleSystemSleep 1\n PreventSystemSleep 0\n PreventUserIdleDisplaySleep 0\n',
                ('ioreg','-n','Root','-d1'):'"IOConsoleLocked" = Yes'}[tuple(command)]

    def test_ac_policy_allows_display_sleep_but_not_idle_system_sleep(self):
        result=host.inspect('Darwin',self.reader)
        self.assertEqual(result['assurance'],'POLICY_READY')
        self.assertTrue(result['screenLocked'])
        self.assertEqual(result['lockDisplayTrial'],'NOT_VERIFIED')
        self.assertEqual(result['sessionContinuity'],'NOT_VERIFIED')
        self.assertNotIn('Battery',str(result))

    def test_active_unowned_assertion_cannot_replace_policy(self):
        def reader(command):
            value=self.reader(command)
            return value.replace('sleep 0','sleep 1') if command[-1]=='custom' else value
        self.assertEqual(host.inspect('Darwin',reader)['assurance'],'BLOCKED_HOST_SLEEP_ASSURANCE')

    def test_display_kept_on_and_battery_and_unknown_are_not_assured(self):
        for key,replacement in [('custom','AC Power:\n sleep 0\n displaysleep 0\n'),('batt',"Now drawing from 'Battery Power'"),('custom',None)]:
            def reader(command):
                return replacement if command[-1]==key else self.reader(command)
            self.assertEqual(host.inspect('Darwin',reader)['assurance'],'BLOCKED_HOST_SLEEP_ASSURANCE')

    def test_linux_and_windows_never_invoke_pmset(self):
        for system in ['Linux','Windows']:
            with self.subTest(system=system):
                result=host.inspect(system,lambda _:self.fail('跨平台不得调用macOS命令'))
                self.assertEqual(result['assurance'],'NOT_APPLICABLE')

    def test_sleep_wake_windows_and_display_off_are_distinct(self):
        start=dt.datetime(2026,10,31,4,tzinfo=dt.timezone.utc)
        raw='\n'.join(['2026-10-31 12:00:10 +0800 Sleep Entering Sleep state due to \'Idle Sleep\': private-device',
                       '2026-10-31 12:00:30 +0800 DarkWake DarkWake from Deep Idle private-device',
                       '2026-10-31 12:00:40 +0800 Notification Display is turned off',
                       '2026-10-31 12:00:45 +0800 Sleep Entering Sleep state due to \'Idle Sleep\'',
                       '2026-10-31 12:01:10 +0800 Wake Wake from Deep Idle'])
        value=host.sleep_events(raw,start,start+dt.timedelta(minutes=1))
        self.assertEqual(value['confirmedSleepMs'],35000)
        self.assertEqual(len(value['events']),3)
        self.assertNotIn('private-device',str(value))
        self.assertEqual(host.sleep_events(None,start,start)['status'],'NOT_VERIFIED')
        self.assertEqual(host.sleep_events('',start,start)['confirmedSleepMs'],0)

    def test_carry_in_sleep_and_open_interval_are_clipped(self):
        start=dt.datetime(2026,10,31,4,tzinfo=dt.timezone.utc)
        raw='2026-10-31 11:59:00 +0800 Sleep Entering Sleep state due to \'Idle Sleep\'\n'
        self.assertEqual(host.sleep_events(raw,start,start+dt.timedelta(seconds=10))['confirmedSleepMs'],10000)

    def test_output_rejects_source_and_symlink(self):
        with self.assertRaises(ValueError):host.output_path(ROOT/'docs/evidence/unsafe.json')
        with self.assertRaises(ValueError):host.output_path(ROOT/'artifacts/../docs/evidence/unsafe.json')
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):host.output_path(Path(folder)/'log.json')

    def test_real_link_is_refused_before_directory_creation(self):
        base=ROOT/'artifacts/g3-m5/host'
        base.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory() as folder:
            linked=base/('linked-'+str(os.getpid()))
            try:
                linked.symlink_to(folder,target_is_directory=True)
                with self.assertRaises(ValueError):host.output_path(linked/'bad.json')
                self.assertFalse((Path(folder)/'bad.json').exists())
            finally:linked.unlink()

    def test_fixture_not_verified_is_nonzero(self):
        with patch.object(host,'fixture',return_value={'status':'NOT_VERIFIED'}),patch.object(sys,'argv',['host','fixture']):
            self.assertEqual(host.main(),2)

    def test_monitor_policy_or_sleep_failure_is_nonzero(self):
        for ready,sleep in [(False,0),(True,1000),(True,None)]:
            summary={'policyContinuouslyReady':ready,'sleep':{'status':'NOT_VERIFIED' if sleep is None else 'OBSERVED_LOG_WINDOW','confirmedSleepMs':sleep}}
            with patch.object(host,'output_path',return_value=Path('does-not-exist')),patch.object(host,'monitor',return_value=summary),patch.object(sys,'argv',['host','monitor','--output','fixture']):
                self.assertEqual(host.main(),2)

    def test_cli_preserves_child_failure_and_rejects_no_command(self):
        path=ROOT/'scripts/maintenance/host_continuity.py'
        result=subprocess.run([sys.executable,str(path),'cli','--',sys.executable,'-c','raise SystemExit(17)'],capture_output=True)
        self.assertEqual(result.returncode,17)
        result=subprocess.run([sys.executable,str(path),'cli'],capture_output=True)
        self.assertEqual(result.returncode,2)

    def test_cli_command_is_standard_caffeinate_without_display_flags(self):
        with patch.object(host.platform,'system',return_value='Darwin'),patch.object(host.subprocess,'run') as run,patch.object(sys,'argv',['host','cli','--','codex']):
            run.return_value.returncode=0
            self.assertEqual(host.main(),0)
            self.assertEqual(run.call_args.args[0],['/usr/bin/caffeinate','-is','codex'])


if __name__=='__main__':unittest.main()
