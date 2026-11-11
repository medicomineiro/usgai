#!/usr/bin/env python3
"""
image_quality.py — Métricas de qualidade de imagem ultrassonográfica, SEM modelo treinado.

Objetivo: feature 4 (avaliação contínua de qualidade) + alimentar a feature 2 (otimização).
Usa as MESMAS primitivas que as libs nativas do app (Sobel, histograma) — portanto é um
baseline principiado que roda no dia 1, antes de qualquer rede neural.

Entrada: frame em tons de cinza 8-bit (ex. 128x512 bruto do harness, ou DSC decodificado).
Saída:  dict de métricas + score 0..100 + sugestões de correção já no vocabulário de controle
        (ganho, dr, harmônica, TGC perto/longe, frequência).

numpy acelera; há fallback puro-Python.
"""
from __future__ import annotations
try:
    import numpy as np
    _NP = True
except Exception:
    _NP = False


def _to_matrix(buf: bytes, w: int, h: int):
    if _NP:
        return np.frombuffer(buf, dtype=np.uint8)[: w * h].reshape(h, w).astype(np.float32)
    return [[buf[y * w + x] for x in range(w)] for y in range(h)]


def _sobel_energy(m, w, h) -> float:
    """Energia média do gradiente (nitidez/estrutura)."""
    if _NP:
        gx = np.abs(np.diff(m, axis=1)).mean()
        gy = np.abs(np.diff(m, axis=0)).mean()
        return float(gx + gy)
    acc = n = 0
    for y in range(h):
        for x in range(1, w):
            acc += abs(m[y][x] - m[y][x - 1]); n += 1
    return acc / max(n, 1)


def _row_means(m, w, h):
    """Média por linha (eixo de profundidade) — base p/ TGC e penetração."""
    if _NP:
        return m.mean(axis=1)
    return [sum(m[y]) / w for y in range(h)]


def analyze(buf: bytes, w: int = 512, h: int = 128,
            tissue_lo: int = 15, sat_hi: int = 250) -> dict:
    """Calcula métricas de qualidade de um frame em tons de cinza."""
    m = _to_matrix(buf, w, h)
    if _NP:
        flat = m.ravel()
        mean = float(flat.mean()); std = float(flat.std())
        sat = float((flat >= sat_hi).mean())          # fração saturada (over-gain)
        dark = float((flat <= tissue_lo).mean())       # fração anecoica/escura
        hist, _ = np.histogram(flat, bins=32, range=(0, 255))
        p = hist / max(hist.sum(), 1); p = p[p > 0]
        entropy = float(-(p * np.log2(p)).sum())       # uso da faixa dinâmica (0..5)
    else:
        n = w * h; s = s2 = sat = dark = 0
        for y in range(h):
            for x in range(w):
                v = m[y][x]; s += v; s2 += v * v
                if v >= sat_hi: sat += 1
                if v <= tissue_lo: dark += 1
        mean = s / n; std = (s2 / n - mean * mean) ** 0.5
        sat /= n; dark /= n; entropy = 4.0  # aproximação no fallback

    sharp = _sobel_energy(m, w, h)
    rows = _row_means(m, w, h)
    near = float(sum(rows[: h // 3]) / max(h // 3, 1))
    far = float(sum(rows[-h // 3:]) / max(h // 3, 1))
    penetration = float(far / (near + 1e-6))           # <~0.25 => dropout de campo distante
    tgc_imbalance = float((near - far))                # >0 grande => perto saturado vs longe fraco

    # Score 0..100: pesos empíricos; penaliza saturação, escuridão, baixa nitidez e dropout
    score = 100.0
    score -= 120 * max(sat - 0.02, 0)          # saturação acima de 2%
    score -= 60 * max(dark - 0.55, 0)          # fundo quase todo preto
    score -= 40 * max(0.35 - min(entropy / 5, 1), 0)   # faixa dinâmica subutilizada
    score -= 50 * max(0.25 - penetration, 0) / 0.25    # penetração ruim
    score += 8 * min(sharp / 12.0, 1.0)        # bônus de nitidez (saturado)
    score = max(0.0, min(100.0, score))

    return {
        "mean": round(mean, 1), "std": round(std, 1),
        "saturated_frac": round(sat, 3), "dark_frac": round(dark, 3),
        "entropy_bits": round(entropy, 2), "sharpness": round(sharp, 2),
        "near_mean": round(near, 1), "far_mean": round(far, 1),
        "penetration": round(penetration, 3), "tgc_imbalance": round(tgc_imbalance, 1),
        "score": round(score, 1),
    }


def suggest(metrics: dict) -> list[dict]:
    """Traduz métricas em ajustes acionáveis (vocabulário do controle)."""
    s = []
    if metrics["saturated_frac"] > 0.03:
        s.append({"param": "gain", "dir": "-", "reason": "saturação (>3% em 255)"})
    elif metrics["dark_frac"] > 0.6 and metrics["mean"] < 40:
        s.append({"param": "gain", "dir": "+", "reason": "imagem subexposta (fundo escuro)"})
    if metrics["entropy_bits"] < 3.0:
        s.append({"param": "dr", "dir": "+", "reason": "faixa dinâmica comprimida"})
    if metrics["penetration"] < 0.2:
        s.append({"param": "freq", "dir": "-", "reason": "dropout de campo distante → freq menor"})
        s.append({"param": "tgc_far", "dir": "+", "reason": "reforçar TGC profundo"})
    if metrics["tgc_imbalance"] > 60:
        s.append({"param": "tgc_near", "dir": "-", "reason": "campo próximo saturado vs distante"})
    if metrics["sharpness"] < 4.0:
        s.append({"param": "harmonic", "dir": "+",
                  "reason": "baixa nitidez → ligar THI (reduz reverberação)"})
    if not s:
        s.append({"param": None, "dir": "0", "reason": "dentro da faixa aceitável"})
    return s


if __name__ == "__main__":
    import sys, os
    if len(sys.argv) < 2:
        # autoteste sintético: gradiente vertical + ruído → métricas plausíveis
        w, h = 512, 128
        if _NP:
            g = (np.linspace(10, 200, h)[:, None] * np.ones((1, w))).astype(np.uint8)
            buf = g.tobytes()
        else:
            buf = bytes([min(255, 10 + (y * 190 // h)) for y in range(h) for _ in range(w)])
        mets = analyze(buf, w, h)
    else:
        path = sys.argv[1]; raw = open(path, "rb").read()
        if path.endswith((".pgm",)):  # pula header P5
            idx = raw.index(b"255\n") + 4; raw = raw[idx:]
        w = int(sys.argv[2]) if len(sys.argv) > 2 else 512
        h = int(sys.argv[3]) if len(sys.argv) > 3 else 128
        mets = analyze(raw, w, h)
    import json
    print(json.dumps(mets, indent=2, ensure_ascii=False))
    print("Sugestões:")
    for s in suggest(mets):
        print(f"  {s['param'] or '—':10s} {s['dir']}  {s['reason']}")
