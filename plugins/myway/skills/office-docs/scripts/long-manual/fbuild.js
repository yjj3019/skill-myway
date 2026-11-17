// fbuild.js — 2-pass TOC 빌드 엔진
// Pass1: TOC 없이 빌드 → soffice PDF 변환 → gen_toc.py로 페이지 추출
// Pass2: 정적 TOC(페이지번호 포함)를 맨 앞에 붙여 최종 docx 빌드
//
// 사용: node fbuild.js [출력파일명]
// 산출물과 중간 파일: $OUT_DIR. OUT_DIR 미지정 시 현재 디렉터리.
// 목차가 2페이지 이상이면 TOC_PAGES=<목차 페이지 수>로 지정한다(기본 1).

const fs = require("fs");
const path = require("path");
const { pathToFileURL } = require("url");
const { execFileSync } = require("child_process");
const {
  Document, Packer, Paragraph, TextRun, TabStopType, TabStopPosition, AlignmentType, Footer, PageNumber,
} = require("docx");
const m = require("./fmh");
const { outputPath, copyExclusive } = require("./output_safety");
const { TITLES, chapters } = require("./fcontent");

const OUT_DIR = process.env.OUT_DIR || process.cwd();
const TOC_PAGES = Number(process.env.TOC_PAGES || 1);
const SCRIPT_DIR = __dirname;
const COMMAND_TIMEOUT_MS = 120000;
const outName = process.argv[2] || "RHEL_운영매뉴얼.docx";
if (!Number.isSafeInteger(TOC_PAGES) || TOC_PAGES < 1) throw new Error("TOC_PAGES must be a positive integer");
const finalPath = outputPath(OUT_DIR, outName);

function sectionProps() {
  return { page: { size: { width: m.STYLE.page.size.width, height: m.STYLE.page.size.height }, margin: m.STYLE.page.margin } };
}

// TOC 단락: "제목 .......... 페이지" (탭 리더)
function tocEntry(title, page) {
  return new Paragraph({
    tabStops: [{ type: TabStopType.RIGHT, position: TabStopPosition.MAX, leader: "dot" }],
    spacing: { after: 80 },
    children: [
      new TextRun({ text: title, size: m.STYLE.size.body, font: m.STYLE.bodyFont, color: m.STYLE.color.text }),
      new TextRun({ text: `\t${page ?? "-"}`, size: m.STYLE.size.body, font: m.STYLE.bodyFont, color: m.STYLE.color.text }),
    ],
  });
}

function buildDoc(tocBlocks) {
  const children = [];
  if (tocBlocks) {
    children.push(new Paragraph({ children: [new TextRun({ text: "목차", bold: true, size: m.STYLE.size.h1, font: m.STYLE.bodyFont, color: m.STYLE.color.text })], spacing: { after: 240 } }));
    children.push(...tocBlocks, m.pageBreak());
  }
  children.push(...chapters());
  const footer = new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
    children: [new TextRun({ children: [PageNumber.CURRENT] })] })] });
  return new Document({ sections: [{ properties: sectionProps(), footers: { default: footer }, children }] });
}

async function save(doc, file) {
  const buf = await Packer.toBuffer(doc);
  fs.writeFileSync(file, buf, { flag: "wx" });
}

(async () => {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  // Keep intermediate files under the explicitly chosen output directory.
  const tmp = fs.mkdtempSync(path.join(OUT_DIR, ".rhelman-"));

  // Pass 1
  const p1docx = path.join(tmp, "pass1.docx");
  await save(buildDoc(null), p1docx);
  console.error("[1/4] Pass1 docx 빌드 완료");

  const profile = pathToFileURL(path.resolve(tmp, "lo-profile")).href;
  execFileSync("soffice", [`-env:UserInstallation=${profile}`, "--headless", "--convert-to", "pdf", "--outdir", tmp, p1docx], { stdio: "inherit", timeout: COMMAND_TIMEOUT_MS });
  const p1pdf = path.join(tmp, "pass1.pdf");
  console.error("[2/4] PDF 변환 완료");

  const titlesJson = path.join(tmp, "titles.json");
  const tocJson = path.join(tmp, "toc.json");
  fs.writeFileSync(titlesJson, JSON.stringify(TITLES, null, 2));
  execFileSync(process.env.PYTHON || "python3", [path.join(SCRIPT_DIR, "gen_toc.py"), p1pdf, titlesJson, tocJson], { stdio: "inherit", timeout: COMMAND_TIMEOUT_MS + 10000 });
  const toc = JSON.parse(fs.readFileSync(tocJson, "utf-8"));
  console.error("[3/4] toc.json 추출 완료");

  // Pass 2 (TOC가 차지하는 페이지만큼 본문이 밀리므로 TOC_PAGES 보정)
  const tocBlocks = toc.map((e) => tocEntry(e.title, e.page == null ? null : e.page + TOC_PAGES));
  const candidate = path.join(tmp, "candidate.docx");
  await save(buildDoc(tocBlocks), candidate);
  execFileSync("soffice", [`-env:UserInstallation=${profile}`, "--headless", "--convert-to", "pdf", "--outdir", tmp, candidate], { stdio: "inherit", timeout: COMMAND_TIMEOUT_MS });
  const finalToc = path.join(tmp, "final-toc.json");
  execFileSync(process.env.PYTHON || "python3", [path.join(SCRIPT_DIR, "gen_toc.py"), path.join(tmp, "candidate.pdf"), titlesJson, finalToc, "--skip-pages", String(TOC_PAGES)], { stdio: "inherit", timeout: COMMAND_TIMEOUT_MS + 10000 });
  const verified = JSON.parse(fs.readFileSync(finalToc, "utf-8"));
  if (verified.length !== toc.length || verified.some((item, i) => item.title !== toc[i].title || item.page !== toc[i].page + TOC_PAGES)) {
    throw new Error("final page locations differ from the table of contents");
  }
  copyExclusive(candidate, finalPath);
  console.error(`[4/4] 최종 빌드 완료 → ${finalPath}`);
})().catch((e) => { console.error("BUILD FAILED:", e); process.exit(1); });
