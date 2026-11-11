#!/usr/bin/env python3
"""
scan_convert.py — Converte as linhas brutas do SmartUSG (160 x 512) na imagem real
(retangular p/ linear, setorial p/ convexo) e calibra pixel->cm.

Para quem não programa: rode a função de demonstração no fim (sem argumentos) e veja as
imagens geradas. Para um frame seu, só mude 'DEPTH_CM' e 'PROBE' no topo.

Entrada: frames.npy  (N, 160, 512)  — gerado da captura.
Saída:   PNGs reconstruídos + eixo em cm.

Geometria: o APK não expõe o raio/ângulo em claro, então são PARÂMETROS. Ajuste 'PROBE'
até o formato bater com a imagem que o app mostra; a profundidade (DEPTH_CM) você lê no app.
"""
import numpy as np

# ---- parâmetros que você ajusta ----
# O EagleView é TRI-MODO: o mesmo array físico se apresenta como convexo, linear ou
# setorial-cardíaco (phased virtual). Cada modo tem geometria própria — escolha em MODE.
MODE = "convex"          # "convex" | "linear" | "cardiac"
DEPTH_CM = 6.0            # profundidade mostrada no app no momento da captura (cm)

# Presets de geometria por modo (ajuste fino com uma captura de água por modo).
# 'apex_mm' = raio do vértice virtual: grande=convexo raso; pequeno=setor cardíaco profundo.
MODE_PRESETS = {
    "convex":  dict(kind="sector", apex_mm=40.0, fov_deg=60.0),   # água: razão borda/centro 0.50
    "linear":  dict(kind="linear", width_mm=38.0),
    "cardiac": dict(kind="sector", apex_mm=18.0, fov_deg=85.0),   # phased virtual (validado no braço)
}
# Identificação de modo pelo byte 7 do frame de controle 5F F5 (canal 5003):
MODE_SIGNATURE = {0x6e: "linear", 0x50: "convex", 0x32: "cardiac"}

# Profundidade NÃO é fixa: é a que o app exibe. cm/amostra = depth_cm/512. A água serve
# só para CONFERIR a velocidade do som assumida (1540 m/s), não para calibrar a escala.

def bmode_window(fr, lo_pct=58, hi_pct=99.3, gamma=0.9):
    """Janela dinâmica de B-mode. Os dados do probe JÁ vêm em log — não aplicar log de novo."""
    lo = np.percentile(fr, lo_pct); hi = np.percentile(fr, hi_pct)
    return (np.clip((fr - lo) / max(hi - lo, 1e-6), 0, 1) ** gamma) * 255
LINEAR_WIDTH_MM  = 38.0
CONVEX_RADIUS_MM = 40.0
CONVEX_FOV_DEG   = 60.0
N_LINES, N_SAMPLES = 160, 512

C_SOUND = 1540.0  # m/s (tecidos moles) — para referência de tempo/profundidade


def axial_cm_per_sample(depth_cm=DEPTH_CM):
    """Resolução axial: profundidade total dividida pelo nº de amostras."""
    return depth_cm / (N_SAMPLES - 1)


def to_linear(frame, depth_cm=DEPTH_CM, width_mm=LINEAR_WIDTH_MM):
    """Probe linear: imagem retangular. frame (160,512) -> (512,160) com eixos em cm."""
    frame = np.asarray(frame)
    if frame.ndim != 2 or min(frame.shape) < 2 or depth_cm <= 0 or width_mm <= 0:
        raise ValueError("frame precisa ser 2D e dimensões físicas positivas")
    img = frame.T.astype(np.float32)             # linhas->colunas, profundidade->vertical
    extent_cm = [0, width_mm / 10.0, depth_cm, 0] # [x0,x1,y_bottom,y_top]
    return img, extent_cm


def to_convex(frame, depth_cm=DEPTH_CM, radius_mm=CONVEX_RADIUS_MM,
              fov_deg=CONVEX_FOV_DEG, out_px=600):
    """Probe convexo: converte (ângulo, profundidade) -> (x,y) cartesiano (setor)."""
    frame = np.asarray(frame)
    if frame.ndim != 2 or min(frame.shape) < 2 or depth_cm <= 0 or radius_mm < 0 or not 0 < fov_deg < 180 or out_px < 2:
        raise ValueError("Geometria setorial inválida")
    n_lines, n_samp = frame.shape
    depth_mm = depth_cm * 10.0
    fov = np.radians(fov_deg)
    # geometria do setor
    ang = np.linspace(-fov / 2, fov / 2, n_lines)          # ângulo por linha
    rad = radius_mm + np.linspace(0, depth_mm, n_samp)      # raio por amostra (apex -> fundo)
    # extensão cartesiana do setor
    x_max = (radius_mm + depth_mm) * np.sin(fov / 2)
    y_min = radius_mm * np.cos(fov / 2)
    y_max = radius_mm + depth_mm
    # grade de saída
    xs = np.linspace(-x_max, x_max, out_px)
    ys = np.linspace(y_min, y_max, out_px)
    gx, gy = np.meshgrid(xs, ys)
    r = np.sqrt(gx**2 + gy**2)
    th = np.arctan2(gx, gy)                                  # 0 = vertical (eixo do probe)
    # mapeia (r,th) de volta para índices (amostra, linha)
    si = (r - radius_mm) / depth_mm * (n_samp - 1)
    li = (th + fov / 2) / fov * (n_lines - 1)
    valid = (si >= 0) & (si < n_samp) & (li >= 0) & (li < n_lines)
    out = np.zeros((out_px, out_px), np.float32)
    si_i = np.clip(si.astype(int), 0, n_samp - 1)
    li_i = np.clip(li.astype(int), 0, n_lines - 1)
    out[valid] = frame[li_i[valid], si_i[valid]]
    extent_cm = [-x_max / 10, x_max / 10, y_max / 10, y_min / 10]
    return out, extent_cm


def cm_from_sample(sample, depth_cm=DEPTH_CM, n_samples=N_SAMPLES):
    """Profundidade nominal (cm), com origem na primeira amostra.

    Convenção: amostra 0 corresponde a 0 cm e amostra n_samples-1 a depth_cm.
    A escala é NOMINAL; exige validação física para uso metrológico.
    """
    if n_samples < 2 or depth_cm <= 0:
        raise ValueError("n_samples deve ser >= 2 e depth_cm positivo")
    if not (0 <= sample <= n_samples - 1):
        raise ValueError("amostra fora do intervalo")
    return float(sample) * float(depth_cm) / (n_samples - 1)


def convert(frame, mode=MODE, depth_cm=DEPTH_CM):
    """Dispatcher por modo do EagleView. Retorna (imagem, extent_cm)."""
    if mode not in MODE_PRESETS:
        raise ValueError(f"Modo desconhecido: {mode}")
    p = MODE_PRESETS[mode]
    if p["kind"] == "linear":
        return to_linear(frame, depth_cm, p["width_mm"])
    return to_convex(frame, depth_cm=depth_cm, radius_mm=p["apex_mm"], fov_deg=p["fov_deg"])


def demo():
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    F = np.load("frames.npy").astype(np.float32)
    # escolhe o frame com mais sinal distal (melhor p/ mostrar geometria)
    far = F[:, :, 340:].mean(axis=(1, 2))
    f = F[int(np.argmax(far))]
    f = np.clip(f * 2.2, 0, 255)
    plt.rcParams["font.family"] = "DejaVu Serif"
    fig, ax = plt.subplots(1, 3, figsize=(15, 5.4))
    ax[0].imshow(f.T, cmap="gray", aspect="auto", vmin=0, vmax=255)
    ax[0].set_title("Linhas brutas (160x512)\npré-conversão"); ax[0].set_xlabel("linha"); ax[0].set_ylabel("amostra axial")
    lin, ext = to_linear(f)
    ax[1].imshow(lin, cmap="gray", extent=ext, aspect="auto", vmin=0, vmax=255)
    ax[1].set_title(f"Reconstrução LINEAR\n(prof. {DEPTH_CM} cm)"); ax[1].set_xlabel("largura (cm)"); ax[1].set_ylabel("profundidade (cm)")
    con, ext2 = to_convex(f)
    ax[2].imshow(con, cmap="gray", extent=ext2, vmin=0, vmax=255)
    ax[2].set_title(f"Reconstrução CONVEXA\n(R={CONVEX_RADIUS_MM}mm, FOV={CONVEX_FOV_DEG}°)")
    ax[2].set_xlabel("largura (cm)"); ax[2].set_ylabel("profundidade (cm)")
    fig.suptitle("SmartUSG — scan conversion das linhas capturadas (frames de bancada, em ar)", fontsize=12)
    fig.tight_layout(); fig.savefig("scan_conversion.png", dpi=130)
    print(f"axial: {axial_cm_per_sample()*10:.3f} mm/amostra  ({DEPTH_CM} cm / {N_SAMPLES} amostras)")
    print("salvo scan_conversion.png")


if __name__ == "__main__":
    demo()
