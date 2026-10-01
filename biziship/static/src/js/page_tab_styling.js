function stylePageTabs() {
    const tabs = document.querySelectorAll('.o_notebook .nav-link');
    tabs.forEach(tab => {
        if (tab.dataset.styled === 'true') return;

        const text = tab.textContent.trim();
        if (!text.includes('biziShip.ai')) return;

        // Clear the tab content
        while (tab.firstChild) {
            tab.removeChild(tab.firstChild);
        }

        // Split text and rebuild with styled parts
        const parts = text.split(/(biziShip\.ai)/);
        parts.forEach(part => {
            if (part === 'biziShip.ai') {
                const span = document.createElement('span');
                span.style.color = '#f49800';
                span.style.fontWeight = '700';
                span.textContent = part;
                tab.appendChild(span);
            } else if (part) {
                tab.appendChild(document.createTextNode(part));
            }
        });

        tab.dataset.styled = 'true';
    });
}

// Run after a short delay to ensure DOM is ready
setTimeout(stylePageTabs, 100);
document.addEventListener('shown.bs.tab', stylePageTabs);
