"""Button assignment through SDL events, physical polling and persisted settings."""
import os
import subprocess
import unittest

from genesis_recompiler.build import BuildError, sdl2_flags
from genesis_recompiler.decode import analyze
from genesis_recompiler.emit import emit
from support import CompiledTestCase, rom_with


class GamepadRemapTests(CompiledTestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.flags,cls.libs=sdl2_flags()
        except BuildError as exc:
            raise unittest.SkipTest(str(exc))

    def check(self, body):
        source='#define GENESIS_NO_MAIN\n#define GENESIS_RINGS_SAVES\n'+emit(analyze(rom_with('4e72 2700'),[0x200]))
        source+=r'''
#include <assert.h>
static void key(SDLHost *h,CPU *c,SDL_Keycode key) {
 SDL_Event e={0};e.type=SDL_KEYDOWN;e.key.keysym.sym=key;assert(SDL_PushEvent(&e)==1);
 assert(sdl_host_service(h,c));
}
static void button(SDLHost *h,CPU *c,SDL_Joystick *j,unsigned b,int down) {
 assert(!SDL_JoystickSetVirtualButton(j,(int)b,(Uint8)down));SDL_PumpEvents();
 assert(sdl_host_service(h,c));
}
static void begin(SDLHost *h,CPU *c) {
 rings_settings_open(h,c);h->settings.controls=1;h->settings.control_selected=2;
 key(h,c,SDLK_RETURN);assert(h->settings.remap==1 && !c->pad_buttons[0]);
}
int main(void) {
 CPU *c=calloc(1,sizeof *c);assert(c);c->rom=rom_data;c->rom_size=sizeof rom_data;
 SDLHost h={0};h.no_throttle=1;assert(sdl_host_open(&h));
 int device=SDL_JoystickAttachVirtual(SDL_JOYSTICK_TYPE_GAMECONTROLLER,SDL_CONTROLLER_AXIS_MAX,SDL_CONTROLLER_BUTTON_MAX,0);
 assert(device>=0);SDL_Joystick *j=SDL_JoystickOpen(device);assert(j);
 sdl_pad_connect(&h.input);assert(h.input.controller && h.input.instance==SDL_JoystickInstanceID(j));
 RingsSaves saves={0};saves.enabled=1;snprintf(saves.directory,sizeof saves.directory,".");h.saves=&saves;
 rings_settings_init(&h,c,0,0,0,0);assert(sdl_host_service(&h,c));
''' + body + r'''
 SDL_JoystickClose(j);assert(!SDL_JoystickDetachVirtual(device));sdl_host_close(&h);free(c);return 0;
}
'''
        path=self.root/'remap.c';path.write_text(source);binary=self.root/'remap'
        result=subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-Wno-unused-function',
                               '-DGENESIS_SDL2',*self.flags,str(path),'-o',str(binary),*self.libs],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        result=subprocess.run([str(binary)],cwd=self.root,env=dict(os.environ,SDL_VIDEODRIVER='dummy',SDL_RENDER_DRIVER='software'),
                              capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_complete_wizard_persists_maps_buttons_and_blocks_confirmation_leak(self):
        self.check(r'''
begin(&h,c);unsigned mapping[4]={SDL_CONTROLLER_BUTTON_Y,SDL_CONTROLLER_BUTTON_B,SDL_CONTROLLER_BUTTON_A,SDL_CONTROLLER_BUTTON_X};
for(unsigned i=0;i<4;++i) {
 button(&h,c,j,mapping[i],1);assert(!c->pad_buttons[0]);
 if(i<3)assert(h.settings.remap==(int)i+2 && !h.input.custom);
 else assert(!h.settings.remap && h.input.custom);
 button(&h,c,j,mapping[i],0);
}
for(unsigned i=0;i<4;++i)assert(sdl_pad_binding(&h.input,i)==mapping[i]);
rings_settings_close(&h,c);
for(unsigned i=0;i<4;++i) {
 button(&h,c,j,mapping[i],1);assert(c->pad_buttons[0]==(PAD_A<<i));
 button(&h,c,j,mapping[i],0);assert(!c->pad_buttons[0]);
}
h.input.custom=0;rings_settings_init(&h,c,0,0,0,0);assert(h.input.custom);
for(unsigned i=0;i<4;++i)assert(sdl_pad_binding(&h.input,i)==mapping[i]);
SaveCodec snapshot={0};c->pc=0x200;c->a[7]=0xffff00;c->sr=0x2700;
assert(save_encode(c,&snapshot));assert(save_decode(c,snapshot.data,snapshot.pos));free(snapshot.data);
rings_save_host_loaded(&h,c);assert(h.input.custom);
for(unsigned i=0;i<4;++i)assert(sdl_pad_binding(&h.input,i)==mapping[i]);
/* Final wizard press stays held: closing settings must not press Start. */
begin(&h,c);
for(unsigned i=0;i<4;++i) {
 button(&h,c,j,mapping[i],1);if(i<3)button(&h,c,j,mapping[i],0);
}
rings_settings_close(&h,c);assert(sdl_host_service(&h,c));assert(!c->pad_buttons[0]);
button(&h,c,j,mapping[3],0);button(&h,c,j,mapping[3],1);assert(c->pad_buttons[0]==PAD_START);
button(&h,c,j,mapping[3],0);
''')

    def test_held_buttons_duplicates_reserved_buttons_and_cancel_preserve_mapping(self):
        self.check(r'''
/* Enter the wizard with a held confirm button; release it first. */
rings_settings_open(&h,c);h.settings.controls=1;h.settings.control_selected=2;
button(&h,c,j,SDL_CONTROLLER_BUTTON_A,1);assert(h.settings.remap==1 && h.settings.remap_held);
button(&h,c,j,SDL_CONTROLLER_BUTTON_Y,1);assert(h.settings.remap==1);
button(&h,c,j,SDL_CONTROLLER_BUTTON_A,0);button(&h,c,j,SDL_CONTROLLER_BUTTON_Y,0);
button(&h,c,j,SDL_CONTROLLER_BUTTON_Y,1);assert(h.settings.remap==2);
button(&h,c,j,SDL_CONTROLLER_BUTTON_Y,0);button(&h,c,j,SDL_CONTROLLER_BUTTON_Y,1);
assert(h.settings.remap==2 && strstr(h.settings.message,"Already assigned"));
button(&h,c,j,SDL_CONTROLLER_BUTTON_Y,0);button(&h,c,j,SDL_CONTROLLER_BUTTON_LEFTSHOULDER,1);
assert(h.settings.remap==2 && !saves.menu && strstr(h.settings.message,"reserved"));
button(&h,c,j,SDL_CONTROLLER_BUTTON_LEFTSHOULDER,0);
key(&h,c,SDLK_ESCAPE);assert(!h.settings.remap && h.settings.controls && !h.input.custom);
FILE *f=fopen("settings.cfg","rb");assert(!f);
begin(&h,c);button(&h,c,j,SDL_CONTROLLER_BUTTON_B,1);assert(h.settings.remap==2); /* B is assignable, not Escape. */
button(&h,c,j,SDL_CONTROLLER_BUTTON_B,0);button(&h,c,j,SDL_CONTROLLER_BUTTON_BACK,1);
assert(!h.settings.remap && h.settings.controls && !h.input.custom);
button(&h,c,j,SDL_CONTROLLER_BUTTON_BACK,0);
''')

    def test_disconnect_focus_and_wrong_controller_do_not_commit_partial_mapping(self):
        self.check(r'''
begin(&h,c);SDL_Event e={0};e.type=SDL_CONTROLLERBUTTONDOWN;e.cbutton.button=SDL_CONTROLLER_BUTTON_Y;
e.cbutton.which=h.input.instance+100;assert(SDL_PushEvent(&e)==1);assert(sdl_host_service(&h,c));assert(h.settings.remap==1);
button(&h,c,j,SDL_CONTROLLER_BUTTON_Y,1);button(&h,c,j,SDL_CONTROLLER_BUTTON_Y,0);
e.type=SDL_WINDOWEVENT;e.window.event=SDL_WINDOWEVENT_FOCUS_LOST;assert(SDL_PushEvent(&e)==1);
assert(sdl_host_service(&h,c));assert(!h.settings.remap && !h.input.custom && !c->pad_buttons[0]);
e.window.event=SDL_WINDOWEVENT_FOCUS_GAINED;assert(SDL_PushEvent(&e)==1);assert(sdl_host_service(&h,c));
begin(&h,c);e.type=SDL_CONTROLLERDEVICEREMOVED;e.cdevice.which=h.input.instance;
assert(SDL_PushEvent(&e)==1);assert(sdl_host_service(&h,c));assert(!h.settings.remap && !h.input.custom);
''')

    def test_old_invalid_partial_settings_and_reset_use_safe_presets(self):
        self.check(r'''
const char *cfg[]={
 "GenesisRecomp Settings 1\ngamepad=1\npad_layout=1\n",
 "GenesisRecomp Settings 1\npad_layout=1\npad_custom=1\npad_a=3\npad_b=1\npad_c=0\n",
 "GenesisRecomp Settings 1\npad_layout=1\npad_custom=1\npad_a=3\npad_b=3\npad_c=0\npad_start=2\n",
 "GenesisRecomp Settings 1\npad_layout=1\npad_custom=1\npad_a=999\npad_b=1\npad_c=0\npad_start=2\n",
 "GenesisRecomp Settings 1\npad_layout=1\npad_custom=1\npad_a=9\npad_b=1\npad_c=0\npad_start=2\n"};
for(unsigned i=0;i<sizeof cfg/sizeof *cfg;++i) {
 FILE *f=fopen("settings.cfg","wb");assert(f);fputs(cfg[i],f);fclose(f);
 h.input.custom=1;rings_settings_init(&h,c,0,0,0,0);
 assert(!h.input.custom && h.input.layout==1 && sdl_pad_binding(&h.input,0)==SDL_CONTROLLER_BUTTON_A);
}
begin(&h,c);unsigned map[4]={3,1,0,2};
for(unsigned i=0;i<4;++i){button(&h,c,j,map[i],1);button(&h,c,j,map[i],0);}
assert(h.input.custom);h.settings.control_selected=3;key(&h,c,SDLK_RETURN);
assert(!h.input.custom && !h.input.layout && sdl_pad_binding(&h.input,0)==SDL_CONTROLLER_BUTTON_X);
h.input.custom=1;rings_settings_init(&h,c,0,0,0,0);assert(!h.input.custom && !h.input.layout);
/* Remapping remains available while gameplay input is switched off. */
h.input.enabled=0;begin(&h,c);
for(unsigned i=0;i<4;++i){button(&h,c,j,map[i],1);button(&h,c,j,map[i],0);}
assert(h.input.custom && !h.input.enabled);
''')
