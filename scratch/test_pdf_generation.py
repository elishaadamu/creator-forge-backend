import os
from fpdf import FPDF
from fpdf.enums import XPos, YPos
from datetime import datetime

class StyledPDF(FPDF):
    def header(self):
        # Draw a sleek top banner
        self.set_fill_color(15, 23, 42) # Dark Slate (slate-900)
        self.rect(0, 0, 210, 35, 'F')
        
        # Title
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", size=16, style="B")
        # Go to x=10, y=10
        self.set_xy(10, 10)
        self.cell(190, 8, text="CREATOR FORGE", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L")
        
        self.set_font("Helvetica", size=9)
        self.set_text_color(148, 163, 184) # slate-400
        self.cell(190, 5, text="SECURITY KEY BACKUP | CONFIDENTIAL", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L")
        
        self.set_y(45)

    def footer(self):
        self.set_y(-25)
        self.set_font("Helvetica", size=8, style="I")
        self.set_text_color(148, 163, 184)
        # Line
        self.set_draw_color(226, 232, 240)
        self.line(10, self.get_y(), 200, self.get_y())
        self.set_y(self.get_y() + 2)
        
        self.cell(100, 10, text=f"Generated on {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')} | Creator Forge Auth Layer", new_x=XPos.RIGHT, new_y=YPos.TOP, align="L")
        self.cell(90, 10, text=f"Page {self.page_no()}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="R")

def generate_test_pdf():
    pdf = StyledPDF()
    pdf.add_page()
    pdf.ln(5)
    
    # Intro text
    pdf.set_text_color(71, 85, 105) # slate-600
    pdf.set_font("Helvetica", size=10)
    pdf.multi_cell(
        190, 5, 
        text="Security Notice: For your privacy and protection, Creator Forge enforces in-memory transient key storage. "
             "These keys are never stored in databases or local browser caches (localStorage). "
             "Keep this PDF backup secure. You can copy-paste these keys when launching the console in a new session."
    )
    pdf.ln(8)
    
    keys_data = [
        ("Apify Token", os.environ.get("APIFY_API_KEY", "[APIFY_API_KEY not set]")),
        ("YouTube API Key", os.environ.get("YOUTUBE_API_KEY", "[YOUTUBE_API_KEY not set]")),
        ("Google Gemini Key", os.environ.get("GEMINI_API_KEY", "[GEMINI_API_KEY not set]")),
        ("Together.ai Key", os.environ.get("TOGETHER_AI_KEY", "[TOGETHER_AI_KEY not set]"))
    ]
    
    for label, val in keys_data:
        # Label
        pdf.set_text_color(15, 23, 42) # Slate-900
        pdf.set_font("Helvetica", size=10, style="B")
        pdf.cell(190, 6, text=label, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        
        # Styled Box for the Key
        pdf.set_fill_color(248, 250, 252) # slate-50
        pdf.set_draw_color(226, 232, 240) # slate-200
        pdf.set_text_color(30, 41, 59) # slate-800
        pdf.set_font("Courier", size=9)
        
        # Calculate padding/height
        # We can use multi_cell to handle text wrapping and draw a nice border
        pdf.multi_cell(190, 8, text=val if val.strip() else "[Not Configured]", border=1, fill=True)
        pdf.ln(4)
        
    pdf.output("scratch/test_keys_output.pdf")
    print("PDF generated successfully.")

if __name__ == "__main__":
    generate_test_pdf()
