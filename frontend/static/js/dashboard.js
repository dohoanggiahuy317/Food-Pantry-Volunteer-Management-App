// Global state
let currentUser = null;
let currentPantryId = null;
let allPantries = [];
let allPublicPantries = [];
let expandedShiftContext = null;
let registrationsCache = {};
let editingShiftSnapshot = null;
let activeManageShiftsSubtab = 'create';

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

        // Setup UI based on role and choose default tab
        const defaultTab = setupRoleBasedUI();

        // Load pantries
        await loadPantries();

        // Setup event listeners
        setupEventListeners();

        // Load initial tab content
        await activateTab(defaultTab);

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
    const calendarTab = document.querySelector('.nav-tab[data-tab="calendar"]');
    const calendarContent = document.getElementById('content-calendar');
    let defaultTab = 'calendar';

    const hideCalendarForLead = isPantryLead && !isAdmin && !isVolunteer;
    if (hideCalendarForLead && calendarTab) {
        calendarTab.classList.add('hidden');
        calendarContent?.classList.remove('active');
        defaultTab = 'shifts';
    }

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
        pantrySelector.style.display = (targetTab === 'calendar' || targetTab === 'my-shifts') ? 'none' : 'block';
    }

    // Load tab-specific data
    if (targetTab === 'shifts') {
        setManageShiftsSubtab(activeManageShiftsSubtab);
        await loadShiftsTable();
    } else if (targetTab === 'my-shifts') {
        await loadMyRegisteredShifts();
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
            const shiftCancelled = String(shift.status || 'OPEN').toUpperCase() === 'CANCELLED';
            const roleCancelled = String(role.status || 'OPEN').toUpperCase() === 'CANCELLED';
            const isUnavailable = shiftCancelled || roleCancelled;
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
    if (!currentUser || !currentUser.user_id) {
        showMessage('calendar', 'Signup failed: Missing current user context', 'error');
        return;
    }

    let message = 'Successfully signed up!';
    let messageType = 'success';

    try {
        const signupResult = await signupForShift(roleId, currentUser.user_id);
        if (signupResult && signupResult.already_signed_up) {
            message = 'You already signed up for this shift.';
            messageType = 'error';
        }
    } catch (error) {
        showMessage('calendar', `Signup failed: ${error.message}`, 'error');
        return;
    }

    try {

        const myShiftsTab = document.getElementById('content-my-shifts');
        const isVolunteer = currentUser && currentUser.roles.includes('VOLUNTEER');
        if (isVolunteer && myShiftsTab && myShiftsTab.classList.contains('active')) {
            await loadMyRegisteredShifts();
        }
        showMessage('calendar', message, messageType);
    } catch (error) {
        showMessage('calendar', `Signup completed, but refresh failed: ${error.message}`, 'error');
    }

    await loadCalendarShifts(); // Reload to show updated counts no matter the error or success
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

function formatShiftRange(startTime, endTime) {
    const start = safeDateValue(startTime);
    const end = safeDateValue(endTime);
    if (!start || !end) return 'Time unavailable';

    return `${start.toLocaleDateString()} | ${start.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} - ${end.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
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
                ? `<button class="btn btn-success" onclick="reconfirmMySignup(${signup.signup_id}, 'CONFIRM')" style="padding: 0.5rem 1rem; font-size: 0.875rem;">Confirm</button>`
                : `<span class="reconfirm-note">Role is full or unavailable for reconfirmation.</span>`
            }
                <button class="btn btn-danger" onclick="reconfirmMySignup(${signup.signup_id}, 'CANCEL')" style="padding: 0.5rem 1rem; font-size: 0.875rem;">Cancel</button>
            </div>
        `;
    } else if (showCancel) {
        actionsHtml = `
            <div class="my-shift-actions">
                <button class="btn btn-danger" onclick="cancelMySignup(${signup.signup_id})" style="padding: 0.5rem 1rem; font-size: 0.875rem;">Cancel Signup</button>
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
    const canMarkAttendance = currentUser && (currentUser.roles.includes('ADMIN') || currentUser.roles.includes('PANTRY_LEAD'));

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
                                class="btn btn-secondary btn-attendance btn-attendance-showup"
                                onclick="markSignupAttendance(${signup.signup_id}, 'SHOW_UP', ${shiftRegistrations.shift_id})"
                                ${disabledAttr}
                                title="${disabledReason}"
                                style="padding: 0.25rem 0.6rem; font-size: 0.75rem;"
                            >
                                Mark Show Up
                            </button>
                            <button
                                class="btn btn-secondary btn-attendance btn-attendance-noshow"
                                onclick="markSignupAttendance(${signup.signup_id}, 'NO_SHOW', ${shiftRegistrations.shift_id})"
                                ${disabledAttr}
                                title="${disabledReason}"
                                style="padding: 0.25rem 0.6rem; font-size: 0.75rem;"
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
    tbody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: #718096;">${escapeHtml(text)}</td></tr>`;
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
            ? `${startDate.toLocaleString()} - ${endDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
            : 'Time unavailable';
        const rolesText = shift.roles && shift.roles.length > 0
            ? shift.roles.map((role) => `${escapeHtml(role.role_title || 'Untitled Role')} (${role.filled_count || 0}/${role.required_count || 0})`).join(', ')
            : 'No roles';
        const shiftStatus = String(shift.status || 'OPEN').toUpperCase();
        const lockHint = 'Past shifts are locked';
        const registrationsButton = `<button
                        class="btn btn-secondary"
                        data-registrations-btn="${shift.shift_id}"
                        onclick="toggleShiftRegistrations(${shift.shift_id}, this)"
                        style="padding: 0.5rem 1rem; font-size: 0.875rem;"
                    >
                        View Registrations
                    </button>`;
        const editButton = isPastBucket
            ? `<button class="btn btn-primary" style="padding: 0.5rem 1rem; font-size: 0.875rem;" disabled title="${lockHint}">Edit</button>`
            : `<button class="btn btn-primary" onclick="openEditShift(${shift.shift_id})" style="padding: 0.5rem 1rem; font-size: 0.875rem;">Edit</button>`;
        let actionButton = '';
        if (isPastBucket) {
            actionButton = `<button class="btn btn-secondary" style="padding: 0.5rem 1rem; font-size: 0.875rem;" disabled title="${lockHint}">Locked</button>`;
        } else if (shiftStatus === 'CANCELLED') {
            actionButton = `<button class="btn btn-success" onclick="revokeShiftConfirm(${shift.shift_id})" style="padding: 0.5rem 1rem; font-size: 0.875rem;">Revoke</button>`;
        } else {
            actionButton = `<button class="btn btn-danger" onclick="cancelShiftConfirm(${shift.shift_id})" style="padding: 0.5rem 1rem; font-size: 0.875rem;">Cancel Shift</button>`;
        }

        const tr = document.createElement('tr');
        tr.dataset.shiftId = String(shift.shift_id);
        tr.innerHTML = `
            <td><strong>${escapeHtml(shift.shift_name || 'Untitled Shift')}</strong><br><span class="status-badge ${toStatusClass('shift-status', shiftStatus)}">${escapeHtml(shiftStatus)}</span></td>
            <td>${escapeHtml(timeText)}</td>
            <td>${rolesText}</td>
            <td>
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
    roleGroup.style.marginTop = '1rem';
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
            <div class="form-group" style="display: flex; align-items: flex-end;">
                <button type="button" class="btn btn-danger remove-edit-role-btn" style="width: 100%;">Remove</button>
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
    document.getElementById('edit-shift-card').style.display = 'none';
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

        document.getElementById('edit-shift-card').style.display = 'block';
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
        showMessage('shifts', `Shift cancelled successfully! ${affected} volunteer signup(s) moved to pending confirmation.`, 'success');
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
        await updateShift(shiftId, { status: 'OPEN' });
        showMessage('shifts', 'Shift revoked successfully! Volunteers remain pending confirmation until they reconfirm.', 'success');
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

    document.querySelectorAll('.manage-shifts-subtab').forEach((button) => {
        button.addEventListener('click', async () => {
            const targetSubtab = button.dataset.manageSubtab === 'view' ? 'view' : 'create';
            setManageShiftsSubtab(targetSubtab);
            if (targetSubtab === 'view') {
                await loadShiftsTable();
            }
        });
    });

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
            if (targetTab === 'calendar' || targetTab === 'my-shifts' ||  targetTab === 'admin') {
                pantrySelector.style.display = 'none';
            } else {
                pantrySelector.style.display = 'block';
            }

            // Load tab-specific data
            if (targetTab === 'shifts') {
                setManageShiftsSubtab(activeManageShiftsSubtab);
                await loadShiftsTable();
            } else if (targetTab === 'my-shifts') {
                await loadMyRegisteredShifts();
            }
        });
    });

    // Pantry selection
    document.getElementById('pantry-select').addEventListener('change', async (e) => {
        currentPantryId = parseInt(e.target.value);
        resetEditShiftForm();
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

        const existingRoleIds = new Set((editingShiftSnapshot.roles || []).map(role => Number(role.shift_role_id)));
        const submittedRoleIds = new Set(roleInputs.filter(role => role.shift_role_id).map(role => Number(role.shift_role_id)));
        const roleIdsToDelete = Array.from(existingRoleIds).filter(roleId => !submittedRoleIds.has(roleId));

        try {
            const responses = [];

            const shiftResponse = await updateShift(shiftId, updatedShiftPayload);
            responses.push(shiftResponse);

            for (const role of roleInputs) {
                if (role.shift_role_id) {
                    const updatedRole = await updateShiftRole(role.shift_role_id, {
                        role_title: role.role_title,
                        required_count: role.required_count
                    });
                    responses.push(updatedRole);
                } else {
                    await createShiftRole(shiftId, {
                        role_title: role.role_title,
                        required_count: role.required_count
                    });
                }
            }

            for (const roleId of roleIdsToDelete) {
                const deletedRoleResponse = await deleteShiftRole(roleId);
                responses.push(deletedRoleResponse);
            }

            const impacted = collectAffectedContacts(responses);
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
window.cancelShiftConfirm = cancelShiftConfirm;
window.revokeShiftConfirm = revokeShiftConfirm;
window.openEditShift = openEditShift;
window.toggleShiftRegistrations = toggleShiftRegistrations;
window.cancelMySignup = cancelMySignup;
window.reconfirmMySignup = reconfirmMySignup;
window.markSignupAttendance = markSignupAttendance;
