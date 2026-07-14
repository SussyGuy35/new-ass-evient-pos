/**
 * EViENT POS - Admin Panel Logic
 * Tab system, CRUD for products/users, order browsing, system logs.
 */

// --- State ---
let activeTab = 'products';
let adminProductsPage = 1;
let adminProductsTotalPages = 1;
let adminOrdersPage = 1;
let adminOrdersTotalPages = 1;
let adminLogsPage = 1;
let adminLogsTotalPages = 1;
let editingProductId = null;
let editingUserId = null;

// --- Tab System ---
function switchTab(tabName) {
    activeTab = tabName;

    // Update tab buttons
    document.querySelectorAll('.tab-btn').forEach(function (btn) {
        btn.classList.toggle('active', btn.dataset.tab === tabName);
    });

    // Update tab panels
    document.querySelectorAll('.tab-panel').forEach(function (panel) {
        panel.style.display = panel.id === 'panel-' + tabName ? 'block' : 'none';
    });

    // Load data for the active tab
    switch (tabName) {
        case 'products':
            loadAdminProducts();
            break;
        case 'users':
            loadUsers();
            break;
        case 'orders':
            loadOrders();
            break;
        case 'logs':
            loadLogs();
            break;
    }
}

// =====================
// TAB: PRODUCTS
// =====================
async function loadAdminProducts(page = 1) {
    adminProductsPage = page;
    const container = document.getElementById('admin-products-table');
    if (!container) return;

    container.innerHTML = '<div style="text-align: center; padding: 2rem;"><div class="spinner" style="margin: 0 auto;"></div></div>';

    try {
        const data = await api.get(`/products?page=${page}&per_page=${APP_CONFIG.ITEMS_PER_PAGE}`);
        const items = data.items || data.products || data || [];
        adminProductsTotalPages = data.total_pages || data.totalPages || 1;

        if (items.length === 0) {
            container.innerHTML = '<div class="empty-state"><p>Chưa có sản phẩm nào</p></div>';
            return;
        }

        let html = `
            <table class="admin-table">
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Tên sản phẩm</th>
                        <th>Barcode</th>
                        <th>Giá</th>
                        <th>Tồn kho</th>
                        <th style="text-align: right;">Thao tác</th>
                    </tr>
                </thead>
                <tbody>
        `;

        items.forEach(function (p) {
            const stockClass = p.stock <= 0 ? 'stock-out' : p.stock <= 10 ? 'stock-low' : 'stock-ok';
            html += `
                <tr>
                    <td style="color: #64748B;">#${p.id}</td>
                    <td style="font-weight: 500; color: #E2E8F0;">${escapeHtml(p.name)}</td>
                    <td style="font-family: monospace; color: #64748B;">${escapeHtml(p.barcode || '—')}</td>
                    <td style="color: #3B82F6; font-weight: 500;">${formatCurrency(p.price)}</td>
                    <td class="${stockClass}">${p.stock}</td>
                    <td style="text-align: right;">
                        <button class="btn btn-ghost" style="min-width: auto; padding: 0.25rem 0.5rem;" onclick="showProductModal('${p.id}')">Sửa</button>
                        <button class="btn btn-ghost" style="min-width: auto; padding: 0.25rem 0.5rem; color: #EF4444;" onclick="deleteProduct('${p.id}')">Xóa</button>
                    </td>
                </tr>
            `;
        });

        html += '</tbody></table>';
        container.innerHTML = html;

        renderAdminPagination('admin-products-pagination', adminProductsPage, adminProductsTotalPages, 'loadAdminProducts');
    } catch (err) {
        container.innerHTML = `<div class="empty-state"><p>Lỗi: ${err.message}</p></div>`;
        showToast('Lỗi tải sản phẩm: ' + err.message, 'error');
    }
}

function showProductModal(productId) {
    editingProductId = productId || null;
    const modal = document.getElementById('modal-overlay');
    const title = document.getElementById('modal-title');
    const body = document.getElementById('modal-body');
    if (!modal || !body) return;

    title.textContent = productId ? 'Sửa Sản Phẩm' : 'Thêm Sản Phẩm';

    // If editing, find the product data (attempt from a quick API call)
    if (productId) {
        body.innerHTML = '<div style="text-align: center; padding: 1rem;"><div class="spinner" style="margin: 0 auto;"></div></div>';
        modal.classList.add('active');

        api.get(`/products/${productId}`).then(function (product) {
            renderProductForm(product);
        }).catch(function (err) {
            body.innerHTML = `<p style="color: #EF4444;">Lỗi: ${err.message}</p>`;
        });
    } else {
        renderProductForm(null);
        modal.classList.add('active');
    }
}

function renderProductForm(product) {
    const body = document.getElementById('modal-body');
    if (!body) return;

    body.innerHTML = `
        <form id="form-product" onsubmit="event.preventDefault(); saveProduct();">
            <div style="margin-bottom: 1rem;">
                <label class="form-label" for="prod-name">Tên sản phẩm *</label>
                <input class="form-input" id="prod-name" required value="${product ? escapeHtml(product.name) : ''}" placeholder="Nhập tên sản phẩm">
            </div>
            <div style="margin-bottom: 1rem;">
                <label class="form-label" for="prod-barcode">Barcode</label>
                <input class="form-input" id="prod-barcode" value="${product ? escapeHtml(product.barcode || '') : ''}" placeholder="Mã barcode">
            </div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: 1rem;">
                <div>
                    <label class="form-label" for="prod-price">Giá (VNĐ) *</label>
                    <input class="form-input" id="prod-price" type="number" min="0" required value="${product ? product.price : ''}" placeholder="0">
                </div>
                <div>
                    <label class="form-label" for="prod-stock">Tồn kho *</label>
                    <input class="form-input" id="prod-stock" type="number" min="0" required value="${product ? product.stock : ''}" placeholder="0">
                </div>
            </div>
            <div style="display: flex; gap: 0.75rem; justify-content: flex-end; margin-top: 1.5rem;">
                <button type="button" class="btn btn-ghost" onclick="closeModal()">Hủy</button>
                <button type="submit" class="btn btn-primary" id="btn-save-product">
                    ${editingProductId ? 'Cập nhật' : 'Thêm mới'}
                </button>
            </div>
        </form>
    `;
}

async function saveProduct() {
    const name = document.getElementById('prod-name').value.trim();
    const barcode = document.getElementById('prod-barcode').value.trim();
    const price = parseFloat(document.getElementById('prod-price').value);
    const stock = parseInt(document.getElementById('prod-stock').value, 10);

    if (!name) {
        showToast('Vui lòng nhập tên sản phẩm', 'warning');
        return;
    }

    const formData = { name, barcode, price, stock };
    const saveBtn = document.getElementById('btn-save-product');
    if (saveBtn) saveBtn.disabled = true;

    try {
        if (editingProductId) {
            await api.put(`/products/${editingProductId}`, formData);
            showToast('Cập nhật sản phẩm thành công', 'success');
        } else {
            await api.post('/products', formData);
            showToast('Thêm sản phẩm thành công', 'success');
        }
        closeModal();
        loadAdminProducts(adminProductsPage);
    } catch (err) {
        showToast('Lỗi: ' + err.message, 'error');
    } finally {
        if (saveBtn) saveBtn.disabled = false;
    }
}

async function deleteProduct(id) {
    if (!confirm('Bạn có chắc chắn muốn xóa sản phẩm này?')) return;

    try {
        await api.del(`/products/${id}`);
        showToast('Đã xóa sản phẩm', 'success');
        loadAdminProducts(adminProductsPage);
    } catch (err) {
        showToast('Lỗi xóa: ' + err.message, 'error');
    }
}

// =====================
// TAB: USERS
// =====================
async function loadUsers() {
    const container = document.getElementById('admin-users-table');
    if (!container) return;

    container.innerHTML = '<div style="text-align: center; padding: 2rem;"><div class="spinner" style="margin: 0 auto;"></div></div>';

    try {
        const data = await api.get('/auth/users');
        const users = data.items || data.users || data || [];

        if (users.length === 0) {
            container.innerHTML = '<div class="empty-state"><p>Chưa có nhân viên nào</p></div>';
            return;
        }

        let html = `
            <table class="admin-table">
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Username</th>
                        <th>Họ tên</th>
                        <th>Vai trò</th>
                        <th>Trạng thái</th>
                        <th style="text-align: right;">Thao tác</th>
                    </tr>
                </thead>
                <tbody>
        `;

        users.forEach(function (u) {
            const roleBadge = u.role === 'admin' ? 'badge-error'
                : u.role === 'manager' ? 'badge-warning'
                : 'badge-info';
            const roleLabel = u.role === 'admin' ? 'Admin'
                : u.role === 'manager' ? 'Quản lý'
                : 'Nhân viên';
            const statusBadge = u.is_active !== false ? 'badge-success' : 'badge-error';
            const statusLabel = u.is_active !== false ? 'Hoạt động' : 'Khóa';

            html += `
                <tr>
                    <td style="color: #64748B;">#${u.id}</td>
                    <td style="font-weight: 500; color: #E2E8F0;">${escapeHtml(u.username)}</td>
                    <td>${escapeHtml(u.full_name || '—')}</td>
                    <td><span class="badge ${roleBadge}">${roleLabel}</span></td>
                    <td><span class="badge ${statusBadge}">${statusLabel}</span></td>
                    <td style="text-align: right;">
                        <button class="btn btn-ghost" style="min-width: auto; padding: 0.25rem 0.5rem;" onclick="showUserModal('${u.id}')">Sửa</button>
                        <button class="btn btn-ghost" style="min-width: auto; padding: 0.25rem 0.5rem; color: #EF4444;" onclick="deleteUser('${u.id}')">Xóa</button>
                    </td>
                </tr>
            `;
        });

        html += '</tbody></table>';
        container.innerHTML = html;
    } catch (err) {
        container.innerHTML = `<div class="empty-state"><p>Lỗi: ${err.message}</p></div>`;
        showToast('Lỗi tải nhân viên: ' + err.message, 'error');
    }
}

function showUserModal(userId) {
    editingUserId = userId || null;
    const modal = document.getElementById('modal-overlay');
    const title = document.getElementById('modal-title');
    const body = document.getElementById('modal-body');
    if (!modal || !body) return;

    title.textContent = userId ? 'Sửa Nhân Viên' : 'Thêm Nhân Viên';

    if (userId) {
        body.innerHTML = '<div style="text-align: center; padding: 1rem;"><div class="spinner" style="margin: 0 auto;"></div></div>';
        modal.classList.add('active');

        api.get(`/auth/users/${userId}`).then(function (user) {
            renderUserForm(user);
        }).catch(function (err) {
            body.innerHTML = `<p style="color: #EF4444;">Lỗi: ${err.message}</p>`;
        });
    } else {
        renderUserForm(null);
        modal.classList.add('active');
    }
}

function renderUserForm(user) {
    const body = document.getElementById('modal-body');
    if (!body) return;

    body.innerHTML = `
        <form id="form-user" onsubmit="event.preventDefault(); saveUser();">
            <div style="margin-bottom: 1rem;">
                <label class="form-label" for="user-username">Username *</label>
                <input class="form-input" id="user-username" required value="${user ? escapeHtml(user.username) : ''}" placeholder="Nhập username"
                       ${user ? 'readonly style="opacity: 0.6; cursor: not-allowed; background: #0F172A; border: 1px solid #334155; width: 100%; padding: 0.625rem 0.875rem; border-radius: 0.5rem; color: #E2E8F0; font-size: 0.875rem; min-height: 44px;"' : ''}>
            </div>
            <div style="margin-bottom: 1rem;">
                <label class="form-label" for="user-fullname">Họ tên *</label>
                <input class="form-input" id="user-fullname" required value="${user ? escapeHtml(user.full_name || '') : ''}" placeholder="Nhập họ tên">
            </div>
            <div style="margin-bottom: 1rem;">
                <label class="form-label" for="user-password">${user ? 'Mật khẩu mới (để trống nếu không đổi)' : 'Mật khẩu *'}</label>
                <input class="form-input" id="user-password" type="password" ${user ? '' : 'required'} placeholder="Nhập mật khẩu">
            </div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: 1rem;">
                <div>
                    <label class="form-label" for="user-role">Vai trò</label>
                    <select class="form-input form-select" id="user-role">
                        <option value="employee" ${user && user.role === 'employee' ? 'selected' : ''}>Nhân viên</option>
                        <option value="manager" ${user && user.role === 'manager' ? 'selected' : ''}>Quản lý</option>
                        <option value="admin" ${user && user.role === 'admin' ? 'selected' : ''}>Admin</option>
                    </select>
                </div>
                <div>
                    <label class="form-label" for="user-active">Trạng thái</label>
                    <select class="form-input form-select" id="user-active">
                        <option value="true" ${!user || user.is_active !== false ? 'selected' : ''}>Hoạt động</option>
                        <option value="false" ${user && user.is_active === false ? 'selected' : ''}>Khóa</option>
                    </select>
                </div>
            </div>
            <div style="display: flex; gap: 0.75rem; justify-content: flex-end; margin-top: 1.5rem;">
                <button type="button" class="btn btn-ghost" onclick="closeModal()">Hủy</button>
                <button type="submit" class="btn btn-primary" id="btn-save-user">
                    ${editingUserId ? 'Cập nhật' : 'Thêm mới'}
                </button>
            </div>
        </form>
    `;
}

async function saveUser() {
    const username = document.getElementById('user-username').value.trim();
    const full_name = document.getElementById('user-fullname').value.trim();
    const password = document.getElementById('user-password').value;
    const role = document.getElementById('user-role').value;
    const is_active = document.getElementById('user-active').value === 'true';

    if (!username || !full_name) {
        showToast('Vui lòng điền đầy đủ thông tin', 'warning');
        return;
    }

    const formData = { username, full_name, role, is_active };
    if (password) {
        formData.password = password;
    }

    const saveBtn = document.getElementById('btn-save-user');
    if (saveBtn) saveBtn.disabled = true;

    try {
        if (editingUserId) {
            await api.put(`/auth/users/${editingUserId}`, formData);
            showToast('Cập nhật nhân viên thành công', 'success');
        } else {
            if (!password) {
                showToast('Vui lòng nhập mật khẩu', 'warning');
                if (saveBtn) saveBtn.disabled = false;
                return;
            }
            await api.post('/auth/users', formData);
            showToast('Thêm nhân viên thành công', 'success');
        }
        closeModal();
        loadUsers();
    } catch (err) {
        showToast('Lỗi: ' + err.message, 'error');
    } finally {
        if (saveBtn) saveBtn.disabled = false;
    }
}

async function deleteUser(id) {
    if (!confirm('Bạn có chắc chắn muốn xóa nhân viên này?')) return;

    try {
        await api.del(`/auth/users/${id}`);
        showToast('Đã xóa nhân viên', 'success');
        loadUsers();
    } catch (err) {
        showToast('Lỗi xóa: ' + err.message, 'error');
    }
}

// =====================
// TAB: ORDERS
// =====================
async function loadOrders(page = 1) {
    adminOrdersPage = page;
    const container = document.getElementById('admin-orders-table');
    if (!container) return;

    container.innerHTML = '<div style="text-align: center; padding: 2rem;"><div class="spinner" style="margin: 0 auto;"></div></div>';

    try {
        const data = await api.get(`/orders?page=${page}&per_page=${APP_CONFIG.ITEMS_PER_PAGE}`);
        const orders = data.items || data.orders || data || [];
        adminOrdersTotalPages = data.total_pages || data.totalPages || 1;

        if (orders.length === 0) {
            container.innerHTML = '<div class="empty-state"><p>Chưa có đơn hàng nào</p></div>';
            return;
        }

        let html = `
            <table class="admin-table">
                <thead>
                    <tr>
                        <th>Mã ĐH</th>
                        <th>Nhân viên</th>
                        <th>Tổng tiền</th>
                        <th>Thanh toán</th>
                        <th>Thời gian</th>
                        <th style="text-align: right;">Hóa đơn</th>
                    </tr>
                </thead>
                <tbody>
        `;

        orders.forEach(function (o) {
            const paymentLabel = o.payment_method === 'cash' ? 'Tiền mặt' : 'Chuyển khoản';
            const paymentBadge = o.payment_method === 'cash' ? 'badge-success' : 'badge-info';
            const createdAt = o.created_at ? new Date(o.created_at).toLocaleString('vi-VN') : '—';

            html += `
                <tr>
                    <td style="font-weight: 500; color: #E2E8F0;">#${o.id || o.order_id}</td>
                    <td>${escapeHtml(o.cashier_name || o.user?.username || '—')}</td>
                    <td style="color: #3B82F6; font-weight: 500;">${formatCurrency(o.total || o.total_amount || 0)}</td>
                    <td><span class="badge ${paymentBadge}">${paymentLabel}</span></td>
                    <td style="color: #64748B; font-size: 0.8125rem;">${createdAt}</td>
                    <td style="text-align: right;">
                        <button class="btn btn-ghost" style="min-width: auto; padding: 0.25rem 0.5rem;"
                                onclick="downloadInvoice('${o.id || o.order_id}')">
                            📄 Xem HĐ
                        </button>
                    </td>
                </tr>
            `;
        });

        html += '</tbody></table>';
        container.innerHTML = html;

        renderAdminPagination('admin-orders-pagination', adminOrdersPage, adminOrdersTotalPages, 'loadOrders');
    } catch (err) {
        container.innerHTML = `<div class="empty-state"><p>Lỗi: ${err.message}</p></div>`;
        showToast('Lỗi tải đơn hàng: ' + err.message, 'error');
    }
}



// =====================
// TAB: LOGS
// =====================
async function loadLogs(page = 1) {
    adminLogsPage = page;
    const container = document.getElementById('admin-logs-table');
    if (!container) return;

    container.innerHTML = '<div style="text-align: center; padding: 2rem;"><div class="spinner" style="margin: 0 auto;"></div></div>';

    try {
        const data = await api.get(`/logs?page=${page}&per_page=${APP_CONFIG.ITEMS_PER_PAGE}`);
        const logs = data.items || data.logs || data || [];
        adminLogsTotalPages = data.total_pages || data.totalPages || 1;

        if (logs.length === 0) {
            container.innerHTML = '<div class="empty-state"><p>Chưa có log nào</p></div>';
            return;
        }

        let html = `
            <table class="admin-table">
                <thead>
                    <tr>
                        <th>Thời gian</th>
                        <th>Người dùng</th>
                        <th>Hành động</th>
                        <th>Chi tiết</th>
                    </tr>
                </thead>
                <tbody>
        `;

        logs.forEach(function (log) {
            const timestamp = log.created_at ? new Date(log.created_at).toLocaleString('vi-VN') : '—';
            const levelBadge = log.level === 'error' ? 'badge-error'
                : log.level === 'warning' ? 'badge-warning'
                : 'badge-info';

            html += `
                <tr>
                    <td style="color: #64748B; font-size: 0.8125rem; white-space: nowrap;">${timestamp}</td>
                    <td style="font-weight: 500; color: #E2E8F0;">${escapeHtml(log.username || log.user || '—')}</td>
                    <td><span class="badge ${levelBadge}">${escapeHtml(log.action || log.event || '—')}</span></td>
                    <td style="color: #94A3B8; font-size: 0.8125rem; max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                        ${escapeHtml(log.detail || log.details || log.message || '—')}
                    </td>
                </tr>
            `;
        });

        html += '</tbody></table>';
        container.innerHTML = html;

        renderAdminPagination('admin-logs-pagination', adminLogsPage, adminLogsTotalPages, 'loadLogs');
    } catch (err) {
        container.innerHTML = `<div class="empty-state"><p>Lỗi: ${err.message}</p></div>`;
        showToast('Lỗi tải logs: ' + err.message, 'error');
    }
}

// =====================
// SHARED UTILITIES
// =====================
function renderAdminPagination(containerId, currentPage, totalPages, loadFunction) {
    const container = document.getElementById(containerId);
    if (!container) return;

    if (totalPages <= 1) {
        container.innerHTML = '';
        return;
    }

    container.innerHTML = `
        <div class="pagination">
            <button class="page-btn" onclick="${loadFunction}(${currentPage - 1})"
                    ${currentPage <= 1 ? 'disabled' : ''}>‹ Trước</button>
            <span style="color: #94A3B8; font-size: 0.8125rem; padding: 0 0.5rem;">
                Trang ${currentPage} / ${totalPages}
            </span>
            <button class="page-btn" onclick="${loadFunction}(${currentPage + 1})"
                    ${currentPage >= totalPages ? 'disabled' : ''}>Sau ›</button>
        </div>
    `;
}

function closeModal() {
    const modal = document.getElementById('modal-overlay');
    if (modal) {
        modal.classList.remove('active');
    }
    editingProductId = null;
    editingUserId = null;
}

// --- Initialize Admin ---
function initAdmin() {
    // Display user info
    const user = auth.getUser();
    const userNameEl = document.getElementById('user-display-name');
    if (userNameEl && user) {
        userNameEl.textContent = user.full_name || user.username || 'Nhân viên';
    }

    // Tab click handlers
    document.querySelectorAll('.tab-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            switchTab(btn.dataset.tab);
        });
    });

    // Close modal on overlay click
    const modal = document.getElementById('modal-overlay');
    if (modal) {
        modal.addEventListener('click', function (e) {
            if (e.target === modal) {
                closeModal();
            }
        });
    }

    // Close modal on Escape key
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            closeModal();
        }
    });

    // Add product button
    const addProductBtn = document.getElementById('btn-add-product');
    if (addProductBtn) {
        addProductBtn.addEventListener('click', function () {
            showProductModal(null);
        });
    }

    // Add user button
    const addUserBtn = document.getElementById('btn-add-user');
    if (addUserBtn) {
        addUserBtn.addEventListener('click', function () {
            showUserModal(null);
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

    // Hide users tab if not admin
    if (user && user.role !== 'admin') {
        const usersTab = document.querySelector('[data-tab="users"]');
        if (usersTab) usersTab.style.display = 'none';
    }

    // Load initial tab
    switchTab('products');
}
