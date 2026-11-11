import sys
import unittest
from pathlib import Path
from unittest.mock import Mock
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'01_aquisicao_protocolo'))
sys.path.insert(0, str(ROOT/'02_calibracao_reconstrucao'))
sys.path.insert(0, str(ROOT/'03_analise_imagem'))
import smartusg_wifi as hw
import scan_convert as sc
from optimizer_policy import AcquisitionOptimizer
import numpy as np

class ProtocolTests(unittest.TestCase):
    def test_checksum_a(self):
        f=hw.build_cmd_A(0x81,70)
        self.assertEqual(f[:4],hw.MAGIC_A)
        self.assertEqual(len(f),16)
        self.assertEqual(sum(f)%256,0)
    def test_observe_only_default(self):
        device=hw.SmartUSG('127.0.0.1')
        device._queue(b'abc','teste')
        self.assertFalse(device.allow_control)
        self.assertEqual(device._pending, b'')
    def test_ambiguous_opcodes_refused_even_if_enabled(self):
        d=hw.SmartUSG('127.0.0.1',allow_control=True)
        for f in (lambda:d.set_gain(65),lambda:d.toggle_harmonic(True),lambda:d.run(),lambda:d.freeze()):
            with self.assertRaises(RuntimeError): f()
        self.assertEqual(d._pending,b'')
    def test_jpeg_fragmentation_and_concatenation(self):
        got=[]
        d=hw.SmartUSG('127.0.0.1',on_frame=lambda x,m:got.append((x,m)))
        j1=b'\xff\xd8\xff' + b'alpha' + b'\xff\xd9'
        j2=b'\xff\xd8\xff' + b'beta' + b'\xff\xd9'
        for part in [b'junk\xff', b'\xd8\xffalpha\xff',b'\xd9'+j2+b'noise']:
            d._rxbuf.extend(part);d._demux()
        self.assertEqual([x for x,_ in got],[j1,j2])
        self.assertEqual(d.stats['mjpeg_frames'],2)
    def test_raw_requires_explicit_opt_in(self):
        self.assertEqual(hw.SmartUSG('127.0.0.1').framing,'jpeg')
        with self.assertRaises(ValueError):hw.SmartUSG('127.0.0.1',framing='raw')

class GeometryTests(unittest.TestCase):
    def test_axial_endpoints(self):
        self.assertEqual(sc.cm_from_sample(0,depth_cm=8),0.0)
        self.assertAlmostEqual(sc.cm_from_sample(511,depth_cm=8),8.0)
    def test_bad_geometry(self):
        with self.assertRaises(ValueError):sc.cm_from_sample(512)
        with self.assertRaises(ValueError):sc.convert(np.zeros((128,512)),mode='invalid')
    def test_linear_any_number_lines(self):
        fr=np.ones((128,512),dtype=np.uint8)
        img, ext=sc.to_linear(fr,depth_cm=8)
        self.assertEqual(img.shape,(512,128))
        self.assertAlmostEqual(ext[1],3.8)
    def test_sector_bounds(self):
        fr=np.ones((160,512),dtype=np.uint8)
        img,ext=sc.to_convex(fr,depth_cm=8,out_px=48)
        self.assertEqual(img.shape,(48,48))
        self.assertTrue(np.isfinite(img).all())

class OptimizerTests(unittest.TestCase):
    def test_no_hardware_push(self):
        opt=AcquisitionOptimizer('test','test',presets_path='/tmp/nonexistent_smartusg.csv')
        device=Mock()
        with self.assertRaises(RuntimeError):opt.push(device)
        device.assert_not_called()
        self.assertFalse(device.set_gain.called)
    def test_bounded_offline_suggestions(self):
        opt=AcquisitionOptimizer('test','test',presets_path='/tmp/nonexistent_smartusg.csv')
        for _ in range(40): opt.step([{'param':'gain','dir':'+','reason':'benchmark'}])
        self.assertEqual(opt.params['gain'],100)

if __name__=='__main__':unittest.main()
