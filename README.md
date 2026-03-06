# Dental Clinic Loan Verification — FastMCP Server
## Provider-Agnostic LLM · Local (Slingshot) → Cloud (Horizon)

---

## Switch LLM Provider — Zero Code Changes

```bash
# Use Anthropic Claude (default)
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...

# Use Google Gemini
LLM_PROVIDER=google
GOOGLE_API_KEY=AIza...
```

| Provider | Default model | Override |
|---|---|---|
| anthropic | claude-sonnet-4-20250514 | `LLM_MODEL=claude-opus-4-5` |
| google | gemini-2.0-flash | `LLM_MODEL=gemini-1.5-pro` |

---

## Phase 1 — Local Dev with VS Code / Slingshot

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add your API key
```

`.vscode/mcp.json` is already in the project — VS Code and Slingshot auto-discover it.
Open the folder in VS Code and the tools appear automatically in agent mode.

To switch to Gemini in VS Code, edit `.vscode/mcp.json`:
```json
"env": { "LLM_PROVIDER": "google", "GOOGLE_API_KEY": "${env:GOOGLE_API_KEY}" }
```

```bash
python demo.py        # end-to-end demo
mcp dev server.py     # browser tool inspector
```

---

## Phase 2 — Cloud Deploy on Horizon

```bash
# 1. Push to GitHub (.env in .gitignore)
git add server.py llm_tools.py llm_client.py requirements.txt .vscode/mcp.json
git push

# 2. Connect repo at https://horizon.prefect.io
#    Horizon auto-detects requirements.txt

# 3. Set secrets in Horizon dashboard:
#    LLM_PROVIDER=anthropic
#    ANTHROPIC_API_KEY=sk-ant-...

# 4. Get live URL: https://dental-loan-verifier.fastmcp.app/mcp
```

Switch Slingshot from local → cloud by updating `.vscode/mcp.json`:
```json
{
  "servers": {
    "dental-loan-verifier": {
      "type": "http",
      "url": "https://dental-loan-verifier.fastmcp.app/mcp"
    }
  }
}
```

Zero code changes between local and cloud.

---

## File Structure

```
dental_loan_mcp/
├── server.py          ← FastMCP server + rule-based tools
├── llm_tools.py       ← LLM sub-agent tools (provider-agnostic)
├── llm_client.py      ← Provider switch: Anthropic / Google
├── demo.py            ← Local end-to-end demo
├── requirements.txt
├── .env.example       ← Copy → .env, add keys
└── .vscode/
    └── mcp.json       ← Auto-discovered by VS Code + Slingshot
```

---

## Tool Reference

| Tool | Type | LLM task |
|---|---|---|
| `doc_validate_document_set` | Rule-based stub | — |
| `pan_validate` | Rule-based stub → NSDL | — |
| `fraud_registry_check` | Rule-based stub | — |
| `aadhaar_verify` | Rule-based stub → UIDAI | — |
| `dci_credential_verify` | Rule-based stub → DCI | — |
| `gst_verify` | Rule-based stub → GST | — |
| `llm_health_check` | LLM | Shows active provider/model |
| `llm_analyze_document` | LLM Vision | Reads doc image, detects photo gender |
| `llm_cross_check_documents` | LLM Reasoning | Cross-doc inconsistencies |
| `llm_assess_name_match` | LLM Language | Indian name judgment |
| `llm_fraud_reasoning` | LLM Reasoning | Fraud signal clustering |
| `llm_generate_risk_narrative` | LLM Language | Final report writing |
| `orchestrate_stage2_verification` | Orchestrator | Full execution plan |
