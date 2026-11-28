CREATE TABLE lab_admission (
  lease TEXT PRIMARY KEY NOT NULL,
  started INTEGER NOT NULL,
  active INTEGER NOT NULL CHECK(active IN (0, 1))
);
