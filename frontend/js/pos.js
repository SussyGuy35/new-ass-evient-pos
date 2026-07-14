/**
 * EViENT POS - Main POS Logic
 * Cart management, product browsing, checkout, barcode scanning.
 */

// --- State ---
let cart = [];
let products = [];
let currentPage = 1;
let totalPages = 1;
let searchQuery = '';
let searchDebounceTimer = null;

// --- Currency Formatter ---
const currencyFormatter = new Intl.NumberFormat('vi-VN');
function formatCurrency(amount) {
    return currencyFormatter.format(amount) + ' đ';
}

// --- Toast Notification ---
function showToast(message, type = 'info') {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'toast-container';
        container.style.top = 'auto';
        container.style.bottom = '1rem';
        container.style.flexDirection = 'column-reverse';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    container.appendChild(toast);

    // Trigger show animation
    requestAnimationFrame(() => {
        toast.classList.add('show');
    });

    // Auto-dismiss after 3 seconds
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 150);
    }, 3000);
}

// --- Product Loading ---
async function loadProducts(page = 1, search = '') {
    currentPage = page;
    searchQuery = search;

    const grid = document.getElementById('product-grid');
    if (!grid) return;

    // Show loading state
    grid.innerHTML = `
        <div class="empty-state" style="grid-column: 1 / -1; padding: 3rem;">
            <div class="spinner"></div>
            <p style="margin-top: 1rem; color: #64748B;">Đang tải sản phẩm...</p>
        </div>
    `;

    try {
        let url = `/products?page=${page}&per_page=${APP_CONFIG.ITEMS_PER_PAGE}`;
        if (search) {
            url += `&q=${encodeURIComponent(search)}`;
        }

        const data = await api.get(url);

        products = data.items || data.products || data || [];
        totalPages = data.total_pages || data.totalPages || 1;
        currentPage = data.page || data.current_page || page;

        renderProducts();
        renderPagination();
    } catch (err) {
        grid.innerHTML = `
            <div class="empty-state" style="grid-column: 1 / -1;">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <circle cx="12" cy="12" r="10"/>
                    <path d="M12 8v4m0 4h.01"/>
                </svg>
                <p>Không thể tải sản phẩm</p>
                <p style="font-size: 0.75rem; margin-top: 0.25rem;">${err.message}</p>
            </div>
        `;
        showToast('Lỗi tải sản phẩm: ' + err.message, 'error');
    }
}

// --- Render Products Grid (ONLY updates #product-grid) ---
function renderProducts() {
    const grid = document.getElementById('product-grid');
    if (!grid) return;

    if (!products || products.length === 0) {
        grid.innerHTML = `
            <div class="empty-state" style="grid-column: 1 / -1;">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <path d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"/>
                </svg>
                <p>Không tìm thấy sản phẩm</p>
            </div>
        `;
        return;
    }

    grid.innerHTML = products.map(function (p) {
        const stockClass = p.stock <= 0 ? 'stock-out' : p.stock <= 10 ? 'stock-low' : 'stock-ok';
        const stockLabel = p.stock <= 0 ? 'Hết hàng' : `Còn ${p.stock}`;
        const isDisabled = p.stock <= 0;

        return `
            <div class="product-card card-hover ${isDisabled ? 'opacity-50' : ''}"
                 ${isDisabled ? '' : `onclick="addToCart('${p.id}')"`}
                 role="button"
                 tabindex="0"
                 id="product-card-${p.id}">
                <div style="font-weight: 600; color: #E2E8F0; font-size: 0.875rem; line-height: 1.3;">
                    ${escapeHtml(p.name)}
                </div>
                <div style="font-size: 1.125rem; font-weight: 700; color: #3B82F6;">
                    ${formatCurrency(p.price)}
                </div>
                <div style="font-size: 0.75rem;" class="${stockClass}">
                    ${stockLabel}
                </div>
                ${p.barcode ? `<div style="font-size: 0.6875rem; color: #475569; font-family: monospace;">${escapeHtml(p.barcode)}</div>` : ''}
            </div>
        `;
    }).join('');
}

// --- Render Pagination (ONLY updates #pagination) ---
function renderPagination() {
    const container = document.getElementById('pagination');
    if (!container) return;

    if (totalPages <= 1) {
        container.innerHTML = '';
        return;
    }

    let html = '<div class="pagination">';

    html += `<button class="page-btn" onclick="loadProducts(${currentPage - 1}, searchQuery)"
                     ${currentPage <= 1 ? 'disabled' : ''}>
                ‹ Trước
             </button>`;

    html += `<span style="color: #94A3B8; font-size: 0.8125rem; padding: 0 0.5rem;">
                Trang ${currentPage} / ${totalPages}
             </span>`;

    html += `<button class="page-btn" onclick="loadProducts(${currentPage + 1}, searchQuery)"
                     ${currentPage >= totalPages ? 'disabled' : ''}>
                Sau ›
             </button>`;

    html += '</div>';
    container.innerHTML = html;
}

// --- Cart Operations ---
function addToCart(productId) {
    const product = products.find(function (p) { return p.id === productId; });
    if (!product) {
        showToast('Không tìm thấy sản phẩm', 'error');
        return;
    }

    if (product.stock <= 0) {
        showToast('Sản phẩm đã hết hàng', 'warning');
        return;
    }

    const existing = cart.find(function (item) { return item.id === productId; });
    if (existing) {
        if (existing.quantity >= product.stock) {
            showToast('Đã đạt số lượng tối đa trong kho', 'warning');
            return;
        }
        existing.quantity += 1;
    } else {
        cart.push({
            id: product.id,
            name: product.name,
            price: product.price,
            quantity: 1,
            stock: product.stock
        });
    }

    showToast(`Đã thêm ${product.name}`, 'success');
    renderCart();
}

function removeFromCart(index) {
    if (index >= 0 && index < cart.length) {
        const item = cart[index];
        cart.splice(index, 1);
        showToast(`Đã xóa ${item.name}`, 'info');
        renderCart();
    }
}

function updateQuantity(index, delta) {
    if (index < 0 || index >= cart.length) return;

    const item = cart[index];
    const newQty = item.quantity + delta;

    if (newQty <= 0) {
        removeFromCart(index);
        return;
    }

    if (newQty > item.stock) {
        showToast('Đã đạt số lượng tối đa trong kho', 'warning');
        return;
    }

    item.quantity = newQty;
    renderCart();
}

function calculateTotal() {
    return cart.reduce(function (sum, item) {
        return sum + (item.price * item.quantity);
    }, 0);
}

// --- Render Cart (ONLY updates #cart-items and #cart-total) ---
function renderCart() {
    const itemsContainer = document.getElementById('cart-items');
    const totalContainer = document.getElementById('cart-total');

    if (!itemsContainer) return;

    if (cart.length === 0) {
        itemsContainer.innerHTML = `
            <div class="empty-state" style="padding: 2rem 1rem;">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/>
                    <path d="M1 1h4l2.68 13.39a2 2 0 002 1.61h9.72a2 2 0 002-1.61L23 6H6"/>
                </svg>
                <p>Giỏ hàng trống</p>
            </div>
        `;
    } else {
        itemsContainer.innerHTML = cart.map(function (item, index) {
            return `
                <div class="cart-item" id="cart-item-${index}">
                    <div style="flex: 1; min-width: 0;">
                        <div style="font-size: 0.8125rem; font-weight: 500; color: #E2E8F0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                            ${escapeHtml(item.name)}
                        </div>
                        <div style="font-size: 0.75rem; color: #64748B;">
                            ${formatCurrency(item.price)} × ${item.quantity}
                        </div>
                    </div>
                    <div style="display: flex; align-items: center; gap: 0.375rem; flex-shrink: 0;">
                        <button class="qty-btn" onclick="updateQuantity(${index}, -1)" aria-label="Giảm">−</button>
                        <span style="width: 1.75rem; text-align: center; font-size: 0.875rem; color: #E2E8F0; font-weight: 600;">${item.quantity}</span>
                        <button class="qty-btn" onclick="updateQuantity(${index}, 1)" aria-label="Tăng">+</button>
                    </div>
                    <div style="width: 5.5rem; text-align: right; font-weight: 600; color: #3B82F6; font-size: 0.8125rem; flex-shrink: 0;">
                        ${formatCurrency(item.price * item.quantity)}
                    </div>
                    <button class="qty-btn" style="background: rgba(239,68,68,0.15); color: #EF4444;"
                            onclick="removeFromCart(${index})" aria-label="Xóa">×</button>
                </div>
            `;
        }).join('');
    }

    // Update total
    if (totalContainer) {
        const subtotal = calculateTotal();
        const vatRate = APP_CONFIG.VAT_RATE || 0;
        const vatAmount = subtotal * (vatRate / 100);
        const total = subtotal + vatAmount;

        let html = `
            <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.875rem; color: #94A3B8; margin-bottom: 0.25rem;">
                <span>Tạm tính:</span>
                <span>${formatCurrency(subtotal)}</span>
            </div>
        `;

        if (vatRate > 0) {
            html += `
                <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.875rem; color: #94A3B8; margin-bottom: 0.5rem;">
                    <span>VAT (${vatRate}%):</span>
                    <span>${formatCurrency(vatAmount)}</span>
                </div>
            `;
        }

        html += `
            <div style="display: flex; justify-content: space-between; align-items: center; font-size: 1.125rem;">
                <span style="color: #94A3B8; font-weight: 500;">Tổng cộng:</span>
                <span style="font-weight: 700; color: #E2E8F0;">${formatCurrency(total)}</span>
            </div>
        `;
        totalContainer.innerHTML = html;
    }

    // Enable/disable checkout buttons
    const cashBtn = document.getElementById('btn-checkout-cash');
    const bankBtn = document.getElementById('btn-checkout-bank');
    if (cashBtn) cashBtn.disabled = cart.length === 0;
    if (bankBtn) bankBtn.disabled = cart.length === 0;
}

// --- Checkout Flow ---
function showCheckoutModal(paymentMethod) {
    const overlay = document.getElementById('checkout-modal-overlay');
    const body = document.getElementById('checkout-modal-body');
    if (!overlay || !body) return;

    const subtotal = calculateTotal();
    const vatRate = APP_CONFIG.VAT_RATE || 0;
    const total = subtotal + (subtotal * (vatRate / 100));
    
    if (paymentMethod === 'bank_transfer') {
        const bankId = APP_CONFIG.VIETQR_BANK_ID || '970436';
        const accNo = APP_CONFIG.VIETQR_ACCOUNT_NO || '';
        const rawAccName = APP_CONFIG.VIETQR_ACCOUNT_NAME || '';
        const accName = encodeURIComponent(rawAccName);
        
        // Tạo lời nhắn chuyển khoản ngẫu nhiên (5 số)
        const randomCode = Math.floor(10000 + Math.random() * 90000);
        const transferMessage = `EViENT-ORDER-${randomCode}`;
        const addInfo = encodeURIComponent(transferMessage);

        // Standard VietQR URL format
        const qrUrl = `https://img.vietqr.io/image/${bankId}-${accNo}-compact.png?amount=${total}&accountName=${accName}&addInfo=${addInfo}`;

        body.innerHTML = `
            <h3 style="font-size: 1.25rem; font-weight: 700; color: #E2E8F0; margin-bottom: 1rem;">Quét Mã Thanh Toán</h3>
            <div style="background: white; padding: 1rem; border-radius: 0.5rem; display: inline-block; margin-bottom: 1rem;">
                <img src="${qrUrl}" alt="VietQR" style="max-width: 100%; height: auto; width: 250px;">
            </div>
            <div style="font-size: 1.125rem; color: #3B82F6; font-weight: 700; margin-bottom: 0.5rem;">
                Số tiền: ${formatCurrency(total)}
            </div>
            <div style="font-size: 0.875rem; color: #E2E8F0; margin-bottom: 0.25rem; font-weight: 600;">
                ${escapeHtml(rawAccName)}
            </div>
            <div style="font-size: 0.875rem; color: #94A3B8; margin-bottom: 1.5rem;">
                Nội dung: <span style="color: #10B981; font-weight: bold;">${transferMessage}</span>
            </div>
            <div style="display: flex; gap: 0.75rem; justify-content: center;">
                <button class="btn btn-ghost" onclick="closeCheckoutModal()">Hủy</button>
                <button class="btn btn-primary" onclick="completeCheckout('bank_transfer')" id="btn-confirm-transfer">
                    Xác nhận đã nhận tiền
                </button>
            </div>
        `;
    } else {
        window._cashFields = {
            'cash-amount-given': "0",
            'cash-change-actual': "0"
        };
        window._cashActiveField = 'cash-amount-given';
        body.innerHTML = `
            <h3 style="font-size: 1.25rem; font-weight: 700; color: #E2E8F0; margin-bottom: 1rem;">Thanh Toán Tiền Mặt</h3>
            <div style="margin-bottom: 0.5rem; text-align: left;">
                <label class="form-label">Tổng tiền (VNĐ)</label>
                <div style="font-size: 1.25rem; color: #3B82F6; font-weight: bold;">${formatCurrency(total)}</div>
            </div>
            <div style="margin-bottom: 0.5rem; text-align: left;">
                <label class="form-label">Khách đưa</label>
                <input type="text" id="cash-amount-given" class="form-input cash-numpad-field" style="font-size: 1.25rem; font-weight: bold; caret-color: transparent;" value="0" readonly inputmode="none" autocomplete="off">
            </div>
            <div style="margin-bottom: 0.5rem; text-align: left;">
                <label class="form-label">Tiền thừa</label>
                <div id="cash-change-expected" style="font-size: 1.25rem; color: #10B981; font-weight: bold;">0</div>
            </div>
            <div style="margin-bottom: 1rem; text-align: left;">
                <label class="form-label">Tiền thối thực tế</label>
                <input type="text" id="cash-change-actual" class="form-input cash-numpad-field" style="font-size: 1.25rem; font-weight: bold; caret-color: transparent;" value="0" readonly inputmode="none" autocomplete="off">
            </div>
            <div class="numpad-grid">
                <button class="numpad-btn" onclick="numpadPress('1')">1</button>
                <button class="numpad-btn" onclick="numpadPress('2')">2</button>
                <button class="numpad-btn" onclick="numpadPress('3')">3</button>
                <button class="numpad-btn" onclick="numpadPress('4')">4</button>
                <button class="numpad-btn" onclick="numpadPress('5')">5</button>
                <button class="numpad-btn" onclick="numpadPress('6')">6</button>
                <button class="numpad-btn" onclick="numpadPress('7')">7</button>
                <button class="numpad-btn" onclick="numpadPress('8')">8</button>
                <button class="numpad-btn" onclick="numpadPress('9')">9</button>
                <button class="numpad-btn" onclick="numpadPress('C')" style="color: #EF4444;">C</button>
                <button class="numpad-btn" onclick="numpadPress('0')">0</button>
                <button class="numpad-btn" onclick="numpadPress('000')">000</button>
            </div>
            <div style="display: flex; gap: 0.75rem; justify-content: center; margin-top: 1.5rem;">
                <button class="btn btn-ghost" onclick="closeCheckoutModal()">Hủy</button>
                <button class="btn btn-primary" onclick="submitCashCheckout(${total})" id="btn-confirm-cash">
                    Hoàn tất thanh toán
                </button>
            </div>
        `;

        // Focus tracking: highlight active field, switch numpad target
        document.querySelectorAll('.cash-numpad-field').forEach(function(el) {
            el.addEventListener('focus', function() {
                document.querySelectorAll('.cash-numpad-field').forEach(function(f) {
                    f.style.borderColor = '';
                });
                el.style.borderColor = '#3B82F6';
                window._cashActiveField = el.id;
            });
        });

        // Capture physical keyboard on the modal overlay
        overlay.addEventListener('keydown', cashKeydownHandler);
    }

    overlay.classList.add('active');

    // Focus the amount-given field
    setTimeout(function() {
        var input = document.getElementById('cash-amount-given');
        if (input) {
            input.focus();
            input.style.borderColor = '#3B82F6';
        }
    }, 50);
}

function cashKeydownHandler(e) {
    if (!window._cashFields) return;
    var key = e.key;
    if (key >= '0' && key <= '9') {
        e.preventDefault();
        numpadPress(key);
    } else if (key === 'Backspace') {
        e.preventDefault();
        numpadPress('BACK');
    } else if (key === 'Delete' || key === 'Escape') {
        e.preventDefault();
        numpadPress('C');
    } else if (key === 'Tab') {
        e.preventDefault();
        var nextField = window._cashActiveField === 'cash-amount-given'
            ? 'cash-change-actual' : 'cash-amount-given';
        var nextEl = document.getElementById(nextField);
        if (nextEl) nextEl.focus();
    } else if (key === 'Enter') {
        e.preventDefault();
        var btn = document.getElementById('btn-confirm-cash');
        if (btn) btn.click();
    } else {
        e.preventDefault();
    }
}

function cashRefreshDisplay() {
    var givenRaw = window._cashFields['cash-amount-given'] || "0";
    var actualRaw = window._cashFields['cash-change-actual'] || "0";
    var givenVal = parseInt(givenRaw, 10);
    var actualVal = parseInt(actualRaw, 10);

    var givenInput = document.getElementById('cash-amount-given');
    if (givenInput) givenInput.value = formatCurrency(givenVal);

    var actualInput = document.getElementById('cash-change-actual');
    if (actualInput) actualInput.value = formatCurrency(actualVal);

    var subtotal = calculateTotal();
    var vatRate = APP_CONFIG.VAT_RATE || 0;
    var total = subtotal + (subtotal * (vatRate / 100));
    var expectedChange = givenVal - total;
    if (expectedChange < 0) expectedChange = 0;

    var changeLabel = document.getElementById('cash-change-expected');
    if (changeLabel) changeLabel.innerText = formatCurrency(expectedChange);

    // Auto-sync actual change when user is editing given amount
    if (window._cashActiveField === 'cash-amount-given') {
        window._cashFields['cash-change-actual'] = String(Math.round(expectedChange));
        if (actualInput) actualInput.value = formatCurrency(expectedChange);
    }
}

window.numpadPress = function(key) {
    var fieldId = window._cashActiveField || 'cash-amount-given';
    var raw = window._cashFields[fieldId] || "0";
    if (key === 'C') {
        raw = "0";
    } else if (key === 'BACK') {
        raw = raw.slice(0, -1);
        if (!raw) raw = "0";
    } else {
        if (raw === "0") {
            raw = key;
        } else {
            raw += key;
        }
    }
    window._cashFields[fieldId] = raw;
    cashRefreshDisplay();
};

window.submitCashCheckout = function(total) {
    var givenVal = parseInt(window._cashFields['cash-amount-given'] || "0", 10);
    if (givenVal < total) {
        showToast('Khách đưa không đủ tiền!', 'error');
        return;
    }
    var actualChange = parseInt(window._cashFields['cash-change-actual'] || "0", 10);
    var expectedChange = givenVal - total;
    completeCheckout('cash', givenVal, expectedChange, actualChange);
};


function closeCheckoutModal() {
    var overlay = document.getElementById('checkout-modal-overlay');
    if (overlay) {
        overlay.removeEventListener('keydown', cashKeydownHandler);
        overlay.classList.remove('active');
    }
    window._cashFields = null;
}

function downloadInvoice(orderId) {
    const token = auth.getToken();
    const url = `${APP_CONFIG.API_BASE_URL}/invoices/${orderId}/png?token=${token}`;
    
    let modal = document.getElementById('invoice-modal-overlay');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'invoice-modal-overlay';
        modal.className = 'modal-overlay';
        modal.innerHTML = `
            <div class="modal-content" style="max-width: 500px; padding: 1.5rem;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
                    <h3 style="font-size: 1.25rem; font-weight: 700; color: #E2E8F0;">Hoá đơn #${orderId}</h3>
                    <button class="btn btn-ghost" style="padding: 0.5rem;" onclick="document.getElementById('invoice-modal-overlay').classList.remove('active')">
                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
                    </button>
                </div>
                <div style="background: white; padding: 1rem; border-radius: 0.5rem; max-height: 60vh; overflow-y: auto;">
                    <img id="invoice-image" src="" alt="Invoice" style="max-width: 100%; display: block; margin: 0 auto;">
                </div>
                <div style="margin-top: 1.5rem; display: flex; gap: 1rem; justify-content: center;">
                    <button class="btn btn-primary" onclick="printInvoiceImage()">
                        <svg class="w-4 h-4 mr-2 inline-block -mt-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z"></path></svg>
                        In Hoá Đơn
                    </button>
                    <button class="btn btn-ghost" onclick="document.getElementById('invoice-modal-overlay').classList.remove('active')">Đóng</button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
    } else {
        const title = modal.querySelector('h3');
        if (title) title.textContent = `Hoá đơn #${orderId}`;
    }
    
    document.getElementById('invoice-image').src = url;
    modal.classList.add('active');
}

function printInvoiceImage() {
    const img = document.getElementById('invoice-image');
    if (!img || !img.src) return;
    
    const iframe = document.createElement('iframe');
    iframe.style.display = 'none';
    document.body.appendChild(iframe);
    
    iframe.contentWindow.document.open();
    iframe.contentWindow.document.write(`
        <html>
            <head><title>Print</title></head>
            <body style="margin:0; padding:0; text-align:center;">
                <img src="${img.src}" style="max-width:100%;" onload="window.print(); setTimeout(() => window.parent.document.body.removeChild(window.frameElement), 500);" />
            </body>
        </html>
    `);
    iframe.contentWindow.document.close();
}

async function completeCheckout(paymentMethod, amountGiven, expectedChange, actualChange) {
    const confirmBtn = document.getElementById('btn-confirm-transfer');
    if (confirmBtn) confirmBtn.disabled = true;
    const confirmCashBtn = document.getElementById('btn-confirm-cash');
    if (confirmCashBtn) confirmCashBtn.disabled = true;

    try {
        const orderPayload = {
            items: cart.map(function (item) {
                return {
                    product_id: item.id,
                    product_name: item.name,
                    price: item.price,
                    quantity: item.quantity
                };
            }),
            payment_method: paymentMethod
        };
        
        if (paymentMethod === 'cash' && amountGiven !== undefined) {
            orderPayload.amount_given = amountGiven;
            orderPayload.expected_change = expectedChange;
            orderPayload.actual_change = actualChange;
        }

        const result = await api.post('/orders', orderPayload);
        const orderId = result.id || result.order_id;
        
        showToast('Đơn hàng #' + orderId + ' tạo thành công!', 'success');

        // Clear cart
        cart = [];
        renderCart();

        // Reload products to update stock
        await loadProducts(currentPage, searchQuery);

        // Open cash drawer for cash payments
        if (paymentMethod === 'cash') {
            try {
                await triggerCashDrawer();
            } catch (drawerErr) {
                console.warn('Cash drawer error:', drawerErr);
            }
        }

        // Show Success state in Modal
        const body = document.getElementById('checkout-modal-body');
        if (body) {
            body.innerHTML = `
                <div style="padding: 1.5rem 0;">
                    <div style="color: #10B981; margin-bottom: 1rem;">
                        <svg class="w-16 h-16 mx-auto" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
                            <path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                    </div>
                    <h3 style="font-size: 1.25rem; font-weight: 700; color: #E2E8F0; margin-bottom: 0.5rem;">Thanh toán thành công!</h3>
                    <p style="color: #94A3B8; margin-bottom: 1.5rem;">Đơn hàng #${orderId}</p>
                    <div style="display: flex; gap: 0.75rem; justify-content: center;">
                        <button class="btn btn-ghost" onclick="closeCheckoutModal()">Đóng</button>
                        <button class="btn btn-success" onclick="downloadInvoice('${orderId}')">
                            <svg class="w-4 h-4 inline-block mr-1 -mt-1" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                                <path stroke-linecap="round" stroke-linejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
                            </svg>
                            In hoá đơn
                        </button>
                    </div>
                </div>
            `;
        }

    } catch (err) {
        showToast('Lỗi tạo đơn hàng: ' + err.message, 'error');
        closeCheckoutModal();
    }
}

async function checkout(paymentMethod) {
    if (cart.length === 0) {
        showToast('Giỏ hàng trống', 'warning');
        return;
    }

    if (paymentMethod === 'cash') {
        const subtotal = calculateTotal();
        const vatRate = APP_CONFIG.VAT_RATE || 0;
        const total = subtotal + (subtotal * (vatRate / 100));
        if (!confirm(`Xác nhận thanh toán ${formatCurrency(total)} bằng tiền mặt?`)) return;
    }
    
    showCheckoutModal(paymentMethod);
}

// --- Barcode Search ---
async function searchByBarcode(barcode) {
    if (!barcode) return;

    try {
        const product = await api.get(`/products/barcode/${encodeURIComponent(barcode)}`);
        if (product && product.id) {
            // Temporarily add to products array if not already there
            if (!products.find(function (p) { return p.id === product.id; })) {
                products.push(product);
            }
            addToCart(product.id);
            showToast(`Quét: ${product.name}`, 'success');
        } else {
            showToast(`Không tìm thấy sản phẩm: ${barcode}`, 'warning');
        }
    } catch (err) {
        showToast(`Không tìm thấy barcode: ${barcode}`, 'warning');
    }
}

// --- Escape HTML utility ---
function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// --- Setup Event Listeners ---
function setupEventListeners() {
    // Search input with debounce
    const searchInput = document.getElementById('search-input');
    if (searchInput) {
        searchInput.addEventListener('input', function (e) {
            const query = e.target.value.trim();
            if (searchDebounceTimer) {
                clearTimeout(searchDebounceTimer);
            }
            searchDebounceTimer = setTimeout(function () {
                loadProducts(1, query);
            }, 300);
        });
    }

    // Checkout buttons
    const cashBtn = document.getElementById('btn-checkout-cash');
    if (cashBtn) {
        cashBtn.addEventListener('click', function () {
            checkout('cash');
        });
    }

    const bankBtn = document.getElementById('btn-checkout-bank');
    if (bankBtn) {
        bankBtn.addEventListener('click', function () {
            checkout('bank_transfer');
        });
    }

    // Cash drawer button
    const drawerBtn = document.getElementById('btn-cash-drawer');
    if (drawerBtn) {
        drawerBtn.addEventListener('click', function () {
            triggerCashDrawer();
        });
    }

    // End Shift button
    const endShiftBtn = document.getElementById('btn-end-shift');
    if (endShiftBtn) {
        endShiftBtn.addEventListener('click', async function () {
            if (confirm('Bạn có chắc muốn kết thúc ca làm và đăng xuất?')) {
                try {
                    await api.post('/auth/shift/end');
                    showToast('Đã lưu log ca làm. Đang đăng xuất...', 'success');
                    setTimeout(() => {
                        auth.logout();
                    }, 1000);
                } catch (err) {
                    showToast('Lỗi khi kết thúc ca: ' + err.message, 'error');
                }
            }
        });
    }
}

// --- Initialize POS ---
function initPOS() {
    setupEventListeners();
    loadProducts();
    renderCart();
    initBarcodeScanner(searchByBarcode);

    // Display user info
    const user = auth.getUser();
    const userNameEl = document.getElementById('user-display-name');
    if (userNameEl && user) {
        userNameEl.textContent = user.full_name || user.username || 'Nhân viên';
    }

    // Hide admin button for employees
    const adminLink = document.getElementById('link-admin');
    if (adminLink && user) {
        if (user.role === 'employee') {
            adminLink.style.display = 'none';
        }
    }
}
