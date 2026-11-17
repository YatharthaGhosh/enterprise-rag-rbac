"""Generate the synthetic document set for "Nimbus Systems Pvt Ltd", a fictional company.

16 documents across 4 departments x 3 access levels, as PDF, DOCX and XLSX, with tables and
multiple pages. Each document holds a few specific, checkable facts (numbers, codenames) that
the evaluation set in eval/golden.jsonl asks about.

Folder layout encodes the access labels:   data/docs/<department>/<public|internal|confidential>/<file>

Run:  python scripts/generate_corpus.py
"""

from pathlib import Path

from docx import Document
from docx.enum.text import WD_BREAK
from openpyxl import Workbook
from openpyxl.styles import Font
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

OUT = Path(__file__).resolve().parent.parent / "data" / "docs"
COMPANY = "Nimbus Systems Pvt Ltd"

# Each section: (heading, [paragraphs], table_rows_or_None). "PAGE" as a section starts a new page.
DOCS = [
    # ---------------- HR ----------------
    ("hr", "public", "employee_handbook.pdf", "Employee Handbook 2026", [
        ("Welcome", [f"This handbook explains how we work at {COMPANY}. It applies to all full-time employees in India. "
                     "Questions about any policy should go to the People team at people@nimbus.example."], None),
        ("Leave Policy", ["Every full-time employee receives 24 days of paid annual leave per calendar year, credited "
                          "monthly at 2 days per month. Up to 10 unused days can be carried forward to the next year; "
                          "the rest lapse on 31 December.",
                          "Employees also receive 12 days of sick leave per year. Sick leave of more than 3 consecutive "
                          "days requires a medical certificate."], None),
        "PAGE",
        ("Parental Leave", ["Birthing parents receive 26 weeks of paid maternity leave. Non-birthing parents receive "
                            "4 weeks of paid paternity leave, which must be taken within 6 months of the child's birth "
                            "or adoption."], None),
        ("Remote Work", ["Employees may work remotely up to 3 days per week. Tuesdays and Thursdays are anchor days "
                         "when the whole team is expected in the office."], None),
        ("Holiday Calendar", ["The company observes the following fixed holidays in 2026:"],
         [["Holiday", "Date"], ["Republic Day", "26 January"], ["Holi", "4 March"], ["Independence Day", "15 August"],
          ["Durga Puja", "20 October"], ["Diwali", "8 November"], ["Christmas", "25 December"]]),
    ]),
    ("hr", "internal", "performance_review_process.docx", "Performance Review Process", [
        ("Review Cycles", ["Performance reviews run twice a year, in April and October. Each cycle has three steps: "
                           "self-review, manager review and a calibration meeting."], None),
        ("Rating Scale", ["Managers rate each employee on a 5-point scale:"],
         [["Rating", "Label", "Meaning"], ["5", "Exceptional", "Consistently far exceeds expectations"],
          ["4", "Strong", "Often exceeds expectations"], ["3", "Solid", "Meets expectations"],
          ["2", "Developing", "Partially meets expectations"], ["1", "Unsatisfactory", "Does not meet expectations"]]),
        "PAGE",
        ("Calibration", ["Calibration meetings are chaired by the department head. No more than 15% of a "
                         "department may be rated 5 (Exceptional) in a single cycle."], None),
        ("Performance Improvement Plans", ["An employee rated 1 in a cycle is placed on a Performance Improvement Plan "
                                           "(PIP) lasting 60 days, with fortnightly check-ins with their manager."], None),
    ]),
    ("hr", "confidential", "salary_bands_2026.xlsx", "Salary Bands 2026", [
        ("Bands", None, [["Level", "Title", "Min (INR LPA)", "Max (INR LPA)", "Bonus target"],
                         ["L1", "Associate Engineer", 6, 9, "5%"], ["L2", "Engineer", 9, 15, "8%"],
                         ["L3", "Senior Engineer", 15, 26, "10%"], ["L4", "Staff Engineer", 26, 42, "15%"],
                         ["L5", "Principal Engineer", 42, 65, "20%"]]),
        ("Increments", None, [["Rating", "Increment range"], ["5", "18-25%"], ["4", "12-16%"], ["3", "7-10%"],
                              ["2", "0-3%"], ["1", "0%"]]),
    ]),
    ("hr", "confidential", "restructuring_plan.docx", "Restructuring Plan (Project Orion)", [
        ("Overview", ["Project Orion is the confidential plan to merge the Support and Customer Success teams into a "
                      "single Customer Experience unit, effective 1 April 2027."], None),
        ("Headcount", ["The merged unit will have 84 roles, down from 97 today. The 13 affected employees will be "
                       "offered internal transfers first; severance is 3 months of base salary plus 1 month per year "
                       "of service."], None),
        ("Communication", ["Project Orion must not be discussed outside the HR leadership group until the all-hands "
                           "announcement on 15 February 2027."], None),
    ]),
    # ---------------- ENGINEERING ----------------
    ("engineering", "public", "tech_stack_overview.pdf", "Technology Stack Overview", [
        ("Platform", ["The Nimbus platform is built with Python (FastAPI) services and a React frontend. Data is "
                      "stored in PostgreSQL 16, with Redis for caching."], None),
        ("Cloud", ["All production workloads run on AWS in the ap-south-1 (Mumbai) region, with disaster recovery in "
                   "ap-south-2 (Hyderabad)."], None),
        ("Languages and Tools", ["Approved languages and their main use:"],
         [["Language", "Use"], ["Python", "Backend services, data pipelines"], ["TypeScript", "Web frontend"],
          ["Go", "High-throughput ingestion service"], ["Terraform", "Infrastructure as code"]]),
    ]),
    ("engineering", "internal", "incident_runbook.pdf", "Incident Response Runbook", [
        ("Severity Levels", ["Incidents are classified by customer impact:"],
         [["Severity", "Definition", "Acknowledge within", "Update cadence"],
          ["SEV1", "Full outage or data loss", "15 minutes", "Every 30 minutes"],
          ["SEV2", "Major feature degraded", "30 minutes", "Every 60 minutes"],
          ["SEV3", "Minor issue, workaround exists", "4 hours", "Daily"]]),
        "PAGE",
        ("On-call and Escalation", ["The primary on-call engineer is paged through PagerDuty. If a SEV1 is not "
                                    "acknowledged in time it escalates to the engineering manager, then to the VP "
                                    "Engineering. The bridge call uses the standing Zoom room 'nimbus-war-room'."], None),
        ("Postmortems", ["Every SEV1 and SEV2 incident requires a blameless postmortem, published within 5 business "
                         "days, with action items tracked in Jira under the INC project."], None),
    ]),
    ("engineering", "internal", "deployment_guide.docx", "Deployment Guide", [
        ("Release Train", ["Production releases ship every Tuesday at 11:00 IST. A release candidate is cut on Monday "
                           "at 17:00 IST and must pass the full regression suite."], None),
        ("Code Freeze", ["There is a code freeze from 20 December to 3 January every year. Only SEV1 fixes approved by "
                         "the VP Engineering may be deployed during the freeze."], None),
        "PAGE",
        ("Rollback", ["Every deployment uses blue-green switching. A rollback must be completed within 10 minutes of "
                      "the decision, using the 'deployctl rollback' command."], None),
    ]),
    ("engineering", "confidential", "security_audit_2026.pdf", "Security Audit Report 2026", [
        ("Summary", ["The 2026 external penetration test was carried out by RedOak Labs between 3 and 21 August 2026. "
                     "It found 3 high, 7 medium and 12 low severity issues."], None),
        ("High Severity Findings", ["The high severity findings were:"],
         [["ID", "Finding", "Owner", "Deadline"],
          ["H-1", "IDOR in invoice download API", "Payments team", "31 January 2027"],
          ["H-2", "Stale admin accounts without MFA", "IT", "15 December 2026"],
          ["H-3", "Unencrypted backups in legacy S3 bucket", "Platform team", "31 January 2027"]]),
        ("Remediation", ["All high severity issues must be remediated by 31 January 2027 and verified by a RedOak Labs "
                         "retest."], None),
    ]),
    # ---------------- FINANCE ----------------
    ("finance", "public", "expense_policy.pdf", "Travel and Expense Policy", [
        ("Meals and Allowances", ["The daily meal allowance during business travel is INR 1,500 in metro cities and "
                                  "INR 1,000 elsewhere."], None),
        ("Travel Class", ["Flights under 6 hours must be booked in economy. Trains may be booked in AC 2-tier."], None),
        ("Reimbursement", ["Claims must be submitted within 30 days of the expense with receipts, and are reimbursed "
                           "in the next monthly payroll."], None),
    ]),
    ("finance", "internal", "budget_process.docx", "Annual Budget Process", [
        ("Timeline", ["The financial year runs April to March. Department budget drafts for FY 2027-28 are due by "
                      "15 January 2027, and the board approves the final budget in its March meeting."], None),
        ("Approval Thresholds", ["Spend must be approved at the following levels:"],
         [["Amount", "Approver"], ["Up to INR 50,000", "Line manager"], ["INR 50,001 to INR 5,00,000", "Department head"],
          ["INR 5,00,001 to INR 50,00,000", "CFO"], ["Above INR 50,00,000", "CEO and board"]]),
        "PAGE",
        ("Vendor Payments", ["Approved vendor invoices are paid on net-45 terms."], None),
    ]),
    ("finance", "confidential", "q3_financials.xlsx", "Q3 FY2026-27 Financials", [
        ("Summary", None, [["Metric", "Value"], ["Revenue (INR Cr)", 48.2], ["Gross margin", "71.5%"],
                           ["EBITDA margin", "18.4%"], ["Cash in bank (INR Cr)", 132.6], ["Headcount", 412]]),
        ("By Segment", None, [["Segment", "Revenue (INR Cr)", "YoY growth"], ["Enterprise", 29.1, "34%"],
                              ["Mid-market", 13.4, "21%"], ["SMB", 5.7, "-6%"]]),
    ]),
    ("finance", "confidential", "acquisition_memo.pdf", "Acquisition Memo: Project Kestrel", [
        ("Proposal", ["Project Kestrel is the proposed acquisition of Brightpath Analytics, a Pune-based data analytics "
                      "startup, for INR 120 crore in a mix of 70% cash and 30% stock."], None),
        ("Rationale", ["Brightpath's forecasting engine would let Nimbus launch a predictive analytics add-on for "
                       "Enterprise customers in FY 2027-28."], None),
        ("Timeline", ["Due diligence completes in January 2027 and the deal is targeted to close by 31 March 2027."], None),
    ]),
    # ---------------- SALES ----------------
    ("sales", "public", "product_catalog.pdf", "Product Catalog", [
        ("Plans", ["Nimbus is sold in three plans, billed annually:"],
         [["Plan", "Price per user per month", "Minimum users"], ["Starter", "INR 499", "5"],
          ["Growth", "INR 1,199", "20"], ["Enterprise", "INR 2,499", "100"]]),
        ("Add-ons", ["The Advanced Audit Log add-on costs INR 199 per user per month and is available on Growth and "
                     "Enterprise plans."], None),
    ]),
    ("sales", "internal", "sales_playbook.docx", "Sales Playbook", [
        ("Qualification", ["Reps qualify opportunities using the BANT framework: Budget, Authority, Need and Timeline. "
                           "An opportunity must score at least 3 of 4 to enter the pipeline."], None),
        ("Discount Authority", ["Discount limits on list price:"],
         [["Role", "Maximum discount"], ["Sales rep", "10%"], ["Sales manager", "20%"], ["VP Sales", "30%"]]),
        "PAGE",
        ("Deal Desk", ["Any deal above INR 25 lakh annual contract value must be reviewed by the Deal Desk before the "
                       "proposal is sent."], None),
    ]),
    ("sales", "internal", "territory_targets.xlsx", "Territory Targets FY2026-27", [
        ("Targets", None, [["Region", "Annual target (INR Cr)", "Regional head"], ["North", 14.0, "Arjun Kapoor"],
                           ["South", 18.5, "Meera Nair"], ["West", 16.0, "Rohan Desai"], ["East", 7.5, "Sneha Das"]]),
    ]),
    ("sales", "confidential", "key_accounts.xlsx", "Key Accounts", [
        ("Accounts", None, [["Account", "Annual contract value (INR Cr)", "Renewal date", "Renewal risk"],
                            ["Vardhan Retail", 3.8, "June 2027", "High"], ["Kaveri Logistics", 2.9, "March 2027", "Low"],
                            ["Sahyadri Bank", 5.2, "September 2027", "Medium"], ["Ganga Foods", 1.6, "May 2027", "High"]]),
    ]),
    # ---------------- DISTRACTORS: similar wording, different facts (make retrieval genuinely hard) ----------------
    ("hr", "public", "contractor_guidelines.pdf", "Contractor Guidelines", [
        ("Engagement", ["These guidelines apply to independent contractors engaged through a statement of work. "
                        "Contractors are not employees and are not covered by the Employee Handbook."], None),
        ("Time Off", ["Contractors may take up to 12 days of unpaid time off per year with two weeks' notice. Unused "
                      "days cannot be carried forward."], None),
        ("Working Location", ["Contractors may work fully remotely; there are no anchor days for contractors."], None),
    ]),
    ("engineering", "internal", "support_escalation_guide.docx", "Customer Support Escalation Guide", [
        ("Ticket Priorities", ["Customer support tickets are prioritised as follows:"],
         [["Priority", "Example", "First response within"], ["P1", "Customer cannot log in", "1 hour"],
          ["P2", "Report export failing", "4 hours"], ["P3", "How-to question", "1 business day"]]),
        ("Escalation to Engineering", ["A P1 ticket that is not resolved within 4 hours is escalated to engineering "
                                       "as a SEV2 incident."], None),
    ]),
    ("sales", "public", "partner_pricing.pdf", "Reseller Partner Pricing", [
        ("Partner Prices", ["Authorised resellers buy Nimbus at the following partner prices:"],
         [["Plan", "Partner price per user per month"], ["Starter", "INR 399"], ["Growth", "INR 999"],
          ["Enterprise", "INR 2,099"]]),
        ("Partner Discounts", ["Resellers may pass on up to 5% additional discount to their customers."], None),
    ]),
    ("finance", "public", "procurement_policy.pdf", "Procurement Policy", [
        ("Purchase Orders", ["All purchases above INR 25,000 need a purchase order raised by the Procurement team. "
                             "Purchases below that can be paid with a company card."], None),
        ("Small Vendors", ["Registered MSME vendors are paid on net-30 terms, as required by law."], None),
        ("Vendor Onboarding", ["New vendors must submit GST registration and bank details before the first "
                               "purchase order is issued."], None),
    ]),
]


def make_pdf(path: Path, title: str, sections: list) -> None:
    styles = getSampleStyleSheet()
    story = [Paragraph(title, styles["Title"]), Paragraph(COMPANY, styles["Normal"]), Spacer(1, 12)]
    for sec in sections:
        if sec == "PAGE":
            story.append(PageBreak())
            continue
        heading, paras, table = sec
        story.append(Paragraph(heading, styles["Heading2"]))
        for p in paras or []:
            story += [Paragraph(p, styles["BodyText"]), Spacer(1, 6)]
        if table:
            t = Table([[str(c) for c in r] for r in table])
            t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                                   ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey)]))
            story += [t, Spacer(1, 10)]
    SimpleDocTemplate(str(path), pagesize=A4, title=title).build(story)


def make_docx(path: Path, title: str, sections: list) -> None:
    doc = Document()
    doc.add_heading(title, level=0)
    doc.add_paragraph(COMPANY)
    for sec in sections:
        if sec == "PAGE":
            doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
            continue
        heading, paras, table = sec
        doc.add_heading(heading, level=1)
        for p in paras or []:
            doc.add_paragraph(p)
        if table:
            t = doc.add_table(rows=len(table), cols=len(table[0]))
            t.style = "Table Grid"
            for i, row in enumerate(table):
                for j, val in enumerate(row):
                    t.cell(i, j).text = str(val)
    doc.save(path)


def make_xlsx(path: Path, title: str, sections: list) -> None:
    wb = Workbook()
    wb.remove(wb.active)
    for heading, _, table in [s for s in sections if s != "PAGE"]:
        ws = wb.create_sheet(heading)
        for row in table:
            ws.append(row)
        for cell in ws[1]:
            cell.font = Font(bold=True)
    wb.properties.title = title
    wb.save(path)


def main() -> None:
    for dept, level, name, title, sections in DOCS:
        folder = OUT / dept / level
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / name
        {".pdf": make_pdf, ".docx": make_docx, ".xlsx": make_xlsx}[path.suffix](path, title, sections)
        print(f"wrote {path.relative_to(OUT.parent.parent)}")


if __name__ == "__main__":
    main()
