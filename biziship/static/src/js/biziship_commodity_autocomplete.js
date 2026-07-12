/** @odoo-module **/

import { registry } from "@web/core/registry";
import { CharField } from "@web/views/fields/char/char_field";
import { useService } from "@web/core/utils/hooks";
import { onMounted, useState, useRef } from "@odoo/owl";

const COMMODITIES = [
    "Computer desktops", "Computer laptops / notebooks", "Computer monitors / displays", "Computer servers / rack units", 
    "Electronic components / circuit boards", "LED lighting fixtures", "Network switches / routers", "Printers / copiers / scanners", 
    "Projectors / presentation equipment", "Smartphones / tablets", "Solar panels / photovoltaic modules", 
    "Televisions / flat-screen displays", "UPS units / battery backup systems",
    "Air compressors", "CNC machines / machining centers", "Conveyor systems / conveyor belts", "Electric motors", 
    "Generators / diesel generators", "Hydraulic cylinders", "Hydraulic pumps", "Industrial fans / blowers", 
    "Industrial mixers / agitators", "Industrial scales / weighing equipment", "Industrial valves / pipe fittings", 
    "Machine tools / lathes / milling machines", "Packaging machinery", "Printing presses / printing machines", 
    "Pumps / centrifugal pumps / submersible pumps", "Welding equipment / welders",
    "Automotive batteries / car batteries", "Automotive brake components", "Automotive exhaust systems / mufflers", 
    "Automotive filters (oil, air, fuel)", "Automotive lighting / headlamps", "Automotive seat covers / interior trim", 
    "Automotive transmissions / gearboxes", "Engine parts / cylinder heads", "Tires / pneumatic tires", 
    "Wheels / rims / alloy wheels", "Windshields / automotive glass",
    "Bookcases / shelving units", "Chairs / office chairs / task chairs", "Desks / office desks / workstations", 
    "Dining room sets / dining tables", "Dressers / wardrobes / armoires", "Filing cabinets / storage cabinets", 
    "Mattresses / box springs", "Outdoor furniture / patio sets", "Sectional sofas / couches / loveseats", 
    "Tables / coffee tables / end tables", "TV stands / entertainment centers",
    "Air conditioners / window AC units", "Dishwashers", "Dryers / clothes dryers", "Freezers / chest freezers", 
    "Microwaves", "Refrigerators / fridges", "Stoves / ovens / cooking ranges", "Washing machines", 
    "Water heaters / tankless water heaters",
    "Cabinets / kitchen cabinets / bathroom vanities", "Ceiling tiles / drop ceiling panels", "Concrete blocks / masonry / cinder blocks", 
    "Doors / interior doors / exterior doors", "Electrical conduit / wiring / cable trays", "Flooring / hardwood flooring / laminate flooring", 
    "HVAC ductwork / air handling units", "Insulation materials / fiberglass batts", "Lumber / wood planks / timber", 
    "Plumbing fixtures / faucets / sinks", "Roofing materials / shingles / membranes", "Steel beams / structural steel / I-beams", 
    "Steel coils / steel sheets / flat-rolled steel", "Steel pipes / steel tubes / pipe fittings", "Windows / window frames / window assemblies",
    "Beer / craft beer (bottled or canned)", "Bottled water / soft drinks / beverages", "Canned goods / canned food products", 
    "Coffee / coffee beans / ground coffee", "Distilled spirits / liquor / whiskey / vodka", "Energy drinks / sports drinks", 
    "Frozen foods / frozen meals", "Snack foods / packaged dry foods", "Wine / bottled wine",
    "Dental equipment / dental chairs", "Hospital beds / medical furniture", "Medical devices / diagnostic equipment", 
    "Medical supplies / disposable medical products", "Mobility aids / walkers / canes", "Pharmaceutical products / medications", 
    "Wheelchairs / power wheelchairs",
    "Apparel / clothing / garments", "Carpets / area rugs / floor coverings", "Curtains / window treatments / blinds", 
    "Footwear / shoes / boots", "Textile / fabric rolls / bolt fabric", "Uniforms / workwear", "Upholstery fabric / foam padding",
    "Adhesives / industrial glues / sealants", "Cleaning products / industrial detergents", "Epoxy / resin / industrial coatings", 
    "Fertilizers / soil amendments", "Lubricants / industrial oils / greases", "Paints / architectural coatings", 
    "Solvents / degreasers (non-hazmat)",
    "Bicycles / electric bikes (e-bikes)", "Exercise equipment / treadmills / ellipticals", "Golf equipment / golf carts", 
    "Outdoor / camping equipment", "Playground equipment / swing sets", "Sporting goods / fitness accessories", "Toys / games / hobby items",
    "Electrical cabinets / control panels", "Electrical wire / copper wire / cable", "Power transformers / distribution transformers", 
    "Switchgear / circuit breakers",
    "Boilers / commercial boilers", "Heat pumps / split systems", "Pipe insulation / pipe wrap", "PVC pipes / PVC fittings", 
    "Water pumps / well pumps"
];

const NMFC_RULES = [
    { keywords: ['refrigerator', 'fridge', 'freezer'], code: '086720', conf: 0.82 },
    { keywords: ['washer', 'washing machine', 'clothes dryer'], code: '119900', conf: 0.82 },
    { keywords: ['dishwasher'], code: '086710', conf: 0.82 },
    { keywords: ['oven', 'gas range', 'electric range', 'stove'], code: '086740', conf: 0.82 },
    { keywords: ['microwave'], code: '086760', conf: 0.80 },
    { keywords: ['air conditioner', 'hvac unit', 'heat pump'], code: '009630', conf: 0.80 },
    { keywords: ['water heater'], code: '191960', conf: 0.82 },
    { keywords: ['sofa', 'couch', 'sectional', 'loveseat'], code: '089050', conf: 0.82 },
    { keywords: ['mattress', 'box spring'], code: '108000', conf: 0.82 },
    { keywords: ['office chair', 'desk chair', 'task chair'], code: '089010', conf: 0.80 },
    { keywords: ['dining table', 'coffee table', 'end table'], code: '089080', conf: 0.78 },
    { keywords: ['desk', 'office desk'], code: '089080', conf: 0.78 },
    { keywords: ['cabinet', 'dresser', 'wardrobe'], code: '089080', conf: 0.76 },
    { keywords: ['computer', 'laptop', 'notebook', 'desktop'], code: '060920', conf: 0.82 },
    { keywords: ['server', 'rack server'], code: '060920', conf: 0.80 },
    { keywords: ['monitor', 'display screen', 'lcd monitor'], code: '060920', conf: 0.80 },
    { keywords: ['television', 'flat screen tv', 'smart tv'], code: '102280', conf: 0.82 },
    { keywords: ['printer', 'copier', 'inkjet', 'laser'], code: '060920', conf: 0.78 },
    { keywords: ['telephone', 'pbx system'], code: '171700', conf: 0.78 },
    { keywords: ['hydraulic pump', 'centrifugal pump'], code: '114860', conf: 0.82 },
    { keywords: ['air compressor', 'rotary compressor'], code: '055800', conf: 0.82 },
    { keywords: ['generator', 'diesel generator'], code: '084160', conf: 0.80 },
    { keywords: ['electric motor', 'ac motor', 'dc motor'], code: '114870', conf: 0.80 },
    { keywords: ['forklift', 'lift truck', 'pallet jack'], code: '084700', conf: 0.82 },
    { keywords: ['conveyor', 'conveyor belt'], code: '056500', conf: 0.78 },
    { keywords: ['cnc machine', 'lathe', 'milling machine'], code: '114860', conf: 0.76 },
    { keywords: ['tire', 'tires', 'pneumatic tire'], code: '183540', conf: 0.82 },
    { keywords: ['automobile', 'car engine', 'vehicle engine'], code: '084320', conf: 0.78 },
    { keywords: ['brake pad', 'brake rotor', 'disc brake'], code: '012200', conf: 0.78 },
    { keywords: ['car battery', 'auto battery', 'lead acid'], code: '021600', conf: 0.80 },
    { keywords: ['automotive filter', 'oil filter', 'air filter', 'fuel filter'], code: '012200', conf: 0.78 },
    { keywords: ['auto part', 'automotive part', 'car part'], code: '012200', conf: 0.72 },
    { keywords: ['lumber', 'timber', 'wood plank', 'hardwood'], code: '110120', conf: 0.80 },
    { keywords: ['steel pipe', 'iron pipe', 'pipe fitting'], code: '120260', conf: 0.80 },
    { keywords: ['steel coil', 'steel sheet', 'flat rolled'], code: '152650', conf: 0.78 },
    { keywords: ['electrical wire', 'copper wire', 'coaxial'], code: '065500', conf: 0.80 },
    { keywords: ['concrete block', 'cinder block', 'masonry'], code: '040600', conf: 0.80 },
    { keywords: ['insulation', 'fiberglass insulation'], code: '093140', conf: 0.78 },
    { keywords: ['copy paper', 'printing paper', 'paper ream'], code: '146280', conf: 0.82 },
    { keywords: ['book', 'textbook', 'hardcover', 'paperback'], code: '026080', conf: 0.82 },
    { keywords: ['cardboard', 'corrugated box'], code: '040040', conf: 0.78 },
    { keywords: ['paint', 'latex paint', 'exterior paint'], code: '146360', conf: 0.80 },
    { keywords: ['lubricant', 'gear oil', 'hydraulic oil'], code: '086960', conf: 0.78 },
    { keywords: ['adhesive', 'epoxy', 'glue', 'sealant'], code: '003240', conf: 0.76 },
    { keywords: ['bottled wine', 'case of wine'], code: '190240', conf: 0.82 },
    { keywords: ['beer', 'canned beer', 'bottled beer'], code: '190510', conf: 0.80 },
    { keywords: ['whiskey', 'bourbon', 'vodka', 'spirits'], code: '190300', conf: 0.82 },
    { keywords: ['clothing', 'apparel', 'garment', 'shirt'], code: '181870', conf: 0.80 },
    { keywords: ['fabric', 'textile', 'woven fabric'], code: '182210', conf: 0.78 },
    { keywords: ['carpet', 'area rug', 'rug'], code: '036700', conf: 0.80 },
    { keywords: ['bicycle', 'bike', 'mountain bike'], code: '023040', conf: 0.82 },
    { keywords: ['treadmill', 'elliptical', 'exercise bike'], code: '084160', conf: 0.76 },
    { keywords: ['wheelchair', 'power wheelchair'], code: '106870', conf: 0.82 },
    { keywords: ['hospital bed', 'medical bed'], code: '086100', conf: 0.80 },
    { keywords: ['medical device', 'diagnostic equipment'], code: '106690', conf: 0.72 }
];

const GENERIC_TERMS = ['freight', 'goods', 'cargo', 'shipment', 'items', 'general freight'];

export class BiziShipCommodityAutocomplete extends CharField {
    setup() {
        super.setup();
        this.state = useState({
            suggestions: [],
            showDropdown: false,
            isProcessing: false,
            currentValue: this.props.record.data[this.props.name] || ""
        });
        this.inputRef = useRef("input");
        this.rpc = useService("rpc");
        this.debounceTimer = null;
        
        onMounted(() => {
            this._initAutocomplete();
        });
    }

    _initAutocomplete() {
        // Handled by OWL events
    }

    _onInput(ev) {
        const val = ev.target.value;
        this.state.currentValue = val;
        
        // Autocomplete
        const words = val.toLowerCase().split(/\s+/).filter(w => w && w.length > 0);
        if (words.length === 0 || val.length < 2) {
            this.state.showDropdown = false;
        } else {
            const matches = COMMODITIES.filter(c => {
                const lowerC = c.toLowerCase();
                return words.every(w => lowerC.includes(w));
            });
            // Sort match
            const lowerVal = val.toLowerCase();
            matches.sort((a, b) => {
                const aLow = a.toLowerCase();
                const bLow = b.toLowerCase();
                const aStarts = aLow.startsWith(lowerVal);
                const bStarts = bLow.startsWith(lowerVal);
                if (aStarts && !bStarts) return -1;
                if (!aStarts && bStarts) return 1;
                return aLow.localeCompare(bLow);
            });
            this.state.suggestions = matches.slice(0, 10);
            this.state.showDropdown = this.state.suggestions.length > 0;
        }

        // Hide old suggestion labels immediately in record (silently)
        // Note: we ONLY update the meta-fields, NOT the main text field yet to avoid re-render loops
        this.props.record.update({ 
            nmfc_suggestion_label: false,
            nmfc_suggested_code: false,
            nmfc_suggestion_rationale: false
        });

        // Suggestion Debounce
        clearTimeout(this.debounceTimer);
        const lowerVal = val.toLowerCase();
        if (GENERIC_TERMS.includes(lowerVal)) {
            this.props.record.update({ nmfc_suggestion_label: 'low' });
            return;
        }
        if (val.length < 4) {
            return;
        }
        this.debounceTimer = setTimeout(() => {
            if (this.state.currentValue === val) {
                // Sync the main text field to the record right before suggesting
                this.props.record.update({ [this.props.name]: val });
                this._suggestNMFC(val);
            }
        }, 1500);
    }
    _onBlur() {
        // Sync local value to record on blur to ensure Odoo saves it
        this.props.record.update({ [this.props.name]: this.state.currentValue });
        
        // Small delay to allow clicking on dropdown items
        setTimeout(() => {
            this.state.showDropdown = false;
        }, 200);
    }

    _onKeyDown(ev) {
        if (ev.key === "Enter" && this.state.showDropdown && this.state.suggestions.length > 0) {
            ev.preventDefault();
            this._onSuggestionClick(this.state.suggestions[0]);
        } else if (ev.key === "Escape") {
            this.state.showDropdown = false;
        }
    }

    async _onSuggestionClick(suggestion) {
        this.state.currentValue = suggestion;
        await this.props.record.update({ 
            [this.props.name]: suggestion,
            nmfc_suggestion_label: false,
            nmfc_suggested_code: false
        });
        this.state.showDropdown = false;
        this._suggestNMFC(suggestion);
    }

    async _suggestNMFC(desc) {
        // 1. Rule-Based Lookup
        const match = this._findRuleMatch(desc);
        if (match && match.conf >= 0.65) {
            const label = match.conf >= 0.85 ? 'high' : 'medium';
            const updates = {
                nmfc_suggested_code: match.code,
                nmfc_suggestion_confidence: match.conf,
                nmfc_suggestion_label: label,
                nmfc_suggestion_rationale: "Rule-based match from internal database."
            };
            if (label === 'high') {
                updates.nmfc = match.code;
                updates.nmfc_applied_desc = desc;
            }
            await this.props.record.update(updates);
            return;
        }

        // 2. AI Fallback via Proxy
        await this.rpc("/web/dataset/call_button", {
            model: "biziship.sale.cargo.line",
            method: "action_biziship_nmfc_suggest",
            args: [[this.props.record.resId]],
            kwargs: {},
        });
    }

    _findRuleMatch(desc) {
        const d = desc.toLowerCase();
        for (const rule of NMFC_RULES) {
            if (rule.keywords.some(k => d.includes(k))) return rule;
        }
        return null;
    }

    async _dismissSuggestion() {
        await this.props.record.update({
            nmfc_suggested_code: false,
            nmfc_suggestion_label: false
        });
    }

    async _applySuggestion() {
        const data = this.props.record.data;
        const code = data.nmfc_suggested_code;
        this.state.currentValue = data.cargo_desc; // Ensure local state matches applied desc if needed
        await this.props.record.update({
            nmfc: code,
            nmfc_applied_desc: data.cargo_desc,
            nmfc_suggested_code: false,
            nmfc_suggestion_label: false
        });
    }

    async _clearAppliedNMFC() {
        await this.props.record.update({
            nmfc: "",
            nmfc_applied_desc: false
        });
    }
}

BiziShipCommodityAutocomplete.template = "biziship.CommodityAutocomplete";
BiziShipCommodityAutocomplete.components = { ...CharField.components };
BiziShipCommodityAutocomplete.props = { ...CharField.props };

registry.category("fields").add("biziship_commodity", {
    ...registry.category("fields").get("char"),
    component: BiziShipCommodityAutocomplete,
});
