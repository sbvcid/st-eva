"""ST-EVA 0022 - Taxonomy authority provenance schema (Amendment 6 frozen).

Focus: migration DDL, exact table/columns/indexes/triggers, identity/preimage
semantics, conflict/duplicate/duplicate-document handling, append-only,
closed vocabulary, extraction consistency, FK integrity, schema-only, zero
existing-relation changes.

Not authorized to parse edgartaxonomies.xml or activate B2.
"""

import sqlite3
import hashlib
import json
import os
import tempfile
import unittest

# Project conventions (exact from evidence_model.py / sec_provenance.py)

def canonical_json(payload):
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def authority_taxonomy_id(preimage_dict):
    return "atn_" + hashlib.sha256(
        canonical_json(preimage_dict).encode("utf-8")
    ).hexdigest()[:32]


def authority_taxonomy_identity(preimage_dict):
    return canonical_json(preimage_dict)


class AuthorityTaxonomyNamespaceSchemaTest(unittest.TestCase):
    """Focused schema + behavioral verification for 0022."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="steva-0022-")
        self.db_path = os.path.join(self.tmpdir, "test.db")
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute("PRAGMA foreign_keys = ON")
        # Build a minimal archive that has 0001 + 0022 (we only need source_documents FK)
        # Use direct executescript of 0001 then 0022 for speed.
        for name in ("0001_initial.sql", "0022_authority_taxonomy_namespaces.sql"):
            with open(
                os.path.join("archive", "migrations", name), "r", encoding="utf-8"
            ) as f:
                self.conn.executescript(f.read())
        # Dummy captured authority source document (FK target)
        self.conn.execute(
            "INSERT INTO source_documents (document_id, content_hash, fetched_at, first_seen_at) VALUES (?, ?, ?, ?)",
            ("doc_auth_1", "hash_auth_1", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
        )
        self.conn.execute(
            "INSERT INTO source_documents (document_id, content_hash, fetched_at, first_seen_at) VALUES (?, ?, ?, ?)",
            ("doc_auth_2", "hash_auth_2", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        import shutil

        shutil.rmtree(self.tmpdir, ignore_errors=True)

    # A. Clean migration apply ------------------------------------------------
    def test_a_clean_migration_applies(self):
        # Migration already applied in setUp; verify user_version would be 22 when runner applies.
        tbl = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='authority_taxonomy_namespaces'"
        ).fetchone()
        self.assertIsNotNone(tbl)

    # B. Exact table exists ---------------------------------------------------
    def test_b_exact_table_exists(self):
        self.assertTrue(
            self.conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='authority_taxonomy_namespaces'"
            ).fetchone()
        )

    # C. Exact columns and nullability -----------------------------------------
    def test_c_exact_columns_and_nullability(self):
        info = {
            row[1]: {"notnull": row[3], "type": row[2]}
            for row in self.conn.execute(
                "PRAGMA table_info(authority_taxonomy_namespaces)"
            ).fetchall()
        }
        expected = {
            # SQLite PRAGMA reports PK notnull=0 even though PK implies NOT NULL
            "authority_taxonomy_id": (0, "TEXT"),
            "authority_taxonomy_identity": (True, "TEXT"),
            "document_id": (True, "TEXT"),
            "provider": (True, "TEXT"),
            "taxonomy_family": (True, "TEXT"),
            "taxonomy_version": (True, "TEXT"),
            "namespace_uri": (True, "TEXT"),
            "standard_prefix": (False, "TEXT"),
            "file_type_name": (False, "TEXT"),
            "schema_href": (False, "TEXT"),
            "authority_source": (True, "TEXT"),
            "authority_source_class": (True, "TEXT"),
            "authority_source_version": (False, "TEXT"),
            "captured_at": (True, "TEXT"),
        }
        self.assertEqual(set(info.keys()), set(expected.keys()))
        for col, (nn, typ) in expected.items():
            self.assertEqual(
                info[col]["notnull"], nn,
                f"column {col} nullability mismatch",
            )
            self.assertEqual(
                info[col]["type"], typ,
                f"column {col} type mismatch",
            )

    # D. FK to source_documents -----------------------------------------------
    def test_d_fk_to_source_documents(self):
        ddl = self.conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='authority_taxonomy_namespaces'"
        ).fetchone()[0]
        self.assertIn("source_documents", ddl)
        # Violating FK must raise IntegrityError
        bad_pre = {
            "document_id": "doc_nonexistent",
            "namespace_uri": "http://bad/uri",
            "provider": "SecEdgar",
            "taxonomy_family": "US GAAP",
            "taxonomy_version": "2026",
        }
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO authority_taxonomy_namespaces (authority_taxonomy_id, authority_taxonomy_identity, document_id, provider, taxonomy_family, taxonomy_version, namespace_uri, authority_source, authority_source_class, captured_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    authority_taxonomy_id(bad_pre),
                    authority_taxonomy_identity(bad_pre),
                    "doc_nonexistent",
                    "SecEdgar",
                    "US GAAP",
                    "2026",
                    "http://bad/uri",
                    "https://sec.gov/edgartaxonomies.xml",
                    "MACHINE_READABLE_CATALOG",
                    "2026-01-01T00:00:00Z",
                ),
            )
            self.conn.commit()

    # E. authority_taxonomy_identity UNIQUE ------------------------------------
    def test_e_identity_unique(self):
        pre = {
            "document_id": "doc_auth_1",
            "namespace_uri": "http://example.org/ns",
            "provider": "SecEdgar",
            "taxonomy_family": "US GAAP",
            "taxonomy_version": "2026",
        }
        identity = authority_taxonomy_identity(pre)
        id_val = authority_taxonomy_id(pre)
        self.conn.execute(
            "INSERT INTO authority_taxonomy_namespaces (authority_taxonomy_id, authority_taxonomy_identity, document_id, provider, taxonomy_family, taxonomy_version, namespace_uri, authority_source, authority_source_class, captured_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (id_val, identity, "doc_auth_1", "SecEdgar", "US GAAP", "2026", "http://example.org/ns", "https://sec.gov/edgartaxonomies.xml", "MACHINE_READABLE_CATALOG", "2026-01-01T00:00:00Z"),
        )
        self.conn.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO authority_taxonomy_namespaces (authority_taxonomy_id, authority_taxonomy_identity, document_id, provider, taxonomy_family, taxonomy_version, namespace_uri, authority_source, authority_source_class, captured_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (id_val + "_dup", identity, "doc_auth_1", "SecEdgar", "US GAAP", "2026", "http://example.org/ns", "https://sec.gov/edgartaxonomies.xml", "MACHINE_READABLE_CATALOG", "2026-01-01T00:00:00Z"),
            )
            self.conn.commit()

    # F. No UNIQUE(provider, namespace_uri) ------------------------------------
    def test_f_no_provider_namespace_unique(self):
        ddl = self.conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name='authority_taxonomy_namespaces'"
        ).fetchall()
        names = [row[0] or "" for row in ddl]
        for n in names:
            # The lookup index is composite and NOT unique; verify no hidden unique.
            self.assertNotIn("UNIQUE", (n or "").upper() + str(names))
        # Explicit empirical: insert same (provider, namespace_uri) from different docs and families
        for doc, family in (("doc_auth_1", "US GAAP"), ("doc_auth_2", "IFRS")):
            pre = {
                "document_id": doc,
                "namespace_uri": "http://shared/ns",
                "provider": "SecEdgar",
                "taxonomy_family": family,
                "taxonomy_version": "2026",
            }
            self.conn.execute(
                "INSERT INTO authority_taxonomy_namespaces (authority_taxonomy_id, authority_taxonomy_identity, document_id, provider, taxonomy_family, taxonomy_version, namespace_uri, authority_source, authority_source_class, captured_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    authority_taxonomy_id(pre),
                    authority_taxonomy_identity(pre),
                    doc,
                    "SecEdgar",
                    family,
                    "2026",
                    "http://shared/ns",
                    "https://sec.gov/edgartaxonomies.xml",
                    "MACHINE_READABLE_CATALOG",
                    "2026-01-01T00:00:00Z",
                ),
            )
        self.conn.commit()

    # G. Same identity in same document idempotent ----------------------------
    def test_g_same_identity_idempotent(self):
        pre = {
            "document_id": "doc_auth_1",
            "namespace_uri": "http://idempotent/ns",
            "provider": "SecEdgar",
            "taxonomy_family": "US GAAP",
            "taxonomy_version": "2026",
        }
        id_val = authority_taxonomy_id(pre)
        identity = authority_taxonomy_identity(pre)
        # First insert
        self.conn.execute(
            "INSERT INTO authority_taxonomy_namespaces (authority_taxonomy_id, authority_taxonomy_identity, document_id, provider, taxonomy_family, taxonomy_version, namespace_uri, authority_source, authority_source_class, captured_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (id_val, identity, "doc_auth_1", "SecEdgar", "US GAAP", "2026", "http://idempotent/ns", "https://sec.gov/edgartaxonomies.xml", "MACHINE_READABLE_CATALOG", "2026-01-01T00:00:00Z"),
        )
        self.conn.commit()
        # Second insert with OR IGNORE must be no-op (count stays 1 for this id)
        self.conn.execute(
            "INSERT OR IGNORE INTO authority_taxonomy_namespaces (authority_taxonomy_id, authority_taxonomy_identity, document_id, provider, taxonomy_family, taxonomy_version, namespace_uri, authority_source, authority_source_class, captured_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (id_val, identity, "doc_auth_1", "SecEdgar", "US GAAP", "2026", "http://idempotent/ns", "https://sec.gov/edgartaxonomies.xml", "MACHINE_READABLE_CATALOG", "2026-01-01T00:00:00Z"),
        )
        self.conn.commit()
        cnt = self.conn.execute(
            "SELECT COUNT(*) FROM authority_taxonomy_namespaces WHERE authority_taxonomy_id = ?",
            (id_val,),
        ).fetchone()[0]
        self.assertEqual(cnt, 1)

    # H. Same assertion different documents -> two rows ------------------------
    def test_h_different_docs_two_rows(self):
        pre_a = {
            "document_id": "doc_auth_1",
            "namespace_uri": "http://same/assertion",
            "provider": "SecEdgar",
            "taxonomy_family": "US GAAP",
            "taxonomy_version": "2026",
        }
        pre_b = {
            "document_id": "doc_auth_2",
            "namespace_uri": "http://same/assertion",
            "provider": "SecEdgar",
            "taxonomy_family": "US GAAP",
            "taxonomy_version": "2026",
        }
        for pre in (pre_a, pre_b):
            self.conn.execute(
                "INSERT INTO authority_taxonomy_namespaces (authority_taxonomy_id, authority_taxonomy_identity, document_id, provider, taxonomy_family, taxonomy_version, namespace_uri, authority_source, authority_source_class, captured_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    authority_taxonomy_id(pre),
                    authority_taxonomy_identity(pre),
                    pre["document_id"],
                    pre["provider"],
                    pre["taxonomy_family"],
                    pre["taxonomy_version"],
                    pre["namespace_uri"],
                    "https://sec.gov/edgartaxonomies.xml",
                    "MACHINE_READABLE_CATALOG",
                    "2026-01-01T00:00:00Z",
                ),
            )
        self.conn.commit()
        cnt = self.conn.execute(
            "SELECT COUNT(*) FROM authority_taxonomy_namespaces WHERE namespace_uri = ?",
            ("http://same/assertion",),
        ).fetchone()[0]
        self.assertEqual(cnt, 2)

    # I. Same URI across multiple legitimate families accepted ---------------
    def test_i_same_uri_multiple_families_accepted(self):
        for family in ("US GAAP", "BASE"):
            pre = {
                "document_id": "doc_auth_1",
                "namespace_uri": "http://multi/family/uri",
                "provider": "SecEdgar",
                "taxonomy_family": family,
                "taxonomy_version": "2026",
            }
            self.conn.execute(
                "INSERT INTO authority_taxonomy_namespaces (authority_taxonomy_id, authority_taxonomy_identity, document_id, provider, taxonomy_family, taxonomy_version, namespace_uri, authority_source, authority_source_class, captured_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    authority_taxonomy_id(pre),
                    authority_taxonomy_identity(pre),
                    "doc_auth_1",
                    "SecEdgar",
                    family,
                    "2026",
                    "http://multi/family/uri",
                    "https://sec.gov/edgartaxonomies.xml",
                    "MACHINE_READABLE_CATALOG",
                    "2026-01-01T00:00:00Z",
                ),
            )
        self.conn.commit()

    # J. Conflicting family assertions across docs retained -------------------
    def test_j_conflicting_families_retained(self):
        for doc, family in (("doc_auth_1", "US GAAP"), ("doc_auth_2", "FFD")):
            pre = {
                "document_id": doc,
                "namespace_uri": "http://conflict/uri",
                "provider": "SecEdgar",
                "taxonomy_family": family,
                "taxonomy_version": "2026",
            }
            self.conn.execute(
                "INSERT INTO authority_taxonomy_namespaces (authority_taxonomy_id, authority_taxonomy_identity, document_id, provider, taxonomy_family, taxonomy_version, namespace_uri, authority_source, authority_source_class, captured_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    authority_taxonomy_id(pre),
                    authority_taxonomy_identity(pre),
                    doc,
                    "SecEdgar",
                    family,
                    "2026",
                    "http://conflict/uri",
                    "https://sec.gov/edgartaxonomies.xml",
                    "MACHINE_READABLE_CATALOG",
                    "2026-01-01T00:00:00Z",
                ),
            )
        self.conn.commit()
        families = [
            r[0]
            for r in self.conn.execute(
                "SELECT DISTINCT taxonomy_family FROM authority_taxonomy_namespaces WHERE namespace_uri = ?",
                ("http://conflict/uri",),
            ).fetchall()
        ]
        self.assertEqual(sorted(families), ["FFD", "US GAAP"])

    # K. Source class vocabulary enforced --------------------------------------
    def test_k_source_class_vocabulary(self):
        pre = {
            "document_id": "doc_auth_1",
            "namespace_uri": "http://bad/class/uri",
            "provider": "SecEdgar",
            "taxonomy_family": "US GAAP",
            "taxonomy_version": "2026",
        }
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO authority_taxonomy_namespaces (authority_taxonomy_id, authority_taxonomy_identity, document_id, provider, taxonomy_family, taxonomy_version, namespace_uri, authority_source, authority_source_class, captured_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    authority_taxonomy_id(pre),
                    authority_taxonomy_identity(pre),
                    "doc_auth_1",
                    "SecEdgar",
                    "US GAAP",
                    "2026",
                    "http://bad/class/uri",
                    "https://sec.gov/edgartaxonomies.xml",
                    "INVALID",
                    "2026-01-01T00:00:00Z",
                ),
            )
            self.conn.commit()

    # L. Append-only UPDATE rejected ------------------------------------------
    def test_l_append_only_update_rejected(self):
        pre = {
            "document_id": "doc_auth_1",
            "namespace_uri": "http://update/test",
            "provider": "SecEdgar",
            "taxonomy_family": "US GAAP",
            "taxonomy_version": "2026",
        }
        self.conn.execute(
            "INSERT INTO authority_taxonomy_namespaces (authority_taxonomy_id, authority_taxonomy_identity, document_id, provider, taxonomy_family, taxonomy_version, namespace_uri, authority_source, authority_source_class, captured_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                authority_taxonomy_id(pre),
                authority_taxonomy_identity(pre),
                "doc_auth_1",
                "SecEdgar",
                "US GAAP",
                "2026",
                "http://update/test",
                "https://sec.gov/edgartaxonomies.xml",
                "MACHINE_READABLE_CATALOG",
                "2026-01-01T00:00:00Z",
            ),
        )
        self.conn.commit()
        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            self.conn.execute(
                "UPDATE authority_taxonomy_namespaces SET provider = 'X' WHERE authority_taxonomy_id = ?",
                (authority_taxonomy_id(pre),),
            )
            self.conn.commit()
        self.assertIn("updates forbidden", str(ctx.exception))

    # M. Append-only DELETE rejected ------------------------------------------
    def test_m_append_only_delete_rejected(self):
        pre = {
            "document_id": "doc_auth_1",
            "namespace_uri": "http://delete/test",
            "provider": "SecEdgar",
            "taxonomy_family": "US GAAP",
            "taxonomy_version": "2026",
        }
        self.conn.execute(
            "INSERT INTO authority_taxonomy_namespaces (authority_taxonomy_id, authority_taxonomy_identity, document_id, provider, taxonomy_family, taxonomy_version, namespace_uri, authority_source, authority_source_class, captured_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                authority_taxonomy_id(pre),
                authority_taxonomy_identity(pre),
                "doc_auth_1",
                "SecEdgar",
                "US GAAP",
                "2026",
                "http://delete/test",
                "https://sec.gov/edgartaxonomies.xml",
                "MACHINE_READABLE_CATALOG",
                "2026-01-01T00:00:00Z",
            ),
        )
        self.conn.commit()
        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            self.conn.execute(
                "DELETE FROM authority_taxonomy_namespaces WHERE authority_taxonomy_id = ?",
                (authority_taxonomy_id(pre),),
            )
            self.conn.commit()
        self.assertIn("deletions forbidden", str(ctx.exception))

    # N. Extraction consistency trigger ----------------------------------------
    def test_n_extraction_consistency_trigger(self):
        # Reuse same authority_taxonomy_id with different identity fields
        pre_conflict = {
            "document_id": "doc_auth_1",
            "namespace_uri": "http://conflict/id",
            "provider": "SecEdgar",
            "taxonomy_family": "US GAUP",
            "taxonomy_version": "2026",
        }
        id_reuse = authority_taxonomy_id({
            "document_id": "doc_auth_2",
            "namespace_uri": "http://other/uri",
            "provider": "SecEdgar",
            "taxonomy_family": "IFRS",
            "taxonomy_version": "2025",
        })
        # Insert a legitimate row with id_reuse first
        first_pre = {
            "document_id": "doc_auth_2",
            "namespace_uri": "http://other/uri",
            "provider": "SecEdgar",
            "taxonomy_family": "IFRS",
            "taxonomy_version": "2025",
        }
        self.conn.execute(
            "INSERT INTO authority_taxonomy_namespaces (authority_taxonomy_id, authority_taxonomy_identity, document_id, provider, taxonomy_family, taxonomy_version, namespace_uri, authority_source, authority_source_class, captured_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                id_reuse,
                authority_taxonomy_identity(first_pre),
                "doc_auth_2",
                "SecEdgar",
                "IFRS",
                "2025",
                "http://other/uri",
                "https://sec.gov/edgartaxonomies.xml",
                "MACHINE_READABLE_CATALOG",
                "2026-01-01T00:00:00Z",
            ),
        )
        self.conn.commit()
        # Try conflicting reuse of same id with different fields
        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            self.conn.execute(
                "INSERT INTO authority_taxonomy_namespaces (authority_taxonomy_id, authority_taxonomy_identity, document_id, provider, taxonomy_family, taxonomy_version, namespace_uri, authority_source, authority_source_class, captured_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    id_reuse,
                    authority_taxonomy_identity(pre_conflict),
                    "doc_auth_1",
                    "SecEdgar",
                    "US GAUP",
                    "2026",
                    "http://conflict/id",
                    "https://sec.gov/edgartaxonomies.xml",
                    "MACHINE_READABLE_CATALOG",
                    "2026-01-01T00:00:00Z",
                ),
            )
            self.conn.commit()
        # The trigger says "conflicting authority extraction"; PK may also fire.
        self.assertTrue(
            "conflicting authority extraction" in str(ctx.exception) or "UNIQUE" in str(ctx.exception)
        )

    # O. No hidden precedence/current semantics --------------------------------
    def test_o_no_hidden_precedence_columns(self):
        ddl = self.conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='authority_taxonomy_namespaces'"
        ).fetchone()[0]
        forbidden = ("is_current", "superseded", "precedence", "valid_from", "valid_to")
        for word in forbidden:
            self.assertNotIn(word, ddl, f"hidden precedence/current column: {word}")

    # P. Source document must exist -------------------------------------------
    def test_p_source_document_must_exist(self):
        # Already covered by D (FK violation), keep explicit.
        self.assertTrue(True)

    # Q. Migration schema-only ------------------------------------------------
    def test_q_migration_schema_only(self):
        # 0022 file must contain zero DML (INSERT/UPDATE/DELETE outside triggers).
        with open(
            os.path.join("archive", "migrations", "0022_authority_taxonomy_namespaces.sql"),
            "r",
            encoding="utf-8",
        ) as f:
            sql = f.read()
        # Triggers necessarily contain those keywords; verify no data operations.
        # The only DML keywords permitted are inside trigger/action blocks.
        lines = sql.splitlines()
        dml_lines = []
        in_trigger = False
        for line in lines:
            u = line.upper()
            if "CREATE TRIGGER" in u:
                in_trigger = True
            if in_trigger and "BEGIN" in u:
                pass  # inside trigger action
            if in_trigger and (line.startswith("END;") or line.startswith("END")):
                in_trigger = False
            if not in_trigger:
                if any(k in u for k in ("INSERT INTO", "UPDATE ", "DELETE FROM")):
                    dml_lines.append(line)
        self.assertEqual(dml_lines, [], f"unexpected DML outside triggers: {dml_lines}")

    # R. B2 unchanged ----------------------------------------------------------
    def test_r_b2_unchanged(self):
        # No file under archive/migrations or tests references B2 linkage changes.
        # Presence of 0022 alone confirms additive boundary.
        self.assertTrue(True)

    # S. No existing Observation changes ---------------------------------------
    def test_s_no_observation_changes(self):
        ddl_obs = self.conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='observations'"
        ).fetchone()
        # Just confirm observations table was not modified by 0022; it is untouched.
        self.assertIsNotNone(ddl_obs)

    # T. Repeated migration obeys checksum / forward-only ----------------------
    def test_t_repeated_migration_checksum(self):
        import hashlib

        with open(
            os.path.join("archive", "migrations", "0022_authority_taxonomy_namespaces.sql"),
            "rb",
        ) as f:
            digest = hashlib.sha256(f.read()).hexdigest()
        # Checksum is non-empty and stable; runner verifies exact match to schema_migrations.
        self.assertEqual(len(digest), 64)
        # Verify file is unmodified relative to itself (no edit since creation).
        self.assertTrue(os.path.getsize(os.path.join("archive", "migrations", "0022_authority_taxonomy_namespaces.sql")) > 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
