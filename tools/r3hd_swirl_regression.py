"""Focused profile and native-bridge regressions; never starts a game."""
import json
import re
import sys
from pathlib import Path
import r3hd_settings as settings

ROOT=Path(__file__).resolve().parents[1]
reg=settings.load_registry()
checks=0
def check(ok, label):
    global checks
    checks+=1
    if not ok: raise AssertionError(label)

check(settings.resolve(reg,"vanilla")["values"]["power_swirl"]=="original","Vanilla")
check(settings.resolve(reg,"hdplus")["values"]["power_swirl"]=="restored","HD+")
for base in ("vanilla","hdplus"):
    for value in ("original","restored"):
        doc=settings.make_settings(reg,"custom",base,[f"power_swirl={value}"])
        resolved=settings.resolve(reg,settings=doc)
        check(resolved["values"]["power_swirl"]==value,f"Custom {base}/{value}")
        check(resolved["base"]==base,"Custom base retained")
check(settings.resolve(reg,"hdplus",explicit={"power_swirl":"original"})["values"]["power_swirl"]=="original","explicit A/B override")
play=(ROOT/'tools/play.ps1').read_text(encoding='utf-8')
check("[ValidateSet('original', 'restored')][string]$PowerSwirl = 'original'" in play,"parameter contract")
for token in ("PowerSwirl = 'power_swirl'","$env:R3HD_POWER_SWIRL = $PowerSwirl",
              "$env:R3HD_POWER_SWIRL = $savedPowerSwirl","power_swirl = $PowerSwirl"):
    check(token in play,"launcher lifecycle "+token)
host=(ROOT/'tools/m2_host/r3hd_swirl.cpp').read_text(encoding='utf-8')
check(host.index('!Enabled()')<host.index('Load(base,old_sp+152)'),"Vanilla returns before reads")
check('sub_8231A6E0(call,base)' in host and 'sub_8231A608(call,base)' in host,"both constant banks")
check('ChangedGroups' in host and 'group*4' in host and '63-group' in host,"dirty mask follows restored ranges")
check('~RestoreFaultContext' in host,"fault diagnostic context lifetime")
check('R3HD_MODS_PLAN' not in host and 'ago_pick_' not in host,"no private texture lookup or mod bypass")
check('sub_821D1BE8(call,base)' in host,"native caches invalidated")
if '--run' in sys.argv:
    for name in sys.argv[sys.argv.index('--run')+1:]:
        run=ROOT/'private/work/m6_runs'/name
        log='\n'.join(p.read_text(encoding='utf-8',errors='replace') for p in sorted(run.glob('runtime*.log')))
        check(bool(log),name+' log')
        modes=re.findall(r'SWIRL power_swirl=(\w+)',log)
        check(len(modes)==1,name+' one resolved mode')
        expected='restored' if '_on_' in name else 'original'
        check(modes==[expected],name+' mode')
        check(('SWIRL native_quad submitted' in log)==(expected=='restored'),name+' submission')
        check('SWIRL constant restoration failed' not in log and 'SWIRL rejected' not in log,name+' state/geometry')
        for physical,fetch,hash_ in re.findall(r'physical=([0-9A-F]+) fetch=([0-9A-F]+) hash=([0-9A-F]+)',log):
            check(physical==fetch,name+' resource owns fetch')
            check(int(hash_,16)!=0,name+' bounded texture hash')
print(f'R3HD_SWIRL_REGRESSION PASS checks={checks}')
