import requests
import logging
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class BizishipEmailQuotesSimpleWizard(models.TransientModel):
    _name = 'biziship.email.quotes.simple.wizard'
    _description = 'Email Quotes Report (Simplified)'

    sale_order_id = fields.Many2one('sale.order', readonly=True)
    to_emails = fields.Text(
        'Recipient Emails',
        placeholder='Enter comma-separated email addresses',
        required=True
    )

    markup_enabled = fields.Boolean(readonly=True)
    markup_rule_description = fields.Char(readonly=True)
    apply_markup = fields.Boolean('Include Markup in Pricing', default=False)
    markup_preview_html = fields.Html(compute='_compute_markup_preview')
    shipment_details_html = fields.Html(compute='_compute_shipment_details')
    html_report = fields.Text(compute='_compute_html_report')  # Text, not Html, to avoid Odoo sanitization

    # State tracking
    send_success = fields.Boolean(readonly=True, default=False)
    success_recipients = fields.Text(readonly=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        context = self.env.context

        sale_order_id = context.get('default_sale_order_id')
        if sale_order_id:
            res['sale_order_id'] = sale_order_id

        # Fetch markup config
        from odoo.addons.biziship.models.quotes_markup import QuotesMarkup
        markup_config = QuotesMarkup.get_company_markup_config(self.env)

        if markup_config and markup_config.get('enabled'):
            res['markup_enabled'] = True
            res['markup_rule_description'] = QuotesMarkup.format_markup_description(markup_config)
        else:
            res['markup_enabled'] = False

        return res

    @api.depends('apply_markup', 'sale_order_id', 'markup_enabled')
    def _compute_markup_preview(self):
        from odoo.addons.biziship.models.quotes_markup import QuotesMarkup

        for record in self:
            if not record.sale_order_id:
                record.markup_preview_html = ''
                continue

            quotes = record.sale_order_id.biziship_quote_ids
            if not quotes:
                record.markup_preview_html = ''
                continue

            markup_config = None
            if record.markup_enabled:
                markup_config = QuotesMarkup.get_company_markup_config(self.env)

            # Build table rows
            rows = []
            for quote in quotes:
                carrier = quote.carrier_name or 'Unknown'
                original = quote.total_charge or 0
                transit_days = quote.transit_days or '-'

                if record.apply_markup and markup_config and markup_config.get('enabled'):
                    marked_up = QuotesMarkup.apply_markup(original, markup_config)
                    delta = marked_up - original
                    rows.append(f"""
                        <tr>
                            <td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>{carrier}</strong></td>
                            <td style="padding: 8px; border-bottom: 1px solid #eee; text-align: center;">{transit_days}</td>
                            <td style="padding: 8px; border-bottom: 1px solid #eee; text-align: right;">${original:,.2f}</td>
                            <td style="padding: 8px; border-bottom: 1px solid #eee; text-align: right;">${marked_up:,.2f}</td>
                            <td style="padding: 8px; border-bottom: 1px solid #eee; text-align: right; color: #f49800; font-weight: 600;">+${delta:,.2f}</td>
                        </tr>
                    """)
                else:
                    rows.append(f"""
                        <tr>
                            <td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>{carrier}</strong></td>
                            <td style="padding: 8px; border-bottom: 1px solid #eee; text-align: center;">{transit_days}</td>
                            <td style="padding: 8px; border-bottom: 1px solid #eee; text-align: right;">${original:,.2f}</td>
                        </tr>
                    """)

            # Build table with conditional columns
            if record.apply_markup and record.markup_enabled:
                table_header = """
                    <thead style="background: #f8f9fa;">
                        <tr>
                            <th style="padding: 8px; text-align: left; font-weight: 700;">Carrier</th>
                            <th style="padding: 8px; text-align: center; font-weight: 700;">Transit Delivery</th>
                            <th style="padding: 8px; text-align: right; font-weight: 700;">Original</th>
                            <th style="padding: 8px; text-align: right; font-weight: 700;">With Markup</th>
                            <th style="padding: 8px; text-align: right; font-weight: 700;">Fee Delta</th>
                        </tr>
                    </thead>
                """
            else:
                table_header = """
                    <thead style="background: #f8f9fa;">
                        <tr>
                            <th style="padding: 8px; text-align: left; font-weight: 700;">Carrier</th>
                            <th style="padding: 8px; text-align: center; font-weight: 700;">Transit Delivery</th>
                            <th style="padding: 8px; text-align: right; font-weight: 700;">Total Charge</th>
                        </tr>
                    </thead>
                """

            html = f"""
                <table style="width: 100%; border-collapse: collapse; font-size: 12px;">
                    {table_header}
                    <tbody>
                        {''.join(rows)}
                    </tbody>
                </table>
            """
            record.markup_preview_html = html

    @api.depends('sale_order_id')
    def _compute_shipment_details(self):
        try:
            for record in self:
                if not record.sale_order_id:
                    record.shipment_details_html = ''
                    continue

                so = record.sale_order_id

                # Safely escape and format strings
                def safe_str(val):
                    if not val:
                        return ''
                    return str(val).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')

                # Origin section
                origin_addr = safe_str(so.biziship_origin_address or '')
                origin_addr2 = safe_str(so.biziship_origin_address2 or '')
                origin_address = f"{origin_addr} {origin_addr2}".strip()
                origin_city = safe_str(so.biziship_origin_city or '')
                origin_state = safe_str(so.biziship_origin_state_id.code if so.biziship_origin_state_id else '')
                origin_zip = safe_str(so.biziship_origin_zip or '')
                origin_city_state = f"{origin_city}, {origin_state} {origin_zip}".strip()
                origin_company = safe_str(so.biziship_origin_company or 'N/A')
                origin_phone = safe_str(so.biziship_origin_contact_phone or '')

                origin_html = f"""
                    <div style="border: 1px solid #dee2e6; border-radius: 4px; padding: 12px; background: #f8f9fa;">
                        <div style="font-weight: 600; color: #1a3c6e; margin-bottom: 8px; font-size: 13px;">ORIGIN (SHIPPER)</div>
                        <div style="font-size: 12px; line-height: 1.6; color: #333;">
                            <div style="font-weight: 600; margin-bottom: 4px;">{origin_company}</div>
                            <div>{origin_address}</div>
                            <div>{origin_city_state}</div>
                            <div>{origin_phone}</div>
                        </div>
                    </div>
                """

                # Destination section
                dest_addr = safe_str(so.biziship_dest_address or '')
                dest_addr2 = safe_str(so.biziship_dest_address2 or '')
                dest_address = f"{dest_addr} {dest_addr2}".strip()
                dest_city = safe_str(so.biziship_dest_city or '')
                dest_state = safe_str(so.biziship_dest_state_id.code if so.biziship_dest_state_id else '')
                dest_zip = safe_str(so.biziship_dest_zip or '')
                dest_city_state = f"{dest_city}, {dest_state} {dest_zip}".strip()
                dest_company = safe_str(so.biziship_dest_company or 'N/A')
                dest_phone = safe_str(so.biziship_dest_contact_phone or '')

                dest_html = f"""
                    <div style="border: 1px solid #dee2e6; border-radius: 4px; padding: 12px; background: #f8f9fa;">
                        <div style="font-weight: 600; color: #1a3c6e; margin-bottom: 8px; font-size: 13px;">DESTINATION (CONSIGNEE)</div>
                        <div style="font-size: 12px; line-height: 1.6; color: #333;">
                            <div style="font-weight: 600; margin-bottom: 4px;">{dest_company}</div>
                            <div>{dest_address}</div>
                            <div>{dest_city_state}</div>
                            <div>{dest_phone}</div>
                        </div>
                    </div>
                """

                # Cargo table
                cargo_rows = []
                for line in so.biziship_cargo_line_ids:
                    packaging = safe_str(line.packaging_type or '-')
                    pieces = line.pieces or 0
                    weight = f"{float(line.weight) if line.weight else 0:.0f} {line.weight_unit or 'lbs'}"
                    dims = f"{float(line.length) if line.length else 0:.0f}x{float(line.width) if line.width else 0:.0f}x{float(line.height) if line.height else 0:.0f} {line.dim_unit or 'in'}"
                    freight_class = safe_str(line.freight_class or '-')
                    cargo_desc = safe_str(line.cargo_desc or '-')
                    nmfc = safe_str(line.nmfc or '-')

                    cargo_rows.append(f"""
                        <tr style="border-bottom: 1px solid #dee2e6;">
                            <td style="padding: 6px; text-align: left;">{packaging}</td>
                            <td style="padding: 6px; text-align: center;">{pieces}</td>
                            <td style="padding: 6px; text-align: right;">{weight}</td>
                            <td style="padding: 6px; text-align: right;">{dims}</td>
                            <td style="padding: 6px; text-align: center;">{freight_class}</td>
                            <td style="padding: 6px; text-align: left;">{cargo_desc}</td>
                            <td style="padding: 6px; text-align: center;">{nmfc}</td>
                        </tr>
                    """)

                cargo_table = f"""
                    <div style="background: #f8f9fa; border-radius: 4px; padding: 12px;">
                        <div style="font-weight: 600; color: #1a3c6e; margin-bottom: 8px; font-size: 13px;">CARGO</div>
                        <table style="width: 100%; font-size: 12px; border-collapse: collapse;">
                            <thead style="background: #e9ecef;">
                                <tr>
                                    <th style="padding: 6px; text-align: left; font-weight: 600;">Packaging</th>
                                    <th style="padding: 6px; text-align: center; font-weight: 600;">Pieces</th>
                                    <th style="padding: 6px; text-align: right; font-weight: 600;">Weight</th>
                                    <th style="padding: 6px; text-align: right; font-weight: 600;">Dimensions</th>
                                    <th style="padding: 6px; text-align: center; font-weight: 600;">Class</th>
                                    <th style="padding: 6px; text-align: left; font-weight: 600;">Description</th>
                                    <th style="padding: 6px; text-align: center; font-weight: 600;">NMFC</th>
                                </tr>
                            </thead>
                            <tbody>
                                {''.join(cargo_rows)}
                            </tbody>
                        </table>
                    </div>
                """

                html = f"""
                    <div style="border-top: 1px solid #e9ecef; padding-top: 16px; margin-bottom: 16px;">
                        <div class="o_form_label" style="font-weight: 600; color: #1a3c6e; display: block; margin-bottom: 12px; font-size: 13px;">SHIPMENT DETAILS</div>
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px;">
                            {origin_html}
                            {dest_html}
                        </div>
                        {cargo_table}
                    </div>
                """
                record.shipment_details_html = html
        except Exception as e:
            _logger.error("Error computing shipment_details_html: %s", str(e), exc_info=True)
            for record in self:
                record.shipment_details_html = ''

    @api.depends('sale_order_id', 'apply_markup')
    def _compute_html_report(self):
        from odoo.addons.biziship.models.quotes_report_generator import QuotesReportGenerator
        from odoo.addons.biziship.models.quotes_markup import QuotesMarkup

        for record in self:
            if not record.sale_order_id:
                record.html_report = ''
                continue

            so = record.sale_order_id

            # Build shipment data (exactly like Export Wizard)
            shipment_data = {
                'request_id': str(so.id),  # Use Odoo record ID like Export Wizard does
                'po_number': so.biziship_po_number or '',
                'origin_company': so.biziship_origin_company or '',
                'origin_address': so.biziship_origin_address or '',
                'origin_address2': so.biziship_origin_address2 or '',
                'origin_city': so.biziship_origin_city or '',
                'origin_state': str(so.biziship_origin_state_id.code if so.biziship_origin_state_id else ''),
                'origin_zip': so.biziship_origin_zip or '',
                'origin_phone': so.biziship_origin_contact_phone or '',
                'destination_company': so.biziship_dest_company or '',
                'destination_address': so.biziship_dest_address or '',
                'destination_address2': so.biziship_dest_address2 or '',
                'destination_city': so.biziship_dest_city or '',
                'destination_state': str(so.biziship_dest_state_id.code if so.biziship_dest_state_id else ''),
                'destination_zip': so.biziship_dest_zip or '',
                'destination_phone': so.biziship_dest_contact_phone or '',
                'freight_lines': [
                    {
                        'packaging_type': str(line.packaging_type or ''),
                        'pieces': int(line.pieces or 0),
                        'weight': float(line.weight or 0),
                        'weight_unit': str(line.weight_unit or 'lbs'),
                        'length': float(line.length or 0),
                        'width': float(line.width or 0),
                        'height': float(line.height or 0),
                        'dim_unit': str(line.dim_unit or 'in'),
                        'freight_class': str(line.freight_class or ''),
                        'nmfc': str(line.nmfc or ''),
                        'cargo_desc': str(line.cargo_desc or ''),
                        'hazmat': bool(line.hazmat),
                    }
                    for line in so.biziship_cargo_line_ids
                ],
            }

            # Build quotes list (exactly like Export Wizard)
            quotes = [
                {
                    'quote_id': str(q.id),
                    'carrier_name': str(q.carrier_name or ''),
                    'carrier_code': str(q.carrier_code or ''),
                    'service_level': str(q.service_level or ''),
                    'service_level_description': '',
                    'transit_days': int(q.transit_days or 0),
                    'delivery_date': str(q.delivery_date or ''),
                    'total_charge': float(q.total_charge or 0),
                    'currency': str(q.currency or 'USD'),
                    'carrier_quote_number': str(q.quote_id_ref or ''),
                    'carrier_liability_new': float(q.carrier_liability_new or 0),
                    'carrier_liability_used': float(q.carrier_liability_used or 0),
                }
                for q in so.biziship_quote_ids
            ]

            # Get markup config if needed
            markup_config = None
            if record.apply_markup:
                markup_config = QuotesMarkup.get_company_markup_config(self.env)

            html = QuotesReportGenerator.generate_quotes_html_report(
                shipment_data=shipment_data,
                quotes=quotes,
                markup_config=markup_config,
                apply_markup=record.apply_markup and record.markup_enabled
            )
            record.html_report = html

    def action_send_report(self):
        """Open confirmation dialog to review emails before sending."""
        _logger.info("action_send_report called: to_emails='%s'", self.to_emails)

        if not self.to_emails or not self.to_emails.strip():
            return

        # Clean up any old confirmation wizard records to ensure fresh state
        self.env['biziship.email.quotes.confirm.wizard'].search([]).unlink()

        # Create fresh confirmation wizard with current emails and markup setting
        confirm_wizard = self.env['biziship.email.quotes.confirm.wizard'].create({
            'sale_order_id': self.sale_order_id.id,
            'to_emails': self.to_emails,
            'apply_markup': self.apply_markup,
        })

        # Open confirmation dialog
        return {
            'type': 'ir.actions.act_window',
            'name': 'Confirm Recipients',
            'res_model': 'biziship.email.quotes.confirm.wizard',
            'res_id': confirm_wizard.id,
            'view_mode': 'form',
            'views': [[False, 'form']],
            'target': 'new',
        }

    def _get_api_url(self):
        from odoo.addons.biziship.api_utils import get_biziship_api_url
        return get_biziship_api_url(self.env)

    def _get_erp_api_key(self):
        from odoo.addons.biziship.api_utils import get_erp_api_key
        return get_erp_api_key(self.env)

    def action_cancel(self):
        """Close the wizard."""
        return {'type': 'ir.actions.act_window_close'}

    def close(self):
        """Close the wizard from success state."""
        return {'type': 'ir.actions.act_window_close'}
