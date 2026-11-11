> **Atualização v0.2 (11/11/2026):** consulte [CHANGELOG_v0.2.md](CHANGELOG_v0.2.md). Controle bloqueado até validar opcodes; parser JPEG incremental; medições nominais; HTML com exportação independente do Claude. As declarações históricas de validação abaixo são do pacote original e **não foram verificadas**.

# Projeto SmartUSG-AI — Código-fonte

Engenharia reversa do transdutor Wi-Fi EagleView (Sonostar/Sonoptek) e plataforma
POCUS construída sobre ele. Este pacote reúne todo o código implementado no projeto.

Autor do projeto: Dr. Matheus de Freitas Silva — Araguari, MG
Versão do pacote: novembro de 2026

---

## Mapa do pacote

### 01_aquisicao_protocolo/  — comunicação com o probe
- `smartusg_wifi.py` — harness de companheiro/MITM. Conecta no probe (TCP 5002 imagem /
  5003 controle), monta/envia comandos (frame 55AAFF00 + checksum), recebe e decodifica
  os frames. Modo OBSERVE por padrão; controle só com --allow-control.
- `pcap_decode.py` — decodificador de capturas PCAP (PCAPdroid/tcpdump): extrai e rotula
  os frames de comando, verifica checksum, classifica o stream de imagem. Requer scapy.
- `protocolo_smartusg_wifi.md` — especificação do protocolo (portas, frames, checksum,
  famílias, framing de imagem, controle de Doppler).

### 02_calibracao_reconstrucao/  — geometria e scan conversion
- `scan_convert.py` — conversão das linhas brutas (160x512) na imagem real (linear/
  convexo/cardíaco), calibração pixel->cm, janela de B-mode. Tri-modo EagleView.
- `exam_registry.json` — registro de calibração por ASSINATURA de preset
  (modo + código de profundidade -> geometria). Fórmula oficial R = 780000*B/A.
- `presets_matrix.csv` — 196 presets (38 probes) extraídos dos ExamJsons do APK.

### 03_analise_imagem/  — medição e qualidade
- `image_quality.py` — métricas de qualidade sem modelo treinado (Sobel, histograma,
  penetração, desequilíbrio de TGC) + sugestões de ajuste.
- `optimizer_policy.py` — política de otimização de aquisição (preset do fabricante +
  métricas -> ajuste limitado dos parâmetros).
- `vessel_detect.py` — reimplementação portável do algoritmo da lib nativa vessel_flow
  (Sobel -> segmentação -> findLine -> curva), para detecção de vaso em frames reais.

### 04_api_nativa/  — libs do fabricante
- `api_nativa_referencia.md` — superfície JNI/C++ de libvessel_flow.so e
  libneedle_location.so (CV clássica; needle = rastreio magnético), e das libs ausentes
  dsc/enh (scan conversion e realce), com as receitas de reaproveitamento.

### 05_engine_web/  — plataforma POCUS (roda no navegador)
- `pocus_engine.html` — PRINCIPAL. Plataforma com os módulos Cardíaco (TAPSE, FEVE/
  Teichholz, derrame), VCI (colapsabilidade) e Acesso Central (Ø + profundidade). Modo-M
  do cine, caliper, ROI ancorada, exportação DICOM (validada), coleta de anotações e
  upload de exames (vídeo/imagem). Autossuficiente (frames embutidos).
- `vaso_ancorado.html` — versão inicial: detector de vaso ancorado (setROI).
- `vaso_tool.html` — versão intermediária: cine + medição + DICOM + dataset.

### 06_dossie/
- `build_dossie.js` — gera o dossiê técnico em Word (Times New Roman). Node + docx.

### dados/
- `commands.csv` — exemplo de saída do pcap_decode (timeline de comandos).

---

## Como rodar os scripts Python

Dependências (conforme o script): `pip install scapy numpy scipy scikit-learn pillow matplotlib pydicom`

Exemplos:
    python3 01_aquisicao_protocolo/pcap_decode.py captura.pcap
    python3 02_calibracao_reconstrucao/scan_convert.py
    python3 03_analise_imagem/vessel_detect.py

## Como rodar o engine
Abrir `05_engine_web/pocus_engine.html` no navegador (ou usar o link publicado).

## Como gerar o dossiê
    cd 06_dossie && node build_dossie.js   # requer: npm i docx

---

## Notas importantes
- Protocolo e calibração validados para o EagleView específico do projeto (portas
  5002/5003, família 5A A5, frame 160x512). Outro modelo/firmware pode exigir ajuste.
- Color/PW NÃO trafegam no stream: são renderizados pelo app. Para obtê-los é preciso
  computá-los (via vessel_flow), não decodificá-los.
- DICOM gerado é Secondary Capture (imagem + calibração + medidas), universal e sem PACS.
- PHI: remover identificação na origem para qualquer uso além do estudo.
