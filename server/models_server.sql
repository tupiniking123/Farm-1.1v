
-- users + farms + memberships
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS farms (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  owner_user_id TEXT NOT NULL,
  currency TEXT NOT NULL DEFAULT 'BRL',
  timezone TEXT NOT NULL DEFAULT 'America/Sao_Paulo',
  created_at TEXT NOT NULL,
  FOREIGN KEY (owner_user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS memberships (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  farm_id TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('OWNER','ADMIN','MANAGER','STAFF','VIEWER')),
  created_at TEXT NOT NULL,
  UNIQUE(user_id, farm_id),
  FOREIGN KEY (user_id) REFERENCES users(id),
  FOREIGN KEY (farm_id) REFERENCES farms(id)
);

CREATE TABLE IF NOT EXISTS farm_invites (
  code TEXT PRIMARY KEY,
  farm_id TEXT NOT NULL,
  created_by_user_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  expires_at TEXT,
  FOREIGN KEY (farm_id) REFERENCES farms(id),
  FOREIGN KEY (created_by_user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS sync_log (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  device_id TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Core tables (same columns as client, with updated_at as truth)
CREATE TABLE IF NOT EXISTS categories (
  id TEXT PRIMARY KEY,
  farm_id TEXT NOT NULL,
  name TEXT NOT NULL,
  is_direct_cost INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS income (
  id TEXT PRIMARY KEY,
  farm_id TEXT NOT NULL,
  date TEXT NOT NULL,
  description TEXT,
  amount REAL NOT NULL,
  source TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS expense (
  id TEXT PRIMARY KEY,
  farm_id TEXT NOT NULL,
  date TEXT NOT NULL,
  category_id TEXT,
  description TEXT,
  amount REAL NOT NULL,
  vendor TEXT,
  is_unplanned INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS inventory_items (
  id TEXT PRIMARY KEY,
  farm_id TEXT NOT NULL,
  name TEXT NOT NULL,
  type TEXT NOT NULL CHECK (type IN ('FEED','INPUT','VACCINE')),
  unit TEXT NOT NULL,
  min_level REAL NOT NULL DEFAULT 0,
  expires_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS inventory_movements (
  id TEXT PRIMARY KEY,
  farm_id TEXT NOT NULL,
  item_id TEXT NOT NULL,
  date TEXT NOT NULL,
  qty REAL NOT NULL,
  cost_total REAL NOT NULL DEFAULT 0,
  movement_type TEXT NOT NULL CHECK (movement_type IN ('IN','OUT')),
  note TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS cattle (
  id TEXT PRIMARY KEY,
  farm_id TEXT NOT NULL,
  tag TEXT NOT NULL,
  birth_date TEXT,
  notes TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS vaccinations (
  id TEXT PRIMARY KEY,
  farm_id TEXT NOT NULL,
  cattle_id TEXT NOT NULL,
  vaccine_item_id TEXT NOT NULL,
  date TEXT NOT NULL,
  dose TEXT,
  cost REAL NOT NULL DEFAULT 0,
  next_due_date TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  deleted_at TEXT
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_memberships_user ON memberships(user_id);
CREATE INDEX IF NOT EXISTS idx_memberships_farm ON memberships(farm_id);

CREATE INDEX IF NOT EXISTS idx_income_farm_date ON income(farm_id, date);
CREATE INDEX IF NOT EXISTS idx_income_farm_updated ON income(farm_id, updated_at);

CREATE INDEX IF NOT EXISTS idx_expense_farm_date ON expense(farm_id, date);
CREATE INDEX IF NOT EXISTS idx_expense_farm_updated ON expense(farm_id, updated_at);

CREATE INDEX IF NOT EXISTS idx_items_farm_updated ON inventory_items(farm_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_movements_farm_updated ON inventory_movements(farm_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_cattle_farm_updated ON cattle(farm_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_vacc_farm_updated ON vaccinations(farm_id, updated_at);
