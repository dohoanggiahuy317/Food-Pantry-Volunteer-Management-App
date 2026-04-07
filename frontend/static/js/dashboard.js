// Global state
let currentUser = null;
let currentPantryId = null;
let allPantries = [];
let allPublicPantries = [];
let expandedShiftContext = null;
let registrationsCache = {};
let editingShiftSnapshot = null;
let activeManageShiftsSubtab = 'create';
let activeAdminSubtab = 'pantries';
let adminRoles = [];
let adminUsers = [];
let selectedAdminUserId = null;
let selectedAdminUserProfile = null;
let selectedAdminUserProfileError = '';
let lastAdminUsersPhoneViewport = null;
let dashboardBootPromise = null;
let dashboardEventListenersBound = false;

function currentUserHasRole(roleName) {
    return Boolean(currentUser && Array.isArray(currentUser.roles) && currentUser.roles.includes(roleName));
}

function currentUserIsAdminCapable() {
    return currentUserHasRole('ADMIN') || currentUserHasRole('SUPER_ADMIN');
}

async function syncCurrentUserTimezoneIfNeeded() {
    if (!currentUser || typeof updateCurrentUserProfile !== 'function') {
        return;
    }

    const browserTimeZone = getBrowserTimeZone();
    if (!browserTimeZone || currentUser.timezone === browserTimeZone) {
        return;
    }

    try {
        currentUser = await updateCurrentUserProfile({ timezone: browserTimeZone });
    } catch (error) {
        console.error('Failed to sync browser timezone:', error);
    }
}

async function initializeDashboardApp() {
    if (dashboardBootPromise) {
        return dashboardBootPromise;
    }

    dashboardBootPromise = (async () => {
        try {
            if (typeof getCurrentUser === 'undefined') {
                throw new Error('Required functions not loaded. Please refresh the page.');
            }

            currentUser = await getCurrentUser();
            await syncCurrentUserTimezoneIfNeeded();
            document.getElementById('user-email').textContent = currentUser.email;
            document.getElementById('user-role').textContent = currentUser.roles.join(', ');

            const defaultTab = setupRoleBasedUI();
            await loadPantries();

            if (!dashboardEventListenersBound) {
                setupEventListeners();
                dashboardEventListenersBound = true;
            }

            await activateTab(defaultTab);
        } catch (error) {
            dashboardBootPromise = null;
            console.error('Failed to initialize dashboard:', error);
            showMessage('calendar', `Failed to load: ${error.message}`, 'error');
            const shiftsContainer = document.getElementById('shifts-container');
            if (shiftsContainer) {
                shiftsContainer.innerHTML = `
                    <div class="error-state-card">
                        <h3>Failed to Load</h3>
                        <p><strong>${escapeHtml(error.message || 'Unknown error')}</strong></p>
                    </div>
                `;
            }
            throw error;
        }
    })();

    return dashboardBootPromise;
}

// Setup UI based on role
function setupRoleBasedUI() {
    const isAdmin = currentUserIsAdminCapable();
    const isPantryLead = currentUserHasRole('PANTRY_LEAD');
    const isVolunteer = currentUserHasRole('VOLUNTEER');
    const calendarTab = document.querySelector('.nav-tab[data-tab="calendar"]');
    const calendarContent = document.getElementById('content-calendar');
    const shiftsTab = document.getElementById('tab-shifts');
    const adminTab = document.getElementById('tab-admin');
    const myShiftsTab = document.getElementById('tab-my-shifts');
    let defaultTab = 'calendar';

    const hideCalendarForLead = isPantryLead && !isAdmin && !isVolunteer;
    if (calendarTab) {
        calendarTab.classList.toggle('hidden', hideCalendarForLead);
        if (hideCalendarForLead) {
            calendarContent?.classList.remove('active');
            defaultTab = 'shifts';
        }
    }

    shiftsTab?.classList.toggle('hidden', !(isAdmin || isPantryLead));
    adminTab?.classList.toggle('hidden', !isAdmin);
    myShiftsTab?.classList.toggle('hidden', !isVolunteer);

    return defaultTab;
}

async function activateTab(targetTab) {
    // Update active tab style
    document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
    const targetButton = document.querySelector(`.nav-tab[data-tab="${targetTab}"]`);
    targetButton?.classList.add('active');

    // Show target content
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.remove('active');
    });
    document.getElementById(`content-${targetTab}`)?.classList.add('active');

    // Show/hide pantry selector based on tab
    const pantrySelector = document.getElementById('pantry-selector');
    if (pantrySelector) {
        const shouldHideSelector = targetTab === 'calendar' || targetTab === 'my-shifts' || targetTab === 'my-account' || targetTab === 'admin';
        pantrySelector.classList.toggle('app-hidden', shouldHideSelector);
    }

    // Load tab-specific data
    if (targetTab === 'shifts') {
        setManageShiftsSubtab(activeManageShiftsSubtab);
        await loadShiftsTable();
    } else if (targetTab === 'admin') {
        setAdminSubtab(activeAdminSubtab);
        await loadAdminTab();
    } else if (targetTab === 'my-shifts') {
        await loadMyRegisteredShifts();
    } else if (targetTab === 'my-account') {
        await loadMyAccount();
    } else if (targetTab === 'calendar') {
        await loadCalendarShifts();
    }
}

// Load pantries
async function loadPantries() {
    try {
        allPantries = await getPantries();
        allPublicPantries = await getAllPantries();
        const select = document.getElementById('pantry-select');
        const assignSelect = document.getElementById('assign-pantry');
        const selectedPantryStillExists = allPantries.some(pantry => pantry.pantry_id === currentPantryId);

        select.innerHTML = '';
        assignSelect.innerHTML = '<option value="">-- Select Pantry --</option>';

        if (allPantries.length === 0) {
            currentPantryId = null;
            select.innerHTML = '<option value="">No pantries available</option>';
            if (typeof syncCalendarPantryOptions === 'function') {
                syncCalendarPantryOptions();
            }
            if (currentUserIsAdminCapable()) {
                await updatePantriesTable();
            }
            return;
        }

        allPantries.forEach(pantry => {
            const opt = document.createElement('option');
            opt.value = pantry.pantry_id;
            opt.textContent = pantry.name;
            select.appendChild(opt);

            const assignOpt = opt.cloneNode(true);
            assignSelect.appendChild(assignOpt);
        });

        currentPantryId = selectedPantryStillExists ? currentPantryId : allPantries[0].pantry_id;
        select.value = currentPantryId;
        if (typeof syncCalendarPantryOptions === 'function') {
            syncCalendarPantryOptions();
        }

        // Load pantry leads for admin
        if (currentUserIsAdminCapable()) {
            await loadPantryLeads();
        }
    } catch (error) {
        console.error('Failed to load pantries:', error);
        showMessage('calendar', `Failed to load pantries: ${error.message}`, 'error');
    }
}

// Load pantry leads (admin)
async function loadPantryLeads() {
    try {
        const leads = await getAllUsers('PANTRY_LEAD');
        const leadSelect = document.getElementById('assign-lead');
        leadSelect.innerHTML = '<option value="">-- Select Lead --</option>';

        leads.forEach(lead => {
            const opt = document.createElement('option');
            opt.value = lead.user_id;
            opt.textContent = `${lead.full_name} (${lead.email})`;
            leadSelect.appendChild(opt);
        });

        // Update pantries table
        await updatePantriesTable();
    } catch (error) {
        console.error('Failed to load leads:', error);
    }
}

// Update pantries table
async function updatePantriesTable() {
    const tbody = document.getElementById('pantries-table-body');
    tbody.innerHTML = '';

    if (allPantries.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" class="table-empty-cell">No pantries yet</td></tr>';
        return;
    }

    allPantries.forEach(pantry => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
                    <td data-label="Pantry Name">${pantry.name}</td>
                    <td data-label="Location">${pantry.location_address || '—'}</td>
                    <td data-label="Assigned Leads">${pantry.leads && pantry.leads.length > 0
                ? pantry.leads.map(l => `<span class="lead-pill">${l.full_name}</span>`).join('')
                : '<span class="muted-text">No leads assigned</span>'}</td>
                    <td data-label="Actions">
                        <div class="action-group">
                            <button class="btn btn-secondary btn-sm edit-pantry-btn" data-id="${pantry.pantry_id}" data-name="${pantry.name}" data-address="${pantry.location_address || ''}">Edit</button>
                            <button class="btn btn-danger btn-sm delete-pantry-btn" data-id="${pantry.pantry_id}" data-name="${pantry.name}">Delete</button>
                        </div>
                    </td>
                `;
        tbody.appendChild(tr);
    });

    document.querySelectorAll('.edit-pantry-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.getElementById('edit-pantry-id').value = btn.dataset.id;
            document.getElementById('edit-pantry-name').value = btn.dataset.name;
            document.getElementById('edit-pantry-address').value = btn.dataset.address;
            document.getElementById('edit-pantry-modal').classList.remove('app-hidden');
        });
    });

    document.querySelectorAll('.delete-pantry-btn').forEach(btn => {
        btn.addEventListener('click', async () => {
            const pantryId = parseInt(btn.dataset.id);
            const pantryName = btn.dataset.name;
            const confirmed = window.confirm(
                `Delete pantry "${pantryName}"? This will also remove its shifts, roles, signups, and lead assignments.`
            );

            if (!confirmed) {
                return;
            }

            try {
                await deletePantry(pantryId);

                if (currentPantryId === pantryId) {
                    currentPantryId = null;
                    resetEditShiftForm();
                }

                showMessage('pantry', 'Pantry deleted successfully!', 'success');
                await loadPantries();
            } catch (error) {
                showMessage('pantry', `Error: ${error.message}`, 'error');
            }
        });
    });
}

// Load calendar shifts from ALL pantries
async function loadCalendarShifts() {
    try {
        document.getElementById('shifts-container').innerHTML = '<div class="loading"><div class="spinner"></div><p>Loading shifts from all pantries...</p></div>';

        // Load shifts from all pantries and group by pantry
        const allShifts = {};

        if (!allPublicPantries || allPublicPantries.length === 0) {
            document.getElementById('shifts-container').innerHTML = '<p class="empty-state">No pantries available</p>';
            return;
        }

        for (const pantry of allPublicPantries) {
            try {
                const shifts = await getActiveShifts(pantry.pantry_id);

                if (shifts && shifts.length > 0) {
                    for (const shift of shifts) {
                        allShifts[pantry.pantry_id] = {
                            name: pantry.name,
                            location: pantry.location_address,
                            shifts: shifts && shifts.length > 0 ? shifts : []
                        };
                    }
                }

            } catch (err) {
                console.warn(`Failed to load shifts for pantry ${pantry.pantry_id}:`, err);
            }
        }

        displayAllShiftsGroupedByPantry(allShifts);
    } catch (error) {
        console.error('Failed to load shifts:', error);
        document.getElementById('shifts-container').innerHTML = `<p class="my-shift-load-error empty-state-compact">Error: ${escapeHtml(error.message)}</p>`;
    }
}

// Display all shifts grouped by pantry
function displayAllShiftsGroupedByPantry(allShifts) {
    console.log('All shifts grouped by pantry:', allShifts);
    const container = document.getElementById('shifts-container');
    container.classList.remove('loading');

    const pantryIds = Object.keys(allShifts);
    if (pantryIds.length === 0) {
        container.innerHTML = '<p class="empty-state">No pantries available</p>';
        return;
    }

    container.innerHTML = '';

    // Create sections for each pantry
    pantryIds.forEach(pantryId => {
        const pantryData = allShifts[pantryId];

        // Pantry section header
        const section = document.createElement('div');
        section.className = 'pantry-section';

        const header = document.createElement('div');
        header.className = 'pantry-section-header';
        header.innerHTML = `
                    <h3 class="pantry-section-title">${pantryData.name}</h3>
                    <p class="pantry-section-subtitle">${pantryData.location || 'No location listed'}</p>
                `;
        section.appendChild(header);

        // Shifts grid for this pantry
        const grid = document.createElement('div');
        grid.className = 'shifts-grid';

        if (pantryData.shifts && pantryData.shifts.length > 0) {
            pantryData.shifts.forEach(shift => {
                displayShiftCard(grid, shift);
            });
        } else {
            const noShifts = document.createElement('p');
            noShifts.className = 'empty-state';
            noShifts.textContent = 'No shifts scheduled yet';
            grid.appendChild(noShifts);
        }

        section.appendChild(grid);
        container.appendChild(section);
    });
}

// Display shifts as cards
function displayShiftsCards(shifts) {
    const container = document.getElementById('shifts-container');
    container.classList.remove('loading');

    if (!shifts || shifts.length === 0) {
        container.innerHTML = '<p class="empty-state">No shifts available yet</p>';
        return;
    }

    container.innerHTML = '';
    const grid = document.createElement('div');
    grid.className = 'shifts-grid';

    shifts.forEach(shift => {
        displayShiftCard(grid, shift);
    });

    container.appendChild(grid);
}

// Display a single shift card
function displayShiftCard(grid, shift) {
    const card = document.createElement('div');
    card.className = 'shift-card';

    const startDate = new Date(shift.start_time);
    const endDate = new Date(shift.end_time);

    let rolesHTML = '';
    // API returns roles in 'roles' field, not 'shift_roles'
    const shiftRoles = shift.roles || shift.shift_roles || [];

    if (shiftRoles && shiftRoles.length > 0) {
        rolesHTML = shiftRoles.map(role => {
            const filled = role.filled_count || 0;
            const required = role.required_count || 1;
            const percentage = (filled / required) * 100;
            const isFull = filled >= required;
            const shiftCancelled = String(shift.status || 'OPEN').toUpperCase() === 'CANCELLED';
            const roleCancelled = String(role.status || 'OPEN').toUpperCase() === 'CANCELLED';
            const isUnavailable = shiftCancelled || roleCancelled;
            const capacityClass = isFull ? 'capacity-full' : 'capacity-available';

            return `
                        <div class="role-item">
                            <div class="role-item-main">
                                <div class="role-name">${role.role_title}</div>
                                <div class="role-capacity ${capacityClass}">${filled}/${required} filled</div>
                                <div class="progress-bar">
                                    <div class="progress-fill" style="width: ${percentage}%"></div>
                                </div>
                            </div>
                            <div class="role-item-action">
                                ${isUnavailable
                    ? '<button class="btn btn-secondary" disabled>Unavailable</button>'
                    : isFull
                    ? '<button class="btn btn-secondary" disabled>Full</button>'
                    : `<button class="btn btn-success" onclick="signupForRole(${role.shift_role_id})">Sign Up</button>`
                }
                            </div>
                        </div>
                    `;
        }).join('');
    } else {
        rolesHTML = '<p class="empty-state empty-state-compact">No positions available</p>';
    }

    card.innerHTML = `
                <div class="shift-header">
                    <div>
                        <div class="shift-title">${shift.shift_name}</div>
                        <div class="shift-date">📅 ${escapeHtml(formatLocalTimeRange(startDate, endDate))}</div>
                    </div>
                </div>
                <div class="shift-roles">
                    ${rolesHTML}
                </div>
            `;

    grid.appendChild(card);
}

// Signup for role
async function signupForRole(roleId) {
    if (!currentUser || !currentUser.user_id) {
        showMessage('calendar', 'Signup failed: Missing current user context', 'error');
        return false;
    }

    try {
        await signupForShift(roleId, currentUser.user_id);
    } catch (error) {
        showMessage('calendar', `Signup failed: ${error.message}`, 'error');
        await loadCalendarShifts(); 
        return false;
    }

    try {

        const myShiftsTab = document.getElementById('content-my-shifts');
        const isVolunteer = currentUserHasRole('VOLUNTEER');
        if (isVolunteer && myShiftsTab && myShiftsTab.classList.contains('active')) {
            await loadMyRegisteredShifts();
        }
        showMessage('calendar', 'Successfully signed up!', 'success');
    } catch (error) {
        showMessage('calendar', `Signup completed, but refresh failed: ${error.message}`, 'error');
    }

    await loadCalendarShifts(); // Reload to show updated counts no matter the error or success
    return true;
}

function escapeHtml(value) {
    if (value === null || value === undefined) return '';
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function parseApiErrorDetails(error) {
    const raw = String(error && error.message ? error.message : '');
    const jsonStart = raw.indexOf('{');
    if (jsonStart === -1) return null;

    try {
        return JSON.parse(raw.slice(jsonStart));
    } catch (_err) {
        return null;
    }
}

function toStatusClass(prefix, status) {
    const normalized = String(status || 'unknown').toLowerCase().replace(/[^a-z0-9]+/g, '-');
    return `${prefix}-${normalized}`;
}

function safeDateValue(value) {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? null : date;
}

function sortByDate(a, b, field, direction = 'asc') {
    const aDate = safeDateValue(a[field]);
    const bDate = safeDateValue(b[field]);
    const aMs = aDate ? aDate.getTime() : Number.POSITIVE_INFINITY;
    const bMs = bDate ? bDate.getTime() : Number.POSITIVE_INFINITY;
    return direction === 'asc' ? aMs - bMs : bMs - aMs;
}

function classifyManagedShiftBucket(shift, now = new Date()) {
    const shiftStatus = String(shift.status || 'OPEN').toUpperCase();
    const start = safeDateValue(shift.start_time);
    const end = safeDateValue(shift.end_time);
    if (!start || !end) return 'past';

    // Cancelled shifts that already ended should be treated as past (locked),
    // not actionable cancelled shifts.
    if (shiftStatus === 'CANCELLED') {
        return end <= now ? 'past' : 'cancelled';
    }

    if (start > now) return 'incoming';
    if (start <= now && now < end) return 'ongoing';
    return 'past';
}

function getManagedShiftBuckets(shifts, now = new Date()) {
    const buckets = {
        incoming: [],
        ongoing: [],
        past: [],
        cancelled: [],
    };

    shifts.forEach((shift) => {
        const bucket = classifyManagedShiftBucket(shift, now);
        buckets[bucket].push(shift);
    });

    buckets.incoming.sort((a, b) => sortByDate(a, b, 'start_time', 'asc'));
    buckets.ongoing.sort((a, b) => sortByDate(a, b, 'end_time', 'asc'));
    buckets.past.sort((a, b) => sortByDate(a, b, 'end_time', 'desc'));
    buckets.cancelled.sort((a, b) => sortByDate(a, b, 'start_time', 'desc'));
    return buckets;
}

function setManageShiftsSubtab(target) {
    const normalized = target === 'view' ? 'view' : 'create';
    activeManageShiftsSubtab = normalized;

    document.querySelectorAll('.manage-shifts-subtab').forEach((btn) => {
        btn.classList.toggle('active', btn.dataset.manageSubtab === normalized);
    });

    const createContent = document.getElementById('manage-shifts-subcontent-create');
    const viewContent = document.getElementById('manage-shifts-subcontent-view');
    if (createContent) {
        createContent.classList.toggle('active', normalized === 'create');
    }
    if (viewContent) {
        viewContent.classList.toggle('active', normalized === 'view');
    }
}

function setAdminSubtab(target) {
    const normalized = target === 'users' ? 'users' : 'pantries';
    activeAdminSubtab = normalized;

    document.querySelectorAll('.admin-subtab').forEach((btn) => {
        btn.classList.toggle('active', btn.dataset.adminSubtab === normalized);
    });

    document.querySelectorAll('.admin-subcontent').forEach((section) => {
        section.classList.toggle('active', section.id === `admin-subcontent-${normalized}`);
    });
}

function formatAuthProviderLabel(value) {
    const normalized = String(value || '').trim();
    if (!normalized) {
        return 'Not linked';
    }
    return normalized.replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

async function ensureAdminRolesLoaded() {
    if (adminRoles.length > 0) {
        return adminRoles;
    }
    adminRoles = await getRoles();
    return adminRoles;
}

async function loadAdminTab() {
    if (activeAdminSubtab === 'users') {
        await loadAdminUsers();
        return;
    }
    await updatePantriesTable();
}

function isPhoneViewport() {
    return window.matchMedia('(max-width: 767px)').matches;
}

function renderAdminUserRoleChips(roles) {
    if (!Array.isArray(roles) || !roles.length) {
        return '<div class="table-user-secondary compact">No roles</div>';
    }

    return `
        <div class="admin-user-chip-list">
            ${roles.map((role) => `<span class="admin-user-chip">${escapeHtml(role)}</span>`).join('')}
        </div>
    `;
}

function renderAdminInlineProfile(userId) {
    if (selectedAdminUserProfileError) {
        return `
            <tr class="admin-user-inline-row">
                <td colspan="5" class="admin-user-inline-cell">
                    <p class="my-shift-load-error">Failed to load user profile: ${escapeHtml(selectedAdminUserProfileError)}</p>
                </td>
            </tr>
        `;
    }

    if (!selectedAdminUserProfile || selectedAdminUserProfile.user_id !== userId) {
        return `
            <tr class="admin-user-inline-row">
                <td colspan="5" class="admin-user-inline-cell">
                    <div class="loading">
                        <div class="spinner"></div>
                        <p>Loading user profile...</p>
                    </div>
                </td>
            </tr>
        `;
    }

    return `
        <tr class="admin-user-inline-row">
            <td colspan="5" class="admin-user-inline-cell">
                <div data-admin-inline-profile="${userId}">
                    ${buildAdminUserProfileMarkup(selectedAdminUserProfile, { inline: true })}
                </div>
            </td>
        </tr>
    `;
}

function renderAdminUserTable() {
    const tbody = document.getElementById('admin-users-table-body');
    if (!tbody) {
        return;
    }

    if (!adminUsers.length) {
        tbody.innerHTML = '<tr><td colspan="5" class="table-empty-cell">No users found.</td></tr>';
        return;
    }

    const phoneView = isPhoneViewport();
    tbody.innerHTML = adminUsers.map((user) => {
        const isSelected = selectedAdminUserId === user.user_id;
        const phoneText = formatAccountValue(user.phone_number, 'No phone');
        const authText = formatAuthProviderLabel(user.auth_provider);
        const viewLabel = phoneView && isSelected ? 'Hide' : 'View';
        return `
            <tr class="admin-user-row ${isSelected ? 'selected' : ''}" data-admin-user-row="${user.user_id}">
                <td data-label="User">
                    <div class="table-user-primary">${escapeHtml(formatAccountValue(user.full_name))}</div>
                    <div class="table-user-secondary">Joined ${escapeHtml(formatAccountTimestamp(user.created_at))}</div>
                </td>
                <td data-label="Contact">
                    <div class="table-user-primary">${escapeHtml(formatAccountValue(user.email))}</div>
                    <div class="table-user-secondary">${escapeHtml(phoneText)}</div>
                </td>
                <td data-label="Access">
                    ${renderAdminUserRoleChips(user.roles)}
                    <div class="table-user-secondary">${escapeHtml(authText)}</div>
                </td>
                <td data-label="Score">${escapeHtml(String(Number(user.attendance_score || 0)))}%</td>
                <td data-label="Open"><button type="button" class="btn btn-secondary btn-sm" data-open-admin-user="${user.user_id}">${viewLabel}</button></td>
            </tr>
            ${phoneView && isSelected ? renderAdminInlineProfile(user.user_id) : ''}
        `;
    }).join('');

    if (!phoneView) {
        tbody.querySelectorAll('[data-admin-user-row]').forEach((row) => {
            row.addEventListener('click', async (event) => {
                if (event.target.closest('[data-open-admin-user]')) {
                    return;
                }
                await openAdminUserProfile(Number(row.dataset.adminUserRow));
            });
        });
    }

    tbody.querySelectorAll('[data-open-admin-user]').forEach((button) => {
        button.addEventListener('click', async () => {
            await openAdminUserProfile(Number(button.dataset.openAdminUser));
        });
    });

    if (phoneView && selectedAdminUserProfile && selectedAdminUserProfile.user_id === selectedAdminUserId) {
        const inlineContainer = tbody.querySelector(`[data-admin-inline-profile="${selectedAdminUserProfile.user_id}"]`);
        if (inlineContainer) {
            bindAdminUserProfileInteractions(inlineContainer, selectedAdminUserProfile);
        }
    }
}

function renderAdminRoleOptions(userProfile, inputName = 'admin-user-role') {
    const editableRoles = adminRoles.filter((role) => role.role_name !== 'SUPER_ADMIN');
    const selectedRole = Array.isArray(userProfile.roles) && userProfile.roles.length ? userProfile.roles[0] : '';
    return editableRoles.map((role) => `
        <label class="admin-role-option ${selectedRole === role.role_name ? 'selected' : ''}">
            <input
                type="radio"
                name="${inputName}"
                value="${role.role_id}"
                ${selectedRole === role.role_name ? 'checked' : ''}
            >
            <span>${escapeHtml(role.role_name)}</span>
        </label>
    `).join('');
}

function buildAdminUserProfileMarkup(userProfile, options = {}) {
    const inline = Boolean(options.inline);
    const rolesText = Array.isArray(userProfile.roles) && userProfile.roles.length ? userProfile.roles.join(', ') : 'No roles';
    const isProtectedSuperAdmin = userProfile.user_id === 1 || (Array.isArray(userProfile.roles) && userProfile.roles.includes('SUPER_ADMIN'));
    const canEditRoles = !isProtectedSuperAdmin;
    const inputName = `admin-user-role-${userProfile.user_id}`;
    const roleNote = isProtectedSuperAdmin
        ? '<div class="account-note memory-note">This protected super admin account is read-only. Its roles cannot be changed or removed.</div>'
        : '<div class="account-note">Update the selected user roles below. SUPER_ADMIN is intentionally excluded from editable controls.</div>';

    return `
        <div class="admin-user-profile ${inline ? 'admin-user-profile-inline' : ''}">
            <div class="account-summary-grid admin-user-summary-grid">
                ${renderAccountSummaryItem('Full Name', formatAccountValue(userProfile.full_name))}
                ${renderAccountSummaryItem('Email', formatAccountValue(userProfile.email))}
                ${renderAccountSummaryItem('Phone Number', formatAccountValue(userProfile.phone_number))}
                ${renderAccountSummaryItem('Roles', rolesText)}
                ${renderAccountSummaryItem('Attendance Score', `${Number(userProfile.attendance_score || 0)}%`)}
                ${renderAccountSummaryItem('Auth Provider', formatAuthProviderLabel(userProfile.auth_provider))}
                ${renderAccountSummaryItem('Auth UID', formatAccountValue(userProfile.auth_uid))}
                ${renderAccountSummaryItem('Created At', formatAccountTimestamp(userProfile.created_at))}
                ${renderAccountSummaryItem('Updated At', formatAccountTimestamp(userProfile.updated_at))}
            </div>
            <div class="admin-user-role-editor">
                <h3 class="admin-user-role-title">Roles</h3>
                ${roleNote}
                <form data-admin-user-role-form="${userProfile.user_id}">
                    <div class="admin-role-options">
                        ${renderAdminRoleOptions(userProfile, inputName)}
                    </div>
                    <div class="admin-user-role-actions">
                        <button type="submit" class="btn btn-primary" ${canEditRoles ? '' : 'disabled'}>Save Roles</button>
                    </div>
                </form>
            </div>
        </div>
    `;
}

function bindAdminUserProfileInteractions(container, userProfile) {
    const isProtectedSuperAdmin = userProfile.user_id === 1 || (Array.isArray(userProfile.roles) && userProfile.roles.includes('SUPER_ADMIN'));
    const canEditRoles = !isProtectedSuperAdmin;
    const inputName = `admin-user-role-${userProfile.user_id}`;
    const roleForm = container.querySelector(`[data-admin-user-role-form="${userProfile.user_id}"]`);

    roleForm?.querySelectorAll(`input[name="${inputName}"]`).forEach((input) => {
        input.addEventListener('change', () => {
            roleForm.querySelectorAll('.admin-role-option').forEach((option) => {
                option.classList.toggle('selected', option.contains(input) && input.checked);
            });
        });
    });
    roleForm?.addEventListener('submit', async (event) => {
        event.preventDefault();

        if (!canEditRoles) {
            showMessage('admin-users', 'The protected super admin account cannot be edited.', 'error');
            return;
        }

        const selectedRoleInput = roleForm.querySelector(`input[name="${inputName}"]:checked`);
        if (!selectedRoleInput) {
            showMessage('admin-users', 'Select one role before saving.', 'error');
            return;
        }

        const selectedRoleIds = [Number(selectedRoleInput.value)];
        const editingSelf = currentUser && currentUser.user_id === userProfile.user_id;

        try {
            const updatedProfile = await updateUserRoles(userProfile.user_id, selectedRoleIds);
            showMessage('admin-users', 'User roles updated successfully.', 'success');
            await refreshCurrentUserState();
            if (editingSelf) {
                await loadPantries();
                if (!currentUserIsAdminCapable()) {
                    await activateTab(setupRoleBasedUI());
                    return;
                }
            }
            await loadAdminUsers({ preserveSelection: true, preferredUserId: updatedProfile.user_id });
        } catch (error) {
            showMessage('admin-users', `Failed to update roles: ${error.message}`, 'error');
        }
    });
}

function renderAdminUserProfile(userProfile) {
    const panel = document.getElementById('admin-user-profile-panel');
    if (!panel) {
        return;
    }

    panel.innerHTML = buildAdminUserProfileMarkup(userProfile);
    bindAdminUserProfileInteractions(panel, userProfile);
}

async function openAdminUserProfile(userId, options = {}) {
    const force = Boolean(options.force);
    if (isPhoneViewport() && !force && selectedAdminUserId === userId) {
        selectedAdminUserId = null;
        selectedAdminUserProfile = null;
        selectedAdminUserProfileError = '';
        renderAdminUserTable();
        return;
    }

    selectedAdminUserId = userId;
    selectedAdminUserProfile = null;
    selectedAdminUserProfileError = '';
    renderAdminUserTable();

    const panel = document.getElementById('admin-user-profile-panel');
    if (!isPhoneViewport() && panel) {
        panel.innerHTML = '<div class="loading"><div class="spinner"></div><p>Loading user profile...</p></div>';
    }

    try {
        const profile = await getUserProfile(userId);
        if (selectedAdminUserId !== userId) {
            return;
        }
        selectedAdminUserProfile = profile;
        if (isPhoneViewport()) {
            renderAdminUserTable();
            return;
        }
        renderAdminUserProfile(profile);
    } catch (error) {
        if (selectedAdminUserId !== userId) {
            return;
        }
        selectedAdminUserProfileError = error.message;
        if (isPhoneViewport()) {
            renderAdminUserTable();
        } else if (panel) {
            panel.innerHTML = `<p class="my-shift-load-error">Failed to load user profile: ${escapeHtml(error.message)}</p>`;
        }
        showMessage('admin-users', `Failed to load user profile: ${error.message}`, 'error');
    }
}

async function loadAdminUsers(options = {}) {
    const preserveSelection = Boolean(options.preserveSelection);
    const preferredUserId = options.preferredUserId || null;
    const searchInput = document.getElementById('admin-user-search');
    const roleFilterSelect = document.getElementById('admin-user-role-filter');
    const panel = document.getElementById('admin-user-profile-panel');

    try {
        await ensureAdminRolesLoaded();

        if (roleFilterSelect && !roleFilterSelect.dataset.initialized) {
            roleFilterSelect.innerHTML = '<option value="">All roles</option>';
            adminRoles.forEach((role) => {
                const option = document.createElement('option');
                option.value = role.role_name;
                option.textContent = role.role_name;
                roleFilterSelect.appendChild(option);
            });
            roleFilterSelect.dataset.initialized = 'true';
        }

        const roleFilter = roleFilterSelect ? roleFilterSelect.value : '';
        const searchQuery = searchInput ? searchInput.value.trim() : '';
        adminUsers = await getAllUsers(roleFilter || null, searchQuery);

        if (!preserveSelection) {
            selectedAdminUserId = null;
            selectedAdminUserProfile = null;
            selectedAdminUserProfileError = '';
        }

        if (preferredUserId) {
            selectedAdminUserId = preferredUserId;
        } else if (selectedAdminUserId && !adminUsers.some((user) => user.user_id === selectedAdminUserId)) {
            selectedAdminUserId = null;
            selectedAdminUserProfile = null;
            selectedAdminUserProfileError = '';
        }

        renderAdminUserTable();

        if (selectedAdminUserId) {
            await openAdminUserProfile(selectedAdminUserId, { force: true });
        } else if (panel) {
            panel.innerHTML = '<p class="auth-empty">Select a user to view the full profile and manage roles.</p>';
        }
    } catch (error) {
        if (panel) {
            panel.innerHTML = `<p class="my-shift-load-error">Failed to load users: ${escapeHtml(error.message)}</p>`;
        }
        showMessage('admin-users', `Failed to load users: ${error.message}`, 'error');
    }
}

function handleAdminUsersViewportChange() {
    const phoneView = isPhoneViewport();
    if (lastAdminUsersPhoneViewport === phoneView) {
        return;
    }

    lastAdminUsersPhoneViewport = phoneView;
    renderAdminUserTable();

    if (!selectedAdminUserId) {
        return;
    }

    if (phoneView) {
        return;
    }

    if (selectedAdminUserProfile) {
        renderAdminUserProfile(selectedAdminUserProfile);
        return;
    }

    openAdminUserProfile(selectedAdminUserId, { force: true });
}

function formatShiftRange(startTime, endTime) {
    return formatLocalTimeRange(startTime, endTime);
}

function getAttendanceInfo(signupStatus) {
    const normalized = String(signupStatus || '').toUpperCase();
    if (normalized === 'SHOW_UP') {
        return { label: 'Attended', className: 'attendance-badge-attended', isMarked: true };
    }
    if (normalized === 'NO_SHOW') {
        return { label: 'Missed', className: 'attendance-badge-missed', isMarked: true };
    }
    return { label: 'Pending Attendance', className: 'attendance-badge-pending', isMarked: false };
}

function getAttendanceWindowInfo(startTime, endTime, now = new Date()) {
    // TODO(dev): Re-enable client-side attendance window UX before production.
    // Server-side checks are currently disabled for dev, so keep UI unrestricted too.
    return { canMark: true, message: 'Attendance window is open (dev mode).' };

    /*
    const start = safeDateValue(startTime);
    const end = safeDateValue(endTime);
    if (!start || !end) {
        return { canMark: false, message: 'Attendance window unavailable for this shift.' };
    }

    const openAt = new Date(start.getTime() - 15 * 60 * 1000);
    const closeAt = new Date(end.getTime() + 6 * 60 * 60 * 1000);
    if (now < openAt) {
        return { canMark: false, message: 'Attendance opens 15 minutes before shift start.' };
    }
    if (now > closeAt) {
        return { canMark: false, message: 'Attendance window is closed (6 hours after shift end).' };
    }
    return { canMark: true, message: 'Attendance window is open.' };
    */
}

function renderCredibilitySummary(attendanceScore) {
    const normalizedScore = Number.isFinite(Number(attendanceScore))
        ? Math.max(0, Math.min(100, Math.round(Number(attendanceScore))))
        : null;

    if (normalizedScore === null) {
        return `
            <section class="credibility-summary">
                <h3 class="credibility-title">Credibility</h3>
                <p class="credibility-value">N/A</p>
                <p class="credibility-detail">Attendance score unavailable.</p>
            </section>
        `;
    }

    return `
        <section class="credibility-summary">
            <h3 class="credibility-title">Credibility</h3>
            <p class="credibility-value">${normalizedScore}%</p>
            <p class="credibility-detail">Based on marked attendance records.</p>
        </section>
    `;
}

function formatAccountValue(value, fallback = '—') {
    if (value === null || value === undefined || value === '') {
        return fallback;
    }
    return String(value);
}

function formatAccountTimestamp(value) {
    return formatLocalDateTime(value) || '—';
}

function renderAccountSummaryItem(label, value) {
    return `
        <div class="account-summary-item">
            <span class="account-summary-label">${escapeHtml(label)}</span>
            <div class="account-summary-value">${escapeHtml(value)}</div>
        </div>
    `;
}

function updateAccountEmailUi() {
    const note = document.getElementById('my-account-email-note');
    const submitButton = document.getElementById('account-email-submit-btn');
    const newEmailInput = document.getElementById('account-new-email');
    const currentEmailInput = document.getElementById('account-current-email');

    if (!note || !submitButton || !newEmailInput || !currentEmailInput || !currentUser) {
        return;
    }

    currentEmailInput.value = currentUser.email || '';

    if (currentUser.email_change_supported) {
        note.className = 'account-note firebase-note';
        note.innerHTML = 'We will ask you to confirm with Google of <b>the current email</b>, send a verification link to the new email, then update the app after your next sign-in.';
        submitButton.disabled = false;
        newEmailInput.disabled = false;
    } else {
        note.className = 'account-note memory-note';
        note.textContent = currentUser.auth_mode === 'firebase'
            ? 'This account is not linked to Firebase yet. Sign out and sign in again with Google before changing email.'
            : 'Demo auth allows editing name and phone number only. Email changes are not available in memory mode.';
        submitButton.disabled = true;
        newEmailInput.disabled = true;
    }
}

function updateDeleteAccountUi() {
    const deleteButton = document.getElementById('delete-account-btn');
    const deleteNote = document.querySelector('.delete-account-note');
    if (!deleteButton || !deleteNote || !currentUser) {
        return;
    }

    const isProtectedSuperAdmin = currentUser.user_id === 1 || currentUserHasRole('SUPER_ADMIN');
    if (isProtectedSuperAdmin) {
        deleteButton.disabled = true;
        deleteNote.textContent = 'The protected super admin account cannot delete itself.';
        return;
    }

    deleteButton.disabled = false;
    deleteNote.textContent = 'Deleting your account removes your local app user, signs you out, and in Firebase mode also deletes the linked Firebase account after a fresh Google reauthentication.';
}

function renderMyAccountSummary() {
    const container = document.getElementById('my-account-summary');
    if (!container || !currentUser) {
        return;
    }

    const rolesText = Array.isArray(currentUser.roles) && currentUser.roles.length > 0
        ? currentUser.roles.join(', ')
        : 'No roles';

    container.innerHTML = `
        ${renderAccountSummaryItem('Full Name', formatAccountValue(currentUser.full_name))}
        ${renderAccountSummaryItem('Email', formatAccountValue(currentUser.email))}
        ${renderAccountSummaryItem('Phone Number', formatAccountValue(currentUser.phone_number))}
        ${renderAccountSummaryItem('Saved Timezone', formatTimeZoneDisplay(currentUser.timezone || DEFAULT_APP_TIMEZONE))}
        ${renderAccountSummaryItem('Roles', rolesText)}
        ${renderAccountSummaryItem('Attendance Score', `${Number(currentUser.attendance_score || 0)}%`)}
        ${renderAccountSummaryItem('Created At', formatAccountTimestamp(currentUser.created_at))}
        ${renderAccountSummaryItem('Updated At', formatAccountTimestamp(currentUser.updated_at))}
    `;

    const timezoneNote = document.getElementById('my-account-timezone-note');
    if (timezoneNote) {
        timezoneNote.textContent = `Times on the web are shown in your browser timezone: ${formatTimeZoneDisplay()}.`;
    }
}

function syncMyAccountForms() {
    if (!currentUser) {
        return;
    }

    const fullNameInput = document.getElementById('account-full-name');
    const phoneInput = document.getElementById('account-phone-number');
    const newEmailInput = document.getElementById('account-new-email');

    if (fullNameInput) {
        fullNameInput.value = currentUser.full_name || '';
    }
    if (phoneInput) {
        phoneInput.value = currentUser.phone_number || '';
    }
    if (newEmailInput) {
        newEmailInput.value = '';
    }

    updateAccountEmailUi();
    updateDeleteAccountUi();
}

async function refreshCurrentUserState() {
    currentUser = await getCurrentUser();
    document.getElementById('user-email').textContent = currentUser.email;
    document.getElementById('user-role').textContent = currentUser.roles.join(', ');
    setupRoleBasedUI();
    renderMyAccountSummary();
    syncMyAccountForms();
}

async function loadMyAccount() {
    if (!currentUser) {
        return;
    }
    renderMyAccountSummary();
    syncMyAccountForms();
}

function renderMyShiftCard(signup, now) {
    const signupStatus = String(signup.signup_status || 'UNKNOWN').toUpperCase();
    const shiftStatus = String(signup.shift_status || 'OPEN').toUpperCase();
    const attendanceInfo = getAttendanceInfo(signupStatus);
    const showCancelByTime = canCancelSignup(signup, now);
    const nonActionableStatuses = new Set(['CANCELLED', 'WAITLISTED']);
    const showCancel = showCancelByTime
        && !nonActionableStatuses.has(signupStatus)
        && shiftStatus !== 'CANCELLED';
    const showSignupStatusBadge = !attendanceInfo.isMarked;
    const isPendingReconfirm = signupStatus === 'PENDING_CONFIRMATION';
    const reconfirmAvailable = Boolean(signup.reconfirm_available);

    let actionsHtml = '';
    if (isPendingReconfirm) {
        actionsHtml = `
            <div class="my-shift-actions">
                ${reconfirmAvailable
                ? `<button class="btn btn-success btn-compact" onclick="reconfirmMySignup(${signup.signup_id}, 'CONFIRM')">Confirm</button>`
                : `<span class="reconfirm-note">Role is full or unavailable for reconfirmation.</span>`
            }
                <button class="btn btn-danger btn-compact" onclick="reconfirmMySignup(${signup.signup_id}, 'CANCEL')">Cancel</button>
            </div>
        `;
    } else if (showCancel) {
        actionsHtml = `
            <div class="my-shift-actions">
                <button class="btn btn-danger btn-compact" onclick="cancelMySignup(${signup.signup_id})">Cancel Signup</button>
            </div>
        `;
    }

    return `
        <article class="my-shift-card">
            <div class="my-shift-card-header">
                <div>
                    <h4 class="my-shift-title">${escapeHtml(signup.shift_name || 'Untitled Shift')}</h4>
                    <p class="my-shift-role">Role: ${escapeHtml(signup.role_title || 'Unassigned')}</p>
                </div>
                <div class="my-shift-badges">
                    <span class="status-badge attendance-badge ${attendanceInfo.className}">${escapeHtml(attendanceInfo.label)}</span>
                    ${showSignupStatusBadge
            ? `<span class="status-badge ${toStatusClass('signup-status', signupStatus)}">${escapeHtml(signupStatus)}</span>`
            : ''
        }
                    <span class="status-badge ${toStatusClass('shift-status', shiftStatus)}">${escapeHtml(shiftStatus)}</span>
                </div>
            </div>
            <div class="my-shift-meta">
                <p><strong>When:</strong> ${escapeHtml(formatShiftRange(signup.start_time, signup.end_time))}</p>
                <p><strong>Pantry:</strong> ${escapeHtml(signup.pantry_name || 'Unknown Pantry')}</p>
                <p><strong>Location:</strong> ${escapeHtml(signup.pantry_location || 'No location listed')}</p>
            </div>
            ${actionsHtml}
        </article>
    `;
}

function renderMyShiftSection(sectionId, title, signups, now) {
    if (!signups || signups.length === 0) {
        return `
            <section class="my-shift-section" id="my-shift-section-${sectionId}">
                <h3 class="my-shift-section-title">${title}</h3>
                <p class="my-shift-empty">No ${title.toLowerCase()}.</p>
            </section>
        `;
    }

    return `
        <section class="my-shift-section" id="my-shift-section-${sectionId}">
            <h3 class="my-shift-section-title">${title}</h3>
            <div class="my-shifts-grid">
                ${signups.map(signup => renderMyShiftCard(signup, now)).join('')}
            </div>
        </section>
    `;
}

async function loadMyRegisteredShifts() {
    const container = document.getElementById('my-shifts-container');
    if (!container || !currentUser) return;

    container.innerHTML = '<div class="loading"><div class="spinner"></div><p>Loading your registered shifts...</p></div>';

    try {
        const signups = await getUserSignups(currentUser.user_id);
        const now = new Date();
        container.classList.remove('loading');

        if (!signups || signups.length === 0) {
            container.innerHTML = `
                ${renderCredibilitySummary(currentUser.attendance_score)}
                <p class="my-shift-empty-all">You have no registered shifts yet.</p>
            `;
            return;
        }

        const buckets = {
            incoming: [],
            ongoing: [],
            past: [],
        };

        signups.forEach(signup => {
            const bucket = classifyShiftBucket(signup, now);
            buckets[bucket].push(signup);
        });

        buckets.incoming.sort((a, b) => sortByDate(a, b, 'start_time', 'asc'));
        buckets.ongoing.sort((a, b) => sortByDate(a, b, 'end_time', 'asc'));
        buckets.past.sort((a, b) => sortByDate(a, b, 'end_time', 'desc'));

        container.innerHTML = `
            <div class="my-shifts-sections">
                ${renderCredibilitySummary(currentUser.attendance_score)}
                ${renderMyShiftSection('incoming', 'Incoming Shifts', buckets.incoming, now)}
                ${renderMyShiftSection('ongoing', 'Ongoing Shifts', buckets.ongoing, now)}
                ${renderMyShiftSection('past', 'Past Shifts', buckets.past, now)}
            </div>
        `;
    } catch (error) {
        console.error('Failed to load my shifts:', error);
        container.innerHTML = `<p class="my-shift-load-error">Failed to load your registered shifts: ${escapeHtml(error.message)}</p>`;
        showMessage('my-shifts', `Failed to load shifts: ${error.message}`, 'error');
    }
}

async function cancelMySignup(signupId) {
    if (!confirm('Cancel this signup?')) return;

    try {
        await cancelSignup(signupId);
        showMessage('my-shifts', 'Signup cancelled successfully!', 'success');
        await Promise.all([loadMyRegisteredShifts(), loadCalendarShifts()]);
    } catch (error) {
        showMessage('my-shifts', `Cancel failed: ${error.message}`, 'error');
    }
}

async function reconfirmMySignup(signupId, action) {
    const normalizedAction = String(action || '').toUpperCase();
    const actionLabel = normalizedAction === 'CONFIRM' ? 'confirm this updated shift' : 'cancel this updated shift signup';
    if (!confirm(`Do you want to ${actionLabel}?`)) return;

    try {
        await reconfirmSignup(signupId, normalizedAction);
        showMessage('my-shifts', normalizedAction === 'CONFIRM' ? 'Shift reconfirmed successfully!' : 'Signup cancelled successfully!', 'success');
        await Promise.all([loadMyRegisteredShifts(), loadCalendarShifts()]);
    } catch (error) {
        const details = parseApiErrorDetails(error);
        if (details && details.code === 'ROLE_FULL_OR_UNAVAILABLE') {
            showMessage('my-shifts', 'This role is full or unavailable. Please cancel or pick another shift.', 'error');
        } else if (details && details.code === 'RESERVATION_EXPIRED') {
            showMessage('my-shifts', 'Your reservation expired. Please sign up again if slots are available.', 'error');
        } else {
            showMessage('my-shifts', `Action failed: ${error.message}`, 'error');
        }
        await loadMyRegisteredShifts();
    }
}

async function markSignupAttendance(signupId, attendanceStatus, shiftId) {
    try {
        await markAttendance(signupId, attendanceStatus);
        showMessage('shifts', 'Attendance updated successfully!', 'success');

        if (typeof shiftId === 'number') {
            delete registrationsCache[shiftId];
        }

        if (expandedShiftContext && expandedShiftContext.shiftId === shiftId) {
            const activeTbody = document.getElementById(expandedShiftContext.tbodyId);
            const detailsRow = activeTbody
                ? activeTbody.querySelector(`.shift-registrations-row[data-shift-id="${shiftId}"]`)
                : null;
            if (detailsRow) {
                const refreshedRegistrations = await getShiftRegistrations(shiftId);
                registrationsCache[shiftId] = refreshedRegistrations;
                detailsRow.innerHTML = `<td colspan="4">${renderRegistrationsRowContent(refreshedRegistrations)}</td>`;
            }
        }

        const myShiftsTab = document.getElementById('content-my-shifts');
        if (myShiftsTab && myShiftsTab.classList.contains('active')) {
            await loadMyRegisteredShifts();
        }
    } catch (error) {
        showMessage('shifts', `Attendance update failed: ${error.message}`, 'error');
    }
}

function renderRegistrationsRowContent(shiftRegistrations) {
    const roles = shiftRegistrations.roles || [];
    const windowInfo = getAttendanceWindowInfo(shiftRegistrations.start_time, shiftRegistrations.end_time);
    const canMarkAttendance = currentUser && (currentUserIsAdminCapable() || currentUserHasRole('PANTRY_LEAD'));

    if (roles.length === 0) {
        return `
            <div class="shift-registrations">
                <h4 class="registrations-title">Registrations by Role</h4>
                <p class="registrations-empty">No roles configured for this shift.</p>
            </div>
        `;
    }

    const roleBlocks = roles.map(role => {
        const required = role.required_count || 0;
        const filled = role.filled_count || 0;
        const signups = role.signups || [];
        const pendingReconfirmCount = Number(role.pending_reconfirm_count || 0);

        const signupsHtml = signups.length > 0
            ? `
                <ul class="registrant-list">
                    ${signups.map(signup => {
                const user = signup.user || {};
                const userName = escapeHtml(user.full_name || 'Unknown volunteer');
                const userEmail = escapeHtml(user.email || 'No email');
                const attendanceInfo = getAttendanceInfo(signup.signup_status);
                const disabledAttr = windowInfo.canMark ? '' : 'disabled';
                const disabledReason = escapeHtml(windowInfo.message);
                const attendanceActions = canMarkAttendance
                    ? `
                        <div class="registrant-actions">
                            <button
                                class="btn btn-secondary btn-compact btn-attendance btn-attendance-showup"
                                onclick="markSignupAttendance(${signup.signup_id}, 'SHOW_UP', ${shiftRegistrations.shift_id})"
                                ${disabledAttr}
                                title="${disabledReason}"
                            >
                                Mark Show Up
                            </button>
                            <button
                                class="btn btn-secondary btn-compact btn-attendance btn-attendance-noshow"
                                onclick="markSignupAttendance(${signup.signup_id}, 'NO_SHOW', ${shiftRegistrations.shift_id})"
                                ${disabledAttr}
                                title="${disabledReason}"
                            >
                                Mark No Show
                            </button>
                        </div>
                    `
                    : '';

                return `
                            <li class="registrant-item">
                                <div class="registrant-main">
                                    <div class="registrant-name">${userName}</div>
                                    <div class="registrant-email">${userEmail}</div>
                                </div>
                                <div class="registrant-right">
                                    <span class="registrant-status ${attendanceInfo.className}">${escapeHtml(attendanceInfo.label)}</span>
                                    ${attendanceActions}
                                </div>
                            </li>
                        `;
            }).join('')}
                </ul>
            `
            : '<p class="registrations-empty">No volunteers registered yet.</p>';

        return `
            <div class="registration-role">
                <div class="registration-role-header">
                    <div class="registration-role-title">${escapeHtml(role.role_title || 'Untitled Role')}</div>
                    <div class="registration-role-capacity">${filled}/${required} reserved</div>
                </div>
                ${pendingReconfirmCount > 0
                    ? `<p class="reconfirm-note">${pendingReconfirmCount} volunteer(s) pending reconfirmation.</p>`
                    : ''
                }
                ${signupsHtml}
            </div>
        `;
    }).join('');

    return `
        <div class="shift-registrations">
            <h4 class="registrations-title">Registrations by Role</h4>
            ${canMarkAttendance ? `<p class="attendance-window-note ${windowInfo.canMark ? 'attendance-window-open' : 'attendance-window-closed'}">${escapeHtml(windowInfo.message)}</p>` : ''}
            <div class="registration-role-grid">
                ${roleBlocks}
            </div>
        </div>
    `;
}

async function toggleShiftRegistrations(shiftId, buttonEl) {
    const tbody = buttonEl ? buttonEl.closest('tbody') : null;
    if (!tbody) return;
    const tbodyId = tbody.id;

    const targetRow = tbody.querySelector(`tr[data-shift-id="${shiftId}"]`);
    if (!targetRow) return;

    const isTogglingSameShift = expandedShiftContext
        && expandedShiftContext.shiftId === shiftId
        && expandedShiftContext.tbodyId === tbodyId;

    if (expandedShiftContext) {
        const previousTbody = document.getElementById(expandedShiftContext.tbodyId);
        if (previousTbody) {
            const previousDetailsRow = previousTbody.querySelector(`.shift-registrations-row[data-shift-id="${expandedShiftContext.shiftId}"]`);
            if (previousDetailsRow) {
                previousDetailsRow.remove();
            }

            const previousButton = previousTbody.querySelector(`button[data-registrations-btn="${expandedShiftContext.shiftId}"]`);
            if (previousButton) {
                previousButton.textContent = 'View Registrations';
            }
        }
    }

    if (isTogglingSameShift) {
        expandedShiftContext = null;
        return;
    }

    expandedShiftContext = {
        shiftId,
        tbodyId,
    };
    if (buttonEl) {
        buttonEl.textContent = 'Hide Registrations';
    }

    const detailsRow = document.createElement('tr');
    detailsRow.className = 'shift-registrations-row';
    detailsRow.dataset.shiftId = String(shiftId);
    detailsRow.innerHTML = `
        <td colspan="4">
            <div class="shift-registrations shift-registrations-loading">Loading registrations...</div>
        </td>
    `;
    targetRow.insertAdjacentElement('afterend', detailsRow);

    try {
        if (!registrationsCache[shiftId]) {
            registrationsCache[shiftId] = await getShiftRegistrations(shiftId);
        }

        if (!expandedShiftContext || expandedShiftContext.shiftId !== shiftId || expandedShiftContext.tbodyId !== tbodyId) return;
        detailsRow.innerHTML = `<td colspan="4">${renderRegistrationsRowContent(registrationsCache[shiftId])}</td>`;
    } catch (error) {
        console.error('Failed to load registrations:', error);
        if (!expandedShiftContext || expandedShiftContext.shiftId !== shiftId || expandedShiftContext.tbodyId !== tbodyId) return;

        detailsRow.innerHTML = `
            <td colspan="4">
                <div class="shift-registrations">
                    <p class="registrations-error">Failed to load registrations: ${escapeHtml(error.message || 'Unknown error')}</p>
                </div>
            </td>
        `;
        showMessage('shifts', `Failed to load registrations: ${error.message}`, 'error');
    }
}

function collapseExpandedRegistrations() {
    if (!expandedShiftContext) return;

    const previousTbody = document.getElementById(expandedShiftContext.tbodyId);
    if (previousTbody) {
        const previousDetailsRow = previousTbody.querySelector(`.shift-registrations-row[data-shift-id="${expandedShiftContext.shiftId}"]`);
        if (previousDetailsRow) {
            previousDetailsRow.remove();
        }

        const previousButton = previousTbody.querySelector(`button[data-registrations-btn="${expandedShiftContext.shiftId}"]`);
        if (previousButton) {
            previousButton.textContent = 'View Registrations';
        }
    }

    expandedShiftContext = null;
}

function setShiftBucketEmptyState(tbody, text) {
    if (!tbody) return;
    tbody.innerHTML = `<tr><td colspan="4" class="table-empty-cell">${escapeHtml(text)}</td></tr>`;
}

function renderShiftBucketRows(tbody, shifts, emptyText, bucketKey) {
    if (!tbody) return;
    tbody.innerHTML = '';
    const isPastBucket = bucketKey === 'past';

    if (!shifts || shifts.length === 0) {
        setShiftBucketEmptyState(tbody, emptyText);
        return;
    }

    shifts.forEach((shift) => {
        const startDate = safeDateValue(shift.start_time);
        const endDate = safeDateValue(shift.end_time);
        const timeText = startDate && endDate
            ? formatLocalTimeRange(startDate, endDate)
            : 'Time unavailable';
        const rolesText = shift.roles && shift.roles.length > 0
            ? shift.roles.map((role) => `${escapeHtml(role.role_title || 'Untitled Role')} (${role.filled_count || 0}/${role.required_count || 0})`).join(', ')
            : 'No roles';
        const shiftStatus = String(shift.status || 'OPEN').toUpperCase();
        const lockHint = 'Past shifts are locked';
        const registrationsButton = `<button
                        class="btn btn-secondary btn-sm"
                        data-registrations-btn="${shift.shift_id}"
                        onclick="toggleShiftRegistrations(${shift.shift_id}, this)"
                    >
                        View Registrations
                    </button>`;
        const editButton = isPastBucket
            ? `<button class="btn btn-primary btn-sm" disabled title="${lockHint}">Edit</button>`
            : `<button class="btn btn-primary btn-sm" onclick="openEditShift(${shift.shift_id})">Edit</button>`;
        let actionButton = '';
        if (isPastBucket) {
            actionButton = `<button class="btn btn-secondary btn-sm" disabled title="${lockHint}">Locked</button>`;
        } else if (shiftStatus === 'CANCELLED') {
            actionButton = `<button class="btn btn-success btn-sm" onclick="revokeShiftConfirm(${shift.shift_id})">Revoke</button>`;
        } else {
            actionButton = `<button class="btn btn-danger btn-sm" onclick="cancelShiftConfirm(${shift.shift_id})">Cancel Shift</button>`;
        }

        const tr = document.createElement('tr');
        tr.dataset.shiftId = String(shift.shift_id);
        tr.innerHTML = `
            <td data-label="Shift Name"><strong>${escapeHtml(shift.shift_name || 'Untitled Shift')}</strong><br><span class="status-badge ${toStatusClass('shift-status', shiftStatus)}">${escapeHtml(shiftStatus)}</span></td>
            <td data-label="Date & Time">${escapeHtml(timeText)}</td>
            <td data-label="Roles">${rolesText}</td>
            <td data-label="Actions">
                <div class="shift-actions">
                    ${registrationsButton}
                    ${editButton}
                    ${actionButton}
                </div>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

// Load shifts table (admin)
async function loadShiftsTable() {
    const incomingTbody = document.getElementById('shifts-incoming-table-body');
    const ongoingTbody = document.getElementById('shifts-ongoing-table-body');
    const pastTbody = document.getElementById('shifts-past-table-body');
    const cancelledTbody = document.getElementById('shifts-cancelled-table-body');

    try {
        collapseExpandedRegistrations();
        registrationsCache = {};

        if (!currentPantryId) {
            setShiftBucketEmptyState(incomingTbody, 'Please select a pantry first.');
            setShiftBucketEmptyState(ongoingTbody, 'Please select a pantry first.');
            setShiftBucketEmptyState(pastTbody, 'Please select a pantry first.');
            setShiftBucketEmptyState(cancelledTbody, 'Please select a pantry first.');
            return;
        }

        const shifts = await getShifts(currentPantryId);
        const buckets = getManagedShiftBuckets(shifts, new Date());
        renderShiftBucketRows(incomingTbody, buckets.incoming, 'No incoming shifts.', 'incoming');
        renderShiftBucketRows(ongoingTbody, buckets.ongoing, 'No ongoing shifts.', 'ongoing');
        renderShiftBucketRows(pastTbody, buckets.past, 'No past shifts.', 'past');
        renderShiftBucketRows(cancelledTbody, buckets.cancelled, 'No canceled shifts.', 'cancelled');
    } catch (error) {
        console.error('Failed to load shifts table:', error);
        setShiftBucketEmptyState(incomingTbody, `Failed to load shifts: ${error.message}`);
        setShiftBucketEmptyState(ongoingTbody, `Failed to load shifts: ${error.message}`);
        setShiftBucketEmptyState(pastTbody, `Failed to load shifts: ${error.message}`);
        setShiftBucketEmptyState(cancelledTbody, `Failed to load shifts: ${error.message}`);
        showMessage('shifts', `Failed to load shifts: ${error.message}`, 'error');
    }
}

function buildEditRoleRow(role = null) {
    const roleId = role && role.shift_role_id ? String(role.shift_role_id) : '';
    const roleTitle = role && role.role_title ? role.role_title : '';
    const roleCount = role && role.required_count ? Number(role.required_count) : 1;

    const roleGroup = document.createElement('div');
    roleGroup.className = 'role-input-group';
    roleGroup.dataset.roleId = roleId;
    roleGroup.innerHTML = `
        <div class="form-grid">
            <div class="form-group">
                <label>Role Title *</label>
                <input type="text" class="edit-role-title" value="${escapeHtml(roleTitle)}" placeholder="e.g., Food Sorter" required>
            </div>
            <div class="form-group">
                <label>Required Count *</label>
                <input type="number" class="edit-role-count" min="1" value="${roleCount}" required>
            </div>
            <div class="form-group role-input-actions">
                <label>Action</label>
                <button type="button" class="btn btn-danger remove-edit-role-btn">Remove</button>
            </div>
        </div>
    `;
    roleGroup.querySelector('.remove-edit-role-btn').addEventListener('click', () => {
        roleGroup.remove();
    });
    return roleGroup;
}

function resetEditShiftForm() {
    editingShiftSnapshot = null;
    document.getElementById('edit-shift-id').value = '';
    document.getElementById('edit-shift-name').value = '';
    document.getElementById('edit-shift-start').value = '';
    document.getElementById('edit-shift-end').value = '';
    document.getElementById('edit-roles-container').innerHTML = '';
    document.getElementById('edit-shift-card').classList.add('app-hidden');
}

async function openEditShift(shiftId) {
    try {
        setManageShiftsSubtab('view');
        const shift = await getShift(shiftId);
        editingShiftSnapshot = shift;

        document.getElementById('edit-shift-id').value = String(shift.shift_id);
        document.getElementById('edit-shift-name').value = shift.shift_name || '';
        document.getElementById('edit-shift-start').value = formatDateTimeForInput(shift.start_time);
        document.getElementById('edit-shift-end').value = formatDateTimeForInput(shift.end_time);

        const container = document.getElementById('edit-roles-container');
        container.innerHTML = '';
        const roles = shift.roles || [];
        if (roles.length === 0) {
            container.appendChild(buildEditRoleRow(null));
        } else {
            roles.forEach(role => {
                container.appendChild(buildEditRoleRow(role));
            });
        }

        document.getElementById('edit-shift-card').classList.remove('app-hidden');
        document.getElementById('edit-shift-card').scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (error) {
        showMessage('shifts', `Failed to load shift for editing: ${error.message}`, 'error');
    }
}

function collectAffectedContacts(responses) {
    const seen = new Set();
    let affectedCount = 0;

    responses.forEach(response => {
        if (!response) return;
        affectedCount += Number(response.affected_signup_count || 0);
        const contacts = response.affected_volunteer_contacts || [];
        contacts.forEach(contact => {
            if (!contact || !contact.email) return;
            seen.add(contact.email);
        });
    });

    return {
        affectedCount,
        uniqueVolunteers: seen.size
    };
}

// Cancel shift with confirmation
async function cancelShiftConfirm(shiftId) {
    if (!confirm('Cancel this shift? Volunteers will need to reconfirm and no new signups will be accepted.')) return;

    try {
        const response = await deleteShift(shiftId);
        const affected = response.affected_signup_count || 0;
        showMessage('shifts', `Shift cancelled successfully! ${affected} volunteer signup(s) moved to pending confirmation and volunteers were notified.`, 'success');
        await loadShiftsTable();
        await loadCalendarShifts(); // Update calendar view too
        const myShiftsTab = document.getElementById('content-my-shifts');
        if (myShiftsTab && myShiftsTab.classList.contains('active')) {
            await loadMyRegisteredShifts();
        }
    } catch (error) {
        showMessage('shifts', `Cancel failed: ${error.message}`, 'error');
    }
}

async function revokeShiftConfirm(shiftId) {
    if (!confirm('Revoke this cancelled shift? Previously signed-up volunteers will stay pending confirmation.')) return;

    try {
        const response = await updateShift(shiftId, { status: 'OPEN' });
        const affected = response.affected_signup_count || 0;
        const notifiedMsg = affected > 0
            ? ` ${affected} volunteer(s) were notified to review and reconfirm.`
            : '';
        showMessage('shifts', `Shift revoked successfully! Volunteers remain pending confirmation until they reconfirm.${notifiedMsg}`, 'success');
        await loadShiftsTable();
        await loadCalendarShifts();
        const myShiftsTab = document.getElementById('content-my-shifts');
        if (myShiftsTab && myShiftsTab.classList.contains('active')) {
            await loadMyRegisteredShifts();
        }
    } catch (error) {
        showMessage('shifts', `Revoke failed: ${error.message}`, 'error');
    }
}

// Setup event listeners
function setupEventListeners() {
    setManageShiftsSubtab(activeManageShiftsSubtab);
    setAdminSubtab(activeAdminSubtab);
    lastAdminUsersPhoneViewport = isPhoneViewport();
    window.addEventListener('resize', handleAdminUsersViewportChange);
    if (typeof initializeCalendarUi === 'function') {
        initializeCalendarUi();
    }

    document.querySelectorAll('.manage-shifts-subtab').forEach((button) => {
        button.addEventListener('click', async () => {
            const targetSubtab = button.dataset.manageSubtab === 'view' ? 'view' : 'create';
            setManageShiftsSubtab(targetSubtab);
            if (targetSubtab === 'view') {
                await loadShiftsTable();
            }
        });
    });

    document.querySelectorAll('.admin-subtab').forEach((button) => {
        button.addEventListener('click', async () => {
            const targetSubtab = button.dataset.adminSubtab === 'users' ? 'users' : 'pantries';
            setAdminSubtab(targetSubtab);
            await loadAdminTab();
        });
    });

    // Tab navigation
    document.querySelectorAll('.nav-tab').forEach(tab => {
        tab.addEventListener('click', async () => {
            await activateTab(tab.dataset.tab);
        });
    });

    document.getElementById('admin-user-search-btn')?.addEventListener('click', async () => {
        await loadAdminUsers();
    });

    document.getElementById('admin-user-search')?.addEventListener('keydown', async (event) => {
        if (event.key === 'Enter') {
            event.preventDefault();
            await loadAdminUsers();
        }
    });

    document.getElementById('admin-user-role-filter')?.addEventListener('change', async () => {
        await loadAdminUsers();
    });

    document.getElementById('my-account-profile-form').addEventListener('submit', async (event) => {
        event.preventDefault();

        const fullName = document.getElementById('account-full-name').value.trim();
        const phoneNumber = document.getElementById('account-phone-number').value.trim();
        if (!fullName) {
            showMessage('my-account', 'Full name is required.', 'error');
            return;
        }

        try {
            currentUser = await updateCurrentUserProfile({
                full_name: fullName,
                phone_number: phoneNumber
            });
            await refreshCurrentUserState();
            showMessage('my-account', 'Basic information updated successfully.', 'success');
        } catch (error) {
            showMessage('my-account', `Failed to update profile: ${error.message}`, 'error');
        }
    });

    document.getElementById('my-account-email-form').addEventListener('submit', async (event) => {
        event.preventDefault();

        if (!currentUser?.email_change_supported) {
            showMessage('my-account', 'Email changes are unavailable for this account.', 'error');
            return;
        }

        const newEmail = document.getElementById('account-new-email').value.trim().toLowerCase();
        if (!newEmail) {
            showMessage('my-account', 'Enter a new email address first.', 'error');
            return;
        }

        try {
            await prepareCurrentUserEmailChange(newEmail);
            const result = await window.requestFirebaseEmailChange(currentUser, newEmail);
            const note = document.getElementById('my-account-email-note');
            if (note && result?.message) {
                note.className = 'account-note account-note-success';
                note.textContent = result.message;
            }
            document.getElementById('account-new-email').value = '';
            showMessage('my-account', 'Email verification started. Confirm the change from your email, then <b>log out this tab</b> and sign in again.', 'success');
        } catch (error) {
            updateAccountEmailUi();
            showMessage('my-account', `Failed to start email change: ${error.message}`, 'error');
        }
    });

    document.getElementById('delete-account-btn').addEventListener('click', async () => {
        if (!currentUser) {
            showMessage('my-account', 'No user is loaded.', 'error');
            return;
        }

        const confirmed = confirm('Delete your account permanently? This cannot be undone.');
        if (!confirmed) {
            return;
        }

        try {
            let payload = {};
            if (currentUser.auth_mode === 'firebase' && currentUser.auth_provider === 'firebase') {
                const result = await window.requestFirebaseAccountDeletion(currentUser);
                payload = { id_token: result.idToken };
            }

            await deleteCurrentUserAccount(payload);
            window.location.reload();
        } catch (error) {
            showMessage('my-account', `Failed to delete account: ${error.message}`, 'error');
        }
    });

    // Edit pantry modal - cancel
    document.getElementById('cancel-edit-pantry-btn').addEventListener('click', () => {
        document.getElementById('edit-pantry-modal').classList.add('app-hidden');
    });

    document.getElementById('edit-pantry-modal').addEventListener('click', (event) => {
        if (event.target === event.currentTarget) {
            event.currentTarget.classList.add('app-hidden');
        }
    });

    document.getElementById('notification-modal-close-btn').addEventListener('click', () => {
        document.getElementById('notification-modal').classList.add('app-hidden');
    });

    document.getElementById('notification-modal').addEventListener('click', (event) => {
        if (event.target === event.currentTarget) {
            event.currentTarget.classList.add('app-hidden');
        }
    });

    // Edit pantry modal - save
    document.getElementById('save-edit-pantry-btn').addEventListener('click', async () => {
        const pantryId = parseInt(document.getElementById('edit-pantry-id').value);
        const name = document.getElementById('edit-pantry-name').value.trim();
        const location_address = document.getElementById('edit-pantry-address').value.trim();

        if (!name || !location_address) {
            showMessage('edit-pantry', 'Both fields are required.', 'error');
            return;
        }

        try {
            await updatePantry(pantryId, { name, location_address });
            document.getElementById('edit-pantry-modal').classList.add('app-hidden');
            showMessage('pantry', 'Pantry updated successfully!', 'success');
            await loadPantries();
        } catch (error) {
            showMessage('edit-pantry', `Error: ${error.message}`, 'error');
        }
    });

    // Pantry selection
    document.getElementById('pantry-select').addEventListener('change', async (e) => {
        currentPantryId = parseInt(e.target.value);
        resetEditShiftForm();
        await loadCalendarShifts();
        if (currentUserIsAdminCapable() || currentUserHasRole('PANTRY_LEAD')) {
            await loadShiftsTable();
        }
    });

    // Create pantry form
    document.getElementById('create-pantry-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const formData = new FormData(e.target);
        const data = {
            name: formData.get('name'),
            location_address: formData.get('location_address')
        };

        try {
            await createPantry(data);
            showMessage('pantry', 'Pantry created successfully!', 'success');
            e.target.reset();
            await loadPantries();
        } catch (error) {
            showMessage('pantry', `Error: ${error.message}`, 'error');
        }
    });

    // Assign lead
    document.getElementById('assign-lead-btn').addEventListener('click', async () => {
        const pantryId = parseInt(document.getElementById('assign-pantry').value);
        const leadId = parseInt(document.getElementById('assign-lead').value);

        if (!pantryId || !leadId) {
            showMessage('assign', 'Please select both pantry and lead', 'error');
            return;
        }

        try {
            await addPantryLead(pantryId, leadId);
            showMessage('assign', 'Lead assigned successfully!', 'success');
            await loadPantries();
        } catch (error) {
            showMessage('assign', `Error: ${error.message}`, 'error');
        }
    });

    // Remove lead
    document.getElementById('remove-lead-btn').addEventListener('click', async () => {
        const pantryId = parseInt(document.getElementById('assign-pantry').value);
        const leadId = parseInt(document.getElementById('assign-lead').value);

        if (!pantryId || !leadId) {
            showMessage('assign', 'Please select both pantry and lead', 'error');
            return;
        }

        if (!confirm('Remove this lead from the pantry?')) return;

        try {
            await removePantryLead(pantryId, leadId);
            showMessage('assign', 'Lead removed successfully!', 'success');
            await loadPantries();
        } catch (error) {
            showMessage('assign', `Error: ${error.message}`, 'error');
        }
    });

    // Add role button
    document.getElementById('add-role-btn').addEventListener('click', () => {
        const container = document.getElementById('roles-container');
        const roleGroup = document.createElement('div');
        roleGroup.className = 'role-input-group';
        roleGroup.innerHTML = `
                    <div class="form-grid">
                        <div class="form-group">
                            <label>Role Title *</label>
                            <input type="text" class="role-title" placeholder="e.g., Food Sorter" required>
                        </div>
                        <div class="form-group">
                            <label>Required Count *</label>
                            <input type="number" class="role-count" min="1" value="1" required>
                        </div>
                        <div class="form-group role-input-actions">
                            <label>Action</label>
                            <button type="button" class="btn btn-danger" onclick="this.closest('.role-input-group').remove()">Remove</button>
                        </div>
                    </div>
                `;
        container.appendChild(roleGroup);
    });

    document.getElementById('cancel-edit-shift-btn').addEventListener('click', () => {
        resetEditShiftForm();
    });

    document.getElementById('add-edit-role-btn').addEventListener('click', () => {
        const container = document.getElementById('edit-roles-container');
        container.appendChild(buildEditRoleRow(null));
    });

    document.getElementById('edit-shift-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        if (!editingShiftSnapshot) {
            showMessage('shifts', 'No shift selected for editing', 'error');
            return;
        }

        const shiftId = parseInt(document.getElementById('edit-shift-id').value, 10);
        if (!shiftId) {
            showMessage('shifts', 'Invalid shift selected', 'error');
            return;
        }

        const updatedShiftPayload = {
            shift_name: document.getElementById('edit-shift-name').value.trim(),
            start_time: new Date(document.getElementById('edit-shift-start').value).toISOString(),
            end_time: new Date(document.getElementById('edit-shift-end').value).toISOString(),
            status: String(editingShiftSnapshot.status || 'OPEN').toUpperCase()
        };

        if (!updatedShiftPayload.shift_name || Number.isNaN(new Date(updatedShiftPayload.start_time).getTime()) || Number.isNaN(new Date(updatedShiftPayload.end_time).getTime())) {
            showMessage('shifts', 'Please provide valid shift name and time range', 'error');
            return;
        }

        const roleRows = Array.from(document.querySelectorAll('#edit-roles-container .role-input-group'));
        if (roleRows.length === 0) {
            showMessage('shifts', 'Shift must include at least one role', 'error');
            return;
        }

        const roleInputs = roleRows.map((row) => {
            const roleIdRaw = row.dataset.roleId || '';
            const roleTitle = row.querySelector('.edit-role-title')?.value.trim() || '';
            const requiredCount = parseInt(row.querySelector('.edit-role-count')?.value || '0', 10);
            return {
                shift_role_id: roleIdRaw ? parseInt(roleIdRaw, 10) : null,
                role_title: roleTitle,
                required_count: requiredCount
            };
        });

        const invalidRole = roleInputs.find((role) => !role.role_title || Number.isNaN(role.required_count) || role.required_count < 1);
        if (invalidRole) {
            showMessage('shifts', 'Each role requires a title and required count >= 1', 'error');
            return;
        }

        try {
            const response = await updateFullShift(shiftId, {
                ...updatedShiftPayload,
                roles: roleInputs.map(role => ({
                    ...(role.shift_role_id ? { shift_role_id: role.shift_role_id } : {}),
                    role_title: role.role_title,
                    required_count: role.required_count
                }))
            });

            const impacted = collectAffectedContacts([response]);
            const impactedMsg = impacted.uniqueVolunteers > 0
                ? ` ${impacted.uniqueVolunteers} volunteer(s) need reconfirmation.`
                : '';
            showMessage('shifts', `Shift updated successfully.${impactedMsg}`, 'success');

            resetEditShiftForm();
            await loadShiftsTable();
            await loadCalendarShifts();
            const myShiftsTab = document.getElementById('content-my-shifts');
            if (myShiftsTab && myShiftsTab.classList.contains('active')) {
                await loadMyRegisteredShifts();
            }
        } catch (error) {
            showMessage('shifts', `Update failed: ${error.message}`, 'error');
        }
    });

    // Create shift form
    document.getElementById('create-shift-form').addEventListener('submit', async (e) => {
        e.preventDefault();

        if (!currentPantryId) {
            showMessage('shifts', 'Please select a pantry first', 'error');
            return;
        }

        const formData = new FormData(e.target);
        const shiftData = {
            shift_name: formData.get('shift_name'),
            start_time: new Date(formData.get('start_time')).toISOString(),
            end_time: new Date(formData.get('end_time')).toISOString()
        };

        // Collect roles
        const roleTitles = document.querySelectorAll('.role-title');
        const roleCounts = document.querySelectorAll('.role-count');
        const roles = [];

        for (let i = 0; i < roleTitles.length; i++) {
            const title = roleTitles[i].value.trim();
            const count = parseInt(roleCounts[i].value);
            if (title && count > 0) {
                roles.push({ role_title: title, required_count: count });
            }
        }

        if (roles.length === 0) {
            showMessage('shifts', 'Please add at least one role', 'error');
            return;
        }

        try {
            // Create shift
            const shift = await createShift(currentPantryId, shiftData);

            // Create roles
            for (const role of roles) {
                await createShiftRole(shift.shift_id, role);
            }

            showMessage('shifts', 'Shift created successfully with all roles!', 'success');
            e.target.reset();

            // Reset roles container to single role
            document.getElementById('roles-container').innerHTML = `
                        <div class="role-input-group">
                            <div class="form-grid">
                                <div class="form-group">
                                    <label>Role Title *</label>
                                    <input type="text" class="role-title" placeholder="e.g., Greeter" required>
                                </div>
                                <div class="form-group">
                                    <label>Required Count *</label>
                                    <input type="number" class="role-count" min="1" value="1" required>
                                </div>
                            </div>
                        </div>
                    `;

            await loadShiftsTable();
            await loadCalendarShifts();
        } catch (error) {
            showMessage('shifts', `Error: ${error.message}`, 'error');
        }
    });
}

// Show message helper
function showMessage(target, text, type = 'info') {
    const modal = document.getElementById('notification-modal');
    const box = document.getElementById('notification-modal-box');
    const textEl = document.getElementById('notification-modal-text');
    const iconEl = document.getElementById('notification-modal-icon');
    if (!modal || !textEl) return;

    const styles = {
        success: { icon: '✓', color: '#22543d', bg: '#c6f6d5', border: '#48bb78' },
        error:   { icon: '✕', color: '#742a2a', bg: '#fed7d7', border: '#f56565' },
        info:    { icon: 'ℹ', color: '#2c5282', bg: '#bee3f8', border: '#4299e1' },
    };
    const s = styles[type] || styles.info;

    box.style.borderTop = `4px solid ${s.border}`;
    box.style.background = s.bg;
    iconEl.textContent = s.icon;
    iconEl.style.color = s.border;
    textEl.innerHTML = text;
    textEl.style.color = s.color;

    modal.classList.remove('app-hidden');
}

// Make functions globally available
window.signupForRole = signupForRole;
window.cancelShiftConfirm = cancelShiftConfirm;
window.revokeShiftConfirm = revokeShiftConfirm;
window.openEditShift = openEditShift;
window.toggleShiftRegistrations = toggleShiftRegistrations;
window.cancelMySignup = cancelMySignup;
window.reconfirmMySignup = reconfirmMySignup;
window.markSignupAttendance = markSignupAttendance;
window.initializeDashboardApp = initializeDashboardApp;
