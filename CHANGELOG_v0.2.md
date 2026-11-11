# SmartUSG-AI v0.2 — Entrega de consolidação técnica (11/11/2026)

## Implementado nesta etapa

1. **Bloqueio fail-closed de comandos ambíguos**: opcodes 0x81, 0x82, 0x84, 0x85, 0xF2 e run/freeze não são enviados, inclusive com `allow_control=True`. O algoritmo de otimização permanece **offline**; `push()` lança uma exceção descritiva.
2. **Demultiplexação incremental de JPEG**: suporta fragmentação TCP, múltiplos frames em um recebimento e SOI/EOI divididos; limita buffering de JPEG incompleto. `framing=jpeg` padrão. Parser de linhas de 128x512 foi mantido como **`raw-fixed-experimental`**, pois não há validação da delimitação do stream. O parser bruto legado não é recomendado para medições.
3. **Geometria**: `cm_from_sample()` deixa de depender de variáveis inexistentes; corrige convenção de endpoints e valida entradas de scan conversion. Os presets continuam **estimativas nominais**, sem validação metrológica.
4. **Engine HTML**: exportações JSON e DICOM deixam de depender de `claude.use('downloads')`; funcionam por Blob/URL em navegador moderno. O gerador DICOM original não foi auditado conforme padrão IOD e segue experimental.
5. **Testes** em `tests/test_foundation.py` com protocolo, fragmentação, calibração, isolamento de controle e otimização.

## Pendências importantes

- Capturas de rede com comandos individuais, incluindo ACK/resposta e identificação do firmware, para resolver a incompatibilidade entre famílias 55AA (128 linhas) e 5FF5 (160 linhas).
- Identificar framing bruto a partir de fluxos reais antes de implementar reassembly de linhas.
- Phantom de ultrassom para medir erro de calibração axial/lateral em todos os modos/profundidades.
- Validar conformidade DICOM Secondary Capture e metadados com pydicom/dciodvfy e PACS.
- Reestruturar o HTML e ligar o pipeline ao Android; **nenhum APK foi produzido nesta etapa**.
- Qualificar métricas de qualidade contra avaliação especialista; não há IA treinada no ZIP.

## Executar

```bash
python -m pip install numpy
python -m unittest discover -s tests -v
python 01_aquisicao_protocolo/smartusg_wifi.py --host 190.166.8.1 --observe
```

Para testar somente a interface, abra `05_engine_web/pocus_engine.html` no navegador. As imagens preexistentes podem ser demonstrações; não inferir validação clínica a partir delas.

**Segurança**: Não usar medidas, controles ou exportações experimentais como base isolada para conduta clínica. O envio de comandos foi desabilitado intencionalmente, inclusive quando `--allow-control` é passado.
