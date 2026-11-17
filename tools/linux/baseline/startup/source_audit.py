"""Read pinned startup sources, report metadata/order only; never patch or compile SDK."""
from pathlib import Path
import subprocess
import supplements as S
C=S.C
ROOT=Path(__file__).resolve().parents[4]


def audit():
    texts={}
    for name,row in S.LOCK['source_facts'].items():
        sub=name.startswith('thirdparty/sdl3/')
        repo=ROOT/'external/rexglue-sdk'/('thirdparty/sdl3' if sub else '')
        path=name.removeprefix('thirdparty/sdl3/') if sub else name
        b=subprocess.check_output(['git','-C',str(repo),'show',row['commit']+':'+path])
        C.need(C.digest(b)==row['sha256'],'pinned startup source hash: '+name);texts[name]=b.decode()
    main=texts['src/ui/windowed_app_main_sdl.cpp']
    C.need(main.index('rex::cvar::Init(')<main.index('app_context.Initialize()')<main.index('GetWindowedAppCreator()'),'entry ordering changed')
    cvar=texts['src/core/cvar.cpp'];C.need('catch (const CLI::ParseError& e)' in cvar,'help handling changed')
    sdl=texts['thirdparty/sdl3/src/SDL.c'];C.need(sdl.index('SDL_DBus_Init();')<sdl.index('SDL_VideoInit(NULL)'),'SDL DBus/video ordering changed')
    video=texts['thirdparty/sdl3/src/video/SDL_video.c'];body=video[video.index('bool SDL_VideoInit('):]
    C.need(body.index('SDL_InitSubSystem(SDL_INIT_EVENTS)')<body.index('driver_name = SDL_GetHint('),'pre-driver work changed')
    rex=texts['src/ui/rex_app.cpp'];body=rex[rex.index('bool ReXApp::OnInitialize()'):]
    C.need(body.index('SetupPresentation()')<body.index('ConstructRuntime('),'presentation/data ordering changed')
    construct=rex[rex.index('bool ReXApp::ConstructRuntime('):]
    C.need(construct.index('is_directory(paths.game_data_root)')<construct.index('make_unique<rex::Runtime>'),'missing-directory stop moved')
    return {'pinned_source_hashes':'PASS','unattended_startup':'NOT ESTABLISHED',
            'why':'SDL DBus/events precede backend selection; presentation/window precede data checks',
            'help_early_exit':'NOT GUARANTEED','safe_data_free_manual_stop':'nonexistent game_data_root before Runtime construction',
            'minimum_entry_observation':'exact deliberate SDL backend rejection, natural exit1'}


if __name__=='__main__':
    import json
    print(json.dumps(audit(),indent=2))
