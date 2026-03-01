from fastmcp import FastMCP
import json
from datetime import datetime
from pathlib import Path

mcp = FastMCP("Sapient Contract PDF POC - Kabilan")

#output_dir = Path(__file__).parent / "output"
#output_dir.mkdir(exist_ok=True)
output_dir = "tmp"

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
    try:
        data = json.loads(data_json)
        sections = json.loads(sections_json)
        
        html = f"""<!DOCTYPE html>
<html><head><title>{data.get('contract_title', 'Contract')}</title>
<style>body{{font-family:Arial;margin:40px;}} .header{{border-bottom:2px solid #333;}}</style></head>
<body>
<div class="header"><h1>{data.get('contract_title', 'Contract POC')}</h1></div>
<p><strong>Contract #:</strong> {data.get('contract_number', 'POC-001')}</p>
<p><strong>Date:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M IST')}</p>
<p><strong>Parties:</strong> {data.get('party_a', 'Sapient')} & {data.get('party_b', 'Client')}</p>

<h2>Sections:</h2><ul>"""
        
        for section, include in sections.items():
            if include: html += f"<li>✅ {section.title()}</li>"
        
        html += """</ul><p><em>Sapient POC COMPLETE | Next: WeasyPrint + S3</em></p></body></html>"""
        
        # HTML + PDF both!
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        html_path = output_dir / f"{template_name}_{timestamp}.html"
        pdf_path = output_dir / f"{template_name}_{timestamp}.pdf"

        html_path.write_text(html, encoding='utf-8-sig')

        try:
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import A4
            pdf_path = html_path.with_suffix('.pdf')
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
            c.drawString(50, 50, "Sapient POC COMPLETE | Next: S3 + Agentforce")
            c.save()
            
            return f"HTML: {html_path.name} + PDF: {pdf_path.name}"
        except Exception as pdf_error:
            return f"HTML: {html_path.name} | PDF error: {str(pdf_error)}"

    except Exception as e:
        return f"❌ Error: {str(e)}"


@mcp.tool()
async def list_templates() -> str:
    """Available templates."""
    return json.dumps({"templates": ["msa", "sow", "nda"], "status": "POC ready"})

if __name__ == "__main__":
    mcp.run(transport="stdio")
