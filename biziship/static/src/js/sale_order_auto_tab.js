/** Auto-activate LTL Freight Details tab on sale.order forms */
(function() {
    'use strict';

    // Activate freight tab when form loads
    activateFreightTab();

    // Also watch for dynamic loads
    document.addEventListener('DOMContentLoaded', activateFreightTab);
    if (document.readyState === 'loading') {
        document.addEventListener('readystatechange', activateFreightTab);
    }

    function activateFreightTab() {
        // Check if we're on a sale.order form
        const isQuotation = document.querySelector('[data-name="quotation_template"]') !== null ||
                           document.querySelector('[data-model="sale.order"]') !== null ||
                           window.location.href.includes('model=sale.order');

        if (!isQuotation) return;

        // Try to activate LTL Freight Details tab
        const freightTab = document.querySelector('[data-page-name="biziship_freight_details"]');
        if (freightTab) {
            setTimeout(function() {
                // Only click if not already active
                if (!freightTab.classList.contains('active')) {
                    freightTab.click();
                }
            }, 200);
        }
    }
})();
