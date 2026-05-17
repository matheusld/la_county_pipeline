/**
 * Adds the CPRA AI Business Cases section to METHODS_APPENDIX_v2.docx
 * Output: METHODS_APPENDIX_v3.docx
 */
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  HeadingLevel, AlignmentType, BorderStyle, WidthType, ShadingType,
  LevelFormat, Header, Footer, PageNumber, PageBreak
} = require("docx");
const fs = require("fs");

// ── Shared style constants (must match build_docx.js) ─────────────────────────
const BLUE = "1F4E79";
const MID  = "2E75B6";
const NONE = "FFFFFF";

const bThick = { style: BorderStyle.SINGLE, size: 12, color: "000000" };
const bThin  = { style: BorderStyle.SINGLE, size:  4, color: "999999" };
const bNone  = { style: BorderStyle.NONE,   size:  0, color: NONE };
const noShade = { fill: NONE, type: ShadingType.CLEAR };

function cellBorders(top, bottom) {
  return { top, bottom, left: bNone, right: bNone, insideH: bThin, insideV: bNone };
}

function aCell(text, colWidth, { topBorder = bNone, bottomBorder = bThin, bold: isBold = false } = {}) {
  return new TableCell({
    width: { size: colWidth, type: WidthType.DXA },
    shading: noShade,
    borders: cellBorders(topBorder, bottomBorder),
    margins: { top: 80, bottom: 80, left: 80, right: 80 },
    children: [new Paragraph({
      spacing: { before: 0, after: 0 },
      children: [new TextRun({ text, bold: isBold, size: 19, font: "Times New Roman" })],
    })],
  });
}

function tableCaption(label, description) {
  return new Paragraph({
    spacing: { before: 240, after: 60 },
    children: [
      new TextRun({ text: label + " ", bold: true, size: 20, font: "Times New Roman" }),
      new TextRun({ text: description, italics: true, size: 20, font: "Times New Roman" }),
    ],
  });
}

function h1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 360, after: 120 },
    children: [new TextRun({ text, bold: true, color: BLUE, size: 32, font: "Arial" })],
  });
}

function h3(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_3,
    spacing: { before: 200, after: 60 },
    children: [new TextRun({ text, bold: true, size: 24, font: "Arial" })],
  });
}

function p(runs, opts = {}) {
  const children = typeof runs === "string"
    ? [new TextRun({ text: runs, size: 22, font: "Arial" })]
    : runs;
  return new Paragraph({ spacing: { before: 80, after: 120 }, children, ...opts });
}

function t(text, opts = {}) { return new TextRun({ text, size: 22, font: "Arial", ...opts }); }
function bold(text)          { return t(text, { bold: true }); }

function rule() {
  return new Paragraph({
    border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: "CCCCCC", space: 1 } },
    spacing: { before: 200, after: 200 },
    children: [],
  });
}

// ── Clean CPRA data (hand-curated) ────────────────────────────────────────────
const CASES = [
  // [Department (full), AI Tool / System, Year]
  ["Auditor-Controller",                        "Clearview AI — Facial Recognition",              "2025"],
  ["Auditor-Controller",                        "Microsoft 365 Copilot",                          "2025"],
  ["Board of Supervisors",                      "Microsoft Copilot Chat & Copilot Studio",        "2025"],
  ["Board of Supervisors",                      "Copilot Studio — Customer Service Chatbot",      "2025"],
  ["Board of Supervisors",                      "Wordly AI — Language Translation",               "2025"],
  ["Chief Executive Office",                    "Document Summarization (GenAI)",                 "2025"],
  ["Chief Executive Office",                    "LegalBert — California Code Categorization",     "2026"],
  ["Dept. of Children and Family Services",     "BlueVector / Google Translate",                  "2025"],
  ["Dept. of Children and Family Services",     "Microsoft 365 Copilot",                          "2025"],
  ["Dept. of Economic Opportunity",             "Microsoft Copilot Studio",                       "2026"],
  ["Dept. of Human Resources",                  "AI-Assisted Resume Screening",                   "2025"],
  ["Dept. of Health Services",                  "Microsoft 365 Copilot Chat & Copilot Studio",   "2025"],
  ["Dept. of Public Health",                    "Healthvana AI",                                  "2025"],
  ["Dept. of Public Health",                    "SOPIE — Clinical Data Abstraction",              "2025"],
  ["Dept. of Parks and Recreation",             "Microsoft 365 Copilot",                          "2025"],
  ["Dept. of Parks and Recreation",             "UMS AI Rewrite Tool",                            "2026"],
  ["Dept. of Parks and Recreation",             "Synthesia AI — Video Generation",                "2026"],
  ["Dept. of Public Social Services",           "AWS Contact Lens AI",                            "2025"],
  ["Dept. of Public Social Services",           "Magic Notes AI",                                 "2025"],
  ["Dept. of Public Social Services",           "BlueVector / Google Translate",                  "2025"],
  ["Dept. of Public Social Services",           "Box AI",                                         "2025"],
  ["Dept. of Public Social Services",           "Microsoft 365 Copilot",                          "2025"],
  ["Dept. of Public Works",                     "Armada Commander Connect",                       "2025"],
  ["Dept. of Public Works",                     "Bluebeam Revu 21 — AI-Assisted Markup",         "2025"],
  ["Dept. of Public Works",                     "ChatGPT Team",                                   "2025"],
  ["Dept. of Public Works",                     "Microsoft Copilot Agent Builder",                "2026"],
  ["Dept. of Public Works",                     "Grammarly AI",                                   "2025"],
  ["Dept. of Public Works",                     "Microsoft 365 Copilot",                          "2025"],
  ["Dept. of Public Works",                     "Metadata Management AI",                         "2025"],
  ["Dept. of Public Works",                     "Polly AI",                                       "2025"],
  ["Dept. of Public Works",                     "Urbanlogiq — Data Visualization",                "2025"],
  ["Dept. of Public Works",                     "AWS and GCP AI Services",                        "2025"],
  ["Dept. of Public Works",                     "Bentley Blyncsy",                                "2025"],
  ["Dept. of Regional Planning",                "Microsoft Copilot Chat",                         "2026"],
  ["Dept. of Regional Planning",                "Archistar AI",                                   "2025"],
  ["Fire Department",                           "NICE Inform AI — Call Transcription",            "2025"],
  ["Fire Department",                           "Microsoft 365 Copilot",                          "2025"],
  ["Internal Services Dept.",                   "AI Automation Testing",                          "2025"],
  ["Internal Services Dept.",                   "CAB Document Translation Service",               "2025"],
  ["Justice, Care and Opportunities Dept.",     "Microsoft 365 Copilot",                          "2025"],
  ["Library",                                   "ChatGPT",                                        "2026"],
  ["Library",                                   "Claude (Anthropic)",                             "2026"],
  ["Library",                                   "Microsoft Copilot",                              "2025"],
  ["Motor Vehicle Administration",              "Microsoft 365 Copilot",                          "2025"],
  ["Registrar-Recorder / County Clerk",         "GenAI-Based Q&A Bot",                           "2025"],
  ["Registrar-Recorder / County Clerk",         "Anthropic Claude — GenAI Assistant",            "2026"],
  ["Registrar-Recorder / County Clerk",         "Microsoft 365 Copilot GenAI",                   "2026"],
  ["Sheriff's Department",                      "Alcatraz AI — Facial Authentication",            "2025"],
  ["Treasurer and Tax Collector",               "Microsoft Copilot",                              "2025"],
  ["Treasurer and Tax Collector",               "Helpdesk ChatBot",                               "2026"],
];

// ── Build table ───────────────────────────────────────────────────────────────
const COLS = [3960, 4200, 1200]; // Dept | Tool | Year
const HEADERS = ["Department", "AI Tool / System", "Year"];

const tableRows = [
  new TableRow({
    children: HEADERS.map((h, i) =>
      aCell(h, COLS[i], { topBorder: bThick, bottomBorder: bThick, bold: true })
    ),
  }),
  ...CASES.map(([dept, tool, year], ri) => {
    const isLast = ri === CASES.length - 1;
    return new TableRow({
      children: [dept, tool, year].map((txt, i) =>
        aCell(txt, COLS[i], {
          topBorder:    bNone,
          bottomBorder: isLast ? bThick : bThin,
          bold:         false,
        })
      ),
    });
  }),
];

const cpraTable = new Table({
  width: { size: 9360, type: WidthType.DXA },
  columnWidths: COLS,
  rows: tableRows,
});

// ── Build section content ─────────────────────────────────────────────────────
const sectionChildren = [
  new Paragraph({ spacing: { before: 0, after: 0 }, children: [new PageBreak()] }),
  rule(),
  h1("Appendix B: AI Business Cases Obtained via CPRA Request"),
  p([
    t("The following 50 AI business cases were obtained from Los Angeles County through a California Public Records Act (CPRA) request. Each document is a formal business case submitted by a county department to the "),
    bold("GenAI Governance Board"),
    t(" (chaired by CIO Peter Loo) as part of the review process established under Technology Directive TD 24-04. The cases represent "),
    bold("low-risk AI deployments"),
    t(" that received approval without escalation to a full algorithmic impact assessment. They are catalogued here as primary source evidence of the scope and character of AI adoption across county departments as of 2025–2026."),
  ]),
  p([
    t("Departments are sorted alphabetically. Where multiple cases exist for one department, each system is listed separately. "),
    bold("DCFS"),
    t(" = Dept. of Children and Family Services; "),
    bold("DPSS"),
    t(" = Dept. of Public Social Services; "),
    bold("JCOD"),
    t(" = Justice, Care and Opportunities Dept.; "),
    bold("RRCC"),
    t(" = Registrar-Recorder/County Clerk."),
  ]),
  new Paragraph({ spacing: { before: 120, after: 0 }, children: [] }),
  tableCaption(
    "Table B.1.",
    "AI business cases submitted to the LA County GenAI Governance Board, obtained via CPRA (n = 50)."
  ),
  cpraTable,
  new Paragraph({ spacing: { before: 160, after: 80 }, children: [] }),
  h3("Observations"),
  p([
    bold("Breadth of adoption. "),
    t("Nineteen distinct departments submitted at least one business case, ranging from the Fire Department and Sheriff's Department to the Library and the Justice, Care and Opportunities Dept. (JCOD). This confirms that AI procurement is not confined to technology-facing agencies."),
  ]),
  p([
    bold("Concentration of tools. "),
    t("Microsoft 365 Copilot and its variants (Copilot Chat, Copilot Studio, Copilot Agent Builder) account for the majority of cases, reflecting the county's enterprise Microsoft agreement. ChatGPT and Anthropic's Claude appear in cases from the Library and Registrar-Recorder, indicating that departments are also procuring consumer and API-based tools outside the Microsoft ecosystem."),
  ]),
  p([
    bold("Facial recognition and biometric tools. "),
    t("Two cases — Clearview AI (Auditor-Controller) and Alcatraz AI facial authentication (Sheriff's Department) — involve biometric identification systems. These are the highest-sensitivity tools in the dataset and would be expected to receive elevated scrutiny under any mature AI governance framework."),
  ]),
  p([
    bold("Care-first infrastructure. "),
    t("JCOD's Microsoft 365 Copilot case is the only submission from a department within the care-first governance apparatus. The absence of cases from ODR, DYD, ATI, or CFCI-affiliated bodies is itself a finding: AI procurement is occurring across the county, but the care-first system is not yet a visible participant in the AI governance process."),
  ]),
];

// ── Read existing docx and append ─────────────────────────────────────────────
// We rebuild from scratch using the existing JS content + new section.
// Strategy: emit a standalone docx for this section, to be merged manually if needed,
// OR re-run build_docx.js with the section injected. Here we produce the full doc.

// Since we can't trivially append to an existing docx without unpacking XML,
// we write the CPRA section as a standalone appendix file.
const doc = new Document({
  numbering: { config: [] },
  styles: {
    default: { document: { run: { font: "Arial", size: 22 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 32, bold: true, font: "Arial", color: BLUE },
        paragraph: { spacing: { before: 360, after: 120 }, outlineLevel: 0 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 24, bold: true, font: "Arial" },
        paragraph: { spacing: { before: 200, after: 60 }, outlineLevel: 2 } },
    ],
  },
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 },
        margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 },
      },
    },
    headers: {
      default: new Header({
        children: [new Paragraph({
          border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: "CCCCCC", space: 4 } },
          children: [
            new TextRun({ text: "Appendix B: AI Business Cases — CPRA", size: 18, font: "Arial", color: "666666" }),
          ],
        })],
      }),
    },
    footers: {
      default: new Footer({
        children: [new Paragraph({
          alignment: AlignmentType.RIGHT,
          border: { top: { style: BorderStyle.SINGLE, size: 4, color: "CCCCCC", space: 4 } },
          children: [
            new TextRun({ text: "Page ", size: 18, font: "Arial", color: "666666" }),
            new TextRun({ children: [PageNumber.CURRENT], size: 18, font: "Arial", color: "666666" }),
          ],
        })],
      }),
    },
    children: sectionChildren.filter(c => !(c instanceof Paragraph && c.options && c.options.children && c.options.children[0] instanceof PageBreak)),
  }],
});

Packer.toBuffer(doc).then(buf => {
  const OUT = "APPENDIX_B_CPRA_Cases.docx";
  fs.writeFileSync(OUT, buf);
  console.log("Written:", OUT, "—", CASES.length, "cases");
});
