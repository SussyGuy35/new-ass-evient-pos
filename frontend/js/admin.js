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
        case 'categories':
            loadCategories();
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
                <div class="bg-slate-700 p-4 rounded-xl border border-slate-600">
                    <div class="text-sm text-slate-400 mb-1">Đặt trước</div>
                    <div class="text-xl font-bold text-white">${formatCurrency(data.all_time.preorder_revenue)}</div>
                </div>
            </div>
            
            <h3 class="text-lg font-bold text-white mb-4">Sản phẩm Bán chạy</h3>
            <div style="max-height: 400px; overflow-y: auto; border: 1px solid #334155; border-radius: 0.75rem;">
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
            </div>
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
        let url = `/products?page=${page}&per_page=${APP_CONFIG.ITEMS_PER_PAGE}`;
        const sortSelect = document.getElementById('product-sort-select');
        if (sortSelect && sortSelect.value) {
            const [sortBy, order] = sortSelect.value.split('-');
            url += `&sort_by=${sortBy}&order=${order}`;
        }

        const data = await api.get(url);
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
                        <th style="width: 40px; text-align: center;">
                            <input type="checkbox" id="select-all-products" class="form-checkbox" onclick="toggleAllProducts(this)">
                        </th>
                        <th>ID</th>
                        <th>Tên sản phẩm</th>
                        <th>Danh mục</th>
                        <th>Barcode</th>
                        <th>Giá bán</th>
                        <th>Giá Preorder</th>
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
                    <td style="text-align: center;">
                        <input type="checkbox" class="product-checkbox form-checkbox" value="${p.id}" ${!p.barcode ? 'disabled title="Sản phẩm không có barcode"' : ''}>
                    </td>
                    <td style="color: #94A3B8;">#${p.id}</td>
                    <td style="font-weight: 500; color: #E2E8F0;">${escapeHtml(p.name)}</td>
                    <td style="color: #94A3B8;">${escapeHtml(p.category || '—')}</td>
                    <td style="font-family: monospace; color: #94A3B8;">${escapeHtml(p.barcode || '—')}</td>
                    <td style="color: #3B82F6; font-weight: 500;">${formatCurrency(p.price)}</td>
                    <td style="color: #8B5CF6; font-weight: 500;">${p.preorder_price != null ? formatCurrency(p.preorder_price) : '—'}</td>
                    <td class="${stockClass}">
                        ${p.stock} 
                        ${p.stock_reserved ? `<br><span style="font-size: 0.75rem; color: #F59E0B;">(giữ ${p.stock_reserved})</span>` : ''}
                    </td>
                    <td style="text-align: right;">
                        <button class="btn btn-ghost" style="padding: 0.375rem 0.75rem;" onclick="showProductModal('${p.id}')">Sửa</button>
                        <button class="btn btn-ghost" style="padding: 0.375rem 0.75rem; color: #EF4444;" onclick="deleteProduct('${p.id}')">Xóa</button>
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

window.toggleAllProducts = function(source) {
    const checkboxes = document.querySelectorAll('.product-checkbox:not([disabled])');
    checkboxes.forEach(cb => cb.checked = source.checked);
};

async function recalculateReservedStock() {
    if (!confirm('Bạn có chắc chắn muốn tính toán lại toàn bộ số lượng hàng giữ cho đơn đặt trước?')) return;
    
    const btn = document.getElementById('btn-recalc-stock');
    const oldHtml = btn.innerHTML;
    btn.innerHTML = '<div class="spinner" style="width:16px;height:16px;border-width:2px;margin-right:6px;"></div> Đang xử lý...';
    btn.disabled = true;

    try {
        const res = await api.post('/products/recalculate-reserved-stock');
        showToast(`Đã tính lại tồn kho! Cập nhật ${res.updated} sản phẩm.`, 'success');
        loadAdminProducts(); // reload the table
    } catch (err) {
        showToast('Lỗi: ' + err.message, 'error');
    } finally {
        btn.innerHTML = oldHtml;
        btn.disabled = false;
    }
}

function showProductModal(productId) {
    editingProductId = productId || null;
    const modal = document.getElementById('modal-overlay');
    const title = document.getElementById('modal-title');
    const body = document.getElementById('modal-body');
    if (!modal || !body) return;

    title.textContent = productId ? 'Sửa Sản Phẩm' : 'Thêm Sản Phẩm';
    body.innerHTML = '<div style="text-align: center; padding: 1rem;"><div class="spinner" style="margin: 0 auto;"></div></div>';
    modal.classList.add('active');

    Promise.all([
        api.get('/categories'),
        productId ? api.get(`/products/${productId}`) : Promise.resolve(null)
    ]).then(function ([categories, product]) {
        renderProductForm(product, categories);
    }).catch(function (err) {
        body.innerHTML = `<p style="color: #EF4444;">Lỗi: ${err.message}</p>`;
    });
}

function renderProductForm(product, categories = []) {
    const body = document.getElementById('modal-body');
    if (!body) return;

    let categoryOptions = '<option value="">-- Không chọn --</option>';
    categories.forEach(cat => {
        const selected = (product && product.category === cat.name) ? 'selected' : '';
        categoryOptions += `<option value="${escapeHtml(cat.name)}" ${selected}>${escapeHtml(cat.name)}</option>`;
    });

    body.innerHTML = `
        <form id="form-product" onsubmit="event.preventDefault(); saveProduct();">
            <div style="margin-bottom: 1rem;">
                <label class="form-label" for="prod-name">Tên sản phẩm *</label>
                <input class="form-input" id="prod-name" required value="${product ? escapeHtml(product.name) : ''}" placeholder="Nhập tên sản phẩm">
            </div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: 1rem;">
                <div>
                    <label class="form-label" for="prod-barcode">Barcode</label>
                    <input class="form-input" id="prod-barcode" value="${product ? escapeHtml(product.barcode || '') : ''}" placeholder="Mã barcode">
                </div>
                <div>
                    <label class="form-label" for="prod-category">Danh mục</label>
                    <select class="form-input form-select" id="prod-category">
                        ${categoryOptions}
                    </select>
                </div>
            </div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: 1rem;">
                <div>
                    <label class="form-label" for="prod-price">Giá (VNĐ) *</label>
                    <input class="form-input" id="prod-price" type="number" min="0" required value="${product ? product.price : ''}" placeholder="0">
                </div>
                <div>
                    <label class="form-label" for="prod-preorder-price">Giá Preorder (VNĐ)</label>
                    <input class="form-input" id="prod-preorder-price" type="number" min="0" value="${(product && product.preorder_price !== null && product.preorder_price !== undefined) ? product.preorder_price : ''}" placeholder="Nếu trống, sẽ dùng Giá mặc định">
                </div>
            </div>
            <div style="margin-bottom: 1rem;">
                <label class="form-label" for="prod-stock">Tồn kho *</label>
                <input class="form-input" id="prod-stock" type="number" min="0" required value="${product ? product.stock : ''}" placeholder="0">
            </div>
            <div style="display: flex; gap: 0.75rem; justify-content: flex-end; margin-top: 1.5rem;">
                <button type="button" class="btn btn-ghost" onclick="closeModal()">Hủy</button>
                <button type="submit" class="btn btn-primary" id="btn-save-product">
                    ${editingProductId ? 'Cập nhật' : 'Thêm mới'}
                </button>
            </div>
        </form>
    `;
    
    // Init custom select for product category
    if (typeof initCustomSelect === 'function') {
        const prodCategorySelect = document.getElementById('prod-category');
        if (prodCategorySelect) initCustomSelect(prodCategorySelect);
    }
}

async function saveProduct() {
    const name = document.getElementById('prod-name').value.trim();
    const barcode = document.getElementById('prod-barcode').value.trim();
    const price = parseFloat(document.getElementById('prod-price').value);
    const preorderPriceVal = document.getElementById('prod-preorder-price').value;
    const preorder_price = preorderPriceVal !== '' ? parseFloat(preorderPriceVal) : null;
    const categoryVal = document.getElementById('prod-category').value;
    const category = categoryVal !== '' ? categoryVal : null;
    const stock = parseInt(document.getElementById('prod-stock').value, 10);

    if (!name) {
        showToast('Vui lòng nhập tên sản phẩm', 'warning');
        return;
    }

    const formData = { name, barcode, price, preorder_price, category, stock };
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
                        <button class="btn btn-ghost" style="padding: 0.375rem 0.75rem;" onclick="showUserModal('${u.id}')">Sửa</button>
                        <button class="btn btn-ghost" style="padding: 0.375rem 0.75rem; color: #EF4444;" onclick="deleteUser('${u.id}')">Xóa</button>
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
    
    if (typeof initCustomSelect === 'function') {
        const roleSelect = document.getElementById('user-role');
        const activeSelect = document.getElementById('user-active');
        if (roleSelect) initCustomSelect(roleSelect);
        if (activeSelect) initCustomSelect(activeSelect);
    }
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
                        <th>Mã đơn hàng</th>
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
            let paymentLabel = 'Chuyển khoản';
            let paymentBadge = 'badge-info';
            if (o.payment_method === 'cash') {
                paymentLabel = 'Tiền mặt';
                paymentBadge = 'badge-success';
            } else if (o.payment_method === 'preorder') {
                paymentLabel = 'Đặt trước';
                paymentBadge = 'badge-secondary';
            }
            
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
                    <td style="color: #94A3B8; font-size: 0.875rem;">${createdAt}</td>
                    <td style="text-align: right;">
                        <button class="btn btn-ghost" style="padding: 0.375rem 0.75rem;"
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
                        <th style="width: 40px;"><input type="checkbox" id="preorder-select-all" onchange="toggleAllPreorderCheckboxes(this)" style="width: 18px; height: 18px; cursor: pointer;"></th>
                        <th>Mã barcode</th>
                        <th>Khách hàng</th>
                        <th>Email</th>
                        <th>Ghi chú</th>
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
                    <td><input type="checkbox" class="preorder-checkbox" value="${po.id}" onchange="updateBulkResendButton()" style="width: 18px; height: 18px; cursor: pointer;"></td>
                    <td style="font-family: monospace; font-weight: 500; color: #E2E8F0;">${escapeHtml(po.barcode_code)}</td>
                    <td style="font-weight: 500; color: #E2E8F0;">${escapeHtml(po.customer_name)}</td>
                    <td style="color: #94A3B8; font-size: 0.8125rem;">${escapeHtml(po.email)}</td>
                    <td style="color: #94A3B8; font-size: 0.8125rem; max-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtml(po.note || '')}</td>
                    <td style="color: #3B82F6; font-weight: 500;">${formatCurrency(po.total)}</td>
                    <td><span class="badge ${st.badge}">${st.label}</span></td>
                    <td style="color: #94A3B8; font-size: 0.875rem;">${createdAt}</td>
                    <td style="text-align: right;">
                        <button class="btn btn-ghost" style="padding: 0.375rem 0.75rem; color: #3B82F6;" onclick="resendPreorderEmail('${po.id}')" title="Gửi lại mã vạch qua Email">✉ Gửi lại mail</button>
                        ${po.status === 'pending' ? `<button class="btn btn-ghost" style="padding: 0.375rem 0.75rem; color: #EF4444;" onclick="cancelPreorder('${po.id}')">Huỷ</button>` : ''}
                    </td>
                </tr>
            `;
        });

        html += '</tbody></table>';
        container.innerHTML = html;

        // Reset bulk button state
        updateBulkResendButton();

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
            const displayPrice = p.preorder_price != null ? p.preorder_price : p.price;
            productOptions += `<option value="${p.id}">${escapeHtml(p.name)} - ${formatCurrency(displayPrice)}</option>`;
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
                
                <div style="margin-bottom: 1rem;">
                    <label class="form-label" for="po-note">Ghi chú</label>
                    <input class="form-input" id="po-note" placeholder="Ví dụ: Giao gấp, hoặc thông tin thêm...">
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
        
        if (typeof initCustomSelect === 'function') {
            const poProductSelect = document.getElementById('po-product-select');
            if (poProductSelect) initCustomSelect(poProductSelect);
        }
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
    const note = document.getElementById('po-note') ? document.getElementById('po-note').value.trim() : "";
    
    const submitBtn = document.getElementById('btn-submit-preorder');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Đang tạo...';
    
    try {
        const payload = {
            customer_name: customerName,
            email: email,
            note: note,
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

let pendingImportBatch = null;

function showImportCSVModal() {
    pendingImportBatch = null;
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
        </div>
        <div id="csv-upload-section" style="margin-bottom: 1rem;">
            <label class="form-label" for="csv-file">Chọn file CSV *</label>
            <input type="file" class="form-input" id="csv-file" accept=".csv" required
                   style="padding: 0.5rem; cursor: pointer;">
            <div style="display: flex; gap: 0.75rem; justify-content: flex-end; margin-top: 1.5rem;">
                <button type="button" class="btn btn-ghost" onclick="closeModal()">Huỷ</button>
                <button type="button" class="btn btn-primary" id="btn-preview-csv" onclick="previewCSV()">
                    Xem trước
                </button>
            </div>
        </div>
        <div id="csv-preview-section" style="display: none; margin-bottom: 1rem; max-height: 400px; overflow-y: auto;">
            <!-- Injected preview -->
        </div>
        <div id="csv-confirm-section" style="display: none; gap: 0.75rem; justify-content: flex-end; margin-top: 1.5rem;">
            <button type="button" class="btn btn-ghost" onclick="showImportCSVModal()">Tải file khác</button>
            <button type="button" class="btn btn-primary" id="btn-confirm-csv" onclick="confirmCSV()">
                Xác nhận & Tạo đơn
            </button>
        </div>
    `;
    modal.classList.add('active');
}

async function previewCSV() {
    const fileInput = document.getElementById('csv-file');
    const previewBtn = document.getElementById('btn-preview-csv');
    const previewSection = document.getElementById('csv-preview-section');
    const confirmSection = document.getElementById('csv-confirm-section');

    if (!fileInput || !fileInput.files.length) {
        showToast('Vui lòng chọn file CSV', 'warning');
        return;
    }

    const file = fileInput.files[0];
    if (!file.name.toLowerCase().endsWith('.csv')) {
        showToast('Vui lòng chọn file có định dạng .csv', 'warning');
        return;
    }

    if (previewBtn) previewBtn.disabled = true;
    previewSection.style.display = 'block';
    previewSection.innerHTML = '<div style="text-align: center; padding: 1rem;"><div class="spinner" style="margin: 0 auto;"></div></div>';

    try {
        const formData = new FormData();
        formData.append('file', file);

        const result = await api.upload('/preorders/preview-csv', formData);
        
        pendingImportBatch = result.valid_preorders;

        let html = '';
        if (result.errors && result.errors.length > 0) {
            html += `<div style="color: #EF4444; margin-bottom: 1rem; padding: 0.75rem; background: rgba(239, 68, 68, 0.1); border-radius: 0.5rem;">`;
            html += `<div style="font-weight: 600; margin-bottom: 0.5rem;">⚠ ${result.errors.length} Lỗi phát hiện:</div>`;
            html += '<ul style="margin: 0; padding-left: 1.5rem; font-size: 0.875rem;">';
            result.errors.forEach(e => html += `<li>${escapeHtml(e)}</li>`);
            html += '</ul></div>';
        }

        if (result.valid_preorders && result.valid_preorders.length > 0) {
            html += `<div style="color: #22C55E; margin-bottom: 0.5rem; font-weight: 600;">✓ Sẵn sàng tạo ${result.valid_preorders.length} đơn:</div>`;
            html += `<table class="admin-table" style="font-size: 0.875rem;">
                <thead>
                    <tr>
                        <th>Khách hàng</th>
                        <th>Email</th>
                        <th style="text-align: right;">Tổng tiền</th>
                    </tr>
                </thead>
                <tbody>
            `;
            result.valid_preorders.forEach(p => {
                html += `
                    <tr>
                        <td>${escapeHtml(p.customer_name)}<br><span style="font-size: 0.75rem; color: #94A3B8;">${p.items.length} SP</span></td>
                        <td>${escapeHtml(p.email)}</td>
                        <td style="text-align: right; color: #10B981; font-weight: 500;">${formatCurrency(p.total)}</td>
                    </tr>
                `;
            });
            html += `</tbody></table>`;
            
            document.getElementById('csv-upload-section').style.display = 'none';
            confirmSection.style.display = 'flex';
        } else {
            html += `<div style="color: #EF4444; margin-top: 1rem;">Không có đơn hàng nào hợp lệ để tạo.</div>`;
        }

        previewSection.innerHTML = html;

    } catch (err) {
        showToast('Lỗi xem trước: ' + err.message, 'error');
        previewSection.innerHTML = `<div style="color: #EF4444;">Lỗi: ${escapeHtml(err.message)}</div>`;
    } finally {
        if (previewBtn) previewBtn.disabled = false;
    }
}

async function confirmCSV() {
    if (!pendingImportBatch || pendingImportBatch.length === 0) return;
    
    const confirmBtn = document.getElementById('btn-confirm-csv');
    if (confirmBtn) {
        confirmBtn.disabled = true;
        confirmBtn.innerHTML = '<span class="spinner" style="width: 1rem; height: 1rem; border-width: 2px; margin-right: 0.5rem;"></span> Đang xử lý...';
    }

    try {
        const result = await api.post('/preorders/confirm-csv', { valid_preorders: pendingImportBatch });
        
        if (result.success > 0) {
            showToast(`Đã tạo thành công ${result.success} đơn đặt trước!`, 'success');
            closeModal();
            loadPreorders();
        } else {
            showToast('Không có đơn hàng nào được tạo', 'warning');
            closeModal();
        }
    } catch (err) {
        showToast('Lỗi xác nhận: ' + err.message, 'error');
        if (confirmBtn) {
            confirmBtn.disabled = false;
            confirmBtn.textContent = 'Xác nhận & Tạo đơn';
        }
    }
}

function toggleAllPreorderCheckboxes(masterCheckbox) {
    const checkboxes = document.querySelectorAll('.preorder-checkbox');
    checkboxes.forEach(function (cb) {
        cb.checked = masterCheckbox.checked;
    });
    updateBulkResendButton();
}

function updateBulkResendButton() {
    const checked = document.querySelectorAll('.preorder-checkbox:checked');
    const btn = document.getElementById('btn-bulk-resend-email');
    const countSpan = document.getElementById('bulk-resend-count');
    if (btn) {
        btn.style.display = checked.length > 0 ? 'inline-flex' : 'none';
    }
    if (countSpan) {
        countSpan.textContent = checked.length;
    }
}

async function bulkResendEmail() {
    const checked = document.querySelectorAll('.preorder-checkbox:checked');
    const ids = Array.from(checked).map(function (cb) { return cb.value; });
    if (ids.length === 0) {
        showToast('Chưa chọn đơn nào', 'warning');
        return;
    }
    if (!confirm('Gửi lại email cho ' + ids.length + ' đơn đặt trước?')) return;

    const btn = document.getElementById('btn-bulk-resend-email');
    if (btn) btn.disabled = true;

    try {
        showToast('Đang gửi ' + ids.length + ' email...', 'info');
        const result = await api.post('/preorders/bulk-resend-email', { ids: ids });
        showToast(result.message, result.failed > 0 ? 'warning' : 'success');
        // Uncheck all
        const selectAll = document.getElementById('preorder-select-all');
        if (selectAll) selectAll.checked = false;
        toggleAllPreorderCheckboxes({ checked: false });
    } catch (err) {
        showToast('Lỗi: ' + err.message, 'error');
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function resendPreorderEmail(id) {
    try {
        showToast('Đang gửi lại email...', 'info');
        await api.post(`/preorders/${id}/resend-email`);
        showToast('Đã gửi lại email thành công!', 'success');
    } catch (err) {
        showToast('Lỗi gửi email: ' + err.message, 'error');
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
// CATEGORIES TAB
// =====================
let editingCategoryId = null;

async function loadCategories() {
    const tableBody = document.getElementById('admin-categories-table');
    if (!tableBody) return;
    
    tableBody.innerHTML = '<tr><td colspan="2" style="text-align: center;"><div class="spinner"></div></td></tr>';
    
    try {
        const categories = await api.get('/categories');
        
        if (!categories || categories.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="2" style="text-align: center; color: #94A3B8;">Chưa có danh mục nào</td></tr>';
            return;
        }
        
        let html = '';
        categories.forEach(cat => {
            html += `
                <tr>
                    <td class="font-semibold text-white">${escapeHtml(cat.name)}</td>
                    <td style="text-align: right; width: 320px;">
                        <button class="btn btn-ghost text-sm gap-1.5" style="color: #10B981; padding: 0.375rem 0.75rem;" onclick="showCategoryProductsModal('${escapeHtml(cat.name).replace(/'/g, "\\'")}')">
                            <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                                <path stroke-linecap="round" stroke-linejoin="round" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"/>
                            </svg>
                            Sản phẩm
                        </button>
                        <button class="btn btn-ghost text-sm gap-1.5" style="color: #3B82F6; padding: 0.375rem 0.75rem;" onclick='showCategoryModal(${JSON.stringify(cat).replace(/'/g, "&#39;")})'>
                            <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                               <path stroke-linecap="round" stroke-linejoin="round" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                            </svg>
                            Sửa
                        </button>
                        <button class="btn btn-ghost text-sm gap-1.5" style="color: #EF4444; padding: 0.375rem 0.75rem;" onclick="deleteCategory('${cat.id}')">
                            <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                               <path stroke-linecap="round" stroke-linejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                            </svg>
                            Xoá
                        </button>
                    </td>
                </tr>
            `;
        });
        tableBody.innerHTML = html;
    } catch (err) {
        tableBody.innerHTML = `<tr><td colspan="2" style="color: #EF4444; text-align: center;">Lỗi tải dữ liệu: ${err.message}</td></tr>`;
    }
}

function showCategoryModal(cat = null) {
    editingCategoryId = cat ? cat.id : null;
    
    const modal = document.getElementById('modal-overlay');
    const title = document.getElementById('modal-title');
    const body = document.getElementById('modal-body');
    if (!modal || !body) return;
    
    title.textContent = cat ? 'Sửa Danh mục' : 'Thêm Danh mục';
    body.innerHTML = `
        <form id="category-form" onsubmit="event.preventDefault(); saveCategory();">
            <div style="margin-bottom: 1rem;">
                <label class="form-label">Tên danh mục *</label>
                <input type="text" class="form-input" id="cat-name" required value="${cat ? escapeHtml(cat.name) : ''}">
            </div>
            </div>
            <div style="display: flex; justify-content: flex-end; gap: 0.75rem;">
                <button type="button" class="btn btn-ghost" onclick="closeModal()">Hủy</button>
                <button type="submit" class="btn btn-primary" id="btn-save-cat">Lưu</button>
            </div>
        </form>
    `;
    modal.classList.add('active');
    document.getElementById('cat-name').focus();
}

async function saveCategory() {
    const btn = document.getElementById('btn-save-cat');
    if (btn) btn.disabled = true;
    
    const payload = {
        name: document.getElementById('cat-name').value.trim()
    };
    
    try {
        if (editingCategoryId) {
            await api.put('/categories/' + editingCategoryId, payload);
            showToast('Đã cập nhật danh mục', 'success');
        } else {
            await api.post('/categories', payload);
            showToast('Đã thêm danh mục', 'success');
        }
        closeModal();
        loadCategories();
    } catch (err) {
        showToast('Lỗi: ' + err.message, 'error');
        if (btn) btn.disabled = false;
    }
}

async function deleteCategory(id) {
    if (!confirm('Bạn có chắc chắn muốn xóa danh mục này?')) return;
    
    try {
        await api.delete('/categories/' + id);
        showToast('Đã xóa danh mục', 'success');
        loadCategories();
    } catch (err) {
        showToast('Lỗi xóa: ' + err.message, 'error');
    }
}

// =====================
// CATEGORY PRODUCTS MODAL
// =====================

function closeCategoryProductsModal() {
    const modal = document.getElementById('modal-category-products-overlay');
    if (modal) modal.classList.remove('active');
}

async function showCategoryProductsModal(categoryName) {
    const modal = document.getElementById('modal-category-products-overlay');
    const title = document.getElementById('modal-category-products-title');
    const body = document.getElementById('modal-category-products-body');
    
    if (!modal || !title || !body) return;
    
    title.textContent = `Sản phẩm trong danh mục: ${categoryName}`;
    body.innerHTML = '<div style="text-align: center; padding: 2rem;"><div class="spinner" style="margin: 0 auto;"></div></div>';
    modal.classList.add('active');
    
    try {
        // Fetch products in this category (up to 1000 items)
        const productsData = await api.get(`/products?category=${encodeURIComponent(categoryName)}&per_page=1000`);
        const items = productsData.items || productsData.products || productsData || [];
        
        // Fetch all products to allow adding
        const allProductsData = await api.get('/products?per_page=10000');
        const allProducts = allProductsData.items || allProductsData.products || allProductsData || [];
        
        // Only include products that do not belong to any category
        const availableProducts = allProducts.filter(p => !p.category);
        
        let availableOptions = '<option value="">-- Chọn sản phẩm để thêm --</option>';
        availableProducts.forEach(p => {
            availableOptions += `<option value="${p.id}">${escapeHtml(p.name)} (${p.barcode || 'N/A'})</option>`;
        });
        
        let html = `
            <div style="margin-bottom: 1.5rem; display: flex; gap: 0.75rem;">
                <select id="add-category-product-select" class="form-input form-select" style="flex: 1;">
                    ${availableOptions}
                </select>
                <button class="btn btn-primary" style="padding-left: 1.5rem; padding-right: 1.5rem;" onclick="addProductToCategory('${escapeHtml(categoryName).replace(/'/g, "\\'")}')">Thêm</button>
            </div>
            
            <div class="bg-slate-800 border border-slate-700 rounded-xl overflow-x-auto" style="max-height: 400px; overflow-y: auto;">
                <table class="admin-table w-full">
                    <thead style="position: sticky; top: 0; background: #1E293B; z-index: 10;">
                        <tr>
                            <th>Tên sản phẩm</th>
                            <th>Barcode</th>
                            <th>Giá bán</th>
                            <th>Tồn kho</th>
                            <th class="text-right">Hành động</th>
                        </tr>
                    </thead>
                    <tbody>
        `;
        
        if (items.length === 0) {
            html += '<tr><td colspan="5" style="text-align: center; color: #94A3B8;">Danh mục này chưa có sản phẩm nào</td></tr>';
        } else {
            items.forEach(p => {
                const stockClass = p.stock <= 0 ? 'stock-out' : p.stock <= 10 ? 'stock-low' : 'stock-ok';
                html += `
                    <tr>
                        <td class="font-semibold text-white">${escapeHtml(p.name)}</td>
                        <td style="font-family: monospace; color: #94A3B8;">${escapeHtml(p.barcode || '—')}</td>
                        <td style="color: #3B82F6; font-weight: 500;">${formatCurrency(p.price)}</td>
                        <td class="${stockClass}">${p.stock}</td>
                        <td style="text-align: right;">
                            <button class="btn btn-ghost" style="padding: 0.25rem 0.5rem; color: #EF4444;" onclick="removeProductFromCategory('${p.id}', '${escapeHtml(categoryName).replace(/'/g, "\\'")}')">Gỡ</button>
                        </td>
                    </tr>
                `;
            });
        }
        
        html += `
                    </tbody>
                </table>
            </div>
            <div style="display: flex; justify-content: flex-end; margin-top: 1.5rem;">
                <button class="btn btn-ghost" onclick="closeCategoryProductsModal()">Đóng</button>
            </div>
        `;
        
        body.innerHTML = html;
        
        if (typeof initCustomSelect === 'function') {
            const addProductSelect = document.getElementById('add-category-product-select');
            if (addProductSelect) initCustomSelect(addProductSelect);
        }
        
    } catch (err) {
        body.innerHTML = `<p style="color: #EF4444; text-align: center;">Lỗi tải dữ liệu: ${err.message}</p>`;
    }
}

async function removeProductFromCategory(productId, categoryName) {
    if (!confirm('Bạn có chắc chắn muốn gỡ sản phẩm này khỏi danh mục?')) return;
    try {
        await api.put(`/products/${productId}`, { category: null });
        showToast('Đã gỡ sản phẩm khỏi danh mục', 'success');
        showCategoryProductsModal(categoryName); // Refresh modal
    } catch (err) {
        showToast('Lỗi: ' + err.message, 'error');
    }
}

async function addProductToCategory(categoryName) {
    const select = document.getElementById('add-category-product-select');
    const productId = select ? select.value : null;
    if (!productId) {
        showToast('Vui lòng chọn sản phẩm', 'warning');
        return;
    }
    
    try {
        await api.put(`/products/${productId}`, { category: categoryName });
        showToast('Đã thêm sản phẩm vào danh mục', 'success');
        showCategoryProductsModal(categoryName); // Refresh modal
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
                // Determine selected products
                const selectedCheckboxes = document.querySelectorAll('.product-checkbox:checked');
                const selectedIds = Array.from(selectedCheckboxes).map(cb => cb.value);

                // Determine current sort & search
                const sortSelect = document.getElementById('product-sort-select');
                let sortBy = 'created_at', order = 'desc';
                if (sortSelect && sortSelect.value) {
                    [sortBy, order] = sortSelect.value.split('-');
                }
                const searchInput = document.getElementById('search-input'); // if we have global search, else omit

                const payload = {
                    product_ids: selectedIds,
                    sort_by: sortBy,
                    order: order
                };
                
                showToast('Đang tạo Barcode Sheet...', 'info');
                const token = localStorage.getItem('evient_token');
                const response = await fetch(`${api.baseUrl}/products/export/sheet`, {
                    method: 'POST',
                    headers: { 
                        'Authorization': `Bearer ${token}`,
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(payload)
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

