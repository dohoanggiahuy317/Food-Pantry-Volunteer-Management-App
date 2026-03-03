// Global state
let currentUser = null;
let currentPantryId = null;
let allPantries = [];
let allPublicPantries = [];
let expandedShiftId = null;
let registrationsCache = {};

// Wait for all scripts to load before initializing
window.addEventListener('load', async function () {
    try {
        // Verify functions are loaded
        if (typeof getCurrentUser === 'undefined') {
            throw new Error('Required functions not loaded. Please refresh the page.');
        }

        // Load current user
        currentUser = await getCurrentUser();
        document.getElementById('user-email').textContent = currentUser.email;

        // Display roles
        const roleNames = currentUser.roles.join(', ');
        document.getElementById('user-role').textContent = roleNames;

        // Setup UI based on role
        setupRoleBasedUI();

        // Load pantries
        await loadPantries();

        // Setup event listeners
        setupEventListeners();

        // Load initial tab content
        await loadCalendarShifts();

    } catch (error) {
        console.error('Failed to initialize:', error);
        showMessage('calendar', `Failed to load: ${error.message}`, 'error');
        // Display error on page
        document.getElementById('shifts-container').innerHTML = `
                    <div style="background: #fed7d7; border: 2px solid #f56565; padding: 2rem; border-radius: 12px; text-align: center;">
                        <h3 style="color: #742a2a; margin-bottom: 1rem;">⚠️ Failed to Load</h3>
                        <p style="color: #742a2a; margin-bottom: 1rem;"><strong>${error.message}</strong></p>
                        <p style="color: #742a2a; font-size: 0.875rem;">
                            Make sure you include <code>?user_id=X</code> in the URL<br>
                            Example: <code>http://127.0.0.1:5000/?user_id=4</code>
                        </p>
                        <button onclick="window.location.href='/?user_id=4'" class="btn btn-primary" style="margin-top: 1rem;">
                            Load as Admin
                        </button>
                    </div>
                `;
    }
});

// Setup UI based on role
function setupRoleBasedUI() {
    const isAdmin = currentUser.roles.includes('ADMIN');
    const isPantryLead = currentUser.roles.includes('PANTRY_LEAD');
    const isVolunteer = currentUser.roles.includes('VOLUNTEER');

    // Show/hide tabs based on role
    if (isAdmin || isPantryLead) {
        document.getElementById('tab-shifts').classList.remove('hidden');
    }

    if (isAdmin) {
        document.getElementById('tab-admin').classList.remove('hidden');
    }

    if (isVolunteer) {
        document.getElementById('tab-my-shifts').classList.remove('hidden');
    }
}

// Load pantries
async function loadPantries() {
    try {
        allPantries = await getPantries();
        allPublicPantries = await getAllPantries();
        const select = document.getElementById('pantry-select');
        const assignSelect = document.getElementById('assign-pantry');

        select.innerHTML = '';
        assignSelect.innerHTML = '<option value="">-- Select Pantry --</option>';

        if (allPantries.length === 0) {
            select.innerHTML = '<option value="">No pantries available</option>';
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

        // Select first pantry by default
        if (allPantries.length > 0) {
            currentPantryId = allPantries[0].pantry_id;
            select.value = currentPantryId;
        }

        // Load pantry leads for admin
        if (currentUser.roles.includes('ADMIN')) {
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
        tbody.innerHTML = '<tr><td colspan="3" style="text-align: center; color: #718096;">No pantries yet</td></tr>';
        return;
    }

    allPantries.forEach(pantry => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
                    <td>${pantry.name}</td>
                    <td>${pantry.location_address || '—'}</td>
                    <td>${pantry.leads && pantry.leads.length > 0
                ? pantry.leads.map(l => `<span style="background: #e2e8f0; padding: 0.25rem 0.5rem; border-radius: 4px; margin-right: 0.5rem; display: inline-block; margin-bottom: 0.25rem;">${l.full_name}</span>`).join('')
                : '<span style="color: #718096;">No leads assigned</span>'}</td>
                `;
        tbody.appendChild(tr);
    });
}

// Load calendar shifts from ALL pantries
async function loadCalendarShifts() {
    try {
        document.getElementById('shifts-container').innerHTML = '<div class="loading"><div class="spinner"></div><p>Loading shifts from all pantries...</p></div>';

        // Load shifts from all pantries and group by pantry
        const allShifts = {};

        if (!allPublicPantries || allPublicPantries.length === 0) {
            document.getElementById('shifts-container').innerHTML = '<p style="text-align: center; color: #718096; padding: 2rem;">No pantries available</p>';
            return;
        }

        for (const pantry of allPublicPantries) {
            try {
                const shifts = await getShifts(pantry.pantry_id);

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
        document.getElementById('shifts-container').innerHTML = `<p style="text-align: center; color: #f56565;">Error: ${error.message}</p>`;
    }
}

// Display all shifts grouped by pantry
function displayAllShiftsGroupedByPantry(allShifts) {
    console.log('All shifts grouped by pantry:', allShifts);
    const container = document.getElementById('shifts-container');

    const pantryIds = Object.keys(allShifts);
    if (pantryIds.length === 0) {
        container.innerHTML = '<p style="text-align: center; color: #718096; padding: 2rem;">No pantries available</p>';
        return;
    }

    container.innerHTML = '';

    // Create sections for each pantry
    pantryIds.forEach(pantryId => {
        const pantryData = allShifts[pantryId];

        // Pantry section header
        const section = document.createElement('div');
        section.style.marginBottom = '2rem';

        const header = document.createElement('div');
        header.style.cssText = 'background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 1rem; border-radius: 8px; margin-bottom: 1rem;';
        header.innerHTML = `
                    <h3 style="margin: 0; font-size: 1.25rem;">${pantryData.name}</h3>
                    <p style="margin: 0.25rem 0 0 0; opacity: 0.9; font-size: 0.875rem;">${pantryData.location || 'No location listed'}</p>
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
            noShifts.style.cssText = 'text-align: center; color: #718096; padding: 2rem;';
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

    if (!shifts || shifts.length === 0) {
        container.innerHTML = '<p style="text-align: center; color: #718096; padding: 2rem;">No shifts available yet</p>';
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
            const capacityClass = isFull ? 'capacity-full' : 'capacity-available';

            return `
                        <div class="role-item">
                            <div>
                                <div class="role-name">${role.role_title}</div>
                                <div class="role-capacity ${capacityClass}">${filled}/${required} filled</div>
                                <div class="progress-bar">
                                    <div class="progress-fill" style="width: ${percentage}%"></div>
                                </div>
                            </div>
                            <div>
                                ${isFull
                    ? '<button class="btn btn-secondary" disabled>Full</button>'
                    : `<button class="btn btn-success" onclick="signupForRole(${role.shift_role_id})">Sign Up</button>`
                }
                            </div>
                        </div>
                    `;
        }).join('');
    } else {
        rolesHTML = '<p style="color: #718096; font-style: italic;">No positions available</p>';
    }

    card.innerHTML = `
                <div class="shift-header">
                    <div>
                        <div class="shift-title">${shift.shift_name}</div>
                        <div class="shift-date">📅 ${startDate.toLocaleDateString()} | ${startDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} - ${endDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</div>
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
    try {
        await signupForShift(roleId);
        showMessage('calendar', 'Successfully signed up!', 'success');
        await loadCalendarShifts(); // Reload to show updated counts

        const myShiftsTab = document.getElementById('content-my-shifts');
        const isVolunteer = currentUser && currentUser.roles.includes('VOLUNTEER');
        if (isVolunteer && myShiftsTab && myShiftsTab.classList.contains('active')) {
            await loadMyRegisteredShifts();
        }
    } catch (error) {
        showMessage('calendar', `Signup failed: ${error.message}`, 'error');
    }
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

function formatShiftRange(startTime, endTime) {
    const start = safeDateValue(startTime);
    const end = safeDateValue(endTime);
    if (!start || !end) return 'Time unavailable';

    return `${start.toLocaleDateString()} | ${start.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} - ${end.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
}

function renderMyShiftCard(signup, now) {
    const signupStatus = String(signup.signup_status || 'UNKNOWN').toUpperCase();
    const shiftStatus = String(signup.shift_status || 'OPEN').toUpperCase();
    const showCancel = canCancelSignup(signup, now);

    return `
        <article class="my-shift-card">
            <div class="my-shift-card-header">
                <div>
                    <h4 class="my-shift-title">${escapeHtml(signup.shift_name || 'Untitled Shift')}</h4>
                    <p class="my-shift-role">Role: ${escapeHtml(signup.role_title || 'Unassigned')}</p>
                </div>
                <div class="my-shift-badges">
                    <span class="status-badge ${toStatusClass('signup-status', signupStatus)}">${escapeHtml(signupStatus)}</span>
                    <span class="status-badge ${toStatusClass('shift-status', shiftStatus)}">${escapeHtml(shiftStatus)}</span>
                </div>
            </div>
            <div class="my-shift-meta">
                <p><strong>When:</strong> ${escapeHtml(formatShiftRange(signup.start_time, signup.end_time))}</p>
                <p><strong>Pantry:</strong> ${escapeHtml(signup.pantry_name || 'Unknown Pantry')}</p>
                <p><strong>Location:</strong> ${escapeHtml(signup.pantry_location || 'No location listed')}</p>
            </div>
            ${showCancel
            ? `
                <div class="my-shift-actions">
                    <button class="btn btn-danger" onclick="cancelMySignup(${signup.signup_id})" style="padding: 0.5rem 1rem; font-size: 0.875rem;">Cancel Signup</button>
                </div>
            `
            : ''
        }
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
        if (!signups || signups.length === 0) {
            container.innerHTML = '<p class="my-shift-empty-all">You have no registered shifts yet.</p>';
            return;
        }

        const now = new Date();
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

function renderRegistrationsRowContent(shiftRegistrations) {
    const roles = shiftRegistrations.roles || [];

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

        const signupsHtml = signups.length > 0
            ? `
                <ul class="registrant-list">
                    ${signups.map(signup => {
                    const user = signup.user || {};
                    const userName = escapeHtml(user.full_name || 'Unknown volunteer');
                    const userEmail = escapeHtml(user.email || 'No email');
                    const signupStatus = escapeHtml(signup.signup_status || 'CONFIRMED');
                    return `
                            <li class="registrant-item">
                                <div class="registrant-main">
                                    <div class="registrant-name">${userName}</div>
                                    <div class="registrant-email">${userEmail}</div>
                                </div>
                                <span class="registrant-status">${signupStatus}</span>
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
                    <div class="registration-role-capacity">${filled}/${required} filled</div>
                </div>
                ${signupsHtml}
            </div>
        `;
    }).join('');

    return `
        <div class="shift-registrations">
            <h4 class="registrations-title">Registrations by Role</h4>
            <div class="registration-role-grid">
                ${roleBlocks}
            </div>
        </div>
    `;
}

async function toggleShiftRegistrations(shiftId, buttonEl) {
    const tbody = document.getElementById('shifts-table-body');
    if (!tbody) return;

    const targetRow = tbody.querySelector(`tr[data-shift-id="${shiftId}"]`);
    if (!targetRow) return;

    const previousExpandedShiftId = expandedShiftId;
    const isTogglingSameShift = previousExpandedShiftId === shiftId;

    const existingDetailsRow = tbody.querySelector('.shift-registrations-row');
    if (existingDetailsRow) {
        existingDetailsRow.remove();
    }

    if (previousExpandedShiftId !== null) {
        const previousButton = tbody.querySelector(`button[data-registrations-btn="${previousExpandedShiftId}"]`);
        if (previousButton) {
            previousButton.textContent = 'View Registrations';
        }
    }

    if (isTogglingSameShift) {
        expandedShiftId = null;
        return;
    }

    expandedShiftId = shiftId;
    if (buttonEl) {
        buttonEl.textContent = 'Hide Registrations';
    }

    const detailsRow = document.createElement('tr');
    detailsRow.className = 'shift-registrations-row';
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

        if (expandedShiftId !== shiftId) return;
        detailsRow.innerHTML = `<td colspan="4">${renderRegistrationsRowContent(registrationsCache[shiftId])}</td>`;
    } catch (error) {
        console.error('Failed to load registrations:', error);
        if (expandedShiftId !== shiftId) return;

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

// Load shifts table (admin)
async function loadShiftsTable() {
    if (!currentPantryId) return;

    try {
        expandedShiftId = null;
        registrationsCache = {};

        const shifts = await getShifts(currentPantryId);
        const tbody = document.getElementById('shifts-table-body');
        tbody.innerHTML = '';

        if (shifts.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; color: #718096;">No shifts created yet</td></tr>';
            return;
        }

        shifts.forEach(shift => {
            console.log('Shift data for table:', shift);
            const startDate = new Date(shift.start_time);
            const rolesText = shift.roles && shift.roles.length > 0
                ? shift.roles.map(r => `${r.role_title} (${r.filled_count || 0}/${r.required_count})`).join(', ')
                : 'No roles';

            const tr = document.createElement('tr');
            tr.dataset.shiftId = String(shift.shift_id);
            tr.innerHTML = `
                        <td><strong>${shift.shift_name}</strong></td>
                        <td>${startDate.toLocaleString()}</td>
                        <td>${rolesText}</td>
                        <td>
                            <div class="shift-actions">
                                <button
                                    class="btn btn-secondary"
                                    data-registrations-btn="${shift.shift_id}"
                                    onclick="toggleShiftRegistrations(${shift.shift_id}, this)"
                                    style="padding: 0.5rem 1rem; font-size: 0.875rem;"
                                >
                                    View Registrations
                                </button>
                                <button class="btn btn-danger" onclick="deleteShiftConfirm(${shift.shift_id})" style="padding: 0.5rem 1rem; font-size: 0.875rem;">Delete</button>
                            </div>
                        </td>
                    `;
            tbody.appendChild(tr);
        });
    } catch (error) {
        console.error('Failed to load shifts table:', error);
    }
}

// Delete shift with confirmation
async function deleteShiftConfirm(shiftId) {
    if (!confirm('Delete this shift? This will also delete all roles and signups.')) return;

    try {
        await deleteShift(shiftId);
        showMessage('shifts', 'Shift deleted successfully!', 'success');
        await loadShiftsTable();
        await loadCalendarShifts(); // Update calendar view too
    } catch (error) {
        showMessage('shifts', `Delete failed: ${error.message}`, 'error');
    }
}

// Setup event listeners
function setupEventListeners() {
    // Tab navigation
    document.querySelectorAll('.nav-tab').forEach(tab => {
        tab.addEventListener('click', async () => {
            const targetTab = tab.dataset.tab;

            // Update active tab style
            document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');

            // Show target content
            document.querySelectorAll('.tab-content').forEach(content => {
                content.classList.remove('active');
            });
            document.getElementById(`content-${targetTab}`).classList.add('active');

            // Show/hide pantry selector based on tab
            const pantrySelector = document.getElementById('pantry-selector');
            if (targetTab === 'calendar' || targetTab === 'my-shifts') {
                pantrySelector.style.display = 'none';
            } else {
                pantrySelector.style.display = 'block';
            }

            // Load tab-specific data
            if (targetTab === 'shifts') {
                await loadShiftsTable();
            } else if (targetTab === 'my-shifts') {
                await loadMyRegisteredShifts();
            }
        });
    });

    // Pantry selection
    document.getElementById('pantry-select').addEventListener('change', async (e) => {
        currentPantryId = parseInt(e.target.value);
        await loadCalendarShifts();
        if (currentUser.roles.includes('ADMIN') || currentUser.roles.includes('PANTRY_LEAD')) {
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
        roleGroup.style.marginTop = '1rem';
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
                        <div class="form-group" style="display: flex; align-items: flex-end;">
                            <button type="button" class="btn btn-danger" onclick="this.closest('.role-input-group').remove()" style="width: 100%;">Remove</button>
                        </div>
                    </div>
                `;
        container.appendChild(roleGroup);
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
    const messageEl = document.getElementById(`message-${target}`);
    if (!messageEl) return;

    messageEl.className = `message message-${type} show`;
    messageEl.textContent = text;

    setTimeout(() => {
        messageEl.classList.remove('show');
    }, 5000);
}

// Make functions globally available
window.signupForRole = signupForRole;
window.deleteShiftConfirm = deleteShiftConfirm;
window.toggleShiftRegistrations = toggleShiftRegistrations;
window.cancelMySignup = cancelMySignup;
