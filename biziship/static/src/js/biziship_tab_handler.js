/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";
import { onMounted, onPatched } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

patch(FormController.prototype, {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.lastHandledNonce = null;

        this._bizishipPickupCheckedId = null;

        onMounted(() => {
            this._checkBiziShipTabSwitch();
            this._setupBiziShipHandlers();
            this._bizishipRefreshProfile();
            this._bizishipEnsurePickupToday();
        });
        onPatched(() => {
            this._checkBiziShipTabSwitch();
            this._bizishipEnsurePickupToday();
        });
    },

    // When opening a sale order whose BiziShip pickup date is in the past, advance it to
    // today right on the form — a past pickup date is never valid for a new quote/booking.
    // Touches ONLY biziship_pickup_date; the value is saved with the order's next save
    // (e.g. automatically when "Get Quotes" runs).
    _bizishipEnsurePickupToday() {
        if (!this.props || this.props.resModel !== "sale.order") return;
        const root = this.model.root;
        if (!root || !root.data) return;
        const resId = root.resId; // database id of the saved record (false for new records)
        if (!resId) return;
        // Only evaluate once per record so the update below doesn't re-trigger itself.
        if (this._bizishipPickupCheckedId === resId) return;
        const pickup = root.data.biziship_pickup_date;
        if (!pickup || typeof pickup.startOf !== "function") return; // wait for the field
        this._bizishipPickupCheckedId = resId;
        // Derive "today" from the field value's own luxon class — no extra import needed.
        const today = pickup.constructor.now().startOf("day");
        if (pickup.startOf("day") < today) {
            root.update({ biziship_pickup_date: today }).catch(() => {});
        }
    },

    _setupBiziShipHandlers() {
        if (this.bizishipHandlersInitialized) return;
        this.bizishipHandlersInitialized = true;

        // 1. Autofilter Logic (Debounced)
        document.addEventListener('input', (ev) => {
            const input = ev.target;
            if (input && input.classList && input.classList.contains('biziship-autofilter')) {
                if (this.autoFilterTimeout) clearTimeout(this.autoFilterTimeout);
                this.autoFilterTimeout = setTimeout(() => {
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                }, 300);
            }
        }, true);

        // 1b. Show the "Fetching Live Quotes" progress bar only on a real Get-Quotes click.
        //     (Tying it to the button's :disabled state was too broad — Odoo also disables
        //     the button when the record is dirty/invalid, e.g. after adding a cargo line.)
        document.addEventListener('click', (ev) => {
            const btn = ev.target.closest('.biziship-btn-get-quotes');
            if (!btn) return;
            const formView = btn.closest('.o_form_view');
            if (!formView) return;
            formView.classList.add('biziship-quote-fetching');
            // Safety net: the form reloads after a successful fetch (new DOM, no class),
            // but on a validation error it won't — clear the class after the fetch window.
            setTimeout(() => formView.classList.remove('biziship-quote-fetching'), 18000);
        }, true);

        // 2. Refresh BiziShip user profile when either freight tab is clicked
        document.addEventListener('click', (ev) => {
            const navLink = ev.target.closest('.o_notebook .nav-link');
            if (!navLink) return;
            const tabName = navLink.getAttribute('name') || navLink.getAttribute('data-name');
            if (tabName !== 'biziship_freight_quotes' && tabName !== 'biziship_freight_details') return;
            this._bizishipRefreshProfile();
        }, true);
    },

    _bizishipRefreshProfile() {
        if (!this.props || this.props.resModel !== 'sale.order') return;
        const record = this.model.root;
        const recordId = (record && record.resId) || (record && record.data && record.data.id);
        if (!recordId) return;

        // Debounce: collapse rapid back-to-back calls (e.g. onMounted + tab click)
        // into a single server request to prevent SERIALIZATION_FAILURE on concurrent writes.
        if (this._bizishipRefreshTimer) clearTimeout(this._bizishipRefreshTimer);
        this._bizishipRefreshTimer = setTimeout(() => {
            this._bizishipRefreshTimer = null;
            if (this._bizishipRefreshPending) return;
            this._bizishipRefreshPending = true;
            this.orm.call('sale.order', 'action_biziship_refresh_profile_rpc', [[recordId]])
                .then((result) => this._bizishipApplyProfileResult(result))
                .catch((err) => console.warn('BiziShip refresh error:', err))
                .finally(() => { this._bizishipRefreshPending = false; });
        }, 300);
    },

    _bizishipApplyProfileResult(result) {
        if (!result || !this.model.root) return;
        const root = this.model.root;
        // root.data.id is falsy until the form's own initial web_read has finished
        // populating the RelationalModel. Calling root.load() before that completes
        // creates two concurrent web_read calls that race and corrupt the model state,
        // causing Odoo to try fetching One2many IDs that no longer exist →
        // "Can't fetch record(s) X. They might have been deleted."
        // When the initial load is still in-flight, skip the reload — the form's own
        // web_read will already read the just-written profile values from DB.
        if (!root.data || !root.data.id) return;
        if (typeof root.load === 'function' && !root.dirty) {
            root.load().catch(() => {});
        }
    },

    _checkBiziShipTabSwitch() {
        const record = this.model.root;
        if (!record || !record.data) return;

        const nonce = record.data.biziship_last_fetch_nonce;
        const hasSwitchFlag = this.props.context && this.props.context.biziship_switch_tab;

        if (hasSwitchFlag && nonce && nonce !== this.lastHandledNonce) {
            this.lastHandledNonce = nonce;
            setTimeout(() => {
                const quotesTab = document.querySelector(
                    '.o_notebook [name="biziship_freight_quotes"], .o_notebook [data-name="biziship_freight_quotes"]'
                );
                if (quotesTab && !quotesTab.classList.contains('active')) {
                    quotesTab.click();
                }
            }, 100);
        }
    }
});
