"""
llm_tools.py — LLM sub-agent tools (flat args, MCP Inspector compatible)
=========================================================================
llm_analyze_document accepts EITHER:
  - image_path  : local file path string  → for local dev / Slingshot
  - file_base64 : base64 encoded string   → for Horizon / remote clients
  - file_mime   : mime type               → required with file_base64

All other LLM tools are text-only (no file input needed).
"""
import json
from llm_client import call_llm_json, current_provider_info


def register_llm_tools(mcp):

    # ── TOOL 0 — Health check ────────────────────────────────────────────────

    @mcp.tool()
    def llm_health_check() -> dict:
        """Check which LLM provider and model is active. Call this first."""
        info = current_provider_info()
        return {
            "status":   "OK",
            "provider": info["provider"],
            "model":    info["model"],
            "note":     f"Using {info['provider']} / {info['model']}. "
                        "Change via LLM_PROVIDER env var.",
        }

    # ── TOOL 1 — Document Vision Analysis ───────────────────────────────────

    @mcp.tool()
    def llm_analyze_document(
        case_id:      str,
        document_key: str,
        image_path:   str = "",
        file_base64:  str = "",
        file_mime:    str = "",
    ) -> dict:
        """
        LLM VISION — Extract fields from a document image or PDF.
        Detects photo gender, tampering, expiry dates, issuing authority.

        Provide ONE of:
          image_path  = "C:/docs/dci_cert.pdf"        (local dev / Slingshot)
          file_base64 = "<base64 string>"              (Horizon / remote)
          file_mime   = "application/pdf"              (required with file_base64)

        document_key: DCI_CERTIFICATE | PAN_CARD | AADHAAR | DENTAL_DEGREE_BDS | BANK_STATEMENT | ITR
        """
        # Determine input mode and build a note for the response
        if file_base64 and file_mime:
            input_mode = "base64"
        elif image_path:
            input_mode = "file_path"
        else:
            return {
                "status":  "ERROR",
                "error":   "No file provided. Pass either image_path (local) or file_base64 + file_mime (remote).",
                "case_id": case_id,
            }

        system = (
            f"You are a forensic document analyst for loan verification. "
            f"Examine this {document_key} document carefully. "
            f"Extract ALL visible fields and flag any anomalies: "
            f"photo gender mismatch, signs of tampering, inconsistent fonts, expired dates."
        )

        user = f"""Analyze this {document_key} for loan case {case_id}.

Return JSON with this exact structure:
{{
  "document_type": "{document_key}",
  "extracted_fields": {{
    "name": "",
    "id_number": "",
    "dob": "",
    "expiry_date": "",
    "issuing_authority": "",
    "address": "",
    "state": "",
    "photo_gender_estimate": "male | female | unclear | not_applicable"
  }},
  "anomalies": [
    "list any suspicious observations here"
  ],
  "document_quality": "GOOD | POOR | UNREADABLE",
  "confidence_score": 0.0,
  "llm_notes": "any additional observations"
}}"""

        try:
            result = call_llm_json(
                system      = system,
                user_text   = user,
                image_path  = image_path  or None,
                file_base64 = file_base64 or None,
                file_mime   = file_mime   or None,
            )
            result["status"]     = "SUCCESS"
            result["case_id"]    = case_id
            result["input_mode"] = input_mode
            result["provider"]   = current_provider_info()["provider"]
            return result
        except FileNotFoundError as e:
            return {"status": "ERROR", "error": f"File not found: {e}", "case_id": case_id}
        except Exception as e:
            return {"status": "ERROR", "error": str(e), "case_id": case_id,
                    "hint": "Check image_path exists locally, or that file_base64 is valid base64."}

    # ── TOOL 2 — Cross-Document Consistency ─────────────────────────────────

    @mcp.tool()
    def llm_cross_check_documents(
        case_id:          str,
        applicant_name:   str,
        pan_data:         dict,
        aadhaar_data:     dict,
        dci_data:         dict,
        gst_data:         dict,
        application_data: dict,
    ) -> dict:
        """
        LLM REASONING — Find inconsistencies across all documents simultaneously.
        Pass outputs from: pan_validate, aadhaar_verify, dci_credential_verify, gst_verify.
        Also pass llm_analyze_document results if available.
        """
        system = (
            "You are a senior fraud analyst for dental clinic loans. "
            "Find ALL inconsistencies, mismatches, and fraud signals across these documents. "
            "Think step by step. Consider state mismatches, name variations, "
            "photo anomalies, expired credentials, address inconsistencies."
        )
        user = f"""Cross-document analysis for case {case_id} — {applicant_name}.

APPLICATION DATA:
{json.dumps(application_data, indent=2)}

PAN DATA:
{json.dumps(pan_data, indent=2)}

AADHAAR DATA:
{json.dumps(aadhaar_data, indent=2)}

DCI CERTIFICATE DATA:
{json.dumps(dci_data, indent=2)}

GST DATA:
{json.dumps(gst_data, indent=2)}

Return JSON:
{{
  "inconsistencies": [
    {{
      "field": "",
      "severity": "CRITICAL | HIGH | MEDIUM | LOW",
      "doc_a": "",
      "value_a": "",
      "doc_b": "",
      "value_b": "",
      "explanation": ""
    }}
  ],
  "consistent_fields": [],
  "fraud_indicators": [],
  "overall_consistency_score": 0,
  "analyst_summary": ""
}}"""
        try:
            result = call_llm_json(system=system, user_text=user)
            result["status"]   = "SUCCESS"
            result["case_id"]  = case_id
            result["provider"] = current_provider_info()["provider"]
            return result
        except Exception as e:
            return {"status": "ERROR", "error": str(e), "case_id": case_id}

    # ── TOOL 3 — Name Match ──────────────────────────────────────────────────

    @mcp.tool()
    def llm_assess_name_match(
        case_id:          str,
        application_name: str,
        pan_name:         str,
        aadhaar_name:     str = "",
        dci_name:         str = "",
    ) -> dict:
        """
        LLM LANGUAGE — Judge if name variations across documents are the same person.
        Understands Indian conventions: middle names, Dr./Mr., initials, transliteration.
        aadhaar_name and dci_name are optional.
        """
        system = (
            "You are an expert in Indian name conventions for KYC and loan verification. "
            "Assess whether name variations represent the SAME person or a red flag. "
            "Consider: middle name omission, salutations (Dr./Mr.), "
            "initials, transliteration differences."
        )
        names = {"application_name": application_name, "pan_name": pan_name}
        if aadhaar_name: names["aadhaar_name"] = aadhaar_name
        if dci_name:     names["dci_name"]     = dci_name

        user = f"""Name consistency check for case {case_id}.

Names found across documents:
{json.dumps(names, indent=2)}

Return JSON:
{{
  "same_person_likely": true,
  "match_score": 0,
  "match_type": "EXACT | MINOR_VARIATION | MIDDLE_NAME | SALUTATION | SUSPICIOUS | MISMATCH",
  "explanation": "",
  "requires_clarification": false,
  "clarification_reason": ""
}}"""
        try:
            result = call_llm_json(system=system, user_text=user)
            result["status"]   = "SUCCESS"
            result["case_id"]  = case_id
            result["provider"] = current_provider_info()["provider"]
            return result
        except Exception as e:
            return {"status": "ERROR", "error": str(e), "case_id": case_id}

    # ── TOOL 4 — Fraud Reasoning ─────────────────────────────────────────────

    @mcp.tool()
    def llm_fraud_reasoning(
        case_id:            str,
        applicant_name:     str,
        cross_check_result: dict,
        dci_analysis:       dict,
        registry_results:   dict,
        other_flags:        list = [],
    ) -> dict:
        """
        LLM REASONING — Synthesize all signals into a coherent fraud hypothesis.
        Pass outputs from: llm_cross_check_documents, dci_credential_verify, fraud_registry_check.
        other_flags: any additional CRITICAL/HIGH flags from rule-based tools.
        """
        system = (
            "You are a specialist fraud investigator for dental professional loans. "
            "Synthesize all signals into a coherent fraud hypothesis. "
            "Cluster connected signals (e.g. photo mismatch + state mismatch = borrowed credential). "
            "Distinguish fraud patterns from independent minor issues."
        )
        user = f"""Fraud reasoning for case {case_id} — {applicant_name}.

CROSS-DOCUMENT INCONSISTENCIES:
{json.dumps(cross_check_result, indent=2)}

DCI CERTIFICATE ANALYSIS:
{json.dumps(dci_analysis, indent=2)}

REGISTRY & WATCHLIST RESULTS:
{json.dumps(registry_results, indent=2)}

ADDITIONAL FLAGS:
{json.dumps(other_flags, indent=2)}

Return JSON:
{{
  "fraud_hypothesis": "",
  "signal_clusters": [
    {{
      "cluster_name": "",
      "signals": [],
      "combined_severity": "CRITICAL | HIGH | MEDIUM | LOW",
      "explanation": ""
    }}
  ],
  "independent_flags": [],
  "overall_fraud_risk": "CRITICAL | HIGH | MEDIUM | LOW | CLEAN",
  "recommended_action": "DO_NOT_PROCEED | ESCALATE | MANUAL_REVIEW | PROCEED_WITH_CONDITIONS | PROCEED",
  "escalation_notes": ""
}}"""
        try:
            result = call_llm_json(system=system, user_text=user)
            result["status"]   = "SUCCESS"
            result["case_id"]  = case_id
            result["provider"] = current_provider_info()["provider"]
            return result
        except Exception as e:
            return {"status": "ERROR", "error": str(e), "case_id": case_id}

    # ── TOOL 5 — Risk Narrative ──────────────────────────────────────────────

    @mcp.tool()
    def llm_generate_risk_narrative(
        case_id:         str,
        applicant_name:  str,
        loan_type:       str,
        risk_score:      int,
        risk_band:       str,
        checks_passed:   list,
        warnings:        list,
        fraud_reasoning: dict,
        recommendation:  str,
    ) -> dict:
        """
        LLM LANGUAGE — Write the final Stage 2 Verification Report narrative.
        Pass outputs from orchestrate_generate_verification_summary + llm_fraud_reasoning.
        risk_band: LOW | MEDIUM | HIGH
        """
        system = (
            "You are a senior credit risk officer writing a Stage 2 loan verification report. "
            "Write clearly and professionally. Be direct about risks. "
            "Give the credit officer exactly what they need to decide immediately."
        )
        user = f"""Write the final Stage 2 Verification Report.

Case: {case_id} | Applicant: {applicant_name} | Loan: {loan_type}
Risk Score: {risk_score}/100 ({risk_band} RISK)
Recommendation: {recommendation}

Checks Passed:
{json.dumps(checks_passed, indent=2)}

Warnings & Flags:
{json.dumps(warnings, indent=2)}

Fraud Reasoning:
{json.dumps(fraud_reasoning, indent=2)}

Return JSON:
{{
  "executive_summary": "",
  "critical_findings": [],
  "applicant_must_provide": [],
  "officer_action_items": [],
  "full_narrative": ""
}}"""
        try:
            result = call_llm_json(system=system, user_text=user)
            result["status"]         = "SUCCESS"
            result["case_id"]        = case_id
            result["risk_score"]     = risk_score
            result["risk_band"]      = risk_band
            result["recommendation"] = recommendation
            result["provider"]       = current_provider_info()["provider"]
            return result
        except Exception as e:
            return {"status": "ERROR", "error": str(e), "case_id": case_id}

    # ── TOOL 6 — Analyze all documents from a zip ────────────────────────────

    @mcp.tool()
    def llm_analyze_zip(
        case_id:      str,
        zip_path:     str = "",
        zip_base64:   str = "",
        storage_path: str = "",
    ) -> dict:
        """
        Analyze ALL documents in a zip in one shot.
        Auto-detects document type from filename (best-effort).
        LLM identifies doc type from content if filename is unrecognised.
        Output is directly passable into llm_cross_check_documents.

        Priority (use ONE):
          storage_path = "LOAN-2024-001.zip"
            → downloads from Supabase bucket 'loan-documents'
            → requires SUPABASE_URL + SUPABASE_SERVICE_KEY env vars
            → use this on Horizon / production

          zip_base64 = "<base64 encoded zip content>"
            → decodes zip from string
            → use as fallback / direct upload

          zip_path = "C:\\Users\\...\\loan_docs.zip"
            → reads from local disk
            → use for local dev / Slingshot
        """
        import zipfile
        import tempfile
        import os
        import base64 as b64lib
        from pathlib import Path

        KEYWORD_MAP = {
            "aadhaar":  "AADHAAR",          "aadhar":    "AADHAAR",
            "pan":      "PAN_CARD",          "pan_card":  "PAN_CARD",
            "dci":      "DCI_CERTIFICATE",   "dental":    "DCI_CERTIFICATE",
            "degree":   "DENTAL_DEGREE_BDS", "bds":       "DENTAL_DEGREE_BDS",
            "itr":      "ITR",               "income":    "ITR",
            "bank":     "BANK_STATEMENT",    "statement": "BANK_STATEMENT",
            "gst":      "GST_CERTIFICATE",   "lease":     "LEASE_AGREEMENT",
            "project":  "PROJECT_REPORT",    "report":    "PROJECT_REPORT",
        }
        SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}

        def detect_doc_type(filename: str, used: set) -> str:
            stem = Path(filename).stem.lower().replace("-", "_").replace(" ", "_")
            for keyword, doc_type in KEYWORD_MAP.items():
                if keyword in stem and doc_type not in used:
                    return doc_type
            return f"UNKNOWN_DOC_{len(used) + 1}"

        def get_zip_bytes() -> bytes:
            """Resolve zip bytes from Supabase, base64, or local path."""

            # ── Priority 1: Supabase Storage ─────────────────────────────────
            if storage_path:
                import urllib.request
                supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
                bucket       = os.environ.get("SUPABASE_BUCKET", "loan-documents")
                service_key  = os.environ.get("SUPABASE_SERVICE_KEY", "")

                if not supabase_url:
                    raise ValueError("SUPABASE_URL env var is required when using storage_path.")

                # ── Public bucket — use direct public URL (no auth needed) ───
                public_url = f"{supabase_url}/storage/v1/object/public/{bucket}/{storage_path}"

                try:
                    req = urllib.request.Request(public_url)
                    with urllib.request.urlopen(req) as resp:
                        if resp.status != 200:
                            raise RuntimeError(f"Supabase returned HTTP {resp.status}")
                        return resp.read()
                except urllib.error.HTTPError as e:
                    raise ValueError(
                        f"Failed to download from Supabase (HTTP {e.code}). "
                        f"URL tried: {public_url} — "
                        "Check SUPABASE_URL, SUPABASE_BUCKET, and that the file exists in the bucket."
                    )

            # ── Priority 2: base64 encoded zip ────────────────────────────────
            if zip_base64:
                try:
                    return b64lib.b64decode(zip_base64)
                except Exception:
                    raise ValueError("zip_base64 is not valid base64 encoded data.")

            # ── Priority 3: local file path ───────────────────────────────────
            if zip_path:
                if not os.path.exists(zip_path):
                    raise FileNotFoundError(f"Zip file not found: {zip_path}")
                return Path(zip_path).read_bytes()

            raise ValueError(
                "No zip source provided. Pass one of: "
                "storage_path (Supabase), zip_base64, or zip_path (local)."
            )

        # ── Resolve zip source ────────────────────────────────────────────────
        input_mode = (
            "supabase"   if storage_path else
            "base64"     if zip_base64   else
            "local_path" if zip_path     else
            "none"
        )

        try:
            zip_bytes = get_zip_bytes()
        except (ValueError, FileNotFoundError, RuntimeError) as e:
            return {"status": "ERROR", "error": str(e), "case_id": case_id}

        results         = {}
        errors          = {}
        anomalies_found = []
        used_types      = set()

        # ── Extract and process ───────────────────────────────────────────────
        with tempfile.TemporaryDirectory() as tmp_dir:
            zip_tmp = os.path.join(tmp_dir, "upload.zip")
            with open(zip_tmp, "wb") as f:
                f.write(zip_bytes)

            if not zipfile.is_zipfile(zip_tmp):
                return {"status": "ERROR", "error": "Not a valid zip file.", "case_id": case_id}

            with zipfile.ZipFile(zip_tmp, "r") as zf:
                members = [
                    m for m in zf.namelist()
                    if Path(m).suffix.lower() in SUPPORTED_EXTS
                    and not Path(m).name.startswith(".")
                    and "__MACOSX" not in m
                ]
                if not members:
                    return {
                        "status":  "ERROR",
                        "error":   f"No supported files in zip. Supported: {SUPPORTED_EXTS}",
                        "case_id": case_id,
                    }
                zf.extractall(tmp_dir)

            for member in members:
                file_path = os.path.join(tmp_dir, member)
                filename  = Path(member).name
                doc_type  = detect_doc_type(filename, used_types)
                used_types.add(doc_type)

                system = (
                    "You are a forensic document analyst for loan verification. "
                    "First identify the document TYPE (PAN card, Aadhaar, DCI certificate, "
                    "bank statement, ITR, degree certificate, etc). "
                    "Then extract all visible fields and flag anomalies: "
                    "photo gender mismatch, tampering, expired dates, font inconsistencies."
                )
                user = f"""Analyze this document for loan case {case_id}.
Suggested type from filename: {doc_type}

Return JSON:
{{
  "document_type_detected": "actual document type you identified",
  "filename": "{filename}",
  "extracted_fields": {{
    "name": "",
    "id_number": "",
    "dob": "",
    "expiry_date": "",
    "issuing_authority": "",
    "address": "",
    "state": "",
    "photo_gender_estimate": "male | female | unclear | not_applicable"
  }},
  "anomalies": [],
  "document_quality": "GOOD | POOR | UNREADABLE",
  "confidence_score": 0.0,
  "llm_notes": ""
}}"""
                try:
                    doc_result = call_llm_json(
                        system     = system,
                        user_text  = user,
                        image_path = file_path,
                    )
                    doc_result["status"]         = "SUCCESS"
                    doc_result["suggested_type"] = doc_type
                    doc_result["provider"]       = current_provider_info()["provider"]
                    results[doc_type]            = doc_result
                    for anomaly in doc_result.get("anomalies", []):
                        anomalies_found.append(f"{doc_type} ({filename}): {anomaly}")
                except Exception as e:
                    errors[doc_type] = {"filename": filename, "error": str(e)}

        return {
            "status":                "SUCCESS" if results else "ERROR",
            "case_id":               case_id,
            "input_mode":            input_mode,
            "storage_path":          storage_path or None,
            "total_files_found":     len(members),
            "total_analyzed":        len(results),
            "total_errors":          len(errors),
            "results":               results,
            "errors":                errors,
            "anomalies_found":       anomalies_found,
            "ready_for_cross_check": len(results) >= 2,
            "note": (
                "Pass 'results' into llm_cross_check_documents. "
                + (f"{len(errors)} file(s) failed." if errors else "All files analyzed.")
            ),
        }