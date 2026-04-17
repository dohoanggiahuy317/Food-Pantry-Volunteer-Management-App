const CALENDAR_WEEKDAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const CALENDAR_WEEKDAY_LONG_LABELS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
const CALENDAR_COLOR_PALETTE = [
    { solid: '#2563eb', soft: '#dbeafe', text: '#1d4ed8' },
    { solid: '#16a34a', soft: '#dcfce7', text: '#15803d' },
    { solid: '#9333ea', soft: '#f3e8ff', text: '#7e22ce' },
    { solid: '#ea580c', soft: '#ffedd5', text: '#c2410c' },
    { solid: '#0891b2', soft: '#cffafe', text: '#0e7490' },
    { solid: '#dc2626', soft: '#fee2e2', text: '#b91c1c' },
    { solid: '#ca8a04', soft: '#fef9c3', text: '#a16207' },
    { solid: '#4f46e5', soft: '#e0e7ff', text: '#4338ca' }
];

const calendarState = {
    initialized: false,
    view: isPhoneViewport() ? 'week' : 'month',
    hasUserChangedView: false,
    selectedDate: startOfCalendarDay(new Date()),
    miniDate: startOfCalendarMonth(new Date()),
    shifts: [],
    filteredShifts: [],
    filters: {
        pantryId: 'all',
        search: '',
        timeBucket: 'all'
    },
    activeShiftId: null,
    loadingKey: '',
    lastRangeKey: '',
    lastViewportIsPhone: isPhoneViewport()
};

function initializeCalendarUi() {
    if (calendarState.initialized) {
        syncCalendarPantryOptions();
        renderCalendarMiniPicker();
        return;
    }

    calendarState.initialized = true;
    renderCalendarMiniWeekdays();
    bindCalendarUiEvents();
    syncCalendarPantryOptions();
    renderCalendarMiniPicker();
    updateCalendarToolbarState();
    updateCalendarFilterSummary();
    window.addEventListener('resize', handleCalendarViewportResize);
}

function bindCalendarUiEvents() {
    document.getElementById('calendar-sidebar-toggle')?.addEventListener('click', openCalendarSidebar);
    document.getElementById('calendar-sidebar-close')?.addEventListener('click', closeCalendarSidebar);
    document.getElementById('calendar-sidebar-backdrop')?.addEventListener('click', closeCalendarSidebar);
    document.getElementById('calendar-today-btn')?.addEventListener('click', async () => {
        calendarState.selectedDate = startOfCalendarDay(new Date());
        calendarState.miniDate = startOfCalendarMonth(calendarState.selectedDate);
        await loadCalendarShifts(true);
    });
    document.getElementById('calendar-prev-btn')?.addEventListener('click', async () => {
        shiftCalendarAnchor(-1);
        await loadCalendarShifts(true);
    });
    document.getElementById('calendar-next-btn')?.addEventListener('click', async () => {
        shiftCalendarAnchor(1);
        await loadCalendarShifts(true);
    });
    document.getElementById('calendar-mini-prev')?.addEventListener('click', () => {
        calendarState.miniDate = startOfCalendarMonth(addMonths(calendarState.miniDate, -1));
        renderCalendarMiniPicker();
    });
    document.getElementById('calendar-mini-next')?.addEventListener('click', () => {
        calendarState.miniDate = startOfCalendarMonth(addMonths(calendarState.miniDate, 1));
        renderCalendarMiniPicker();
    });
    document.querySelectorAll('[data-calendar-view]').forEach((button) => {
        button.addEventListener('click', async () => {
            const nextView = String(button.dataset.calendarView || 'month');
            if (!['month', 'week', 'day'].includes(nextView)) {
                return;
            }
            calendarState.view = nextView;
            calendarState.hasUserChangedView = true;
            await loadCalendarShifts(true);
        });
    });
    document.getElementById('calendar-search-input')?.addEventListener('input', () => {
        calendarState.filters.search = document.getElementById('calendar-search-input')?.value.trim() || '';
        renderCalendar();
    });
    document.getElementById('calendar-pantry-filter')?.addEventListener('change', () => {
        calendarState.filters.pantryId = document.getElementById('calendar-pantry-filter')?.value || 'all';
        renderCalendar();
    });
    document.getElementById('calendar-time-filter')?.addEventListener('change', () => {
        calendarState.filters.timeBucket = document.getElementById('calendar-time-filter')?.value || 'all';
        renderCalendar();
    });
    document.getElementById('calendar-clear-filters-btn')?.addEventListener('click', () => {
        calendarState.filters = { pantryId: 'all', search: '', timeBucket: 'all' };
        const searchInput = document.getElementById('calendar-search-input');
        const pantrySelect = document.getElementById('calendar-pantry-filter');
        const timeSelect = document.getElementById('calendar-time-filter');
        if (searchInput) searchInput.value = '';
        if (pantrySelect) pantrySelect.value = 'all';
        if (timeSelect) timeSelect.value = 'all';
        renderCalendar();
    });
    document.getElementById('shifts-container')?.addEventListener('click', async (event) => {
        const target = event.target instanceof HTMLElement ? event.target.closest('[data-calendar-shift-id], [data-calendar-more-day]') : null;
        if (!(target instanceof HTMLElement)) {
            return;
        }

        if (target.dataset.calendarMoreDay) {
            calendarState.selectedDate = parseCalendarDateKey(target.dataset.calendarMoreDay) || calendarState.selectedDate;
            calendarState.view = 'day';
            calendarState.hasUserChangedView = true;
            await loadCalendarShifts(true);
            return;
        }

        if (target.dataset.calendarShiftId) {
            openCalendarShiftModal(parseInt(target.dataset.calendarShiftId, 10));
        }
    });
    document.getElementById('calendar-shift-modal-close')?.addEventListener('click', closeCalendarShiftModal);
    document.getElementById('calendar-shift-modal')?.addEventListener('click', (event) => {
        if (event.target === event.currentTarget) {
            closeCalendarShiftModal();
        }
    });
    document.getElementById('calendar-shift-modal-body')?.addEventListener('click', async (event) => {
        const target = event.target instanceof HTMLElement ? event.target.closest('[data-calendar-role-signup]') : null;
        if (!(target instanceof HTMLElement)) {
            return;
        }
        const roleId = parseInt(target.dataset.calendarRoleSignup || '0', 10);
        if (!roleId) {
            return;
        }
        target.setAttribute('disabled', 'disabled');
        const signedUp = await signupForRole(roleId);
        target.removeAttribute('disabled');
        if (signedUp) {
            closeCalendarShiftModal();
        }
    });
}

function handleCalendarViewportResize() {
    const nextIsPhone = isPhoneViewport();
    if (nextIsPhone !== calendarState.lastViewportIsPhone && !calendarState.hasUserChangedView) {
        calendarState.view = nextIsPhone ? 'week' : 'month';
    }
    calendarState.lastViewportIsPhone = nextIsPhone;
    if (!nextIsPhone) {
        closeCalendarSidebar();
    }
    renderCalendar();
}

function openCalendarSidebar() {
    document.getElementById('calendar-sidebar')?.classList.add('open');
    document.getElementById('calendar-sidebar-backdrop')?.classList.remove('app-hidden');
}

function closeCalendarSidebar() {
    document.getElementById('calendar-sidebar')?.classList.remove('open');
    document.getElementById('calendar-sidebar-backdrop')?.classList.add('app-hidden');
}

function syncCalendarPantryOptions() {
    const select = document.getElementById('calendar-pantry-filter');
    if (!select) {
        return;
    }

    const previousValue = calendarState.filters.pantryId || 'all';
    const options = [
        '<option value="all">All pantries</option>',
        ...getCalendarPantryList().map((pantry) => `<option value="${pantry.pantry_id}">${escapeHtml(pantry.name || `Pantry ${pantry.pantry_id}`)}</option>`)
    ];
    select.innerHTML = options.join('');

    const hasPreviousValue = previousValue === 'all' || getCalendarPantryList().some((pantry) => String(pantry.pantry_id) === String(previousValue));
    calendarState.filters.pantryId = hasPreviousValue ? previousValue : 'all';
    select.value = calendarState.filters.pantryId;
    renderCalendarLegend();
}

function renderCalendarMiniWeekdays() {
    const container = document.getElementById('calendar-mini-weekdays');
    if (!container) {
        return;
    }
    container.innerHTML = CALENDAR_WEEKDAY_LABELS.map((label) => `<span>${label.slice(0, 2)}</span>`).join('');
}

function renderCalendarMiniPicker() {
    const label = document.getElementById('calendar-mini-label');
    const grid = document.getElementById('calendar-mini-grid');
    if (!label || !grid) {
        return;
    }

    label.textContent = formatCalendarDateLabel(calendarState.miniDate, { month: 'long', year: 'numeric' });
    const monthStart = startOfCalendarMonth(calendarState.miniDate);
    const visibleStart = startOfCalendarWeek(monthStart);
    const cells = [];
    for (let index = 0; index < 42; index += 1) {
        const cellDate = addDays(visibleStart, index);
        const isCurrentMonth = cellDate.getMonth() === monthStart.getMonth();
        const isToday = isSameCalendarDay(cellDate, new Date());
        const isSelected = isSameCalendarDay(cellDate, calendarState.selectedDate);
        cells.push(`
            <button
                type="button"
                class="calendar-mini-day${isCurrentMonth ? '' : ' is-outside'}${isToday ? ' is-today' : ''}${isSelected ? ' is-selected' : ''}"
                data-calendar-mini-date="${getCalendarDateKey(cellDate)}"
            >${cellDate.getDate()}</button>
        `);
    }
    grid.innerHTML = cells.join('');
    grid.querySelectorAll('[data-calendar-mini-date]').forEach((button) => {
        button.addEventListener('click', async () => {
            const date = parseCalendarDateKey(button.dataset.calendarMiniDate);
            if (!date) {
                return;
            }
            calendarState.selectedDate = date;
            calendarState.miniDate = startOfCalendarMonth(date);
            await loadCalendarShifts(true);
            if (isPhoneViewport()) {
                closeCalendarSidebar();
            }
        });
    });
}

function renderCalendarLegend() {
    const container = document.getElementById('calendar-pantry-legend');
    if (!container) {
        return;
    }

    const pantries = getCalendarPantryList();
    container.innerHTML = pantries.length > 0
        ? pantries.map((pantry) => {
            const palette = getCalendarPantryPalette(pantry.pantry_id);
            return `
                <div class="calendar-legend-item">
                    <span class="calendar-legend-swatch" style="background:${palette.solid}"></span>
                    <span>${escapeHtml(pantry.name || `Pantry ${pantry.pantry_id}`)}</span>
                </div>
            `;
        }).join('')
        : '<p class="empty-state empty-state-compact">No pantries available.</p>';
}

async function loadCalendarShifts(forceReload = true) {
    initializeCalendarUi();
    if (!calendarState.hasUserChangedView && isPhoneViewport()) {
        calendarState.view = 'week';
    }

    const container = document.getElementById('shifts-container');
    if (!container) {
        return;
    }

    const visibleRange = getCalendarVisibleRange();
    const rangeKey = `${visibleRange.start.toISOString()}|${visibleRange.end.toISOString()}|${calendarState.view}`;
    calendarState.miniDate = startOfCalendarMonth(calendarState.selectedDate);
    updateCalendarToolbarState();
    renderCalendarMiniPicker();

    if (!forceReload && calendarState.lastRangeKey === rangeKey && Array.isArray(calendarState.shifts) && calendarState.shifts.length >= 0) {
        renderCalendar();
        return;
    }

    calendarState.loadingKey = rangeKey;
    calendarState.lastRangeKey = rangeKey;
    container.classList.add('loading');
    container.innerHTML = '<div class="loading"><div class="spinner"></div><p>Loading shifts for this range...</p></div>';

    try {
        const params = new URLSearchParams({
            start: visibleRange.start.toISOString(),
            end: visibleRange.end.toISOString()
        });
        const shifts = await apiGet(`/api/calendar/shifts?${params.toString()}`);
        if (calendarState.loadingKey !== rangeKey) {
            return;
        }
        calendarState.shifts = normalizeCalendarShifts(shifts);
        renderCalendar();
    } catch (error) {
        if (calendarState.loadingKey !== rangeKey) {
            return;
        }
        container.classList.remove('loading');
        container.innerHTML = `<div class="error-state-card"><h3>Failed to load calendar</h3><p><strong>${escapeHtml(error.message || 'Unknown error')}</strong></p></div>`;
    }
}

function normalizeCalendarShifts(shifts) {
    if (!Array.isArray(shifts)) {
        return [];
    }

    return shifts
        .map((shift) => {
            const startDate = safeDateValue(shift.start_time);
            const endDate = safeDateValue(shift.end_time);
            if (!startDate || !endDate) {
                return null;
            }
            const pantry = shift.pantry || {};
            const pantryId = Number(pantry.pantry_id || shift.pantry_id || 0);
            const pantryName = pantry.name || getCalendarPantryNameById(pantryId) || 'Pantry';
            const roleTitles = Array.isArray(shift.roles) ? shift.roles.map((role) => role.role_title || '').filter(Boolean) : [];
            return {
                ...shift,
                pantry: {
                    pantry_id: pantryId,
                    name: pantryName,
                    location_address: pantry.location_address || ''
                },
                pantry_id: pantryId,
                pantry_name: pantryName,
                startDate,
                endDate,
                searchBlob: [
                    shift.shift_name,
                    pantryName,
                    pantry.location_address,
                    roleTitles.join(' ')
                ].filter(Boolean).join(' ').toLowerCase()
            };
        })
        .filter(Boolean)
        .sort((left, right) => left.startDate.getTime() - right.startDate.getTime());
}

function renderCalendar() {
    const container = document.getElementById('shifts-container');
    if (!container) {
        return;
    }

    updateCalendarToolbarState();
    updateCalendarFilterSummary();
    calendarState.filteredShifts = filterCalendarShifts(calendarState.shifts);
    renderActiveCalendarShiftModal();

    container.classList.remove('loading');
    if (isPhoneViewport()) {
        renderPhoneCalendarAgenda(container, calendarState.filteredShifts);
        return;
    }

    if (calendarState.view === 'week') {
        renderDesktopWeekCalendar(container, calendarState.filteredShifts);
        return;
    }
    if (calendarState.view === 'day') {
        renderDesktopDayCalendar(container, calendarState.filteredShifts);
        return;
    }
    renderDesktopMonthCalendar(container, calendarState.filteredShifts);
}

function updateCalendarToolbarState() {
    document.querySelectorAll('[data-calendar-view]').forEach((button) => {
        button.classList.toggle('active', button.dataset.calendarView === calendarState.view);
    });

    const label = document.getElementById('calendar-range-label');
    if (label) {
        label.textContent = getCalendarRangeLabel();
    }
}

function updateCalendarFilterSummary() {
    const summary = document.getElementById('calendar-active-filter-summary');
    if (!summary) {
        return;
    }

    const chips = [];
    if (calendarState.filters.pantryId !== 'all') {
        chips.push(`Pantry: ${escapeHtml(getCalendarPantryNameById(Number(calendarState.filters.pantryId)) || 'Selected pantry')}`);
    }
    if (calendarState.filters.search) {
        chips.push(`Search: ${escapeHtml(calendarState.filters.search)}`);
    }
    if (calendarState.filters.timeBucket !== 'all') {
        chips.push(`Time: ${escapeHtml(capitalizeCalendarLabel(calendarState.filters.timeBucket))}`);
    }

    summary.innerHTML = chips.length > 0
        ? chips.map((chip) => `<span class="calendar-filter-chip">${chip}</span>`).join('')
        : '<span class="calendar-filter-hint">Showing all available shifts in the selected range.</span>';
}

function filterCalendarShifts(shifts) {
    return shifts.filter((shift) => {
        if (calendarState.filters.pantryId !== 'all' && String(shift.pantry_id) !== String(calendarState.filters.pantryId)) {
            return false;
        }
        if (calendarState.filters.search && !shift.searchBlob.includes(calendarState.filters.search.toLowerCase())) {
            return false;
        }
        if (calendarState.filters.timeBucket !== 'all' && resolveCalendarTimeBucket(shift.startDate) !== calendarState.filters.timeBucket) {
            return false;
        }
        return isShiftInVisibleCalendarRange(shift);
    });
}

function renderDesktopMonthCalendar(container, shifts) {
    const monthStart = startOfCalendarMonth(calendarState.selectedDate);
    const visibleStart = startOfCalendarWeek(monthStart);
    const cells = [];
    for (let index = 0; index < 42; index += 1) {
        const cellDate = addDays(visibleStart, index);
        const dayKey = getCalendarDateKey(cellDate);
        const dayShifts = shifts.filter((shift) => getCalendarDateKey(shift.startDate) === dayKey);
        const visibleShifts = dayShifts.slice(0, 2);
        const overflowCount = Math.max(0, dayShifts.length - visibleShifts.length);
        const isCurrentMonth = cellDate.getMonth() === monthStart.getMonth();
        const isToday = isSameCalendarDay(cellDate, new Date());
        const isSelected = isSameCalendarDay(cellDate, calendarState.selectedDate);
        cells.push(`
            <div class="calendar-month-cell${isCurrentMonth ? '' : ' is-outside'}${isToday ? ' is-today' : ''}${isSelected ? ' is-selected' : ''}">
                <button type="button" class="calendar-month-day-number" data-calendar-more-day="${dayKey}">${cellDate.getDate()}</button>
                <div class="calendar-month-events">
                    ${visibleShifts.map((shift) => renderCalendarMonthEvent(shift)).join('')}
                    ${overflowCount > 0 ? `<button type="button" class="calendar-more-link" data-calendar-more-day="${dayKey}">+${overflowCount} more</button>` : ''}
                </div>
            </div>
        `);
    }

    container.innerHTML = `
        <div class="calendar-month-view">
            <div class="calendar-month-weekdays">
                ${CALENDAR_WEEKDAY_LONG_LABELS.map((label) => `<div>${label}</div>`).join('')}
            </div>
            <div class="calendar-month-grid">
                ${cells.join('')}
            </div>
        </div>
    `;
}

function renderCalendarMonthEvent(shift) {
    const palette = getCalendarPantryPalette(shift.pantry_id);
    const spanIndicator = getCalendarSpanIndicator(shift);
    return `
        <button
            type="button"
            class="calendar-month-event"
            data-calendar-shift-id="${shift.shift_id}"
            style="background:${palette.soft}; color:${palette.text}; border-left-color:${palette.solid};"
        >
            <span class="calendar-month-event-time">${escapeHtml(formatLocalTimeRange(shift.startDate, shift.endDate, { includeDate: false }))}</span>
            <span class="calendar-month-event-title">${escapeHtml(shift.shift_name)}</span>
            ${spanIndicator ? `<span class="calendar-month-event-span">${escapeHtml(spanIndicator)}</span>` : ''}
        </button>
    `;
}

function renderDesktopWeekCalendar(container, shifts) {
    const weekStart = startOfCalendarWeek(calendarState.selectedDate);
    const dayColumns = Array.from({ length: 7 }, (_, index) => addDays(weekStart, index));
    const hourBounds = getCalendarHourBounds(shifts);
    const slotHeight = 64;
    const totalHeight = (hourBounds.endHour - hourBounds.startHour) * slotHeight;
    const timeLabels = [];
    for (let hour = hourBounds.startHour; hour < hourBounds.endHour; hour += 1) {
        const hourDate = new Date(weekStart);
        hourDate.setHours(hour, 0, 0, 0);
        timeLabels.push(`
            <div class="calendar-week-time-slot" style="height:${slotHeight}px">
                <span>${escapeHtml(formatCalendarHourLabel(hourDate))}</span>
            </div>
        `);
    }

    const columnsHtml = dayColumns.map((dayDate) => renderWeekDayColumn(dayDate, shifts, hourBounds, slotHeight, totalHeight)).join('');
    container.innerHTML = `
        <div class="calendar-week-view">
            <div class="calendar-week-header">
                <div class="calendar-week-time-gutter"></div>
                ${dayColumns.map((dayDate) => renderWeekDayHeader(dayDate)).join('')}
            </div>
            <div class="calendar-week-body">
                <div class="calendar-week-time-column">
                    ${timeLabels.join('')}
                </div>
                <div class="calendar-week-grid">
                    ${columnsHtml}
                </div>
            </div>
        </div>
    `;
}

function renderWeekDayHeader(dayDate) {
    const isToday = isSameCalendarDay(dayDate, new Date());
    return `
        <div class="calendar-week-day-header${isToday ? ' is-today' : ''}">
            <span class="calendar-week-day-label">${escapeHtml(formatCalendarDateLabel(dayDate, { weekday: 'short', month: 'short', day: 'numeric' }))}</span>
        </div>
    `;
}

function renderWeekDayColumn(dayDate, shifts, hourBounds, slotHeight, totalHeight) {
    const dayEvents = shifts.filter((shift) => isSameCalendarDay(shift.startDate, dayDate));
    const layouts = layoutWeekDayEvents(dayEvents);
    const hourLines = [];
    for (let hour = hourBounds.startHour; hour < hourBounds.endHour; hour += 1) {
        hourLines.push(`<div class="calendar-week-hour-line" style="top:${(hour - hourBounds.startHour) * slotHeight}px"></div>`);
    }

    return `
        <div class="calendar-week-day-column">
            <div class="calendar-week-day-surface" style="height:${totalHeight}px">
                ${hourLines.join('')}
                ${layouts.map((entry) => renderWeekEventBlock(entry, hourBounds.startHour, slotHeight)).join('')}
            </div>
        </div>
    `;
}

function layoutWeekDayEvents(dayEvents) {
    if (dayEvents.length === 0) {
        return [];
    }

    const sorted = [...dayEvents].sort((left, right) => left.startDate.getTime() - right.startDate.getTime());
    const groups = [];
    let currentGroup = [];
    let currentGroupEnd = null;

    sorted.forEach((shift) => {
        if (currentGroup.length === 0) {
            currentGroup = [shift];
            currentGroupEnd = shift.endDate.getTime();
            return;
        }
        if (shift.startDate.getTime() < Number(currentGroupEnd)) {
            currentGroup.push(shift);
            currentGroupEnd = Math.max(Number(currentGroupEnd), shift.endDate.getTime());
            return;
        }
        groups.push(currentGroup);
        currentGroup = [shift];
        currentGroupEnd = shift.endDate.getTime();
    });
    if (currentGroup.length > 0) {
        groups.push(currentGroup);
    }

    const layouts = [];
    groups.forEach((group) => {
        const laneEndTimes = [];
        group.forEach((shift) => {
            const startMs = shift.startDate.getTime();
            let laneIndex = laneEndTimes.findIndex((laneEnd) => laneEnd <= startMs);
            if (laneIndex === -1) {
                laneIndex = laneEndTimes.length;
                laneEndTimes.push(shift.endDate.getTime());
            } else {
                laneEndTimes[laneIndex] = shift.endDate.getTime();
            }
            layouts.push({
                shift,
                laneIndex,
                laneCount: 0
            });
        });
        const laneCount = Math.max(1, laneEndTimes.length);
        layouts.forEach((entry) => {
            if (group.includes(entry.shift)) {
                entry.laneCount = laneCount;
            }
        });
    });

    return layouts;
}

function isCalendarMultiDayShift(shift) {
    return getCalendarDateKey(shift.startDate) !== getCalendarDateKey(shift.endDate);
}

function getCalendarDisplayEndDate(shift) {
    const endOfStartDay = endOfCalendarDay(shift.startDate);
    return shift.endDate.getTime() > endOfStartDay.getTime() ? endOfStartDay : shift.endDate;
}

function getCalendarSpanIndicator(shift) {
    if (!isCalendarMultiDayShift(shift)) {
        return '';
    }

    const daySpan = Math.round(
        (startOfCalendarDay(shift.endDate).getTime() - startOfCalendarDay(shift.startDate).getTime()) / (24 * 60 * 60 * 1000)
    );
    return daySpan > 1 ? 'Multi-day' : 'Continues next day';
}

function renderWeekEventBlock(entry, startHour, slotHeight) {
    const shift = entry.shift;
    const palette = getCalendarPantryPalette(shift.pantry_id);
    const startDecimal = shift.startDate.getHours() + (shift.startDate.getMinutes() / 60);
    const visualEnd = getCalendarDisplayEndDate(shift);
    const endDecimal = visualEnd.getHours() + (visualEnd.getMinutes() / 60) + (visualEnd.getSeconds() / 3600);
    const top = Math.max(0, (startDecimal - startHour) * slotHeight);
    const height = Math.max(32, (endDecimal - startDecimal) * slotHeight);
    const laneWidth = 100 / entry.laneCount;
    const left = laneWidth * entry.laneIndex;
    const spanIndicator = getCalendarSpanIndicator(shift);
    return `
        <button
            type="button"
            class="calendar-week-event"
            data-calendar-shift-id="${shift.shift_id}"
            style="
                top:${top}px;
                height:${height}px;
                left:calc(${left}% + 4px);
                width:calc(${laneWidth}% - 8px);
                background:${palette.soft};
                color:${palette.text};
                border-left-color:${palette.solid};
            "
        >
            <span class="calendar-week-event-title">${escapeHtml(shift.shift_name)}</span>
            <span class="calendar-week-event-meta">${escapeHtml(formatLocalTimeRange(shift.startDate, shift.endDate, { includeDate: false }))}</span>
            ${spanIndicator ? `<span class="calendar-week-event-span">${escapeHtml(spanIndicator)}</span>` : ''}
            <span class="calendar-week-event-meta">${escapeHtml(shift.pantry_name)}</span>
        </button>
    `;
}

function renderDesktopDayCalendar(container, shifts) {
    const selectedDayKey = getCalendarDateKey(calendarState.selectedDate);
    const dayEvents = shifts
        .filter((shift) => getCalendarDateKey(shift.startDate) === selectedDayKey)
        .sort((left, right) => left.startDate.getTime() - right.startDate.getTime());

    container.innerHTML = `
        <div class="calendar-day-view">
            <div class="calendar-day-header">
                <h3>${escapeHtml(formatLocalDate(calendarState.selectedDate, { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' }))}</h3>
                <p>${dayEvents.length} shift${dayEvents.length === 1 ? '' : 's'} available</p>
            </div>
            <div class="calendar-day-agenda">
                ${dayEvents.length > 0
                    ? dayEvents.map((shift) => renderCalendarDayAgendaCard(shift)).join('')
                    : '<p class="empty-state">No available shifts for this day.</p>'}
            </div>
        </div>
    `;
}

function renderCalendarDayAgendaCard(shift) {
    const palette = getCalendarPantryPalette(shift.pantry_id);
    const spanIndicator = getCalendarSpanIndicator(shift);
    return `
        <button
            type="button"
            class="calendar-day-card"
            data-calendar-shift-id="${shift.shift_id}"
            style="border-left-color:${palette.solid}"
        >
            <div class="calendar-day-card-time">${escapeHtml(formatLocalTimeRange(shift.startDate, shift.endDate, { includeDate: false }))}</div>
            <div class="calendar-day-card-title">${escapeHtml(shift.shift_name)}</div>
            ${spanIndicator ? `<div class="calendar-day-card-span">${escapeHtml(spanIndicator)}</div>` : ''}
            <div class="calendar-day-card-meta">${escapeHtml(shift.pantry_name)}${shift.pantry.location_address ? ` • ${escapeHtml(shift.pantry.location_address)}` : ''}</div>
            <div class="calendar-day-card-meta">${escapeHtml(renderCalendarRoleSummary(shift.roles || []))}</div>
        </button>
    `;
}

function renderPhoneCalendarAgenda(container, shifts) {
    const grouped = groupPhoneAgendaShifts(shifts);
    const phoneViewName = capitalizeCalendarLabel(calendarState.view);

    container.innerHTML = `
        <div class="calendar-phone-view">
            <div class="calendar-phone-summary">
                <h3>${phoneViewName} Agenda</h3>
                <p>${escapeHtml(getCalendarRangeLabel())}</p>
            </div>
            ${grouped.length > 0
                ? grouped.map((section) => renderPhoneAgendaSection(section)).join('')
                : '<p class="empty-state">No available shifts match the selected range and filters.</p>'}
        </div>
    `;
}

function groupPhoneAgendaShifts(shifts) {
    const byPantry = new Map();
    shifts.forEach((shift) => {
        const pantryKey = String(shift.pantry_id);
        if (!byPantry.has(pantryKey)) {
            byPantry.set(pantryKey, {
                pantryId: shift.pantry_id,
                pantryName: shift.pantry_name,
                location: shift.pantry.location_address || '',
                days: new Map()
            });
        }
        const pantrySection = byPantry.get(pantryKey);
        const dayKey = getCalendarDateKey(shift.startDate);
        if (!pantrySection.days.has(dayKey)) {
            pantrySection.days.set(dayKey, {
                dayKey,
                label: formatLocalDate(shift.startDate, { weekday: 'long', month: 'short', day: 'numeric', year: 'numeric' }),
                shifts: []
            });
        }
        pantrySection.days.get(dayKey).shifts.push(shift);
    });

    return [...byPantry.values()]
        .sort((left, right) => left.pantryName.localeCompare(right.pantryName))
        .map((section) => ({
            ...section,
            days: [...section.days.values()].sort((left, right) => left.dayKey.localeCompare(right.dayKey))
        }));
}

function renderPhoneAgendaSection(section) {
    const palette = getCalendarPantryPalette(section.pantryId);
    return `
        <section class="calendar-phone-pantry-section">
            <div class="calendar-phone-pantry-header" style="border-left-color:${palette.solid}">
                <h4>${escapeHtml(section.pantryName)}</h4>
                <p>${escapeHtml(section.location || 'Location unavailable')}</p>
            </div>
            <div class="calendar-phone-day-groups">
                ${section.days.map((dayGroup) => `
                    <div class="calendar-phone-day-group">
                        <div class="calendar-phone-day-title">${escapeHtml(dayGroup.label)}</div>
                        <div class="calendar-phone-event-list">
                            ${dayGroup.shifts
                                .sort((left, right) => left.startDate.getTime() - right.startDate.getTime())
                                .map((shift) => renderPhoneAgendaEvent(shift, palette))
                                .join('')}
                        </div>
                    </div>
                `).join('')}
            </div>
        </section>
    `;
}

function renderPhoneAgendaEvent(shift, palette) {
    const spanIndicator = getCalendarSpanIndicator(shift);
    return `
        <button
            type="button"
            class="calendar-phone-event"
            data-calendar-shift-id="${shift.shift_id}"
            style="border-left-color:${palette.solid}; background:${palette.soft}; color:${palette.text};"
        >
            <span class="calendar-phone-event-time">${escapeHtml(formatLocalTimeRange(shift.startDate, shift.endDate, { includeDate: false }))}</span>
            <span class="calendar-phone-event-title">${escapeHtml(shift.shift_name)}</span>
            ${spanIndicator ? `<span class="calendar-phone-event-span">${escapeHtml(spanIndicator)}</span>` : ''}
            <span class="calendar-phone-event-meta">${escapeHtml(renderCalendarRoleSummary(shift.roles || []))}</span>
        </button>
    `;
}

function openCalendarShiftModal(shiftId) {
    calendarState.activeShiftId = shiftId;
    renderActiveCalendarShiftModal();
    document.getElementById('calendar-shift-modal')?.classList.remove('app-hidden');
}

function closeCalendarShiftModal() {
    calendarState.activeShiftId = null;
    document.getElementById('calendar-shift-modal')?.classList.add('app-hidden');
}

function renderActiveCalendarShiftModal() {
    const modal = document.getElementById('calendar-shift-modal');
    const body = document.getElementById('calendar-shift-modal-body');
    if (!modal || !body) {
        return;
    }
    if (!calendarState.activeShiftId) {
        modal.classList.add('app-hidden');
        body.innerHTML = '';
        return;
    }

    const shift = calendarState.shifts.find((item) => intValue(item.shift_id) === intValue(calendarState.activeShiftId));
    if (!shift) {
        closeCalendarShiftModal();
        return;
    }

    const palette = getCalendarPantryPalette(shift.pantry_id);
    body.innerHTML = `
        <div class="calendar-modal-header" style="border-top-color:${palette.solid}">
            <span class="calendar-modal-pantry-badge" style="background:${palette.soft}; color:${palette.text};">${escapeHtml(shift.pantry_name)}</span>
            <h2 class="calendar-modal-title">${escapeHtml(shift.shift_name)}</h2>
            <p class="calendar-modal-time">${escapeHtml(formatLocalTimeRange(shift.startDate, shift.endDate))}</p>
            ${getCalendarSpanIndicator(shift) ? `<p class="calendar-modal-span">${escapeHtml(getCalendarSpanIndicator(shift))}</p>` : ''}
            <p class="calendar-modal-location">${escapeHtml(shift.pantry.location_address || 'Location unavailable')}</p>
        </div>
        <div class="calendar-modal-section">
            <h3>Roles</h3>
            <div class="calendar-modal-role-list">
                ${(shift.roles || []).map((role) => renderCalendarModalRole(role, shift)).join('')}
            </div>
        </div>
    `;
}

function renderCalendarModalRole(role, shift) {
    const filled = Number(role.filled_count || 0);
    const required = Number(role.required_count || 0);
    const isFull = required > 0 && filled >= required;
    const isCancelled = String(role.status || 'OPEN').toUpperCase() === 'CANCELLED' || String(shift.status || 'OPEN').toUpperCase() === 'CANCELLED';
    const capacityPercent = getCalendarRoleCapacityPercent(filled, required);
    const canVolunteerSignup = currentUserHasRole('VOLUNTEER');
    let buttonLabel = 'Sign Up';
    let disabled = false;
    if (!canVolunteerSignup) {
        buttonLabel = 'Volunteer Only';
        disabled = true;
    } else if (isCancelled) {
        buttonLabel = 'Unavailable';
        disabled = true;
    } else if (isFull) {
        buttonLabel = 'Full';
        disabled = true;
    }

    return `
        <div class="calendar-modal-role-item">
            <div class="calendar-modal-role-info">
                <div class="calendar-modal-role-title">${escapeHtml(role.role_title || 'Volunteer Role')}</div>
                <div class="calendar-modal-role-meta">${filled}/${required} filled</div>
                <div class="calendar-modal-role-capacity" aria-hidden="true">
                    <div class="calendar-modal-role-capacity-track">
                        <div
                            class="calendar-modal-role-capacity-fill${isFull ? ' is-full' : ''}${isCancelled ? ' is-cancelled' : ''}"
                            style="width:${capacityPercent}%"
                        ></div>
                    </div>
                    <div class="calendar-modal-role-capacity-label">${escapeHtml(getCalendarRoleCapacityLabel(filled, required, isCancelled))}</div>
                </div>
            </div>
            <button
                type="button"
                class="btn ${disabled ? 'btn-secondary' : 'btn-success'} btn-sm"
                data-calendar-role-signup="${disabled ? '' : role.shift_role_id}"
                ${disabled ? 'disabled' : ''}
            >${buttonLabel}</button>
        </div>
    `;
}

function getCalendarRoleCapacityPercent(filled, required) {
    if (required <= 0) {
        return 0;
    }
    return Math.max(0, Math.min(100, Math.round((filled / required) * 100)));
}

function getCalendarRoleCapacityLabel(filled, required, isCancelled) {
    if (isCancelled) {
        return 'Shift unavailable';
    }
    if (required <= 0) {
        return 'Capacity not set';
    }
    const remaining = Math.max(0, required - filled);
    if (remaining === 0) {
        return 'No spots left';
    }
    return `${remaining} spot${remaining === 1 ? '' : 's'} left`;
}

function getCalendarVisibleRange() {
    if (calendarState.view === 'day') {
        return {
            start: startOfCalendarDay(calendarState.selectedDate),
            end: endOfCalendarDay(calendarState.selectedDate)
        };
    }
    if (calendarState.view === 'week') {
        const start = startOfCalendarWeek(calendarState.selectedDate);
        return {
            start,
            end: endOfCalendarDay(addDays(start, 6))
        };
    }

    const monthStart = startOfCalendarMonth(calendarState.selectedDate);
    const start = startOfCalendarWeek(monthStart);
    const end = endOfCalendarDay(addDays(start, 41));
    return { start, end };
}

function isShiftInVisibleCalendarRange(shift) {
    const visibleRange = getCalendarVisibleRange();
    return shift.endDate >= visibleRange.start && shift.startDate <= visibleRange.end;
}

function getCalendarRangeLabel() {
    if (calendarState.view === 'day') {
        return formatCalendarDateLabel(calendarState.selectedDate, { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' });
    }
    if (calendarState.view === 'week') {
        const weekStart = startOfCalendarWeek(calendarState.selectedDate);
        const weekEnd = addDays(weekStart, 6);
        return formatCalendarWeekRangeLabel(weekStart, weekEnd);
    }
    return formatCalendarDateLabel(calendarState.selectedDate, { month: 'long', year: 'numeric' });
}

function formatCalendarWeekRangeLabel(weekStart, weekEnd) {
    const sameYear = weekStart.getFullYear() === weekEnd.getFullYear();
    const sameMonth = sameYear && weekStart.getMonth() === weekEnd.getMonth();
    if (sameMonth) {
        const monthLabel = formatCalendarDateLabel(weekStart, { month: 'short' });
        return `${monthLabel} ${weekStart.getDate()} - ${weekEnd.getDate()}, ${weekStart.getFullYear()}`;
    }
    if (sameYear) {
        const startLabel = formatCalendarDateLabel(weekStart, { month: 'short', day: 'numeric' });
        const endLabel = formatCalendarDateLabel(weekEnd, { month: 'short', day: 'numeric' });
        return `${startLabel} - ${endLabel}, ${weekStart.getFullYear()}`;
    }
    const startLabel = formatCalendarDateLabel(weekStart, { month: 'short', day: 'numeric', year: 'numeric' });
    const endLabel = formatCalendarDateLabel(weekEnd, { month: 'short', day: 'numeric', year: 'numeric' });
    return `${startLabel} - ${endLabel}`;
}

function shiftCalendarAnchor(direction) {
    if (calendarState.view === 'day') {
        calendarState.selectedDate = addDays(calendarState.selectedDate, direction);
        calendarState.miniDate = startOfCalendarMonth(calendarState.selectedDate);
        return;
    }
    if (calendarState.view === 'week') {
        calendarState.selectedDate = addDays(calendarState.selectedDate, direction * 7);
        calendarState.miniDate = startOfCalendarMonth(calendarState.selectedDate);
        return;
    }
    calendarState.selectedDate = addMonths(calendarState.selectedDate, direction);
    calendarState.miniDate = startOfCalendarMonth(calendarState.selectedDate);
}

function getCalendarHourBounds(shifts) {
    if (!shifts || shifts.length === 0) {
        return { startHour: 8, endHour: 18 };
    }

    let minHour = 23;
    let maxHour = 0;
    shifts.forEach((shift) => {
        const startHour = shift.startDate.getHours() + (shift.startDate.getMinutes() / 60);
        const visualEnd = getCalendarDisplayEndDate(shift);
        const endHour = visualEnd.getHours() + (visualEnd.getMinutes() / 60) + (visualEnd.getSeconds() / 3600);
        minHour = Math.min(minHour, Math.floor(startHour));
        maxHour = Math.max(maxHour, Math.ceil(endHour));
    });

    minHour = Math.max(6, minHour - 1);
    maxHour = Math.min(24, maxHour + 1);
    if (maxHour - minHour < 8) {
        maxHour = Math.min(24, minHour + 8);
    }
    return { startHour: minHour, endHour: maxHour };
}

function renderCalendarRoleSummary(roles) {
    if (!Array.isArray(roles) || roles.length === 0) {
        return 'No roles available';
    }
    return roles.map((role) => `${role.role_title || 'Role'} (${role.filled_count || 0}/${role.required_count || 0})`).join(', ');
}

function resolveCalendarTimeBucket(date) {
    const hour = date.getHours();
    if (hour < 12) {
        return 'morning';
    }
    if (hour < 17) {
        return 'afternoon';
    }
    return 'evening';
}

function getCalendarPantryList() {
    return Array.isArray(allPublicPantries)
        ? [...allPublicPantries].sort((left, right) => String(left.name || '').localeCompare(String(right.name || '')))
        : [];
}

function getCalendarPantryNameById(pantryId) {
    const pantry = getCalendarPantryList().find((item) => intValue(item.pantry_id) === intValue(pantryId));
    return pantry ? pantry.name : '';
}

function getCalendarPantryPalette(pantryId) {
    const normalizedId = Math.abs(intValue(pantryId));
    return CALENDAR_COLOR_PALETTE[normalizedId % CALENDAR_COLOR_PALETTE.length];
}

function capitalizeCalendarLabel(value) {
    const normalized = String(value || '').trim();
    return normalized ? normalized.charAt(0).toUpperCase() + normalized.slice(1) : '';
}

function intValue(value) {
    return parseInt(String(value || '0'), 10) || 0;
}

function startOfCalendarDay(value) {
    const date = new Date(value);
    date.setHours(0, 0, 0, 0);
    return date;
}

function endOfCalendarDay(value) {
    const date = startOfCalendarDay(value);
    date.setHours(23, 59, 59, 999);
    return date;
}

function startOfCalendarWeek(value) {
    const date = startOfCalendarDay(value);
    const dayIndex = (date.getDay() + 6) % 7;
    date.setDate(date.getDate() - dayIndex);
    return date;
}

function startOfCalendarMonth(value) {
    const date = startOfCalendarDay(value);
    date.setDate(1);
    return date;
}

function addDays(value, amount) {
    const date = new Date(value);
    date.setDate(date.getDate() + amount);
    return date;
}

function addMonths(value, amount) {
    const date = new Date(value);
    const previousDay = date.getDate();
    date.setDate(1);
    date.setMonth(date.getMonth() + amount);
    date.setDate(Math.min(previousDay, new Date(date.getFullYear(), date.getMonth() + 1, 0).getDate()));
    return date;
}

function getCalendarDateKey(date) {
    const normalized = startOfCalendarDay(date);
    const year = normalized.getFullYear();
    const month = String(normalized.getMonth() + 1).padStart(2, '0');
    const day = String(normalized.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

function parseCalendarDateKey(value) {
    if (!value) {
        return null;
    }
    const date = new Date(`${value}T00:00:00`);
    return Number.isNaN(date.getTime()) ? null : startOfCalendarDay(date);
}

function isSameCalendarDay(left, right) {
    return getCalendarDateKey(left) === getCalendarDateKey(right);
}

function formatCalendarDateLabel(value, options = {}) {
    const date = getDateInstance(value);
    if (!date) {
        return '';
    }

    const formatterOptions = { timeZone: getDisplayTimeZone() };
    if (options.weekday !== undefined) formatterOptions.weekday = options.weekday;
    if (options.month !== undefined) formatterOptions.month = options.month;
    if (options.day !== undefined) formatterOptions.day = options.day;
    if (options.year !== undefined) formatterOptions.year = options.year;
    return new Intl.DateTimeFormat('en-US', formatterOptions).format(date);
}

function formatCalendarHourLabel(value) {
    const date = getDateInstance(value);
    if (!date) {
        return '';
    }

    return new Intl.DateTimeFormat('en-US', {
        timeZone: getDisplayTimeZone(),
        hour: 'numeric',
        minute: '2-digit',
        hour12: true
    }).format(date);
}

window.initializeCalendarUi = initializeCalendarUi;
window.loadCalendarShifts = loadCalendarShifts;
window.syncCalendarPantryOptions = syncCalendarPantryOptions;
