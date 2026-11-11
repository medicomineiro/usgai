#!/usr/bin/env python3
"""
pcap_decode.py — Decodifica uma captura (PCAP/PCAPNG) do probe Wi-Fi SmartUSG e produz uma
LINHA DO TEMPO de comandos rotulada, para você cruzar com as ações feitas na UI e fechar o
mapa opcode→parâmetro.

Captura recomendada (sem root): PCAPdroid no próprio celular (VPNService, exporta .pcap).
Alternativas: tcpdump em celular rooteado; ou o modo --mitm do smartusg_wifi.py.

Uso:
    python3 pcap_decode.py captura.pcap                 # timeline no console + commands.csv
    python3 pcap_decode.py captura.pcap --port 52001    # porta do probe (padrão 52001)
    python3 pcap_decode.py captura.pcap --dump-frames   # salva 1º frame de imagem detectado

Requer scapy (pip install scapy).
"""
import argparse, csv, sys
from collections import defaultdict

PORT = 52001
MAGICS = {b"\x55\xaa\xff\x00": "A", b"\x5a\xa5\x00\x00": "B", b"\x5f\xf5\x00\x00": "C"}

# Rótulo provável dos opcodes Família A (a CONFIRMAR cruzando com a UI).
OP_LABELS_A = {0x81: "P/ganho?", 0x82: "K", 0x84: "L/bool(harm?)",
               0x85: "N", 0xF2: "O/bool", 0x00: "run/freeze"}


def cksum_ok_A(frame: bytes) -> bool:
    return (sum(frame) & 0xFF) == 0            # complemento de 2: soma do frame ≡ 0


def parse_commands(payload: bytes, ts: float, direction: str):
    """Varre um payload TCP e extrai frames de comando (qualquer família)."""
    out, i, n = [], 0, len(payload)
    while i < n - 6:
        magic = payload[i:i + 4]
        fam = MAGICS.get(magic)
        if fam:
            length = payload[i + 4]
            if 8 <= length <= 64 and i + length <= n:
                frame = payload[i:i + length]
                op = frame[6] if length > 6 else None
                val = frame[8] if length > 8 else None
                rec = {
                    "ts": round(ts, 4), "dir": direction, "fam": fam, "len": length,
                    "op": f"0x{op:02X}" if op is not None else "",
                    "op_label": OP_LABELS_A.get(op, "") if fam == "A" else "",
                    "val": val if val is not None else "",
                    "cksum_ok": cksum_ok_A(frame) if fam == "A" else "",
                    "hex": frame.hex(),
                }
                out.append(rec)
                i += length
                continue
        i += 1
    return out


def classify_inbound(payload: bytes):
    """Conta pacotes de status/frame e detecta MJPEG."""
    kinds = []
    if len(payload) >= 525 and (payload[8] & 0xFF) == 0xFF:
        kinds.append("status512" if len(payload) < 1050 else "rawframe")
    if payload[:3] == b"\xff\xd8\xff":
        kinds.append("jpeg")
    return kinds


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pcap")
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--csv", default="commands.csv")
    ap.add_argument("--dump-frames", action="store_true")
    a = ap.parse_args()
    try:
        from scapy.all import rdpcap, TCP, Raw
    except Exception:
        sys.exit("scapy ausente: pip install scapy")

    pkts = rdpcap(a.pcap)
    cmds, inbound = [], defaultdict(int)
    img_buf = bytearray()
    for p in pkts:
        if TCP not in p or Raw not in p:
            continue
        tcp = p[TCP]; data = bytes(p[Raw].load); ts = float(p.time)
        if tcp.dport == a.port:                 # APP -> PROBE (comandos)
            cmds += parse_commands(data, ts, "APP->PROBE")
        elif tcp.sport == a.port:               # PROBE -> APP (imagem/status)
            for k in classify_inbound(data):
                inbound[k] += 1
            if a.dump_frames:
                img_buf += data

    # --- timeline ---
    print(f"{'ts':>12}  {'dir':<10} fam len {'op':<6} {'label':<14} val ck  hex")
    prev = {}
    for c in cmds:
        changed = ""
        if c["fam"] == "A" and c["op"]:
            if prev.get(c["op"]) not in (None, c["val"]):
                changed = "  <== VALOR MUDOU"
            prev[c["op"]] = c["val"]
        ck = "ok" if c["cksum_ok"] is True else ("BAD" if c["cksum_ok"] is False else "-")
        print(f"{c['ts']:>12}  {c['dir']:<10} {c['fam']:<3} {c['len']:>3} "
              f"{c['op']:<6} {c['op_label']:<14} {str(c['val']):>3} {ck:<3} {c['hex']}{changed}")

    with open(a.csv, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(cmds[0].keys()) if cmds else
                           ["ts","dir","fam","len","op","op_label","val","cksum_ok","hex"])
        w.writeheader(); [w.writerow(c) for c in cmds]

    print("\n--- resumo ---")
    print(f"comandos extraídos: {len(cmds)}  -> {a.csv}")
    byop = defaultdict(set)
    for c in cmds:
        if c["op"]:
            byop[c["op"]].add(str(c["val"]))
    print("opcodes vistos (valores distintos):")
    for op in sorted(byop):
        print(f"  {op}: {sorted(byop[op])[:12]}")
    print(f"entrada: {dict(inbound)}")

    if a.dump_frames and img_buf:
        s = bytes(img_buf).find(b"\xff\xd8\xff")
        if s >= 0:
            e = bytes(img_buf).find(b"\xff\xd9", s + 3)
            if e > 0:
                open("frame0.jpg", "wb").write(bytes(img_buf)[s:e + 2])
                print("salvo frame0.jpg (MJPEG)")
        else:
            open("inbound_raw.bin", "wb").write(bytes(img_buf)[:70000])
            print("salvo inbound_raw.bin (procure frames 128x512)")


if __name__ == "__main__":
    main()
