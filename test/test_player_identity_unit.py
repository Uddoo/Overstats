from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
PARENT_DIR = REPO_ROOT.parent
for candidate in (PARENT_DIR, REPO_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

try:
    from overstats.src.db.match_stats import IDPoolDB, PLAYER_IDENTITY_TABLE
    from overstats.src.db.player_identity import (
        extract_identity_records,
        record_identity_payload,
        search_identity_by_bnet_id,
    )
except ModuleNotFoundError:
    from src.db.match_stats import IDPoolDB, PLAYER_IDENTITY_TABLE
    from src.db.player_identity import (
        extract_identity_records,
        record_identity_payload,
        search_identity_by_bnet_id,
    )


class PlayerIdentityExtractionTests(unittest.TestCase):
    def test_extract_identity_records_from_query_card_payload(self) -> None:
        rows = extract_identity_records(
            {
                "code": 0,
                "data": {
                    "bnetId": "12345",
                    "name": "GrowlR#5632",
                    "customerToken": "token-1",
                },
            }
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["bnetid"], "12345")
        self.assertEqual(rows[0]["battletag"], "GrowlR#5632")
        self.assertEqual(rows[0]["battlename"], "GrowlR")
        self.assertEqual(rows[0]["battlenum"], "5632")
        self.assertGreater(rows[0]["update_time"], 0)

    def test_extract_identity_records_from_match_detail_lists(self) -> None:
        payload = {
            "code": 0,
            "data": {
                "bnetId": "111",
                "name": "Target#1111",
                "teammateList": [
                    {"bnetId": "222", "name": "Buddy#2222"},
                    {"bnetId": "333", "userName": "Healer#3333"},
                ],
                "enemyList": [
                    {"bnetId": "444", "playerName": "Enemy#4444"},
                    {"bnetId": "222", "name": "Buddy#2222"},
                ],
            },
        }

        rows = sorted(extract_identity_records(payload), key=lambda item: item["bnetid"])

        self.assertEqual(
            [(row["bnetid"], row["battletag"]) for row in rows],
            [
                ("111", "Target#1111"),
                ("222", "Buddy#2222"),
                ("333", "Healer#3333"),
                ("444", "Enemy#4444"),
            ],
        )


class PlayerIdentityRecorderTests(unittest.IsolatedAsyncioTestCase):
    async def test_record_identity_payload_upserts_latest_player_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "match_stats.sqlite3"
            db = IDPoolDB(db_path)

            inserted = await record_identity_payload(
                {"code": 0, "data": {"bnetId": "12345", "name": "GrowlR#5632"}},
                db=db,
            )
            updated = await record_identity_payload(
                {"code": 0, "data": {"bnetId": "12345", "name": "GrowlRNew#9999"}},
                db=db,
            )

            self.assertEqual(inserted, 1)
            self.assertEqual(updated, 1)

            connection = sqlite3.connect(db_path)
            try:
                row = connection.execute(
                    f"""
                    SELECT bnetid, battletag, battlename, battlenum, update_time
                    FROM {PLAYER_IDENTITY_TABLE}
                    WHERE bnetid = ?
                    """,
                    ("12345",),
                ).fetchone()
            finally:
                connection.close()

            self.assertEqual(row[0], "12345")
            self.assertEqual(row[1], "GrowlRNew#9999")
            self.assertEqual(row[2], "GrowlRNew")
            self.assertEqual(row[3], "9999")
            self.assertGreater(int(row[4]), 0)

    async def test_search_identity_by_bnet_id_returns_ranked_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db = IDPoolDB(Path(temp_dir) / "match_stats.sqlite3")

            await record_identity_payload(
                {"code": 0, "data": {"bnetId": "1234", "name": "Exact#1234"}},
                db=db,
            )
            await record_identity_payload(
                {"code": 0, "data": {"bnetId": "12345", "name": "Prefix#12345"}},
                db=db,
            )
            await record_identity_payload(
                {"code": 0, "data": {"bnetId": "99123499", "name": "Contains#0001"}},
                db=db,
            )

            rows = await search_identity_by_bnet_id("1234", db=db, limit=10)

            self.assertEqual(
                [(row["bnetid"], row["match_type"], row["battletag"]) for row in rows],
                [
                    ("1234", "exact", "Exact#1234"),
                    ("12345", "prefix", "Prefix#12345"),
                    ("99123499", "contains", "Contains#0001"),
                ],
            )

    async def test_search_identity_by_bnet_id_supports_exact_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db = IDPoolDB(Path(temp_dir) / "match_stats.sqlite3")

            await record_identity_payload(
                {"code": 0, "data": {"bnetId": "1234", "name": "Exact#1234"}},
                db=db,
            )
            await record_identity_payload(
                {"code": 0, "data": {"bnetId": "12345", "name": "Prefix#12345"}},
                db=db,
            )

            rows = await search_identity_by_bnet_id("1234", db=db, limit=10, exact_only=True)

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["bnetid"], "1234")
            self.assertEqual(rows[0]["match_type"], "exact")


if __name__ == "__main__":
    unittest.main()
