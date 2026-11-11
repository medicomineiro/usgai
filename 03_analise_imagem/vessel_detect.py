#!/usr/bin/env python3
"""
vessel_detect.py — Reimplementação portável do algoritmo da lib nativa libvessel_flow.so
(com.sonoptek.jni.VesselFlow), que é ARM64+JNI e não roda neste host.

Espelha a cadeia documentada pelos símbolos da lib:
  VesselDirAna: setROI -> Sobel -> histogram -> findLine  (eixo/ângulo/centro do vaso)
  VFCalcCore:   fuzzyCMean -> GenCurve -> FindPeak -> findSD  (segmentação + curva de fluxo)

Aqui: segmentação por clustering de intensidade (equivalente ao FCM), detecção do lúmen
anecoico cercado por paredes ecogênicas, eixo/diâmetro do vaso, e uma curva temporal de
PULSATILIDADE (proxy de fluxo a partir do B-mode) com extração de pico (FindPeak) e FC.

Calibração: 0.078 mm/amostra (linear 4 cm). Entrada: car_Bframes.npy (159, 160, 512).
"""
import numpy as np
from scipy import ndimage
from sklearn.cluster import KMeans

MM_PER_SAMPLE = 0.078      # axial, modo linear 4 cm
MM_PER_LINE   = 38.0/160   # lateral, array 38 mm / 160 linhas


def preprocess(fr):
    fr = ndimage.median_filter(fr, size=3)
    lo, hi = np.percentile(fr, 55), np.percentile(fr, 99)
    return np.clip((fr - lo)/(hi - lo), 0, 1)


def sobel_energy(img):                         # VesselDirAna::Sobel()
    gx = ndimage.sobel(img, axis=1); gy = ndimage.sobel(img, axis=0)
    return np.hypot(gx, gy)


def segment_lumen(img, k=3):                    # VFCalcCore::fuzzyCMean -> classes
    X = img.reshape(-1, 1)
    km = KMeans(n_clusters=k, n_init=4, random_state=0).fit(X)
    centers = km.cluster_centers_.ravel()
    lumen_cluster = int(np.argmin(centers))     # classe mais escura = sangue/lúmen
    mask = (km.labels_ == lumen_cluster).reshape(img.shape)
    mask = ndimage.binary_opening(mask, iterations=2)
    mask = ndimage.binary_closing(mask, iterations=2)
    return mask


def find_vessel(mask, img):                     # VesselDirAna::findLine -> maior lúmen com paredes
    lbl, n = ndimage.label(mask)
    if n == 0: return None
    best = None
    for i in range(1, n+1):
        ys, xs = np.where(lbl == i)
        area = len(xs)
        if area < 150: continue
        h = ys.max()-ys.min()+1; w = xs.max()-xs.min()+1
        # vaso longitudinal: alongado horizontal, na metade superior do campo
        elong = w/max(h,1)
        depth_ok = 20 < ys.mean() < 130
        # paredes: brilho logo acima e abaixo do lúmen
        yc = int(ys.mean())
        wall = img[max(0,yc-ys.std().astype(int)-6):max(1,yc-6)].mean() + \
               img[min(159,yc+6):min(160,yc+ys.std().astype(int)+6)].mean()
        score = area*elong*(wall) * (1.2 if depth_ok else 0.5)
        if best is None or score > best[0]:
            best = (score, i, ys, xs)
    if best is None: return None
    _, i, ys, xs = best
    # diâmetro por coluna (extensão vertical do lúmen) e eixo
    diam=[]; cy=[]
    for xv in range(xs.min(), xs.max()+1):
        col = ys[xs==xv]
        if len(col): diam.append(col.max()-col.min()+1); cy.append(col.mean())
    diam=np.array(diam); cy=np.array(cy); cx=np.arange(xs.min(),xs.min()+len(cy))
    # ângulo do eixo (findLine): regressão da linha central
    if len(cx)>5:
        a=np.polyfit(cx,cy,1); angle=np.degrees(np.arctan(a[0]*MM_PER_SAMPLE/MM_PER_LINE))
    else: angle=0.0
    return dict(label=i, ys=ys, xs=xs, cx=cx, cy=cy,
                diam_mm=float(np.median(diam)*MM_PER_SAMPLE),
                angle_deg=float(angle),
                center=(float(cx.mean()), float(cy.mean())))


def pulsatility_curve(B, roi):                  # VFCalcCore::GenCurve -> FindPeak (proxy B-mode)
    """Diâmetro do lúmen ao longo do tempo = curva de distensão (proxy de fluxo)."""
    x0,x1 = int(roi['cx'].min()), int(roi['cx'].max())
    yc = int(roi['center'][1])
    curve=[]
    for fr in B:
        img=preprocess(fr)
        strip=img[max(0,yc-25):yc+25, x0:x1]       # faixa sobre o vaso
        prof=strip.mean(axis=1)                      # perfil axial local
        dark=prof < (prof.min()+ (prof.max()-prof.min())*0.4)
        curve.append(dark.sum())                     # espessura anecoica ~ diâmetro
    c=np.array(curve,float); c=(c-c.mean())
    # FindPeak + FC via FFT (10 fps)
    fps=10.0; f=np.fft.rfftfreq(len(c),1/fps); P=np.abs(np.fft.rfft(c*np.hanning(len(c))))
    band=(f>0.7)&(f<3.0)                              # 42-180 bpm
    hr = f[band][np.argmax(P[band])]*60 if band.any() else np.nan
    return c, hr


if __name__ == "__main__":
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    B=np.load("car_Bframes.npy").astype(np.float32)
    # escolhe frame com vaso longitudinal nítido
    best=None
    for idx in [57,58,63,66,60,62,55]:
        img=preprocess(B[idx]); mask=segment_lumen(img); roi=find_vessel(mask,img)
        if roi and (best is None or roi['diam_mm']>best[1]['diam_mm']):
            best=(idx,roi,img,mask)
    idx,roi,img,mask=best
    c,hr=pulsatility_curve(B,roi)
    plt.rcParams["font.family"]="DejaVu Serif"
    fig,ax=plt.subplots(2,2,figsize=(13,9))
    ax[0,0].imshow(img,cmap="gray",aspect="auto"); ax[0,0].set_title(f"B-mode frame {idx}")
    ax[0,1].imshow(sobel_energy(img),cmap="magma",aspect="auto"); ax[0,1].set_title("Sobel (bordas) — VesselDirAna")
    ov=np.stack([img]*3,-1); ov[mask]=[0.1,0.5,1.0]
    ax[1,0].imshow(ov,aspect="auto")
    ax[1,0].plot(roi['cx'],roi['cy'],'y-',lw=1.5)
    ax[1,0].set_title(f"Lúmen detectado (azul) + eixo\nØ≈{roi['diam_mm']:.1f} mm · ângulo {roi['angle_deg']:+.0f}°")
    ax[1,1].plot(np.arange(len(c))/10.0,c,lw=1.2)
    ax[1,1].set_title(f"Curva de pulsatilidade (GenCurve/FindPeak)\nFC≈{hr:.0f} bpm"); ax[1,1].set_xlabel("s"); ax[1,1].set_ylabel("Ø relativo"); ax[1,1].grid(alpha=.3)
    for a in ax.ravel()[:3]: a.set_xlabel("linha"); a.set_ylabel("amostra")
    fig.suptitle("vessel_flow reimplementado — carótida D (frames reais)",fontsize=12)
    fig.tight_layout(); fig.savefig("vessel_detect.png",dpi=135)
    print(f"frame {idx}: Ø={roi['diam_mm']:.1f} mm, ângulo={roi['angle_deg']:+.1f}°, FC={hr:.0f} bpm")
