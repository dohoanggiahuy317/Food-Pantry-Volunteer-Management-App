CREATE TABLE IF NOT EXISTS google_calendar_connections (
  user_id INT PRIMARY KEY,
  google_subject VARCHAR(255) NULL,
  google_email VARCHAR(255) NULL,
  scopes_csv TEXT NULL,
  refresh_token TEXT NULL,
  access_token TEXT NULL,
  token_expires_at DATETIME(6) NULL,
  created_at DATETIME(6) NOT NULL,
  updated_at DATETIME(6) NOT NULL,
  CONSTRAINT fk_google_calendar_connections_user
    FOREIGN KEY (user_id) REFERENCES users(user_id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS google_calendar_event_links (
  signup_id INT PRIMARY KEY,
  user_id INT NOT NULL,
  calendar_id VARCHAR(255) NOT NULL DEFAULT 'primary',
  google_event_id VARCHAR(255) NOT NULL,
  created_at DATETIME(6) NOT NULL,
  updated_at DATETIME(6) NOT NULL,
  INDEX idx_google_calendar_event_links_user_id (user_id),
  CONSTRAINT fk_google_calendar_event_links_signup
    FOREIGN KEY (signup_id) REFERENCES shift_signups(signup_id)
    ON DELETE CASCADE,
  CONSTRAINT fk_google_calendar_event_links_user
    FOREIGN KEY (user_id) REFERENCES users(user_id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
