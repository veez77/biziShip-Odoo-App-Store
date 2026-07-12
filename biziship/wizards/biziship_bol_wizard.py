import json
import base64
import requests
import io
import os
from datetime import datetime
try:
    from dateutil.parser import parse as date_parse
except ImportError:
    date_parse = None

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

from odoo.addons.biziship.api_utils import get_biziship_api_url, get_groq_api_key, BIZISHIP_MODULE_VERSION, BIZISHIP_APP_NAME

try:
    from PyPDF2 import PdfReader
except ImportError:
    try:
        from PyPDF2 import PdfFileReader as PdfReader
    except ImportError:
        PdfReader = None

class BizishipBolImportWizard(models.TransientModel):
    _name = 'biziship.bol.import.wizard'
    _description = 'BiziShip BOL Import Wizard'

    bol_file = fields.Binary(string="BOL Document (PDF/Image)", required=True)
    file_name = fields.Char(string="File Name")

    def action_process_bol(self):
        self.ensure_one()
        if not self.bol_file:
            raise UserError(_("Please upload a BOL PDF file."))

        # 1. Base64 file string (Odoo Binary fields are already base64 encoded bytes)
        file_base64 = self.bol_file.decode('utf-8')
        file_name = self.file_name or "document.pdf"
        
        is_pdf = file_name.lower().endswith('.pdf')
        is_image = file_name.lower().endswith(('.png', '.jpg', '.jpeg'))
        
        if not is_pdf and not is_image:
            # Default to PDF behavior if unknown extension, or could enforce
            is_pdf = True

        mime_type = "application/pdf"
        if is_image:
            mime_type = "image/png" if file_name.lower().endswith('.png') else "image/jpeg"

        # Determine extraction strategy
        pdf_text = ""
        payload = {}
        
        # --- GROQ EXTRACTION TEMPORARILY DISABLED ---
        # prompt = """
        # You are an expert logistics data extractor. I have a Bill of Lading (BOL). 
        # I need to get Freight details from the document for an LTL Freight request to be passed to freight brokers.
        # Please parse the provided data, and extract the following information in a strict JSON format with exactly these keys:
        # - "Weight"
        # - "Dimensions"
        # - "Origin"
        # - "Destination"
        # - "Freight Class"
        # 
        # Respond ONLY with a valid JSON object, without any markdown formatting, backticks, or additional explanation.
        # """
        # 
        # # 2. Setup API Key and Endpoint
        # groq_api_key = get_groq_api_key()
        # if not groq_api_key:
        #     raise UserError(_("Groq API Key is not configured in secrets.json"))
        #     
        # groq_endpoint = "https://api.groq.com/openai/v1/chat/completions"
        # 
        # headers = {
        #     "Authorization": f"Bearer {groq_api_key}",
        #     "Content-Type": "application/json"
        # }
        # 
        # if is_pdf:
        #     try:
        #         if PdfReader:
        #             pdf_bytes = base64.b64decode(self.bol_file)
        #             reader = PdfReader(io.BytesIO(pdf_bytes))
        #             pages = reader.pages if hasattr(reader, 'pages') else reader.pages
        #             for page in pages:
        #                 text = page.extract_text() if hasattr(page, 'extract_text') else page.extractText()
        #                 if text:
        #                     pdf_text += text + "\n"
        #         else:
        #             pdf_text = "Error: PyPDF2 library is not available in Odoo to extract text."
        #     except Exception as e:
        #         pdf_text = f"Error extracting PDF text: {str(e)}"
        #         
        #     payload = {
        #         "model": "llama-3.3-70b-versatile",
        #         "messages": [
        #             {
        #                 "role": "system",
        #                 "content": "You are a helpful logistics assistant that outputs data in strict JSON."
        #             },
        #             {
        #                 "role": "user",
        #                 "content": f"{prompt}\n\nDocument Text:\n{pdf_text}"
        #             }
        #         ],
        #         "temperature": 0.1,
        #         "response_format": {"type": "json_object"}
        #     }
        # else:
        #     payload = {
        #         "model": "llama-3.2-90b-vision-preview",
        #         "messages": [
        #             {
        #                 "role": "user",
        #                 "content": [
        #                     {"type": "text", "text": prompt},
        #                     {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{file_base64}"}}
        #                 ]
        #             }
        #         ],
        #         "temperature": 0.1
        #     }
        # 
        # try:
        #     response = requests.post(groq_endpoint, headers=headers, json=payload, timeout=60)
        #     response.raise_for_status()
        #     ai_data = response.json()
        #     message_content = ai_data.get('choices', [{}])[0].get('message', {}).get('content', '')
        #     
        #     # Clean up potential markdown wrapper from vision model if present
        #     if message_content.startswith('```json'):
        #         message_content = message_content.strip('`').replace('json\n', '', 1)
        #     elif message_content.startswith('```'):
        #         message_content = message_content.strip('`')
        #         
        #     parsed_json = json.loads(message_content)
        # except requests.exceptions.RequestException as e:
        #     error_details = e.response.text if hasattr(e, 'response') and e.response is not None else str(e)
        #     raise UserError(_("Failed to connect to Groq API. Error: %s") % error_details)
        # except json.JSONDecodeError:
        #     raise UserError(_("Groq API did not return valid JSON. Response was: %s") % message_content)
        # 
        # # Validate required data presence
        # required_keys = ["Weight", "Dimensions", "Origin", "Destination", "Freight Class"]
        # if not all(key in parsed_json for key in required_keys):
        #     raise UserError(
        #         _("Groq API failed to find required LTL data.\n"
        #           "Expected keys: %s\n"
        #           "Parsed data received:\n%s") % (required_keys, json.dumps(parsed_json, indent=2))
        #     )
        # --- END GROQ EXTRACTION TEMPORARILY DISABLED ---
        
        parsed_json = {}

        # 3. Send to Local API (Email2Quote)
        email2quote_api_url = get_biziship_api_url(self.env)
        local_api_bol_url = f"{email2quote_api_url.rstrip('/')}/erp/bol/extract"
        erp_api_key = self.env['ir.config_parameter'].sudo().get_param('biziship.erp_api_key', '')
        api_key_header = {
            "X-ERP-API-Key": erp_api_key,
            "X-User-Email": (self.env.user.biziship_email if self.env.user.biziship_token and self.env.user.biziship_email else self.env.user.email) or "",
            "X-Client-App": BIZISHIP_APP_NAME,
            "X-Client-Version": BIZISHIP_MODULE_VERSION,
        }

        # Decode base64 PDF/Image bytes from Odoo
        file_bytes = base64.b64decode(self.bol_file)

        _logger.info("BiziShip BOL Extraction API Request Headers: %s", api_key_header)

        try:
            # Send BOL Document (PDF or Image)
            files = {"file": (file_name, file_bytes, mime_type)}
            local_response_bol = requests.post(
                local_api_bol_url, 
                headers=api_key_header, 
                files=files, 
                timeout=30
            )
            local_response_bol.raise_for_status()

            # Process JSON response
            response_json = local_response_bol.json()
            
            # Check context to see if we were launched from a sale order
            active_id = self.env.context.get('active_id')
            active_model = self.env.context.get('active_model')
            
            if active_id and active_model == 'sale.order':
                # Save the JSON dict string directly to the sales order
                extracted_details = response_json.get('extracted_details', response_json)
                sale_order_record = self.env['sale.order'].browse(active_id)
                
                # --- AUTO-POPULATION LOGIC ---
                vals = {
                    'biziship_extracted_json': json.dumps(extracted_details),
                    'biziship_po_number': extracted_details.get('po_number'),
                    # Addresses - Origin
                    'biziship_origin_company': extracted_details.get('origin_company'),
                    'biziship_origin_address': extracted_details.get('origin_address'),
                    'biziship_origin_address2': extracted_details.get('origin_address2'),
                    'biziship_origin_city': extracted_details.get('origin_city'),
                    'biziship_origin_zip': extracted_details.get('origin_zip'),
                    'biziship_origin_contact_name': extracted_details.get('origin_contact_name'),
                    'biziship_origin_contact_phone': extracted_details.get('origin_phone'),
                    'biziship_origin_contact_email': extracted_details.get('origin_email'),
                    
                    # Addresses - Destination
                    'biziship_dest_company': extracted_details.get('destination_company'),
                    'biziship_dest_address': extracted_details.get('destination_address'),
                    'biziship_dest_address2': extracted_details.get('destination_address2'),
                    'biziship_dest_city': extracted_details.get('destination_city'),
                    'biziship_dest_zip': extracted_details.get('destination_zip'),
                    'biziship_dest_contact_name': extracted_details.get('destination_contact_name'),
                    'biziship_dest_contact_phone': extracted_details.get('destination_phone'),
                    'biziship_dest_contact_email': extracted_details.get('destination_email'),
                    'biziship_cargo_desc': extracted_details.get('cargo_description', 'General Freight'),
                    'biziship_special_instructions': extracted_details.get('special_instructions'),
                }
                
                # State and Country resolution (scoped by country to avoid 'GA' -> Goa)
                origin_country_code = extracted_details.get('origin_country', 'US') or 'US'
                origin_country = self.env['res.country'].search([('code', '=', origin_country_code)], limit=1)
                if origin_country:
                    vals['biziship_origin_country_id'] = origin_country.id
                    origin_state_code = extracted_details.get('origin_state')
                    if origin_state_code:
                        state = self.env['res.country.state'].search([
                            ('code', '=', origin_state_code),
                            ('country_id', '=', origin_country.id)
                        ], limit=1)
                        if state:
                            vals['biziship_origin_state_id'] = state.id

                dest_country_code = extracted_details.get('destination_country', 'US') or 'US'
                dest_country = self.env['res.country'].search([('code', '=', dest_country_code)], limit=1)
                if dest_country:
                    vals['biziship_dest_country_id'] = dest_country.id
                    dest_state_code = extracted_details.get('destination_state')
                    if dest_state_code:
                        state = self.env['res.country.state'].search([
                            ('code', '=', dest_state_code),
                            ('country_id', '=', dest_country.id)
                        ], limit=1)
                        if state:
                            vals['biziship_dest_state_id'] = state.id
                
                # Pickup Date
                pdate_raw = extracted_details.get('pickup_date')
                if pdate_raw:
                    try:
                        if date_parse:
                            parsed_date = date_parse(str(pdate_raw)).date()
                            vals['biziship_pickup_date'] = fields.Date.to_string(parsed_date)
                        else:
                            # Fallback if dateutil not available
                            for fmt in ('%Y-%m-%d', '%m-%d-%Y', '%d-%m-%Y', '%m/%d/%Y', '%d/%m/%Y'):
                                try:
                                    parsed_date = datetime.strptime(str(pdate_raw), fmt).date()
                                    vals['biziship_pickup_date'] = fields.Date.to_string(parsed_date)
                                    break
                                except ValueError:
                                    continue
                    except Exception as e:
                        _logger.warning("Failed to parse BOL Pickup Date '%s': %s", pdate_raw, str(e))
                    
                # Accessorials Mapping
                acc_codes = extracted_details.get('accessorial_codes', [])
                if isinstance(acc_codes, list):
                    vals.update({
                        'biziship_origin_residential': 'RESPU' in acc_codes,
                        'biziship_origin_liftgate': 'LGPU' in acc_codes,
                        'biziship_origin_limited_access': 'LTDPU' in acc_codes,
                        'biziship_dest_residential': 'RESDEL' in acc_codes,
                        'biziship_dest_liftgate': 'LGDEL' in acc_codes,
                        'biziship_dest_limited_access': 'LTDDEL' in acc_codes,
                        'biziship_dest_appointment': 'APPT' in acc_codes,
                        'biziship_dest_notify': 'NOTIFY' in acc_codes,
                        'biziship_dest_hazmat': 'HAZM' in acc_codes,
                    })
                    
                    # Handle Many2many accessorials (clearing is handled by Odoo standard if list is provided)
                    # We match codes from the registry
                    origin_acc_ids = self.env['biziship.accessorial'].search([('type', '=', 'origin'), ('code', 'in', acc_codes)]).ids
                    dest_acc_ids = self.env['biziship.accessorial'].search([('type', '=', 'destination'), ('code', 'in', acc_codes)]).ids
                    if origin_acc_ids:
                        vals['biziship_origin_accessorial_ids'] = [(6, 0, origin_acc_ids)]
                    if dest_acc_ids:
                        vals['biziship_dest_accessorial_ids'] = [(6, 0, dest_acc_ids)]

                # Cargo Lines Mapping
                # 1. Clear existing lines
                vals['biziship_cargo_line_ids'] = [(5, 0, 0)]
                
                # 2. Add new lines from line_items
                items = extracted_details.get('line_items', [])
                if not items:
                    # Fallback if no line_items but top-level weight exists
                    w = extracted_details.get('weight', 0.0)
                    if w > 0:
                        items = [{
                            "weight": w,
                            "weight_unit": extracted_details.get("weight_unit", "lbs"),
                            "num_pieces": 1,
                            "packaging_type": "pallet",
                            "cargo_description": extracted_details.get("cargo_description", "General Freight")
                        }]

                for item in items:
                    # Map packaging type
                    pkg = str(item.get('packaging_type', 'pallet')).lower()
                    if 'crate' in pkg: pkg = 'crate'
                    elif 'box' in pkg: pkg = 'box'
                    elif 'drum' in pkg: pkg = 'drum'
                    else: pkg = 'pallet'
                    
                    # Map units
                    w_unit = str(item.get('weight_unit', 'lbs')).lower()
                    if 'kg' in w_unit: w_unit = 'kg'
                    else: w_unit = 'lbs'
                    
                    d_unit = str(item.get('dimension_unit', item.get('dim_unit', 'in'))).lower()
                    if 'cm' in d_unit: d_unit = 'cm'
                    elif 'm' in d_unit: d_unit = 'm'
                    elif 'ft' in d_unit: d_unit = 'ft'
                    else: d_unit = 'in'

                    vals['biziship_cargo_line_ids'].append((0, 0, {
                        'packaging_type': pkg,
                        'pieces': item.get('num_pieces', item.get('pieces', 1)),
                        'weight': item.get('weight', 0.0),
                        'weight_unit': w_unit,
                        'length': item.get('length', 48.0),
                        'width': item.get('width', 40.0),
                        'height': item.get('height', 48.0),
                        'dim_unit': d_unit,
                        'freight_class': str(item.get('freight_class', '50')),
                        'nmfc': item.get('nmfc', ''),
                        'cargo_desc': item.get('cargo_description', item.get('cargo_desc', 'General Freight')),
                    }))
                
                sale_order_record.write(vals)
                # --- END AUTO-POPULATION LOGIC ---

        except requests.exceptions.RequestException as e:
            error_details = e.response.text if hasattr(e, 'response') and e.response is not None else str(e)
            raise UserError(
                _("BiziShip External API Blocked: Failed to send data to local Email2Quote API.\n\n"
                  "Please ensure the local service is running and accepting requests.\n\n"
                  "Details:\n%s") % error_details
            )

        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }
