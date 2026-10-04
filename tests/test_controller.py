import subprocess
from support import CompiledTestCase, rom_with
from genesis_recompiler.decode import analyze
from genesis_recompiler.emit import emit


class ControllerTests(CompiledTestCase):
    def check(self, body):
        program = analyze(rom_with("4e72 2700"), [0x200])
        source = "#define GENESIS_NO_MAIN\n" + emit(program) + "\n#include <assert.h>\nint main(void) { CPU c={0}; c.rom=rom_data; c.rom_size=sizeof rom_data;\n" + body + "\nreturn 0; }\n"
        binary = self.compile(source)
        result = subprocess.run([str(binary)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_active_low_buttons_in_both_th_phases(self):
        self.check('''
assert(read8(&c,0xa10003)==0x7f);
io_write(&c,4,0x40);
const unsigned buttons[]={PAD_UP,PAD_DOWN,PAD_LEFT,PAD_RIGHT,PAD_A,PAD_B,PAD_C,PAD_START};
const unsigned high[]={0x7e,0x7d,0x7b,0x77,0x7f,0x6f,0x5f,0x7f};
const unsigned low[]={0x32,0x31,0x33,0x33,0x23,0x33,0x33,0x13};
for (unsigned i=0;i<8;++i) {
    c.pad_buttons[0]=(uint8_t)buttons[i];
    io_write(&c,1,0x40); assert(read8(&c,0xa10003)==high[i]);
    io_write(&c,1,0); assert(read8(&c,0xa10003)==low[i]);
    assert(read8(&c,0xa10005)==0x7f);
}
c.pad_buttons[0]=0xff;
io_write(&c,1,0); assert(io_read(&c,1)==0);
io_write(&c,1,0x40); assert(io_read(&c,1)==0x40);
assert(!c.fault);
''')

    def test_input_th_is_pulled_high_and_outputs_override_pad(self):
        self.check('''
c.pad_buttons[0]=PAD_A|PAD_START;
io_write(&c,1,0); assert(io_read(&c,1)==0x7f);
io_write(&c,4,0x40); assert(io_read(&c,1)==3);
c.pad_buttons[0]=0xff;
io_write(&c,4,0xff); io_write(&c,1,0xa5); assert(io_read(&c,1)==0xa5);
io_write(&c,4,0x01); io_write(&c,1,0x01); assert(io_read(&c,1)==0x41);
assert(!c.fault);
''')

    def test_second_port_is_independent(self):
        self.check('''
c.pad_buttons[1]=PAD_LEFT|PAD_C;
assert(io_read(&c,1)==0x7f && io_read(&c,2)==0x5b);
io_write(&c,5,0x40); io_write(&c,2,0);
c.pad_buttons[1]=PAD_DOWN|PAD_START;
assert(io_read(&c,2)==0x11 && io_read(&c,1)==0x7f);
assert(!c.fault);
''')

    def test_serial_initialization_and_read_only_receive_status(self):
        self.check('''
for (unsigned p=0;p<3;++p) {
    unsigned base=7+3*p;
    io_write(&c,base,0xa5); assert(io_read(&c,base)==0xa5);
    io_write(&c,base+1,0xff); assert(io_read(&c,base+1)==0);
    io_write(&c,base+2,0xc7); assert(io_read(&c,base+2)==0xc0);
    io_write(&c,base+2,0x40); assert(io_read(&c,base+2)==0x40);
}
io_write(&c,1,0x80); assert(io_read(&c,1)==0xff);
assert(!c.fault);
io_write(&c,9,0x30); assert(c.fault);
assert(strstr(c.reason,"active serial communication"));
''')
