ALTER TABLE shift_signups
ADD COLUMN IF NOT EXISTS advance_reminder_sent_at DATETIME(6) NULL AFTER signup_status;
