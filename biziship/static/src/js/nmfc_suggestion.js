/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { KanbanRecord } from "@web/views/kanban/kanban_record";
import { useService } from "@web/core/utils/hooks";
import { onWillStart, onMounted, useState, useRef } from "@odoo/owl";

// NMFC Rule-Based Lookup Table
const NMFC_RULES = [
    // Appliances
    { keywords: ['refrigerator', 'fridge', 'freezer'], code: '086720', conf: 0.82 },
    { keywords: ['washer', 'washing machine', 'clothes dryer'], code: '119900', conf: 0.82 },
    { keywords: ['dishwasher'], code: '086710', conf: 0.82 },
    { keywords: ['oven', 'gas range', 'electric range', 'stove'], code: '086740', conf: 0.82 },
    { keywords: ['microwave'], code: '086760', conf: 0.80 },
    { keywords: ['air conditioner', 'hvac unit', 'heat pump'], code: '009630', conf: 0.80 },
    { keywords: ['water heater'], code: '191960', conf: 0.82 },
    // Furniture
    { keywords: ['sofa', 'couch', 'sectional', 'loveseat'], code: '089050', conf: 0.82 },
    { keywords: ['mattress', 'box spring'], code: '108000', conf: 0.82 },
    { keywords: ['office chair', 'desk chair', 'task chair'], code: '089010', conf: 0.80 },
    { keywords: ['dining table', 'coffee table', 'end table'], code: '089080', conf: 0.78 },
    { keywords: ['desk', 'office desk'], code: '089080', conf: 0.78 },
    { keywords: ['cabinet', 'dresser', 'wardrobe'], code: '089080', conf: 0.76 },
    // Electronics
    { keywords: ['computer', 'laptop', 'notebook', 'desktop'], code: '060920', conf: 0.82 },
    { keywords: ['server', 'rack server'], code: '060920', conf: 0.80 },
    { keywords: ['monitor', 'display screen', 'lcd monitor'], code: '060920', conf: 0.80 },
    { keywords: ['television', 'flat screen tv', 'smart tv'], code: '102280', conf: 0.82 },
    { keywords: ['printer', 'copier', 'inkjet', 'laser'], code: '060920', conf: 0.78 },
    { keywords: ['telephone', 'pbx system'], code: '171700', conf: 0.78 },
    // Industrial Machinery
    { keywords: ['hydraulic pump', 'centrifugal pump'], code: '114860', conf: 0.82 },
    { keywords: ['air compressor', 'rotary compressor'], code: '055800', conf: 0.82 },
    { keywords: ['generator', 'diesel generator'], code: '084160', conf: 0.80 },
    { keywords: ['electric motor', 'ac motor', 'dc motor'], code: '114870', conf: 0.80 },
    { keywords: ['forklift', 'lift truck', 'pallet jack'], code: '084700', conf: 0.82 },
    { keywords: ['conveyor', 'conveyor belt'], code: '056500', conf: 0.78 },
    { keywords: ['cnc machine', 'lathe', 'milling machine'], code: '114860', conf: 0.76 },
    // Automotive
    { keywords: ['tire', 'tires', 'pneumatic tire'], code: '183540', conf: 0.82 },
    { keywords: ['automobile', 'car engine', 'vehicle engine'], code: '084320', conf: 0.78 },
    { keywords: ['brake pad', 'brake rotor', 'disc brake'], code: '012200', conf: 0.78 },
    { keywords: ['car battery', 'auto battery', 'lead acid'], code: '021600', conf: 0.80 },
    { keywords: ['automotive filter', 'oil filter', 'air filter', 'fuel filter'], code: '012200', conf: 0.78 },
    { keywords: ['auto part', 'automotive part', 'car part'], code: '012200', conf: 0.72 },
    // Building Materials
    { keywords: ['lumber', 'timber', 'wood plank', 'hardwood'], code: '110120', conf: 0.80 },
    { keywords: ['steel pipe', 'iron pipe', 'pipe fitting'], code: '120260', conf: 0.80 },
    { keywords: ['steel coil', 'steel sheet', 'flat rolled'], code: '152650', conf: 0.78 },
    { keywords: ['electrical wire', 'copper wire', 'coaxial'], code: '065500', conf: 0.80 },
    { keywords: ['concrete block', 'cinder block', 'masonry'], code: '040600', conf: 0.80 },
    { keywords: ['insulation', 'fiberglass insulation'], code: '093140', conf: 0.78 },
    // Paper & Print
    { keywords: ['copy paper', 'printing paper', 'paper ream'], code: '146280', conf: 0.82 },
    { keywords: ['book', 'textbook', 'hardcover', 'paperback'], code: '026080', conf: 0.82 },
    { keywords: ['cardboard', 'corrugated box'], code: '040040', conf: 0.78 },
    // Chemicals & Paints
    { keywords: ['paint', 'latex paint', 'exterior paint'], code: '146360', conf: 0.80 },
    { keywords: ['lubricant', 'gear oil', 'hydraulic oil'], code: '086960', conf: 0.78 },
    { keywords: ['adhesive', 'epoxy', 'glue', 'sealant'], code: '003240', conf: 0.76 },
    // Food & Beverage
    { keywords: ['bottled wine', 'case of wine'], code: '190240', conf: 0.82 },
    { keywords: ['beer', 'canned beer', 'bottled beer'], code: '190510', conf: 0.80 },
    { keywords: ['whiskey', 'bourbon', 'vodka', 'spirits'], code: '190300', conf: 0.82 },
    // Textiles & Apparel
    { keywords: ['clothing', 'apparel', 'garment', 'shirt'], code: '181870', conf: 0.80 },
    { keywords: ['fabric', 'textile', 'woven fabric'], code: '182210', conf: 0.78 },
    { keywords: ['carpet', 'area rug', 'rug'], code: '036700', conf: 0.80 },
    // Sports & Recreation
    { keywords: ['bicycle', 'bike', 'mountain bike'], code: '023040', conf: 0.82 },
    { keywords: ['treadmill', 'elliptical', 'exercise bike'], code: '084160', conf: 0.76 },
    // Medical
    { keywords: ['wheelchair', 'power wheelchair'], code: '106870', conf: 0.82 },
    { keywords: ['hospital bed', 'medical bed'], code: '086100', conf: 0.80 },
    { keywords: ['medical device', 'diagnostic equipment'], code: '106690', conf: 0.72 }
];

const GENERIC_TERMS = ['freight', 'goods', 'cargo', 'shipment', 'items'];

// Patch KanbanRecord to add NMFC suggestion logic
patch(KanbanRecord.prototype, {
    setup() {
        super.setup();
        this.rpc = useService("rpc");
        this.nmfcState = useState({
            suggestedCode: null,
            confidence: 0,
            label: null,
            rationale: null,
            isStale: false,
            alternativeSuggestions: [],
            isProcessing: false
        });
        
        this.debounceTimer = null;
        
        onMounted(() => {
            // Check initial state for staleness if applied
            this._checkStaleness();
        });
    },

    /**
     * Triggered by description change (debounced)
     */
    onCargoDescChanged(ev) {
        if (this.debounceTimer) clearTimeout(this.debounceTimer);
        
        const desc = ev.target.value || "";
        if (desc.length < 4 || GENERIC_TERMS.includes(desc.toLowerCase())) {
            return;
        }

        this.debounceTimer = setTimeout(() => {
            this._suggestNMFC(desc);
        }, 1500);
    },

    /**
     * Manual trigger via Star button
     */
    async onSuggestButtonClick() {
        const desc = this.props.record.data.cargo_desc || "";
        await this._suggestNMFC(desc, true);
    },

    async _suggestNMFC(desc, manual = false) {
        // 1. Rule-Based Lookup (Client-side)
        const match = this._findRuleMatch(desc);
        if (match && match.conf >= 0.65) {
            this._updateSuggestionState({
                suggestedCode: match.code,
                confidence: match.conf,
                label: match.conf >= 0.85 ? 'high' : 'medium',
                rationale: "Rule-based match from internal database.",
                alternativeSuggestions: []
            });
            return;
        }

        // 2. AI Fallback (API via Proxy)
        if (manual || !match) {
            this.nmfcState.isProcessing = true;
            try {
                await this.rpc("/web/dataset/call_button", {
                    model: "biziship.sale.cargo.line",
                    method: "action_biziship_nmfc_suggest",
                    args: [[this.props.record.resId]],
                });
            } finally {
                this.nmfcState.isProcessing = false;
            }
        }
    },

    _findRuleMatch(desc) {
        const d = desc.toLowerCase();
        for (const rule of NMFC_RULES) {
            if (rule.keywords.some(k => d.includes(k))) {
                return rule;
            }
        }
        return null;
    },

    _updateSuggestionState(data) {
        Object.assign(this.nmfcState, data);
    },

    _checkStaleness() {
        const record = this.props.record.data;
        if (record.nmfc && record.nmfc_applied_desc && record.cargo_desc !== record.nmfc_applied_desc) {
            this.nmfcState.isStale = true;
        } else {
            this.nmfcState.isStale = false;
        }
    },

    async applySuggestion() {
        const record = this.props.record;
        await record.update({
            nmfc: this.nmfcState.suggestedCode,
            nmfc_applied_desc: record.data.cargo_desc
        });
        this.nmfcState.isStale = false;
    }
});
