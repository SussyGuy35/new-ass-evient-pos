/**
 * EViENT POS - UI Library
 * Shared UI components and logic
 */

window.customSelectWrappers = window.customSelectWrappers || new Map();
window.customSelectPanels = window.customSelectPanels || new Map();

function initCustomSelect(selectElement) {
    if (!selectElement) return;

    // Check if it already has a custom wrapper, if so, remove it to rebuild
    if (window.customSelectWrappers.has(selectElement)) {
        const oldWrapper = window.customSelectWrappers.get(selectElement);
        if (oldWrapper && oldWrapper.parentNode) {
            oldWrapper.parentNode.removeChild(oldWrapper);
        }
    }
    if (window.customSelectPanels.has(selectElement)) {
        const oldPanel = window.customSelectPanels.get(selectElement);
        if (oldPanel && oldPanel.parentNode) {
            oldPanel.parentNode.removeChild(oldPanel);
        }
    }

    // Hide original select
    selectElement.style.display = 'none';

    // Get options
    const options = Array.from(selectElement.options);
    const selectedOption = selectElement.options[selectElement.selectedIndex];
    const initialText = selectedOption ? selectedOption.text : '-- Chọn --';
    
    // Check if we need search (more than 5 options)
    const showSearch = selectElement.dataset.search !== 'false' && options.length > 5;

    // Create wrapper
    const wrapper = document.createElement('div');
    wrapper.className = 'custom-select-wrapper';
    
    // Copy styles from select to wrapper
    wrapper.style.flex = selectElement.style.flex || '';
    if (selectElement.style.width) wrapper.style.width = selectElement.style.width;
    if (selectElement.style.minHeight) wrapper.style.minHeight = selectElement.style.minHeight;

    // Create trigger
    const trigger = document.createElement('div');
    trigger.className = 'custom-select-trigger';
    
    // Copy padding and font size for exact match
    if (selectElement.style.padding) {
        trigger.style.padding = selectElement.style.padding;
        trigger.style.paddingRight = '0.75rem'; // Override to remove native select's large arrow padding
    }
    if (selectElement.style.fontSize) trigger.style.fontSize = selectElement.style.fontSize;
    
    const classNames = selectElement.className.replace('form-select', '').split(' ').filter(c => c);
    classNames.forEach(c => trigger.classList.add(c));
    
    const label = document.createElement('span');
    label.className = 'custom-select-label';
    label.textContent = initialText;
    
    const icon = document.createElement('div');
    icon.style.marginLeft = 'auto';
    icon.style.flexShrink = '0';
    icon.innerHTML = '<svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" /></svg>';
    
    trigger.appendChild(label);
    trigger.appendChild(icon);

    // Create panel
    const panel = document.createElement('div');
    panel.className = 'custom-select-panel';

    let searchInput;
    if (showSearch) {
        const searchDiv = document.createElement('div');
        searchDiv.className = 'custom-select-search';
        searchInput = document.createElement('input');
        searchInput.type = 'text';
        searchInput.placeholder = 'Tìm kiếm...';
        searchInput.autocomplete = 'off';
        searchDiv.appendChild(searchInput);
        panel.appendChild(searchDiv);
    }

    const list = document.createElement('ul');
    list.className = 'custom-select-list';

    // Helper escape
    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    // Render options
    const renderOptions = () => {
        list.innerHTML = '';
        if (options.length === 0) {
            const emptyLi = document.createElement('li');
            emptyLi.className = 'custom-select-option-empty';
            emptyLi.textContent = 'Không có lựa chọn';
            list.appendChild(emptyLi);
        } else {
            options.forEach(opt => {
                const li = document.createElement('li');
                li.className = 'custom-select-option';
                if (opt.selected) li.classList.add('selected');
                
                const text = opt.text;
                li.dataset.value = opt.value;
                
                // Format "Name (Barcode)" if matched
                if (text.includes('(') && text.endsWith(')')) {
                    const match = text.match(/^(.*) \((.*)\)$/);
                    if (match) {
                        li.innerHTML = `${escapeHtml(match[1])} <span style="color: #94A3B8; font-size: 0.875rem;">(${escapeHtml(match[2])})</span>`;
                    } else {
                        li.textContent = text;
                    }
                } else {
                    li.textContent = text;
                }
                
                li.addEventListener('click', (e) => {
                    e.stopPropagation();
                    // Update select
                    selectElement.value = opt.value;
                    label.textContent = opt.text;
                    
                    // Update active class
                    Array.from(list.children).forEach(child => child.classList.remove('selected'));
                    li.classList.add('selected');
                    
                    // Close panel
                    closeAllCustomSelects();
                    
                    // Trigger change event
                    const event = new Event('change', { bubbles: true });
                    selectElement.dispatchEvent(event);
                });
                
                list.appendChild(li);
            });
        }
    };
    
    renderOptions();
    panel.appendChild(list);

    // Assembly
    wrapper.appendChild(trigger);
    
    // Append panel to body to break out of modal overflows
    document.body.appendChild(panel);
    
    // Insert wrapper after select
    selectElement.parentNode.insertBefore(wrapper, selectElement.nextSibling);
    
    // Save to registry
    window.customSelectWrappers.set(selectElement, wrapper);
    window.customSelectPanels.set(selectElement, panel);

    // Link them together for event handling
    trigger.customPanel = panel;
    panel.customTrigger = trigger;

    // Event listeners
    trigger.addEventListener('click', (e) => {
        e.stopPropagation();
        const isActive = panel.classList.contains('active');
        
        // Close others
        closeAllCustomSelects();
        
        if (!isActive) {
            // Position panel
            const rect = trigger.getBoundingClientRect();
            panel.style.position = 'fixed';
            panel.style.top = (rect.bottom + 4) + 'px';
            panel.style.left = rect.left + 'px';
            panel.style.width = rect.width + 'px';
            panel.style.zIndex = '999999';

            panel.classList.add('active');
            trigger.classList.add('active');
            if (showSearch && searchInput) {
                searchInput.value = '';
                Array.from(list.children).forEach(li => {
                    if (li.classList.contains('custom-select-option')) li.style.display = '';
                });
                setTimeout(() => searchInput.focus(), 50);
            }
        }
    });

    if (showSearch && searchInput) {
        searchInput.addEventListener('click', (e) => e.stopPropagation());
        searchInput.addEventListener('input', (e) => {
            const val = e.target.value.toLowerCase();
            Array.from(list.children).forEach(li => {
                if (!li.classList.contains('custom-select-option')) return;
                const text = li.textContent.toLowerCase();
                li.style.display = text.includes(val) ? '' : 'none';
            });
        });
    }
}

// Global functions for custom selects
window.closeAllCustomSelects = function() {
    document.querySelectorAll('.custom-select-panel').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.custom-select-trigger').forEach(t => t.classList.remove('active'));
};

// Global click handler to close custom select panels
document.addEventListener('click', (e) => {
    const isTrigger = e.target.closest('.custom-select-trigger');
    const isPanel = e.target.closest('.custom-select-panel');
    if (!isTrigger && !isPanel) {
        if (typeof window.closeAllCustomSelects === 'function') {
            window.closeAllCustomSelects();
        }
    }
});

// Close panels on scroll or resize to prevent them from detaching from triggers
window.addEventListener('scroll', (e) => {
    if (!e.target.closest('.custom-select-panel')) {
        if (typeof window.closeAllCustomSelects === 'function') {
            window.closeAllCustomSelects();
        }
    }
}, true); // Use capture phase to catch scrolls on any element

window.addEventListener('resize', () => {
    if (typeof window.closeAllCustomSelects === 'function') {
        window.closeAllCustomSelects();
    }
});

// Helper function to initialize all static selects
function initAllCustomSelects() {
    document.querySelectorAll('select.form-select').forEach(sel => {
        // Exclude specific ones if needed, otherwise apply to all form-select
        if (!sel.classList.contains('no-custom-select')) {
            initCustomSelect(sel);
        }
    });
}

// Global functions for sync indicator
window.showSyncIndicator = function() {
    const el = document.getElementById('sync-indicator');
    if (el) el.style.display = 'flex';
};

window.hideSyncIndicator = function() {
    const el = document.getElementById('sync-indicator');
    if (el) el.style.display = 'none';
};
