"""
Dental Clinic Loan Verification Pipeline — FastMCP Server
==========================================================
Run:  mcp dev server.py
All tools use flat arguments (no Pydantic wrapper) for full
MCP Inspector + Slingshot compatibility.
"""

from mcp.server.fastmcp import FastMCP
from typing import Literal
import re, random, datetime

# Load .env for local dev
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from llm_tools import register_llm_tools

mcp = FastMCP(
    name="dental-loan-verifier",
    instructions=(
        "You are a loan verification orchestrator for dental clinic loans. "
        "Run Stage 2 checks in order: Group 1 (doc check) → Group 2 (PAN + fraud) → "
        "Group 3 (Aadhaar + DCI + GST) → Group 3b (LLM cross-check) → "
        "Group 4 (fraud reasoning) → Group 5 (final report)."
    ),
)

register_llm_tools(mcp)

REQUIRED_DOCS: dict[str, list[str]] = {
    "clinic_setup":    ["PAN_CARD", "AADHAAR", "DENTAL_DEGREE_BDS", "ITR", "BANK_STATEMENT", "PROJECT_REPORT", "LEASE_AGREEMENT"],
    "equipment":       ["PAN_CARD", "AADHAAR", "DENTAL_DEGREE_BDS", "ITR", "BANK_STATEMENT", "EQUIPMENT_QUOTE"],
    "working_capital": ["PAN_CARD", "AADHAAR", "ITR", "BANK_STATEMENT"],
    "expansion":       ["PAN_CARD", "AADHAAR", "DENTAL_DEGREE_BDS", "ITR", "BANK_STATEMENT", "PROJECT_REPORT"],
}

# ─────────────────────────────────────────────
# GROUP 1 — Document Completeness
# ─────────────────────────────────────────────

@mcp.tool()
def doc_validate_document_set(
    case_id: str,
    loan_type: Literal["clinic_setup", "equipment", "working_capital", "expansion"],
    uploaded_docs: list[str],
) -> dict:
    """
    GROUP 1 — Check mandatory documents for the loan type.
    loan_type: clinic_setup | equipment | working_capital | expansion
    uploaded_docs: e.g. ["PAN_CARD", "AADHAAR", "DENTAL_DEGREE_BDS", "ITR", "BANK_STATEMENT"]
    """
    required = set(REQUIRED_DOCS.get(loan_type, []))
    uploaded = set(uploaded_docs)
    missing  = sorted(required - uploaded)
    present  = sorted(required & uploaded)
    extra    = sorted(uploaded - required)
    complete = len(missing) == 0
    return {
        "status":         "COMPLETE" if complete else "INCOMPLETE",
        "complete":       complete,
        "present_docs":   present,
        "missing_docs":   missing,
        "extra_docs":     extra,
        "required_count": len(required),
        "uploaded_count": len(uploaded),
        "note": (
            "All required documents present. Proceed to Group 2."
            if complete
            else f"Missing {len(missing)} document(s): {missing}. "
                 "Pipeline continues but final approval will be blocked."
        ),
    }


# ─────────────────────────────────────────────
# GROUP 2 — PAN Validation + Fraud Registry
# ─────────────────────────────────────────────

@mcp.tool()
def pan_validate(
    case_id: str,
    pan: str,
    applicant_name: str,
) -> dict:
    """
    GROUP 2a — Validate PAN format, watchlist check, deduplication.
    pan: e.g. ABCDE1234F
    """
    pan = pan.upper().strip()
    valid_format  = bool(re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", pan))
    nsdl_name     = applicant_name.upper().replace("DR. ", "DR ") + " KUMAR"
    name_match    = 79 if "SHARMA" in applicant_name.upper() else 95
    watchlist_hit = False
    dedup_clean   = True
    return {
        "pan":              pan,
        "format_valid":     valid_format,
        "nsdl_name":        nsdl_name,
        "application_name": applicant_name,
        "name_match_score": name_match,
        "name_match_flag":  name_match < 85,
        "watchlist_hit":    watchlist_hit,
        "dedup_clean":      dedup_clean,
        "status":           "PASS" if (valid_format and not watchlist_hit and dedup_clean) else "FAIL",
        "note":             f"PAN {pan} valid, no watchlist hits, dedup clean." if valid_format else "PAN validation failed.",
    }


@mcp.tool()
def fraud_registry_check(
    case_id: str,
    identifier: str,
    identifier_type: Literal["PAN", "GSTIN", "AADHAAR"],
) -> dict:
    """
    GROUP 2b / 4a — Check PAN or GSTIN against fraud registry.
    identifier_type: PAN | GSTIN | AADHAAR
    """
    risk_score    = random.randint(5, 15)
    prior_signals = []
    passed        = risk_score < 30 and len(prior_signals) == 0
    return {
        "identifier":      identifier,
        "identifier_type": identifier_type,
        "risk_score":      risk_score,
        "risk_band":       "LOW" if risk_score < 30 else ("MEDIUM" if risk_score < 60 else "HIGH"),
        "prior_signals":   prior_signals,
        "status":          "PASS" if passed else "FAIL",
        "note":            f"Risk score {risk_score}/100, no prior signals." if passed else "Fraud signals found.",
    }


# ─────────────────────────────────────────────
# GROUP 3 — Aadhaar + DCI + GST
# ─────────────────────────────────────────────

@mcp.tool()
def aadhaar_verify(
    case_id: str,
    aadhaar_last4: str,
    name: str,
    address_state: str,
) -> dict:
    """
    GROUP 3a — Verify Aadhaar via UIDAI API (stub).
    aadhaar_last4: last 4 digits of Aadhaar number
    """
    return {
        "status":          "PENDING",
        "aadhaar_last4":   aadhaar_last4,
        "note":            "Aadhaar verification could not be completed via API. Manual verification required.",
        "manual_required": True,
    }


@mcp.tool()
def dci_credential_verify(
    case_id: str,
    dci_registration_number: str,
    applicant_name: str,
    applicant_gender: Literal["male", "female", "other"],
) -> dict:
    """
    GROUP 3b — Verify DCI registration: active status, expiry, photo gender check.
    applicant_gender: male | female | other
    """
    reg = dci_registration_number.upper()
    registry_record = {
        "reg_number":     f"MCI/BDS/2015/{reg.replace('MCI', '')}",
        "name":           applicant_name,
        "active":         True,
        "issue_date":     "2015-03-10",
        "expiry_date":    "2023-12-31",
        "council":        "Tamil Nadu Dental Council",
        "photo_gender":   "female",
        "practice_years": 9,
    }
    expired       = datetime.date.fromisoformat(registry_record["expiry_date"]) < datetime.date.today()
    photo_mismatch = registry_record["photo_gender"] != applicant_gender
    flags = []
    if expired:
        flags.append({"severity": "WARNING", "code": "DCI_EXPIRED",
                      "message": f"DCI certificate expired on {registry_record['expiry_date']}."})
    if photo_mismatch:
        flags.append({"severity": "CRITICAL", "code": "PHOTO_GENDER_MISMATCH",
                      "message": f"Certificate photo is {registry_record['photo_gender']} but applicant is {applicant_gender}. Likely borrowed credential."})
    status = "FAIL" if any(f["severity"] == "CRITICAL" for f in flags) else ("WARNING" if flags else "PASS")
    return {
        "status":          status,
        "registry_record": registry_record,
        "expired":         expired,
        "photo_mismatch":  photo_mismatch,
        "flags":           flags,
        "note":            f"Reg {registry_record['reg_number']}, {registry_record['practice_years']} yrs practice."
                           + (" EXPIRED." if expired else "")
                           + (" PHOTO MISMATCH — CRITICAL." if photo_mismatch else ""),
    }


@mcp.tool()
def gst_verify(
    case_id: str,
    gstin: str,
    applicant_name: str,
) -> dict:
    """
    GROUP 3c — Verify GSTIN: active status, compliance score, state check.
    gstin: e.g. 29ABCDE1234F1Z5
    """
    gstin      = gstin.upper().strip()
    state_code = gstin[:2]
    STATE_CODES = {"29": "Karnataka", "33": "Tamil Nadu", "27": "Maharashtra", "07": "Delhi"}
    state      = STATE_CODES.get(state_code, "Unknown")
    gst_record = {
        "gstin": gstin, "business_name": "SHARMA DENTAL CLINIC LLP",
        "state": state,  "status": "ACTIVE",
        "compliance_score": 88, "filing_months": 24, "missed_filings": 2,
    }
    passed = gst_record["status"] == "ACTIVE" and gst_record["compliance_score"] >= 70
    flags  = []
    if state != "Karnataka":
        flags.append({"severity": "WARNING", "code": "STATE_MISMATCH",
                      "message": f"GSTIN in {state} but DCI from Tamil Nadu Dental Council."})
    return {
        "status":     "PASS" if passed else "FAIL",
        "gst_record": gst_record,
        "state":      state,
        "flags":      flags,
        "note":       f"{gst_record['business_name']}, compliance {gst_record['compliance_score']}/100.",
    }


@mcp.tool()
def dci_document_parse(
    case_id: str,
    document_key: str,
) -> dict:
    """GROUP 4b — OCR parse DCI certificate (stub → AWS Textract / Google Vision)."""
    return {
        "status":   "PARSED",
        "document": document_key,
        "fields": {
            "extracted_name":       "Dr. Rajesh Sharma",
            "extracted_reg_number": "34142",
            "extracted_council":    "Tamil Nadu Dental Council",
            "extracted_expiry":     "31.12.2023",
            "extracted_photo_desc": "Female photograph detected",
            "ocr_confidence":       0.91,
        },
        "note": "Cross-check extracted fields against registry record.",
    }


@mcp.tool()
def fraud_submit_signal(
    case_id: str,
    signal_code: str,
    severity: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"],
    description: str,
    evidence: list[str],
) -> dict:
    """
    GROUP 4c — Submit fraud signal to registry (conditional — only if CRITICAL/HIGH).
    severity: CRITICAL | HIGH | MEDIUM | LOW
    """
    signal_id = f"SIG-{signal_code}-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
    return {
        "status":      "SUBMITTED",
        "signal_id":   signal_id,
        "case_id":     case_id,
        "severity":    severity,
        "signal_code": signal_code,
        "description": description,
        "note":        f"Fraud signal {signal_id} submitted. Escalate to fraud/credit officer.",
    }


# ─────────────────────────────────────────────
# ORCHESTRATION
# ─────────────────────────────────────────────

@mcp.tool()
def orchestrate_stage2_verification(
    case_id: str,
    applicant_name: str,
    pan: str,
    dci_number: str,
    gstin: str,
    loan_type: Literal["clinic_setup", "equipment", "working_capital", "expansion"],
    uploaded_docs: list[str],
) -> dict:
    """
    CALL THIS FIRST — returns the full execution plan for the Stage 2 pipeline.
    loan_type: clinic_setup | equipment | working_capital | expansion
    uploaded_docs: list of document keys e.g. ["PAN_CARD", "AADHAAR", "ITR"]
    """
    return {
        "case_id": case_id,
        "applicant_name": applicant_name,
        "execution_plan": [
            {"group": 1,   "label": "doc_validate_document_set",           "parallel": False},
            {"group": 2,   "label": "pan_validate + fraud_registry_check + llm_analyze_document(PAN)", "parallel": True},
            {"group": 3,   "label": "aadhaar_verify + dci_credential_verify + gst_verify + llm_analyze_document(DCI, AADHAAR)", "parallel": True},
            {"group": "3b","label": "llm_cross_check_documents + llm_assess_name_match", "parallel": True},
            {"group": 4,   "label": "fraud_registry_check(GSTIN) + dci_document_parse + llm_fraud_reasoning", "parallel": True},
            {"group": 5,   "label": "llm_generate_risk_narrative + orchestrate_generate_verification_summary", "parallel": True},
        ],
    }


@mcp.tool()
def orchestrate_generate_verification_summary(
    case_id: str,
    applicant_name: str,
    loan_type: str,
    doc_check_result: dict,
    pan_result: dict,
    pan_fraud_result: dict,
    aadhaar_result: dict,
    dci_result: dict,
    gst_result: dict,
    gstin_fraud_result: dict,
    dci_parse_result: dict,
    fraud_signal_result: dict = {},
) -> dict:
    """FINAL STEP — Aggregate all results into Stage 2 report with risk score and recommendation."""
    checks_passed = []
    warnings      = []
    risk_score    = 0

    if pan_result.get("status") == "PASS":
        checks_passed.append({"check": "PAN Validation", "result": "PASS", "notes": pan_result.get("note", "")})
    else:
        warnings.append({"severity": "HIGH", "check": "PAN Validation", "message": pan_result.get("note", "")})
        risk_score += 20

    if pan_result.get("name_match_flag"):
        warnings.append({"severity": "WARNING", "check": "Name Discrepancy",
                         "message": f"PAN: '{pan_result.get('nsdl_name')}' vs application: '{pan_result.get('application_name')}' "
                                    f"(score: {pan_result.get('name_match_score')}/100)."})
        risk_score += 10

    if pan_fraud_result.get("status") == "PASS":
        checks_passed.append({"check": "Fraud Registry (PAN)", "result": "PASS", "notes": pan_fraud_result.get("note", "")})
    else:
        risk_score += 25

    if aadhaar_result.get("status") == "PENDING":
        warnings.append({"severity": "WARNING", "check": "Aadhaar", "message": aadhaar_result.get("note", "")})
        risk_score += 10
    elif aadhaar_result.get("status") == "PASS":
        checks_passed.append({"check": "Aadhaar", "result": "PASS", "notes": "Verified."})

    for f in dci_result.get("flags", []):
        warnings.append({"severity": f["severity"], "check": "DCI Credential", "message": f["message"]})
        risk_score += 25 if f["severity"] == "CRITICAL" else 10
    if not dci_result.get("flags"):
        checks_passed.append({"check": "DCI Credential", "result": "PASS", "notes": dci_result.get("note", "")})

    if gst_result.get("status") == "PASS":
        checks_passed.append({"check": "GST Verification", "result": "PASS", "notes": gst_result.get("note", "")})
    for f in gst_result.get("flags", []):
        warnings.append({"severity": f["severity"], "check": "GST", "message": f["message"]})
        risk_score += 10

    missing_docs = doc_check_result.get("missing_docs", [])
    if missing_docs:
        warnings.append({"severity": "WARNING", "check": "Missing Documents",
                         "message": f"{missing_docs} mandatory for {loan_type} loans."})
        risk_score += 5 * len(missing_docs)

    risk_score = min(risk_score, 100)
    risk_band  = "LOW" if risk_score < 30 else ("MEDIUM" if risk_score < 60 else "HIGH")
    critical   = [w for w in warnings if w["severity"] == "CRITICAL"]

    if critical or risk_band == "HIGH":
        recommendation = "DO NOT PROCEED TO STAGE 3. Escalate immediately."
        proceed        = False
    elif risk_band == "MEDIUM":
        recommendation = "CONDITIONAL PROCEED. Resolve warnings first."
        proceed        = None
    else:
        recommendation = "PROCEED TO STAGE 3."
        proceed        = True

    return {
        "report_title":         f"Stage 2 Verification Report — {case_id}",
        "case_id":              case_id,
        "applicant_name":       applicant_name,
        "loan_type":            loan_type,
        "overall_risk_score":   risk_score,
        "risk_band":            risk_band,
        "checks_passed":        checks_passed,
        "warnings":             warnings,
        "warning_count":        len(warnings),
        "critical_flag_count":  len(critical),
        "final_recommendation": recommendation,
        "proceed_to_stage3":    proceed,
        "generated_at":         datetime.datetime.utcnow().isoformat() + "Z",
    }

if __name__ == "__main__":
    import sys
    if "--stdio" in sys.argv:
        mcp.run(transport="stdio")
    else:
        mcp.run(transport="streamable-http")    