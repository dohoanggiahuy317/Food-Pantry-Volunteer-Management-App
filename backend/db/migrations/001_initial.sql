CREATE TABLE IF NOT EXISTS roles (
  role_id INT PRIMARY KEY,
  role_name VARCHAR(64) NOT NULL UNIQUE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS users (
  user_id INT AUTO_INCREMENT PRIMARY KEY,
  full_name VARCHAR(255) NOT NULL,
  email VARCHAR(255) NOT NULL UNIQUE,
  phone_number VARCHAR(32) NULL,
  timezone VARCHAR(64) NULL,
  auth_provider VARCHAR(64) NULL,
  auth_uid VARCHAR(255) NULL,
  attendance_score INT NOT NULL DEFAULT 100,
  created_at DATETIME(6) NOT NULL,
  updated_at DATETIME(6) NOT NULL,
  UNIQUE KEY idx_users_auth_uid (auth_uid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS user_roles (
  user_id INT NOT NULL,
  role_id INT NOT NULL,
  PRIMARY KEY (user_id, role_id),
  INDEX idx_user_roles_user_id (user_id),
  CONSTRAINT fk_user_roles_user
    FOREIGN KEY (user_id) REFERENCES users(user_id)
    ON DELETE CASCADE,
  CONSTRAINT fk_user_roles_role
    FOREIGN KEY (role_id) REFERENCES roles(role_id)
    ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS pantries (
  pantry_id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(255) NOT NULL,
  location_address VARCHAR(512) NOT NULL,
  created_at DATETIME(6) NOT NULL,
  updated_at DATETIME(6) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS pantry_leads (
  pantry_id INT NOT NULL,
  user_id INT NOT NULL,
  PRIMARY KEY (pantry_id, user_id),
  INDEX idx_pantry_leads_user_id (user_id),
  CONSTRAINT fk_pantry_leads_pantry
    FOREIGN KEY (pantry_id) REFERENCES pantries(pantry_id)
    ON DELETE CASCADE,
  CONSTRAINT fk_pantry_leads_user
    FOREIGN KEY (user_id) REFERENCES users(user_id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS pantry_subscriptions (
  pantry_id INT NOT NULL,
  user_id INT NOT NULL,
  created_at DATETIME(6) NOT NULL,
  PRIMARY KEY (pantry_id, user_id),
  INDEX idx_pantry_subscriptions_user_id (user_id),
  CONSTRAINT fk_pantry_subscriptions_pantry
    FOREIGN KEY (pantry_id) REFERENCES pantries(pantry_id)
    ON DELETE CASCADE,
  CONSTRAINT fk_pantry_subscriptions_user
    FOREIGN KEY (user_id) REFERENCES users(user_id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS shift_series (
  shift_series_id INT AUTO_INCREMENT PRIMARY KEY,
  pantry_id INT NOT NULL,
  created_by INT NULL,
  timezone VARCHAR(64) NOT NULL,
  frequency VARCHAR(32) NOT NULL DEFAULT 'WEEKLY',
  interval_weeks INT NOT NULL DEFAULT 1,
  weekdays_csv VARCHAR(64) NOT NULL,
  end_mode VARCHAR(16) NOT NULL,
  occurrence_count INT NULL,
  until_date DATE NULL,
  created_at DATETIME(6) NOT NULL,
  updated_at DATETIME(6) NOT NULL,
  INDEX idx_shift_series_pantry_id (pantry_id),
  CONSTRAINT fk_shift_series_pantry
    FOREIGN KEY (pantry_id) REFERENCES pantries(pantry_id)
    ON DELETE CASCADE,
  CONSTRAINT fk_shift_series_created_by
    FOREIGN KEY (created_by) REFERENCES users(user_id)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS shifts (
  shift_id INT AUTO_INCREMENT PRIMARY KEY,
  pantry_id INT NOT NULL,
  shift_series_id INT NULL,
  series_position INT NULL,
  shift_name VARCHAR(255) NOT NULL,
  start_time DATETIME(6) NOT NULL,
  end_time DATETIME(6) NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'OPEN',
  created_by INT NULL,
  created_at DATETIME(6) NOT NULL,
  updated_at DATETIME(6) NOT NULL,
  INDEX idx_shifts_pantry_id (pantry_id),
  INDEX idx_shifts_shift_series_id (shift_series_id),
  CONSTRAINT fk_shifts_pantry
    FOREIGN KEY (pantry_id) REFERENCES pantries(pantry_id)
    ON DELETE CASCADE,
  CONSTRAINT fk_shifts_shift_series
    FOREIGN KEY (shift_series_id) REFERENCES shift_series(shift_series_id)
    ON DELETE SET NULL,
  CONSTRAINT fk_shifts_created_by
    FOREIGN KEY (created_by) REFERENCES users(user_id)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS shift_roles (
  shift_role_id INT AUTO_INCREMENT PRIMARY KEY,
  shift_id INT NOT NULL,
  role_title VARCHAR(255) NOT NULL,
  required_count INT NOT NULL,
  filled_count INT NOT NULL DEFAULT 0,
  status VARCHAR(32) NOT NULL DEFAULT 'OPEN',
  INDEX idx_shift_roles_shift_id (shift_id),
  CONSTRAINT fk_shift_roles_shift
    FOREIGN KEY (shift_id) REFERENCES shifts(shift_id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS shift_signups (
  signup_id INT AUTO_INCREMENT PRIMARY KEY,
  shift_role_id INT NOT NULL,
  user_id INT NOT NULL,
  signup_status VARCHAR(32) NOT NULL DEFAULT 'CONFIRMED',
  reservation_expires_at DATETIME(6) NULL,
  created_at DATETIME(6) NOT NULL,
  UNIQUE KEY uq_shift_signups_role_user (shift_role_id, user_id),
  INDEX idx_shift_signups_shift_role_id (shift_role_id),
  INDEX idx_shift_signups_user_id (user_id),
  INDEX idx_shift_signups_role_status_reservation (shift_role_id, signup_status, reservation_expires_at),
  CONSTRAINT fk_shift_signups_role
    FOREIGN KEY (shift_role_id) REFERENCES shift_roles(shift_role_id)
    ON DELETE CASCADE,
  CONSTRAINT fk_shift_signups_user
    FOREIGN KEY (user_id) REFERENCES users(user_id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS help_broadcasts (
  broadcast_id INT AUTO_INCREMENT PRIMARY KEY,
  shift_id INT NOT NULL,
  sender_user_id INT NOT NULL,
  recipient_count INT NOT NULL,
  created_at DATETIME(6) NOT NULL,
  INDEX idx_help_broadcasts_sender_created (sender_user_id, created_at),
  INDEX idx_help_broadcasts_shift_id (shift_id),
  CONSTRAINT fk_help_broadcasts_shift
    FOREIGN KEY (shift_id) REFERENCES shifts(shift_id)
    ON DELETE CASCADE,
  CONSTRAINT fk_help_broadcasts_sender
    FOREIGN KEY (sender_user_id) REFERENCES users(user_id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
