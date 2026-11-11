# Protocolo Wi-Fi SmartUSG / Sonostar-Sonoptek — reconstrução estática

**Fonte:** APK `com.sonostar.SmartUSG` v1.0.3 (jadx + androguard). Reconstrução **estática**;
rótulos de parâmetro marcados *(inferido)* exigem validação por PCAP contra o hardware.

## 1. Transporte

| Item | Valor | Origem |
|---|---|---|
| Meio | Wi-Fi; o probe é o Access Point | permissões do Manifest |
| Host (gateway) | `190.166.{3..9}.1`, `190.188.1.1`, default `192.168.1.1` | `u4/*`, `u4.q.f22862v` |
| Porta | **52001** (TCP) | `u4.q.f22863w` |
| Socket | **único, bidirecional** (comando + imagem no mesmo canal) | `r4.a` |
| Timeout de conexão | 1000 ms | `u4.q.c()` |
| Buffer RX | 29200 → 58400 B | `r4.a.C0237a.run()` |
| Pump de comando | Timer a cada **50 ms**; envia só parâmetros "sujos" | `u4.q.k()/j()` |
| Rótulo da camada | `"WIFI"` | `u4.q.b()` |

## 2. Frame de comando (Família A — magic `55 AA FF 00`)

Família dominante (classe base `t0`/`z0`, probes de scanline bruto).

```
offset  campo
0..3    magic         = 55 AA FF 00
4       length        = tamanho total do frame (0x10=16 ou 0x18=24)
5       checksum      = (0 - Σ(bytes, com [5]=0)) & 0xFF     # complemento de 2, 8-bit
6       opcode
7       subtype/reserv= 00
8..     payload (valor & 0xFF), zero-pad até length
```

Propriedade de verificação: **Σ(frame) mod 256 == 0**.

### Opcodes confirmados (estrutura) / rótulo inferido

| Opcode | Len | Método | Payload | Rótulo provável |
|---|---|---|---|---|
| `0x81` | 16 | `P()` | valor em [8] | parâmetro primário `G` — ganho/TGC-base *(inferido)* |
| `0x82` | 16 | `K()` | valor `W` | parâmetro *(inferido)* |
| `0x84` | 16 | `L()` | 0/1 `S` | booleano — harmônica/THI ou needle-enhance *(inferido)* |
| `0x85` | 16 | `N()` | valor `R` | parâmetro *(inferido)* |
| `0xF2` | 16 | `O()` | 0/1 `V` | booleano *(inferido)* |
| `0x00` | 24 | `M()` | ver abaixo | **run/freeze/cine** |

Frame `M()` (len 24): `[14]=nframes`, `[15]=freeze(0/1)`, `[16]=1`, `[17]=E`, `[18]=1`, `[19]=F&3`.
Governa quantos frames capturar e o estado de congelamento.

> O mapeamento JSON→setter existe em `u4/v0` (Família B): `gain→z()`, `harmonic→toggle`,
> `dr→o0()`, `enhance→p0()`, `focus→s0()`. Esses nomes de método cruzam com os opcodes
> acima — é exatamente o cruzamento que o PCAP vai fechar.

## 3. Outras famílias (estrutura detectada, não implementada)

| Família | Magic | Classe | Observação |
|---|---|---|---|
| B | `5A A5 00 00` | `u4/v0` | provável geração MJPEG; mapeia o ExamJsons completo |
| C | `5F F5 00 00` | `u4/h` | variante; também usa blocos `55 AA FF 00` len 0x18 |

Imagem nessas famílias: **MJPEG** (decodificador JPEG em software em `u4/i`, `r4/q1`).

## 4. Fluxo de entrada (Família A)

`u4.q.a(byte[])` recebe pacotes reassemblados por `r`:

- **Status/linha** (`len ≥ 525` e `byte[8]==0xFF`): payload de 512 B em `[12..524]` →
  `driver.a()`. Parseia flags (ex. `[10]&3` = Doppler/cor ativo, `[11]&0x7F`, `[12]`).
- **Frame B completo** (`len ≥ 1050`, tipicamente **67725 B** = 129×525): 128 linhas úteis,
  cada linha = 13 B header + **512 amostras** 8-bit → imagem **128×512** → `driver.b()`.

Stride de linha = **525**; dados por linha = **512**; linhas = **128**.

## 5. Mapa mental do pipeline

```
[probe AP :52001]
   │  (TCP bidirecional, 1 socket)
   ├─► RX: status 512B  ──► driver.a()  (flags: Doppler on, escala…)
   ├─► RX: frame 128×512 ─► driver.b()  ──► Bitmap ──► sua IA (overlay/medidas)
   └─◄ TX: a cada 50 ms, batch de frames 55AAFF00 só dos parâmetros alterados
            (ganho, harmônica, run/freeze…) com checksum de complemento de 2
```

## 6. Lacunas a fechar no hardware (PCAP)

1. Rótulo exato de cada opcode (`0x81/0x82/0x85`) vs parâmetro clínico (ganho, dr, foco, freq).
2. Handshake inicial / autenticação do AP (se houver) e SSID/senha padrão do probe.
3. Família de protocolo do *seu* modelo (A raw vs B/C MJPEG) e resolução real do frame.
4. Fator de calibração **pixel→cm** (necessário p/ VTI, TAPSE, diâmetros) — vem do status/escala.
5. Faixas válidas por opcode (clamp do firmware) e se frequência/PRF alteram emissão.

## 7. Nota de segurança acústica

`gain`, `dr`, `enhance`, `focus` são *receive/display-side* — não alteram emissão. O teto de
saída acústica (MI/TI) é do firmware do probe, não desses parâmetros; o app não o excede e o
harness também não deve tentar. Mantenha o laço de otimização dentro do envelope do app.
