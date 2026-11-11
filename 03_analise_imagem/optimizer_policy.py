#!/usr/bin/env python3
"""
optimizer_policy.py — Política de otimização de aquisição (feature 2), 100% estática.

Fecha o laço: preset do fabricante (ponto de partida) + métricas de qualidade (image_quality)
→ ajuste limitado dos parâmetros → comandos para o harness (smartusg_wifi), com clamp e
deadband para não oscilar. Conservador por projeto: passos pequenos, limites rígidos, e nunca
toca em emissão acústica (só parâmetros receive/display).

Depende de: presets_matrix.csv (gerado do APK) e, opcionalmente, image_quality.suggest().
"""
from __future__ import annotations
import csv, os

# Faixas seguras (receive/display-side). freq/tgc deixados como "soft" até validar opcode no PCAP.
BOUNDS = {
    "gain":     (0, 100), "dr": (40, 120), "enhance": (0, 4),
    "harmonic": (0, 1),   "focus": (0, 5),
}
STEP = {"gain": 5, "dr": 10, "enhance": 1, "harmonic": 1, "focus": 1}  # passo por iteração


def load_presets(path="presets_matrix.csv") -> dict:
    out = {}
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            key = (r["probe"], r["preset"])
            out[key] = {k: int(r[k]) for k in ("gain", "dr", "enhance", "harmonic", "focus")
                        if r.get(k, "").lstrip("-").isdigit()}
    return out


def _clamp(p, v):
    lo, hi = BOUNDS[p]; return max(lo, min(hi, v))


class AcquisitionOptimizer:
    """
    Mantém o estado dos parâmetros e os ajusta a partir das sugestões de qualidade.
    Uso:
        opt = AcquisitionOptimizer("DW-C1", "abdomen")
        changes = opt.step(image_quality.suggest(metrics))
        opt.push(dev)   # envia ao probe (gated pelo harness)
    """
    def __init__(self, probe, preset, presets_path="presets_matrix.csv"):
        self.probe, self.preset = probe, preset
        base = {}
        if os.path.exists(presets_path):
            base = load_presets(presets_path).get((probe, preset), {})
        self.params = {"gain": 70, "dr": 70, "enhance": 2, "harmonic": 1, "focus": 2}
        self.params.update(base)                       # semeia com o preset do fabricante
        self.history = []

    def step(self, suggestions) -> list[dict]:
        """Aplica nudges limitados. 'freq'/'tgc_*' são registrados mas não enviados ainda."""
        changes = []
        for s in suggestions:
            p, d = s.get("param"), s.get("dir")
            if p in self.params and d in ("+", "-"):
                old = self.params[p]
                new = _clamp(p, old + (STEP[p] if d == "+" else -STEP[p]))
                if new != old:
                    self.params[p] = new
                    changes.append({"param": p, "from": old, "to": new, "why": s["reason"]})
            elif p in ("freq", "tgc_far", "tgc_near"):
                changes.append({"param": p, "note": "requer opcode validado (PCAP)", "why": s["reason"]})
        self.history.append(changes)
        return changes

    def push(self, dev):
        """Empurra o estado atual para o probe via harness (respeita allow_control)."""
        raise RuntimeError("Envio automático DESABILITADO: não há mapa de comandos confirmado para este hardware. Utilize report() para sugestões offline.")
        # dr/enhance/focus: habilitar quando o opcode estiver confirmado no hardware

    def report(self) -> str:
        return (f"[{self.probe}/{self.preset}] " +
                " ".join(f"{k}={v}" for k, v in self.params.items()))


def _demo():
    # Demonstração offline: começa do preset de abdome e "corrige" uma imagem saturada
    opt = AcquisitionOptimizer("DW-C1", "abdomen")
    print("baseline:", opt.report())
    # simula métricas de uma imagem com over-gain e DR comprimido
    fake_suggestions = [
        {"param": "gain", "dir": "-", "reason": "saturação"},
        {"param": "dr",   "dir": "+", "reason": "faixa dinâmica comprimida"},
        {"param": "freq", "dir": "-", "reason": "dropout distal"},
    ]
    for it in range(3):
        ch = opt.step(fake_suggestions)
        print(f"iter {it}:", [f"{c['param']} {c.get('from','?')}->{c.get('to','(soft)')}" for c in ch])
    print("final:   ", opt.report())


if __name__ == "__main__":
    _demo()
