from odoo import http
from odoo.http import request

class BiziShipMapController(http.Controller):
    
    @http.route('/biziship/map/<int:order_id>', type='http', auth='user', website=False)
    def render_map(self, order_id, **kw):
        order = request.env['sale.order'].sudo().browse(order_id)
        if not order.exists():
            return "Order not found"
            
        api_key = request.env['ir.config_parameter'].sudo().get_param('biziship.google_maps_api_key')
        if not api_key:
            api_key = order._fetch_gateway_maps_key()
            if api_key:
                request.env['ir.config_parameter'].sudo().set_param('biziship.google_maps_api_key', api_key)
        
        if not api_key:
            return "Google Maps API Key not available."

        origin_parts = [order.biziship_origin_address, order.biziship_origin_city, order.biziship_origin_state_id.code if order.biziship_origin_state_id else '', order.biziship_origin_zip, order.biziship_origin_country_id.code if order.biziship_origin_country_id else '']
        dest_parts = [order.biziship_dest_address, order.biziship_dest_city, order.biziship_dest_state_id.code if order.biziship_dest_state_id else '', order.biziship_dest_zip, order.biziship_dest_country_id.code if order.biziship_dest_country_id else '']
        
        origin_str = ", ".join([p for p in origin_parts if p])
        dest_str = ", ".join([p for p in dest_parts if p])
        
        if not origin_str or not dest_str:
            return "Missing Origin or Destination Addresses."

        safe_origin = origin_str.replace("'", "\\'")
        safe_dest = dest_str.replace("'", "\\'")

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                html, body {{ margin: 0; padding: 0; height: 100%; width: 100%; font-family: sans-serif; position: relative; }}
                #map {{ height: 100%; width: 100%; border-radius: 8px; }}
                #distance-box {{
                    background: rgba(32, 31, 65, 0.88);
                    color: white;
                    margin: 0 10px 10px 0;
                    padding: 6px 14px;
                    border-radius: 20px;
                    font-size: 13px;
                    font-weight: 700;
                    letter-spacing: 0.3px;
                    display: none;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.35);
                    border: 1px solid rgba(244,152,0,0.5);
                    cursor: default;
                }}
            </style>
            <script src="https://maps.googleapis.com/maps/api/js?key={api_key}&language=en&region=US"></script>
            <script>
                function initMap() {{
                    var map = new google.maps.Map(document.getElementById('map'), {{
                        zoom: 5,
                        zoomControlOptions: {{ position: google.maps.ControlPosition.RIGHT_CENTER }},
                        mapTypeControl: false, streetViewControl: false, fullscreenControl: false
                    }});
                    var dirService = new google.maps.DirectionsService();
                    var dirRenderer = new google.maps.DirectionsRenderer({{
                        map: map,
                        suppressMarkers: true,
                        preserveViewport: true,
                        polylineOptions: {{ strokeColor: '#3b82f6', strokeWeight: 4, strokeOpacity: 0.9 }}
                    }});
                    dirService.route({{
                        origin: '{safe_origin}',
                        destination: '{safe_dest}',
                        travelMode: 'DRIVING',
                        provideRouteAlternatives: false,
                        unitSystem: google.maps.UnitSystem.IMPERIAL
                    }}, function(response, status) {{
                        if (status === 'OK') {{
                            var route = response.routes[0];
                            var leg = route.legs[0];
                            
                            dirRenderer.setDirections(response);
                            
                            // Fit bounds automatically with 35 pixels padding to see entire route perfectly
                            map.fitBounds(route.bounds, 35);
                            
                            // Draw the exact custom markers used in BiziShip web app
                            var markerOpts = {{
                                path: google.maps.SymbolPath.CIRCLE, 
                                scale: 6, fillColor: '#ef4444', fillOpacity: 1, 
                                strokeColor: '#fff', strokeWeight: 2
                            }};
                            new google.maps.Marker({{ position: leg.start_location, map: map, icon: markerOpts, zIndex: 100 }});
                            new google.maps.Marker({{ position: leg.end_location, map: map, icon: markerOpts, zIndex: 100 }});
                            
                            // Add distance as a native Google Maps control (bottom right)
                            // This is the only reliable way to overlay content inside an iframe map
                            var dist = leg.distance.text;
                            var box = document.getElementById('distance-box');
                            box.innerText = '🛣  ' + dist;
                            box.style.display = 'block';
                            map.controls[google.maps.ControlPosition.BOTTOM_RIGHT].push(box);
                            
                            // Also send to the parent Odoo page to display below the map
                            try {{
                                var orderId = window.location.pathname.split('/').pop();
                                window.parent.postMessage({{ type: 'biziship_distance_' + orderId, distance: dist }}, '*');
                            }} catch(e) {{}}
                        }}
                    }});
                }}
                window.onload = initMap;
            </script>
        </head>
        <body>
            <div id="map"></div>
            <div id="distance-box"></div>
        </body>
        </html>
        """
        return request.make_response(html_content)
