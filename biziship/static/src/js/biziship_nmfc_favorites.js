/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

class NmfcFavoritesDialog extends Component {
    static template = "biziship.NmfcFavoritesDialog";
    static components = { Dialog };
    static props = {
        record: { type: Object },
        close: { type: Function },
    };

    setup() {
        this.orm = useService("orm");
        this.state = useState({
            favorites: [],
            loading: true,
            filter: "",
            confirmDeleteId: null,
            addDesc: this.props.record.data.cargo_desc || "",
            addNmfc: "",
            addError: "",
            saving: false,
        });
        onWillStart(async () => {
            await this._loadFavorites();
        });
    }

    async _loadFavorites() {
        this.state.loading = true;
        try {
            const favorites = await this.orm.call(
                "biziship.sale.cargo.line",
                "action_biziship_get_nmfc_favorites",
                []
            );
            this.state.favorites = favorites || [];
        } catch (e) {
            console.warn("BiziShip NMFC Favorites load error:", e);
            this.state.favorites = [];
        }
        this.state.loading = false;
    }

    get filteredFavorites() {
        const q = (this.state.filter || "").toLowerCase();
        if (!q) return this.state.favorites;
        return this.state.favorites.filter(
            (f) =>
                f.description.toLowerCase().includes(q) ||
                f.nmfc_code.toLowerCase().includes(q)
        );
    }

    onFilterInput(ev) {
        this.state.filter = ev.target.value;
    }

    onUse(fav) {
        this.props.record.update({
            cargo_desc: fav.description,
            nmfc: fav.nmfc_code,
            nmfc_suggested_code: false,
            nmfc_suggestion_confidence: 0,
            nmfc_suggestion_label: false,
        });
        this.props.close();
    }

    onTrashClick(favId) {
        this.state.confirmDeleteId = favId;
    }

    onDeleteCancel() {
        this.state.confirmDeleteId = null;
    }

    async onDeleteConfirm(favId) {
        try {
            await this.orm.call(
                "biziship.sale.cargo.line",
                "action_biziship_delete_nmfc_favorite",
                [],
                { favorite_id: favId }
            );
            this.state.favorites = this.state.favorites.filter((f) => f.id !== favId);
            this.state.confirmDeleteId = null;
        } catch (e) {
            console.warn("BiziShip NMFC Favorites delete error:", e);
        }
    }

    onAddDescInput(ev) {
        this.state.addDesc = ev.target.value;
    }

    onAddNmfcInput(ev) {
        this.state.addNmfc = ev.target.value;
    }

    async onSave() {
        const desc = (this.state.addDesc || "").trim();
        const nmfc = (this.state.addNmfc || "").trim();
        if (!desc || !nmfc) {
            this.state.addError = "Both description and NMFC code are required.";
            return;
        }
        this.state.addError = "";
        this.state.saving = true;
        try {
            const newFav = await this.orm.call(
                "biziship.sale.cargo.line",
                "action_biziship_save_nmfc_favorite",
                [],
                { description: desc, nmfc_code: nmfc }
            );
            this.state.favorites = [...this.state.favorites, newFav].sort((a, b) =>
                a.description.localeCompare(b.description)
            );
            this.state.addNmfc = "";
            this.state.addDesc = this.props.record.data.cargo_desc || "";
        } catch (e) {
            this.state.addError =
                (e.data && e.data.message) || e.message || "Failed to save favorite.";
        }
        this.state.saving = false;
    }
}

class BizishipNmfcStarWidget extends Component {
    static template = "biziship.NmfcStarWidget";
    static props = { ...standardFieldProps };

    setup() {
        this.dialog = useService("dialog");
    }

    openFavorites() {
        this.dialog.add(NmfcFavoritesDialog, {
            record: this.props.record,
        });
    }
}

registry.category("fields").add("biziship_nmfc_star", {
    component: BizishipNmfcStarWidget,
    displayName: "BiziShip NMFC Favorites",
    supportedTypes: ["boolean"],
});
