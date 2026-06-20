"""
Persistent Data Storage.

Problem: the person uploads Sales History, Inventory, and Invoices once a
week (Monday refresh), but the tool was re-asking for them every session.
This module writes uploaded files to a local disk folder (persisted/) so
they survive across browser sessions and app restarts -- you upload once
on Monday, and every session for the rest of the week reads the same
saved copy automatically.

This is disk-based, not a database -- appropriate for a single-operator
weekly-refresh workflow at $0 infrastructure cost. If this tool grows to
multiple concurrent users with different data, this would need to become
per-user storage; that's a real limitation worth knowing, not hidden.
"""
import os
import json
import shutil
from datetime import datetime
import pandas as pd

PERSIST_DIR = "persisted_data"
META_FILE = os.path.join(PERSIST_DIR, "_meta.json")

FILE_MAP = {
    "sales": "sales_history.xlsx",
    "inventory": "inventory_by_region.xlsx",
    "invoices": "shipment_invoices.xlsx",
}


def ensure_dir():
    os.makedirs(PERSIST_DIR, exist_ok=True)


def has_persisted_data():
    """True if all 3 required files exist on disk from a previous upload."""
    ensure_dir()
    return all(os.path.exists(os.path.join(PERSIST_DIR, fname)) for fname in FILE_MAP.values())


def save_uploaded_files(sales_file, inventory_file, invoices_file):
    """
    Saves uploaded file objects (from st.file_uploader) to disk, overwriting
    any previous week's data. Records the upload timestamp in metadata.
    """
    ensure_dir()
    uploads = {"sales": sales_file, "inventory": inventory_file, "invoices": invoices_file}

    for key, file_obj in uploads.items():
        if file_obj is None:
            continue
        dest_path = os.path.join(PERSIST_DIR, FILE_MAP[key])
        # file_obj from st.file_uploader is a BytesIO-like object; read once
        # and write to disk as the canonical .xlsx regardless of original
        # extension, so downstream readers always see a consistent format.
        if file_obj.name.endswith(".csv"):
            df = pd.read_csv(file_obj)
        else:
            df = pd.read_excel(file_obj)
        df.to_excel(dest_path, index=False)

    meta = {
        "uploaded_at": datetime.now().isoformat(),
        "uploaded_at_display": datetime.now().strftime("%A, %B %d, %Y at %I:%M %p"),
    }
    with open(META_FILE, "w") as f:
        json.dump(meta, f)


def load_persisted_data():
    """
    Returns (sales_df, inventory_df, invoices_df, meta_dict) from disk.
    Raises FileNotFoundError if data hasn't been uploaded yet -- caller
    should check has_persisted_data() first.
    """
    if not has_persisted_data():
        raise FileNotFoundError("No persisted data found. Upload files on the Setup page first.")

    sales_df = pd.read_excel(os.path.join(PERSIST_DIR, FILE_MAP["sales"]))
    inventory_df = pd.read_excel(os.path.join(PERSIST_DIR, FILE_MAP["inventory"]))
    invoices_df = pd.read_excel(os.path.join(PERSIST_DIR, FILE_MAP["invoices"]))

    meta = {"uploaded_at_display": "Unknown"}
    if os.path.exists(META_FILE):
        with open(META_FILE, "r") as f:
            meta = json.load(f)

    return sales_df, inventory_df, invoices_df, meta


def get_data_age_days():
    """Returns how many days old the persisted data is, or None if no data exists."""
    if not os.path.exists(META_FILE):
        return None
    with open(META_FILE, "r") as f:
        meta = json.load(f)
    uploaded_at = datetime.fromisoformat(meta["uploaded_at"])
    return (datetime.now() - uploaded_at).days


def clear_persisted_data():
    """Removes all persisted data -- used by the 'Replace Data' action."""
    if os.path.exists(PERSIST_DIR):
        shutil.rmtree(PERSIST_DIR)
    ensure_dir()
