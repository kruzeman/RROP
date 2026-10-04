"""Clocked sound: real bus writes, timesteps, FM/DAC/PSG and headless WAV."""
from pathlib import Path
import array
import contextlib
import io
import os
import shutil
import struct
import subprocess
import tempfile
import unittest
import wave
from genesis_recompiler.build import build_audio_backend, build_executable, sdl2_flags, BuildError
from genesis_recompiler.cli import main
from genesis_recompiler.decode import analyze
from genesis_recompiler.emit import emit
from support import CompiledTestCase, rom_with


class SoundFixture(CompiledTestCase):
    @classmethod
    def setUpClass(cls):
        cls.backend_temp=tempfile.TemporaryDirectory()
        cls.backend=Path(cls.backend_temp.name)/'sound.o'
        build_audio_backend(cls.backend)

    @classmethod
    def tearDownClass(cls):cls.backend_temp.cleanup()

    def compile_sound(self,source,sdl=False):
        path=self.root/'sound.c';obj=self.root/'sound.o';binary=self.root/'sound'
        path.write_text(source)
        flags,libs=sdl2_flags() if sdl else ([],[])
        command=['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-Wno-unused-function','-DGENESIS_AUDIO']
        if sdl:command+=['-DGENESIS_SDL2']
        result=subprocess.run([*command,*flags,'-c',str(path),'-o',str(obj)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        result=subprocess.run(['c++',str(obj),str(self.backend),'-o',str(binary),*libs],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        return binary

    def sound(self,body,pal=False):
        source='#define GENESIS_NO_MAIN\n'+emit(analyze(rom_with('4e72 2700'),[0x200]))+'''
#include <assert.h>
static void fm(CPU*c,unsigned bank,uint8_t reg,uint8_t value){
 write_mem(c,0xa04000+bank*2,1,reg);write_mem(c,0xa04001+bank*2,1,value);
}
static void advance(CPU*c,uint64_t clocks){c->master_cycles+=clocks;audio_sync(c);}
int main(int argc,char**argv){
 assert(argc==2);CPU c={0};c.rom=rom_data;c.rom_size=sizeof rom_data;c.sr=0x2700;
 c.audio_mode=AUDIO_ON;c.vdp.pal=PAL;c.z80_bus.requested=1;
 assert(audio_init(&c,argv[1]));
'''.replace('PAL','1' if pal else '0')+body+'''
 assert(!c.fault && audio_finish(&c));return 0;}
'''
        binary=self.compile_sound(source);wav=self.root/'test.wav'
        result=subprocess.run([str(binary),str(wav)],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)
        with wave.open(str(wav),'rb') as f:
            self.assertEqual((f.getnchannels(),f.getframerate(),f.getsampwidth()),(2,48000,2))
            data=f.readframes(f.getnframes())
        samples=struct.unpack('<'+'h'*(len(data)//2),data)
        self.assertEqual(wav.stat().st_size,len(data)+44)
        return samples


class SoundTests(SoundFixture):
    def test_psg_frequency_stereo_volume_and_pal_clock(self):
        # N=254. Genesis PSG tone frequency is master_clock/(15*16*2*N).
        body='''
 psg_write(&c,0x8e);psg_write(&c,0x0f);psg_write(&c,0x90);
 advance(&c,vdp_master_frequency(&c.vdp));assert(c.audio.frames==48000);
'''
        for pal in (False,True):
            samples=self.sound(body,pal)
            left=samples[4000::2];right=samples[4001::2]
            self.assertEqual(left,right)
            crossings=sum(a<=0<b for a,b in zip(left,left[1:]))
            frequency=crossings*48000/len(left)
            expected=(53203424 if pal else 53693175)/(480*254)
            self.assertAlmostEqual(frequency,expected,delta=2)
            self.assertGreater(max(left)-min(left),3000)
            self.assertLess(max(left),2500)

    def test_chunking_preserves_identical_pcm_and_register_timing(self):
        setup='psg_write(&c,0x84);psg_write(&c,0x08);psg_write(&c,0x93);\n'
        whole=self.sound(setup+'advance(&c,500000);psg_write(&c,0x9f);advance(&c,500000);')
        chunks=self.sound(setup+'''
for(unsigned i=0;i<1000;++i){advance(&c,500);}
psg_write(&c,0x9f);
for(unsigned i=0;i<1000;++i){advance(&c,500);}
''')
        self.assertEqual(whole,chunks)
        self.assertLess(max(abs(s) for s in whole[-100:]),40)

    def test_fm_operators_keyon_panning_and_keyoff(self):
        samples=self.sound('''
 for(unsigned op=0;op<4;++op){
  fm(&c,0,(uint8_t)(0x30+op*4),1);fm(&c,0,(uint8_t)(0x40+op*4),0);
  fm(&c,0,(uint8_t)(0x50+op*4),31);fm(&c,0,(uint8_t)(0x60+op*4),0);
  fm(&c,0,(uint8_t)(0x70+op*4),0);fm(&c,0,(uint8_t)(0x80+op*4),15);
 }
 fm(&c,0,0xb0,7);fm(&c,0,0xb4,0x80);fm(&c,0,0xa4,0x22);fm(&c,0,0xa0,0x69);
 fm(&c,0,0x28,0xf0);advance(&c,vdp_master_frequency(&c.vdp)/2);
 fm(&c,0,0x28,0);advance(&c,vdp_master_frequency(&c.vdp)/2);
''')
        active=samples[4000:40000:2];silent=samples[-2000:];right=samples[4001:40000:2]
        self.assertGreater(max(active)-min(active),5000)
        self.assertLess(max(abs(s) for s in right),20)
        self.assertLess(max(abs(s) for s in silent),20)
        crossings=sum(a<=0<b for a,b in zip(active,active[1:]))
        frequency=crossings*48000/len(active)
        # FNUM=$269, block=4: fnum * 2^(block-1) * FM_clock / (144*2^20).
        expected=0x269*8*(53693175/7)/(144*2**20)
        self.assertAlmostEqual(frequency,expected,delta=3)

    def test_dac_pcm_with_independent_left_right_routing(self):
        samples=self.sound('''
 fm(&c,1,0xb6,0x80);fm(&c,0,0x2b,0x80);
 for(unsigned i=0;i<1000;++i){fm(&c,0,0x2a,i&1 ? 192:64);advance(&c,vdp_master_frequency(&c.vdp)/1000);}
''')
        left=samples[4000::2];right=samples[4001::2]
        self.assertGreater(max(left)-min(left),3000)
        self.assertLess(max(abs(s) for s in right),20)
        self.assertLess(max(abs(s) for s in left),10000)

    def test_busy_timer_a_b_clear_cancel_and_z80_reset(self):
        self.sound('''
 fm(&c,0,0x22,0);assert(read_mem(&c,0xa04000,1)&0x80);
 advance(&c,300*7);assert(!(read_mem(&c,0xa04000,1)&0x80));
 fm(&c,0,0x24,0xff);fm(&c,0,0x25,3);fm(&c,0,0x26,0xff);fm(&c,0,0x27,0x0f);
 advance(&c,3000*7);assert((read_mem(&c,0xa04000,1)&3)==3);
 fm(&c,0,0x27,0x30);advance(&c,3000*7);assert(!(read_mem(&c,0xa04000,1)&3));
 fm(&c,0,0x27,5);advance(&c,300*7);assert(read_mem(&c,0xa04000,1)&1);
 write_mem(&c,0xa11200,2,0);advance(&c,300*7);assert(read_mem(&c,0xa04000,1)==0);
''')

    def test_periodic_noise_and_white_noise_feedback(self):
        self.sound('''
 psg_write(&c,0xe0);advance(&c,1024*240);assert(c.psg.noise_lfsr==0x8000);
 psg_write(&c,0xe4);advance(&c,1024*240);assert(c.psg.noise_lfsr!=0x8000 && c.psg.noise_lfsr!=0);
 psg_write(&c,0xe3);assert(c.psg.counter[3]==1);
 psg_write(&c,0xf0);advance(&c,200000);assert(c.audio.peak>1000);
''')

    def test_wav_without_device_and_invalid_configuration(self):
        source=emit(analyze(rom_with('60fe'),[0x200]));binary=self.compile_sound(source)
        path=self.root/'diagnostic.wav'
        result=subprocess.run([str(binary),'--headless','--audio','on','--limit','1000','--dump-audio',str(path)],capture_output=True,text=True)
        self.assertEqual(result.returncode,2,result.stderr)
        self.assertIn('rate=48000 channels=2',result.stdout)
        with wave.open(str(path),'rb') as f:self.assertGreater(f.getnframes(),50)
        bad=subprocess.run([str(binary),'--audio','mute','--dump-audio',str(path)],capture_output=True,text=True)
        self.assertEqual(bad.returncode,64)
        bad=subprocess.run([str(binary),'--audio','on','--dump-audio',str(self.root/'missing/child.wav')],capture_output=True,text=True)
        self.assertEqual(bad.returncode,1);self.assertIn('cannot open audio WAV',bad.stderr)
        plain=self.execute(rom_with('4e72 2700'),['--audio','on'])
        self.assertEqual(plain.returncode,64);self.assertIn('--sound ymfm',plain.stderr)

    def test_ring_overflow_is_bounded_and_does_not_change_wav(self):
        samples=self.sound('''
 c.audio.playback=1;advance(&c,vdp_master_frequency(&c.vdp)/2);
 assert(c.audio.count==AUDIO_RING_FRAMES && c.audio.dropped>10000);
 int16_t buffer[14];assert(audio_pop(&c,buffer,7)==7);
 assert(c.audio.count==AUDIO_RING_FRAMES-7);
''')
        self.assertAlmostEqual(len(samples)//2,24000,delta=1)

    def test_backend_build_validation_and_atomic_previous_binary(self):
        binary=self.root/'game';binary.write_bytes(b'previous')
        source=emit(analyze(rom_with('4e72 2700'),[0x200]))
        with self.assertRaises(BuildError):build_executable(source,binary,sound='unknown')
        with self.assertRaises(BuildError):build_executable(source,binary,sound='ymfm',cxx='nonexistent-genesis-cxx')
        self.assertEqual(binary.read_bytes(),b'previous')
        rom=self.root/'game.bin';rom.write_bytes(rom_with('4e72 2700'))
        with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):
            main([str(rom),'-o',str(self.root/'game.c'),'--sound','ymfm'])

    @unittest.skipUnless(Path('/dev/full').exists(), 'requires Linux /dev/full')
    def test_wav_write_failure_stops_without_overrunning_buffer(self):
        source='#define GENESIS_NO_MAIN\n'+emit(analyze(rom_with('4e72 2700'),[0x200]))+'''
#include <assert.h>
int main(void){
 CPU c={0};c.rom=rom_data;c.rom_size=sizeof rom_data;c.audio_mode=AUDIO_ON;
 assert(audio_init(&c,"/dev/full"));
 c.master_cycles=vdp_master_frequency(&c.vdp);audio_sync(&c);
 assert(c.fault && c.audio.error && c.audio.frames==48000);
 assert(c.audio.wav_count<=AUDIO_WAV_FRAMES);
 assert(!audio_finish(&c));return 0;}
'''
        binary=self.compile_sound(source)
        result=subprocess.run([str(binary)],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)


class SDLSoundTests(SoundFixture):
    @classmethod
    def setUpClass(cls):
        try:sdl2_flags()
        except BuildError:raise unittest.SkipTest('SDL2 development files are absent')
        super().setUpClass()

    def host(self,body,driver='dummy'):
        source='#define GENESIS_NO_MAIN\n'+emit(analyze(rom_with('4e72 2700'),[0x200]))+'''
#include <assert.h>
static void key(Uint32 type,SDL_Keycode code){SDL_Event event={0};event.type=type;event.key.keysym.sym=code;assert(SDL_PushEvent(&event)==1);}
int main(void){
 CPU c={0};c.rom=rom_data;c.rom_size=sizeof rom_data;c.audio_mode=AUDIO_ON;assert(audio_init(&c,NULL));
 SDLHost h={0};assert(sdl_host_open(&h));sdl_host_audio_open(&h,&c);
'''+body+'''
 sdl_host_close(&h);assert(!h.audio_device);assert(audio_finish(&c));return 0;}
'''
        binary=self.compile_sound(source,sdl=True)
        result=subprocess.run([str(binary)],env={**os.environ,'SDL_VIDEODRIVER':'dummy','SDL_RENDER_DRIVER':'software','SDL_AUDIODRIVER':driver},capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        return result

    def test_dummy_audio_queue_pause_resume_and_fast_forward_flush(self):
        self.host('''
 assert(h.audio_device && c.audio.playback);
 h.audio_running=1; // Leave the initially paused dummy device paused while inspecting its queue.
 c.master_cycles=vdp_master_frequency(&c.vdp)*30/1000;audio_sync(&c);
 assert(c.audio.count>=1439 && c.audio.count<=1440);
 unsigned queued=c.audio.count;assert(sdl_host_audio_service(&h,&c));
 assert(c.audio.count==0 && SDL_GetQueuedAudioSize(h.audio_device)==queued*4);
 key(SDL_KEYDOWN,SDLK_SPACE);assert(sdl_host_service(&h,&c));
 assert(h.paused && !c.audio.playback && SDL_GetQueuedAudioSize(h.audio_device)==0);
 key(SDL_KEYUP,SDLK_SPACE);key(SDL_KEYDOWN,SDLK_SPACE);assert(sdl_host_service(&h,&c));
 assert(!h.paused && c.audio.playback && !h.audio_running);
 c.master_cycles+=vdp_master_frequency(&c.vdp)*30/1000;audio_sync(&c);
 assert(sdl_host_audio_service(&h,&c));assert(h.audio_running);
 assert(SDL_GetAudioDeviceStatus(h.audio_device)==SDL_AUDIO_PLAYING);
 key(SDL_KEYDOWN,SDLK_TAB);assert(sdl_host_service(&h,&c));
 assert(h.fast_forward && !c.audio.playback && SDL_GetQueuedAudioSize(h.audio_device)==0);
 uint64_t frames=c.audio.frames;c.master_cycles+=vdp_master_frequency(&c.vdp)/100;audio_sync(&c);
 assert(c.audio.frames>frames && !c.audio.count);
 key(SDL_KEYUP,SDLK_TAB);assert(sdl_host_service(&h,&c));assert(c.audio.playback && !c.audio.count);
 h.no_throttle=1;assert(sdl_host_audio_service(&h,&c));assert(!c.audio.playback);
''')

    def test_missing_audio_device_keeps_video_and_synthesis_running(self):
        result=self.host('''
 assert(!h.audio_device && !h.error && !c.audio.playback);
 c.master_cycles=vdp_master_frequency(&c.vdp)/100;audio_sync(&c);
 assert(c.audio.frames>=480 && sdl_host_service(&h,&c));
''',driver='nonexistent-genesis-sound-driver')
        self.assertIn('audio unavailable',result.stderr)
        self.assertIn('video continues',result.stderr)

    def test_cli_sdl_build_with_sound_and_wav(self):
        rom=self.root/'test.bin';rom.write_bytes(rom_with('60fe'))
        binary=self.root/'game';report=self.root/'analysis.json';wav=self.root/'record.wav'
        with contextlib.redirect_stdout(io.StringIO()):
            result=main([str(rom),'--build','--frontend','sdl2','--sound','ymfm','-o',str(binary),'--report',str(report)])
        self.assertEqual(result,0)
        import json
        self.assertEqual(json.loads(report.read_text())['sound_backend'],'ymfm')
        result=subprocess.run([str(binary),'--window','--audio','on','--no-throttle','--limit','1000','--dump-audio',str(wav)],env={**os.environ,'SDL_VIDEODRIVER':'dummy','SDL_RENDER_DRIVER':'software','SDL_AUDIODRIVER':'dummy'},capture_output=True,text=True)
        self.assertEqual(result.returncode,2,result.stderr)
        self.assertIn('sound samples=',result.stdout)
        with wave.open(str(wav),'rb') as f:self.assertGreater(f.getnframes(),50)
