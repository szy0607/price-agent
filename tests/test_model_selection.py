"""Model-name validation, fallback and listing normalisation. Pure functions, no database."""

import unittest

from app.models import UserApiKey
from app.services.chat_service import (
    MODEL_PROVIDERS,
    normalize_models,
    resolve_model_name,
    validate_model_name,
)


class ValidateModelNameTests(unittest.TestCase):
    def test_empty_values_mean_use_the_provider_default(self):
        for value in (None, "", "   ", "\t\n"):
            self.assertIsNone(validate_model_name(value))

    def test_real_provider_ids_are_accepted(self):
        for value in (
            "gpt-4o-mini",
            "gpt-4o-mini-2024-07-18",
            "claude-haiku-4-5",
            "deepseek-chat",
            "qwen2.5-72b-instruct",
            "kimi-k2:0.1",
            "Meta-Llama-3.1-70B-Instruct",
        ):
            self.assertEqual(validate_model_name(value), value)

    def test_the_length_bound_equals_the_column_width(self):
        # 校验上限和列宽必须一起改，否则要么静默截断、要么 128 字符的合法 id 存不下。
        self.assertEqual(len("a" * 128), 128)
        self.assertEqual(validate_model_name("a" * 128), "a" * 128)
        self.assertEqual(UserApiKey.__table__.c.model_name.type.length, 128)

    def test_surrounding_whitespace_is_trimmed(self):
        # 从网页上复制模型 id 常带首尾空白；先 strip 再校验，存进去的就是干净值。
        self.assertEqual(validate_model_name("  gpt-4o \n"), "gpt-4o")

    def test_junk_is_rejected(self):
        for value in (
            "gpt 4o",
            "gpt-4o;drop table",
            "gpt-4o\nwith tail",
            "\u200bgpt-4o",
            "-gpt-4o",
            ".gpt",
            "gpt-4o模型",
            "../evil",
            "a" * 129,
            123,
        ):
            with self.assertRaises(ValueError, msg=repr(value)):
                validate_model_name(value)


class ResolveModelNameTests(unittest.TestCase):
    def test_saved_choice_wins(self):
        self.assertEqual(resolve_model_name("openai", "gpt-4o"), "gpt-4o")

    def test_missing_or_blank_falls_back_to_the_provider_default(self):
        for provider, config in MODEL_PROVIDERS.items():
            for saved in (None, "", "   "):
                self.assertEqual(resolve_model_name(provider, saved), config["model"])

    def test_a_dirty_stored_value_never_reaches_the_request_body(self):
        # 列里可能是格式校验规则之前写入的，或有人在 SQL 里手改过的值。
        self.assertEqual(resolve_model_name("openai", "gpt-4o;curl evil"), "gpt-4o-mini")
        self.assertEqual(resolve_model_name("qwen", "a" * 500), "qwen-plus")


class NormalizeModelsTests(unittest.TestCase):
    def test_openai_shape_keeps_chat_models_and_drops_the_rest(self):
        payload = {"data": [
            {"id": "whisper-1"},
            {"id": "gpt-4o-mini"},
            {"id": "text-embedding-3-small"},
            {"id": "dall-e-3"},
            {"id": "gpt-4o-audio-preview"},
            {"id": "omni-moderation-latest"},
            {"id": "gpt-realtime-1.5"},
            {"id": "deepseek-chat"},
        ]}
        self.assertEqual(
            [item["id"] for item in normalize_models(payload)],
            ["deepseek-chat", "gpt-4o-mini"],
        )

    def test_qwen_generation_models_are_dropped_but_vision_chat_stays(self):
        payload = {"data": [
            {"id": "wanx2.1-t2i-turbo"},
            {"id": "wanx2.1-t2v-plus"},
            {"id": "gte-rerank-v2"},
            {"id": "qwen-plus"},
            # qwen-vl-* 是对话模型（可收图），不能按名字误杀
            {"id": "qwen-vl-plus"},
        ]}
        self.assertEqual([item["id"] for item in normalize_models(payload)], ["qwen-plus", "qwen-vl-plus"])

    def test_anthropic_display_name_becomes_the_label(self):
        payload = {"data": [
            {"id": "claude-3-5-sonnet-20241022", "display_name": "Claude 3.5 Sonnet"},
            {"id": "claude-haiku-4-5"},
        ], "has_more": True, "next_page": "cursor"}
        self.assertEqual(normalize_models(payload), [
            {"id": "claude-3-5-sonnet-20241022", "label": "Claude 3.5 Sonnet"},
            {"id": "claude-haiku-4-5", "label": "claude-haiku-4-5"},
        ])

    def test_unusable_ids_are_skipped_not_raised(self):
        self.assertEqual(normalize_models({"data": []}), [])
        self.assertEqual(normalize_models({"data": [{"id": 123}, {"id": ""}, {"nope": 1}, "gpt-4o", None]}), [])
        # 存不下的 id（含空格）不能出现在列表里，否则用户选中它却在保存时被拒。
        self.assertEqual(normalize_models({"data": [{"id": "gpt 4o"}]}), [])

    def test_duplicates_are_collapsed(self):
        payload = {"data": [{"id": "deepseek-chat"}, {"id": "deepseek-chat"}]}
        self.assertEqual(len(normalize_models(payload)), 1)

    def test_the_list_is_capped(self):
        payload = {"data": [{"id": f"model-{index}"} for index in range(500)]}
        self.assertEqual(len(normalize_models(payload)), 200)

    def test_a_payload_that_is_not_a_listing_is_an_error_not_a_crash(self):
        for payload in ({}, [], {"data": "x"}, {"data": None}, None, "models"):
            with self.assertRaises(ValueError, msg=repr(payload)):
                normalize_models(payload)


if __name__ == "__main__":
    unittest.main()
