#!/usr/bin/env python3
"""
smartusg_wifi.py — Harness de companheiro/MITM para transdutores Wi-Fi Sonostar/Sonoptek
(app com.sonostar.SmartUSG / wirelessusg4).

Reconstruído por engenharia reversa ESTÁTICA do APK v1.0.3. Protocolo "Família A"
(magic 55 AA FF 00, probes de scanline bruto 128x512) totalmente implementado;
Famílias B (5A A5) e C (5F F5) e MJPEG são detectadas e logadas, não controladas.

>>> STATUS: não validado contra hardware. Use primeiro em modo OBSERVE (padrão). <<<
>>> Envio de comandos exige allow_control=True explicitamente.                   <<<

Dependências: só stdlib para captura/controle. Pillow/numpy opcionais p/ salvar PNG.

Uso típico:
    # 1) Só observar (seguro): conecta no probe e loga o que chega
    python3 smartusg_wifi.py --host 190.166.8.1 --observe

    # 2) Capturar N frames brutos para disco
    python3 smartusg_wifi.py --host 190.166.8.1 --observe --save-frames 20

    # 3) Controle (bancada): ex. ajustar ganho e congelar — requer --allow-control
    python3 smartusg_wifi.py --host 190.166.8.1 --allow-control --set-gain 70
"""
import socket, struct, threading, time, argparse, logging, os, sys

LOG = logging.getLogger("smartusg")

# ---------------------------------------------------------------------------
# Parâmetros do protocolo (extraídos do APK)
# ---------------------------------------------------------------------------
DEFAULT_PORT   = 52001          # u4.q.f22863w
CONNECT_TMO    = 1.0            # c(): a(host, 52001, 1000ms)
PUMP_PERIOD    = 0.050          # u4.q.k(): Timer a cada 50 ms
RECV_CHUNK     = 29200          # r4.a: buffer de recepção (sobe p/ 58400)
MAGIC_A        = bytes([0x55, 0xAA, 0xFF, 0x00])
MAGIC_B        = bytes([0x5A, 0xA5, 0x00, 0x00])
MAGIC_C        = bytes([0x5F, 0xF5, 0x00, 0x00])

# Gateways conhecidos por geração de probe (u4/* .n("190.166.x.1"))
KNOWN_GATEWAYS = ["190.166.3.1","190.166.4.1","190.166.5.1","190.166.6.1",
                  "190.166.7.1","190.166.8.1","190.166.9.1","190.188.1.1","192.168.1.1"]

# Reconstrução COMPLETA do mapa (classe-base u4.t0 + especialização z0). Há dois conjuntos
# de frames; o probe usa um OU outro conforme o método s() (classe do transdutor):
#   perfil "a55"  (s()==true):  frames 55 AA FF 00 (opcodes abaixo) + run/freeze len 24
#   perfil "a5a5" (s()==false): frame combinado 5A A5 (gain+freq+freeze) + 5C C5 (profundidade)
MAGIC_D = bytes([0x5C, 0xC5])       # profundidade/focal (G(): {5C C5 g g})

# setter(t0) -> campo -> opcode (perfil a55). Estrutura CONFIRMADA; rótulo clínico de
# 0x82/0x84/0x85/0xF2 é INFERÊNCIA de alta confiança (falta trace de UI p/ fechar 100%).
OPCODES_A = {
    0x81: "C()->G  profundidade/focal (válidos: 1..13, 36/40/44/48, 149/153/157/161/165)",
    0x82: "T()->O  parâmetro [provável zoom/color-gain]",
    0x84: "H()->K  booleano [provável harmônica/THI on-off]",
    0x85: "V()->J  parâmetro [provável índice de foco]",
    0xF2: "I()->N  booleano [provável inversão/steer]",
    0x00: "A()->   run/freeze/cine (len 24): D(nframes), C(freeze), E(gain), F(freq)",
}

# Lei de ganho (confirmada em t0.z()/F()): E em [30,105] -> byte de 7 bits.
def gain_to_tx(E: int) -> int:
    E = max(30, min(105, E))
    return int(((E - 30) / 75.0) * 127.0 + 0.5) & 0x7F

def _cksum(buf: bytearray):
    buf[5] = (0 - (sum(buf) & 0xFF)) & 0xFF   # complemento de 2: soma do frame ≡ 0

# ---- Perfil a55 (55 AA FF 00) ----
def build_cmd_A(opcode: int, value: int = 0, length: int = 16, extra=b"") -> bytes:
    buf = bytearray(length)
    buf[0:4] = MAGIC_A; buf[4] = length & 0xFF; buf[6] = opcode & 0xFF
    if length >= 9: buf[8] = value & 0xFF
    for i, b in enumerate(extra):
        if 9 + i < length: buf[9 + i] = b & 0xFF
    _cksum(buf); return bytes(buf)

def build_run_A(nframes: int, freeze: bool, gain_E=0, freq=0) -> bytes:
    """run/freeze len 24 (Q()): [14]=nframes [15]=freeze [17]=gain(E) [19]=freq&3."""
    buf = bytearray(24)
    buf[0:4] = MAGIC_A; buf[4] = 24
    buf[14] = nframes & 0xFF; buf[15] = (1 if freeze else 0); buf[16] = 1
    buf[17] = gain_E & 0xFF; buf[18] = 1; buf[19] = freq & 0x03
    _cksum(buf); return bytes(buf)

# ---- Perfil a5a5 (5A A5 + 5C C5), SEM checksum ----
FREEZE_BIT = 0x80   # k6.o.f15788b
def build_bmode_5AA5(gain_E: int, freq: int, run: bool, freeze: bool) -> bytes:
    """Controle B-mode combinado (F()): [2]=flags(run 0x20|freeze 0x80|freq&3) [3]=gain7b."""
    b = bytearray(4); b[0] = 0x5A; b[1] = 0xA5
    flags = 0x20 if run else 0x00
    if freeze: flags |= FREEZE_BIT
    b[2] = flags | (freq & 0x03)
    b[3] = gain_to_tx(gain_E) & 0x7F
    return bytes(b)

def build_depth_5CC5(g: int, color_capable: bool = False) -> bytes:
    """Profundidade/focal (G()): {5C C5 g g}; byte[3]=0 em probes com cor."""
    return bytes([0x5C, 0xC5, g & 0xFF, 0x00 if color_capable else (g & 0xFF)])

# ---------------------------------------------------------------------------
# Parser de entrada (reassembly) — Família A
# ---------------------------------------------------------------------------
# u4.q.a(): pacote util >= 525B; linha/status se byte[8]==0xFF (payload em [12..12+512)).
# Frame B completo >= 1050B; no driver z0.b() o buffer cru tem 128 linhas * 525 + header,
# cada linha = 13B header + 512B dados (amostras 8-bit). 128x512 => imagem.
LINE_STRIDE = 525
LINE_DATA   = 512
N_LINES     = 128

def try_parse_raw_frame_A(buf: bytes):
    """Extrai imagem 128x512 (bytes) de um buffer de frame Família A, se couber."""
    need = (N_LINES + 1) * LINE_STRIDE
    if len(buf) < need:
        return None
    img = bytearray(N_LINES * LINE_DATA)
    for ln in range(1, N_LINES + 1):
        off = ln * LINE_STRIDE + 12
        img[(ln - 1) * LINE_DATA:(ln) * LINE_DATA] = buf[off:off + LINE_DATA]
    return bytes(img)  # 128*512, 1 byte/amostra, ordem linha-maior

def scan_mjpeg(stream: bytes):
    """Gera (jpeg_bytes) para cada SOI..EOI no buffer (Famílias B/C / probes JPEG)."""
    i = 0
    while True:
        s = stream.find(b"\xff\xd8\xff", i)
        if s < 0: break
        e = stream.find(b"\xff\xd9", s + 3)
        if e < 0: break
        yield stream[s:e + 2]
        i = e + 2

# ---------------------------------------------------------------------------
# Cliente
# ---------------------------------------------------------------------------
class SmartUSG:
    def __init__(self, host, port=DEFAULT_PORT, allow_control=False, on_frame=None, framing="jpeg"):
        if framing not in ("jpeg", "raw-fixed-experimental"):
            raise ValueError("framing deve ser jpeg ou raw-fixed-experimental")
        self.framing = framing
        self.host, self.port = host, port
        self.allow_control = allow_control
        self.on_frame = on_frame           # callback(img_bytes, meta) p/ sua IA
        self.sock = None
        self._tx_lock = threading.Lock()
        self._pending = bytearray()        # comandos a enviar no próximo tick
        self._run = False
        self._rxbuf = bytearray()
        self.stats = {"status_pkts":0,"raw_frames":0,"mjpeg_frames":0,"bytes":0}

    # -- conexão --
    def connect(self):
        LOG.info("Conectando %s:%d (control=%s)", self.host, self.port,
                 "ON" if self.allow_control else "OFF/observe")
        self.sock = socket.create_connection((self.host, self.port), timeout=CONNECT_TMO)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 58400)
        self.sock.settimeout(1.0)
        self._run = True
        threading.Thread(target=self._rx_loop, daemon=True).start()
        threading.Thread(target=self._pump_loop, daemon=True).start()

    def close(self):
        self._run = False
        try: self.sock and self.sock.close()
        except Exception: pass

    # -- envio (gated) --
    def _queue(self, frame: bytes, why: str):
        if not self.allow_control:
            LOG.warning("[OBSERVE] comando suprimido (%s): %s", why, frame.hex())
            return
        with self._tx_lock:
            self._pending += frame
        LOG.info("[TX enfileirado] %s: %s", why, frame.hex())

    def _pump_loop(self):
        while self._run:
            time.sleep(PUMP_PERIOD)
            with self._tx_lock:
                if self._pending and self.sock:
                    data = bytes(self._pending); self._pending.clear()
                else:
                    data = b""
            if data:
                try: self.sock.sendall(data)
                except Exception as e: LOG.error("TX falhou: %s", e)

    # -- API de alto nível (Família A; rótulos a validar no PCAP) --
    def set_gain(self, v):
        raise RuntimeError("BLOQUEADO: opcode 0x81 corresponde a profundidade/foco no mapa A; ganho ainda não validado. Não transmitir.")
    def set_param_82(self, v):
        raise RuntimeError("BLOQUEADO: opcode 0x82 não validado")
    def toggle_harmonic(self, on):
        raise RuntimeError("BLOQUEADO: função harmônica para opcode 0x84 é inferência não validada. Não transmitir.")
    def set_param_85(self, v):
        raise RuntimeError("BLOQUEADO: opcode 0x85 não validado")
    def toggle_F2(self, on):
        raise RuntimeError("BLOQUEADO: opcode 0xF2 não validado")
    def freeze(self):
        raise RuntimeError("BLOQUEADO: run/freeze não foi validado neste transdutor")
    def run(self, nframes=1):
        raise RuntimeError("BLOQUEADO: run/freeze não foi validado neste transdutor")

    def apply_preset(self, preset: dict):
        """Aplica um preset do ExamJsons (gain, harmonic...). Só os parâmetros mapeados."""
        if "gain" in preset or "harmonic" in preset:
            raise RuntimeError("Preset bloqueado: comandos não validados")
        # dr/enhance/focus: opcodes a confirmar no PCAP antes de habilitar

    # -- recepção --
    def _rx_loop(self):
        while self._run:
            try:
                chunk = self.sock.recv(RECV_CHUNK)
            except socket.timeout:
                continue
            except Exception as e:
                LOG.error("RX erro: %s", e); break
            if not chunk:
                LOG.info("RX: conexão fechada pelo probe"); break
            self.stats["bytes"] += len(chunk)
            self._rxbuf += chunk
            self._demux()

    def _demux(self):
        """Extrator incremental conservador. Nunca interpreta 525 B isolados como status.

        jpeg: procura SOI/EOI, retém JPEG incompleto entre recv();
        raw-fixed-experimental: habilita parser legado APENAS em bancada;
        o framing de linhas e metadados ainda não foi demonstrado.
        """
        if self.framing == "raw-fixed-experimental":
            self._demux_legacy()
            return
        soi = b"\xff\xd8\xff"
        eoi = b"\xff\xd9"
        while True:
            start = self._rxbuf.find(soi)
            if start < 0:
                # Retém até dois bytes para SOI dividido entre blocos TCP.
                if len(self._rxbuf) > 2:
                    del self._rxbuf[:-2]
                return
            if start:
                del self._rxbuf[:start]
            end = self._rxbuf.find(eoi, 3)
            if end < 0:
                if len(self._rxbuf) > 16 * 1024 * 1024:
                    LOG.warning("JPEG >16MB sem EOI: reiniciando sincronização")
                    del self._rxbuf[:3]
                return
            jpg = bytes(self._rxbuf[:end + 2])
            del self._rxbuf[:end + 2]
            self.stats["mjpeg_frames"] += 1
            if self.on_frame:
                self.on_frame(jpg, {"kind": "jpeg", "len": len(jpg), "timestamp": time.time()})

    def _demux_legacy(self):
        buf = bytes(self._rxbuf)
        # (a) frame bruto Família A completo?
        need = (N_LINES + 1) * LINE_STRIDE
        if len(buf) >= need and (buf[8] & 0xFF) == 0xFF:
            img = try_parse_raw_frame_A(buf)
            if img:
                self.stats["raw_frames"] += 1
                meta = {"kind":"raw128x512","w":LINE_DATA,"h":N_LINES}
                if self.on_frame: self.on_frame(img, meta)
                del self._rxbuf[:need]
                return
        # (b) status/linha 512B (byte[8]==0xFF, payload em [12..])
        if len(buf) >= LINE_STRIDE and (buf[8] & 0xFF) == 0xFF and len(buf) < need:
            self.stats["status_pkts"] += 1
            del self._rxbuf[:LINE_STRIDE]
            return
        # (c) MJPEG (Famílias B/C / probes JPEG) — detecção oportunista
        last = 0
        for jpg in scan_mjpeg(buf):
            self.stats["mjpeg_frames"] += 1
            meta = {"kind":"jpeg","len":len(jpg)}
            if self.on_frame: self.on_frame(jpg, meta)
            last = buf.find(jpg) + len(jpg)
        if last: del self._rxbuf[:last]
        # anti-estouro
        if len(self._rxbuf) > 4 * need:
            LOG.debug("rxbuf grande, descartando %d B sem sync", len(self._rxbuf)//2)
            del self._rxbuf[:len(self._rxbuf)//2]

# ---------------------------------------------------------------------------
# Utilidades de saída
# ---------------------------------------------------------------------------
def save_frame(img_or_jpeg, meta, idx, outdir):
    os.makedirs(outdir, exist_ok=True)
    if meta["kind"] == "jpeg":
        p = os.path.join(outdir, f"frame_{idx:04d}.jpg")
        open(p, "wb").write(img_or_jpeg); return p
    # raw 128x512 -> PNG (se Pillow) ou PGM (sempre)
    w, h = meta["w"], meta["h"]
    try:
        from PIL import Image
        im = Image.frombytes("L", (w, h), img_or_jpeg)
        p = os.path.join(outdir, f"frame_{idx:04d}.png"); im.save(p); return p
    except Exception:
        p = os.path.join(outdir, f"frame_{idx:04d}.pgm")
        with open(p, "wb") as f:
            f.write(f"P5\n{w} {h}\n255\n".encode()); f.write(img_or_jpeg)
        return p

# ---------------------------------------------------------------------------
# MITM passivo (opcional): sente-se entre app e probe para VALIDAR o protocolo
# sem arriscar o hardware. O telefone conecta neste PC (gateway falso) e este
# PC repassa ao probe real, logando os dois sentidos.
# ---------------------------------------------------------------------------
def run_mitm(listen_host, probe_host, port=DEFAULT_PORT, logfile="mitm.log"):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((listen_host, port)); srv.listen(1)
    LOG.info("MITM ouvindo %s:%d -> probe %s:%d", listen_host, port, probe_host, port)
    app, _ = srv.accept()
    up = socket.create_connection((probe_host, port), timeout=CONNECT_TMO)
    lf = open(logfile, "ab")
    def relay(src, dst, tag):
        while True:
            try: data = src.recv(65536)
            except Exception: break
            if not data: break
            lf.write(f"[{time.time():.3f}] {tag} {len(data)}B\n".encode())
            lf.write(data.hex().encode() + b"\n"); lf.flush()
            try: dst.sendall(data)
            except Exception: break
    threading.Thread(target=relay, args=(app, up, "APP->PROBE"), daemon=True).start()
    relay(up, app, "PROBE->APP")

# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Harness Wi-Fi SmartUSG (Família A)")
    ap.add_argument("--host", help="gateway do probe (ex. 190.166.8.1)")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--observe", action="store_true", help="só recebe (padrão seguro)")
    ap.add_argument("--allow-control", action="store_true", help="HABILITA envio de comandos")
    ap.add_argument("--save-frames", type=int, default=0, help="salva N frames e sai")
    ap.add_argument("--outdir", default="frames")
    ap.add_argument("--set-gain", type=int, help="RESERVADO: bloqueado até validar opcode")
    ap.add_argument("--framing", choices=["jpeg", "raw-fixed-experimental"], default="jpeg")
    ap.add_argument("--mitm", nargs=2, metavar=("LISTEN_IP","PROBE_IP"),
                    help="modo proxy passivo app<->probe")
    ap.add_argument("-v","--verbose", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    if a.mitm:
        run_mitm(a.mitm[0], a.mitm[1], a.port); return
    if not a.host:
        ap.error("--host é obrigatório (ou use --mitm)")

    saved = {"n": 0}
    def on_frame(data, meta):
        if a.save_frames and saved["n"] < a.save_frames:
            p = save_frame(data, meta, saved["n"], a.outdir)
            LOG.info("salvo %s (%s)", p, meta["kind"]); saved["n"] += 1

    dev = SmartUSG(a.host, a.port, allow_control=a.allow_control and not a.observe,
                   on_frame=on_frame, framing=a.framing)
    dev.connect()
    try:
        if a.allow_control and not a.observe:
            LOG.warning("Controle do equipamento bloqueado nesta versão enquanto os comandos não forem validados por PCAP")
            if a.set_gain is not None: dev.set_gain(a.set_gain)
        t0 = time.time()
        while True:
            time.sleep(1.0)
            LOG.info("stats %s", dev.stats)
            if a.save_frames and saved["n"] >= a.save_frames: break
            if time.time() - t0 > 120: break
    except KeyboardInterrupt:
        pass
    finally:
        dev.close()

if __name__ == "__main__":
    main()
