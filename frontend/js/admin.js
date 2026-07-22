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
let adminPreordersPage = 1;
let adminPreordersTotalPages = 1;
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
        case 'dashboard':
            loadDashboard();
            break;
        case 'products':
            loadAdminProducts();
            break;
        case 'users':
            loadUsers();
            break;
        case 'orders':
            loadOrders();
            break;
        case 'preorders':
            loadPreorders();
            break;
        case 'logs':
            loadLogs();
            break;
    }
}

// =====================
// TAB: DASHBOARD
// =====================
async function loadDashboard() {
    const container = document.getElementById('dashboard-content');
    if (!container) return;

    container.innerHTML = '<div style="text-align: center; padding: 2rem;"><div class="spinner" style="margin: 0 auto;"></div></div>';

    try {
        const data = await api.get('/reports/dashboard');
        
        let html = `
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin-bottom: 2rem;">
                <div class="bg-slate-700 p-4 rounded-xl border border-slate-600">
                    <div class="text-sm text-slate-400 mb-1">Doanh thu hôm nay</div>
                    <div class="text-2xl font-bold text-blue-400">${formatCurrency(data.today.revenue)}</div>
                    <div class="text-xs text-slate-500 mt-2">${data.today.orders} đơn hàng</div>
                </div>
                <div class="bg-slate-700 p-4 rounded-xl border border-slate-600">
                    <div class="text-sm text-slate-400 mb-1">Tổng doanh thu</div>
                    <div class="text-2xl font-bold text-emerald-400">${formatCurrency(data.all_time.revenue)}</div>
                    <div class="text-xs text-slate-500 mt-2">${data.all_time.orders} đơn hàng</div>
                </div>
                <div class="bg-slate-700 p-4 rounded-xl border border-slate-600">
                    <div class="text-sm text-slate-400 mb-1">Tiền mặt</div>
                    <div class="text-xl font-bold text-white">${formatCurrency(data.all_time.cash_revenue)}</div>
                </div>
                <div class="bg-slate-700 p-4 rounded-xl border border-slate-600">
                    <div class="text-sm text-slate-400 mb-1">Chuyển khoản</div>
                    <div class="text-xl font-bold text-white">${formatCurrency(data.all_time.transfer_revenue)}</div>
                </div>
            </div>
            
            <h3 class="text-lg font-bold text-white mb-4">Top 5 Sản phẩm Bán chạy</h3>
            <table class="admin-table">
                <thead>
                    <tr>
                        <th>Sản phẩm</th>
                        <th style="text-align: right;">Đã bán</th>
                        <th style="text-align: right;">Doanh thu</th>
                    </tr>
                </thead>
                <tbody>
        `;
        
        if (data.top_products && data.top_products.length > 0) {
            data.top_products.forEach(p => {
                html += `
                    <tr>
                        <td style="font-weight: 500; color: #E2E8F0;">${escapeHtml(p.name)}</td>
                        <td style="text-align: right; color: #94A3B8;">${p.quantity}</td>
                        <td style="text-align: right; color: #3B82F6; font-weight: 500;">${formatCurrency(p.revenue)}</td>
                    </tr>
                `;
            });
        } else {
            html += `<tr><td colspan="3" style="text-align: center; color: #64748B;">Chưa có dữ liệu</td></tr>`;
        }
        
        html += `
                </tbody>
            </table>
        `;
        
        container.innerHTML = html;
    } catch (err) {
        container.innerHTML = `<div class="empty-state"><p>Lỗi tải báo cáo: ${err.message}</p></div>`;
        showToast('Lỗi tải báo cáo: ' + err.message, 'error');
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
            let createdTime = o.created_at;
            if (createdTime && !createdTime.endsWith('Z') && !createdTime.includes('+')) {
                createdTime += 'Z';
            }
            const createdAt = createdTime ? new Date(createdTime).toLocaleString('vi-VN') : '—';

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
            let timeValue = log.timestamp || log.created_at;
            if (timeValue && !timeValue.endsWith('Z') && !timeValue.includes('+')) {
                timeValue += 'Z';
            }
            const timestamp = timeValue ? new Date(timeValue).toLocaleString('vi-VN') : '—';
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
// TAB: PRE-ORDERS
// =====================
async function loadPreorders(page = 1) {
    adminPreordersPage = page;
    const container = document.getElementById('admin-preorders-table');
    if (!container) return;

    container.innerHTML = '<div style="text-align: center; padding: 2rem;"><div class="spinner" style="margin: 0 auto;"></div></div>';

    try {
        const statusFilter = document.getElementById('preorder-status-filter');
        const status = statusFilter ? statusFilter.value : '';
        let url = `/preorders?page=${page}&per_page=${APP_CONFIG.ITEMS_PER_PAGE}`;
        if (status) url += `&status=${status}`;

        const data = await api.get(url);
        const preorders = data.items || [];
        adminPreordersTotalPages = data.total_pages || 1;

        if (preorders.length === 0) {
            container.innerHTML = '<div class="empty-state"><p>Chưa có đơn đặt trước nào</p></div>';
            return;
        }

        const statusMap = {
            'pending': { label: 'Chờ nhận', badge: 'badge-warning' },
            'fulfilled': { label: 'Đã giao', badge: 'badge-success' },
            'cancelled': { label: 'Đã huỷ', badge: 'badge-error' },
        };

        let html = `
            <table class="admin-table">
                <thead>
                    <tr>
                        <th>Mã barcode</th>
                        <th>Khách hàng</th>
                        <th>Email</th>
                        <th>Tổng tiền</th>
                        <th>Trạng thái</th>
                        <th>Thời gian</th>
                        <th style="text-align: right;">Thao tác</th>
                    </tr>
                </thead>
                <tbody>
        `;

        preorders.forEach(function (po) {
            const st = statusMap[po.status] || { label: po.status, badge: 'badge-info' };
            let createdTime = po.created_at;
            if (createdTime && !createdTime.endsWith('Z') && !createdTime.includes('+')) {
                createdTime += 'Z';
            }
            const createdAt = createdTime ? new Date(createdTime).toLocaleString('vi-VN') : '—';

            html += `
                <tr>
                    <td style="font-family: monospace; font-weight: 500; color: #E2E8F0;">${escapeHtml(po.barcode_code)}</td>
                    <td style="font-weight: 500; color: #E2E8F0;">${escapeHtml(po.customer_name)}</td>
                    <td style="color: #94A3B8; font-size: 0.8125rem;">${escapeHtml(po.email)}</td>
                    <td style="color: #3B82F6; font-weight: 500;">${formatCurrency(po.total)}</td>
                    <td><span class="badge ${st.badge}">${st.label}</span></td>
                    <td style="color: #64748B; font-size: 0.8125rem;">${createdAt}</td>
                    <td style="text-align: right;">
                        ${po.status === 'pending' ? `<button class="btn btn-ghost" style="min-width: auto; padding: 0.25rem 0.5rem; color: #EF4444;" onclick="cancelPreorder('${po.id}')">Huỷ</button>` : ''}
                    </td>
                </tr>
            `;
        });

        html += '</tbody></table>';
        container.innerHTML = html;

        renderAdminPagination('admin-preorders-pagination', adminPreordersPage, adminPreordersTotalPages, 'loadPreorders');
    } catch (err) {
        container.innerHTML = `<div class="empty-state"><p>Lỗi: ${err.message}</p></div>`;
        showToast('Lỗi tải đơn đặt trước: ' + err.message, 'error');
    }
}

let manualPreorderItems = [];
let allProductsForPreorder = [];

async function showCreatePreorderModal() {
    manualPreorderItems = [];
    const modal = document.getElementById('modal-overlay');
    const title = document.getElementById('modal-title');
    const body = document.getElementById('modal-body');
    if (!modal || !body) return;

    title.textContent = 'Tạo Đơn Đặt Trước Thủ Công';
    body.innerHTML = `
        <div style="text-align: center; padding: 2rem;">
            <div class="spinner" style="margin: 0 auto;"></div>
            <p style="margin-top: 1rem; color: #94A3B8;">Đang tải danh sách sản phẩm...</p>
        </div>
    `;
    modal.classList.add('active');

    try {
        let allProducts = [];
        let page = 1;
        let totalPages = 1;
        
        while (page <= totalPages) {
            const res = await api.get(`/products?page=${page}&per_page=100`);
            allProducts = allProducts.concat(res.items || []);
            totalPages = res.total_pages || 1;
            page++;
        }
        
        allProductsForPreorder = allProducts;
        
        let productOptions = '<option value="">-- Chọn sản phẩm --</option>';
        allProductsForPreorder.forEach(p => {
            productOptions += `<option value="${p.id}">${escapeHtml(p.name)} - ${formatCurrency(p.price)}</option>`;
        });

        body.innerHTML = `
            <form id="form-preorder" onsubmit="event.preventDefault(); submitManualPreorder();">
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: 1rem;">
                    <div>
                        <label class="form-label" for="po-customer">Tên khách hàng *</label>
                        <input class="form-input" id="po-customer" required placeholder="Nguyễn Văn A">
                    </div>
                    <div>
                        <label class="form-label" for="po-email">Email (nhận mã vạch) *</label>
                        <input class="form-input" id="po-email" type="email" required placeholder="email@example.com">
                    </div>
                </div>
                
                <div style="background: #1E293B; padding: 1rem; border-radius: 0.5rem; margin-bottom: 1rem;">
                    <label class="form-label">Thêm sản phẩm vào đơn</label>
                    <div style="display: flex; gap: 0.5rem; margin-bottom: 0.5rem;">
                        <select class="form-input form-select" id="po-product-select" style="flex: 1;">
                            ${productOptions}
                        </select>
                        <input class="form-input" id="po-qty" type="number" min="1" value="1" style="width: 80px;" placeholder="SL">
                        <button type="button" class="btn btn-primary" onclick="addManualPreorderItem()">Thêm</button>
                    </div>
                    
                    <div style="max-height: 200px; overflow-y: auto; background: #0F172A; border-radius: 0.25rem;">
                        <table style="width: 100%; border-collapse: collapse; text-align: left;">
                            <thead>
                                <tr style="border-bottom: 1px solid #334155; color: #94A3B8; font-size: 0.8125rem;">
                                    <th style="padding: 0.5rem;">Sản phẩm</th>
                                    <th style="padding: 0.5rem;">SL</th>
                                    <th style="padding: 0.5rem; text-align: right;">Thao tác</th>
                                </tr>
                            </thead>
                            <tbody id="po-items-list">
                                <tr><td colspan="3" style="text-align: center; padding: 1rem; color: #64748B; font-size: 0.875rem;">Chưa có sản phẩm nào</td></tr>
                            </tbody>
                        </table>
                    </div>
                </div>

                <div style="display: flex; gap: 0.75rem; justify-content: flex-end; margin-top: 1.5rem;">
                    <button type="button" class="btn btn-ghost" onclick="closeModal()">Huỷ</button>
                    <button type="submit" class="btn btn-primary" id="btn-submit-preorder">Tạo Đơn</button>
                </div>
            </form>
        `;
    } catch (err) {
        body.innerHTML = `<p style="color: #EF4444;">Lỗi tải dữ liệu: ${err.message}</p>`;
    }
}

function addManualPreorderItem() {
    const select = document.getElementById('po-product-select');
    const qtyInput = document.getElementById('po-qty');
    const productId = select.value;
    const qty = parseInt(qtyInput.value, 10);
    
    if (!productId) {
        showToast('Vui lòng chọn sản phẩm', 'warning');
        return;
    }
    if (isNaN(qty) || qty < 1) {
        showToast('Số lượng không hợp lệ', 'warning');
        return;
    }
    
    const product = allProductsForPreorder.find(p => p.id === productId);
    if (!product) return;
    
    // Check if already in list
    const existing = manualPreorderItems.find(item => item.product_id === productId);
    if (existing) {
        existing.quantity += qty;
    } else {
        manualPreorderItems.push({
            product_id: productId,
            product_name: product.name,
            quantity: qty
        });
    }
    
    renderManualPreorderItems();
    // Reset qty
    qtyInput.value = '1';
}

function removeManualPreorderItem(productId) {
    manualPreorderItems = manualPreorderItems.filter(item => item.product_id !== productId);
    renderManualPreorderItems();
}

function renderManualPreorderItems() {
    const tbody = document.getElementById('po-items-list');
    if (!tbody) return;
    
    if (manualPreorderItems.length === 0) {
        tbody.innerHTML = '<tr><td colspan="3" style="text-align: center; padding: 1rem; color: #64748B; font-size: 0.875rem;">Chưa có sản phẩm nào</td></tr>';
        return;
    }
    
    tbody.innerHTML = manualPreorderItems.map(item => `
        <tr style="border-bottom: 1px solid #1E293B;">
            <td style="padding: 0.5rem; color: #E2E8F0; font-size: 0.875rem;">${escapeHtml(item.product_name)}</td>
            <td style="padding: 0.5rem; color: #3B82F6; font-weight: 500;">${item.quantity}</td>
            <td style="padding: 0.5rem; text-align: right;">
                <button type="button" class="btn btn-ghost" style="padding: 0.25rem 0.5rem; color: #EF4444;" onclick="removeManualPreorderItem('${item.product_id}')">Xoá</button>
            </td>
        </tr>
    `).join('');
}

async function submitManualPreorder() {
    if (manualPreorderItems.length === 0) {
        showToast('Vui lòng thêm ít nhất 1 sản phẩm vào đơn', 'warning');
        return;
    }
    
    const customerName = document.getElementById('po-customer').value.trim();
    const email = document.getElementById('po-email').value.trim();
    
    const submitBtn = document.getElementById('btn-submit-preorder');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Đang tạo...';
    
    try {
        const payload = {
            customer_name: customerName,
            email: email,
            items: manualPreorderItems.map(item => ({
                product_id: item.product_id,
                quantity: item.quantity
            }))
        };
        
        await api.post('/preorders', payload);
        
        showToast('Tạo đơn đặt trước thành công!', 'success');
        closeModal();
        loadPreorders(1);
    } catch (err) {
        showToast('Lỗi: ' + err.message, 'error');
        submitBtn.disabled = false;
        submitBtn.textContent = 'Tạo Đơn';
    }
}

function showImportCSVModal() {
    const modal = document.getElementById('modal-overlay');
    const title = document.getElementById('modal-title');
    const body = document.getElementById('modal-body');
    if (!modal || !body) return;

    title.textContent = 'Import đơn hàng từ CSV';
    body.innerHTML = `
        <div style="margin-bottom: 1rem;">
            <p style="color: #94A3B8; font-size: 0.875rem; margin-bottom: 1rem;">
                Upload file CSV. File cần có các cột:
                <code style="color: #3B82F6; background: #1E293B; padding: 0.125rem 0.375rem; border-radius: 0.25rem;">customer_name</code>,
                <code style="color: #3B82F6; background: #1E293B; padding: 0.125rem 0.375rem; border-radius: 0.25rem;">email</code>,
                <code style="color: #3B82F6; background: #1E293B; padding: 0.125rem 0.375rem; border-radius: 0.25rem;">product_name</code>,
                <code style="color: #3B82F6; background: #1E293B; padding: 0.125rem 0.375rem; border-radius: 0.25rem;">quantity</code>
            </p>
            <p style="color: #64748B; font-size: 0.8125rem; margin-bottom: 1rem;">
                Các dòng có cùng email sẽ được gộp thành một đơn hàng. Mã vạch sẽ được gửi qua email cho khách.
            </p>
        </div>
        <div style="margin-bottom: 1rem;">
            <label class="form-label" for="csv-file">Chọn file CSV *</label>
            <input type="file" class="form-input" id="csv-file" accept=".csv" required
                   style="padding: 0.5rem; cursor: pointer;">
        </div>
        <div id="csv-upload-result" style="display: none; margin-bottom: 1rem;"></div>
        <div style="display: flex; gap: 0.75rem; justify-content: flex-end; margin-top: 1.5rem;">
            <button type="button" class="btn btn-ghost" onclick="closeModal()">Huỷ</button>
            <button type="button" class="btn btn-primary" id="btn-upload-csv" onclick="uploadCSV()">
                Upload & Tạo đơn
            </button>
        </div>
    `;
    modal.classList.add('active');
}

async function uploadCSV() {
    const fileInput = document.getElementById('csv-file');
    const resultDiv = document.getElementById('csv-upload-result');
    const uploadBtn = document.getElementById('btn-upload-csv');

    if (!fileInput || !fileInput.files.length) {
        showToast('Vui lòng chọn file CSV', 'warning');
        return;
    }

    const file = fileInput.files[0];
    if (!file.name.toLowerCase().endsWith('.csv')) {
        showToast('Vui lòng chọn file có định dạng .csv', 'warning');
        return;
    }

    if (uploadBtn) uploadBtn.disabled = true;

    try {
        const formData = new FormData();
        formData.append('file', file);

        const result = await api.upload('/preorders/import-csv', formData);

        // Show results
        if (resultDiv) {
            resultDiv.style.display = 'block';
            let html = '';
            if (result.success > 0) {
                html += `<div style="color: #22C55E; margin-bottom: 0.5rem;">✓ Tạo thành công ${result.success} đơn đặt trước</div>`;
            }
            if (result.errors && result.errors.length > 0) {
                html += `<div style="color: #EF4444; margin-bottom: 0.5rem;">⚠ ${result.errors.length} lỗi:</div>`;
                html += '<ul style="color: #EF4444; font-size: 0.8125rem; padding-left: 1rem;">';
                result.errors.forEach(function (e) {
                    html += `<li>${escapeHtml(e)}</li>`;
                });
                html += '</ul>';
            }
            resultDiv.innerHTML = html;
        }

        if (result.success > 0) {
            showToast(`Đã tạo ${result.success} đơn đặt trước!`, 'success');
            loadPreorders();
        }
    } catch (err) {
        showToast('Lỗi upload: ' + err.message, 'error');
        if (resultDiv) {
            resultDiv.style.display = 'block';
            resultDiv.innerHTML = `<div style="color: #EF4444;">Lỗi: ${escapeHtml(err.message)}</div>`;
        }
    } finally {
        if (uploadBtn) uploadBtn.disabled = false;
    }
}

async function cancelPreorder(id) {
    if (!confirm('Bạn có chắc chắn muốn huỷ đơn đặt trước này?')) return;

    try {
        await api.del(`/preorders/${id}`);
        showToast('Đã huỷ đơn đặt trước', 'success');
        loadPreorders(adminPreordersPage);
    } catch (err) {
        showToast('Lỗi: ' + err.message, 'error');
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

    // Export barcode sheet button
    const exportBarcodeSheetBtn = document.getElementById('btn-export-barcode-sheet');
    if (exportBarcodeSheetBtn) {
        exportBarcodeSheetBtn.addEventListener('click', async function () {
            try {
                showToast('Đang tạo Barcode Sheet...', 'info');
                const token = localStorage.getItem('evient_token');
                const response = await fetch(`${api.baseUrl}/products/export/sheet`, {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                
                if (!response.ok) throw new Error('Không thể xuất file');
                
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = 'barcode_sheet.png';
                document.body.appendChild(a);
                a.click();
                a.remove();
                window.URL.revokeObjectURL(url);
                showToast('Xuất thành công!', 'success');
            } catch (err) {
                showToast('Lỗi: ' + err.message, 'error');
            }
        });
    }

    // Add user button
    const addUserBtn = document.getElementById('btn-add-user');
    if (addUserBtn) {
        addUserBtn.addEventListener('click', function () {
            showUserModal(null);
        });
    }

    // Import CSV button
    const importCSVBtn = document.getElementById('btn-import-csv');
    if (importCSVBtn) {
        importCSVBtn.addEventListener('click', function () {
            showImportCSVModal();
        });
    }

    // Create Preorder button
    const createPreorderBtn = document.getElementById('btn-create-preorder');
    if (createPreorderBtn) {
        createPreorderBtn.addEventListener('click', function () {
            showCreatePreorderModal();
        });
    }

    // Pre-order status filter
    const preorderFilter = document.getElementById('preorder-status-filter');
    if (preorderFilter) {
        preorderFilter.addEventListener('change', function () {
            loadPreorders(1);
        });
    }

    // Shift Management button
    const shiftBtn = document.getElementById('btn-shift');
    if (shiftBtn) {
        shiftBtn.addEventListener('click', function () {
            if (typeof manageShift === 'function') {
                manageShift();
            } else {
                showToast('Chức năng quản lý ca chỉ có trên trang POS.', 'warning');
            }
        });
    }

    // Hide users and logs tabs if not admin
    if (user && user.role !== 'admin') {
        const usersTab = document.querySelector('[data-tab="users"]');
        if (usersTab) usersTab.style.display = 'none';
        
        const logsTab = document.querySelector('[data-tab="logs"]');
        if (logsTab) logsTab.style.display = 'none';
    }

    // Load initial tab
    switchTab('dashboard');
}
