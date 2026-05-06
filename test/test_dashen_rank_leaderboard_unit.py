from __future__ import annotations

from pathlib import Path
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
PARENT_DIR = REPO_ROOT.parent
for candidate in (PARENT_DIR, REPO_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

try:
    from overstats.src.modules.dashen_rank_leaderboard import (
        DashenRankLeaderboardModule,
        DashenRankLeaderboardQuery,
        render_rank_leaderboard,
    )
    from overstats.src.modules.errors import ModuleError
except ModuleNotFoundError:
    from src.modules.dashen_rank_leaderboard import (
        DashenRankLeaderboardModule,
        DashenRankLeaderboardQuery,
        render_rank_leaderboard,
    )
    from src.modules.errors import ModuleError


try:
    import PIL  # noqa: F401
except ModuleNotFoundError:
    PIL_AVAILABLE = False
else:
    PIL_AVAILABLE = True


class DashenRankLeaderboardModuleTests(unittest.IsolatedAsyncioTestCase):
    async def test_role_alias_normalizes_and_groups_sorted_entries(self) -> None:
        requests = _StubRankLeaderboardRequests(
            {
                "rankList": [
                    {
                        "rankNum": 3,
                        "name": "DiamondThree",
                        "matchSum": 7,
                        "winRate": 57.14,
                        "rankInfo": {"rankScore": 3120},
                    },
                    {
                        "rankNum": 2,
                        "name": "ChampionTwo",
                        "matchSum": 5,
                        "winRate": 80,
                        "rankInfo": {"rankScore": 4550},
                    },
                    {
                        "rankNum": 1,
                        "name": "ChampionOne",
                        "matchSum": 10,
                        "winRate": 70,
                        "rankInfo": {"rankScore": 4550},
                    },
                ]
            }
        )
        module = DashenRankLeaderboardModule(requests=requests)

        result = await module.query_rank_leaderboard(
            DashenRankLeaderboardQuery(province="北京", role="支援"),
            render=False,
        )

        self.assertEqual(requests.calls, [("北京", "healer")])
        self.assertEqual(result.province, "北京")
        self.assertEqual(result.role, "healer")
        self.assertEqual(result.role_label, "支援")
        self.assertEqual(result.entry_count, 3)
        self.assertEqual(result.groups[0].rank_label, "英杰5")
        self.assertEqual(result.groups[0].rank_icon_level, 8)
        self.assertEqual([item.user_name for item in result.groups[0].entries], ["ChampionOne", "ChampionTwo"])
        self.assertEqual(result.groups[0].entries[0].wins, 7)
        self.assertEqual(result.groups[1].rank_label, "钻石4")
        self.assertEqual(result.to_dict()["groups"][1]["entries"][0]["rank_score"], 3120)

    async def test_missing_province_raises_expected_error(self) -> None:
        module = DashenRankLeaderboardModule(requests=_StubRankLeaderboardRequests({"rankList": []}))

        with self.assertRaises(ModuleError) as context:
            await module.query_rank_leaderboard(DashenRankLeaderboardQuery(role="tank"), render=False)

        self.assertEqual(context.exception.error, "missing_province")
        self.assertEqual(context.exception.status_code, 400)

    async def test_missing_role_raises_expected_error(self) -> None:
        module = DashenRankLeaderboardModule(requests=_StubRankLeaderboardRequests({"rankList": []}))

        with self.assertRaises(ModuleError) as context:
            await module.query_rank_leaderboard(DashenRankLeaderboardQuery(province="北京"), render=False)

        self.assertEqual(context.exception.error, "missing_role")
        self.assertEqual(context.exception.status_code, 400)

    async def test_invalid_role_raises_expected_error(self) -> None:
        module = DashenRankLeaderboardModule(requests=_StubRankLeaderboardRequests({"rankList": []}))

        with self.assertRaises(ModuleError) as context:
            await module.query_rank_leaderboard(
                DashenRankLeaderboardQuery(province="北京", role="flex"),
                render=False,
            )

        self.assertEqual(context.exception.error, "invalid_role")
        self.assertEqual(context.exception.status_code, 400)

    async def test_empty_rank_list_raises_expected_error(self) -> None:
        module = DashenRankLeaderboardModule(requests=_StubRankLeaderboardRequests({"rankList": []}))

        with self.assertRaises(ModuleError) as context:
            await module.query_rank_leaderboard(
                DashenRankLeaderboardQuery(province="北京", role="tank"),
                render=False,
            )

        self.assertEqual(context.exception.error, "dashen_rank_leaderboard_empty")
        self.assertEqual(context.exception.status_code, 404)


@unittest.skipUnless(PIL_AVAILABLE, "Pillow required for render smoke tests")
class DashenRankLeaderboardRenderTests(unittest.TestCase):
    def test_render_rank_leaderboard_returns_png(self) -> None:
        result = render_rank_leaderboard(
            province="北京",
            role_label="重装",
            entry_count=2,
            groups=[
                {
                    "rank_label": "英杰5",
                    "rank_icon_level": 8,
                    "count": 2,
                    "entries": [
                        {
                            "rank_num": 1,
                            "user_name": "RankOne",
                            "match_sum": 10,
                            "win_rate": 70.0,
                            "wins": 7,
                            "rank_score": 4550,
                        },
                        {
                            "rank_num": 2,
                            "user_name": "RankTwo",
                            "match_sum": 8,
                            "win_rate": 62.5,
                            "wins": 5,
                            "rank_score": 4520,
                        },
                    ],
                }
            ],
        )

        self.assertEqual(result.media_type, "image/png")
        self.assertTrue(result.content.startswith(b"\x89PNG\r\n\x1a\n"))


class _StubRankLeaderboardRequests:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    async def query_province_rank(self, province, role):  # noqa: ANN001
        self.calls.append((province, role))
        return dict(self.payload)


if __name__ == "__main__":
    unittest.main()
