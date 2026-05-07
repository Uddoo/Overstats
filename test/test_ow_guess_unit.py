from __future__ import annotations

import datetime as dt
from pathlib import Path
import random
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
PARENT_DIR = REPO_ROOT.parent
for candidate in (PARENT_DIR, REPO_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

try:
    from overstats.config import config as app_config
    from overstats.src.modules.errors import ModuleError
    from overstats.src.modules.ow_guess import OWGuessModule, OWGuessQuery
    from overstats.src.modules.ow_guess.catalog import OWGuessCatalog, OWGuessQuestionSelection, OWGuessTypeSpec
    from overstats.src.modules.ow_guess.render import RenderedImage, render_guess_image
except ModuleNotFoundError:
    from config import config as app_config
    from src.modules.errors import ModuleError
    from src.modules.ow_guess import OWGuessModule, OWGuessQuery
    from src.modules.ow_guess.catalog import OWGuessCatalog, OWGuessQuestionSelection, OWGuessTypeSpec
    from src.modules.ow_guess.render import RenderedImage, render_guess_image


LOCAL_CATALOG_TYPE_SLUGS = [
    "map_music",
    "skill_icon_hero",
    "perk_icon_hero",
    "ult_voice",
    "skill_icon_name",
    "hero_description",
]


class CatalogNormalizationTests(unittest.TestCase):
    def test_normalizes_slug_id_label_and_alias(self) -> None:
        catalog = OWGuessCatalog()
        cases = [
            ("skill_icon_hero", "skill_icon_hero"),
            (3, "skill_icon_hero"),
            ("技能图标猜英雄", "skill_icon_hero"),
            ("图标", "hero_icon"),
            ("终极语音", "ult_voice"),
        ]

        for raw_value, expected_slug in cases:
            with self.subTest(raw_value=raw_value):
                spec = catalog.resolve_question_type(raw_value)
                self.assertEqual(spec.slug, expected_slug)

    def test_rejects_unavailable_hero_conversation(self) -> None:
        catalog = OWGuessCatalog()

        with self.assertRaises(ModuleError) as ctx:
            catalog.resolve_question_type("英雄对话")

        self.assertEqual(ctx.exception.error, "ow_guess_type_unavailable")

    def test_rejects_missing_and_unknown_type(self) -> None:
        catalog = OWGuessCatalog()

        with self.assertRaises(ModuleError) as missing_ctx:
            catalog.resolve_question_type("")
        self.assertEqual(missing_ctx.exception.error, "ow_guess_invalid_type")

        with self.assertRaises(ModuleError) as unknown_ctx:
            catalog.resolve_question_type("not-a-real-type")
        self.assertEqual(unknown_ctx.exception.error, "ow_guess_invalid_type")


class ResourceIntegrityTests(unittest.TestCase):
    def test_supported_catalogs_and_assets_exist(self) -> None:
        catalog_root = REPO_ROOT / "res" / "ow_guess"
        configured_asset_root = Path(str(getattr(app_config, "OW_GUESS_ASSET_ROOT", "../ow_guess_assets")) or "../ow_guess_assets")
        asset_root = configured_asset_root if configured_asset_root.is_absolute() else (REPO_ROOT / configured_asset_root).resolve()

        for slug in LOCAL_CATALOG_TYPE_SLUGS:
            with self.subTest(question_type=slug):
                self.assertTrue((catalog_root / slug / "questions.json").exists())

        self.assertTrue((REPO_ROOT / "res" / "query_tool.json").exists())
        self.assertGreater(len(list((asset_root / "map_music" / "assets").glob("*.*"))), 0)
        self.assertGreater(len(list((asset_root / "ult_voice" / "assets").glob("*.*"))), 0)
        self.assertGreater(len(list((asset_root / "shared" / "hero_icons").rglob("Abilities/*.png"))), 0)
        self.assertGreater(len(list((asset_root / "shared" / "hero_icons").rglob("Perks/*.png"))), 0)
        self.assertTrue((asset_root / "hero_silhouette" / "whois_bg.jpg").exists())

    def test_module_files_do_not_reference_overshop(self) -> None:
        module_root = REPO_ROOT / "src" / "modules" / "ow_guess"
        for path in module_root.glob("*.py"):
            with self.subTest(path=path.name):
                content = path.read_text(encoding="utf-8")
                self.assertNotIn("overshop", content)


class CatalogSelectionTests(unittest.TestCase):
    def test_hero_description_selection_contains_hint_steps_and_aliases(self) -> None:
        catalog = OWGuessCatalog(random_source=random.Random(0))
        spec = catalog.resolve_question_type("hero_description")
        selection = catalog.pick_question(spec)

        self.assertEqual(selection.type_spec.slug, "hero_description")
        self.assertGreater(len(selection.hint_steps), 0)
        self.assertEqual(selection.hint_steps[0]["recommended_delay_seconds"], 10)
        self.assertIn(selection.answer_canonical, selection.answer_aliases)

    def test_remote_hero_icon_selection_comes_from_query_tool(self) -> None:
        catalog = OWGuessCatalog(random_source=random.Random(0))
        spec = catalog.resolve_question_type("hero_icon")
        selection = catalog.pick_question(spec)

        self.assertEqual(selection.type_spec.slug, "hero_icon")
        self.assertTrue(str(selection.payload.get("remote_url") or "").startswith("http"))
        self.assertIn(selection.answer_canonical, selection.answer_aliases)

    def test_local_pack_dependent_type_is_unavailable_without_external_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            catalog = OWGuessCatalog(resource_root=Path(temp_dir), random_source=random.Random(0))
            spec = catalog.resolve_question_type("skill_icon_hero")

            with self.assertRaises(ModuleError) as ctx:
                catalog.pick_question(spec)

        self.assertEqual(ctx.exception.error, "ow_guess_type_unavailable")
        self.assertEqual(ctx.exception.details.get("reason"), "local_asset_pack_missing")


class ModuleTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_local_question_types_return_expected_replies(self) -> None:
        module = OWGuessModule(
            random_source=random.Random(0),
            time_provider=lambda: dt.datetime(2026, 5, 7, 12, 0, 0),
        )

        map_music = await module.query_guess_replies(OWGuessQuery(question_type="map_music"))
        ult_voice = await module.query_guess_replies(OWGuessQuery(question_type="ult_voice"))
        hero_description = await module.query_guess_replies(OWGuessQuery(question_type="hero_description"))

        self.assertEqual(map_music.question_type, "map_music")
        self.assertEqual(map_music.recommended_wait_seconds, 60)
        self.assertEqual(map_music.replies[0]["type"], "text")
        self.assertEqual(map_music.replies[1]["type"], "audio")
        self.assertTrue(str(map_music.replies[1]["media_type"]).startswith("audio/"))

        self.assertEqual(ult_voice.question_type, "ult_voice")
        self.assertEqual(ult_voice.recommended_wait_seconds, 30)
        self.assertNotIn("?", ult_voice.question["prompt_text"])
        self.assertEqual(ult_voice.replies[1]["type"], "audio")

        self.assertEqual(hero_description.question_type, "hero_description")
        self.assertEqual(hero_description.recommended_wait_seconds, 60)
        self.assertEqual(len(hero_description.replies), 1)
        self.assertEqual(hero_description.replies[0]["type"], "text")
        self.assertGreater(len(hero_description.question["hint_steps"]), 0)
        self.assertIn(hero_description.answer["canonical"], hero_description.answer["aliases"])

    async def test_retries_same_type_when_resource_is_temporarily_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = Path(temp_dir) / "retry.ogg"
            audio_path.write_bytes(b"OggSretry")
            catalog = _RetryCatalog(audio_path)
            module = OWGuessModule(
                catalog=catalog,
                time_provider=lambda: dt.datetime(2026, 5, 7, 13, 0, 0),
            )

            result = await module.query_guess_replies(OWGuessQuery(question_type="map_music"))

        self.assertEqual(catalog.pick_count, 2)
        self.assertEqual(result.question_type, "map_music")
        self.assertEqual(result.replies[1]["type"], "audio")


class RenderSmokeTests(unittest.TestCase):
    def test_render_smoke_for_supported_image_types(self) -> None:
        try:
            from PIL import Image, ImageDraw
        except ModuleNotFoundError as exc:
            self.skipTest(str(exc))
            return

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            image_path = temp_root / "source.png"
            background_path = temp_root / "bg.png"

            source = Image.new("RGBA", (480, 480), (255, 255, 255, 0))
            draw = ImageDraw.Draw(source)
            draw.rectangle((40, 40, 440, 440), fill=(60, 120, 220, 255))
            draw.ellipse((120, 80, 360, 360), fill=(255, 180, 60, 255))
            source.save(image_path, format="PNG")

            background = Image.new("RGBA", (320, 320), (36, 42, 52, 255))
            background.save(background_path, format="PNG")

            cases = [
                {"question_type": "hero_icon"},
                {"question_type": "map_image"},
                {"question_type": "skill_icon_hero"},
                {"question_type": "perk_icon_hero"},
                {"question_type": "skill_icon_name"},
                {"question_type": "hero_silhouette", "background_path": str(background_path)},
            ]

            for selection in cases:
                with self.subTest(question_type=selection["question_type"]):
                    rendered = render_guess_image(selection, image_path, rng=random.Random(0))
                    self.assertIsInstance(rendered, RenderedImage)
                    self.assertTrue(rendered.content.startswith(b"\x89PNG\r\n\x1a\n"))
                    self.assertEqual(rendered.media_type, "image/png")


class _RetryCatalog:
    def __init__(self, audio_path: Path) -> None:
        self.audio_path = audio_path
        self.pick_count = 0
        self.type_spec = OWGuessTypeSpec(
            slug="map_music",
            type_id=1,
            label="地图音乐",
            aliases=("1",),
            media_kind="audio",
            recommended_wait_seconds=60,
        )

    def resolve_question_type(self, value: object) -> OWGuessTypeSpec:
        return self.type_spec

    def pick_question(self, type_spec: OWGuessTypeSpec) -> OWGuessQuestionSelection:
        self.pick_count += 1
        return OWGuessQuestionSelection(
            type_spec=type_spec,
            question_id=f"retry-{self.pick_count}",
            difficulty=3,
            prompt_text="请尝试猜出音乐对应的地图",
            answer_canonical="多拉多",
            answer_aliases=("多拉多",),
            hint_steps=(),
            payload={},
        )

    async def resolve_media_path(self, selection: OWGuessQuestionSelection) -> Path:
        if self.pick_count == 1:
            raise FileNotFoundError(selection.question_id)
        return self.audio_path


if __name__ == "__main__":
    unittest.main()
