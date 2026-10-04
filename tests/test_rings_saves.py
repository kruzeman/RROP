"""Persistent Rings snapshots: device continuation, slots, rotation and UI."""
import contextlib
import hashlib
import io
import os
from pathlib import Path
import subprocess
import unittest
from genesis_recompiler.build import sdl2_flags, BuildError
from genesis_recompiler.cli import main
from genesis_recompiler.decode import analyze
from genesis_recompiler.emit import emit
from support import CompiledTestCase, rom_with
from test_audio import SoundFixture

INIT = r'''
CPU *c=calloc(1,sizeof *c);assert(c);
c->rom=rom_data;c->rom_size=sizeof rom_data;c->pc=0x200;c->a[7]=0xffff00;c->sr=0x2700;
c->audio_mode=AUDIO_STUB;c->eeprom.enabled=1;c->z80_bus.requested=1;
c->vdp.frame_width=320;c->vdp.frame_height=224;
RingsSaves saves={0};assert(rings_saves_open(&saves,c,argv[1],1));
'''

class RingsSaveTests(CompiledTestCase):
    def check(self, body, features=False, sdl=False):
        prefix = '#define GENESIS_NO_MAIN\n#define GENESIS_RINGS_SAVES\n'
        if features: prefix += '#define GENESIS_RINGS_WIDE\n#define GENESIS_RINGS_MENU_FONT\n'
        if sdl:
            prefix += '#define GENESIS_SDL2\n#include <SDL.h>\nstatic Uint64 save_test_clock(void) {return 1000;}\n#define SDL_GetPerformanceCounter save_test_clock\n'
        source = prefix + emit(analyze(rom_with('5240 60fc'), [0x200]))
        source += '\n#include <assert.h>\nint main(int argc,char **argv) {assert(argc==2);\n' + INIT + body + '\nfree(c);return 0;}\n'
        if sdl:
            try: flags, libs = sdl2_flags()
            except BuildError as exc: self.skipTest(str(exc))
            path = self.root/'saves.c';path.write_text(source);binary = self.root/'saves'
            result = subprocess.run(['cc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function', *flags, str(path), '-o', str(binary), *libs], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        else: binary = self.compile(source)
        env = dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_RENDER_DRIVER='software', SDL_AUDIODRIVER='dummy')
        result = subprocess.run([str(binary), str(self.root/'slots')], env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def test_roundtrip_includes_devices_pending_transfers_and_machine_clocks(self):
        self.check(r'''
for(unsigned i=0;i<65536;++i) {c->ram[i]=(uint8_t)i;c->vdp.vram[i]=(uint8_t)(i>>8);}
for(unsigned i=0;i<8;++i) {c->d[i]=0x12345600+i;c->a[i]=0xff1000+i*4;}
c->usp=0xff8888;c->ssp=0xff7777;c->cycles=123;c->master_cycles=861;c->steps=40;
c->vdp.command_pending=1;c->vdp.fill_pending=1;c->vdp.bus_value=0x9335;
c->vdp.irq_h=1;c->vdp.irq_v=1;c->vdp.hint_counter=7;c->vdp.line=37;c->vdp.line_clock=22;
c->vdp.cram[22]=0xeee;c->vdp.vsram[17]=0x340;c->vdp.registers[3]=0x48;
c->z80_bus.bank=333;c->z80_bus.ram[800]=0x98;c->z80_cpu.iff1=1;c->z80_cpu.im=2;c->z80_cpu.ei_delay=1;c->z80_cpu.debt=-7;
c->psg.tone[1]=444;c->psg.noise_lfsr=0x8543;c->psg.next_tick=1600;c->psg.area=-5555;
c->eeprom.phase=EE_WRITE;c->eeprom.bits=5;c->eeprom.address=126;c->eeprom.pending[3]=0x77;c->eeprom.data[60]=0xf8;
c->ym2612_stub.address[1]=0x40;c->ym2612_stub.registers[1][0x40]=0x99;
memset(c->vdp.frame,0x63,sizeof c->vdp.frame);c->io_control[1]=0x40;c->pad_buttons[2]=0x23;
SaveCodec before={0};assert(save_encode(c,&before));
c->d[1]=0;c->ram[123]=0;c->vdp.vram[12345]=0;c->psg.area=0;c->fault=1;c->reason="old fault";
assert(save_decode(c,before.data,before.size));assert(!c->fault && !c->reason);
SaveCodec after={0};assert(save_encode(c,&after));assert(before.size==after.size && !memcmp(before.data,after.data,before.size));
assert(c->z80_cpu.debt==-7 && c->eeprom.pending[3]==0x77 && c->psg.area==-5555);
free(before.data);free(after.data);
''')

    def test_continue_execution_after_restore_matches_uninterrupted_cpu(self):
        self.check(r'''
for(unsigned i=0;i<400;++i)machine_step(c);
assert(rings_save_write(&saves,c,0));
for(unsigned i=0;i<500;++i)machine_step(c);
SaveCodec expected={0};assert(save_encode(c,&expected));
assert(rings_save_load(&saves,c,0));
for(unsigned i=0;i<500;++i)machine_step(c);
SaveCodec actual={0};assert(save_encode(c,&actual));
assert(actual.size==expected.size && !memcmp(actual.data,expected.data,actual.size));
free(expected.data);free(actual.data);
''')

    def test_five_manual_slots_and_rotating_autosaves_survive_restart(self):
        self.check(r'''
for(int i=0;i<5;++i) {c->d[3]=(unsigned)i+40;assert(rings_save_write(&saves,c,i));}
saves.started=1;c->d[3]=100;rings_save_tick(&saves,c,0,1);
for(int i=1;i<=7;++i) {c->d[3]=(unsigned)i;rings_save_tick(&saves,c,(uint64_t)i*300000,1);}
RingsSaves reopened={0};assert(rings_saves_open(&reopened,c,argv[1],1));assert(reopened.serial==12);
for(int i=0;i<10;++i)assert(reopened.slots[i].compatible);
for(int i=0;i<5;++i) {assert(rings_save_load(&reopened,c,i));assert(c->d[3]==(unsigned)i+40);}
assert(rings_save_load(&reopened,c,5));assert(c->d[3]==6);
assert(rings_save_load(&reopened,c,6));assert(c->d[3]==7);
assert(rings_save_load(&reopened,c,7));assert(c->d[3]==3);
reopened.started=1;rings_save_tick(&reopened,c,0,1);c->d[3]=8;rings_save_tick(&reopened,c,300000,1);
assert(rings_save_load(&reopened,c,7));assert(c->d[3]==8);
''')

    def test_timer_excludes_pause_title_and_resets_after_loading(self):
        self.check(r'''
rings_save_tick(&saves,c,0,1);rings_save_tick(&saves,c,900000,1);assert(!saves.serial);
saves.started=1;rings_save_tick(&saves,c,1000000,1);rings_save_tick(&saves,c,1299999,1);assert(!saves.serial);
rings_save_tick(&saves,c,1300000,1);assert(saves.serial==1);
rings_save_tick(&saves,c,1300001,0);rings_save_tick(&saves,c,1900001,0);
rings_save_tick(&saves,c,1900002,1);assert(saves.serial==1 && !saves.elapsed_ms);
rings_save_tick(&saves,c,2100002,1);assert(saves.elapsed_ms==200000);
assert(rings_save_load(&saves,c,5));rings_save_tick(&saves,c,2200002,1);assert(!saves.elapsed_ms);
rings_save_tick(&saves,c,2500001,1);assert(saves.serial==1);
rings_save_tick(&saves,c,2500002,1);assert(saves.serial==2);
saves.autosave=0;rings_save_tick(&saves,c,3500002,1);assert(saves.serial==2);
''')

    def test_corrupt_truncated_wrong_rom_audio_invalid_state_do_not_mutate_cpu(self):
        self.check(r'''
assert(rings_save_write(&saves,c,0));char path[1100];assert(rings_save_path(&saves,0,path,sizeof path));
FILE *f=fopen(path,"rb");assert(f);assert(!fseek(f,0,SEEK_END));long n=ftell(f);rewind(f);
uint8_t *bytes=malloc((size_t)n);assert(bytes && fread(bytes,1,(size_t)n,f)==(size_t)n);fclose(f);
CPU *expected=malloc(sizeof *expected);assert(expected);
c->d[2]=0x42434445;c->ram[7000]=0x99;memcpy(expected,c,sizeof *c);
for(int variant=0;variant<7;++variant) {
 uint8_t *bad=malloc((size_t)n);assert(bad);memcpy(bad,bytes,(size_t)n);size_t count=(size_t)n;
 if(variant==0)bad[n-40]^=0x80;
 if(variant==1)count-=1;
 if(variant==2) {bad[24]^=1;save_put(bad+60,save_crc(bad,60),4);}
 if(variant==3) {save_put(bad+52,AUDIO_ON,4);save_put(bad+60,save_crc(bad,60),4);}
 if(variant==4) {save_put(bad+12,SAVE_MAX_BYTES+1,4);save_put(bad+60,save_crc(bad,60),4);}
 if(variant==5)bad[40]^=0x80;
 if(variant==6) {save_put(bad+64+8+64,0x201,4);save_put(bad+16,save_crc(bad+64,(size_t)n-64),4);save_put(bad+60,save_crc(bad,60),4);}
 f=fopen(path,"wb");assert(f && fwrite(bad,1,count,f)==count);fclose(f);free(bad);
 assert(!rings_save_load(&saves,c,0));assert(!memcmp(expected,c,sizeof *c));
}
free(expected);free(bytes);
''')

    def test_failed_atomic_write_preserves_old_slot_and_does_not_fault(self):
        self.check(r'''
c->d[7]=11;assert(rings_save_write(&saves,c,0));char path[1100],temp[1200];assert(rings_save_path(&saves,0,path,sizeof path));
snprintf(temp,sizeof temp,"%s.tmp.%ld.%u",path,(long)getpid(),saves.temp_counter+1);
FILE *f=fopen(temp,"wb");assert(f);fclose(f);c->d[7]=22;
assert(!rings_save_write(&saves,c,0));assert(!c->fault && saves.serial==1);
assert(rings_save_load(&saves,c,0));assert(c->d[7]==11);unlink(temp);
''')

    def test_text_zoom_world_buffers_restore_but_host_settings_and_pointers_survive(self):
        self.check(r'''
RingsWide *wide=calloc(1,sizeof *wide);assert(wide);c->wide=wide;wide->shadow=(void*)c;
c->vdp.font_enabled=1;c->vdp.font_supported[65]=1;c->vdp.font_count=1;c->vdp.font_visible=1;
c->vdp.font_marks[123].ch='A';c->vdp.font_cells[0].ch='A';c->vdp.font_frame[20]=91;
c->vdp.wide_enabled=1;c->vdp.zoom_enabled=1;c->vdp.wide_font_frame[17]=87;c->vdp.zoom_scene[54321]=7;
wide->zoom_scene[321]=4;wide->lift_scene[321]=25;wide->pending=1;wide->work_focus_x=455;
SaveCodec state={0};assert(save_encode(c,&state));
c->vdp.font_enabled=0;c->vdp.font_supported[65]=0;c->vdp.wide_enabled=0;
c->vdp.font_marks[123].ch=0;wide->zoom_scene[321]=0;c->vdp.wide_font_frame[17]=0;
assert(save_decode(c,state.data,state.size));
assert(c->wide==wide && wide->shadow==(void*)c && wide->zoom_scene[321]==4 && wide->lift_scene[321]==25 && wide->pending && wide->work_focus_x==455);
assert(c->vdp.font_marks[123].ch=='A' && c->vdp.font_frame[20]==91 && c->vdp.wide_font_frame[17]==87 && c->vdp.zoom_scene[54321]==7);
assert(!c->vdp.font_enabled && !c->vdp.font_supported[65] && !c->vdp.wide_enabled && c->vdp.zoom_enabled);
free(state.data);free(wide);
''', features=True)

    def test_native_save_load_continue_hooks_preserve_stack_and_cancel_path(self):
        self.check(r'''
c->pc=0xd2be;assert(!rings_save_observe(&saves,c,1) && saves.started);
c->pc=0x20670;assert(!rings_save_observe(&saves,c,0) && c->pc==0x20670);
c->ram[0x1a]=4;c->pad_buttons[0]=PAD_B;uint32_t sp=c->a[7];
assert(rings_save_observe(&saves,c,1) && saves.menu==1 && c->pc==0x2068a && c->a[7]==sp);
assert(!c->pad_buttons[0] && !c->ram[0x1a]);saves.menu=0;
c->pc=0x20652;assert(rings_save_observe(&saves,c,1) && saves.menu==2 && c->pc==0x2066c && c->a[7]==sp);saves.menu=0;
c->pc=0x1b8ee;assert(rings_save_observe(&saves,c,1) && saves.menu==2 && c->pc==0x1b914 && c->a[7]==sp);
saves.menu=0;c->pc=0x15538;assert(!rings_save_observe(&saves,c,1) && !saves.started);
''')

    def test_sdl_slot_picker_consumes_keys_cancels_and_loads_from_fault(self):
        self.check(r'''
SDLHost host={0};host.saves=&saves;host.no_throttle=1;assert(sdl_host_open(&host));
c->vdp.rendered_frames=1;saves.started=1;uint64_t steps=c->steps;
SDL_Event event={0};event.type=SDL_KEYDOWN;event.key.keysym.sym=SDLK_F5;assert(SDL_PushEvent(&event)==1);
assert(sdl_host_service(&host,c));assert(saves.menu==1 && !c->pad_buttons[0]);
event.key.keysym.sym=SDLK_DOWN;SDL_PushEvent(&event);event.key.keysym.sym=SDLK_RETURN;SDL_PushEvent(&event);
c->d[5]=77;assert(sdl_host_service(&host,c));assert(!saves.menu && saves.slots[1].compatible && c->steps==steps && !c->pad_buttons[0]);
c->d[5]=88;c->fault=1;c->reason="test fault";host.stopped=1;
event.key.keysym.sym=SDLK_F9;SDL_PushEvent(&event);assert(sdl_host_service(&host,c));assert(saves.menu==2 && saves.selected==1);
event.key.keysym.sym=SDLK_RETURN;SDL_PushEvent(&event);assert(sdl_host_service(&host,c));
assert(!saves.menu && !c->fault && !host.stopped && c->d[5]==77 && !c->pad_buttons[0]);assert(host.origin_master==c->master_cycles);
event.key.keysym.sym=SDLK_F9;SDL_PushEvent(&event);event.key.keysym.sym=SDLK_ESCAPE;SDL_PushEvent(&event);
assert(sdl_host_service(&host,c) && !saves.menu);assert(!c->steps);
/* Combat sets native mode 2; it remains part of the active save session. */
c->ram[0xae]=0;c->ram[0xaf]=2;saves.clock_ready=1;saves.clock_active=1;
/* Seed a due interval instead of subtracting from a young host clock. */
saves.last_ms=rings_save_now(&host);saves.elapsed_ms=RINGS_SAVE_INTERVAL_MS;
assert(sdl_host_service(&host,c));assert(saves.slots[5].compatible);
sdl_host_close(&host);
''', sdl=True)

    def test_cli_slots_and_limit_relative_to_restored_progress(self):
        binary = self.compile('#define GENESIS_RINGS_SAVES\n' + emit(analyze(rom_with('5240 60fc'), [0x200])))
        args = [str(binary), '--audio', 'stub', '--save-dir', str(self.root/'slots')]
        before = subprocess.run([*args, '--limit', '500', '--save-slot', 'manual-3'], capture_output=True, text=True)
        self.assertEqual(before.returncode, 2, before.stderr)
        loaded = subprocess.run([*args, '--load-slot', 'manual-3', '--limit', '0'], capture_output=True, text=True)
        self.assertEqual(loaded.returncode, 2, loaded.stderr);self.assertEqual(loaded.stdout, before.stdout)
        resumed = subprocess.run([*args, '--load-slot', 'manual-3', '--limit', '100'], capture_output=True, text=True)
        uninterrupted = subprocess.run([*args, '--limit', '600'], capture_output=True, text=True)
        self.assertEqual(resumed.stdout, uninterrupted.stdout)
        for slot in ('manual-0', 'manual-6', 'auto-6', '1', ''):
            bad = subprocess.run([*args, '--load-slot', slot], capture_output=True, text=True)
            self.assertEqual(bad.returncode, 64)

    def test_build_requires_verified_rom_and_build_flag(self):
        rom = self.root/'test.gen';rom.write_bytes(rom_with('60fe'))
        with contextlib.redirect_stderr(io.StringIO()) as error:
            with self.assertRaises(SystemExit):main([str(rom), '--rings-saves', '-o', str(self.root/'game')])
            self.assertEqual(main([str(rom), '--build', '--rings-saves', '-o', str(self.root/'game')]), 1)
        self.assertIn('verified', error.getvalue())

    @unittest.skipUnless((Path(__file__).resolve().parents[1]/'build/rings-of-power/Rings of Power (UE) [!].gen').exists(), 'user ROM absent')
    def test_menu_hook_addresses_match_verified_original_rom(self):
        from examples.build_rings_of_power import ROM_SHA256
        rom = (Path(__file__).resolve().parents[1]/'build/rings-of-power/Rings of Power (UE) [!].gen').read_bytes()
        self.assertEqual(hashlib.sha256(rom).hexdigest(), ROM_SHA256)
        for address, data in ((0x20670,'4eb90002f11a'),(0x20652,'4eb90002f896'),(0x1b8ee,'4eb90002f896'),(0x2068a,'600000cc'),(0x2066c,'600000ea'),(0x1b914,'4e5e4e75')):
            self.assertEqual(rom[address:address+len(bytes.fromhex(data))], bytes.fromhex(data))

class RingsSaveSoundTests(SoundFixture):
    def test_restored_fm_psg_pcm_and_timers_match_uninterrupted_sound(self):
        source = '#define GENESIS_NO_MAIN\n#define GENESIS_RINGS_SAVES\n' + emit(analyze(rom_with('60fe'), [0x200]))
        source += r'''
#include <assert.h>
static void fm(CPU *c,uint8_t reg,uint8_t value) {audio_fm_write(c,0,reg);audio_fm_write(c,1,value);}
int main(void) {
CPU *c=calloc(1,sizeof *c);assert(c);c->rom=rom_data;c->rom_size=sizeof rom_data;c->pc=0x200;c->sr=0x2700;
c->audio_mode=AUDIO_ON;c->z80_bus.requested=1;assert(audio_init(c,NULL));c->audio.playback=1;
for(unsigned op=0;op<4;++op) {fm(c,(uint8_t)(0x30+op*4),1);fm(c,(uint8_t)(0x40+op*4),0);fm(c,(uint8_t)(0x50+op*4),31);fm(c,(uint8_t)(0x80+op*4),15);}
fm(c,0xb0,7);fm(c,0xb4,0xc0);fm(c,0xa4,0x22);fm(c,0xa0,0x69);fm(c,0x28,0xf0);
fm(c,0x24,0xfd);fm(c,0x25,3);fm(c,0x27,5);psg_write(c,0x84);psg_write(c,8);psg_write(c,0x92);psg_write(c,0xe4);psg_write(c,0xf4);
for(unsigned i=0;i<1000;++i)machine_advance(c,173);
int16_t scratch[8192];audio_pop(c,scratch,AUDIO_RING_FRAMES);
SaveCodec snapshot={0};assert(save_encode(c,&snapshot));
for(unsigned i=0;i<300;++i)machine_advance(c,173);
int16_t expected[8192],actual[8192];unsigned count=audio_pop(c,expected,4096);assert(count>100);
uint8_t status=audio_fm_read(c,0);assert(save_decode(c,snapshot.data,snapshot.size));
for(unsigned i=0;i<300;++i)machine_advance(c,173);
assert(audio_pop(c,actual,4096)==count && !memcmp(actual,expected,count*4));assert(audio_fm_read(c,0)==status);
size_t size=genesis_ymfm_state_size(c->audio.fm);uint8_t *state=malloc(size);assert(state && genesis_ymfm_save_state(c->audio.fm,state,size));
assert(!genesis_ymfm_load_state(state,size-1));save_put(state+8,0,8);assert(!genesis_ymfm_load_state(state,size));
free(state);free(snapshot.data);assert(audio_finish(c));free(c);return 0;
}
'''
        binary = self.compile_sound(source)
        result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
