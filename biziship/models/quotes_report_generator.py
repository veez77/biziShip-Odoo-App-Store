from datetime import datetime, timedelta
from odoo import fields
import html


class QuotesReportGenerator:
    """Generate self-contained HTML report for LTL freight quotes."""

    @staticmethod
    def escape_html(text):
        """Safely escape HTML special characters."""
        if not text:
            return ""
        return html.escape(str(text))

    @staticmethod
    def format_currency(amount, currency="USD"):
        """Format amount as currency string."""
        if amount is None:
            return "—"
        return f"${amount:,.2f}"

    @staticmethod
    def generate_quotes_html_report(shipment_data, quotes, markup_config=None, apply_markup=False):
        """
        Generate self-contained HTML report for quotes.

        Args:
            shipment_data: dict with origin/dest, freight lines, accessorials
                {
                    'request_id': str,
                    'origin_company': str,
                    'origin_address': str,
                    'origin_address2': str,
                    'origin_city': str,
                    'origin_state': str,
                    'origin_zip': str,
                    'origin_phone': str,
                    'destination_company': str,
                    'destination_address': str,
                    'destination_address2': str,
                    'destination_city': str,
                    'destination_state': str,
                    'destination_zip': str,
                    'destination_phone': str,
                    'freight_lines': [...],  # cargo line items
                    'accessorials': [...],
                    'special_instructions': str,
                }
            quotes: list of quote dicts from backend
                {
                    'quote_id': str,
                    'carrier_name': str,
                    'carrier_code': str,
                    'service_level': str,
                    'service_level_description': str,
                    'transit_days': int|null,
                    'delivery_date': str|null,  # ISO date
                    'total_charge': float|null,
                    'currency': str,
                    'valid_until': str|null,  # ISO date (not used; computed as today+2)
                    'carrier_quote_number': str|null,
                    'carrier_liability_new': float|null,
                    'carrier_liability_used': float|null,
                }
            markup_config: dict with enabled, ruleType, amounts (if enabled)
            apply_markup: bool, whether to apply markup to prices

        Returns:
            str: self-contained HTML document
        """
        from odoo.addons.biziship.models.quotes_markup import QuotesMarkup

        import logging
        _logger = logging.getLogger(__name__)

        request_id = shipment_data.get('request_id', 'Unknown')
        request_id_short = request_id[:8] if request_id else "Unknown"
        po_number = shipment_data.get('po_number', '')

        _logger.info(f"QuotesReportGenerator: request_id={request_id}, po_number='{po_number}', shipment_data keys={list(shipment_data.keys())}")

        # Sort quotes by total_charge ascending
        sorted_quotes = sorted(
            quotes,
            key=lambda q: q.get('total_charge') or float('inf')
        )

        # Apply markup if enabled and requested
        if apply_markup and markup_config and markup_config.get('enabled'):
            sorted_quotes = [
                {
                    **q,
                    'total_charge': QuotesMarkup.apply_markup(
                        q.get('total_charge'),
                        markup_config
                    ) if q.get('total_charge') is not None else None,
                    '_original_charge': q.get('total_charge'),  # track original for later if needed
                }
                for q in sorted_quotes
            ]

        # Compute "Valid Until" as today + 2 days
        today = datetime.now()
        valid_until = today + timedelta(days=2)
        valid_until_str = valid_until.strftime('%B %d, %Y')

        # Format timestamp for report
        export_time = today.strftime('%A, %B %d, %Y, %I:%M %p')

        # Build address strings
        origin_addr = QuotesReportGenerator._format_address(shipment_data, 'origin')
        dest_addr = QuotesReportGenerator._format_address(shipment_data, 'destination')

        # Build freight items table
        freight_items_html = QuotesReportGenerator._build_freight_items_table(shipment_data.get('freight_lines', []))

        # Build quotes table
        quotes_table_html = QuotesReportGenerator._build_quotes_table(sorted_quotes, valid_until_str)

        # Escape all user inputs
        request_id_esc = QuotesReportGenerator.escape_html(request_id)
        origin_company_esc = QuotesReportGenerator.escape_html(shipment_data.get('origin_company'))
        dest_company_esc = QuotesReportGenerator.escape_html(shipment_data.get('destination_company'))
        origin_phone_esc = QuotesReportGenerator.escape_html(shipment_data.get('origin_phone'))
        dest_phone_esc = QuotesReportGenerator.escape_html(shipment_data.get('destination_phone'))

        # Build BiziShip logo SVG (simple version)
        logo_svg = QuotesReportGenerator._get_logo_svg()

        # Assemble HTML
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BiziShip Carrier Quotes – {request_id_esc}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; font-size: 13px; color: #1a1a1a; background: #f5f5f5; padding: 32px 24px; }}
  .page {{ max-width: 1260px; margin: 0 auto; background: #fff; border-radius: 10px; box-shadow: 0 2px 16px rgba(0,0,0,.10); overflow: hidden; }}
  .header {{ background: #1a3c6e; color: #fff; padding: 28px 36px; display: flex; justify-content: space-between; align-items: flex-start; }}
  .header h1 {{ font-size: 22px; font-weight: 700; letter-spacing: -.3px; }}
  .header .sub {{ margin-top: 4px; font-size: 12px; opacity: .75; }}
  .header .meta {{ text-align: right; font-size: 12px; opacity: .8; line-height: 1.7; }}
  .body {{ padding: 28px 36px; display: flex; flex-direction: column; gap: 28px; }}
  .section-title {{ font-size: 11px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; color: #1a3c6e; border-bottom: 2px solid #1a3c6e; padding-bottom: 5px; margin-bottom: 14px; }}
  .addr-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
  .addr-card {{ background: #f8fafd; border: 1px solid #dce6f5; border-radius: 8px; padding: 16px 18px; line-height: 1.65; }}
  .addr-card .label {{ font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .07em; color: #1a3c6e; margin-bottom: 6px; }}
  .addr-card strong {{ font-size: 14px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  th {{ background: #1a3c6e; color: #fff; font-weight: 600; padding: 8px 10px; text-align: left; }}
  th.num, td.num {{ text-align: right; }}
  th.center, td.center {{ text-align: center; }}
  td {{ padding: 7px 10px; border-bottom: 1px solid #eee; vertical-align: top; }}
  .nowrap {{ white-space: nowrap; }}
  tr.even td {{ background: #f7f9fc; }}
  .footer {{ padding: 16px 36px; border-top: 1px solid #e5e7eb; font-size: 11px; color: #9ca3af; display: flex; justify-content: space-between; }}
  @media print {{ body {{ background: #fff; padding: 0; }} .page {{ box-shadow: none; border-radius: 0; }} }}
</style>
</head>
<body>
<div class="page">
  <div class="header">
    <div>
      {logo_svg}
      <div class="sub" style="margin-top:8px;opacity:.7;">Carrier Quotes Report</div>
    </div>
    <div class="meta">
      {f'<div>PO Number: <strong>{QuotesReportGenerator.escape_html(po_number)}</strong></div>' if po_number else ''}
      <div>Request ID: <strong>{request_id_esc}</strong></div>
      <div>Exported: {export_time}</div>
    </div>
  </div>

  <div class="body">
    <div>
      <div class="section-title">Shipment Details</div>
      <div class="addr-grid">
        <div class="addr-card">
          <div class="label">Origin</div>
          <strong>{origin_company_esc}</strong><br>
          {origin_addr}
          {f'<br>{origin_phone_esc}' if origin_phone_esc else ''}
        </div>
        <div class="addr-card">
          <div class="label">Destination</div>
          <strong>{dest_company_esc}</strong><br>
          {dest_addr}
          {f'<br>{dest_phone_esc}' if dest_phone_esc else ''}
        </div>
      </div>
    </div>

    {freight_items_html}

    <div>
      <div class="section-title">Carrier Quotes ({len(sorted_quotes)})</div>
      {quotes_table_html}
    </div>
  </div>

  <div class="footer">
    <span>Generated by BiziShip · app.biziship.ai</span>
    <span>{export_time}</span>
  </div>
</div>
</body>
</html>"""

        return html_content

    @staticmethod
    def _format_address(data, prefix):
        """Format address block from shipment data."""
        addr1 = QuotesReportGenerator.escape_html(data.get(f'{prefix}_address'))
        addr2 = QuotesReportGenerator.escape_html(data.get(f'{prefix}_address2'))
        city = QuotesReportGenerator.escape_html(data.get(f'{prefix}_city'))
        state = QuotesReportGenerator.escape_html(data.get(f'{prefix}_state'))
        zip_code = QuotesReportGenerator.escape_html(data.get(f'{prefix}_zip'))

        lines = []
        if addr1:
            lines.append(addr1)
        if addr2:
            lines.append(addr2)
        if city or state or zip_code:
            location = f"{city}, {state} {zip_code}".strip().replace(", , ", ", ").rstrip(", ")
            lines.append(location)

        return "<br>".join(lines)

    @staticmethod
    def _build_freight_items_table(freight_lines):
        """Build HTML table for freight line items."""
        if not freight_lines:
            return ""

        rows = []
        total_pieces = 0
        total_weight = 0

        for idx, item in enumerate(freight_lines, 1):
            pkg = QuotesReportGenerator.escape_html(item.get('packaging_type', ''))
            pieces = item.get('pieces', 0)
            weight = item.get('weight', 0)
            weight_unit = item.get('weight_unit', 'lbs')
            length = item.get('length', 0)
            width = item.get('width', 0)
            height = item.get('height', 0)
            dim_unit = item.get('dim_unit', 'in')
            hazmat = item.get('hazmat', False)
            description = QuotesReportGenerator.escape_html(item.get('cargo_desc', ''))
            nmfc = QuotesReportGenerator.escape_html(item.get('nmfc', ''))
            freight_class = QuotesReportGenerator.escape_html(item.get('freight_class', ''))

            total_pieces += pieces
            total_weight += weight

            hazmat_badge = ' <span class="badge-red">HAZMAT</span>' if hazmat else ''

            rows.append(f"""<tr class="{'even' if idx % 2 == 0 else ''}">
                <td class="center">{idx}</td>
                <td>{pkg}</td>
                <td class="center">{pieces}</td>
                <td class="num">{weight:.0f} {weight_unit}</td>
                <td class="center">{length:.0f}×{width:.0f}×{height:.0f} {dim_unit}</td>
                <td class="center">{freight_class}</td>
                <td>{description}{hazmat_badge}</td>
                <td>{nmfc}</td>
            </tr>""")

        rows.append(f"""<tr style="border-top: 2px solid #1a3c6e; font-weight: 700; background: #eef3fc !important;">
            <td colspan="2"><strong>TOTAL</strong></td>
            <td class="center"><strong>{total_pieces}</strong></td>
            <td class="num"><strong>{total_weight:.0f} lbs</strong></td>
            <td colspan="4"></td>
        </tr>""")

        table_html = f"""<div>
            <div class="section-title">Freight Items</div>
            <table>
                <thead>
                    <tr>
                        <th class="center">#</th>
                        <th>Packaging</th>
                        <th class="center">Pieces</th>
                        <th class="num">Weight</th>
                        <th class="center">Dimensions</th>
                        <th class="center">Class</th>
                        <th>Description</th>
                        <th>NMFC</th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(rows)}
                </tbody>
            </table>
        </div>"""

        return table_html

    @staticmethod
    def _build_quotes_table(quotes, valid_until_str):
        """Build HTML table for carrier quotes."""
        rows = []

        for idx, quote in enumerate(quotes, 1):
            carrier_name = QuotesReportGenerator.escape_html(quote.get('carrier_name', ''))
            service_level = QuotesReportGenerator.escape_html(quote.get('service_level', ''))
            description = QuotesReportGenerator.escape_html(quote.get('service_level_description', ''))
            transit_days = quote.get('transit_days')
            transit_str = str(transit_days) if transit_days else "—"
            delivery_date = quote.get('delivery_date')
            delivery_str = delivery_date if delivery_date else "—"
            total_charge = quote.get('total_charge')
            total_str = QuotesReportGenerator.format_currency(total_charge, quote.get('currency', 'USD'))
            quote_number = QuotesReportGenerator.escape_html(quote.get('carrier_quote_number', ''))
            liability_new = quote.get('carrier_liability_new')
            liability_used = quote.get('carrier_liability_used')
            liability_new_str = QuotesReportGenerator.format_currency(liability_new)
            liability_used_str = QuotesReportGenerator.format_currency(liability_used)

            rows.append(f"""<tr class="{'even' if idx % 2 == 0 else ''}">
                <td class="center"><strong>{idx}</strong></td>
                <td><strong>{carrier_name}</strong></td>
                <td>{service_level}</td>
                <td>{description}</td>
                <td class="center">{transit_str}</td>
                <td class="center">{delivery_str}</td>
                <td class="num"><strong>{total_str}</strong></td>
                <td>{quote_number}</td>
                <td class="center">{valid_until_str}</td>
                <td class="num">{liability_new_str}</td>
                <td class="num">{liability_used_str}</td>
            </tr>""")

        table_html = f"""<table>
            <thead>
                <tr>
                    <th class="center">#</th>
                    <th>Carrier</th>
                    <th>Service</th>
                    <th>Description</th>
                    <th class="center">Transit</th>
                    <th class="center">Delivery</th>
                    <th class="num">Total</th>
                    <th>Quote #</th>
                    <th class="center">Valid Until</th>
                    <th class="num">Liability New</th>
                    <th class="num">Liability Used</th>
                </tr>
            </thead>
            <tbody>
                {''.join(rows)}
            </tbody>
        </table>"""

        return table_html

    @staticmethod
    def _get_logo_svg():
        """Return BiziShip.ai logo as clean white text."""
        return '''<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Helvetica Neue', sans-serif; font-size: 28px; font-weight: 700; color: #ffffff; letter-spacing: -0.5px;">biziShip.ai</div>'''
