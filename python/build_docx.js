const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  HeadingLevel, AlignmentType, BorderStyle, WidthType, ShadingType,
  LevelFormat, Header, Footer, PageNumber
} = require("docx");
const fs = require("fs");

const OUT = "METHODS_APPENDIX_v2.docx";

// ── Colours ───────────────────────────────────────────────────────────────────
const BLUE  = "1F4E79";
const LBLUE = "D6E4F0";
const GREY  = "F2F2F2";
const MID   = "2E75B6";
const NONE  = "FFFFFF";

// ── Academic table border helpers ─────────────────────────────────────────────
const bThick  = { style: BorderStyle.SINGLE, size: 12, color: "000000" };
const bThin   = { style: BorderStyle.SINGLE, size:  4, color: "999999" };
const bNone   = { style: BorderStyle.NONE,   size:  0, color: NONE };
const noShade = { fill: NONE, type: ShadingType.CLEAR };

// Borders for cells: horizontal rules only, no verticals
function cellBorders(top, bottom) {
  return { top, bottom, left: bNone, right: bNone, insideH: bThin, insideV: bNone };
}

// Academic table caption: "Table N." bold + italic description
function tableCaption(label, description) {
  return new Paragraph({
    spacing: { before: 240, after: 60 },
    children: [
      new TextRun({ text: label + " ", bold: true, size: 20, font: "Times New Roman" }),
      new TextRun({ text: description, italics: true, size: 20, font: "Times New Roman" }),
    ],
  });
}

// One academic table cell
function aCell(text, colWidth, { topBorder = bNone, bottomBorder = bThin, bold: isBold = false, shade = false } = {}) {
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

// Older helpers kept for non-table use
const cellBorder = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const borders = { top: cellBorder, bottom: cellBorder, left: cellBorder, right: cellBorder };
const noBorders = { top: bNone, bottom: bNone, left: bNone, right: bNone };

function h1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 360, after: 120 },
    children: [new TextRun({ text, bold: true, color: BLUE, size: 32, font: "Arial" })],
  });
}

function h2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 280, after: 80 },
    children: [new TextRun({ text, bold: true, color: MID, size: 26, font: "Arial" })],
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

function t(text, opts = {}) {
  return new TextRun({ text, size: 22, font: "Arial", ...opts });
}

function bold(text) { return t(text, { bold: true }); }

function bullet(runs, level = 0) {
  const children = typeof runs === "string"
    ? [new TextRun({ text: runs, size: 22, font: "Arial" })]
    : runs;
  return new Paragraph({
    numbering: { reference: "bullets", level },
    spacing: { before: 60, after: 60 },
    children,
  });
}

function stepHeader(num, title) {
  return new Paragraph({
    spacing: { before: 200, after: 60 },
    children: [
      new TextRun({ text: `Step ${num} — `, bold: true, size: 22, font: "Arial", color: MID }),
      new TextRun({ text: title, bold: true, size: 22, font: "Arial" }),
    ],
  });
}

function rule() {
  return new Paragraph({
    border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: "CCCCCC", space: 1 } },
    spacing: { before: 200, after: 200 },
    children: [],
  });
}


// ── Tier table (academic style) ───────────────────────────────────────────────
function tierTable() {
  const cols = [1600, 2600, 2960, 2200];
  const headers = ["Tier", "Composite score", "Meaning", "Count"];
  const rows = [
    ["Tier 1", "≥ 6.0, with anchor ≥ 5", "Cite in paper",      "65"],
    ["Tier 2", "≥ 3.5",                        "Background reading", "1,398"],
    ["Tier 3", "≥ 1.0",                        "Skim only",          "—"],
    ["Tier 4", "< 1.0",                             "Likely irrelevant",  "—"],
  ];
  return new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: cols,
    rows: [
      new TableRow({
        children: headers.map((h, i) => aCell(h, cols[i], { topBorder: bThick, bottomBorder: bThick, bold: true })),
      }),
      ...rows.map((row, ri) => new TableRow({
        children: row.map((txt, i) => aCell(txt, cols[i], {
          topBorder: bNone,
          bottomBorder: ri === rows.length - 1 ? bThick : bThin,
          bold: i === 0,
        })),
      })),
    ],
  });
}

// ── Scoring dimensions table (academic style) ─────────────────────────────────
function dimTable() {
  const cols = [2600, 5160, 1600];
  const headers = ["Dimension", "What it measures", "Weight"];
  const rows = [
    ["Care-first relevance",
     "Measure J, CFCI (Care First Community Investment), ODR (Office of Diversion and Reentry), DYD (Dept. of Youth Development), ATI (Alternatives to Incarceration), and related community-investment governance",
     "25%"],
    ["AI/tech governance relevance",
     "TD 24-04 (Technology Directive), GenAI Governance Board, ISD (Internal Services Dept.) procurement, algorithmic policy in county service delivery",
     "25%"],
    ["Intersection",
     "Does the document explicitly connect the two governance systems? (0 = neither mentioned; 10 = bridging them is the central subject)",
     "35%"],
    ["Evidentiary quality",
     "Named officials with title, dollar amounts, contract or motion numbers, verbatim policy language, specific meeting dates",
     "15%"],
  ];
  return new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: cols,
    rows: [
      new TableRow({
        children: headers.map((h, i) => aCell(h, cols[i], { topBorder: bThick, bottomBorder: bThick, bold: true })),
      }),
      ...rows.map((row, ri) => new TableRow({
        children: row.map((txt, i) => aCell(txt, cols[i], {
          topBorder: bNone,
          bottomBorder: ri === rows.length - 1 ? bThick : bThin,
          bold: i === 0,
        })),
      })),
    ],
  });
}

// ── IRR stats table (academic style) ─────────────────────────────────────────
function irrTable() {
  const cols = [5360, 2200, 1800];
  const headers = ["Measure", "Value", "Interpretation"];
  const rows = [
    ["Cohen’s κ (kappa) — tier agreement beyond chance", "0.10", "Slight"],
    ["ICC (intraclass correlation) — composite score consistency", "0.22", "Poor"],
    ["Docs assigned to the same tier by both models",               "46%",  "—"],
    ["Docs flagged as contested (composite gap > 3.0 points)",      "928",  "Human review needed"],
  ];
  return new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: cols,
    rows: [
      new TableRow({
        children: headers.map((h, i) => aCell(h, cols[i], { topBorder: bThick, bottomBorder: bThick, bold: true })),
      }),
      ...rows.map((row, ri) => new TableRow({
        children: row.map((txt, i) => aCell(txt, cols[i], {
          topBorder: bNone,
          bottomBorder: ri === rows.length - 1 ? bThick : bThin,
        })),
      })),
    ],
  });
}

// ── Document ──────────────────────────────────────────────────────────────────
const doc = new Document({
  numbering: {
    config: [{
      reference: "bullets",
      levels: [{
        level: 0, format: LevelFormat.BULLET, text: "•",
        alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 720, hanging: 360 } } },
      }],
    }],
  },
  styles: {
    default: { document: { run: { font: "Arial", size: 22 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 32, bold: true, font: "Arial", color: BLUE },
        paragraph: { spacing: { before: 360, after: 120 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 26, bold: true, font: "Arial", color: MID },
        paragraph: { spacing: { before: 280, after: 80 }, outlineLevel: 1 } },
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
            new TextRun({ text: "Appendix: Document Screening Methodology", size: 18, font: "Arial", color: "666666" }),
            new TextRun({ text: "  —  UC Berkeley Goldman School of Public Policy, MPP Capstone 2026", size: 18, font: "Arial", color: "999999" }),
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
    children: [

      // ── Cover block ──────────────────────────────────────────────────────────
      new Paragraph({
        spacing: { before: 0, after: 60 },
        children: [new TextRun({ text: "APPENDIX", size: 20, font: "Arial", color: "999999", allCaps: true })],
      }),
      new Paragraph({
        spacing: { before: 0, after: 120 },
        children: [new TextRun({ text: "Document Screening Methodology", bold: true, size: 40, font: "Arial", color: BLUE })],
      }),
      new Paragraph({
        spacing: { before: 0, after: 60 },
        children: [new TextRun({ text: "Bridging Care-First and AI Governance in LA County", size: 24, font: "Arial", color: "444444", italics: true })],
      }),
      new Paragraph({
        spacing: { before: 0, after: 60 },
        children: [new TextRun({ text: "Prepared for Derek Steele, Social Justice Learning Institute (SJLI)", size: 20, font: "Arial", color: "666666" })],
      }),
      new Paragraph({
        spacing: { before: 0, after: 360 },
        children: [new TextRun({ text: "UC Berkeley Goldman School of Public Policy — MPP Capstone, Spring 2026", size: 20, font: "Arial", color: "666666" })],
      }),

      rule(),

      // ── The Problem ──────────────────────────────────────────────────────────
      h1("The Problem"),
      p([
        t("LA County government produces thousands of public records — Board of Supervisors agendas, motion letters, departmental reports, contracts, budget documents, and meeting transcripts. Reviewing all of them by hand to find those relevant to this research question is not feasible. This pipeline automates the first pass."),
      ]),
      p([
        t("The goal is not to replace human judgment. It is to reduce "),
        bold("9,000+ documents"),
        t(" to a ranked shortlist that a researcher can read carefully in the time available for qualitative analysis."),
      ]),

      rule(),

      // ── How It Works ─────────────────────────────────────────────────────────
      h1("How It Works"),

      // Step 1
      stepHeader(1, "Text Extraction"),
      p([
        t("Each document is converted to plain text. PDF files are processed with a text-extraction library. Scanned or image-based PDFs — where the text exists only as a photograph of a page — fall back to optical character recognition (OCR), software that attempts to read the image. Documents that cannot be read at all are flagged but kept in the record so nothing is silently lost."),
      ]),

      // Step 2
      stepHeader(2, "Deduplication"),
      p([
        t("Near-identical documents are identified by comparing overlapping word patterns between every pair of documents. Documents judged more than 85% similar to an earlier document are marked as duplicates and skipped in later steps, saving cost and avoiding double-counting."),
      ]),

      // Step 3
      stepHeader(3, "Independent Scoring by Two AI Models"),
      p([
        t("Every non-duplicate document is submitted to two artificial intelligence (AI) language models — "),
        bold("GPT-5.4-mini"),
        t(" (developed by OpenAI) and "),
        bold("Claude Haiku"),
        t(" (developed by Anthropic) — operating independently with identical written instructions. Neither model can see the other’s output. Each model reads the document text and scores it on four dimensions from 0 to 10:"),
      ]),
      tableCaption("Table A.1.", "Scoring dimensions and composite weights."),
      dimTable(),
      new Paragraph({ spacing: { before: 160, after: 80 }, children: [] }),
      p([
        t("A single composite score is then calculated "),
        bold("locally by the pipeline software"),
        t(" — not by the AI — using the fixed weighted formula shown in the table above. Intersection receives the highest weight (35%) because documents that explicitly link the two governance systems are the primary research target. The AI models return only the four sub-scores and a one-sentence rationale; they never produce the composite."),
      ]),
      p([t("Claude Haiku scored 7,425 documents; GPT-5.4-mini scored 7,265. The two runs shared 6,988 documents identified by a unique digital fingerprint (SHA-256 hash of file content).")]),

      // Step 4
      stepHeader(4, "Cross-Model Comparison and Score Resolution"),
      p([
        t("The two models’ scores are compared using standard statistical measures of agreement between two independent raters — a practice called inter-rater reliability (IRR) assessment. The results showed low agreement:"),
      ]),
      tableCaption("Table A.2.", "Inter-rater reliability statistics across 6,988 shared documents."),
      irrTable(),
      new Paragraph({ spacing: { before: 160, after: 80 }, children: [] }),
      p([
        t("Cohen’s κ (kappa) measures how much two raters agree beyond what chance alone would predict; values below 0.20 are considered “slight.” The intraclass correlation coefficient (ICC) measures consistency on a continuous scale; values below 0.50 are considered “poor.” Both measures landing this low means the two models are reading the same documents differently, not randomly."),
      ]),
      p([
        t("Examining the scores dimension by dimension revealed the disagreement is "),
        bold("systematic, not random"),
        t(": GPT-mini scored care-first governance and evidentiary quality higher on average (+1.2 and +1.6 points respectively); Claude Haiku scored AI governance higher (+1.0 points). Both models also produced a small number of hallucination events — assigning near-maximal scores to documents with no substantive relevance to the research question."),
      ]),
      p([
        t("To resolve this, "),
        bold("all four sub-scores were averaged"),
        t(" across the two models for each shared document. A logical correction was also applied: the intersection score was capped at two points above the lower of the two primary dimension scores. The reasoning: a document cannot meaningfully bridge two governance systems if it substantively addresses neither. For example, if a document scores 1 on care-first and 0 on AI governance, its intersection score cannot exceed 2, regardless of what either model originally assigned. This correction affected 402 documents. Composite scores and tier assignments were then recomputed from the corrected averaged sub-scores."),
      ]),
      p([t("Documents were then sorted into four priority tiers:")]),
      tableCaption("Table A.3.", "Priority tier definitions and document counts after score averaging and correction."),
      tierTable(),
      new Paragraph({ spacing: { before: 160, after: 80 }, children: [] }),

      // Step 5
      stepHeader(5, "Disagreement Flagging"),
      p([
        t("When the two models’ composite scores differ by more than 3.0 points on the 0–10 scale, the document is flagged as "),
        bold("contested"),
        t(". Of 6,988 shared documents, 928 were flagged this way. Contested documents in the shortlist are marked for human review before being cited as primary evidence — a gap that large typically means one model responded to something the other ignored, or that one model hallucinated."),
      ]),

      // Step 6
      stepHeader(6, "Shortlist"),
      p([
        t("All Tier 1 and Tier 2 documents are merged and sorted by composite score. The final shortlist contains "),
        bold("1,463 documents"),
        t(" (65 Tier 1, 1,398 Tier 2). This exceeds the original target of ~167 because more documents than anticipated scored above the Tier 2 threshold; all of them are included rather than artificially truncated."),
      ]),
      p([
        t("A subset of "),
        bold("20 documents"),
        t(" — called “robust Tier 1” — received Tier 1 classification independently from both models before any averaging. These 20 represent the highest-confidence relevance judgments and are the recommended starting point for close reading and direct citation. Shortlisted documents flagged as contested (464 of 1,463) should be read carefully before being cited as primary evidence."),
      ]),

      // Step 7
      stepHeader(7, "Spot-Check"),
      p([
        t("A random 10% sample of low-priority documents (Tier 3 and Tier 4) is drawn using a fixed random seed (so the sample is identical if the process is repeated). A human reviewer reads each sampled document and records whether the pipeline’s low-priority classification was correct. This estimates the false-negative rate — how often a relevant document was incorrectly deprioritized."),
      ]),
      p([
        t("If the escalation rate from the spot-check is high (above approximately 15%), the pipeline’s threshold settings should be revisited before treating the shortlist as comprehensive."),
      ]),

      rule(),

      // ── Why Two Models ───────────────────────────────────────────────────────
      h1("Why Two Models?"),
      p([
        t("Single AI models have systematic tendencies — they may consistently overweight or underweight certain types of policy language, misread jargon from a particular agency, or be insensitive to LA County-specific context. Running two models independently provides a partial check against these tendencies."),
      ]),
      p([
        t("This is not a peer-review process. The models are not judging each other’s reasoning; they score the same document in isolation, and their outputs are compared after the fact."),
      ]),
      p([
        t("In practice, the two models showed distinct biases that partially cancelled each other out through averaging. GPT-mini tended to read care-first and evidentiary content more generously; Claude Haiku tended to read AI governance content more broadly. Averaging produces a composite that is less dependent on either model’s particular interpretation of the rubric. The 20 robust Tier 1 documents — those rated highest by "),
        bold("both"),
        t(" models independently — are the subset least sensitive to these individual biases."),
      ]),

      rule(),

      // ── Limitations ──────────────────────────────────────────────────────────
      h1("Limitations"),

      h3("The pipeline screens for relevance, not quality"),
      p([t("A document may score high because it mentions the right programs and officials without actually advancing the research argument. High-ranked documents still require careful human reading.")]),

      h3("OCR introduces noise"),
      p([t("Scanned PDFs, especially older ones, often contain recognition errors that distort the text the models receive. A document with poor OCR quality will tend to score lower than its content warrants. Extraction status is recorded for every document; researchers should be alert to OCR-flagged documents in the shortlist.")]),

      h3("The intersection dimension is the hardest to score reliably"),
      p([t("The research question asks about a gap that is largely implicit in the documentary record — the two governance systems rarely discuss each other directly. Models are instructed to score highly only when an explicit connection is present, which means documents that gesture toward the gap without naming it may be underscored. Inspection of extreme disagreement cases also revealed that both models occasionally assign high intersection scores to documents with no substantive content on either primary dimension. A post-hoc correction caps intersection scores to prevent this logical inconsistency, but borderline cases remain.")]),

      h3("The spot-check estimates but does not eliminate false negatives"),
      p([t("A 10% sample of low-priority documents provides a statistical estimate of how many relevant documents the pipeline missed. It does not guarantee that all missed documents are identified.")]),

      h3("Prompt dependency"),
      p([
        t("The scoring criteria are embedded in a written prompt given to both models. Changes to that prompt would change the scores. Post-hoc analysis identified two rubric weaknesses — ambiguous anchor points for the care-first and AI governance dimensions, and an underspecified evidentiary checklist — that contributed to the low inter-rater reliability. A revised prompt addresses these issues and is archived in the project repository for future runs alongside the version used for this corpus."),
      ]),

      rule(),

      // ── Footer note ──────────────────────────────────────────────────────────
      new Paragraph({
        spacing: { before: 0, after: 0 },
        children: [
          new TextRun({ text: "Full technical documentation, source code, and output files are available in the project repository. The scoring prompt is ", size: 18, font: "Arial", color: "666666", italics: true }),
          new TextRun({ text: "prompts/scorer_agent.md", size: 18, font: "Courier New", color: "444444" }),
          new TextRun({ text: "; IRR statistics and per-document score deltas are in ", size: 18, font: "Arial", color: "666666", italics: true }),
          new TextRun({ text: "comparison/irr_report.md", size: 18, font: "Courier New", color: "444444" }),
          new TextRun({ text: " and ", size: 18, font: "Arial", color: "666666", italics: true }),
          new TextRun({ text: "comparison/compare_detail.jsonl", size: 18, font: "Courier New", color: "444444" }),
          new TextRun({ text: ".", size: 18, font: "Arial", color: "666666", italics: true }),
        ],
      }),
    ],
  }],
});

Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync(OUT, buf);
  console.log("Written:", OUT);
});
