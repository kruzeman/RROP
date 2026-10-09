"""Opt-in world pacing, transactional movement and host intent ownership."""
import subprocess
from genesis_recompiler.decode import analyze
from genesis_recompiler.emit import emit
from support import CompiledTestCase, rom_with
import test_sdl as sdl_tests

class RingsMotionTests(CompiledTestCase):
    @classmethod
    def setUpClass(cls):sdl_tests.SDLTests.setUpClass.__func__(cls)
    compile_sdl=sdl_tests.SDLTests.compile_sdl
    run_sdl=sdl_tests.SDLTests.run_sdl
    def check(self,body,helper='5279 00ff0e8e 5279 00ff02c0 4e75'):
        rom=bytearray(0x25000);rom[:0x400]=rom_with('4e72 2700')
        for at,code in [(0xd2be,'4e71'),(0x1b918,'4e75'),(0x1b950,'4e71 4ef9 0001b9ee'),
                        (0x1b9ee,'4e75'),(0x24984,helper)]:
            data=bytes.fromhex(code);rom[at:at+len(data)]=data
        p=analyze(bytes(rom),[0x200,0x1b918,0x1b950,0x24984])
        self.assertFalse(p.errors)
        source='#define GENESIS_NO_MAIN\n#define GENESIS_RINGS_WIDE\n#define GENESIS_RINGS_SAVES\n'+emit(p)
        source+='\n#include <assert.h>\n'+r'''
int main(void) {
 CPU *c=calloc(1,sizeof *c);RingsWide *w=calloc(1,sizeof *w);assert(c && w);
 c->rom=rom_data;c->rom_size=sizeof rom_data;c->a[7]=0xfff000;c->sr=0x2000;
 assert(rings_wide_open(c,w));c->vdp.zoom_enabled=c->vdp.zoom_world_visible=1;
 c->ram[0xa7fc]=0;c->ram[0xa7fd]=0xff;c->ram[0xa7fe]=0xd0;
 c->ram[0xd001]=c->ram[0xd003]=255;c->ram[0xd00d]=1;c->ram[0x2b5]=1;
 SDLHost h={0};h.input.focused=1;h.settings.ready=h.settings.enhanced=1;
 RingsMotion *m=&w->motion;m->enabled=m->active=m->verified=1;m->intent=&h.pad_intent;
 m->period=20000;m->due=100000;c->pc=0xd2be;c->master_cycles=1000;
'''+body+r'''
 rings_wide_close(c);free(w);free(c);return 0;
}
'''
        r=self.run_sdl(self.compile_sdl(source));self.assertEqual(r.returncode,0,r.stderr)

    def test_short_tap_resolves_once_without_waiting_for_world_or_changing_cpu_context(self):
        self.check(r'''
rings_pad_sample(&h,c,PAD_RIGHT);rings_pad_sample(&h,c,0);assert(h.pad_intent.pending);
uint32_t regs[16];memcpy(regs,c->d,32);memcpy(regs+8,c->a,32);
assert(rings_motion_before(c));assert(c->ram[0xe8f]==1 && m->moves==1);
assert(!h.pad_intent.pending && !c->ram[0xe17]);assert(c->pc==0xd2be);
assert(!memcmp(regs,c->d,32) && !memcmp(regs+8,c->a,32));assert(c->sr==0x2000);
assert(c->master_cycles==1000+256*7 && m->player_budget==56*7);
assert(rings_motion_before(c));assert(m->moves==1 && c->ram[0xe8f]==1);
''')

    def test_held_direction_respects_cooldown_and_release_cannot_repeat_fifo_direction(self):
        self.check(r'''
c->pad_buttons[0]=PAD_RIGHT;assert(rings_motion_before(c));assert(m->moves==1);
for(unsigned i=0;i<5;++i) {assert(rings_motion_before(c));}
assert(m->moves==1);
c->master_cycles=m->next_step;assert(rings_motion_before(c));assert(m->moves==2);
c->pad_buttons[0]=0;c->master_cycles=m->next_step;assert(rings_motion_before(c));assert(m->moves==2);
c->pc=0x12ff8;c->d[0]=PAD_RIGHT;rings_pad_observe(&h,c);assert(!c->d[0]);
c->pad_buttons[0]=PAD_UP|PAD_RIGHT;c->d[0]=0;rings_pad_observe(&h,c);assert(c->d[0]==(PAD_UP|PAD_RIGHT));
''')

    def test_event_side_effect_rolls_back_and_retains_the_tap_for_native_dispatch(self):
        self.check(r'''
uint8_t before[65536];memcpy(before,c->ram,sizeof before);
rings_pad_sample(&h,c,PAD_RIGHT);rings_pad_sample(&h,c,0);assert(rings_motion_before(c));
assert(!memcmp(before,c->ram,sizeof before));assert(!m->moves && m->rejected==1 && m->fallback==PAD_RIGHT);
c->pc=0x12ff8;c->d[0]=0;rings_pad_observe(&h,c);assert(c->d[0]==PAD_RIGHT);
assert(!m->fallback && !h.pad_intent.pending);
''',helper='5279 00ff0110 5279 00ff0e8e 4e75')

    def test_other_actor_changes_roll_back(self):
        self.check(r'''
uint8_t before[65536];memcpy(before,c->ram,sizeof before);
assert(!rings_motion_player(c,1));assert(!memcmp(before,c->ram,sizeof before));assert(!m->moves);
''',helper='5279 00ff02e8 5279 00ff0e8e 4e75')

    def test_reference_bitmap_timing_is_disposable_and_world_deadline_includes_all_work(self):
        self.check(r'''
c->pc=0x1b950;uint8_t before[65536];memcpy(before,c->ram,sizeof before);
uint64_t clock=c->master_cycles;assert(rings_motion_draw_time(c)==16*7);
assert(c->master_cycles==clock && c->pc==0x1b950 && !memcmp(before,c->ram,sizeof before));
c->pc=0xd2be;m->turn=500;m->draw_budget=30000;m->player_budget=2000;m->finish=1;
assert(rings_motion_before(c));assert(m->period==32500 && m->due==33000 && !m->player_budget && !m->finish);
''')

    def test_classic_scene_actions_and_loaded_state_do_not_carry_a_stale_deadline(self):
        self.check(r'''
for(unsigned reason=0;reason<5;++reason) {
 m->active=1;
 if(reason==0)m->enabled=0;
 if(reason==1)c->ram[0xad]=1;
 if(reason==2)c->ram[0xaf]=2;
 if(reason==3)c->ram[0x129]=1;
 if(reason==4)c->pad_buttons[0]=PAD_A|PAD_RIGHT;
 assert(!rings_motion_before(c) || reason==4);assert(!m->moves);
 m->enabled=1;c->ram[0xad]=c->ram[0xaf]=c->ram[0x129]=0;c->pad_buttons[0]=0;
}
assert(!rings_motion_revision(c) && !c->fault); /* Synthetic ROM is never auto-enabled. */
assert(sdl_host_open(&h));RingsSaves saves={0};h.saves=&saves;h.responsive_movement=1;
m->due=123;m->next_step=456;rings_save_host_loaded(&h,c);
assert(m->enabled && m->intent==&h.pad_intent && !m->due && !m->next_step && !m->active);
m->fallback=PAD_RIGHT;h.input.focused=0;rings_pad_sample(&h,c,0);assert(!m->fallback);
h.settings.enhanced=0;rings_settings_apply(&h,c);assert(!m->enabled);
h.settings.enhanced=1;rings_settings_apply(&h,c);assert(m->enabled && !m->active);
sdl_host_close(&h);
''')
