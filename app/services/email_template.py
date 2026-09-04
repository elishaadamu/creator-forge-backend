"""
Luxury Venture Studio Email Template & Markdown Formatter.

Provides:
1. Centralized Studio Branding & Logo configuration.
2. Flawless Markdown-to-HTML conversion with inline styles for email clients.
3. Fully responsive (mobile + desktop) fluid HTML email layout.
4. Embedded Concept Mockup Visual Showcase for Step 5 & Step 6 creator proposals.
"""
import re
import html
from typing import Optional, List, Dict, Any
import markdown

from app.config import settings

# ==============================================================================
# STUDIO BRANDING & LOGO CONFIGURATION
# You can change the studio logo URL and studio details here, in app/config.py,
# or via environment variables in .env (STUDIO_LOGO_URL, STUDIO_NAME).
# ==============================================================================
STUDIO_NAME: str = getattr(settings, "STUDIO_NAME", "Creator Forge")
STUDIO_TAGLINE: str = getattr(settings, "STUDIO_TAGLINE", "Venture Studio & Co-Launch Incubation")

# High-resolution studio logo mark. Change this URL to your own logo PNG or SVG anytime:
STUDIO_LOGO_URL: str = (
    getattr(settings, "STUDIO_LOGO_URL", "")
    or "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=240&auto=format&fit=crop&q=80"
)

# Default curated SaaS visual mockups per category (high-performance Unsplash previews)
CATEGORY_MOCKUP_IMAGES = {
    "tech": "https://images.unsplash.com/photo-1551288049-bebda4e38f71?w=1200&auto=format&fit=crop&q=80",
    "productivity": "https://images.unsplash.com/photo-1460925895917-afdab827c52f?w=1200&auto=format&fit=crop&q=80",
    "finance": "https://images.unsplash.com/photo-1642543492481-44e81e3914a7?w=1200&auto=format&fit=crop&q=80",
    "video_editing": "https://images.unsplash.com/photo-1574717024653-61fd2cf4d44d?w=1200&auto=format&fit=crop&q=80",
    "gaming": "https://images.unsplash.com/photo-1542751371-adc38448a05e?w=1200&auto=format&fit=crop&q=80",
    "data_ai": "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=1200&auto=format&fit=crop&q=80",
    "default": "https://images.unsplash.com/photo-1551288049-bebda4e38f71?w=1200&auto=format&fit=crop&q=80",
}


def _clean_and_extract_ref_tokens(raw_text: str) -> tuple[str, str]:
    """
    Extracts internal tracking tokens like 'Ref: [CF-STAGE:... | CF-CID:...]'
    so they don't clutter the main email text or break markdown parsing.
    Returns (cleaned_body, extracted_token).
    """
    token = ""
    token_match = re.search(r'(?:---\s*)?Ref:\s*(\[[^\]]+\])', raw_text, re.IGNORECASE)
    if token_match:
        token = token_match.group(1).strip()
        raw_text = raw_text[:token_match.start()] + raw_text[token_match.end():]
    
    # Also strip stray standalone [CF-STAGE:...] tokens if any
    token_match2 = re.search(r'(\[CF-[^\]]+\])', raw_text)
    if token_match2 and not token:
        token = token_match2.group(1).strip()
        raw_text = raw_text[:token_match2.start()] + raw_text[token_match2.end():]

    # Clean trailing dashes or excess whitespace
    cleaned_body = re.sub(r'---\s*$', '', raw_text.strip()).strip()
    return cleaned_body, token


def render_concept_showcase_html(
    concepts: Optional[List[Dict[str, Any]]] = None,
    concept_image_url: Optional[str] = None,
    creator_name: str = ""
) -> str:
    """
    Renders an eye-catching, responsive concept mockup card for Step 5 & Step 6 emails.
    Shows the app visual image, browser chrome, key metrics, and features.
    """
    if not concepts and not concept_image_url:
        return ""

    top_concept = concepts[0] if (concepts and len(concepts) > 0) else {}
    app_name = top_concept.get("name") or top_concept.get("title") or "Custom Creator SaaS"
    tagline = top_concept.get("tagline") or top_concept.get("summary") or top_concept.get("description") or "Tailored software suite engineered for your community"
    pricing = top_concept.get("pricing") or "$29/mo Starter • $79/mo Pro"
    problem = top_concept.get("problem") or top_concept.get("description") or ""
    mockup_data = top_concept.get("mockup") or {}

    app_url = mockup_data.get("appUrl") or f"{app_name.lower().replace(' ', '')}.app"
    primary_metric = mockup_data.get("primaryMetric") or "$18.4K Projected MRR"
    active_metric = mockup_data.get("activeMetric") or "1,240 Active Users"
    efficiency_metric = mockup_data.get("efficiencyMetric") or "14-Day MVP Launch"

    # Select best visual image: custom image URL > concept.imageUrl > category fallback
    active_image = concept_image_url or top_concept.get("imageUrl") or top_concept.get("image_url")
    if not active_image:
        niche_key = "default"
        for k in CATEGORY_MOCKUP_IMAGES.keys():
            if k in (top_concept.get("category", "") or "").lower() or k in (tagline or "").lower():
                niche_key = k
                break
        active_image = CATEGORY_MOCKUP_IMAGES.get(niche_key, CATEGORY_MOCKUP_IMAGES["default"])

    features_html = ""
    key_features = top_concept.get("keyFeatures") or top_concept.get("features") or []
    if key_features and isinstance(key_features, list):
        f_items = "".join(
            f'<li style="margin-bottom:6px;line-height:1.5;color:#cbd5e1;font-size:13px;">'
            f'<span style="color:#a855f7;font-weight:bold;margin-right:6px;">✓</span>{html.escape(str(f))}</li>'
            for f in key_features[:4]
        )
        features_html = f'''
        <div style="margin-top:14px;padding-top:12px;border-top:1px solid rgba(255,255,255,0.08);">
          <div style="font-size:11px;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:0.8px;margin-bottom:8px;">
            Key Built-In Features:
          </div>
          <ul style="margin:0;padding:0;list-style:none;">
            {f_items}
          </ul>
        </div>
        '''

    problem_html = ""
    if problem:
        problem_html = f'''
        <div style="background:rgba(15,23,42,0.6);border:1px solid rgba(255,255,255,0.06);border-radius:10px;padding:10px 14px;margin-top:12px;font-size:12px;color:#94a3b8;line-height:1.5;">
          <strong style="color:#f8fafc;">Core Bottleneck Solved:</strong> {html.escape(problem)}
        </div>
        '''

    image_element = ""
    if active_image:
        image_element = f'''
        <div style="margin:14px 0 8px 0;border-radius:12px;overflow:hidden;border:1px solid rgba(255,255,255,0.1);background:#020617;box-shadow:0 12px 24px rgba(0,0,0,0.4);">
          <img src="{active_image}" alt="{html.escape(app_name)} Visual Mockup" width="556" style="width:100%;max-width:556px;height:auto;display:block;object-fit:cover;" class="responsive-img" />
        </div>
        '''

    return f'''
    <!-- CONCEPT SHOWCASE CARD -->
    <table width="100%" border="0" cellspacing="0" cellpadding="0" style="margin:24px 0;background:linear-gradient(145deg,#131a29 0%,#0c101a 100%);border-radius:16px;border:1px solid #2d3748;box-shadow:0 14px 30px rgba(0,0,0,0.45);overflow:hidden;">
      <!-- Window Chrome Header -->
      <tr>
        <td style="padding:12px 18px;background:#090d16;border-bottom:1px solid rgba(255,255,255,0.08);">
          <table width="100%" border="0" cellspacing="0" cellpadding="0">
            <tr>
              <td align="left" style="vertical-align:middle;">
                <span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#ef4444;margin-right:6px;"></span>
                <span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#f59e0b;margin-right:6px;"></span>
                <span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#10b981;margin-right:12px;"></span>
                <span style="font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;color:#94a3b8;background:rgba(255,255,255,0.05);padding:3px 10px;border-radius:6px;border:1px solid rgba(255,255,255,0.08);">
                  https://{html.escape(app_url)}
                </span>
              </td>
              <td align="right" style="vertical-align:middle;">
                <span style="background:rgba(16,185,129,0.15);border:1px solid rgba(16,185,129,0.35);color:#6ee7b7;padding:3px 8px;border-radius:6px;font-size:10px;font-weight:800;letter-spacing:0.5px;text-transform:uppercase;">
                  MVP Ready To Launch
                </span>
              </td>
            </tr>
          </table>
        </td>
      </tr>
      <!-- Card Main Body -->
      <tr>
        <td style="padding:20px 22px;">
          <!-- Concept Title & Badge -->
          <table width="100%" border="0" cellspacing="0" cellpadding="0">
            <tr>
              <td>
                <div style="font-size:18px;font-weight:900;color:#ffffff;letter-spacing:-0.4px;">
                  {html.escape(app_name)}
                </div>
                <div style="font-size:13px;color:#a855f7;font-weight:600;margin-top:2px;">
                  {html.escape(tagline)}
                </div>
              </td>
              <td align="right" style="vertical-align:top;">
                <span style="font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11px;font-weight:700;color:#38bdf8;background:rgba(56,189,248,0.1);padding:4px 10px;border-radius:8px;border:1px solid rgba(56,189,248,0.25);white-space:nowrap;">
                  {html.escape(pricing)}
                </span>
              </td>
            </tr>
          </table>

          {image_element}

          <!-- Metric Highlights Grid -->
          <table width="100%" border="0" cellspacing="0" cellpadding="0" style="margin-top:14px;">
            <tr>
              <td width="32%" style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);border-radius:10px;padding:10px;text-align:center;" class="metric-col">
                <div style="font-size:10px;color:#94a3b8;text-transform:uppercase;font-weight:700;letter-spacing:0.5px;">Est. Revenue</div>
                <div style="font-size:14px;font-weight:800;color:#34d399;margin-top:3px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;">{html.escape(primary_metric)}</div>
              </td>
              <td width="2%">&nbsp;</td>
              <td width="32%" style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);border-radius:10px;padding:10px;text-align:center;" class="metric-col">
                <div style="font-size:10px;color:#94a3b8;text-transform:uppercase;font-weight:700;letter-spacing:0.5px;">Target Users</div>
                <div style="font-size:14px;font-weight:800;color:#c084fc;margin-top:3px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;">{html.escape(active_metric)}</div>
              </td>
              <td width="2%">&nbsp;</td>
              <td width="32%" style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);border-radius:10px;padding:10px;text-align:center;" class="metric-col">
                <div style="font-size:10px;color:#94a3b8;text-transform:uppercase;font-weight:700;letter-spacing:0.5px;">Build Speed</div>
                <div style="font-size:14px;font-weight:800;color:#38bdf8;margin-top:3px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;">{html.escape(efficiency_metric)}</div>
              </td>
            </tr>
          </table>

          {problem_html}
          {features_html}
        </td>
      </tr>
    </table>
    '''


def convert_markdown_to_clean_html(markdown_text: str) -> str:
    """
    Converts markdown text to clean, email-safe HTML with inline CSS.
    Handles headings, bold, italics, links, lists, blockquotes, and CTA portal buttons.
    """
    if not markdown_text:
        return ""

    # 1. Normalize bullet characters (•, -, *) to standard markdown lists
    lines = markdown_text.splitlines()
    normalized_lines = []
    
    for line in lines:
        stripped = line.strip()
        # If line starts with unicode bullet •, convert to markdown *
        if stripped.startswith("•"):
            indent_count = len(line) - len(line.lstrip())
            indent = " " * indent_count
            normalized_lines.append(f"{indent}* {stripped[1:].strip()}")
        else:
            normalized_lines.append(line)

    clean_md = "\n".join(normalized_lines)

    # 2. Check for portal/preview URL to render an eye-catching CTA button
    url_match = re.search(r'(https?://[^\s<"\']+)', clean_md)
    cta_btn_html = ""
    if url_match:
        raw_url = url_match.group(1).rstrip(".,)")
        is_portal = any(k in raw_url.lower() for k in ["portal", "launch", "preview", "project", "review"])
        cta_label = "Access Co-Founder Portal →" if is_portal else "Review Software Concepts →"
        
        cta_btn_html = f'''
        <div style="margin:26px 0 16px 0;text-align:center;">
          <a href="{raw_url}" target="_blank" class="mobile-btn" style="display:inline-block;padding:15px 34px;background:linear-gradient(135deg,#9333ea 0%,#6366f1 100%);color:#ffffff;font-size:15px;font-weight:800;text-decoration:none;border-radius:12px;box-shadow:0 10px 25px rgba(147,51,234,0.35);border:1px solid rgba(255,255,255,0.2);letter-spacing:0.3px;">
            {cta_label}
          </a>
          <div style="margin-top:8px;font-size:11px;color:#94a3b8;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;">
            Direct Secure Link: <a href="{raw_url}" style="color:#a855f7;text-decoration:underline;">{raw_url}</a>
          </div>
        </div>
        '''

    # 3. Parse with Python markdown parser
    raw_html = markdown.markdown(
        clean_md,
        extensions=["extra", "sane_lists", "nl2br"]
    )

    # 4. Post-process and inject inline CSS for email client rendering
    # Paragraphs
    raw_html = re.sub(
        r'<p>(.*?)</p>',
        r'<p style="margin:0 0 16px 0;line-height:1.7;color:#cbd5e1;font-size:15px;">\1</p>',
        raw_html,
        flags=re.DOTALL
    )

    # Headings
    raw_html = re.sub(
        r'<h1>(.*?)</h1>',
        r'<h1 style="margin:24px 0 14px 0;font-size:22px;font-weight:900;color:#ffffff;letter-spacing:-0.5px;line-height:1.3;">\1</h1>',
        raw_html
    )
    raw_html = re.sub(
        r'<h2>(.*?)</h2>',
        r'<h2 style="margin:22px 0 12px 0;font-size:18px;font-weight:800;color:#ffffff;letter-spacing:-0.4px;line-height:1.35;">\1</h2>',
        raw_html
    )
    raw_html = re.sub(
        r'<h3>(.*?)</h3>',
        r'<h3 style="margin:18px 0 10px 0;font-size:16px;font-weight:800;color:#ffffff;letter-spacing:-0.3px;line-height:1.4;">\1</h3>',
        raw_html
    )

    # Bold & Strong
    raw_html = re.sub(
        r'<strong>(.*?)</strong>',
        r'<strong style="color:#ffffff;font-weight:700;">\1</strong>',
        raw_html
    )

    # Emphasis & Italics
    raw_html = re.sub(
        r'<em>(.*?)</em>',
        r'<em style="color:#e2e8f0;font-style:italic;">\1</em>',
        raw_html
    )

    # Unordered Lists
    raw_html = re.sub(
        r'<ul>',
        r'<ul style="margin:14px 0 18px 0;padding-left:20px;color:#a855f7;line-height:1.65;">',
        raw_html
    )

    # Ordered Lists
    raw_html = re.sub(
        r'<ol>',
        r'<ol style="margin:14px 0 18px 0;padding-left:22px;color:#a855f7;line-height:1.65;">',
        raw_html
    )

    # List Items
    raw_html = re.sub(
        r'<li>(.*?)</li>',
        r'<li style="margin-bottom:8px;line-height:1.65;color:#cbd5e1;font-size:14px;"><span style="color:#cbd5e1;">\1</span></li>',
        raw_html,
        flags=re.DOTALL
    )

    # Blockquotes
    raw_html = re.sub(
        r'<blockquote>\s*<p>(.*?)</p>\s*</blockquote>',
        r'<blockquote style="margin:18px 0;padding:12px 18px;border-left:3px solid #9333ea;background:rgba(147,51,234,0.08);border-radius:0 10px 10px 0;color:#e2e8f0;font-size:14px;line-height:1.6;font-style:italic;">\1</blockquote>',
        raw_html,
        flags=re.DOTALL
    )

    # Horizontal Rules
    raw_html = re.sub(
        r'<hr\s*/?>',
        r'<hr style="border:none;border-top:1px solid #1e293b;margin:24px 0;">',
        raw_html
    )

    # Anchor links
    raw_html = re.sub(
        r'<a\s+href="([^"]+)">([^<]+)</a>',
        r'<a href="\1" target="_blank" style="color:#a855f7;font-weight:600;text-decoration:underline;">\2</a>',
        raw_html
    )

    # Code tags
    raw_html = re.sub(
        r'<code>(.*?)</code>',
        r'<code style="font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:13px;background:rgba(255,255,255,0.08);color:#f1f5f9;padding:2px 6px;border-radius:4px;">\1</code>',
        raw_html
    )

    # Append CTA button if present and not already embedded
    if cta_btn_html and "mobile-btn" not in raw_html:
        raw_html = f"{raw_html}\n{cta_btn_html}"

    return raw_html


def format_luxury_html_email(
    body_text: str,
    subject: str,
    creator_name: str = "",
    tracking_token: str = "",
    concept_image_url: Optional[str] = None,
    concepts: Optional[List[Dict[str, Any]]] = None,
    logo_url: Optional[str] = None,
    studio_name: Optional[str] = None
) -> str:
    """
    Master Responsive Luxury Venture Studio Email Formatter.
    Creates a responsive, retina-sharp, Human-Crafted Venture Studio email.
    """
    clean_body, extracted_token = _clean_and_extract_ref_tokens(body_text)
    active_token = tracking_token or extracted_token

    active_logo_url = logo_url or STUDIO_LOGO_URL
    active_studio_name = studio_name or STUDIO_NAME

    # Convert markdown body into styled HTML
    formatted_body_html = convert_markdown_to_clean_html(clean_body)

    # Render concept mockup card if concepts or concept image are present
    concept_card_html = render_concept_showcase_html(
        concepts=concepts,
        concept_image_url=concept_image_url,
        creator_name=creator_name
    )

    # Reference footer token block
    ref_block = ""
    if active_token:
        ref_block = f'''
        <div style="border-top:1px solid #1e293b;margin-top:28px;padding-top:14px;font-size:11px;color:#64748b;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;">
          Studio Reference: <span style="color:#94a3b8;">{html.escape(active_token)}</span>
        </div>
        '''

    # Logo element: image + fallback wordmark
    logo_img_tag = ""
    if active_logo_url:
        logo_img_tag = f'''
        <img src="{active_logo_url}" alt="{html.escape(active_studio_name)} Logo" height="34" style="height:34px;max-height:34px;width:auto;display:inline-block;vertical-align:middle;margin-right:12px;border-radius:6px;" class="header-logo" />
        '''

    return f"""<!DOCTYPE html>
<html lang="en" xmlns="http://www.w3.org/1999/xhtml" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="X-UA-Compatible" content="IE=edge">
  <meta name="x-apple-disable-message-reformatting">
  <title>{html.escape(subject)}</title>
  <!--[if mso]>
  <noscript>
    <xml>
      <o:OfficeDocumentSettings>
        <o:PixelsPerInch>96</o:PixelsPerInch>
      </o:OfficeDocumentSettings>
    </xml>
  </noscript>
  <![endif]-->
  <style>
    html, body {{
      margin: 0 !important;
      padding: 0 !important;
      height: 100% !important;
      width: 100% !important;
      background-color: #07090e;
      -webkit-text-size-adjust: 100%;
      -ms-text-size-adjust: 100%;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
    }}
    table, td {{
      mso-table-lspace: 0pt !important;
      mso-table-rspace: 0pt !important;
    }}
    table {{
      border-spacing: 0 !important;
      border-collapse: collapse !important;
      table-layout: fixed !important;
      margin: 0 auto !important;
    }}
    img {{
      -ms-interpolation-mode: bicubic;
      max-width: 100%;
    }}
    a {{
      text-decoration: none;
    }}
    /* Responsive Media Queries */
    @media only screen and (max-width: 600px) {{
      .email-container {{
        width: 100% !important;
        max-width: 100% !important;
        border-radius: 0 !important;
        border-left: none !important;
        border-right: none !important;
      }}
      .content-padding {{
        padding: 24px 16px !important;
      }}
      .header-padding {{
        padding: 20px 16px !important;
      }}
      .metric-col {{
        display: block !important;
        width: 100% !important;
        margin-bottom: 8px !important;
      }}
      .mobile-btn {{
        display: block !important;
        width: 100% !important;
        box-sizing: border-box !important;
        text-align: center !important;
        padding: 14px 20px !important;
      }}
      .header-logo {{
        height: 28px !important;
        max-height: 28px !important;
      }}
    }}
  </style>
</head>
<body style="margin:0;padding:0;background-color:#07090e;color:#f8fafc;">
  <!-- Full Width Background Wrapper -->
  <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color:#07090e;padding:32px 12px;">
    <tr>
      <td align="center" style="vertical-align:top;">
        <!-- Email Card Container (600px fluid) -->
        <table width="100%" border="0" cellspacing="0" cellpadding="0" class="email-container" style="max-width:620px;background:#0f172a;border-radius:18px;border:1px solid #1e293b;overflow:hidden;box-shadow:0 24px 48px rgba(0,0,0,0.6);">
          
          <!-- Top Accent Glow Line -->
          <tr>
            <td height="3" style="background:linear-gradient(90deg,#9333ea 0%,#6366f1 50%,#38bdf8 100%);font-size:1px;line-height:1px;">&nbsp;</td>
          </tr>

          <!-- Header -->
          <tr>
            <td class="header-padding" style="padding:26px 32px;background:linear-gradient(135deg,#13192b 0%,#0f172a 100%);border-bottom:1px solid #1e293b;">
              <table width="100%" border="0" cellspacing="0" cellpadding="0">
                <tr>
                  <td align="left" style="vertical-align:middle;">
                    <table border="0" cellspacing="0" cellpadding="0">
                      <tr>
                        <td style="vertical-align:middle;">
                          {logo_img_tag}
                        </td>
                        <td style="vertical-align:middle;">
                          <div style="font-size:18px;font-weight:900;color:#ffffff;letter-spacing:-0.5px;line-height:1.2;">
                            <span style="color:#a855f7;">{html.escape(active_studio_name.split()[0].upper())}</span> {html.escape(" ".join(active_studio_name.split()[1:]).upper() if len(active_studio_name.split()) > 1 else "STUDIO")}
                          </div>
                          <div style="font-size:11px;color:#94a3b8;font-weight:600;text-transform:uppercase;letter-spacing:1px;margin-top:2px;">
                            {html.escape(STUDIO_TAGLINE)}
                          </div>
                        </td>
                      </tr>
                    </table>
                  </td>
                  <td align="right" style="vertical-align:middle;">
                    <span style="background:rgba(168,85,247,0.15);border:1px solid rgba(168,85,247,0.4);color:#d8b4fe;padding:5px 12px;border-radius:20px;font-size:11px;font-weight:800;letter-spacing:0.4px;white-space:nowrap;">
                      50/50 Co-Founder
                    </span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Body Content Area -->
          <tr>
            <td class="content-padding" style="padding:32px 32px 28px 32px;background-color:#0f172a;">
              {formatted_body_html}
              {concept_card_html}
              {ref_block}
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding:22px 32px;background:#090d16;border-top:1px solid #1e293b;font-size:12px;color:#64748b;text-align:center;line-height:1.6;">
              <div style="font-weight:700;color:#94a3b8;margin-bottom:4px;">
                {html.escape(active_studio_name)}
              </div>
              <div style="color:#64748b;margin-bottom:8px;">
                Co-launching high-margin software ventures with digital creators under a 50/50 model.
              </div>
              <div style="font-size:11px;color:#475569;">
                100% Engineering Funded • Zero Financial Cost to Creator • Automated Direct Payouts
              </div>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""
