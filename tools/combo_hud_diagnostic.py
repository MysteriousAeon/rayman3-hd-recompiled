"""Read-only event diagnostics for the explicitly invoked private playable launcher.

No game starter or input/window APIs. At most eight event-specific readbacks;
all logs, trace data and copied saves stay in the launcher's private session.
"""
import hashlib
import json
import re
import struct
import threading
import time

from m5_live import Process, Actor, i32, f32, u8


def profile_hashes(path):
    return {str(p.relative_to(path)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(path.rglob('*')) if p.is_file()}


def configure(command, env, session, mode):
    command = [f'--user_data_root={session / "user"}' if s.startswith('--user_data_root=')
               else f'--cache_root={session / "cache"}' if s.startswith('--cache_root=')
               else s for s in command]
    env = dict(env, R3HD_FRAME_REQUEST=str(session / 'frame.request'), R3HD_M22_DRAW_TRACE='1',
               R3HD_TEST_COMBO_CAPTURE='1')
    if mode == 'off':
        env.pop('R3HD_TEST_COMBO_CLOSE', None)
        env.pop('R3HD_TEST_COMBO_PLAYTEST', None)
    return command, env


def resolve_combo_object(process):
    """Mirror guest821ABC88: active command10029 handle -> registered payload+16."""
    handle = process.words(0x8288D658, 1)[0]
    count = process.words(0x829A3E18, 1)[0]
    if handle and 0 < count <= 256:
        for index in range(count):
            record = process.words(0x82890598 + index * 16, 3)
            if record[0] == handle:
                payload = record[2]
                if 0x82800000 <= payload <= 0x828FFFA0 and not payload & 3:
                    return handle, payload + 16
                break
    return handle, 0


def sampled_guards(process, row, now):
    """Read-only mirror of playable guards, NOT proof that the hook PC ran.

    Reads are not atomic. Exact selections remain the native ComboDelayed log;
    rejected samples identify candidates, never an executed rejection branch.
    """
    def word(address):
        return process.words(address, 1)[0]

    def valid(address):
        return 0x40000000 <= address <= 0x41FFF000 and not address & 3

    failures = []
    if word(0x40CD65D8) != 2 or word(0x40CD65DC) != 0x40CD6340:
        failures.append('shared_actor')
    std, brain = word(0x40CD6344), word(0x40CD634C)
    if not valid(std) or not valid(brain) or word(std + 12) != 0x40CD65D8:
        failures.append('stdgame_or_brain')
    else:
        mind = word(brain)
        mem = word(mind + 12) if valid(mind) else 0
        model = word(mem) if valid(mem) else 0
        variables = word(model) if valid(model) else 0
        infos = word(variables + 4) if valid(variables) else 0
        if (not all(valid(p) for p in (mind, mem, model, variables, infos))
                or word(mem + 8) != 0x40CDD5BC or word(variables + 8) != 325):
            failures.append('designer_layout')
        elif [word(infos + i * 16) for i in (24, 25, 26, 29, 36)] != [136, 140, 144, 322, 188]:
            failures.append('designer_offsets')
    for accepted, reason in (
            (row['object_class'] == 0x8200FE2C, 'object_class'),
            (row['selector'] == 1, 'selector'), (row['pending'] == 1, 'pending'),
            (row['state'] == 2, 'native_open_state'),
            (2000 <= row['window'] <= 6000, 'window_range'),
            (((now-row['start']) & 0xFFFFFFFF) < row['window'], 'unexpired'),
            (row['window']-((now-row['start']) & 0xFFFFFFFF) <= 1000, 'hold_interval')):
        if not accepted:
            failures.append(reason)
    return dict(sampled_private_guard_failures=failures,
                native_update_enabled=row['update_disabled'] == 0,
                hook_pc_execution='sample only; see native ComboEligibility and ComboDelayed runtime logs')


def start(session, process_id, *, intro15=False):
    stop = threading.Event()

    def observe():
        # Only the launcher's own child PID; the current log supplies its base.
        # Never attach by executable name to another development/production run.
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.windll.kernel32
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        process = None
        last_score = None
        signature = None
        queue, captures, score_events = [], [], 0
        intro15_event = None
        last_capture = 0
        object_address = None
        try:
            with (session / 'hud_events.jsonl').open('w', encoding='utf-8') as out:
                while not stop.wait(.05):
                    if process is None:
                        log = session / 'runtime.log'
                        text = log.read_text(errors='replace') if log.exists() else ''
                        base = re.search(r'virtual base 0x0*([0-9A-Fa-f]+),', text)
                        if not base:
                            continue
                        process = Process(process_id, int(base[1], 16))
                    if not process.running():
                        break
                    try:
                        actor = Actor(process, 0x40CD65D8)
                        if not actor.alive() or actor.model != 'YAM_GenGratificator':
                            continue
                        d = actor.dsg()
                        memory = process.words(actor.mind[3], 3)
                        now = process.words(0x82C0628C, 1)[0]
                        handle, address = resolve_combo_object(process)
                        obj = process.words(address, 24) if address else [0] * 24
                        if intro15 and address and address != object_address:
                            from m17_frame_trace import write_watch, TIMER_WATCH
                            write_watch(session / 'intro15.trace', TIMER_WATCH + [
                                (0x82C06221, 32), (0x40CDD5BC, 325), (0x8288D528, 0x134),
                                (0x828A3E98, 0x5C), (address, 0x5C), (0x8288B4D4, 4),
                                (0x82837E9C, 8), (0x829A3E18, 4), (0x82890598, 0x1000)])
                            object_address = address
                        row = dict(level=process.cstr(0x82C06221, 32), score=i32(d[36]),
                                   bonus=f32(d[24]), window=i32(d[25]), start=i32(d[26]),
                                   pending=u8(d[29]), state=process.words(0x8288D618, 1)[0],
                                   update_disabled=process.words(0x8288B4D4, 1)[0],
                                   object_class=obj[0], selector=obj[22],
                                   combo_handle=handle, object_address=address,
                                   designer_buffer=memory[2],
                                   relevant_offsets=[d[i][1] for i in (24, 25, 26, 29, 36)],
                                   visible=list(process.words(0x82837E9C, 2)))
                        if intro15:
                            player = Actor(process, 0x40C52514)
                            if not player.alive() or player.model != 'YLT_RaymanModel':
                                continue
                            row.update(handless=u8(player.dsg()[13]), player_state=player.comport(),
                                       player_position=player.position(), **sampled_guards(process, row, now))
                            row['deadline'] = (row['start'] + row['window']) & 0xFFFFFFFF
                            row['remaining'] = row['window'] - ((now-row['start']) & 0xFFFFFFFF)
                            row['hud_position'] = f32((process.read(0x8288D53C, 4), 0))
                        current = json.dumps(row, sort_keys=True)
                        if current != signature:
                            out.write(json.dumps(dict(engine=now, **row)) + '\n')
                            out.flush()
                            signature = current
                        if (last_score is not None and row['score'] > last_score and score_events < 4
                                and (not intro15 or (score_events == 0 and row['level'] == 'intro_15'
                                                     and row['handless'] == 1))):
                            offsets = (.1, .65, .95, 1.2, 1.5, 1.8, 2.1, 2.5) if intro15 else (.1, .4)
                            queue.extend(time.monotonic() + delay for delay in offsets)
                            if intro15:
                                intro15_event = dict(engine=now, previous_score=last_score, **row)
                                (session / 'intro15_scoring_event.json').write_text(
                                    json.dumps(intro15_event, indent=2), encoding='utf-8')
                            score_events += 1
                        last_score = row['score']
                        wall = time.monotonic()
                        if queue and wall >= queue[0] and wall-last_capture >= .25 and len(captures) < 8:
                            queue.pop(0)
                            captures.append(dict(request=len(captures)+1, engine=now, **row,
                                hud_words=list(process.words(0x8288D000, 0x680//4))))
                            (session / 'frame.request').write_text(str(len(captures))+'\n', encoding='ascii')
                            last_capture = wall
                    except (OSError, TypeError, IndexError, struct.error):
                        continue
        except Exception as error:
            (session / 'diagnostic_error.txt').write_text(repr(error), encoding='utf-8')
        finally:
            (session / 'hud_capture_requests.json').write_text(json.dumps(captures, indent=2), encoding='utf-8')
            if intro15:
                (session / 'intro15_status.json').write_text(json.dumps(dict(
                    scoring_event_observed=intro15_event is not None, capture_requests=len(captures),
                    verdict='Needs timeline/render inspection' if intro15_event else 'INCOMPLETE: no handless intro_15 scoring event',
                    hook_rejections='see native ComboEligibility logs; sampled eligibility alone is not execution proof'), indent=2), encoding='utf-8')
            if process:
                kernel.CloseHandle(process.handle)

    observer = threading.Thread(target=observe, daemon=True)
    observer.start()
    return stop, observer
