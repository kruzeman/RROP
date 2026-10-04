from support import CompiledTestCase, rom_with


class Z80BusTests(CompiledTestCase):
    def test_granted_ram_access_and_mirroring(self):
        # Request bus, release reset while retaining bus ownership, write RAM.
        code='33fc 0100 00a11100 33fc 0100 00a11200 23fc 12345678 00a00000 2039 00a02000 1239 00a11100 4e72 2700'
        dump=self.root/'z80.bin'
        result=self.execute(rom_with(code),['--dump-z80',str(dump)])
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('D0=12345678',result.stdout)
        self.assertIn('D1=00000000',result.stdout)
        self.assertIn('ram_writes=4 bus_request=1 reset_released=1',result.stdout)
        data=dump.read_bytes()
        self.assertEqual(len(data),8192)
        self.assertEqual(data[:4],bytes.fromhex('12345678'))

    def test_ram_access_requires_bus_request(self):
        result=self.execute(rom_with('1039 00a00000 4e72 2700'))
        self.assertEqual(result.returncode,1)
        self.assertIn('bus has not been granted',result.stderr)

    def test_reset_preserves_uploaded_ram(self):
        code='33fc 0100 00a11100 13fc 00ab 00a00000 33fc 0100 00a11200 33fc 0000 00a11200 1039 00a00000 33fc 0000 00a11100 4e72 2700'
        result=self.execute(rom_with(code))
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('D0=000000ab',result.stdout)

    def test_release_reports_missing_execution(self):
        for code in (
            '33fc 0100 00a11200 4e72 2700',
            '33fc 0100 00a11100 33fc 0100 00a11200 33fc 0000 00a11100 4e72 2700',
        ):
            with self.subTest(code=code):
                result=self.execute(rom_with(code))
                self.assertEqual(result.returncode,1)
                self.assertIn('Z80 PC has no static translation',result.stderr)

    def test_odd_control_byte_does_not_change_bus_request(self):
        code='13fc 0001 00a11101 1039 00a11100 4e72 2700'
        result=self.execute(rom_with(code))
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('D0=00000001',result.stdout)
