import ast, hashlib, os, struct, subprocess, sys, tempfile, time, unittest, zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import render  # noqa: E402

ENTRY = os.path.join(ROOT, 'art', 'entry.png')


def run_main(out_dir):
    env = dict(os.environ, MAKEFUN_OUTPUT_DIR=out_dir)
    t = time.time()
    subprocess.run([sys.executable, os.path.join(ROOT, 'main.py')], env=env, check=True)
    with open(os.path.join(out_dir, 'entry.png'), 'rb') as fh:
        return time.time() - t, fh.read()


class TestEntry(unittest.TestCase):
    def test_1_main_twice_identical(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            _, d1 = run_main(a)
            _, d2 = run_main(b)
        self.assertEqual(d1, d2)
        self.assertEqual(d1, open(ENTRY, 'rb').read())

    def test_2_png_valid(self):
        data = open(ENTRY, 'rb').read()
        self.assertEqual(data[:8], b'\x89PNG\r\n\x1a\n')
        pos, idat, tags = 8, b'', []
        while pos < len(data):
            ln, = struct.unpack('>I', data[pos:pos + 4])
            tag, body = data[pos + 4:pos + 8], data[pos + 8:pos + 8 + ln]
            crc, = struct.unpack('>I', data[pos + 8 + ln:pos + 12 + ln])
            self.assertEqual(crc, zlib.crc32(tag + body) & 0xffffffff, tag)
            tags.append(tag)
            if tag == b'IHDR':
                w, h, bd, ct, _, _, il = struct.unpack('>IIBBBBB', body)
                self.assertEqual((w, h, bd, ct, il), (1024, 1024, 8, 2, 0))
            if tag == b'IDAT':
                idat += body
            pos += 12 + ln
        self.assertEqual(pos, len(data))
        self.assertEqual(tags[0], b'IHDR')
        self.assertEqual(tags[-1], b'IEND')
        self.assertEqual(len(zlib.decompress(idat)), 1024 * (1 + 3 * 1024))

    def test_3_size(self):
        size = os.path.getsize(ENTRY)
        print('\n  entry.png size: %d bytes' % size)
        self.assertLessEqual(size, 1048576)

    def test_4_runtime(self):
        with tempfile.TemporaryDirectory() as a:
            dt, _ = run_main(a)
        print('\n  main.py runtime: %.3f s' % dt)
        self.assertLess(dt, 5.0)

    def test_5_render_deterministic(self):
        with tempfile.TemporaryDirectory() as a:
            out = os.path.join(a, 'r.png')
            t = time.time()
            subprocess.run([sys.executable, os.path.join(ROOT, 'render.py'), '--out', out],
                           check=True, stdout=subprocess.DEVNULL)
            print('\n  render.py runtime: %.1f s' % (time.time() - t))
            h1 = hashlib.sha256(open(out, 'rb').read()).hexdigest()
        h0 = hashlib.sha256(open(ENTRY, 'rb').read()).hexdigest()
        print('  sha256: %s' % h0)
        self.assertEqual(h1, h0)

    def test_6_preview_300(self):
        dst = os.path.join(ROOT, 'candidates', 'preview-300.png')
        render.preview300(ENTRY, dst)
        w, h, rows = render.read_png(dst)
        self.assertEqual((w, h, len(rows)), (300, 300, 300))

    def test_7_stdlib_only(self):
        allowed = set(sys.stdlib_module_names) | {'render'}
        for rel in ('main.py', 'render.py', os.path.join('tests', 'test_entry.py')):
            with open(os.path.join(ROOT, rel)) as fh:
                tree = ast.parse(fh.read())
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or '']
                for n in names:
                    self.assertIn(n.split('.')[0], allowed, '%s imports %s' % (rel, n))


if __name__ == '__main__':
    unittest.main()
