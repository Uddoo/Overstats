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
    from overstats.src.modules.dashen_hero_leaderboard import (
        DashenHeroLeaderboardModule,
        DashenHeroLeaderboardQuery,
        render_hero_leaderboard,
    )
    from overstats.src.modules.errors import ModuleError
except ModuleNotFoundError:
    from src.modules.dashen_hero_leaderboard import (
        DashenHeroLeaderboardModule,
        DashenHeroLeaderboardQuery,
        render_hero_leaderboard,
    )
    from src.modules.errors import ModuleError


try:
    import PIL  # noqa: F401
except ModuleNotFoundError:
    PIL_AVAILABLE = False
else:
    PIL_AVAILABLE = True


def _query_tool_payload():
    return {
        "heroList": [
            {
                "heroGuid": "tracer-guid",
                "name": "猎空",
                "roleType": "dps",
                "smallIconUrl": "",
            },
            {
                "heroGuid": "ana-guid",
                "name": "安娜",
                "roleType": "healer",
                "smallIconUrl": "",
            },
        ],
        "heroConfig": {
            "tracer-guid": {"Name": "猎空", "Color": "#F59E0BFF"},
            "ana-guid": {"Name": "安娜", "Color": "#60A5FAFF"},
        },
    }


class DashenHeroLeaderboardModuleTests(unittest.IsolatedAsyncioTestCase):
    async def test_mode_alias_and_hero_alias_normalize_and_sort(self) -> None:
        requests = _StubHeroLeaderboardRequests(
            {
                "itemList": [
                    {
                        "rankNum": 3,
                        "userName": "DiamondThree",
                        "matchSum": 9,
                        "winRate": 66.7,
                        "rankedLevel": 3120,
                    },
                    {
                        "rankNum": 2,
                        "userName": "TracerTwo",
                        "matchSum": 5,
                        "winRate": 60,
                        "rankedLevel": 4550,
                    },
                    {
                        "rankNum": 1,
                        "userName": "TracerOne",
                        "matchSum": 10,
                        "winRate": 80,
                        "rankedLevel": 4550,
                    },
                ]
            }
        )
        module = DashenHeroLeaderboardModule(requests=requests, config_loader=_query_tool_payload)

        result = await module.query_hero_leaderboard(
            DashenHeroLeaderboardQuery(province="北京", hero="Tracer", mode="开放"),
            render=False,
        )

        self.assertEqual(requests.calls, [("北京", "open", "tracer-guid")])
        self.assertEqual(result.province, "北京")
        self.assertEqual(result.mode, "open")
        self.assertEqual(result.mode_label, "开放")
        self.assertEqual(result.hero.hero_guid, "tracer-guid")
        self.assertEqual(result.hero.hero_name, "猎空")
        self.assertEqual(result.hero.accent_color, "#F59E0BFF")
        self.assertEqual(result.groups[0].rank_label, "英杰5")
        self.assertEqual([item.user_name for item in result.groups[0].entries], ["TracerOne", "TracerTwo"])
        self.assertEqual(result.groups[0].entries[0].wins, 8)
        self.assertEqual(result.groups[1].rank_label, "钻石4")

    async def test_hero_guid_and_default_mode_are_accepted(self) -> None:
        requests = _StubHeroLeaderboardRequests({"itemList": [_hero_row("GuidUser", 1, 2500, 6, 50.0)]})
        module = DashenHeroLeaderboardModule(requests=requests, config_loader=_query_tool_payload)

        result = await module.query_hero_leaderboard(
            DashenHeroLeaderboardQuery(province="北京", hero="tracer-guid"),
            render=False,
        )

        self.assertEqual(requests.calls, [("北京", "preset", "tracer-guid")])
        self.assertEqual(result.mode, "preset")
        self.assertEqual(result.hero.hero_name, "猎空")

    async def test_missing_province_raises_expected_error(self) -> None:
        module = DashenHeroLeaderboardModule(
            requests=_StubHeroLeaderboardRequests({"itemList": []}),
            config_loader=_query_tool_payload,
        )

        with self.assertRaises(ModuleError) as context:
            await module.query_hero_leaderboard(DashenHeroLeaderboardQuery(hero="Tracer"), render=False)

        self.assertEqual(context.exception.error, "missing_province")
        self.assertEqual(context.exception.status_code, 400)

    async def test_missing_hero_raises_expected_error(self) -> None:
        module = DashenHeroLeaderboardModule(
            requests=_StubHeroLeaderboardRequests({"itemList": []}),
            config_loader=_query_tool_payload,
        )

        with self.assertRaises(ModuleError) as context:
            await module.query_hero_leaderboard(DashenHeroLeaderboardQuery(province="北京"), render=False)

        self.assertEqual(context.exception.error, "missing_hero")
        self.assertEqual(context.exception.status_code, 400)

    async def test_invalid_mode_raises_expected_error(self) -> None:
        module = DashenHeroLeaderboardModule(
            requests=_StubHeroLeaderboardRequests({"itemList": []}),
            config_loader=_query_tool_payload,
        )

        with self.assertRaises(ModuleError) as context:
            await module.query_hero_leaderboard(
                DashenHeroLeaderboardQuery(province="北京", hero="Tracer", mode="arcade"),
                render=False,
            )

        self.assertEqual(context.exception.error, "invalid_mode")
        self.assertEqual(context.exception.status_code, 400)

    async def test_unknown_hero_raises_expected_error(self) -> None:
        module = DashenHeroLeaderboardModule(
            requests=_StubHeroLeaderboardRequests({"itemList": []}),
            config_loader=_query_tool_payload,
        )

        with self.assertRaises(ModuleError) as context:
            await module.query_hero_leaderboard(
                DashenHeroLeaderboardQuery(province="北京", hero="UnknownHero"),
                render=False,
            )

        self.assertEqual(context.exception.error, "hero_leaderboard_hero_not_found")
        self.assertEqual(context.exception.status_code, 404)

    async def test_empty_item_list_raises_expected_error(self) -> None:
        module = DashenHeroLeaderboardModule(
            requests=_StubHeroLeaderboardRequests({"itemList": []}),
            config_loader=_query_tool_payload,
        )

        with self.assertRaises(ModuleError) as context:
            await module.query_hero_leaderboard(
                DashenHeroLeaderboardQuery(province="北京", hero="Tracer", mode="preset"),
                render=False,
            )

        self.assertEqual(context.exception.error, "dashen_hero_leaderboard_empty")
        self.assertEqual(context.exception.status_code, 404)


@unittest.skipUnless(PIL_AVAILABLE, "Pillow required for render smoke tests")
class DashenHeroLeaderboardRenderTests(unittest.TestCase):
    def test_render_hero_leaderboard_returns_png(self) -> None:
        result = render_hero_leaderboard(
            province="北京",
            hero={
                "hero_guid": "tracer-guid",
                "hero_name": "猎空",
                "hero_role": "dps",
                "icon_url": "",
                "accent_color": "#F59E0BFF",
            },
            mode_label="预设",
            entry_count=2,
            groups=[
                {
                    "rank_label": "英杰5",
                    "rank_icon_level": 8,
                    "count": 2,
                    "entries": [
                        {
                            "rank_num": 1,
                            "user_name": "TracerOne",
                            "match_sum": 10,
                            "win_rate": 80.0,
                            "wins": 8,
                            "ranked_level": 4550,
                        },
                        {
                            "rank_num": 2,
                            "user_name": "TracerTwo",
                            "match_sum": 5,
                            "win_rate": 60.0,
                            "wins": 3,
                            "ranked_level": 4520,
                        },
                    ],
                }
            ],
        )

        self.assertEqual(result.media_type, "image/png")
        self.assertTrue(result.content.startswith(b"\x89PNG\r\n\x1a\n"))


def _hero_row(name, rank_num, ranked_level, match_sum, win_rate):  # noqa: ANN001
    return {
        "rankNum": rank_num,
        "userName": name,
        "matchSum": match_sum,
        "winRate": win_rate,
        "rankedLevel": ranked_level,
    }


class _StubHeroLeaderboardRequests:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    async def query_hero_leaderboard(self, province, mode, hero_guid):  # noqa: ANN001
        self.calls.append((province, mode, hero_guid))
        return dict(self.payload)


if __name__ == "__main__":
    unittest.main()
