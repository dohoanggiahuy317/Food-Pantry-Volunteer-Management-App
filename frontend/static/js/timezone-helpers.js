const DEFAULT_APP_TIMEZONE = 'America/New_York';

function isValidBrowserTimeZone(timeZone) {
    if (!timeZone || typeof timeZone !== 'string') {
        return false;
    }

    try {
        new Intl.DateTimeFormat('en-US', { timeZone });
        return true;
    } catch (_error) {
        return false;
    }
}

function getBrowserTimeZone() {
    const detected = Intl.DateTimeFormat().resolvedOptions().timeZone;
    return isValidBrowserTimeZone(detected) ? detected : DEFAULT_APP_TIMEZONE;
}

function getDisplayTimeZone(timeZone = null) {
    return isValidBrowserTimeZone(timeZone) ? timeZone : getBrowserTimeZone();
}

function getDateInstance(value) {
    if (!value) {
        return null;
    }

    const date = value instanceof Date ? value : new Date(value);
    return Number.isNaN(date.getTime()) ? null : date;
}

function getTimeZoneShortLabel(value = new Date(), timeZone = null) {
    const date = getDateInstance(value);
    if (!date) {
        return '';
    }

    const formatter = new Intl.DateTimeFormat('en-US', {
        timeZone: getDisplayTimeZone(timeZone),
        timeZoneName: 'short'
    });
    const part = formatter.formatToParts(date).find((item) => item.type === 'timeZoneName');
    return part ? part.value : getDisplayTimeZone(timeZone);
}

function formatTimeZoneDisplay(timeZone = null, value = new Date()) {
    const resolvedTimeZone = getDisplayTimeZone(timeZone);
    const shortLabel = getTimeZoneShortLabel(value, resolvedTimeZone);
    return shortLabel ? `${resolvedTimeZone} (${shortLabel})` : resolvedTimeZone;
}

function formatLocalDateTime(value, options = {}) {
    const date = getDateInstance(value);
    if (!date) {
        return '';
    }

    const includeTimeZone = options.includeTimeZone !== false;
    const formatter = new Intl.DateTimeFormat('en-US', {
        timeZone: getDisplayTimeZone(options.timeZone),
        month: options.month || 'short',
        day: options.day || 'numeric',
        year: options.year || 'numeric',
        hour: options.hour || 'numeric',
        minute: options.minute || '2-digit',
        hour12: options.hour12 !== false,
        timeZoneName: includeTimeZone ? 'short' : undefined
    });
    return formatter.format(date);
}

function formatLocalDate(value, options = {}) {
    const date = getDateInstance(value);
    if (!date) {
        return '';
    }

    const formatter = new Intl.DateTimeFormat('en-US', {
        timeZone: getDisplayTimeZone(options.timeZone),
        weekday: options.weekday,
        month: options.month || 'short',
        day: options.day || 'numeric',
        year: options.year || 'numeric'
    });
    return formatter.format(date);
}

function getLocalDateKeyForTimeZone(value, timeZone = null) {
    const date = getDateInstance(value);
    if (!date) {
        return '';
    }

    const formatter = new Intl.DateTimeFormat('en-CA', {
        timeZone: getDisplayTimeZone(timeZone),
        year: 'numeric',
        month: '2-digit',
        day: '2-digit'
    });
    return formatter.format(date);
}

function formatLocalTimeRange(startValue, endValue, options = {}) {
    const start = getDateInstance(startValue);
    const end = getDateInstance(endValue);
    if (!start || !end) {
        return 'Time unavailable';
    }

    const resolvedTimeZone = getDisplayTimeZone(options.timeZone);
    const dateLabel = formatLocalDate(start, {
        timeZone: resolvedTimeZone,
        weekday: options.includeWeekday ? 'short' : undefined
    });
    const timeFormatter = new Intl.DateTimeFormat('en-US', {
        timeZone: resolvedTimeZone,
        hour: 'numeric',
        minute: '2-digit',
        hour12: true
    });
    const sameLocalDay = getLocalDateKeyForTimeZone(start, resolvedTimeZone) === getLocalDateKeyForTimeZone(end, resolvedTimeZone);
    const startTime = timeFormatter.format(start);
    const endTime = timeFormatter.format(end);
    const startTimeZoneLabel = getTimeZoneShortLabel(start, resolvedTimeZone);
    const endTimeZoneLabel = getTimeZoneShortLabel(end, resolvedTimeZone);
    let timeZoneLabel = '';
    if (options.includeTimeZone !== false) {
        if (startTimeZoneLabel && endTimeZoneLabel && startTimeZoneLabel !== endTimeZoneLabel) {
            timeZoneLabel = ` ${startTimeZoneLabel} / ${endTimeZoneLabel}`;
        } else {
            timeZoneLabel = ` ${startTimeZoneLabel || endTimeZoneLabel}`;
        }
    }

    if (sameLocalDay && options.includeDate === false) {
        return `${startTime} - ${endTime}${timeZoneLabel}`.trim();
    }

    if (!sameLocalDay) {
        const endDateLabel = formatLocalDate(end, {
            timeZone: resolvedTimeZone,
            weekday: options.includeWeekday ? 'short' : undefined
        });
        return `${dateLabel}, ${startTime} - ${endDateLabel}, ${endTime}${timeZoneLabel}`.trim();
    }

    return `${dateLabel} | ${startTime} - ${endTime}${timeZoneLabel}`.trim();
}

function formatDateTimeForLocalInput(value) {
    const date = getDateInstance(value);
    if (!date) {
        return '';
    }

    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const hour = String(date.getHours()).padStart(2, '0');
    const minute = String(date.getMinutes()).padStart(2, '0');
    return `${year}-${month}-${day}T${hour}:${minute}`;
}
