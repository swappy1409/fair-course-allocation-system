"""Tests never touch the real beta database: they get a throwaway data directory."""
import os
import tempfile

os.environ["FCA_DATA_DIR"] = tempfile.mkdtemp(prefix="fca-test-")
os.environ["ADMIN_SECRET"] = "test-admin-secret-123"
