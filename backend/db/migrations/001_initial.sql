CREATE TABLE IF NOT EXISTS roles (
  role_id INT AUTO_INCREMENT PRIMARY KEY,
  role_name VARCHAR(64) NOT NULL UNIQUE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS users (
  user_id INT AUTO_INCREMENT PRIMARY KEY,
  full_name VARCHAR(255) NOT NULL,
  email VARCHAR(255) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  attendance_score INT NOT NULL DEFAULT 100,
  created_at DATETIME(6) NOT NULL,
  updated_at DATETIME(6) NOT NULL
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

CREATE TABLE IF NOT EXISTS shifts (
  shift_id INT AUTO_INCREMENT PRIMARY KEY,
  pantry_id INT NOT NULL,
  shift_name VARCHAR(255) NOT NULL,
  start_time DATETIME(6) NOT NULL,
  end_time DATETIME(6) NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'OPEN',
  created_by INT NOT NULL,
  created_at DATETIME(6) NOT NULL,
  updated_at DATETIME(6) NOT NULL,
  INDEX idx_shifts_pantry_id (pantry_id),
  CONSTRAINT fk_shifts_pantry
    FOREIGN KEY (pantry_id) REFERENCES pantries(pantry_id)
    ON DELETE CASCADE,
  CONSTRAINT fk_shifts_created_by
    FOREIGN KEY (created_by) REFERENCES users(user_id)
    ON DELETE RESTRICT
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
  created_at DATETIME(6) NOT NULL,
  UNIQUE KEY uq_shift_signups_role_user (shift_role_id, user_id),
  INDEX idx_shift_signups_shift_role_id (shift_role_id),
  INDEX idx_shift_signups_user_id (user_id),
  CONSTRAINT fk_shift_signups_role
    FOREIGN KEY (shift_role_id) REFERENCES shift_roles(shift_role_id)
    ON DELETE CASCADE,
  CONSTRAINT fk_shift_signups_user
    FOREIGN KEY (user_id) REFERENCES users(user_id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
