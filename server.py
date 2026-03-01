from fastmcp import FastMCP
import json
from datetime import datetime
from pathlib import Path
import tempfile
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

mcp = FastMCP("Sapient Contract PDF POC - Kabilan")

output_dir = Path(tempfile.gettempdir())

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")


async def upload_to_supabase(pdf_path: Path, filename: str) -> str:
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{SUPABASE_URL}/storage/v1/object/contracts/{filename}",
            headers={
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/pdf",
                "x-upsert": "true"
            },
            content=pdf_bytes
        )

    if response.status_code not in (200, 201):
        raise Exception(f"Supabase upload failed: {response.status_code} {response.text}")

    return f"{SUPABASE_URL}/storage/v1/object/public/contracts/{filename}"


@mcp.tool()
async def hello_contract(template_name: str = "msa") -> str:
    """Test MCP POC connection."""
    return f"✅ Kabilan POC SUCCESS! Ready for {template_name} generation."


@mcp.tool()
async def generate_contract_pdf(
    template_name: str,
    data_json: str,
    sections_json: str = '{"introduction": true, "payment_terms": true}'
) -> str:
    """Generate a contract PDF and return a download URL."""
    try:
        data = json.loads(data_json)
        sections = json.loads(sections_json)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{template_name}_{timestamp}.pdf"
        pdf_path = output_dir / filename

        # Generate PDF with ReportLab
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4
        c = canvas.Canvas(str(pdf_path), pagesize=A4)
        width, height = A4

        c.setFont("Helvetica-Bold", 20)
        c.drawString(50, height - 60, data.get('contract_title', 'Contract'))

        c.setFont("Helvetica", 12)
        c.drawString(50, height - 100, f"Contract #: {data.get('contract_number', 'POC-001')}")
        c.drawString(50, height - 120, f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M IST')}")
        c.drawString(50, height - 140, f"Parties: {data.get('party_a', 'Sapient')} & {data.get('party_b', 'Client')}")

        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, height - 180, "Sections:")

        y = height - 210
        for section, include in sections.items():
            if include:
                c.setFont("Helvetica", 12)
                c.drawString(70, y, f"- {section.replace('_', ' ').title()}")
                y -= 20

        c.setFont("Helvetica-Oblique", 10)
        c.drawString(50, 50, "Sapient POC COMPLETE | Next: Agentforce")
        c.save()

        # Upload to Supabase
        url = await upload_to_supabase(pdf_path, filename)
        return f"✅ Contract PDF ready!\nDownload: {url}"

    except Exception as e:
        return f"❌ Error generating contract PDF: {str(e)}"


@mcp.tool()
async def list_templates() -> str:
    """List available contract templates."""
    return json.dumps({"templates": ["msa", "sow", "nda"], "status": "POC ready"})

if __name__ == "__main__":
    import sys
    if "--stdio" in sys.argv:
        mcp.run(transport="stdio")
    else:
        mcp.run(transport="streamable-http")
