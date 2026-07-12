/** @odoo-module */

import { registry } from "@web/core/registry";
import { CharField } from "@web/views/fields/char/char_field";
import { useService } from "@web/core/utils/hooks";
import { onMounted, useRef } from "@odoo/owl";

export class BiziShipPlacesAutocomplete extends CharField {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.dropdownState = { items: [], activeIndex: -1 };
        
        onMounted(() => {
            console.log("BiziShipPlacesAutocomplete mounted for field:", this.props.name);
            this.orm.call("sale.order", "biziship_get_maps_key", []).then((key) => {
                if (key) {
                    this.apiKey = key;
                    this.initCustomAutocomplete();
                } else {
                    console.error("Missing Google Maps API Key.");
                }
            });
        });
    }

    initCustomAutocomplete() {
        const inputId = this.props.id;
        let input = document.getElementById(inputId);
        if (!input) input = document.querySelector(`input[name='${this.props.name}']`);
        
        if (!input) {
            setTimeout(() => {
                let delayedInput = document.getElementById(inputId) || document.querySelector(`input[name='${this.props.name}']`);
                if (delayedInput) this._attachPlacesREST(delayedInput);
            }, 300);
            return;
        }
        this._attachPlacesREST(input);
    }

    _attachPlacesREST(input) {
        input.setAttribute("autocomplete", "off");
        
        // Create custom dropdown container
        const dropdown = document.createElement("ul");
        dropdown.style.cssText = "position: absolute; width: 100%; top: 100%; left: 0; z-index: 9999; background: white; border: 1px solid #ddd; border-top: none; list-style: none; margin: 0; padding: 0; max-height: 250px; overflow-y: auto; display: none; border-radius: 0 0 6px 6px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); font-family: sans-serif;";
        input.parentNode.style.position = "relative";
        input.parentNode.appendChild(dropdown);
        
        // Debounce timer
        let timeout = null;

        input.addEventListener("input", (e) => {
            const query = e.target.value;
            if (query.length < 3) {
                dropdown.style.display = "none";
                return;
            }
            
            clearTimeout(timeout);
            timeout = setTimeout(async () => {
                try {
                    const res = await fetch("https://places.googleapis.com/v1/places:autocomplete", {
                        method: "POST",
                        headers: { "Content-Type": "application/json", "X-Goog-Api-Key": this.apiKey },
                        body: JSON.stringify({ input: query, includedRegionCodes: ["us", "ca", "mx"] })
                    });
                    
                    if (!res.ok) {
                        console.error("Google Places API (New) Autocomplete returned an error:", res.status);
                        dropdown.style.display = "none";
                        return;
                    }
                    
                    const data = await res.json();
                    if (!data.suggestions || data.suggestions.length === 0) {
                        dropdown.style.display = "none";
                        return;
                    }
                    
                    dropdown.innerHTML = "";
                    data.suggestions.forEach((suggestion) => {
                        const placeId = suggestion.placePrediction.placeId;
                        const mainText = suggestion.placePrediction.structuredFormat.mainText.text;
                        const secText = suggestion.placePrediction.structuredFormat.secondaryText ? suggestion.placePrediction.structuredFormat.secondaryText.text : "";
                        
                        const li = document.createElement("li");
                        li.style.cssText = "padding: 10px 12px; cursor: pointer; border-bottom: 1px solid #f0f0f0;";
                        li.innerHTML = `<strong>${mainText}</strong> <span style="color: #6c757d; font-size: 0.9em;">${secText}</span>`;
                        
                        li.addEventListener("mousedown", async (ev) => {
                            ev.preventDefault(); // prevent blur
                            dropdown.style.display = "none";
                            await this._fetchPlaceDetails(placeId, mainText, input);
                        });
                        
                        li.addEventListener("mouseover", () => { li.style.background = "#f8f9fa"; });
                        li.addEventListener("mouseout", () => { li.style.background = "white"; });
                        
                        dropdown.appendChild(li);
                    });
                    dropdown.style.display = "block";
                    
                } catch (err) {
                    console.error("Error fetching places:", err);
                }
            }, 300);
        });
        
        input.addEventListener("blur", () => { setTimeout(() => { dropdown.style.display = "none"; }, 150); });
        input.addEventListener("focus", () => { if (dropdown.innerHTML !== "") dropdown.style.display = "block"; });
    }

    async _fetchPlaceDetails(placeId, streetString, input) {
        try {
            const res = await fetch(`https://places.googleapis.com/v1/places/${placeId}?fields=addressComponents`, {
                headers: { "X-Goog-Api-Key": this.apiKey }
            });
            if (!res.ok) {
                console.error("Google Places API (New) Place Details failed.");
                return;
            }
            const data = await res.json();
            
            let street_number = "", route = "", city = "", stateCode = "", zip = "", countryCode = "";
            
            if (data.addressComponents) {
                for (const component of data.addressComponents) {
                    const types = component.types;
                    if (types.includes("street_number")) street_number = component.shortText;
                    if (types.includes("route")) route = component.shortText;
                    if (types.includes("locality") || types.includes("sublocality")) city = component.longText;
                    if (types.includes("administrative_area_level_1")) stateCode = component.shortText;
                    if (types.includes("postal_code")) zip = component.shortText;
                    if (types.includes("country")) countryCode = component.shortText;
                }
            }
            
            // Reconstruct full street address
            const fullAddress = `${street_number} ${route}`.trim() || streetString;
            const isOrigin = this.props.name.includes("origin");
            const prefix = isOrigin ? "biziship_origin_" : "biziship_dest_";
            
            // Update UI Field explicitly
            input.value = fullAddress;
            input.dispatchEvent(new Event("change", { bubbles: true }));
            
            // Sync with backend & Smarty API
            this.orm.call("sale.order", "biziship_resolve_address", [
                this.props.record.resId || 0, fullAddress, city, stateCode, zip, countryCode, prefix
            ]).then((result) => {
                if (result) {
                    result[`${prefix}address_invalid`] = false;
                    result[`${prefix}address2`] = '';
                    this.props.record.update(result);
                }
            });
            
        } catch (err) {
            console.error("Error fetching place details:", err);
        }
    }
}

BiziShipPlacesAutocomplete.template = "web.CharField";
BiziShipPlacesAutocomplete.components = { ...CharField.components };
BiziShipPlacesAutocomplete.props = CharField.props;

export const biziShipPlacesField = {
    ...registry.category("fields").get("char"),  // inherit all properties from the standard Char field
    component: BiziShipPlacesAutocomplete,
};

registry.category("fields").add("biziship_places", biziShipPlacesField);
