# API nativa SmartUSG/Sonoptek — referência e receitas de reaproveitamento

Extraído de `libvessel_flow.so` e `libneedle_location.so` (nm/readelf/c++filt) e das classes JNI
no DEX. Reconstrução **estática**.

## Achado importante: 4 libs carregadas, 2 ausentes no APK

`System.loadLibrary` referencia **`dsc`, `enh`, `vessel_flow`, `needle_location`**, mas o APK só
contém `libvessel_flow.so` e `libneedle_location.so` (arm64-v8a). **`libdsc.so` e `libenh.so`
não estão neste pacote** — provavelmente em split APK / outra ABI, ou baixados em runtime. Para
reaproveitá-las você precisa extraí-las do dispositivo, ou reimplementar (DSC é geometria padrão).

| Lib | Presente? | Função | Depende de |
|---|---|---|---|
| `vessel_flow` | ✅ | Doppler/fluxo + direção de vaso (CV clássica) | só libc/libm/liblog |
| `needle_location` | ✅ | **Rastreio magnético** de agulha (não imagem) | só libc/libm |
| `dsc` | ❌ ausente | Scan conversion (polar→leque), Vulkan | AssetManager (shaders) |
| `enh` | ❌ ausente | Realce/speckle reduction, Vulkan | AssetManager (shaders) |

## 1. `vessel_flow` — reaproveitável direto (feature 6, parte imagem)

Internals: `VFCalcCore` (fuzzyCMean, erosion/dilation, median/meanFilter, GenCurve, FindPeak,
FindSD) + `VesselDirAna` (Sobel, FCM, histogram, findLine). Zero dependência externa.

JNI (`com.sonoptek.jni.VesselFlow`, métodos `static native`):

| Assinatura | Uso |
|---|---|
| `boolean setROI(byte[] img, int w, int h, int x, int y)` | injeta frame cinza 8-bit + ROI; retorna validade |
| `int[] GenCurve(int[] data, int w, int h)` | gera a curva espectral de fluxo |
| `int[] findPeak()` | pico (sístole) da curva |
| `int[] findSD()` | largura espectral / SD |
| `float getAngle()` | ângulo do eixo do vaso (correção Doppler) |
| `int getStartCenterX/Y()`, `getEndCenterX/Y()` | geometria do vaso |
| `void dealloc()` | libera estado |

**Receita:** `setROI(frameBytes, 512, 128, roiX, roiY)` → `getStartCenter*/getEndCenter*` + `getAngle()`
para o eixo; `GenCurve → findPeak/findSD` para métricas de fluxo. Você alimenta com o mesmo
`byte[]` que o harness entrega.

## 2. `needle_location` — CORREÇÃO: é magnético, não por imagem

Não detecta agulha na imagem. É ajuste de **modelo de dipolo magnético** por Levenberg-Marquardt
(`CLevmarFitting`, `CLevmarFittingL3`) + `CKalmanFilter`. Requer **agulha sensorizada + magnetômetro
no probe**. Sem esse hardware, a lib é inútil para você — para agulha por imagem (B-mode) o modelo é
net-new.

JNI (`com.sonoptek.magneticpositiondemo.jni.Needle`):

| Assinatura | Uso |
|---|---|
| `double[] needleLocation(double[] sensor, double[48] out)` | posição/orientação; `out[7]==-1` ⇒ inválido |
| `boolean getPOSIsRight()` | validade do ajuste |
| `int sensorCalibration(double[])`, `int setSensorParam(double[], double[], double[])` | bias/escala do sensor |
| `int setLocationParam(d0..d9)` | geometria/offsets do conjunto |

## 3. `dsc` (ausente) — scan conversion e o fator pixel→cm

Converte os scanlines polares **128×512** na imagem em leque. É **aqui que mora a calibração
geométrica** que as medições (VTI, TAPSE, diâmetros) exigem.

JNI (`com.sonoptek.vulkan.VKDSCJni`, `loadLibrary("dsc")`):

| Assinatura | Papel |
|---|---|
| `initDSCTableWithSteer(apex, startAngle, angleSpan, inW, inH, outW, outH, f, radius, d, d)` | tabela polar→cartesiano (fan) |
| `int[] vulkanDSCImage(byte[] lines, w, h, outW, outH, mode)` | B-mode → ARGB em leque |
| `byte[] vulkanColorDSCImage(...)`, `vulkanPowerDSCImage(...)` | overlay Doppler cor/power |
| `vulkanInitDSC(w, h, _, f×4, int, int, f, f)` / `updateDscParams(int[], ...)` | geometria dinâmica |

**Implicação:** `apex`, `radius`, `angleSpan`, profundidade → definem mm/pixel. Sem `libdsc.so`,
reimplemente o DSC (mapeamento polar→cartesiano padrão para convexo/linear) usando esses mesmos
parâmetros, que vêm do ExamJsons/status do probe. Esse é o passo que destrava a feature 5.

## 4. `enh` (ausente) — realce

`VKEnhJni`: `enhance(byte[] img, w, h) → byte[]`, `setEnhanceMode/Level`, `getEnhanceLevel`.
Speckle reduction GPU. Substituível por filtro próprio (anisotrópico/NLM) se não obtiver a lib.

## Mapa feature → recurso nativo

| Feature | Recurso | Situação |
|---|---|---|
| 3/6 vaso e fluxo | `vessel_flow` ✅ | reutilizar direto |
| 6 agulha (magnética) | `needle_location` ✅ | só com hardware sensorizado |
| 6 agulha (imagem) | — | modelo próprio |
| 5 medições | geometria do `dsc` ❌ | reimplementar DSC a partir dos params |
| realce | `enh` ❌ | lib própria |
| 1/4 janela e qualidade | — (ver `image_quality.py`) | baseline pronto, rede = net-new |
