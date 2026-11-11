const d = require('docx');
const {Document, Packer, Paragraph, TextRun, HeadingLevel, Table, TableRow, TableCell,
       WidthType, BorderStyle, AlignmentType, PageBreak, ShadingType} = d;
const fs = require('fs');

const FONT = "Times New Roman";
const ACCENT = "1F4E79";
const LINE = "BFBFBF";

// ---- helpers ----
function p(text, opts={}) {
  return new Paragraph({
    spacing: {after: opts.after ?? 120, before: opts.before ?? 0, line: 276},
    alignment: opts.align,
    children: (Array.isArray(text)? text : [new TextRun({text, font: FONT, size: opts.size ?? 22,
       bold: opts.bold, italics: opts.italics, color: opts.color})])
  });
}
function h1(text){ return new Paragraph({heading: HeadingLevel.HEADING_1, children:[new TextRun({text, font:FONT})]}); }
function h2(text){ return new Paragraph({heading: HeadingLevel.HEADING_2, children:[new TextRun({text, font:FONT})]}); }
function bullet(text, lvl=0){
  return new Paragraph({ bullet:{level:lvl}, spacing:{after:80, line:264},
    children:[new TextRun({text, font:FONT, size:22})]});
}
function mono(text){ return new TextRun({text, font:"Consolas", size:19}); }
function cell(text, {w, bold, head, align}={}) {
  return new TableCell({
    width: {size:w, type:WidthType.DXA},
    shading: head? {type:ShadingType.CLEAR, fill:"E7EEF6", color:"auto"} : undefined,
    margins:{top:60,bottom:60,left:90,right:90},
    children:[new Paragraph({alignment:align, spacing:{after:0,line:252},
      children:[new TextRun({text, font:FONT, size:20, bold:bold||head})]})]
  });
}
function table(headers, rows, widths) {
  const total = widths.reduce((a,b)=>a+b,0);
  const mk = (arr, head)=> new TableRow({children: arr.map((t,i)=>cell(t,{w:widths[i],head}))});
  return new Table({
    width:{size:total,type:WidthType.DXA}, columnWidths:widths,
    borders: ["top","bottom","left","right","insideHorizontal","insideVertical"].reduce((o,k)=>{
      o[k]={style:BorderStyle.SINGLE,size:4,color:LINE}; return o;},{}),
    rows:[mk(headers,true), ...rows.map(r=>mk(r,false))]
  });
}
function rule(){ return new Paragraph({spacing:{after:120,before:40},
  border:{bottom:{style:BorderStyle.SINGLE,size:6,color:ACCENT,space:1}},children:[]}); }

const children = [];

// ===== CAPA =====
children.push(new Paragraph({spacing:{before:1800,after:0},alignment:AlignmentType.CENTER,
  children:[new TextRun({text:"PROJETO SmartUSG-AI",font:FONT,size:48,bold:true,color:ACCENT})]}));
children.push(new Paragraph({alignment:AlignmentType.CENTER,spacing:{after:80},
  children:[new TextRun({text:"Dossiê Técnico de Engenharia Reversa e Plataforma POCUS",font:FONT,size:28})]}));
children.push(new Paragraph({alignment:AlignmentType.CENTER,spacing:{after:600},
  children:[new TextRun({text:"Transdutor Wi-Fi EagleView (Sonostar / Sonoptek)",font:FONT,size:24,italics:true})]}));
children.push(new Paragraph({alignment:AlignmentType.CENTER,spacing:{after:40},
  children:[new TextRun({text:"Dr. Matheus de Freitas Silva — Araguari, MG",font:FONT,size:22})]}));
children.push(new Paragraph({alignment:AlignmentType.CENTER,
  children:[new TextRun({text:"Versão 1.0 — novembro de 2026",font:FONT,size:20,color:"666666"})]}));
children.push(new Paragraph({children:[new PageBreak()]}));

// ===== 1. SUMÁRIO EXECUTIVO =====
children.push(h1("1. Sumário executivo"));
children.push(p("A partir de um APK fechado (com.sonostar.SmartUSG), este projeto reconstruiu integralmente a cadeia de aquisição de um ultrassom portátil Wi-Fi EagleView e construiu sobre ela uma plataforma POCUS assistida, com calibração validada contra a fonte primária (a fórmula geométrica do próprio fabricante) e três módulos clínicos funcionais."));
children.push(p([new TextRun({text:"Resultado central: ",font:FONT,size:22,bold:true}),
  new TextRun({text:"um ecógrafo definido por software. A diferença entre medir carótida, VCI ou coração deixou de ser código ou calibração — passou a ser apenas para onde a sonda é apontada. Isso foi alcançado por engenharia reversa estática mais seis sessões de captura, sem alterar o firmware.",font:FONT,size:22})]));
children.push(h2("Marcos atingidos"));
[
 "Protocolo Wi-Fi decodificado e validado (imagem + controle + Doppler).",
 "Calibração geométrica recuperada da fórmula oficial e confirmada fisicamente (água).",
 "Reconstrução de imagem (scan conversion) nos três modos do probe.",
 "Plataforma interativa (engine) com medição ancorada, modo-M, DICOM e coleta de dataset.",
 "Módulos clínicos operando em anatomia real: Acesso Central, VCI e Cardíaco."
].forEach(t=>children.push(bullet(t)));

// ===== 2. PROTOCOLO =====
children.push(h1("2. Protocolo de comunicação Wi-Fi"));
children.push(p("O transdutor é um ponto de acesso Wi-Fi; o aplicativo lê o SSID ao qual o celular já está conectado e dirige-se ao gateway correspondente. Toda a comunicação é local (LAN), sem uplink de internet."));
children.push(table(
 ["Parâmetro","Valor"],
 [["Meio","Wi-Fi; o probe é o Access Point"],
  ["Gateway","190.166.x.1 / 190.188.1.1 / 192.168.1.1 (por modelo)"],
  ["Canal de imagem","TCP porta 5002"],
  ["Canal de controle","TCP porta 5003 (bidirecional, pump ~100 ms)"],
  ["Frame de imagem","160 linhas × 512 amostras, ~10 fps"],
  ["Linha","525 bytes = 13 cabeçalho + 512 amostras (8 bits)"]],
 [2600, 6200]));
children.push(p([new TextRun({text:"Frame de comando (Família A). ",font:FONT,size:22,bold:true}),
  new TextRun({text:"Estrutura: ",font:FONT,size:22}), mono("55 AA FF 00 | LEN | CKSUM | OP | 00 | payload"),
  new TextRun({text:". O checksum (byte 5) é o complemento de 2 de 8 bits — a soma de todo o frame é ≡ 0 (mod 256).",font:FONT,size:22})],{before:120}));
children.push(p([new TextRun({text:"Controle de Doppler. ",font:FONT,size:22,bold:true}),
  new TextRun({text:"Codificado no byte[2] do frame de 4 bytes 5A A5: bit 0x08 = Color, bit 0x04 = PW (somado ao Color), bit 0x80 = live (limpo = freeze).",font:FONT,size:22})]));
children.push(p([new TextRun({text:"Limite honesto. ",font:FONT,size:22,bold:true,italics:true}),
  new TextRun({text:"O stream de imagem carrega apenas a envoltória B-mode em todas as fases; não há linhas de velocidade ou espectro. Color e PW são renderizados pelo app, não transmitidos prontos — para obtê-los no pipeline é preciso computá-los (via a lib nativa vessel_flow), não decodificá-los.",font:FONT,size:22,italics:true})]));

// ===== 3. CALIBRAÇÃO =====
children.push(h1("3. Calibração geométrica (fonte primária)"));
children.push(p("A calibração do fabricante não é uma tabela estática, mas uma fórmula aplicada a constantes que o próprio probe reporta no handshake (frames 58 85 / 59 95). Em u4.i1, com A = 100000:"));
children.push(p([mono("R = 780000 · B[i] / A      (raio de curvatura, mm)")],{align:AlignmentType.CENTER}));
children.push(p([mono("FOV = θ · 180/π  (graus)     axial = profundidade / 512")],{align:AlignmentType.CENTER,after:160}));
children.push(p([new TextRun({text:"Validação cruzada. ",font:FONT,size:22,bold:true}),
  new TextRun({text:"A fórmula aplicada ao handshake deve reproduzir o raio medido fisicamente na água — e reproduz (convexo R≈40 mm; cardíaco R≈18 mm). Duas fontes independentes (binário + medição em fantoma de água) convergem para o mesmo valor.",font:FONT,size:22})]));
children.push(table(
 ["Modo","Geometria","Profundidade","Resolução axial"],
 [["Linear / vascular","retangular","4 cm","0,078 mm/amostra"],
  ["Convexo / abdome","setor, R≈40 mm, FOV≈60°","16 cm","0,312 mm/amostra"],
  ["Cardíaco / setor","setor virtual, R≈18 mm, FOV≈85°","12 cm","0,234 mm/amostra"]],
 [2600,3200,1500,1900]));
children.push(p([new TextRun({text:"A profundidade é sempre uma escolha de runtime do operador — mesmo o fabricante a lê do probe. A única variável não estática da calibração é, portanto, lida da própria captura.",font:FONT,size:22,italics:true})],{before:100}));

// ===== 4. ARQUITETURA =====
children.push(h1("4. Arquitetura da plataforma (engine)"));
children.push(p("O motor é agnóstico a órgão. Cada exame é um módulo que fornece apenas três peças: a geometria (modo do probe), a primitiva de medição e a regra clínica."));
children.push(h2("Toolkit de primitivas"));
children.push(table(
 ["Primitiva","Como","Desbloqueia"],
 [["ROI ancorada (área/Ø)","operador toca; region-growing limitado por parede","vaso, bexiga, VCI, cisto, aorta"],
  ["Caliper (distância)","dois toques; distância em mm","derrame, IMT, dimensões"],
  ["Modo-M do cine","coluna no tempo → movimento","TAPSE, colapsabilidade VCI, pulmão, FC"],
  ["Traço/Teichholz","diâmetros do VE → volumes","FEVE, FS"]],
 [2700,3600,2700]));
children.push(p([new TextRun({text:"Dois trilhos de dados. ",font:FONT,size:22,bold:true}),
  new TextRun({text:"O pcap dá controle de aquisição ao vivo (orientação, otimização, VCI e acesso em tempo real); o vídeo exportado do app traz a imagem já calibrada pela régua impressa, ideal para medição retrospectiva do cineloop. Ambos coexistem no engine.",font:FONT,size:22})]));

// ===== 5. METODOLOGIA DE MEDIÇÃO =====
children.push(h1("5. Metodologia de medição e fórmulas"));
children.push(h2("5.1 Acesso venoso central"));
children.push(p("Medição ancorada do lúmen em eixo curto → diâmetro equivalente e profundidade da agulha. Discriminação clínica veia × artéria pela compressibilidade (a veia colaba) e pulsatilidade."));
children.push(h2("5.2 Veia cava inferior (volemia)"));
children.push(p([new TextRun({text:"Índice de colapsabilidade por modo-M: ",font:FONT,size:22}),
  mono("CI = (D_máx − D_mín) / D_máx × 100")]));
children.push(p("CI > 50% sugere PVC baixa / hipovolemia; CI < 50% com VCI dilatada sugere PVC elevada."));
children.push(h2("5.3 Cardíaco"));
children.push(p([new TextRun({text:"TAPSE: ",font:FONT,size:22,bold:true}),
  new TextRun({text:"excursão sistólica do anel tricúspide lateral por modo-M; corte em 17 mm (abaixo = disfunção sistólica do VD).",font:FONT,size:22})]));
children.push(p([new TextRun({text:"FEVE por Teichholz (do app): ",font:FONT,size:22,bold:true}),
  mono("V = 7·D³/(2,4+D)"), new TextRun({text:"   ;   FEVE = (V_d − V_s)/V_d × 100",font:FONT,size:22})]));
children.push(p([new TextRun({text:"Limitação registrada: ",font:FONT,size:22,italics:true,bold:true}),
  new TextRun({text:"Teichholz assume geometria elipsoide simétrica e distorce em VE remodelado ou com alteração segmentar; nesses casos, Simpson biplano (ASE/EACVI) é preferível. O engine entrega o número que o aparelho entregaria; a leitura crítica é do operador.",font:FONT,size:22,italics:true})]));
children.push(h2("5.4 IMT — não mensurável neste setup"));
children.push(p("A espessura íntima-média normal (~0,6 mm) exige resolver duas interfaces separadas por essa distância. A resolução axial real (largura do pulso, ~0,3–0,5 mm) é pior que o espaçamento de amostragem; sem eixo longo perpendicular, zoom e foco na parede distal, a dupla linha borra. Medir IMT neste setup seria intervenção de baixo valor."));

// ===== 6. LIMITES E PHI =====
children.push(h1("6. Segurança, PHI e limites"));
[["Saída acústica","MI 0,6 / TIS 0,1 observados — dentro do envelope. Parâmetros de ganho/DR/realce são receive-side e não alteram emissão; o teto é imposto pelo firmware."],
 ["PHI","Vídeos clínicos têm nome do paciente queimado na tela. O ingestor recorta o setor e descarta a faixa de overlay; nenhum dado identificável entra no engine ou em artefatos. Recomenda-se anonimizar na origem."],
 ["Detecção automática","A proposta heurística de ROI foi refutada por medição (8% de acerto). Detecção autônoma confiável (feature 1) exige modelo treinado em dataset anotado — que a ferramenta agora coleta a cada medição."],
 ["Regulatório","Ao sair da bancada para uso clínico, aplica-se IEC 62304, IEC 60601-2-37 e registro ANVISA do conjunto (software as a medical device)."]]
 .forEach(([k,v])=>{ children.push(p([new TextRun({text:k+". ",font:FONT,size:22,bold:true}), new TextRun({text:v,font:FONT,size:22})])); });

// ===== 7. ROADMAP =====
children.push(h1("7. Roadmap"));
children.push(p("A fronteira não é o órgão, é a primitiva. Novos exames são novas perguntas sobre primitivas já prontas."));
children.push(table(
 ["Frente","Primitiva","Status"],
 [["Aorta / bexiga","ROI ancorada","instanciar"],
  ["eFAST (derrames)","caliper","instanciar"],
  ["Cine DICOM multiframe","—","evolução do exportador"],
  ["Feature 1 autônoma","modelo treinado","depende do dataset coletado"],
  ["Doppler computado (VTI/VExUS)","vessel_flow sobre frames","fronteira técnica"]],
 [3000,3200,2800]));

children.push(rule());
children.push(p([new TextRun({text:"Pearl de encerramento. ",font:FONT,size:22,bold:true,italics:true}),
  new TextRun({text:"A inteligência de um sistema de imagem médica não está no algoritmo, está nos dados rotulados. A fundação de aquisição, calibração e medição está construída e validada na fonte primária; o próximo salto é de dados, não de descoberta.",font:FONT,size:22,italics:true})]));

// ===== DOC =====
const doc = new Document({
  styles:{ default:{
    document:{run:{font:FONT,size:22}},
    heading1:{run:{font:FONT,size:30,bold:true,color:ACCENT},
      paragraph:{spacing:{before:300,after:140},keepNext:true,
        border:{bottom:{style:BorderStyle.SINGLE,size:4,color:LINE,space:2}}}},
    heading2:{run:{font:FONT,size:25,bold:true,color:"2E2E2E"},
      paragraph:{spacing:{before:200,after:100},keepNext:true}},
  }},
  sections:[{
    properties:{page:{size:{width:12240,height:15840},margin:{top:1200,bottom:1200,left:1300,right:1300}}},
    children
  }]
});
Packer.toBuffer(doc).then(b=>{ fs.writeFileSync("Dossie_SmartUSG_AI.docx", b);
  console.log("ok", b.length, "bytes"); });
